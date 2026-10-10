# Automated experiment report

- Timestamp UTC: 20261010T185715Z
- Independent benchmark series per algorithm: 10
- ECDSA repetitions per operation and series: 100
- ML-DSA-65 repetitions per operation and series: 50
- Timings are means returned by the existing benchmark functions.
- Raw files preserve each independent series result, not each individual operation timing.

## Signature timing statistics

| Algorithm | Metric | Mean (ms) | Sample SD | 95% CI |
|---|---|---:|---:|---:|
| ECDSA | keygen_ms | 0.023435 | 0.000219 | [0.023278, 0.023592] |
| ECDSA | sign_ms | 0.034401 | 0.000479 | [0.034059, 0.034744] |
| ECDSA | verify_ms | 0.079368 | 0.001000 | [0.078653, 0.080083] |
| ML-DSA-65 | keygen_ms | 0.813377 | 0.010223 | [0.806064, 0.820689] |
| ML-DSA-65 | sign_ms | 3.791902 | 0.302215 | [3.575725, 4.008078] |
| ML-DSA-65 | verify_ms | 0.929475 | 0.022751 | [0.913201, 0.945748] |

## Other experiments and checks

- Grover circuit simulation: OK; timestamped CSV copy: results\raw\grover_circuit_20261010T185715Z.csv
- Pytest exit code: 0; log: results\logs\pytest_20261010T185715Z.txt
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
