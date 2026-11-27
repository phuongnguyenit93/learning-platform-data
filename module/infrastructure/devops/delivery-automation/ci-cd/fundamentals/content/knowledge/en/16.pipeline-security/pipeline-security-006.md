# Integrating Dependency, Source Code, and Secret Scanning

## 1. Why Integrate Security Checks into CI/CD?

A pipeline has access to source code, downloads dependencies, produces artifacts, and sometimes deploys to live environments. If a pipeline runs only functional tests without security checks, a change can introduce vulnerable libraries, exploitable code patterns, or accidentally committed credentials into the system.

Three foundational check categories should be combined in the CI/CD flow:

- **Source code checks (SAST and related static checks):** detect signs of security bugs in developer-written code, such as SQL injection, unsafe data handling, weak cryptographic configurations, or dangerous API usage.
- **Dependency checks (SCA):** identify direct and transitive libraries and detect vulnerable versions, incompatible licenses, or unauthorized package sources.
- **Secret scanning:** detect tokens, passwords, private keys, and credentials at risk of being committed to repositories, Git history, logs, or artifacts.

These three categories complement one another. SAST inspects how code is written; SCA inspects the external components the application uses; secret scanning locates authentication material that could grant unauthorized access. None of the three can replace the other two.

Within the scope of **DEVOPS_CI_CD_FUNDAMENTALS**, the objective is to build a traceable release flow from Git events and pipeline-as-code through automated builds and tests to artifact management, environments, quality gates, secret protection, post-deployment verification, and rollback capability. Security checks must run at the right moments, produce evidence bound to commits and artifacts, and enforce clear decisions before changes are released.

## 2. The Three Check Categories and Their Scopes

| Category | Inspection Target | Typical Findings | Evidence to Retain |
|---|---|---|---|
| SAST / source checks | Source code and statically analyzed configs | Injection, weak input handling, insecure cryptography, authorization flaws | Finding, code location, rule, severity, and scanner version |
| SCA / dependency checks | Direct, transitive, and packaged dependencies | CVEs, licenses, unauthorized packages, outdated versions | Dependency graph, SBOM, findings, and data sources |
| Secret scanning | Diffs, repository, Git history, and selected outputs | Tokens, passwords, private keys, connection strings | Secret type, location, commit, and remediation/sanitization status |

Checks can extend to container images, Infrastructure as Code, Kubernetes manifests, APIs, or running applications. However, distinguish them clearly:

- **SAST** analyzes code without executing the application.
- **DAST** tests the behavior of a running application by sending controlled requests.
- **SCA** inspects software components and dependencies.
- **Secret scanning** searches scanned content for exposed credentials.
- **Container scanning** inspects images, OS packages, configurations, and sometimes secrets inside image layers.
- **IaC scanning** inspects infrastructure definitions before they are applied.

This lesson focuses on coordinating SAST, SCA, and secret scanning into one unified control flow.

## 3. Placing Checks at the Right Points in the Change Lifecycle

Do not wait until release day to run every security check. When feedback arrives late, changes have often passed through multiple branches, been integrated with other features, and become hard to trace back to root causes.

A practical model divides checks into layers:

| Stage | Primary Checks | Goal |
|---|---|---|
| Pre-commit | Optional local hooks or tools | Rapid feedback for developers |
| Pull request | Secret scan on diff, fast SAST, SCA on lockfiles, lint, and tests | Block obvious issues before merging |
| Post-merge | Full source and dependency graph scan, build, SBOM generation | Verify integrated state |
| Scheduled | Re-scan dependencies and repositories with updated vulnerability feeds | Catch newly disclosed risks even when code is unchanged |
| Pre-publish/release | Artifact/image scan, license check, provenance, and policy check | Prove the exact artifact being released |
| Post-deployment | Monitor runtime alerts and verify service health | Detect impact in live environments |

Scans can share the same rule sets while differing in timing and depth. Pull requests require fast feedback so development cadence is not disrupted. Release pipelines can run deeper analyses and verify the final artifact.

Scheduled scans are especially critical for SCA. A dependency with zero CVEs today may have a vulnerability disclosed next week even when the repository has not changed. Dependency security is therefore a continuous process, not a one-time pull request step.

## 4. Designing a Unified Checking Flow

A general flow can be implemented as follows:

~~~mermaid
flowchart TD
    A["Pull request or Git change"] --> B["Inspect source and event context"]
    B --> C["Secret scan"]
    B --> D["SAST and security lint"]
    B --> E["SCA: dependencies and licenses"]
    C --> F["Aggregate findings"]
    D --> F
    E --> F
    F --> G{"Quality gate"}
    G -- "Blocking violation" --> H["Block merge, return remediation guidance"]
    G -- "Pass or permitted warnings" --> I["Build artifact"]
    I --> J["Scan artifact and generate SBOM"]
    J --> K{"Release policy met?"}
    K -- "No" --> H
    K -- "Yes" --> L["Publish immutable artifact"]
    L --> M["Deploy per policy"]
    M --> N["Verify and monitor"]
~~~

Independent steps can run in parallel. However, publishing must depend on mandatory checks and must operate on the exact artifact that was scanned. If the pipeline rebuilds after scanning, prior scan results may no longer apply to the released artifact.

Each run should record:

- Repository, branch, event, and commit SHA.
- Associated pull request or change request.
- Scanner, ruleset, and vulnerability database versions.
- Dependency lockfiles or dependency graph.
- Findings and remediation status.
- Artifact digest, SBOM, and provenance.
- Quality gate decision and approved exceptions.

## 5. Checking Source Code with SAST

SAST analyzes source code or bytecode without running the application. Tools may use rules, patterns, data-flow analysis, or taint analysis to trace paths from untrusted inputs to sensitive sinks.

Common vulnerability classes include:

- SQL injection caused by concatenating inputs into query strings.
- Cross-site scripting caused by rendering unencoded data.
- Path traversal when user-supplied filenames directly access the filesystem.
- Command injection when external data is concatenated into OS commands.
- Insufficient authorization checks before resource access.
- Weak cryptographic algorithms or configurations.
- Error handling that leaks internal details.
- Unsafe APIs or weak default security settings.

SAST can understand language and framework context. A rule looking for risky SQL strings might emit false positives if it fails to recognize prepared statements or an input-validating data access layer. Findings should therefore be triaged by data flow, exploitability, and application context.

### 5.1. Layering SAST Checks

Source code checks can be organized into layers:

1. **Linting and basic safety rules:** flag dangerous APIs, misconfigurations, and easily fixed defects.
2. **Fast diff-based SAST:** prioritize new lines or modified regions for rapid feedback.
3. **Full-repository SAST:** perform comprehensive data-flow and cross-component analysis post-merge or on schedule.
4. **Custom checks:** product-specific rules tailored to the framework, architecture, or security requirements.

Do not scan only new lines and ignore legacy security debt indefinitely. Enforce a policy preventing new findings above threshold while maintaining a scheduled remediation plan with severities and deadlines for existing backlog findings.

### 5.2. Reading Findings Properly

A SAST finding should contain:

- Rule or weakness category.
- Affected file and location.
- Data source and sink if supported by the tool.
- Data-flow trace or supporting evidence.
- Severity level.
- Exploitability within application context.
- Remediation guidance and documentation links.

Do not conclude a bug is exploitable solely from the rule name. Verify whether the input is genuinely user-controlled, whether proper validation/encoding exists along the path, and whether the code path is reachable in production.

## 6. Checking Dependencies with SCA

SCA identifies the packages an application uses, including direct and transitive dependencies. Tools match package names, versions, and ecosystems against vulnerability feeds, license databases, and package policies.

A dependency can enter a project via multiple paths:

~~~text
Application
  ├── library A
  │     └── library C
  └── library B
        └── library C
~~~

Library C is a transitive dependency. Developers may not declare it directly, yet the application still bundles and executes it. Inspecting only direct dependency lists misses this risk.

### 6.1. Lockfiles and Dependency Graphs

Lockfiles record resolved dependency versions. They help ensure consistent versions across builds under matching conditions and provide reliable inputs for SCA.

A sound workflow should:

- Generate or update lockfiles using the official package manager.
- Review dependency graph diffs in pull requests.
- Inspect both direct and transitive packages.
- Record the package registry or source.
- Pin versions and verify checksums/signatures per policy.
- Avoid dynamic version ranges in release builds when reproducibility is needed.

Example commands for inspecting dependency graphs:

~~~bash
./mvnw dependency:tree
./gradlew dependencies
npm ls --all
pipdeptree
~~~

These commands inspect package relationships; they do not replace vulnerability scanners or license policies. Combine their outputs with scanners and artifact SBOMs.

### 6.2. Evaluating Dependency Vulnerabilities

Not every CVE carries the same risk for a given application. When evaluating a finding, consider:

- Severity reported by vulnerability feeds.
- Whether the specific package version is actually affected.
- Whether the dependency is bundled into the runtime artifact or used only for build/test.
- Whether the affected component is invoked by the application.
- Whether exploitation prerequisites exist in the deployment environment.
- Whether a patched version or mitigation is available.
- Whether the vulnerability has known active exploitation, if threat intelligence is available.

CVSS is an important signal, not the sole decision factor. Reachability, exposure, package role, and business impact must also be weighed.

### 6.3. Licenses and Package Sources

SCA can inspect licenses to detect terms incompatible with product distribution policies. Teams must distinguish licenses of direct versus transitive dependencies, as well as how license obligations apply to the distributed product.

Beyond licenses, verify package sources:

- Allow only approved registries.
- Control internal package namespaces.
- Prevent dependency confusion.
- Use internal repository proxies or mirrors where appropriate.
- Record checksums, signatures, and provenance.
- Never fall back arbitrarily to public registries when internal sources fail.

## 7. Secret Scanning

Secret scanning searches for credentials that could grant access to systems or data. Examples include:

- API tokens and access keys.
- Database or message broker passwords.
- Private keys and certificates containing private keys.
- Repository or cloud access tokens.
- Connection strings with usernames/passwords.
- Credentials embedded in scripts, config files, logs, or documentation.

Scanners combine known patterns, token checksums, entropy analysis, and vendor-specific rules. However, no scanner catches every secret. Custom tokens or encoded credentials may evade pattern rules.

### 7.1. Scanning Multiple Scopes

Combine the following scopes:

- **Pre-commit:** early detection on developer machines.
- **Pull request diff:** block new secrets from entering protected branches.
- **Repository scan:** check current files.
- **Git history scan:** locate secrets still present in older commits even after files were deleted.
- **Artifact/image scan:** detect credentials packaged inside binaries, layers, or config files.
- **Log and output scan:** check whether pipelines inadvertently print credentials.

Pre-commit is a helpful layer. Users can bypass hooks or commit from other environments, so server-side scanning remains mandatory.

### 7.2. Distinguishing Real Secrets from Test Data

Examples in docs or tests may contain token-like strings. To reduce false positives:

- Use clearly marked dummy values such as EXAMPLE_TOKEN_DO_NOT_USE.
- Never copy real credentials into test fixtures.
- Scope exceptions narrowly and document the rationale.
- Avoid broad filename or directory allowlists without review.
- Re-evaluate exceptions when scanner rules change.

Never put real secrets into documentation expecting scanners to infer illustrative context.

## 8. Responding When a Secret Is Detected

When a scanner detects a potentially real credential, treat it as a security incident until proven otherwise.

Response sequence:

1. **Prevent further use:** block merging or publishing if the secret is in an unmerged change.
2. **Identify the credential type:** determine the service, owner, permissions, and blast radius without printing the secret value to logs.
3. **Revoke or rotate:** invalidate the exposed credential and issue a new one through the secret manager.
4. **Check for signs of use:** review service audit logs for anomalous access.
5. **Clean the repository:** remove the secret from current code; if necessary, scrub Git history under a controlled procedure.
6. **Locate copies:** check branches, forks, caches, artifacts, logs, images, and downloaded copies.
7. **Verify:** re-run secret scanning and confirm the old credential no longer works.
8. **Prevent recurrence:** identify root cause and add checks, permissions, or guidance.

Deleting a line in a new commit does not invalidate an exposed credential. Rewriting Git history does not replace token revocation either, because copies may already exist in forks, clones, logs, or artifacts.

## 9. Protecting Secrets Used by Pipelines

Pipelines may need tokens to download private dependencies, push artifacts, or access cloud resources. These credentials must be provisioned with strict controls.

Core principles:

- Store secrets in a secret manager or CI platform vault.
- Never commit secrets into Git or configuration files.
- Expose secrets only to jobs that genuinely need them.
- Prefer short-lived credentials or workload identity/OIDC whenever possible.
- Separate tokens for reading dependencies from tokens for publishing artifacts.
- Separate staging and production permissions.
- Scope permissions by repository, environment, audience, and action.
- Never pass secrets unnecessarily through artifacts, caches, or job outputs.
- Mask sensitive values in logs and avoid enabling unrestricted debug dumps.
- Maintain rotation and revocation procedures.

A SAST or unit test job rarely needs production credentials. If every job receives the same secret bundle, a compromised dependency or script can abuse permissions far beyond its intended purpose.

### 9.1. OIDC and Short-Lived Credentials

When the CI platform and cloud provider support OIDC, a job can obtain a short-lived identity token and exchange it for narrowly scoped access. This reduces the need to store long-lived access keys in CI.

Trust policies must verify attributes such as:

- Allowed repository or project.
- Allowed branch or tag.
- Target environment.
- Workflow or workload identity.
- Token audience and lifetime.

Never allow every repository in an organization to assume cloud privileges. Constrain identities to the exact pipeline and environment.

## 10. Trust Boundaries for Pull Requests and Runners

Code in a pull request can be untrusted, especially from forks or external contributors. A workflow holding secrets that executes scripts modified by a pull request can leak credentials.

Principles:

- Jobs running code from forks must not receive sensitive secrets.
- Use minimal permissions, usually read-only source access for linting and testing.
- Separate jobs validating untrusted code from publish or deploy jobs.
- Never use high-privilege triggers to directly execute unreviewed pull request code.
- Review changes to workflows, build scripts, and external actions.
- Pin critical actions/plugins to verified commits when supported by the platform.
- Prefer ephemeral runners for high-privilege jobs.
- Clean workspaces and credentials after jobs complete.
- Separate caches between trusted and untrusted branches.

Runners are execution environments. If a runner is reused without thorough cleanup, leftover processes or files can affect subsequent runs. Release jobs should use short-lived runners with restricted permissions and controlled network connectivity.

## 11. Building Quality Gates from Scanner Results

Scanners generate findings; quality gates decide which findings affect merging or releasing.

A policy can classify results as:

- **BLOCK:** high-risk violation or failed mandatory condition.
- **WARN:** requires attention but may proceed within policy limits.
- **INFO:** informational improvement signal, non-blocking.
- **EXEMPTED:** approved exception with defined scope and expiration.
- **UNKNOWN/ERROR:** scanner failed to run or lacked required data.

Example criteria:

| Finding | Common Handling |
|---|---|
| Valid secret in diff or recent history | BLOCK, revoke/rotate, and investigate |
| Dependency with critical runtime-exploitable vulnerability | BLOCK or require mitigation before release |
| Dependency with CVE used only in tests, not packaged | Assess scope; potentially WARN or track in backlog |
| SAST finding with data flow to dangerous sink | BLOCK according to severity and policy |
| Unverified SAST finding or potential false positive | Triage; do not auto-exempt |
| Prohibited license under distribution policy | BLOCK prior to publish |
| Scanner unable to reach vulnerability feed | UNKNOWN/ERROR; handle per risk level and fail-open/fail-closed policy |

Do not rely on a single CVSS threshold for all cases. Combine severity, exploitability, blast radius, exposure, and remediation availability.

### 11.1. When a Scanner Fails or Lacks Data

Scanners can fail due to timeouts, expired licenses, unreachable CVE feeds, or misconfiguration. Never turn a tool error into a PASS result.

Define explicit policies:

- Production releases: require mandatory scans to return valid results.
- Low-sensitivity pull requests: may allow advisory checks to proceed while recording UNKNOWN status.
- Secret scanning or critical privilege checks: block when verification cannot complete.
- Temporary exceptions: require an owner, justification, scope, and expiration date.

The key distinction is between "no vulnerabilities found" and "unable to verify."

## 12. Triaging, Remediating, and Managing Exceptions

A finding must be managed as owned work rather than merely sitting in a dashboard.

Triage workflow:

1. Confirm whether the finding applies to current code or packages.
2. Identify the component, version, location, and impact scope.
3. Assess exploitability and business impact.
4. Determine the fix, upgrade path, or mitigation.
5. Assign an owner and deadline.
6. Update dependencies, source code, or configuration.
7. Re-run relevant scans and tests.
8. Record evidence of resolution.

Exceptions should be granted only with evaluated justification—for instance, no compatible fix exists yet or the finding does not apply to actual usage. A sound exception record specifies:

- Exempted finding or rule.
- Affected component, repository, and version.
- Rationale and supporting evidence.
- Approver.
- Compensating mitigations.
- Expiration or re-evaluation date.

Never use global allowlists to silence a finding across all repositories. Exceptions must be narrowly scoped and traceable.

## 13. Security Evidence Bound to Artifacts

Scan results are valid only for the exact contents scanned. If a pipeline scans commit A and then rebuilds from commit B or produces a different image, prior scan results do not attest to the new artifact.

Each release should attach:

- Commit SHA and repository.
- Pipeline run ID.
- Scanner and ruleset versions.
- SAST timestamp and status.
- Dependency graph, lockfile, and SCA results.
- Artifact SBOM.
- Secret scan status and scanned scope.
- List of active exceptions.
- Artifact digest.
- Provenance and signatures where applicable.

This evidence answers: which artifact was scanned, under which rules, which findings were accepted, and who approved any exceptions.

SBOMs track the components inside an artifact. Provenance records which commit and builder created the artifact. Combining them with SCA results enables teams to rapidly determine whether running versions are affected when a new vulnerability is disclosed.

## 14. Example Integrated Checking Pipeline

The example below is **platform-neutral pseudocode** illustrating relationships between jobs. Adjust actual commands and schemas to match your scanner and CI platform.

~~~yaml
events:
  pull_request:
    permissions:
      source: read
      secrets: none
    jobs:
      - secret_scan_diff
      - sast_changed_code
      - sca_lockfiles
      - unit_tests

  push_to_protected_branch:
    jobs:
      - secret_scan_repository
      - sast_full
      - sca_full_dependency_graph
      - build
      - test

pipeline:
  security_gate:
    requires:
      - secret_scan_passed
      - sast_policy_passed
      - sca_policy_passed
      - test_passed
    on_missing_result: UNKNOWN

  publish:
    depends_on: security_gate
    outputs:
      - immutable_artifact
      - artifact_digest
      - sbom
      - provenance

  release_gate:
    requires:
      - artifact_scan_passed
      - signature_or_provenance_verified
      - approved_exceptions_current

  deploy:
    depends_on: release_gate
    credentials:
      source: short_lived_identity
      scope: target_environment
~~~

The pseudocode highlights key principles:

- Pull requests receive no secrets.
- Source code, dependency, and secret checks can run in parallel.
- Gates aggregate results and distinguish missing data from passes.
- Publishing runs only after mandatory gates pass.
- Releases verify the exact artifact and metadata.
- Deployment credentials are short-lived and scoped to the target environment.

In production systems, ensure publish and deploy jobs cannot be invoked via a path that bypasses gates. Mandatory rules must also be protected in the Git and CI platforms.

## 15. Example Flow for a Java Project

Suppose a Java service uses Maven with both internal and public dependencies.

When a pull request is opened:

1. The secret scanner scans the diff for newly introduced secrets.
2. SAST analyzes modified Java code and associated data flows.
3. SCA inspects the POM and dependency graph for CVEs and licenses.
4. Unit and integration tests run.
5. The gate evaluates new findings, severities, and exceptions.
6. Only if checks pass is the pull request permitted to merge.

After merge:

1. The pipeline scans the entire repository and full dependency graph.
2. Maven builds from the exact commit.
3. The JAR artifact is scanned and its contents verified.
4. The pipeline generates an SBOM, provenance, and digest.
5. The artifact is published to an immutable repository.
6. The release pipeline re-verifies metadata before promoting.
7. Production receives the exact approved artifact digest.

Example commands supporting dependency inspection:

~~~bash
./mvnw -B dependency:tree
./mvnw -B verify
~~~

`dependency:tree` reveals direct and transitive versions; `verify` runs build and test phases configured in the Maven lifecycle. Dedicated scanners are still needed for CVEs, licenses, SAST, and secrets. These two commands alone do not prove an application is secure.

## 16. Common Security Check Implementation Mistakes

| Anti-Pattern | Consequence | Improvement |
|---|---|---|
| Running scanners only before release | Bugs discovered late and costly to fix | Scan early on pull requests and re-scan before release |
| Checking only direct dependencies | Misses transitive vulnerabilities | Scan full dependency graphs and SBOMs |
| Treating CVSS as the sole decision | Ignores actual exploitability in the app | Combine reachability, exposure, and impact |
| Scanning only current files for secrets | Secrets remain in Git history | Scan history and revoke credentials |
| Removing secrets from code without rotating | Old credentials remain usable | Revoke or rotate immediately |
| Giving production secrets to every job | Expands blast radius if any job is compromised | Scope secrets by job and environment |
| Running fork code with high privileges | Pull requests can steal credentials | Enforce trust boundaries and remove secrets from those jobs |
| Suppressing findings via broad allowlists | Risks hidden across many projects | Narrow exceptions with owner and expiry |
| Failing scanners still result in green pipelines | No verification evidence | Record UNKNOWN/ERROR and enforce clear policy |
| Scanning one artifact then publishing another | Evidence does not match shipped software | Scan and publish the exact same digest |
| Failing to record scanner/ruleset versions | Cannot reproduce gate decisions | Record tool version, ruleset, and timestamp |

## 17. Checklist for Integrating SAST, SCA, and Secret Scanning

**Source Code**

- [ ] SAST runs on pull requests and on a full-repository schedule.
- [ ] Rules match the languages and frameworks in use.
- [ ] Findings include location, severity, and remediation guidance.
- [ ] Process exists for triaging false positives and exceptions.
- [ ] Mandatory checks are enforced via main branch protection.

**Dependencies**

- [ ] Direct and transitive dependencies are scanned.
- [ ] Lockfiles are reviewed and committed.
- [ ] Packages originate from controlled sources.
- [ ] Vulnerability and license policies are defined.
- [ ] SBOMs are generated and linked to artifacts.
- [ ] Scheduled scans detect newly disclosed CVEs.

**Secrets**

- [ ] Secret scans cover diffs, repositories, and appropriate history ranges.
- [ ] Artifacts, images, and logs are scanned where necessary.
- [ ] Real secrets are absent from Git, caches, and outputs.
- [ ] Incident procedures exist to rotate/revoke and investigate exposed secrets.
- [ ] Secret exceptions are narrowly scoped and reviewed.

**Pipelines and Credentials**

- [ ] Pull requests from forks receive no sensitive secrets.
- [ ] Jobs run with minimal permissions.
- [ ] Secrets are exposed only to jobs that need them.
- [ ] OIDC or short-lived credentials are preferred.
- [ ] External actions, plugins, and scripts are reviewed and pinned per policy.
- [ ] Runners have appropriate lifecycles and cleanup mechanisms.

**Gates and Traceability**

- [ ] BLOCK, WARN, INFO, UNKNOWN, and EXEMPTED states are defined.
- [ ] Scanner errors are never treated as PASS.
- [ ] Exceptions have owners, rationales, and expiration dates.
- [ ] Findings and scan results are bound to commit, pipeline run, and artifact digest.
- [ ] The published artifact is the exact artifact that was scanned.

## 18. Conclusion

Integrating SAST, SCA, and secret scanning enables CI/CD to inspect three major risk sources: team-written code, external components, and authentication material. Checks must run at multiple points: fast feedback on pull requests, comprehensive scans after merge, scheduled dependency re-scans, and pre-release artifact verification.

A trustworthy pipeline does not merely run scanners—it distinguishes passes, violations, warnings, and unverifiable states. Credentials must be issued strictly along trust boundaries, exposed secrets must be revoked or rotated, and every finding or exception must have an owner and supporting evidence. When security results are bound to commits and artifact digests, teams can explain why a change was allowed forward and govern risk across the entire release lifecycle.
