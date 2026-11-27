# Checking Code, Dependencies, and Infrastructure Configuration in Pipelines

In the **CI/CD and Releases** chapter, security and quality checks must run automatically before artifacts enter a serverless environment. A Java function might compile and pass unit tests yet still contain vulnerabilities in transitive libraries, accidentally package secrets, grant overly broad IAM permissions, or misconfigure triggers causing message loss on retries. Therefore, pipelines must inspect source code, dependencies, and infrastructure configuration simultaneously.

This lesson belongs to the **CLOUD_SERVERLESS** module, focusing on developing and deploying serverless applications—particularly Java functions triggered by HTTP, messages, or events. Learners handle triggers, state, permissions, retries, idempotency, cold starts, scaling, and cost to determine when to use FaaS. Pipeline checks help detect risks before a function receives data access permissions or production traffic.

## 1. Why Run Checks in CI/CD?

A serverless release typically comprises multiple components:

- Java source code, resources, and configuration files.
- Direct libraries and transitive dependencies.
- JAR, ZIP deployment packages, or container images.
- Infrastructure templates such as AWS SAM, CloudFormation, CDK, or Terraform.
- IAM roles, resource policies, event source mappings, and triggers.
- Environment variables, secret references, networking, and logging configurations.

An error in any component can increase security risk or cause outages. For example:

- A JSON parser dependency has a CVE allowing malicious payload processing.
- Source code logs access tokens or personal data.
- Terraform creates an unintentionally public Lambda Function URL.
- An execution role has s3:* permissions across the entire account.
- An SQS event source mapping lacks proper DLQ or redrive configuration.
- A container image includes OS packages with critical vulnerabilities.
- A template sets timeouts too low, causing messages to retry continuously.
- Secrets are passed directly into environment variables and appear in deployment descriptions or logs.

Pipeline checks establish a repeatable quality gate. Every commit or pull request is evaluated against the same rules, with reports traceable back to the source revision.

## 2. Check Layers

Different types of checks complement one another and catch different issues.

| Check Layer | Target | Example Tools |
|---|---|---|
| Code quality | Conventions, potential bugs, complexity | Checkstyle, PMD, SpotBugs |
| SAST | Detecting risky code patterns | CodeQL, Semgrep, SonarQube |
| SCA | Dependency vulnerabilities and licenses | OWASP Dependency-Check, OSV-Scanner, Trivy |
| Secret scanning | Committed credentials or secrets | Gitleaks, detect-secrets |
| IaC scanning | Insecure cloud configurations | Checkov, tfsec, cfn-lint, cdk-nag |
| Policy as code | Organizational rules for infra and releases | OPA/Conftest, CloudFormation Guard |
| Artifact/image scanning | Dangerous components in release packages | Trivy, ECR image scanning |
| SBOM/provenance | Artifact contents and origin | CycloneDX, SPDX, SLSA attestations |

No single tool should be treated as a complete solution. SAST does not replace SCA; IaC scanners do not detect bugs in Java; secret scanners do not prove a credential was revoked. Know which layer protects which assets and which risks remain unchecked.

~~~mermaid
flowchart TD
    SRC["Pull request / source"] --> CODE["Compile, lint, unit test"]
    CODE --> SAST["SAST"]
    SRC --> SECRET["Secret scan"]
    SRC --> SCA["Dependency / license scan"]
    SRC --> IAC["IaC scan and policy"]
    SAST --> GATE{"Quality gates"}
    SECRET --> GATE
    SCA --> GATE
    IAC --> GATE
    GATE --> BUILD["Build immutable artifact"]
    BUILD --> SBOM["SBOM and artifact scan"]
    SBOM --> SIGN["Sign / attest"]
    SIGN --> DEPLOY["Deploy to test environment"]
    DEPLOY --> VERIFY["Integration and smoke tests"]
    VERIFY --> RELEASE["Approve and promote"]
~~~

Pipelines should inspect both source before build and artifacts after build. Source scans find issues in code; artifact scans verify the exact contents about to be deployed, including dependencies actually packaged.

## 3. Java Compilation and Quality Checks

Before running specialized scanners, the pipeline must confirm the project compiles and adheres to baseline quality rules.

With Maven:

~~~bash
mvn -B clean verify
~~~

verify executes preceding phases in the Maven lifecycle, including compile, test, and bound plugins. The pipeline should explicitly configure plugins so static analysis, test coverage, or formatting checks run in the right phases.

Common tools:

- **Checkstyle:** checks style, naming, imports, and code conventions.
- **PMD:** finds code smells and common logic bugs.
- **SpotBugs:** analyzes bytecode for likely bugs.
- **SonarQube/SonarCloud:** aggregates quality, coverage, maintainability, and security findings per ruleset.
- **Error Prone:** detects certain Java errors directly during compilation.

These tools do not share identical goals. For example, formatting issues do not imply security vulnerabilities; concurrency bugs may go unnoticed by style rules.

### 3.1. Pinning Tool Versions

Build plugins and scanners are also pipeline dependencies. Declare explicit versions, update in a controlled manner, and avoid letting builds automatically pull arbitrary new versions on every run.

Maven structure example:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>com.github.spotbugs</groupId>
            <artifactId>spotbugs-maven-plugin</artifactId>
            <version>APPROVED_VERSION</version>
            <executions>
                <execution>
                    <phase>verify</phase>
                    <goals>
                        <goal>check</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

APPROVED_VERSION is a placeholder to be replaced with an organization-approved version pinned in the repository. Keep JDK, Maven/Gradle wrapper, and plugin versions aligned between developer machines and CI.

With Gradle, use the wrapper and pin plugin versions in the plugins block or version catalog. Do not rely on a globally installed Gradle on the runner.

## 4. SAST: Static Source Security Analysis

Static Application Security Testing (SAST) analyzes source code or bytecode to find patterns that may lead to vulnerabilities. Tools can detect:

- SQL injection from concatenating input into queries.
- Command injection when passing input to a shell.
- Path traversal when using unvalidated request paths.
- Unsafe deserialization.
- Hardcoded credentials or tokens.
- Weak cryptography or misconfigured TLS.
- Information leakage via logs or exception responses.
- SSRF from calling user-controlled URLs.
- Missing authorization checks before accessing resources.

Java code example with SQL injection risk:

~~~java
String sql = "SELECT * FROM orders WHERE id = '" + orderId + "'";
Statement statement = connection.createStatement();
ResultSet result = statement.executeQuery(sql);
~~~

Use parameterized queries instead:

~~~java
String sql = "SELECT * FROM orders WHERE id = ?";
try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, orderId);
    try (ResultSet result = statement.executeQuery()) {
        // Read results.
    }
}
~~~

SAST can catch some SQL concatenation patterns, but cannot prove all data paths are safe. Examine source-to-sink flows, validation, framework behavior, and real context.

### 4.1. SAST in Pull Requests

A typical flow:

1. Scan changed files in pull requests for fast feedback.
2. Run full-repository scans on a schedule to detect issues in older code.
3. Triage findings by severity, confidence, and location.
4. Require fixing new findings whose risk exceeds thresholds.
5. Allow exceptions with an owner, rationale, and expiration date.

Never disable an entire rule just because of a single false positive. Create narrow suppressions for specific findings with justification and a review date.

### 4.2. SAST Is Not Runtime Testing

SAST cannot verify production IAM roles, network routes, or event source mapping retry behavior. Combine it with integration tests, IaC scanning, and deployment configuration checks.

## 5. SCA: Checking Direct and Transitive Dependencies

Software Composition Analysis (SCA) inspects third-party libraries used by the application. Java projects commonly have direct dependencies and transitive dependencies.

For example, an application declares an HTTP framework; that framework depends on logging, parsing, or utility libraries. A vulnerability in a transitive dependency can still affect the application even if the development team did not declare it directly.

With Maven, inspect the dependency tree:

~~~bash
mvn -B dependency:tree
~~~

With Gradle:

~~~bash
./gradlew dependencies
./gradlew dependencyInsight --dependency jackson-databind
~~~

SCA typically matches packages, versions, and metadata against vulnerability databases. Tools may use CVE, GitHub Advisory Database, OSV, or vendor advisories.

### 5.1. OWASP Dependency-Check and OSV-Scanner

A pipeline can use OWASP Dependency-Check to identify dependencies with matching advisories. OSV-Scanner matches package versions against the OSV database. Trivy can also scan filesystems, lockfiles, images, and certain artifact formats.

Example running scanners as dedicated pipeline steps:

~~~bash
dependency-check --project "orders-lambda" --scan .
osv-scanner scan source -r .
~~~

Exact syntax depends on tool version and runner installation. Use commands and output formats matching the version pinned in CI.

### 5.2. Assessing Risk Severity

Do not decide every finding solely by CVSS score. Consider:

- Is the dependency included in the production artifact?
- Does code invoke the vulnerable component?
- Can the vulnerability be exploited through inputs the function accepts?
- Does the function run with sensitive permissions?
- Is there a public exploit or signs of active exploitation?
- Is a patch or safe workaround available?
- Does the runtime or platform partially mitigate the risk?

For instance, a library with a CVE in an XML parser module when the application does not package that module has a different exposure than a function accepting XML from the Internet and calling that exact vulnerable parser.

However, do not conclude "unreachable" merely because no direct call is visible. Frameworks may invoke dependencies via reflection, service loaders, or auto-configuration. Inspect the dependency graph and how the runtime loads classes.

### 5.3. Locking Dependency Versions

For repeatable builds:

- Declare explicit versions or use pinned BOMs.
- Verify dependency lockfiles if the build system supports them.
- Avoid dynamic versions like 1.+ in production builds.
- Never fetch dependencies from untrusted repositories.
- Track build plugins and annotation processors as well.
- Update dependencies on schedule and upon critical advisories.

With Maven, dependencyManagement/BOM unifies versions across the dependency tree. With Gradle, version catalogs and dependency locking control resolved versions.

## 6. Dependency License Checks

SCA can detect third-party library licenses. Licensing is part of legal and artifact distribution risk.

Know:

- Licenses of direct and transitive dependencies.
- Obligations when distributing binaries or source.
- Requirements to retain copyright notices or license texts.
- Organizational policies on restrictive or unknown-origin licenses.
- How dual-licensed libraries are handled.

Do not assume a license is permitted based solely on an abbreviation. Unclear cases should be escalated to legal teams or open-source officers. Pipelines can block banned licenses and raise findings to review cases requiring evaluation.

## 7. Secret Scanning

Secret scanners detect credentials that might be committed to source, config files, or repository history. Common patterns:

- AWS access keys and secrets.
- API tokens.
- Private keys.
- Passwords in connection strings.
- OAuth client secrets.
- Webhook signing secrets.
- Credentials in .env, YAML, or JSON files.

Tools include Gitleaks, detect-secrets, and built-in Git platform secret scanning.

Example running Gitleaks:

~~~bash
gitleaks detect --source . --redact
~~~

Depending on the version, the command may be gitleaks git or gitleaks dir; pin the version and use syntax from matching documentation. The redact option helps prevent printing raw secrets into logs.

### 7.1. Scanning Git History

Scanning the working tree only detects current contents. A secret removed from recent commits may still exist in Git history, old branches, forks, or artifacts.

If a real secret is detected:

1. Revoke or rotate the credential immediately per procedure.
2. Identify resources and actions accessible by that credential.
3. Check audit logs for signs of anomalous use.
4. Purge the secret from source and history per repository procedure.
5. Check artifacts, caches, and logs that may hold copies.
6. Replace with workload identity or an appropriate secret manager.

Simply deleting the secret line from a file does not invalidate the old credential.

### 7.2. Distinguishing Secrets from Public Config

Values such as region, function name, or public API endpoint may be ordinary configuration. Not every random-looking string is a secret. Scanners need precise suppressions with rationale and auditability.

Never place secrets in Docker build arguments or image layers. Use the build tool's secret mount mechanism when secrets are genuinely required during build, and avoid letting secrets become part of the artifact.

## 8. Infrastructure as Code Checks

Infrastructure as Code (IaC) describes cloud resources in reviewable, version-controlled files. For serverless, IaC may define:

- Lambda functions, layers, aliases, and Function URLs.
- API Gateway routes, authorizers, and invoke permissions.
- IAM execution roles and resource policies.
- SQS, SNS, EventBridge, Kinesis, or DynamoDB streams.
- Event source mappings, retries, DLQs, and destinations.
- VPCs, subnets, security groups, endpoints, and NATs.
- CloudWatch log groups, alarms, and retention.
- KMS keys, secret references, and encryption configurations.

IaC scanners inspect configurations before deployment. Common tools:

- **cfn-lint:** validates CloudFormation syntax and schema.
- **CloudFormation Guard:** policy as code for CloudFormation templates.
- **Checkov:** scans Terraform, CloudFormation, Kubernetes, and many IaC types.
- **tfsec:** scans Terraform configurations; functionality is now integrated into the Trivy ecosystem.
- **cdk-nag:** applies security and compliance rules to AWS CDK.
- **OPA/Conftest:** enforces policies on config files or rendered outputs.

Not every scanner understands all macros, intrinsic functions, or deploy-time computed values. Inspect rendered/synthesized templates when supported by tools and add post-deploy integration tests.

## 9. Common IaC Mistakes with Lambda

Configurations needing special checks:

| Area | Risk | What to Check |
|---|---|---|
| Function URL/API Gateway | Unintentionally public endpoint | Auth type, resource policy, authorizer |
| Execution role | Wildcard or admin permissions | Action, Resource, Condition |
| Environment | Secrets embedded directly | Secret references and encryption |
| Logging | Missing retention or logging permissions | Log group, retention, execution role |
| SQS trigger | Infinite message retries or loss after timeout | Visibility timeout, DLQ, redrive |
| Stream trigger | Improper checkpointing and batch retries | Starting position, batch size, bisect/partial failure |
| EventBridge | Overly broad rules or wrong target permissions | Event pattern, target role/permission |
| Concurrency | One function exhausts all concurrency | Reserved/provisioned concurrency and account quota |
| Timeout/memory | Mismatched function timeouts or resources | Timeout, memory, ephemeral storage |
| VPC | Unnecessary egress or missing endpoints | Subnets, routes, security groups, endpoints |
| KMS | Key policy blocks workload or is overly permissive | Key policy and encryption context |

### 9.1. Public Access and Authentication

A Function URL can be configured to require IAM authentication or allow public access depending on settings. API Gateway can use JWT authorizers, Lambda authorizers, or IAM authorization. Pipelines should require explicit authentication configuration rather than accepting public endpoints by default.

If a public endpoint is a product requirement, verify authentication, rate limiting, WAF, or abuse protections. Public is not inherently an error, but it must be a reviewed decision.

### 9.2. Execution Roles

Policies like Action "*" or Resource "*" can grant excessive permissions. Some APIs do not support resource-level permissions and require wildcards; in those cases, constrain with conditions or separate statements, and document the rationale.

Do not mechanically block every wildcard, as this creates false positives. However, wildcards on IAM administration, KMS decrypt, S3 delete, or Secrets Manager access require strict review.

### 9.3. Queues, Retries, and DLQs

For SQS event source mappings, queue visibility timeout must align with function timeout and retry behavior. DLQ/redrive policies need thresholds for receiving failed messages and a reprocessing workflow.

For stream event source mappings, partial batch responses, batch size, and checkpoints affect whether a single bad record retries the entire batch. IaC scans can detect missing settings, while integration tests verify actual behavior.

## 10. Checking Policies as Code

Policy as code lets you express infrastructure rules in an automated, executable form. Examples:

- Production Lambdas must not be public without an exception.
- Execution roles must not grant iam:*.
- Functions must have timeouts within approved bounds.
- Log groups must specify retention.
- Queue triggers must have a redrive policy.
- Storage buckets must enable encryption and block public access.
- Secrets must not be hardcoded in templates.
- Container images must come from approved registries.

Conceptual policy example with OPA/Rego:

~~~rego
package serverless.security

# Rego syntax in this example follows the classic rule form.
deny[msg] {
  input.resource_type == "aws_lambda_function"
  input.environment == "production"
  input.public_access == true
  not input.approved_public_endpoint
  msg := "Production Lambda must not be public without an approved exception"
}
~~~

The input schema here is normalized data supplied by the pipeline, not the default Terraform or CloudFormation Rego schema. Write adapters or use policy packs matching your scanner's output.

Policies should describe concrete conditions and exceptions. Avoid rules based solely on resource names when actual security attributes can be evaluated.

## 11. Checking Container Images and Artifacts

If a Java Lambda is packaged as a container image, scan both application dependencies and OS packages inside the image.

Recommended steps:

- Build images from approved base images.
- Pin base images with versioned tags or digests.
- Scan OS packages and Java dependencies.
- Inspect user, entrypoint, file permissions, and secrets.
- Exclude build tools/caches from runtime images via multi-stage builds.
- Push only gate-approved images to deployment registries.
- Store the image digest in release metadata.

Trivy example:

~~~bash
trivy image --severity HIGH,CRITICAL --exit-code 1 \
  123456789012.dkr.ecr.ap-southeast-1.amazonaws.com/orders:1.4.0
~~~

The illustrative command shows how a pipeline can fail when findings hit a threshold. Pin the Trivy version, update vulnerability databases, and define exception policies. When using ZIP/JAR, scan the filesystem and dependency reports before uploading artifacts.

Not every CVE in an OS package is exploitable in Lambda; however, do not ignore findings without assessing runtime, reachability, and exploitability.

## 12. SBOM: Software Bill of Materials

A Software Bill of Materials (SBOM) inventories components inside an artifact. An SBOM can contain:

- Package names and versions.
- Package URLs (purl).
- Dependency relationships.
- Licenses.
- Supplier or publisher if available.
- Checksums and identification metadata.
- Tool and generation timestamp metadata.

Two common formats are CycloneDX and SPDX. SBOMs enable rapid queries to locate affected artifacts when new CVEs emerge.

Example generating an SBOM with CycloneDX Maven Plugin:

~~~bash
mvn -B org.cyclonedx:cyclonedx-maven-plugin:APPROVED_VERSION:makeAggregateBom
~~~

Pin the plugin version in the build instead of relying on implicit versions. Goal names and options may vary across plugin versions. For Gradle, a corresponding CycloneDX plugin exists; check configuration and dependency scopes included in the SBOM.

The SBOM should reflect the actual released artifact. If builds have different profiles or dependencies are shaded into an uber JAR, confirm the SBOM covers final runtime components.

## 13. Provenance, Reproducible Builds, and Artifact Signing

An SBOM states what an artifact contains; provenance states how and from where it was created.

Provenance can record:

- Source repository and commit.
- Workflow or builder that created the artifact.
- Build parameters and dependency resolution.
- Build timestamp.
- Output artifact digest.
- Workload identity that executed the build.

A reproducible build verifies whether two builds from the same source and dependencies yield equivalent artifacts. To improve reproducibility:

- Pin JDK, Maven/Gradle, and plugins.
- Pin dependency versions and repositories.
- Do not download dependencies from uncontrolled URLs.
- Normalize timestamps if supported by the build tool.
- Store checksums and artifact digests.
- Separate artifact builds from environment deployments.

### 13.1. Signing Artifacts

Artifact signing lets deployment stages verify an artifact came from a trusted source and was not altered after signing. For Lambda ZIPs, AWS Lambda Code Signing can validate packages signed by a trusted signing profile configured on the function. For container images, use appropriate supply-chain image signing/attestation mechanisms and deploy-time verification policies.

Signing an artifact does not prove code is vulnerability-free. It confirms origin and integrity per configured keys/policies. SAST, SCA, IaC scans, and tests are still required.

## 14. Designing Quality Gates

Quality gates are conditions deciding whether the pipeline proceeds or stops. Gates must be clear and consistent.

Example:

| Finding | Recommended Action |
|---|---|
| Real secret detected | Block immediately, revoke credential |
| Critical vulnerability exploitable in runtime | Block release |
| High vulnerability in runtime dependency | Block or require approved exception |
| IaC creates public access outside policy | Block |
| Unnecessary admin IAM permissions | Block and require review |
| Medium finding | Create issue, set risk-based SLA deadline |
| Low/informational | Record and track |
| Unknown license | Route for review before distribution |

Do not apply rigid thresholds based purely on CVSS without considering environment context. A public function accepting untrusted payloads has a different risk profile than an internal function with no direct access path. Yet never use "unreachable" as an excuse to ignore findings without evidence.

### 14.1. Baselines and New Findings

Older repositories may already have numerous findings. Blocking everything immediately can halt all deployments even when new changes add no risk.

Options include:

- Establishing an initial baseline with owners.
- Blocking new findings above thresholds.
- Setting remediation deadlines for existing findings.
- Preventing arbitrary baseline growth.
- Reporting trends to steadily reduce security debt.

Baselines are not a place to hide vulnerabilities. Every suppression must have a rationale, accountable owner, and expiration date.

### 14.2. Managing Exceptions

An exception requires:

- Finding ID and affected resource.
- Rationale for accepting the risk.
- Mitigating controls.
- Approving owner.
- Artifact/environment scope.
- Expiration date or re-evaluation condition.

Never allow "ignore all" or disabling a scanner in the pipeline simply because one rule causes a false positive. Suppress the exact rule on the exact resource.

## 15. Sample Pipeline for Java Lambda

A pipeline can be divided into stages:

1. Check out source and verify commit.
2. Set up pinned JDK and build tools.
3. Compile, unit test, and check code quality.
4. Run SAST and secret scans.
5. Run SCA and license scans.
6. Validate/synthesize IaC.
7. Run IaC scanning and policy-as-code.
8. Build ZIP/JAR or container image.
9. Generate SBOM and scan the artifact.
10. Sign/attest the artifact.
11. Deploy to a test environment.
12. Run integration tests, smoke tests, and permission checks.
13. Approve and promote the same artifact to production.

~~~mermaid
flowchart TD
    A["Commit / Pull request"] --> B["Compile + unit tests"]
    B --> C["SAST + secret scan"]
    B --> D["SCA + license"]
    A --> E["IaC validate + scan"]
    C --> F{"Security gates"}
    D --> F
    E --> F
    F --> G["Build immutable artifact"]
    G --> H["SBOM + image/package scan"]
    H --> I["Sign and attest"]
    I --> J["Deploy test environment"]
    J --> K["Integration / permission / smoke tests"]
    K --> L["Approve and promote"]
~~~

Do not rebuild a separate artifact for production when the exact tested artifact can be promoted. If each environment produces a different artifact, record digests and prove source/dependencies remain equivalent.

### 15.1. Skeleton GitHub Actions Workflow Example

~~~yaml
name: serverless-ci

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        # Replace the major tag with an approved full commit SHA in production.
        uses: actions/checkout@v4

      - name: Set up Java
        # Pin this action to a reviewed full commit SHA in production.
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "17"
          cache: maven

      - name: Compile and test
        run: mvn -B clean verify

      - name: Dependency tree
        run: mvn -B dependency:tree

      - name: Secret scan
        run: gitleaks detect --source . --redact

      - name: IaC validation
        run: cfn-lint infrastructure/template.yaml

      - name: IaC security scan
        run: checkov -f infrastructure/template.yaml
~~~

This is an illustrative skeleton. Real workflows must pin actions by full commit SHA, pin tool versions, install scanners from trusted sources, and archive reports. Never grant id-token: write, deploy permissions, or production secrets to jobs checking pull requests from forks.

The cfn-lint and checkov commands assume the repository contains a CloudFormation template at the specified path. If using SAM, CDK, or Terraform, the pipeline must validate/synthesize/plan before scanning the corresponding IaC output.

## 16. Pipeline Permissions and OIDC Federation

CI runners need permissions to read source, download dependencies, store artifacts, and possibly deploy. Do not store long-lived access keys in CI secrets if the platform supports OIDC federation.

A secure flow:

- Source verification jobs only have repository read permissions.
- Build jobs only have write access to the artifact store.
- Deploy jobs obtain a short-lived OIDC token and assume a role scoped solely to the designated environment.
- Production deployments require approvals or environment protection.
- Deploy roles restrict functions, stacks, and roles passable via iam:PassRole.

Do not grant production deploy permissions to arbitrary pull requests. Jobs running forked code must never receive secrets or sensitive cloud permissions.

## 17. Testing After Deploying to an Ephemeral Environment

Static scans cannot verify all runtime configurations. An ephemeral test environment validates actual behavior:

- The function initializes cleanly with the built runtime and dependencies.
- HTTP triggers enforce proper authentication.
- Queue event source mappings receive and acknowledge messages properly.
- Retries and DLQs work when the handler fails.
- The IAM role accesses only permitted resources.
- Secrets are retrieved from the secret manager and never appear in logs.
- Timeouts, memory, concurrency, and networking behave properly.
- Traces/logs/metrics are emitted as configured.
- The function does not accidentally expose a public endpoint.

Ephemeral environments must be provisioned and torn down in a controlled manner. Never share production data or production secrets without approval. Use test data and separate accounts/projects where appropriate.

### 17.1. Testing Allowed and Denied Permissions

An integration test should verify both positive and negative cases:

- The function can read objects under the required prefix.
- The function is denied when reading another bucket.
- The function can publish to the designated topic/queue.
- The function is denied when calling IAM administration APIs.
- A caller without tenant A permissions cannot access tenant B data.

Testing only allowed operations does not prove least privilege. Confirm that out-of-scope permissions are genuinely denied.

## 18. Monitoring Findings Post-Release

Security does not end at deploy time. New CVEs may be disclosed for dependencies months later; base images or runtimes receive patches; infrastructure configurations can change.

Run periodically:

- Scheduled dependency scans, even without new commits.
- Container image scans upon new advisories.
- IaC drift detection or periodic cloud config audits.
- Secret scanning on pull requests and history per policy.
- SBOM inventory queries to locate affected artifacts.
- Tracking runtime deprecations and platform patches.

If a new CVE emerges, trace back through SBOMs to identify which functions/versions include that dependency. After updating, build and test a new artifact, then release through the standard pipeline.

Avoid directly modifying production resources outside IaC whenever possible. If emergency action is required, update the source of truth and record drift so future deployments do not overwrite or recreate broken settings.

## 19. Common Mistakes

**Running only unit tests:** Misses dependency CVEs or IAM wildcards. Add SCA and IaC scans.

**Scanning only direct dependencies:** Misses transitive libraries. Scan the resolved dependency graph and final artifact.

**Not pinning scanners/plugins:** Results fluctuate with uncontrolled tool versions. Pin versions and update on schedule.

**Ignoring secrets removed from files:** Credentials may remain in Git history or artifacts. Rotate/revoke first, then clean up copies.

**Trusting IaC scanners alone:** Macros or runtime-computed values may go unanalyzed. Combine policies, template rendering, and integration tests.

**Blocking solely by raw CVSS:** Generates excessive false positives and undermines pipeline effectiveness. Evaluate reachability, exposure, and context.

**Ignoring scanner errors:** Pipelines may silently skip checks. Distinguish scanner unavailability from zero findings; if policy mandates scanning, scanner failures must fail the gate.

**Using production permissions in pull requests:** Untrusted code can steal secrets. Separate jobs and permissions by environment.

**Rebuilding artifacts during promotion:** Production artifacts may diverge from tested artifacts. Promote the exact verified digest.

**Having no SBOM:** Hard to quickly find affected functions when a new CVE drops. Store SBOMs linked to each artifact/version.

**Scanning images without scanning IaC:** Clean images can still run with overly broad roles or public endpoints. Check both packages and infrastructure configs.

**Not testing denied permissions:** Functions may accidentally inherit excess privileges. Add negative authorization tests.

## 20. Serverless Java Pipeline Security Checklist

- [ ] JDK, Maven/Gradle wrappers, plugins, and actions are version-pinned.
- [ ] Compilation and unit tests run on pull requests.
- [ ] Code quality checks and SAST are enabled.
- [ ] Direct and transitive dependencies are scanned with SCA.
- [ ] Dependency licenses are checked against policy.
- [ ] Secret scanning covers source and history as required.
- [ ] IaC is validated and scanned before deployment.
- [ ] IAM roles and resource policies are checked for least privilege.
- [ ] Function URL/API Gateway authentication is reviewed.
- [ ] Queue retries, visibility timeouts, DLQs, and event source mappings are verified.
- [ ] Timeouts, memory, concurrency, VPC, and logging have clear policies.
- [ ] Container images and deployment packages are scanned after build.
- [ ] SBOM is generated and stored alongside the artifact.
- [ ] Artifacts have digests, provenance, and appropriate signing/verification.
- [ ] Quality gates have thresholds, baselines, and exceptions with owners/expirations.
- [ ] Pipeline jobs have least-privilege permissions and use OIDC instead of long-lived keys where possible.
- [ ] Pull requests from forks receive no secrets or production deploy permissions.
- [ ] Ephemeral environments and integration/negative permission tests exist.
- [ ] Tested artifacts are promoted intact to production.
- [ ] Scheduled rescans and workflows for handling new CVEs are in place.

## Conclusion

Serverless pipelines must inspect Java source, dependencies, and infrastructure concurrently. Code quality and SAST find program flaws; SCA and license scans govern libraries; secret scanning prevents credentials from entering repositories; IaC scanning and policy as code uncover dangerous cloud configurations. After building, SBOMs, artifact/image scanning, provenance, and signing pinpoint the exact contents and origin of a release.

For Java Lambda, checks must pay extra attention to execution roles, public endpoints, event source mappings, retries/DLQs, concurrency, timeouts, secret references, and networking. Quality gates need clear criteria, time-bound exceptions, and minimal CI permissions. Combine static scans with integration tests in ephemeral environments, negative permission tests, and scheduled rescans to catch risks both before and after release.
