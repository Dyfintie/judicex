# Judicex Public Benchmarks

This folder contains small public demo cases that can be shared in the OSS
repository without private client data.

The goal is not to claim enterprise-grade accuracy. The goal is to make
Judicex testable: a contributor can run the same legal-work scenarios and see
whether the answer contains the expected practical sections.

Run:

```bash
python scripts/run_public_benchmark.py --db ./memory.benchmark.db
```

The script uses deterministic no-LLM fallbacks where possible, so it is useful
for CI and for contributors who do not have a model configured.
