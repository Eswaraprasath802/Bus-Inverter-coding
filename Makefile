LOCAL_TOOLS := $(abspath build/tools/root/usr)
IVERILOG ?= $(if $(wildcard $(LOCAL_TOOLS)/bin/iverilog),$(LOCAL_TOOLS)/bin/iverilog -B $(LOCAL_TOOLS)/lib/x86_64-linux-gnu/ivl,iverilog)
VVP ?= $(if $(wildcard $(LOCAL_TOOLS)/bin/vvp),$(LOCAL_TOOLS)/bin/vvp,vvp)
RTL := $(wildcard rtl/*.v)
PYTHON ?= python3

.PHONY: test xrun waves traces synth measure publish
traces:
	$(PYTHON) scripts/generate_traces.py

test: traces build/tb_top.vvp
	cd build && $(VVP) tb_top.vvp > simulation.log
	@cat build/simulation.log
	@! grep -Eq 'ERROR|TEST FAILED' build/simulation.log
	@grep -qx 'TEST PASSED' build/simulation.log

build/tb_top.vvp: $(RTL) tb/tb_top.v
	mkdir -p build
	$(IVERILOG) -g2001 -Wall -DDUMP_VCD -s tb_top -o $@ $(RTL) tb/tb_top.v

xrun: traces
	mkdir -p build/xcelium
	cp -r build/traces build/xcelium/
	cd build/xcelium && xrun -access +rwc -top tb_top +define+DUMP_VCD ../../rtl/*.v ../../tb/tb_top.v
	@! grep -Eq 'ERROR|TEST FAILED' build/xcelium/xrun.log
	@grep -qx 'TEST PASSED' build/xcelium/xrun.log

waves: traces
	mkdir -p build/xcelium
	cp -r build/traces build/xcelium/
	cd build/xcelium && xrun -access +rwc -top tb_top ../../rtl/*.v ../../tb/tb_top.v -input ../../scripts/xrun_waves.tcl

synth:
	$(PYTHON) scripts/measure.py --synthesis-only

measure:
	$(PYTHON) scripts/measure.py

publish: measure
	$(PYTHON) scripts/publish_reference.py
