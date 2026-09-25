# ALE integration review

Engine checkout: AgentsLastExam/ale at 04b0599928317191ca6557847a456a70ab2d0438.

Repository review covered the architecture/specification index and the module/function
inventory across core, run, verify, images and tests. Detailed source inspection focused
on task manifests, CLI selection/validation, the entire StandardEnvironment phase flow,
episode evidence capture, Docker networking, policy rollout, computer-use, desktop MCP,
guestd, task image preparation, verification, and corresponding GUI/network tests.
This is an integration review, not a claim of an exhaustive security audit.

## Findings that affect implementation

- A Task folder is self-contained. `verify/` and `oracle/` are staged only in their own
  phases. Public websites must never serve these directories or data-generation audits.
- `image/Dockerfile` must derive from ALE's desktop base; fixed installations belong
  there. The base source does not install a web browser. Install and configure one.
- Create the declared output directory with `user` ownership before execution. Artifact
  capture treats a missing directory as an infrastructure error, even for untouched runs.
- `computer-use` is a policy harness with screenshots and desktop actions. CLI harnesses
  need the run-level `cua-desktop` MCP explicitly enabled. Neither a successful oracle
  nor Playwright proves that a model-driven GUI agent can solve a task.
- GUI actions and screenshots are captured in ATIF `trajectory.json`; hashes prove
  downloaded bytes, not the user's interaction route. Report both kinds of evidence.
- Docker's allowlist route is an authenticated CONNECT proxy. Proxy variables are
  supplied by DockerSandbox.exec only for agent commands after sealing. A browser
  started by setup does not automatically inherit them.
- At this revision, CLI `validate` and `run --agent oracle` do not create an egress
  proxy for allowlisted tasks. Consequently an externally downloading oracle cannot
  validate over that path without a task/runner adaptation. Do not silently claim
  that the planned allowlist has been validated.
- Verifiers need Python 3.12+, named checks, an explicit `overall` aggregate, and one
  `Verification.write()`. Missing/wrong artifacts score zero; configuration failures
  must remain errors.
- `ale validate` requires every untouched reward to be zero and every oracle reward
  to be one, with matching names. Add negative artifact cases beyond this minimum.
- Task params are visible to the solver; do not place expected hashes or solution URLs
  there. Put references in verification/oracle stage files instead.

## Initial environment observations

Docker and Node were available. uv/just and ALE dependencies were installed during
preparation. Pulling the published ALE desktop base returned `unauthorized`. A local
source build with verified cached downloads subsequently succeeded; its provenance is
recorded in `reports/ale-base-provenance.json`. No model credential was provided.

## Deployment follow-up

The owner subsequently authorized and completed Vercel deployment. Production
https://data-download-task.vercel.app passed host browser download validation, and
all seven task URLs now point there. ALE validated all seven tasks against the identical
site served on the local Docker bridge: untouched rewards were zero and headed oracle
rewards were one. One earlier-revision CORGIS task also passed against the production
origin using a host Docker proxy. The current full task set has not passed a production
ALE run because this host intermittently cannot reach the Vercel edge. Model-driven
GUI execution still needs a configured model service. See `reports/ale-validation.json`.
