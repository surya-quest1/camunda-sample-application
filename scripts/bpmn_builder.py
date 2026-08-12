"""
Minimal BPMN 2.0 + Zeebe extension XML builder.

Not a general-purpose BPMN library -- just enough element/attribute coverage
to author the Northwind Private Bank reference-app processes, matching
exactly the vocabulary the Camunda assessment-tool's pkg/bpmnanalyser parses
(namespace URIs and attribute names taken directly from that package's
source, not guessed).

No BPMNDI (diagram interchange) is emitted -- bpmnanalyser.Parse never reads
it, and Zeebe does not require it to deploy or execute a process. This
keeps every file to its semantic content only.
"""
import xml.etree.ElementTree as ET

NS_BPMN = "http://www.omg.org/spec/BPMN/20100524/MODEL"
NS_ZEEBE = "http://camunda.org/schema/zeebe/1.0"
NS_DI = "http://www.omg.org/spec/BPMN/20100524/DI"
NS_XSI = "http://www.w3.org/2001/XMLSchema-instance"

ET.register_namespace("bpmn", NS_BPMN)
ET.register_namespace("zeebe", NS_ZEEBE)
ET.register_namespace("xsi", NS_XSI)


def q(ns, local):
    return f"{{{ns}}}{local}"


def B(local):
    return q(NS_BPMN, local)


def Z(local):
    return q(NS_ZEEBE, local)


class Definitions:
    """Root <bpmn:definitions> for one deployable .bpmn file."""

    def __init__(self, def_id):
        self.root = ET.Element(
            B("definitions"),
            {
                "id": def_id,
                "targetNamespace": "http://northwind-private-bank.example.com/bpmn",
                "exporter": "northwind-reference-app",
                "exporterVersion": "1.0",
            },
        )
        self._processes = []

    def message(self, msg_id, name, correlation_key=None):
        el = ET.SubElement(self.root, B("message"), {"id": msg_id, "name": name})
        if correlation_key:
            ext = ET.SubElement(el, B("extensionElements"))
            ET.SubElement(ext, Z("subscription"), {"correlationKey": correlation_key})
        return msg_id

    def signal(self, sig_id, name):
        ET.SubElement(self.root, B("signal"), {"id": sig_id, "name": name})
        return sig_id

    def error(self, error_id, error_code, name=None):
        attrs = {"id": error_id, "errorCode": error_code}
        if name:
            attrs["name"] = name
        ET.SubElement(self.root, B("error"), attrs)
        return error_id

    def escalation(self, esc_id, escalation_code, name=None):
        attrs = {"id": esc_id, "escalationCode": escalation_code}
        if name:
            attrs["name"] = name
        ET.SubElement(self.root, B("escalation"), attrs)
        return esc_id

    def process(self, process_id, name, executable=True):
        p = Process(process_id, name, executable)
        self.root.append(p.el)
        self._processes.append(p)
        return p

    def collaboration(self, collab_id, pool_refs):
        """A minimal <bpmn:collaboration> wrapping N processes into pools --
        only used by the F01/F02 two-pool spike fixture. pool_refs is a
        list of (process_id, participant_name) tuples; the collaboration
        element must precede the process elements per BPMN convention, so
        callers build processes first then call this."""
        collab = ET.Element(B("collaboration"), {"id": collab_id})
        for i, (pid, pname) in enumerate(pool_refs):
            ET.SubElement(
                collab,
                B("participant"),
                {"id": f"Participant_{i}", "name": pname, "processRef": pid},
            )
        self.root.insert(0, collab)

    def tostring(self):
        _inject_incoming_outgoing(self.root)
        ET.indent(self.root, space="  ")
        xml_bytes = ET.tostring(self.root, encoding="unicode", xml_declaration=False)
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_bytes + "\n"


# Flow-node element local names that can carry <bpmn:incoming>/<bpmn:outgoing>
# children. Sequence flows, gateways' sub-elements, artifacts, and event/
# message/signal/error root definitions are excluded.
_FLOW_NODE_LOCALS = {
    "startEvent", "endEvent", "intermediateCatchEvent", "intermediateThrowEvent",
    "boundaryEvent", "serviceTask", "userTask", "scriptTask", "businessRuleTask",
    "sendTask", "receiveTask", "manualTask", "task", "exclusiveGateway",
    "parallelGateway", "inclusiveGateway", "eventBasedGateway", "complexGateway",
    "callActivity", "subProcess", "adHocSubProcess",
}


def _inject_incoming_outgoing(root):
    """Adds explicit <bpmn:incoming>/<bpmn:outgoing> children to every flow
    node, derived from <bpmn:sequenceFlow> sourceRef/targetRef anywhere in
    the tree (including nested subprocesses).

    Required because Zeebe's EventBasedGatewayValidator resolves a gateway's
    outgoing flows via FlowNode.getOutgoing() -- which reads these explicit
    child elements, not sourceRef/targetRef attribute matching. Other
    Zeebe-side gateway execution logic tolerates their absence, which is why
    exclusive/parallel gateways deploy fine without them; event-based
    gateways are the one construct where Camunda's own bpmn-model API
    requires the BPMN-spec-standard (if usually redundant, and normally
    written by every real modelling tool) incoming/outgoing elements to be
    physically present. Added for every flow node, not just event-based
    gateways, for full spec compliance.
    """
    by_id = {}
    for el in root.iter():
        eid = el.get("id")
        if eid:
            by_id[eid] = el

    incoming = {}
    outgoing = {}
    for flow in root.iter(B("sequenceFlow")):
        fid = flow.get("id")
        source, target = flow.get("sourceRef"), flow.get("targetRef")
        if source:
            outgoing.setdefault(source, []).append(fid)
        if target:
            incoming.setdefault(target, []).append(fid)

    for eid, el in by_id.items():
        if el.tag not in {B(l) for l in _FLOW_NODE_LOCALS}:
            continue
        # Insert position: right after <bpmn:extensionElements> if present
        # (BPMN content model: extensionElements?, incoming*, outgoing*, ...).
        pos = 1 if len(el) and el[0].tag == B("extensionElements") else 0
        for fid in reversed(outgoing.get(eid, [])):
            e = ET.Element(B("outgoing"))
            e.text = fid
            el.insert(pos, e)
        for fid in reversed(incoming.get(eid, [])):
            e = ET.Element(B("incoming"))
            e.text = fid
            el.insert(pos, e)


class Process:
    """A <bpmn:process> (or nested subProcess/adHocSubProcess) container."""

    def __init__(self, process_id, name, executable=True, el=None, tag="process"):
        if el is not None:
            self.el = el
        else:
            self.el = ET.Element(
                B(tag),
                {"id": process_id, "name": name, "isExecutable": "true" if executable else "false"},
            )
        self.id = process_id

    # ---- extension-elements helper -------------------------------------

    def _ext(self, el):
        """Return (creating if absent) el's <bpmn:extensionElements>, always
        as the first child, matching Camunda Modeler output ordering."""
        ext = el.find(B("extensionElements"))
        if ext is None:
            ext = ET.Element(B("extensionElements"))
            el.insert(0, ext)
        return ext

    def _task_definition(self, el, job_type, retries=None, headers=None, job_priority=None):
        ext = self._ext(el)
        attrs = {"type": job_type}
        if retries is not None:
            attrs["retries"] = str(retries)
        ET.SubElement(ext, Z("taskDefinition"), attrs)
        if headers:
            th = ET.SubElement(ext, Z("taskHeaders"))
            for k, v in headers.items():
                ET.SubElement(th, Z("header"), {"key": k, "value": v})
        if job_priority is not None:
            ET.SubElement(ext, Z("jobPriorityDefinition"), {"priority": str(job_priority)})

    def _io_mapping(self, el, io_in=None, io_out=None):
        if not io_in and not io_out:
            return
        ext = self._ext(el)
        io = ET.SubElement(ext, Z("ioMapping"))
        for source, target in (io_in or {}).items():
            ET.SubElement(io, Z("input"), {"source": source, "target": target})
        for source, target in (io_out or {}).items():
            ET.SubElement(io, Z("output"), {"source": source, "target": target})

    # ---- tasks ------------------------------------------------------------

    def service_task(self, tid, name, job_type, retries=None, headers=None,
                      io_in=None, io_out=None, job_priority=None, modeler_template=None):
        attrs = {"id": tid, "name": name}
        if modeler_template:
            # zeebe:modelerTemplate, not a bare attribute -- Zeebe's deploy
            # XSD rejects an unprefixed "modelerTemplate" on bpmn:serviceTask.
            attrs[Z("modelerTemplate")] = modeler_template
        el = ET.SubElement(self.el, B("serviceTask"), attrs)
        self._task_definition(el, job_type, retries, headers, job_priority)
        self._io_mapping(el, io_in, io_out)
        return tid

    def send_task(self, tid, name, job_type, retries=None):
        el = ET.SubElement(self.el, B("sendTask"), {"id": tid, "name": name})
        self._task_definition(el, job_type, retries)
        return tid

    def receive_task(self, tid, name, message_ref):
        ET.SubElement(self.el, B("receiveTask"), {"id": tid, "name": name, "messageRef": message_ref})
        return tid

    def manual_task(self, tid, name):
        ET.SubElement(self.el, B("manualTask"), {"id": tid, "name": name})
        return tid

    def undefined_task(self, tid, name):
        ET.SubElement(self.el, B("task"), {"id": tid, "name": name})
        return tid

    def user_task_zeebe(self, tid, name, assignee=None, candidate_users=None,
                         candidate_groups=None, due_date=None, follow_up_date=None,
                         priority=None, form_id=None):
        """Native Zeebe user task -- <zeebe:userTask/> marker present."""
        el = ET.SubElement(self.el, B("userTask"), {"id": tid, "name": name})
        ext = self._ext(el)
        ET.SubElement(ext, Z("userTask"))
        if assignee or candidate_users or candidate_groups:
            ad = {}
            if assignee:
                ad["assignee"] = assignee
            if candidate_users:
                ad["candidateUsers"] = candidate_users
            if candidate_groups:
                ad["candidateGroups"] = candidate_groups
            ET.SubElement(ext, Z("assignmentDefinition"), ad)
        if due_date or follow_up_date:
            ts = {}
            if due_date:
                ts["dueDate"] = due_date
            if follow_up_date:
                ts["followUpDate"] = follow_up_date
            ET.SubElement(ext, Z("taskSchedule"), ts)
        if priority is not None:
            ET.SubElement(ext, Z("priorityDefinition"), {"priority": str(priority)})
        if form_id:
            ET.SubElement(ext, Z("formDefinition"), {"formId": form_id})
        return tid

    def user_task_job_worker(self, tid, name, job_type):
        """Old-style user task: zeebe:taskDefinition, no zeebe:userTask marker.
        IsZeebeUserTask resolves false; parity with P02's design intent."""
        el = ET.SubElement(self.el, B("userTask"), {"id": tid, "name": name})
        self._task_definition(el, job_type)
        return tid

    def script_task_in_broker(self, tid, name, expression, result_variable):
        el = ET.SubElement(self.el, B("scriptTask"), {"id": tid, "name": name})
        ext = self._ext(el)
        ET.SubElement(ext, Z("script"), {"expression": expression, "resultVariable": result_variable})
        return tid

    def script_task_job_worker(self, tid, name, job_type, retries=None):
        el = ET.SubElement(self.el, B("scriptTask"), {"id": tid, "name": name})
        self._task_definition(el, job_type, retries)
        return tid

    def business_rule_task_in_broker(self, tid, name, decision_id, result_variable, binding_type=None):
        el = ET.SubElement(self.el, B("businessRuleTask"), {"id": tid, "name": name})
        ext = self._ext(el)
        attrs = {"decisionId": decision_id, "resultVariable": result_variable}
        if binding_type:
            attrs["bindingType"] = binding_type
        ET.SubElement(ext, Z("calledDecision"), attrs)
        return tid

    def business_rule_task_job_worker(self, tid, name, job_type, retries=None):
        el = ET.SubElement(self.el, B("businessRuleTask"), {"id": tid, "name": name})
        self._task_definition(el, job_type, retries)
        return tid

    def mark_compensation_handler(self, tid):
        """Flag an already-created element (by id) as isForCompensation."""
        el = self.el.find(f'.//*[@id="{tid}"]')
        if el is not None:
            el.set("isForCompensation", "true")

    def association(self, aid, source, target):
        """<bpmn:association> -- required to link a compensation boundary
        event to its handler; Zeebe's deploy validator rejects a
        compensation boundary event without one."""
        ET.SubElement(self.el, B("association"),
                      {"id": aid, "sourceRef": source, "targetRef": target, "associationDirection": "None"})
        return aid

    # ---- multi-instance -----------------------------------------------

    def multi_instance(self, tid, sequential, input_collection, input_element,
                        output_collection=None, output_element=None, completion_condition=None):
        el = self.el.find(f'.//*[@id="{tid}"]')
        mi = ET.SubElement(el, B("multiInstanceLoopCharacteristics"),
                            {"isSequential": "true" if sequential else "false"})
        ext = ET.SubElement(mi, B("extensionElements"))
        lc_attrs = {"inputCollection": input_collection, "inputElement": input_element}
        if output_collection:
            lc_attrs["outputCollection"] = output_collection
        if output_element:
            lc_attrs["outputElement"] = output_element
        ET.SubElement(ext, Z("loopCharacteristics"), lc_attrs)
        if completion_condition:
            cc = ET.SubElement(mi, B("completionCondition"))
            cc.text = completion_condition

    # ---- gateways / flow ------------------------------------------------

    def gateway(self, gid, name, kind, default=None):
        tag = {
            "exclusive": "exclusiveGateway",
            "parallel": "parallelGateway",
            "inclusive": "inclusiveGateway",
            "eventBased": "eventBasedGateway",
            "complex": "complexGateway",
        }[kind]
        attrs = {"id": gid, "name": name}
        if default:
            attrs["default"] = default
        ET.SubElement(self.el, B(tag), attrs)
        return gid

    def flow(self, fid, source, target, condition=None, name=None):
        attrs = {"id": fid, "sourceRef": source, "targetRef": target}
        if name:
            attrs["name"] = name
        el = ET.SubElement(self.el, B("sequenceFlow"), attrs)
        if condition:
            cond = ET.SubElement(el, B("conditionExpression"), {q(NS_XSI, "type"): "bpmn:tFormalExpression"})
            cond.text = condition
        return fid

    # ---- events -----------------------------------------------------------

    def start_event(self, eid, name, kind="none", interrupting=True, **kw):
        el = ET.SubElement(self.el, B("startEvent"), {"id": eid, "name": name})
        if not interrupting:
            el.set("isInterrupting", "false")
        self._event_definition(el, kind, **kw)
        return eid

    def end_event(self, eid, name, kind="none", **kw):
        el = ET.SubElement(self.el, B("endEvent"), {"id": eid, "name": name})
        self._event_definition(el, kind, **kw)
        return eid

    def intermediate_catch_event(self, eid, name, kind, **kw):
        el = ET.SubElement(self.el, B("intermediateCatchEvent"), {"id": eid, "name": name})
        self._event_definition(el, kind, **kw)
        return eid

    def intermediate_throw_event(self, eid, name, kind, **kw):
        el = ET.SubElement(self.el, B("intermediateThrowEvent"), {"id": eid, "name": name})
        self._event_definition(el, kind, **kw)
        return eid

    def boundary_event(self, eid, name, attached_to, kind, cancel_activity=True, **kw):
        el = ET.SubElement(self.el, B("boundaryEvent"),
                            {"id": eid, "name": name, "attachedToRef": attached_to})
        if not cancel_activity:
            el.set("cancelActivity", "false")
        self._event_definition(el, kind, **kw)
        return eid

    def _event_definition(self, el, kind, **kw):
        if kind == "none":
            return
        # Every event definition gets an explicit, unique id. Confirmed by
        # direct testing against a live Zeebe 8.8.34 cluster: an omitted id
        # on <bpmn:compensateEventDefinition> crashes the deploy validator
        # with an internal NullPointerException ("Cannot invoke
        # String.getBytes(...) because value is null") instead of a clean
        # rejection -- CatchEventTransformer.transformCompensationEventDefinition
        # calls eventDefinition.getId() unconditionally when building
        # ExecutableCompensation. Applied to every kind here as a general
        # robustness measure, not just compensation, since other definition
        # types plausibly share the same latent assumption.
        def_id = kw.get("def_id", el.get("id") + "_def")
        if kind == "timer":
            d = ET.SubElement(el, B("timerEventDefinition"), {"id": def_id})
            timer_type = kw["timer_type"]  # timeDate | timeDuration | timeCycle
            v = ET.SubElement(d, B(timer_type))
            v.text = kw["value"]
        elif kind == "message":
            # Zeebe 8.8 requires a throw/end message event to carry either
            # zeebe:publishMessage (newer, undocumented at authoring time)
            # or zeebe:taskDefinition (job-worker-completed throw) -- catch
            # positions (start/intermediateCatch/boundary) need neither.
            if kw.get("job_type"):
                ext = ET.SubElement(el, B("extensionElements"))
                ET.SubElement(ext, Z("taskDefinition"), {"type": kw["job_type"]})
            ET.SubElement(el, B("messageEventDefinition"), {"id": def_id, "messageRef": kw["message_ref"]})
        elif kind == "signal":
            ET.SubElement(el, B("signalEventDefinition"), {"id": def_id, "signalRef": kw["signal_ref"]})
        elif kind == "error":
            attrs = {"id": def_id}
            if kw.get("error_ref"):
                attrs["errorRef"] = kw["error_ref"]
            ET.SubElement(el, B("errorEventDefinition"), attrs)
        elif kind == "escalation":
            attrs = {"id": def_id}
            if kw.get("escalation_ref"):
                attrs["escalationRef"] = kw["escalation_ref"]
            ET.SubElement(el, B("escalationEventDefinition"), attrs)
        elif kind == "terminate":
            ET.SubElement(el, B("terminateEventDefinition"), {"id": def_id})
        elif kind == "compensation":
            attrs = {"id": def_id}
            if kw.get("activity_ref"):
                attrs["activityRef"] = kw["activity_ref"]
            ET.SubElement(el, B("compensateEventDefinition"), attrs)
        elif kind == "link":
            ET.SubElement(el, B("linkEventDefinition"), {"id": def_id, "name": kw["link_name"]})
        elif kind == "conditional":
            d = ET.SubElement(el, B("conditionalEventDefinition"), {"id": def_id})
            cond = ET.SubElement(d, B("condition"), {q(NS_XSI, "type"): "bpmn:tFormalExpression"})
            cond.text = kw["condition"]
        else:
            raise ValueError(f"unknown event kind {kind!r}")

    # ---- call activity ------------------------------------------------

    def call_activity(self, cid, name, called_process_id, binding_type=None,
                       version_tag=None, propagate_parent=None, propagate_child=None,
                       io_in=None, io_out=None):
        el = ET.SubElement(self.el, B("callActivity"), {"id": cid, "name": name})
        ext = self._ext(el)
        attrs = {"processId": called_process_id}
        if binding_type:
            attrs["bindingType"] = binding_type
        if version_tag:
            attrs["versionTag"] = version_tag
        if propagate_parent is not None:
            attrs["propagateAllParentVariables"] = "true" if propagate_parent else "false"
        if propagate_child is not None:
            attrs["propagateAllChildVariables"] = "true" if propagate_child else "false"
        ET.SubElement(ext, Z("calledElement"), attrs)
        self._io_mapping(el, io_in, io_out)
        return cid

    # ---- subprocesses ---------------------------------------------------

    def sub_process(self, sid, name, triggered_by_event=False):
        attrs = {"id": sid, "name": name}
        if triggered_by_event:
            attrs["triggeredByEvent"] = "true"
        el = ET.SubElement(self.el, B("subProcess"), attrs)
        return Process(sid, name, el=el, tag="subProcess")

    def ad_hoc_sub_process(self, sid, name):
        el = ET.SubElement(self.el, B("adHocSubProcess"), {"id": sid, "name": name})
        return Process(sid, name, el=el, tag="adHocSubProcess")
