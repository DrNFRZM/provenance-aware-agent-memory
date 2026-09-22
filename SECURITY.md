# Security policy

This repository is a non-operational research simulation. Its fault model is limited to false
claims about generated fictional entities; it contains no exploit code, external targets or
credential-handling workflow. The default benchmark and test suite make no network requests.

For an ordinary correctness or reproducibility problem, open a GitHub issue with the smallest
synthetic example that demonstrates it. If a report involves a possible secret, unsafe external
interaction or other information that should not be public, contact Farzam Nikbakhsh Jorshari at
nikbakhshfarzam@gmail.com instead of posting it in an issue. Please do not include real harmful
content or target a third-party system while reproducing a problem.

Only the current `main` branch is maintained. This is an MSc research artifact, not a security
boundary for deployed agents; the assumptions and out-of-scope cases are documented in
[`docs/threat_model.md`](docs/threat_model.md).
