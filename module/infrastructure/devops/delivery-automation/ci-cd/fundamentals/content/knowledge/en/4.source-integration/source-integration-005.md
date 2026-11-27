# Verifying the Exact Version to Be Merged or Deployed

A green CI pipeline does not automatically prove that the version about to be merged or deployed was actually verified. Check results are meaningful only when tied to the exact source code, the exact integration result, and the exact artifact that will be delivered to the target environment. If a pipeline tests one commit while the merge operation creates a different commit, or if the deployment system pulls the latest state of a branch instead of the verified artifact, the team may release a version that never passed the established quality gates.

Therefore, every merge or deploy decision must answer three questions: **what exact object is being verified, which object do the verification results belong to, and does the object delivered to the environment match the approved object?** This lesson covers how to identify source versions, verify merge results, link commits to artifacts, control releases, and retain evidence for traceability or rollback.

## 1. Why Must You Verify the Exact Version?

In Git, a branch name like main or release/2.x is a movable reference. Today main points to commit A; after a PR is merged, it may point to commit B. If a job records only the branch name without the specific commit, days later the team may be unable to identify the exact source code that was tested.

Similarly, a successful CI run does not automatically prove every related version passes:

- A commit on a feature branch may run fine alone yet conflict with new changes on the target branch.
- A PR may be updated after the pipeline completes, rendering prior results inapplicable to the current content.
- The Git platform may produce a merge commit, squash commit, or rebase commit different from the PR head commit that was checked.
- A tag may be moved to point to a different commit.
- A pipeline may build an artifact from one commit, while the deploy step checks out the latest main branch and rebuilds.
- An artifact may be replaced or overwritten in the repository after being verified.
- Environment configuration or external dependencies outside source code may change between verification and deployment.

These situations create a gap between **the verified version** and **the version actually used**. The goal of the process is to close that gap through immutable identifiers, checks at the right integration points, and artifact traceability across environments.

## 2. Distinguishing Version Identifiers

Not every string that looks like a version number carries the same meaning. Distinguish Git references, commits, tags, release version numbers, and artifact identifiers.

| Identifier | Example | Characteristics | Usage |
|---|---|---|---|
| Branch name | main, release/2.x | Movable reference as new commits arrive | Select a development line or maintenance line |
| Commit SHA | 4f8c... | Identifies a specific commit in the repository | Bind CI results, reviews, and provenance to source code |
| Git tag | v2.4.1 | Named reference to a Git object; can be deleted or recreated if policy allows | Mark release milestones; protect and sign when appropriate |
| Application version | 2.4.1 | Project-managed version label | User display, compatibility, and release notes |
| Artifact digest | sha256:... | Content hash of a package or image | Pinpoint the exact stored and deployed artifact |
| Pipeline run ID | 982731 | Identifies a single pipeline execution | Look up logs, trigger actor, and check results |

### Commit SHA vs. Branch Name

A commit SHA identifies a specific commit object, whereas a branch name denotes the current position of a development line. When proving a version passed CI, record the full SHA or an identifier sufficient for exact lookup. Never record only "CI on main succeeded," because main may already point to another commit.

A commit contains its content tree and parent history. Identical file contents with different commit metadata or parent history produce different SHAs. Hence, SHA comparisons should be understood by repository commit identity, not merely branch names or commit messages.

### Tags vs. Application Versions

Tags like v2.4.1 are convenient for humans, yet a tag is still a Git reference. If tag write permissions are unprotected, a tag can be moved to point to another commit. Release workflows should restrict permissions to create, modify, or delete tags; tags may also be required to be signed and signature-verified per project policy.

An application version does not replace a commit SHA either. A 2.4.1 release needs a record stating which commit built it and which artifacts it produced. If multiple builds carry the 2.4.1 label, that label alone cannot uniquely identify the package to deploy.

### Artifact Digest

An artifact digest, typically SHA-256, identifies the exact content of a package, file, or container image. For container registries, reference images by digest rather than relying solely on tags like latest or stable. Tags aid lookup, while digests guarantee the exact content pulled.

Commit SHA and artifact digest complement each other: the commit shows the input source code; the digest shows the produced output that will be used. A trustworthy release workflow must record the link between both identifiers.

## 3. Verifying PR Head Commits and Merge Results

A PR usually has at least two perspectives to verify:

- **PR head commit:** the version proposed by the PR author. It is suitable for reviewing content and running checks on the source branch's changes.
- **Expected integration result (merge candidate):** the result when changes combine with the current state of the target branch. It indicates whether changes work together in the state about to be merged.

Checking only the head commit can miss interactions with the target branch. For example, a feature branch changes a function signature while main just received a commit adding a call to that function. The feature branch builds fine on its own, yet the post-merge result fails to compile.

### Verifying According to Merge Strategy

How post-merge commits are created affects what must be verified:

| Strategy | Outcome | What to Verify |
|---|---|---|
| Merge commit | Creates a new commit with parent branches showing the merge | Verify the merge candidate containing both PR changes and target branch state |
| Squash merge | Combines PR commits into one new commit on the target branch | Verify integrated content and check the resulting commit after creation |
| Rebase merge | Replays PR commits onto the target branch tip, creating new commits | Verify the rebased commit sequence and the final integrated result |
| Fast-forward | Advances the target branch to an existing commit on the source branch | Ensure the verified commit is still the exact commit landed on the target branch |

Git platforms can generate a synthetic commit to test PRs. Exact naming and behavior depend on the platform, merge strategy, and pipeline configuration. Teams must understand whether the pipeline checks out the head commit or a merge candidate, and enforce the right object as the pre-merge gate.

### Why Re-Verify When the Target Branch Changes?

Suppose a PR was tested when main was at commit A. While reviewers are inspecting it, another PR merges and main advances to commit B. The expected integration result between the current PR and A does not prove the PR works with B.

Three common approaches handle this:

1. Require the PR to update against the target branch and re-run checks.
2. Use a merge queue or merge train to verify changes in the expected integration order.
3. Run a verification pipeline on the actual commit immediately after merge, paired with a response procedure if the main branch breaks.

Merge queues are particularly effective when multiple PRs await the same branch. The system builds integration candidates sequentially, runs checks on the projected state, and lands the merge only if that candidate passes. If the target branch state changes, candidates must be regenerated or re-verified according to platform mechanics.

## 4. Binding Status Checks to the Right Commit

CI results must bind to a specific commit or merge candidate. A status check is only valuable when you can determine:

- The commit SHA checked out and verified.
- The associated PR or target branch.
- The verified object type: head commit, merge candidate, or post-merge commit.
- The pipeline definition and tool versions used.
- Required jobs, individual job results, and completion timestamps.
- Whether the status remains valid for the current PR version.

Branch protection policies should require mandatory status checks to succeed on the exact object the platform uses for merging. If a job name changes, branch protection settings must be updated and verified simultaneously. A forgotten legacy check name or duplicate check names can cause branch rules to diverge from original intent.

### Avoid Reusing Old Results for New Content

Whenever a PR receives a new commit, the system must generate new check results for that commit. Never treat a green status from a prior commit as proof for a later commit, even if the new delta looks minor.

Conditions to watch for:

- A new commit is pushed after CI completed.
- The PR is updated or rebased onto the target branch.
- The target branch changes, yielding a new merge candidate.
- Pipeline configuration or quality gates change.
- Dependency lockfiles, toolchains, or build configuration files change.
- A status check is skipped, cancelled, or incomplete.

A "pending", "skipped", or "cancelled" result does not equal "success". Merge policies must explicitly state which statuses are acceptable, especially when pipelines include conditional jobs or path-filtered jobs.

## 5. Example: Validating a Merge Candidate with GitHub Actions

The example below illustrates a workflow running when a PR is created/updated and when a PR enters a merge queue. The workflow checks out the exact event SHA and runs Gradle verification. On GitHub Actions, the merge_group event lets the workflow participate in the merge queue; teams must enable the merge queue and configure the corresponding required status check in the repository.

    name: validate-merge-candidate

    on:
      pull_request:
      merge_group:

    permissions:
      contents: read

    jobs:
      verify:
        name: verify-merge-candidate
        runs-on: ubuntu-latest
        timeout-minutes: 25

        steps:
          - name: Checkout event commit
            uses: actions/checkout@v4
            with:
              ref: ${{ github.sha }}

          - name: Set up JDK
            uses: actions/setup-java@v4
            with:
              distribution: temurin
              java-version: "21"
              cache: gradle

          - name: Verify
            run: ./gradlew --no-daemon check

Notes when using this example:

- The event SHA is the identifier to verify; do not swap it by checking out the main branch name mid-workflow.
- The JDK version must match the project's toolchain and build requirements.
- The check task must genuinely include the mandatory verifications the team wants as a merge gate.
- If the project uses actions in environments with strict supply-chain controls, pin actions by full commit SHA and update via reviewed workflows.
- For merge queues, required status checks must match the exact check name published by the workflow.
- This workflow verifies source code only. It does not yet automatically prove that an artifact deployed later was built from the exact verified commit.

With GitLab, you can configure merged results pipelines or merge trains to verify expected integration outcomes. Regardless of platform, the principle remains: record the exact checked-out object and bind results to the right merge candidate.

## 6. Identifying the Exact Version at Deployment

After merging, deployment workflows must select an input with a stable identifier. Two common patterns exist:

- Build from the merged commit, then produce an artifact and store its digest.
- Pull an artifact already built and verified in an earlier pipeline, then promote that artifact across environments.

The second approach generally ensures stronger consistency if artifacts are stored immutably with complete provenance. Either way, the deploy step must know the exact artifact being deployed.

### Never Deploy by Moving Branch Names

A deploy command like "fetch the latest main and build" can pick up a different commit than the one reviewed. This often happens when deployments are triggered manually after a delay, or when build and deploy pipelines run independently.

Instead, deployment requests should carry concrete identifiers:

- Source commit SHA.
- Application version or release ID.
- Artifact URI in the repository/registry.
- Artifact digest.
- Target environment.
- Pipeline run that produced the artifact.
- Quality gate results and associated approval details.

If a release spans multiple components, the manifest must list each artifact and its digest. Recording only a single umbrella version may be insufficient to tell exactly which services or images are running.

### Build Once, Promote Many

A core principle of artifact management is building once and promoting the same artifact across environments. For example:

1. Commit C merges into main.
2. The pipeline builds and tests commit C.
3. The pipeline produces a container image, computes digest D, and stores the image in the registry.
4. Image digest D deploys to the test environment.
5. After verification and approval, the exact same digest D deploys to staging and then production.

Do not rebuild from the same version label in each environment, because outputs can differ due to dependencies, toolchains, download timing, or build environment variables. If a rebuild is unavoidable, treat it as a brand-new artifact and re-run all applicable checks for the new artifact.

Environment settings such as service URLs, replica counts, and feature flags can differ across environments. These settings must be managed and traced separately. Build once, promote many does not mean every environment uses identical runtime configuration.

## 7. Verifying Artifact Provenance and Integrity

A trustworthy artifact must be able to answer where it came from and which checks it passed. Provenance metadata should link the output back to the source code, pipeline, and tooling that built it.

A release manifest might include the following fields:

    release:
      version: "2.4.1"
      source:
        repository: "org/service"
        commit: "4f8c1d2..."
        ref: "refs/heads/main"
      build:
        pipeline: "ci"
        run_id: "982731"
        toolchain: "JDK 21"
        dependency_lock_hash: "sha256:..."
      artifact:
        uri: "registry.example.com/service"
        digest: "sha256:..."
        media_type: "application/vnd.oci.image.manifest.v1+json"
      verification:
        unit_tests: "passed"
        integration_tests: "passed"
        security_scan: "passed"
        quality_gate: "passed"

This illustrates the structure; adjust field names and values to your project's platform. Never store secrets or sensitive data in manifests.

### Digests and Integrity Checks

When pulling an artifact for deployment, the system should verify the received digest matches the digest recorded after build. On mismatch, halt deployment and investigate. Use checksums for package files or image digests in container registries.

A digest only proves received content matches hashed content. It does not by itself prove the artifact was created by a trusted pipeline. To prove origin, add signatures, build attestations, or provenance signatures from the build system. Protect signing keys and verify signatures prior to deployment.

### Protecting Immutable Artifacts

Artifact repositories need policies restricting overwrites or deletions of released versions. Common safeguards include:

- Using a unique version or storage path for each release.
- Enabling immutable tags or retention policies if supported by the registry.
- Restricting artifact publish and delete permissions.
- Storing checksums, signatures, and provenance alongside release metadata.
- Recording which actor or pipeline published the artifact.
- Retaining artifacts long enough to support rollbacks and audits.

Do not rely on the latest tag to determine production inputs. Even if friendly tags like stable are used, deployment should resolve the tag to a digest and record that digest in the deployment record.

## 8. Pre-Deployment Condition Checks

Before deploying, the system must evaluate both the artifact and target environment state. A pre-deploy quality gate can include:

| Condition | Question to Answer | Evidence |
|---|---|---|
| Provenance | Was the artifact built from a merged or approved commit? | Commit SHA and build provenance |
| Integrity | Does the downloaded artifact match the content built? | Digest or checksum |
| Quality | Did mandatory checks pass? | CI status, test reports, and quality gates |
| Security | Does the artifact violate security policy? | Dependency scan, image scan, signature, or attestation results |
| Compatibility | Is the artifact compatible with the target runtime and environment? | Configuration, contract, and migration checks |
| Approval | Are required approvals present for controlled environments? | Approval record and deployment policy |
| Recoverability | Is there a previous stable version and rollback plan? | Prior version digest, migrations, and runbook |

Tailor conditions to risk level. An internal service may not need the same approval flow as a payment processing or critical data system. Still, artifact identification and traceability must be preserved.

### Managing Deployment Secrets and Permissions

Source-checking build jobs do not need production deploy permissions. Separate permissions by purpose:

- PR verification jobs need only repository read access and test execution rights.
- Publish jobs are allowed only to write to the required registry or artifact repository.
- Deploy jobs are allowed to access only the specific target environments they own.
- Production approval rights are restricted to designated teams or roles.

Store deployment secrets in the platform's secret store or a dedicated secrets manager. Inject secrets only into jobs that need them, keep them out of logs, and never grant production secrets to workflows running untrusted code from forks.

## 9. Verifying Which Version Is Actually Running Post-Deploy

Tool-level deployment success only means the deploy operation finished as reported by the platform. It does not prove every instance runs the right version or that the application behaves normally.

After deploying, verify:

1. The deployment record logs the correct release ID, commit SHA, and artifact digest.
2. Runtime or version info endpoints report the right running build.
3. Instances, pods, or workers have updated to the target version.
4. Readiness and health checks pass.
5. Smoke tests or critical business flow checks succeed.
6. Metrics, logs, and traces show no anomalies post-rollout.

Applications can expose a read-only build metadata endpoint or fields, such as version, commit, and build ID. Never return secrets, sensitive environment variables, or unnecessary internal details via such endpoints.

### Verifying Across Rollout Phases

In rolling, canary, or blue-green deployments, track the version of each instance group. During a rollout window, multiple versions may coexist. Observability systems must distinguish them so errors appearing only on the new version are caught.

If a canary receiving a small slice of traffic shows elevated error rates, the system can halt rollout expansion. Automated halts should rely on defined thresholds, observation windows, and reliable telemetry. Never declare success just because the deploy process returned exit code 0.

## 10. Rolling Back to a Known-Good Artifact

Rollback restores the system to a previously identified release state. To roll back quickly and accurately, retain the previous version's artifact digest, release manifest, deployment config, and migration metadata.

A rollback procedure can include:

1. Identify the failing release and blast radius.
2. Select the most recent stable release from deployment records.
3. Verify that release's artifact digest and signature/provenance.
4. Check schema, configuration, and data compatibility.
5. Re-deploy the known artifact to the target environment.
6. Verify health checks, smoke tests, and metrics after rollback.
7. Record timestamp, operator, reason, and outcome.

Never roll back by checking out a tag that may have moved or rebuilding an old commit with current dependencies. Use the immutable artifact saved from the prior release.

Application rollback also does not automatically reverse database migrations. If schemas changed incompatibly, you need backward-compatible migrations, expand-and-contract strategies, or a separate data recovery plan. Migration design must be reviewed before deployment.

## 11. Practical Scenario: PR Verified, Wrong Commit Deployed

A team developing a payment service has a PR altering fee calculation. CI succeeds on commit H1 of the feature branch. During review, main receives commit M2 modifying a shared API. The PR then squash-merges, creating commit S3.

If the deploy pipeline simply says "deploy main" and checks out the latest state, a different commit may get built once another PR merges right afterward. During an incident, the team struggles to tell whether the running artifact contains the reviewed change.

The workflow is redesigned as follows:

- The PR records head SHA H1 and runs checks.
- The merge queue builds a merge candidate from current main and the PR; the pipeline verifies that candidate.
- After merging, the main pipeline records the actual commit S3.
- The build produces artifact A with digest D, storing provenance linking S3, pipeline run, and test results.
- Both staging and production deploy digest D.
- Deployment records log D, S3, environment, timestamp, and verification outcome.
- If an error occurs, the team selects the digest of the prior stable release to roll back.

This lets the team trace the full chain from PR to merged commit, produced artifact, and running version in every environment.

## 12. Common Design Mistakes

| Practice | Risk | Adjustment |
|---|---|---|
| Testing only the PR head commit | Misses errors when combining with the target branch | Verify merge candidates or use a merge queue |
| Keeping old CI results after PR commit changes | Unverified content can merge | Bind status to SHA and require re-runs |
| Logging only branch names | Cannot identify which commit ran | Record full commit SHA |
| Discovering integration failure only after merge | Main branch loses stability | Verify merge candidates and run post-merge checks |
| Deploying with the latest tag | Tag may point to newer content | Resolve and deploy by digest |
| Rebuilding in every environment | Artifacts may diverge | Build once, promote many |
| Recording version without commit | Cannot trace back to source code | Link version to commit SHA |
| Mutable artifacts | Test evidence no longer matches | Enable immutable storage and access controls |
| No post-deploy verification | Unknown which version actually runs | Read build metadata, health checks, and smoke tests |
| Rolling back by rebuilding an old tag | Output may differ from original release | Re-deploy saved artifact digest |
| Broad production permissions on CI jobs | Untrusted code can abuse credentials | Isolate jobs and restrict secrets and permissions |

## 13. Pre-Merge and Pre-Deploy Checklists

### Before Merging

- [ ] PR head commit SHA is identified.
- [ ] Pipeline verified the right commit or merge candidate per merge strategy.
- [ ] If the target branch changed, the integration candidate was updated and re-verified.
- [ ] All required status checks pass on the exact SHA.
- [ ] Pending, skipped, or cancelled statuses are not accepted for mandatory gates.
- [ ] Branch protection or merge queue rules are configured accurately.
- [ ] Logs and test reports for the corresponding run are retrievable.

### Before Deploying

- [ ] Artifact source commit matches the approved release.
- [ ] Artifact digest matches post-build recorded metadata.
- [ ] Provenance and signatures are verified per policy.
- [ ] Required quality gates and security checks pass.
- [ ] Target environment, configuration, and migrations are verified.
- [ ] Necessary approvals are recorded.
- [ ] Deploy secrets and permissions are scoped appropriately.
- [ ] A prior stable artifact and rollback plan exist.

### After Deploying

- [ ] Deployment record stores release, commit SHA, and artifact digest.
- [ ] Runtime reports the expected running version.
- [ ] Instances or workloads have reached ready state.
- [ ] Smoke tests and critical business checks pass.
- [ ] Metrics, logs, and traces are monitored during the verification window.
- [ ] If rollout is halted or rolled back, cause and outcome are recorded.

## Conclusion

Verifying the exact version bridges CI, source integration, and software release. Bind every verification result to a specific commit or merge candidate, link every artifact to its source via provenance and digest, and promote the exact verified artifact across environments. With deployment records and post-deploy verification, teams know precisely which version is running, why it was cleared for release, and where to restore if an incident strikes.
