// Standalone validator: parses a .bpmn file with the real
// camunda-assessment-tool bpmnanalyser package (read-only dependency on the
// shinro repo, via a go.mod replace directive -- nothing in shinro is
// modified) and dumps the resulting element census as JSON, so the
// reference-app's BPMN authoring can be checked against the actual parser
// rather than against a re-reading of its source.
package main

import (
	"encoding/json"
	"fmt"
	"os"

	"camunda-assessment-tool/pkg/bpmnanalyser"
	"camunda-assessment-tool/pkg/mapper"
)

func main() {
	classify := false
	args := os.Args[1:]
	if len(args) == 2 && args[0] == "-classify" {
		classify = true
		args = args[1:]
	}
	if len(args) != 1 {
		fmt.Fprintln(os.Stderr, "usage: bpmn-validate [-classify] <file.bpmn>")
		os.Exit(2)
	}
	data, err := os.ReadFile(args[0])
	if err != nil {
		fmt.Fprintln(os.Stderr, "read:", err)
		os.Exit(1)
	}
	pm, err := bpmnanalyser.Parse(data)
	if err != nil {
		fmt.Fprintln(os.Stderr, "parse:", err)
		os.Exit(1)
	}
	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")

	if classify {
		table, err := mapper.DefaultTable()
		if err != nil {
			fmt.Fprintln(os.Stderr, "table:", err)
			os.Exit(1)
		}
		pc := mapper.Classify(pm, table)
		if err := enc.Encode(pc); err != nil {
			fmt.Fprintln(os.Stderr, "encode:", err)
			os.Exit(1)
		}
		return
	}

	if err := enc.Encode(pm); err != nil {
		fmt.Fprintln(os.Stderr, "encode:", err)
		os.Exit(1)
	}
}
