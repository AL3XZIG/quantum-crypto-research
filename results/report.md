# Automated experiment report

- Timestamp UTC: 20261010T184948Z
- Independent benchmark series per algorithm: 2
- ECDSA repetitions per operation and series: 10
- ML-DSA-65 repetitions per operation and series: 30
- Timings are means returned by the existing benchmark functions.
- Raw files preserve each independent series result, not each individual operation timing.

## Signature timing statistics

| Algorithm | Metric | Mean (ms) | Sample SD | 95% CI |
|---|---|---:|---:|---:|
| ECDSA | keygen_ms | 0.024040 | 0.000141 | [0.022769, 0.025311] |
| ECDSA | sign_ms | 0.035585 | 0.000332 | [0.032599, 0.038571] |
| ECDSA | verify_ms | 0.084720 | 0.001047 | [0.075318, 0.094122] |
| ML-DSA-65 | keygen_ms | 0.843132 | 0.011651 | [0.738455, 0.947808] |
| ML-DSA-65 | sign_ms | 4.278590 | 0.403230 | [0.655771, 7.901409] |
| ML-DSA-65 | verify_ms | 0.941610 | 0.023410 | [0.731283, 1.151937] |

## Other experiments and checks

- Grover circuit simulation: OK; timestamped CSV copy: results\raw\grover_circuit_20261010T184948Z.csv
- Pytest exit code: 0; log: results\logs\pytest_20261010T184948Z.txt
- Grover complexity model is analytical, not a measured cryptographic runtime.
- Signature overhead is a data-size model, not a network measurement.

## Output locations

- Raw series: results/raw/
- Aggregate benchmark input: data/signature_benchmark.csv
- Statistics: results\tables\signature_benchmark_statistics.csv
- Figures and summary table: results/figures/ and results/tables/
- Logs and environment: results/logs/

## Limitations

Timing depends on hardware, operating system, library builds, and system load. These results describe this implementation and environment only. The Grover experiment is a small toy simulation, not a break of real cryptography.
