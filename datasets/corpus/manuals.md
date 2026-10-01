# Northwind fictional manual corpus

Invented documentation for a fictional commercial-HVAC family. Nothing here is real
or proprietary. Two entries are distractors: plausible-but-wrong docs used to test
retrieval precision. Retrieval itself is not implemented in Phase 0; these back the
seed cases' expected_retrieval_ids / distractor_ids.

Equipment: RTU (NW-RTU-30/40/50), AHU (NW-AHU-1/2), chiller (NW-CH-1/2).
Alarms: NW-A11 high head pressure, NW-A21 sensor fault, NW-A31 comms loss,
NW-A41 filter differential high, NW-A51 compressor trip, NW-A61 low CHWS.

- DOC-RTU-A11: High head pressure (NW-A11). Causes: fouled condenser coil, failed or
  blocked condenser fan, refrigerant overcharge, high ambient. Action: restore
  condenser airflow (clean coil / repair fan), verify charge.
- DOC-RTU-CYCLE: (DISTRACTOR) Short-cycling, controls. Check thermostat/BAS setpoint
  differential and the minimum-off timer.
- DOC-SENSOR-A21: Sensor fault (NW-A21). Compare the suspect sensor against a second
  reference; if stuck or out of range, recalibrate or replace.
- DOC-COMMS-A31: Comms loss (NW-A31). Controller offline on the field bus; check bus
  wiring/termination/grounding. Intermittent faults require on-site field-bus inspection.
- DOC-FILT-A41: Filter differential high (NW-A41). Replace the return-air filter; do
  not compensate with fan speed.
- DOC-AHU-VFD: (DISTRACTOR) Low airflow, fan speed. Increasing the supply-fan VFD
  frequency raises airflow.
- DOC-COMP-A51: Compressor overload/trip (NW-A51). Megger the windings; low insulation
  resistance indicates winding failure, replace the compressor.
- DOC-CHW-EFF: Chiller efficiency drift. Check approach temps, tube fouling, and
  refrigerant; a full performance workup is a technician task.
- DOC-RTU-COOL: Underperformance with normal fan/filter and slightly-low suction.
  Candidate causes: refrigerant undercharge OR evaporator airflow restriction.
  Operator-performable discriminators: the refrigerant sight-glass check and the
  economizer-damper position check.
- DOC-CHW-LOWCAP: Low-capacity pattern. Candidate causes: refrigerant undercharge OR
  fouled evaporator; separable only by a technician refrigerant-charge measurement.
