# Validating Configuration Before Running Against Live Environments

## 1. Why validate pipeline configuration before deployment?

Pipeline as Code puts build, test, and deployment workflows into Git-managed configuration files. These files are also source code: they can contain syntax errors, broken references, missing conditions, overly broad permissions, or dangerous deployment commands. A syntactically valid pipeline can still produce harmful behavior at runtime.

A small configuration mistake can impact an entire environment. For example:

- A misconfigured trigger causes a production deployment job to run on a pull request.
- Overly broad default permissions allow a source verification job to write to the repository or modify an environment.
- An incorrect configuration value points the application to the wrong database.
- A Kubernetes manifest accidentally grants privileged mode or mounts sensitive host paths.
- A Terraform plan modifies resources outside the intended scope.
- A verification step is skipped due to an inaccurate condition or path filter.
- A broken secret reference prevents the application from starting or leaks data in logs.

Therefore, pre-deployment configuration validation is an integral part of CI/CD. The goal is to catch problems while changes are still in review, define clearly which configurations may proceed, and retain evidence for traceability.

Within the scope of **DEVOPS_CI_CD_FUNDAMENTALS**, pipelines must support automated verification, artifact and environment management, quality gates, secret protection, post-deployment verification, and rollback. Configuration validation connects those capabilities: it ensures pipelines and deployment configs enforce policy before touching live systems.

## 2. Configuration validation spans multiple layers

Parsing YAML cleanly should never be treated as proof that configuration is safe. A thorough validation workflow inspects multiple layers.

| Validation layer | Question to answer | Examples |
|---|---|---|
| Syntax | Can the file be parsed cleanly? | Valid YAML, no broken indentation or structure |
| Schema | Do fields and data types match the contract? | Workflow declares valid fields; Kubernetes manifest matches API schema |
| Semantics | Are values sensible and do references exist? | Jobs depend on existing jobs, env vars are declared, images are versioned |
| Security | Does the config introduce excessive privileges or attack surface? | No exposed secrets, least privilege, no privileged containers |
| Operations | Can the config run reliably and recover? | Health checks, timeouts, resource limits, and rollback plan present |
| Policy | Does the change satisfy organizational standards? | No production deploy without approval or with blocking violations |

These layers complement one another. A file can pass syntax and schema checks yet still fail semantically. A manifest can execute cleanly yet violate security policies. A deployment can succeed yet lack verification or recovery mechanisms.

A practical workflow runs cheap, fast checks first, followed by checks requiring specialized environments or elevated access.

## 3. Scoping which configurations require validation

A CI/CD system typically manages several configuration types, each needing tailored checks.

| Configuration type | Typical contents | Validation approach |
|---|---|---|
| Pipeline workflow | Triggers, jobs, steps, dependencies, conditions, permissions | YAML parser, schema validator, linter, flow checks |
| Build and test | Toolchain, dependencies, caches, test tasks | Version checks, lockfiles, test builds, and tests |
| Container | Dockerfile, base image, build args, runtime user | Dockerfile linter, image scanning, digest checks |
| Kubernetes | Deployment, Service, Ingress, ConfigMap, Secret references | Schema validation, manifest linting, policy tests |
| Helm or Kustomize | Charts, values, overlays, templates | Lint, render, and schema/policy checks on rendered output |
| Infrastructure as Code | Terraform, Pulumi, or similar infra definitions | Format, validate, plan, policy as code |
| Application configuration | Endpoints, feature flags, timeouts, connection pools | Schema, required keys, environment compatibility |
| Release policy | Environments, approvals, rollouts, rollbacks | Permissions, conditions, policy, and audit trail checks |

Clarify which files are configuration sources, which are generated, and which are deployment artifacts. For instance, Helm templates produce final manifests from charts and values. Validate both source charts and rendered manifests, because bugs often emerge only after merging multiple values files or templates.

Similarly, a pipeline may call external reusable workflows or scripts. Validating only the calling workflow file is insufficient without validating the reusable workflow, action versions, scripts, and dependencies it invokes.

## 4. Building a validation pipeline from fast to deep

A sensible validation sequence proceeds in this order:

1. Parse syntax and check formatting.
2. Validate schemas per file type.
3. Run linters and semantic checks.
4. Scan for secrets, dependency issues, and security flaws.
5. Render or simulate outputs.
6. Evaluate policies against final rendered configurations.
7. Execute dry runs or plans in a controlled environment.
8. Permit live deployment only once mandatory gates pass.

~~~mermaid
flowchart TD
    A["Pull request changing configuration"] --> B["Parse and format"]
    B --> C{"Valid syntax?"}
    C -- "No" --> X["Report error, block merge"]
    C -- "Yes" --> D["Schema and lint"]
    D --> E{"Structure and semantics pass?"}
    E -- "No" --> X
    E -- "Yes" --> F["Secret, dependency, and security scan"]
    F --> G{"No blocking violations?"}
    G -- "No" --> X
    G -- "Yes" --> H["Render, plan, or dry run"]
    H --> I["Policy check and review results"]
    I --> J{"Eligible for release?"}
    J -- "No" --> X
    J -- "Yes" --> K["Environment approval"]
    K --> L["Deploy identified artifact"]
    L --> M["Health check and post-deploy verification"]
~~~

Not every configuration type requires every step. For example, editing documentation text does not require a Terraform plan. However, changing IAM permissions or production manifests requires deeper verification than updating a label. Select validation suites according to file type and blast radius.

## 5. Syntax, schema, and semantic checks

### 5.1. Syntax validation

Parsers confirm a file can be read according to its declared format. In YAML, common mistakes include:

- Inconsistent indentation.
- Using tabs where spaces are required.
- Missing colons or quotes.
- Values containing special characters without proper quoting.
- Duplicate keys causing one value to silently overwrite another depending on the parser.
- Unexpected data types, such as strings coerced into booleans or null.

Use a parser matching the format and specification version the platform actually supports. YAML 1.1 and YAML 1.2 differ in interpreting values like true, false, yes, no, or on, off. Therefore, never rely on a generic YAML reader alone to conclude a platform workflow has the intended meaning.

Linters can check formatting and catch common mistakes. However, linters do not replace schema validators or semantic checks.

### 5.2. Schema validation

A schema defines the permitted structure of a configuration type: required fields, data types, allowed values, and disallowed fields.

Examples:

- CI platform workflows have schemas for triggers, jobs, steps, and permissions.
- Kubernetes provides OpenAPI schemas per API version.
- Helm charts can declare schemas for values.
- Application configurations can be validated with JSON Schema.
- Terraform providers define resource types and attributes.

Schema validation catches misspelled field names, numbers passed where strings are expected, or missing required properties. However, schemas generally cannot prove that external references exist or that values suit a target environment.

### 5.3. Semantic validation

Semantic checks examine relationships between components and configuration intent.

Examples for pipelines:

- Does a job declare a dependency on a non-existent job?
- Could a condition let a release job run without an artifact?
- Does a step reference another job's output properly?
- Do triggers fire on the intended event types?
- Does any execution path bypass a mandatory check?
- Could a deploy job run in parallel with the artifact-building job?

Examples for deployment configs:

- Does the Deployment match the Service properly?
- Does the Service selector match Pod labels?
- Do volume mounts reference declared volumes?
- Do Secret references have valid names and keys?
- Do readiness probes use the right port and path?
- Are resource requests and limits within permitted bounds?

These errors may pass parsers and schemas cleanly. Thus, specialized linters, cross-reference checks, and tests on rendered configurations are essential.

## 6. Validating workflows and pipeline logic

Workflows are code orchestrating automation. Both structure and execution paths must be inspected.

### 6.1. Triggers and run conditions

Validate triggers to ensure pipelines run at the right times without opening unintended deployment paths.

Points to verify:

- Pull requests only trigger jobs safe for untrusted code.
- Pushes to integration branches run required checks.
- Release tags are validated against conventions.
- Production jobs run only under authorized events and privileges.
- Path filters do not accidentally skip required status checks.
- Branch, tag, and event conditions do not conflict.
- Changes from forks never receive secrets or deploy privileges.

Test both positive and negative cases. For example, a valid tag must trigger the release workflow; an invalid tag format must be rejected. Pull requests must run tests without deploying to production.

### 6.2. Dependencies between jobs and steps

A pipeline can run many jobs in parallel. Confirm dependencies match data flow and quality gates.

For example, a deploy job must depend on the jobs that build and verify the artifact. Depending only on test without depending on publish could deploy a stale or indeterminate artifact.

Also check for these scenarios:

- A job is skipped by a condition yet downstream jobs still run.
- A job continues after failure because configuration permits it.
- Outputs are missing or not forwarded across dependencies.
- Retries produce a new artifact without updating metadata.
- Two deploy jobs write concurrently to the same environment.

### 6.3. Timeouts, retries, and concurrency

Timeouts prevent pipelines from hanging indefinitely when dependent services stall. Retries help with transient glitches, but must never loop endlessly or mask configuration bugs.

Distinguish clearly:

- Transient network or registry errors may use bounded retries.
- Syntax, permission, or schema errors require fixing configuration.
- Deterministic test failures require investigation, not retrying until green.
- Deploy jobs need locking or concurrency controls to prevent two versions writing to an environment simultaneously.

Retries must preserve traceability. If a retry produces a new artifact, the pipeline must record the new identifier without confusing it with the prior attempt's artifact.

## 7. Validating Kubernetes, Helm, and container configs

Deployment manifests are often assembled from multiple sources: templates, environment values, overlays, and runtime variables. Checking source files alone is insufficient; final outputs must be checked.

### 7.1. Rendering before deployment

With Helm, teams can lint and render templates into manifests to inspect the exact resources produced. With Kustomize, overlays can be built to generate final output. Rendered manifests should be retained as verification evidence or linked to the corresponding commit and artifact.

Verify:

- Namespaces and resource names match the target environment.
- Images reference approved versions or digests.
- Service selectors match Pod labels.
- Ports and targetPorts match the application.
- ConfigMap and Secret references exist per contract.
- Probes use sensible timeouts, periods, and thresholds.
- Resource requests/limits fit workload demands and quotas.
- Replicas, rollout strategies, and disruption policies meet availability requirements.

### 7.2. Manifest security checks

Certain settings must be governed by policy:

- Containers do not run privileged without an approved exception.
- Avoid running as root unnecessarily.
- Do not mount hostPath or sensitive sockets arbitrarily.
- Set filesystems read-only where the application supports it.
- Grant Linux capabilities only when required.
- Service accounts do not receive cluster-wide privileges beyond job scope.
- Network policies restrict traffic to necessary paths.
- Images come from trusted registries with explicit identifiers.
- Secrets are never written directly into manifests, repositories, or logs.

Policies can be enforced using tools like Conftest/OPA, Kyverno, or platform admission policies. Evaluate policies against rendered manifests, since final values may originate from templates or overrides.

### 7.3. Container image checks

Dockerfiles and images need dedicated verification:

- Base images come from trusted sources with controlled versions.
- Dependencies are pinned according to policy.
- Builds never bake secrets into layers or persisted build arguments.
- Images exclude unnecessary tools or packages.
- Runtime users and filesystem permissions are restricted.
- Images are scanned for vulnerabilities and carry SBOMs when required.
- Release artifacts are referenced by digest when immutability is required.

An image scan alone cannot prove an application is completely secure. Findings must be evaluated by severity, exploitability, usage context, and exception policy.

## 8. Validating Infrastructure as Code before changing infrastructure

With Terraform, Pulumi, or similar tools, configurations can create or modify live cloud resources. Distinguish validation levels clearly.

| Level | Example | What it detects |
|---|---|---|
| Format | terraform fmt -check | Inconsistent formatting |
| Validate | terraform validate | Structural and configuration errors within modules |
| Static analysis | Linters or IaC scanners | Risky configurations and best-practice violations |
| Plan | terraform plan | Planned resource additions, modifications, or deletions |
| Policy check | OPA/Conftest or policy engine | Org rules on regions, permissions, encryption, networking, and cost |
| Review | Accountable owner inspects plan | Business impact and unintended risks |

A plan is critical evidence but must be read carefully. A change may replace resources, destroy data, or widen privileges. Teams should scrutinize destroy/replace actions and changes to IAM, security groups, routes, storage encryption, databases, and public exposure.

Key principles:

- Plans must use the target environment's exact workspace, backend, and variables.
- Never expose sensitive plan values in public logs or artifacts.
- Run planning with least-privilege read/plan permissions; separate apply permissions.
- Store plans tied to the commit and creation timestamp.
- If infrastructure state changes after a plan was generated, re-generate the plan before applying.
- Production applies require approvals and audit trails per policy.
- Never auto-apply simply because the plan command returned a zero exit code.

Note: planning can read state and invoke provider data sources or APIs. Therefore, even before mutating resources, control credentials, read permissions, and what gets logged.

## 9. Checking secrets, permissions, and the supply chain

### 9.1. Secret detection

Secret scanning looks for patterns of tokens, private keys, passwords, or accidentally committed credentials. Combine:

- Scanning changed lines in pull requests.
- Scanning the full repository and history when needed.
- Scanning artifacts or images if required by process.
- Inspecting logs and outputs to prevent printed secrets.
- Detecting configs containing literal credential values instead of secret manager references.

If a real secret is found in a commit, deleting the line in a new commit is not enough. Revoke or rotate the credential, audit commit history, and evaluate copies that may have been cloned.

### 9.2. Pipeline permission checks

Pipelines can hold permissions to read repositories, create releases, push to registries, access clouds, or deploy to clusters. Permissions should be scoped per job and per environment.

Items to verify:

- Lint and test jobs hold only permissions needed to read code.
- Publish jobs hold write access only to the intended registry or package.
- Deploy jobs hold access only to the targeted namespace or managed resources.
- Production privileges are never granted to untrusted pull requests.
- Short-lived credentials are preferred where supported.
- OIDC or workload identity scopes identity by repository, branch, environment, and workflow.
- Secrets are provided only to jobs that need them, never passed through outputs or logs.

### 9.3. Pinning pipeline dependencies

A pipeline's behavior can change if external actions, plugins, images, or scripts are referenced via mutable tags.

To improve stability:

- Pin critical actions or plugins by commit SHA where supported.
- Pin container images by digest for sensitive steps.
- Control toolchain versions.
- Review pipeline dependency updates.
- Update periodically via a tested workflow.
- Record tool versions used to produce each artifact.

Version pinning improves reproducibility but does not guarantee a dependency is safe. Continue monitoring vulnerabilities, upstream provenance, and policy-driven updates.

## 10. Policy as Code: turning requirements into automated checks

Policy as Code expresses organizational rules as executable configuration or code. Examples:

- Production workloads must not run privileged.
- Critical storage must not be unencrypted.
- Administrative ports must not be exposed to the Internet.
- Releases must not use the `latest` image tag.
- Every production deployment requires approval.
- Every released artifact must have commit provenance.
- Resources must carry owner, environment, and cost center tags per convention.
- Production jobs must not run from external pull requests.

Policies need clear enforcement levels:

- **Block:** violations halt the pipeline.
- **Warn:** violations are reported while allowing progress within permitted scope.
- **Exception:** permits time-bounded exceptions with rationale, approver, and scope.

Avoid turning every warning into a blocking failure. Overly rigid or context-blind policies generate excessive manual exceptions. Conversely, making severe risks warning-only undermines quality gates.

An exception record should document:

1. Which rule is waived.
2. Which resource or environment is affected.
3. Rationale and risk assessment.
4. Approver identity.
5. Mitigating controls.
6. Expiration timestamp or review date.

### 10.1. Conceptual policy example

~~~yaml
policy:
  production:
    require_approval: true
    require_artifact_digest: true
    require_commit_provenance: true

  container:
    deny_privileged: true
    deny_latest_tag: true
    require_non_root: true

  infrastructure:
    require_encryption: true
    deny_public_admin_ports: true
    require_owner_tag: true

  secrets:
    deny_plaintext_credentials: true
    require_secret_reference: true
~~~

This structure is illustrative, not a specific policy engine's schema. In practice, translate each rule into an evaluable, testable, and explainable policy.

## 11. Dry runs, previews, and testing in controlled environments

After static validation, some changes need simulation to see what the system will actually do.

These mechanisms differ in scope:

| Check method | Meaning | Limitations |
|---|---|---|
| Local render | Generate output from templates and values without calling live environments | Does not prove the API server or cloud will accept the change |
| Client-side dry run | Simulate or validate locally within client tool capabilities | May lack state from the target environment |
| Server-side dry run | Submit validation request to API server without persisting changes if supported | Requires access permissions; admission webhooks and cluster version affect results |
| Infrastructure plan | Display planned infrastructure changes | Depends on state, providers, and data read at plan time |
| Ephemeral environment | Deploy to a scoped temporary environment | Has its own cost, data, and dependencies; not identical to production |
| Staging deployment | Verify in a production-like environment | May differ from production in load, permissions, data, and dependent services |

Dry runs are not absolute guarantees. For example, clean Helm rendering does not prove a cluster has sufficient quota or permissions. A Terraform plan does not guarantee apply succeeds if state changes afterward. Server-side dry runs catch admission errors yet do not verify runtime application behavior.

Choose simulation depth proportional to risk. Documentation pipeline changes may need only parsers and linters. Network policy or database changes need plans, reviews, and testing in a safe environment.

## 12. Designing pre-production gates

A solid production gate defines what evidence must exist before deployment proceeds.

Examples:

- Workflows and configurations parsed, validated, and linted cleanly.
- Mandatory security scans meet policy thresholds.
- Rendered manifests or IaC plans passed policy checks.
- Artifacts carry digests, commits, and provenance.
- Artifacts passed verification in an upstream environment.
- Plans or deployment previews contain no unexpected changes.
- Authorized approvers have signed off.
- Target environment configs and secret references satisfy contracts.
- Health checks, rollout timeouts, and rollback plans are in place.

Gates must evaluate the exact artifact and exact configuration being deployed. If the pipeline rebuilds an image or re-renders manifests with different inputs after checks pass, earlier evidence may no longer match what gets released.

Record the following in each release record:

- Commit SHA.
- Artifact digest and registry.
- Pipeline run ID.
- Toolchain versions.
- Test and scan results.
- Policy version.
- Approved manifests or plans, where applicable.
- Approver and approval timestamp.
- Target environment.
- Post-deployment verification outcome.

## 13. Example pre-deployment validation workflow

The example below illustrates a GitHub Actions workflow validating Kubernetes and Helm configurations before permitting deployment. Actions and tools must be installed or version-pinned per repository policy. In high-assurance supply-chain environments, pin actions by commit SHA rather than illustrative tags.

~~~yaml
name: Validate deployment configuration

on:
  pull_request:
    paths:
      - ".github/workflows/**"
      - "deploy/**"
      - "policy/**"
  push:
    branches:
      - main
  workflow_dispatch:
    inputs:
      artifact_digest:
        description: Immutable digest of an already validated artifact
        required: true
        type: string

permissions:
  contents: read

jobs:
  validate:
    runs-on: ubuntu-latest
    permissions:
      contents: read

    steps:
      - name: Checkout source
        uses: actions/checkout@v4

      - name: Check workflow syntax
        run: actionlint

      - name: Lint YAML files
        run: yamllint .github/workflows deploy

      - name: Lint Helm chart
        run: helm lint deploy/chart

      - name: Render staging manifests
        run: |
          helm template application deploy/chart \
            --values deploy/values/staging.yaml \
            > rendered-staging.yaml

      - name: Validate Kubernetes schema
        run: kubeconform -strict -summary rendered-staging.yaml

      - name: Evaluate deployment policies
        run: conftest test rendered-staging.yaml --policy policy/

      - name: Scan configuration
        run: checkov -f rendered-staging.yaml

  deploy:
    needs: validate
    if: github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    environment: production
    permissions:
      contents: read
      id-token: write
    steps:
      - name: Deploy approved artifact
        env:
          ARTIFACT_DIGEST: ${{ inputs.artifact_digest }}
        run: ./deploy/deploy-approved-artifact.sh --digest "$ARTIFACT_DIGEST"
~~~

This is a structural example for discussion, not a complete production workflow. The workflow_dispatch event requires operators to supply the immutable digest of an already verified artifact; the deploy job runs only when manually triggered from the main branch. The production environment needs protection rules and authorized approvers enabled. The deployment script must verify digest, provenance, and permissions before modifying the environment. The checkout action here uses an illustrative tag; repositories with strict supply-chain requirements should pin actions by commit SHA. This example also shows that validating conditional logic and inputs matters just as much as validating YAML syntax.

A more complete setup should pass an artifact digest built and verified by a release pipeline, enforce permissions and environment protections, and run controlled deployment scripts. Never rebuild artifacts inside a production job.

## 14. Testing configuration validators themselves

Validators are also code and can contain bugs. Untested policies or linters can block valid changes or let dangerous changes slip through.

Test across three categories:

**Positive tests**

- Valid configurations pass parsers and schemas.
- Least-privilege manifests pass policies.
- Artifacts with valid digests and provenance are accepted.
- Eligible deployment requests pass gates.

**Negative tests**

- Malformed syntax fails.
- Plaintext secrets are detected.
- Privileged containers are blocked by policy.
- `latest` image tags are rejected if policy forbids them.
- Production deployments without approvals cannot run.
- Plans deleting databases or opening unexpected admin ports require review or are blocked.

**Exception tests**

- Approved, unexpired exceptions are honored per policy.
- Expired exceptions are rejected.
- Exceptions apply strictly to the designated resource and environment.
- Severe violations are not masked by overly broad exceptions.

Store valid and invalid sample configurations in the repository. Whenever policies change, re-run the entire test suite to verify rules still behave properly.

## 15. Handling validation results and exceptions

A good error message helps the author understand:

- Which file and line has the issue.
- Which rule was violated.
- Why the rule exists.
- How to fix it or where relevant documentation lives.
- Whether an exception can be requested and who can approve it.

Never return a generic message like configuration invalid alone. Also never print full environments, credentials, or secret contents while debugging.

When validation fails:

1. Block dependent steps if the violation is mandatory.
2. Retain sanitized logs and reports.
3. Link results to the commit and pipeline run.
4. Allow re-runs after configuration fixes.
5. Record approved exceptions formally when valid justification exists.
6. Track recurring failures to improve validators or documentation.

If a check frequently produces false positives, identify the root cause and fix the validator. Adding skip or continue-on-error to critical jobs undermines quality gates.

## 16. Post-deployment verification remains mandatory

Configuration passing static validation and dry runs can still fail in live runs due to differences in permissions, quotas, dependent service state, data, or load.

After deployment, verify at minimum:

- Deployments or resources reached ready state.
- Health endpoints and smoke tests pass.
- The application reads its configuration and required secret references cleanly.
- Error rates and latency show no abnormal spikes.
- Critical business flows complete properly.
- Logs, metrics, and traces carry version context for traceability.
- Rollout pauses or rolls back when policy thresholds are breached.

For canary rollouts, establish thresholds and observation windows before shifting more traffic. If signals degrade, the pipeline must halt promotion and trigger the defined recovery procedure.

Rollbacks must use stored artifacts and verify data compatibility. For database or schema changes, rolling forward or applying data recovery procedures may be needed rather than simply redeploying an older binary.

## 17. Common anti-patterns

| Anti-pattern | Consequence | Improvement |
|---|---|---|
| Parsing YAML only and deploying immediately | Misses schema, logic, and security errors | Add schema, semantic, security, and policy validation |
| Validating source files without checking rendered output | Values assembled from templates may be wrong | Render per environment and validate the output |
| Exposing production secrets in pull requests | Untrusted code can read or leak secrets | Separate jobs, restrict permissions, and scope credentials per environment |
| Using the `latest` tag for released images | Image contents can change without config changes | Pin versions or digests |
| Auto-applying Terraform plans immediately | Infrastructure changes bypass review | Separate plan, policy, approval, and apply |
| Treating dry runs as absolute guarantees | Ignores live environment differences | Combine plans, staging, and post-deploy verification |
| Policies emit only generic errors | Authors struggle to know how to fix issues | Emit rule ID, location, and remediation guidance |
| Allowing all checks to be skipped in emergencies | Exceptions become the default path | Define scoped, approved, time-bounded exceptions |
| Logging all environment variables when debugging | Risk of leaking tokens and credentials | Redact sensitive data; log only necessary info |
| Not testing validators | Policies can block valid changes or miss bugs | Maintain positive, negative, and exception tests |

## 18. Checklist before allowing configuration into production

**Structure and semantics**

- [ ] Parsers read all files cleanly.
- [ ] Schemas match platform versions.
- [ ] Linters report no mandatory errors.
- [ ] Job, output, file, resource, and dependency references are valid.
- [ ] Triggers and conditions are tested for both allow and deny cases.

**Security and permissions**

- [ ] No plaintext secrets exist in repositories or outputs.
- [ ] Jobs hold least-privilege permissions only.
- [ ] Code from forks or untrusted sources receives no sensitive credentials.
- [ ] Critical actions, plugins, images, and toolchains are pinned or version-controlled.
- [ ] Security policies run against rendered configurations.

**Deployment and infrastructure**

- [ ] Manifests, Helm charts, or IaC have been rendered/planned.
- [ ] Target environment configuration is verified.
- [ ] Destroy/replace actions or privilege expansions have been reviewed.
- [ ] Artifacts carry digests and provenance.
- [ ] Production environment approvals exist per policy.
- [ ] Verified artifacts are not rebuilt.

**Operations and recovery**

- [ ] Timeouts, health checks, and smoke tests are configured.
- [ ] Rollout halt conditions exist.
- [ ] Previous artifacts or recovery plans are available.
- [ ] Logs and release records provide complete traceability.
- [ ] Accountable owners handle alerts and exceptions.

Adapt this checklist to service type and blast radius. A documentation configuration change may not require the same control depth as changing cloud permissions or production databases.

## 19. Conclusion

Pre-deployment configuration validation must go far beyond confirming YAML syntax is valid. Pipeline as Code must be verified for schema, semantics, security, permissions, policies, and operational impact. For configurations creating infrastructure or deployment resources, render or plan them so actual outputs are reviewed before changing live environments.

A reliable flow combines static checks, policy as code, controlled simulation, properly authorized approvals, and post-deployment verification. Link every outcome to a commit, artifact, and policy version so the team can explain why a change was permitted to proceed. That turns the pipeline into an evidence-backed quality gate that ships fast while keeping live environment impact under control.
