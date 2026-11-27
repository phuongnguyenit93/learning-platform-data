# Applying Policy as Code for Serverless Infrastructure

Serverless infrastructure is continuously created and modified through Terraform, CloudFormation, deployment pipelines, consoles, or APIs. If every team independently decides how to configure functions, APIs, queues, roles, and storage, misconfigurations in security, networking, logging, retention, or cost can easily emerge. A function might accidentally expose public ingress, use an overly broad execution role, lack a dead-letter destination, or retain logs too briefly to investigate an incident.

**Policy as code** turns governance rules into a form that can be read, reviewed, tested, and automatically enforced. Instead of merely stating in documentation that "functions must have a timeout" or "endpoints must not be public without authentication," the organization defines policies so pipelines or control systems can evaluate configurations before deployment and detect drift after launch.

In Java serverless, policies must cover the entire workload path: function/runtime, API triggers, event sources, execution identity, network, secrets, databases, storage, observability, and deployment artifacts. A well-designed policy has an owner, clear scope, business rationale, test suite, and an exception process. This lesson covers the policy as code lifecycle, guardrail layers, OPA/Rego and Terraform examples, CI/CD integration, runtime drift controls, and storing compliance evidence.

## 1. What Is Policy as Code?

Policy as code is a way of expressing technical or governance rules in a machine-readable structure that can be evaluated automatically. Policies can be written using Rego/OPA, Sentinel, Cedar, JSON/YAML schemas, cloud provider rule engines, or IaC policy tools.

A policy typically includes:

- **Subject:** who or what the rule applies to, such as a Lambda function, Cloud Run service, or service account.
- **Resource:** the resource being created or modified.
- **Condition:** the condition that must hold, such as private ingress or timeout within limits.
- **Effect:** allow, deny, warn, or require approval.
- **Scope:** environment, account/project, region, workload class, or data classification.
- **Owner and version:** the accountable team and policy version.
- **Evidence:** data proving that the policy was evaluated and what the result was.

Example rules:

~~~text
Every production function must:
- use a workload-specific execution identity;
- have timeout and memory within approved bounds;
- not contain plaintext secrets in environment variables;
- emit structured logs with retention configured;
- have appropriate trigger authentication;
- have a retry/DLQ strategy for event processing;
- be granted only required network egress and IAM permissions.
~~~

The key point is that policies must be applied consistently across multiple teams and pipelines. A manual checklist can help, but it struggles to catch misconfigurations as the number of functions and deployments scales.

## 2. What Problems Does Policy as Code Solve?

Serverless reduces server management overhead, but it does not eliminate governance responsibilities. Configurations can change independently and be deployed through multiple tools.

Policy as code helps to:

- Prevent risky configurations before deployment.
- Standardize baselines across development, staging, and production.
- Verify IAM, ingress, networking, encryption, and logging.
- Embed compliance requirements into pull requests and pipelines.
- Detect drift between IaC and runtime configurations.
- Retain check results as audit evidence.
- Grant time-bound, approved exceptions.
- Reduce repetitive manual reviews of common rules.

Policy as code does not by itself prove an application complies with all legal regulations. It checks technical conditions that have been codified into policies. The organization must still define requirements, scope, sensitive data handling, accountability, and how to prove controls operate effectively.

## 3. Policy Layers in Serverless

Policies should be organized by layer to make assigning owners and determining enforcement points straightforward.

| Layer | Control Examples | Evaluation Timing |
|---|---|---|
| Organization/account | Block disallowed regions, restrict public resources | Organization guardrail / deployment |
| Infrastructure as Code | Timeout, memory, ingress, encryption, tags | Pull request / plan |
| Identity and access | Least privilege, trust policies, service accounts | Plan, IAM analysis, and runtime |
| Network | Ingress, egress, private connectivity | Plan and runtime |
| API/trigger | Authentication, authorization, rate limits | API configuration and integration tests |
| Event processing | Retries, DLQ, batch size, idempotency strategy | Plan and consumer validation |
| Data protection | Encryption, retention, classification, backups | Provisioning and runtime |
| Observability | Logs, metrics, traces, audits, and retention | Deployment and runtime |
| Artifact/supply chain | Image digest, signatures, dependency scans | Build and release |
| Cost/capacity | Max instances, concurrency, budget tags | Plan, deployment, and FinOps review |

Avoid dumping every rule into one large uncategorized file. Grouping policies by domain helps reviewers understand why a check denied a change and find the right owner to fix it.

## 4. Preventive, Detective, and Corrective Controls

Policies can be enforced at multiple stages:

- **Preventive:** blocks invalid configurations before resources are created or updated.
- **Detective:** scans running resources to identify drift or violations.
- **Corrective:** opens tickets, requires remediation, or auto-remediates when that action is safe and pre-approved.

~~~mermaid
flowchart TD
    Change[Code or infrastructure change]
    PR[Pull request policy checks]
    Plan[Evaluate IaC plan]
    Deploy[Deploy approved change]
    Runtime[Runtime configuration scan]
    Alert[Violation finding / alert]
    Fix[Remediate or approved exception]

    Change --> PR --> Plan
    Plan -->|Pass| Deploy
    Plan -->|Deny| Change
    Deploy --> Runtime
    Runtime -->|Compliant| Monitor[Continuous monitoring]
    Runtime -->|Violation| Alert --> Fix
    Fix --> Runtime
~~~

A policy that runs only in CI can miss direct changes made in the cloud console. A scanner that runs only daily can detect violations too late. Combine preventive and detective controls to cover both managed changes and out-of-band pipeline drift.

Corrective automation requires caution. For instance, automatically deleting a public endpoint or revoking a role can disrupt production traffic. For high-impact actions, creating a finding and requiring the owner to remediate within an SLA is usually safer.

## 5. Building Policies by Risk and Data Classification

Not every function requires the exact same configuration. A function handling public data has different requirements from one processing payments, identity, or personal data.

Define workload profiles:

| Profile | Example | Core Policy Focus |
|---|---|---|
| Internal utility | Internal data cleanup cron | Private ingress, workload identity, audit |
| Public API | Customer-facing HTTP endpoint | Authentication, authorization, rate limiting, WAF/API protection |
| Event processor | Queue consumer | Retries, DLQ, idempotency, encryption, least privilege |
| Sensitive workload | Payment or personal data | Data classification, private networking, key policies, audit, retention |
| Batch/reporting | Large data exports | Timeout, memory, concurrency, storage encryption, cost limits |

Use standardized labels or metadata such as `environment`, `service`, `owner`, `data_classification`, `criticality`, and `cost_center`. Policies can rely on these attributes to apply the right level of control.

Do not allow callers to self-assign classifications to lower control strictness. Classifications must come from a trusted registry or pipeline with separate change permissions.

## 6. Writing Testable Policies

A well-written policy should include:

1. A stable name and ID.
2. A short, clear description.
3. The control objective and mitigated risk.
4. Resource scope.
5. Allow/deny/warn conditions.
6. Severity level.
7. Remediation guidance.
8. Owner.
9. Version and effective date.
10. Positive, negative, and boundary test suites.

Example policy metadata:

~~~yaml
id: SVL-SEC-004
name: production-function-requires-authentication
version: 2
severity: high
scope:
  environments:
    - production
resources:
  - serverless.http_function
control:
  description: Public HTTP function must require approved authentication.
  rationale: Prevent unauthenticated access to protected application operations.
remediation: Configure API authentication or restrict ingress to an approved identity-aware gateway.
owner: platform-security
exception:
  allowed: true
  requires: security-approval
  max_days: 30
~~~

This metadata illustrates an internal contract. Organizations must agree on a schema and validator; do not assume all policy engines interpret these fields identically.

### Policies Must Include Remediation Messages

A "policy failed" message does not help developers fix the issue. Findings should state:

- Which resource violated the policy.
- Which field is invalid.
- Current value and expected condition.
- Why the policy exists.
- How to fix it.
- Link to documentation or owner.

Example:

~~~text
DENY SVL-IAM-002
Resource: aws_lambda_function.payment-worker
Field: role
Finding: execution role grants wildcard administrative actions.
Expected: workload-specific role with scoped actions and resources.
Remediation: replace broad policy with permissions required by payment-worker.
~~~

Never include secrets, tokens, or sensitive data in findings or CI logs.

## 7. OPA and Rego in Pipelines

Open Policy Agent (OPA) is a policy engine that evaluates JSON input against Rego policies. With Infrastructure as Code, a pipeline can convert a Terraform plan or rendered configuration to JSON and have OPA return allow/deny results.

Example Rego policy using Rego v1 syntax:

~~~rego
package serverless.guardrails

import rego.v1

deny contains message if {
    input.resource_type == "aws_lambda_function"
    input.environment == "production"
    input.config.tracing_mode != "Active"

    message := sprintf(
        "%s must enable active tracing in production",
        [input.name],
    )
}

deny contains message if {
    input.resource_type == "aws_lambda_function"
    input.environment == "production"
    input.config.timeout < 3

    message := sprintf(
        "%s timeout must be at least 3 seconds",
        [input.name],
    )
}

deny contains message if {
    input.resource_type == "aws_lambda_function"
    input.config.environment_variables[_] == "PLAINTEXT_SECRET"

    message := sprintf(
        "%s appears to contain a forbidden plaintext secret marker",
        [input.name],
    )
}
~~~

The final example only illustrates a test marker, not how to detect production secrets. Secret detection requires secret scanners and rules tailored to appropriate data sources; policies should not try to infer secrets solely from a single string value.

In Rego, `deny` is a set of findings. The pipeline fails if this set is non-empty. Depending on the OPA version and conventions, you may use `deny contains ... if { ... }` or another package/query contract; pin the version and test syntax in the repository.

### Inputs Must Be Standardized

Do not let each pipeline send a different JSON shape. Standardize inputs with fields for:

- Resource type and resource address.
- Environment/account/project/region.
- Module or workload metadata.
- Configuration to evaluate.
- Identity and policy attachments.
- Source revision and plan digest.

If a policy receives missing fields, handle it by failing closed for critical controls or returning a clear input error. Never treat a missing field as compliant by default.

## 8. OPA Example: Blocking Unauthenticated Public Functions

A simple policy:

~~~rego
package serverless.network

import rego.v1

deny contains message if {
    input.kind == "http_function"
    input.environment == "production"
    input.ingress == "public"
    input.authentication != "required"

    message := sprintf(
        "production HTTP function %s is public without required authentication",
        [input.name],
    )
}
~~~

Policy tests:

~~~rego
package serverless.network_test

import rego.v1
import data.serverless.network

test_public_production_function_without_auth_is_denied if {
    result := network.deny with input as {
        "kind": "http_function",
        "environment": "production",
        "ingress": "public",
        "authentication": "none",
        "name": "orders-api",
    }

    count(result) == 1
}

test_authenticated_public_function_is_allowed if {
    result := network.deny with input as {
        "kind": "http_function",
        "environment": "production",
        "ingress": "public",
        "authentication": "required",
        "name": "orders-api",
    }

    count(result) == 0
}
~~~

Tests should also cover missing authentication fields, invalid values, and non-production environments. If a public endpoint is allowed for product reasons, the policy should require an API gateway or equivalent control rather than bypassing checks entirely.

## 9. Terraform Plans and Policy Evaluation

A Terraform plan can be exported to JSON so a policy engine can evaluate it before apply:

~~~bash
terraform init
terraform validate
terraform plan -out=tfplan
terraform show -json tfplan > tfplan.json
opa eval --data policies/ --input tfplan.json "data.serverless.guardrails.deny"
~~~

These commands are illustrative. In a real pipeline, you must:

- Pin Terraform and OPA versions.
- Check the exit code and query output.
- Handle resource change actions such as create, update, and delete.
- Avoid checking only the final configuration if policies need to know whether a resource is being deleted or replaced.
- Protect plan artifacts and prevent secrets from leaking into JSON or logs.
- Use an adapter to map Terraform JSON to a stable input contract if policies do not directly understand the plan format.
- Store the digests of the plan and the policy bundle used for evaluation.

`opa eval` returns query results; the pipeline must interpret those results and actively fail when denials occur. Do not assume simply running the command automatically blocks Terraform.

### Checking Changed Resources

A policy for functions may need to check:

- Supported runtime and architecture.
- Timeout, memory, and ephemeral storage within limits.
- Environment variables free of secrets.
- Execution roles without wildcard admin permissions.
- Tracing/logging enabled.
- Appropriate ingress and VPC/egress settings.
- Reserved/max concurrency within quotas.
- DLQ or failure destination configured when required.

Evaluate only changed resources if that is the pipeline's intent. For a full-system baseline, add inventory/runtime scans to inspect older resources that do not appear in a plan.

## 10. Policies for IAM and Workload Identity

Least privilege is one of the most important controls for serverless. Each function should have an execution identity scoped to the workload or a functional group sharing the same trust boundary.

IAM policies can verify:

- Overly broad default roles are not used.
- Wildcard actions/resources are not granted without an approved justification.
- Trust policies permit only appropriate service principals and sources.
- Functions cannot assume unrelated roles.
- Secret read permissions are restricted to needed secrets.
- Object write permissions are restricted to specific buckets/prefixes.
- Publish permissions are restricted to required queues/topics.
- Decrypt permissions are restricted to specific keys and encryption contexts where supported by the provider.
- Permissions to modify IAM or create credentials are prohibited except for dedicated administrative workloads.

You cannot detect all overly broad permissions simply by searching for `*`. Some actions require wildcard resources per provider semantics; policies must understand the action/resource model and maintain an explicit exception allowlist.

### Terraform Example: Least-Privilege Role

~~~hcl
data "aws_iam_policy_document" "payment_worker" {
  statement {
    sid    = "ReadPaymentQueue"
    effect = "Allow"

    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes"
    ]

    resources = [
      aws_sqs_queue.payment_events.arn
    ]
  }

  statement {
    sid    = "ReadPaymentSecret"
    effect = "Allow"

    actions = [
      "secretsmanager:GetSecretValue"
    ]

    resources = [
      aws_secretsmanager_secret.payment_api.arn
    ]
  }
}
~~~

This is an example of minimal permissions for a specific consumer. Actual resources and actions must match the API/SDK, encryption key policies, event source mappings, and how the runtime fetches secrets. Do not copy this policy blindly to every function.

## 11. Policies for Network and Ingress

HTTP functions can be called directly from the Internet, via an API gateway, an internal load balancer, or service-to-service identity. Policies must distinguish public network reachability from authentication.

A public endpoint is not inherently insecure if it has proper authentication, authorization, rate limiting, and protections. Conversely, a private endpoint still requires service identity authentication and authorization.

Common guardrails:

- Production endpoints are public only with an approved use case.
- Public endpoints must require authentication or sit behind a gateway with identity-aware policies.
- Do not open broad ingress for internal-only workloads.
- Egress to databases/internal services must use approved routes and security rules.
- Block metadata/link-local addresses and unnecessary internal ranges for outbound URL fetches.
- Do not allow unrestricted Internet egress if the workload does not need it.
- Attach policies to appropriate VPC connectors, firewalls, security groups, or egress gateways.
- Separate network policies by environment and data classification.

Do not confuse ingress policies with application-layer authorization. A gateway can authenticate the caller, but the function must still enforce tenant/resource permissions per its contract.

## 12. Policies for API Triggers and Event Sources

### HTTP/API

Policies may require:

- An approved authentication method.
- Explicit authorization and scopes/roles.
- Rate limits, quotas, or WAF policies aligned with risk level.
- CORS restricted to necessary origins if browser access is supported.
- Reasonable request sizes and timeouts.
- TLS and custom domain configurations matching the baseline.
- No unintended public exposure of debug endpoints or admin routes.

CORS does not replace authentication and does not block server-to-server requests.

### Queues and Events

Policies may require:

- Encryption at rest and in transit per provider capabilities.
- Resource policies restricting producers/consumers.
- Declared retry or redelivery behavior.
- DLQ/failure destinations for flows requiring quarantine.
- Visibility/ack deadlines aligned with processing timeouts.
- Batch sizes and concurrency within downstream capacity.
- Defined event schemas/versions and idempotency contracts.
- Retention and replay windows matching business requirements.
- Avoiding secrets or sensitive data in event payloads unless necessary.

Do not mandate a single arbitrary DLQ threshold for every queue. Policies should be based on criticality and recovery methods; if an event source uses another failure destination, declare the equivalent control.

## 13. Policies for Data Protection and Secrets

Serverless workloads often use environment variables for configuration, but secrets must be managed by a secret manager or the platform's credential provider mechanism.

Guardrails can check that:

- No secret literals exist in IaC, source code, or deployment artifacts.
- Functions only read secrets they are authorized to access.
- Secret references use approved versioning/rotation policies.
- Storage/databases/queues enable encryption according to data classification.
- KMS key policies do not grant broad access.
- Backups and retention meet requirements.
- Logs do not contain tokens, credentials, or sensitive payloads.
- Public object access is blocked except for buckets explicitly designated as public.
- Data residency/regions are controlled according to classification.

Secret scanners and IaC policies complement each other. Secret scanners search for strings that look like credentials; policies verify that resources reference a secret manager and identities only read the right secrets.

## 14. Policies for Runtime, Timeout, and Concurrency

Runtime settings impact security, reliability, and cost.

A baseline can check:

| Attribute | Policy Example |
|---|---|
| Runtime | Only use supported Java LTS/runtimes |
| Timeout | Does not exceed limits for the workload class |
| Memory/CPU | Within benchmarked and approved ranges |
| Concurrency | Does not exceed downstream capacity and quotas |
| Min/max instances | Matches SLOs and budgets |
| Tracing | Enabled per criticality and privacy policy |
| Logging | Structured logs, retention, and redaction |
| Ephemeral storage | Bounded by need and data handling rules |
| Architecture | Uses tested and supported architectures |

Do not set the same timeout for every function. HTTP requests, short event handlers, and batch exports have different profiles. Use workload classes so policies validate values against the work type.

### Limiting Concurrency to Protect Dependencies

If every function invocation opens a database connection, uncontrolled scale-out can exhaust the database. Policies may require:

- Declared max/reserved concurrency.
- Total workload connection budget within quotas.
- Bounded consumer concurrency.
- Retries and batch sizes that do not cause amplification.
- Max instances matched to downstream capacity.

Policies should evaluate the relationship between instance counts and connection pools, rather than checking each value in isolation.

## 15. Policies for Artifacts and the Software Supply Chain

Java functions are usually packaged as JARs or container images. Policies should verify artifact provenance before deployment.

Controls:

- Built from a trusted pipeline.
- Dependencies scanned for CVEs and licenses per policy.
- Container images use immutable digests rather than mutable tags.
- Artifacts include provenance/attestation where supported.
- Images/JARs are signed and verified per procedure.
- No secret files or debug configurations included.
- Base images and Java runtimes are still supported.
- Only artifacts that passed required tests and approvals are deployed.
- Release records link commit, build, artifact digest, and deployment.

Do not rely solely on tags like `latest` or version strings in filenames. Digests identify exact artifact contents and allow the pipeline to prove that what was scanned is exactly what gets deployed.

## 16. Integrating Policies into CI/CD

A pipeline can run policies at multiple points:

1. **Source stage:** secret scans, dependency/license scans, static analysis.
2. **Pull request:** validate metadata and IaC policies.
3. **Plan stage:** evaluate resources about to be created/modified/deleted.
4. **Build stage:** check artifacts, image digests, and provenance.
5. **Pre-deploy:** verify approvals, exceptions, and policy bundle versions.
6. **Post-deploy:** verify actual runtime configurations and run smoke tests.
7. **Continuous scan:** detect drift and newly emerging violations.

~~~mermaid
flowchart TD
    Commit[Commit / pull request]
    Source[Secret and dependency scans]
    IaC[Terraform validate and plan]
    Policy[OPA / IaC policy checks]
    Build[Build and sign Java artifact]
    Approval[Approval and exception check]
    Deploy[Deploy serverless resources]
    Verify[Runtime config and smoke checks]
    Monitor[Continuous compliance scan]

    Commit --> Source --> IaC --> Policy
    Policy -->|Deny| Feedback[Return findings to developer]
    Policy -->|Pass| Build --> Approval
    Approval -->|Approved| Deploy --> Verify --> Monitor
    Approval -->|Missing approval| Feedback
~~~

### Fail Fast with Actionable Output

Severe policy violations should block the pipeline. Warnings may allow deployment while creating a finding or requiring review. The pipeline should emit machine-readable outputs for dashboard aggregation and auditing.

Never let a policy engine network failure or bundle download error default to allow in production. Define fail-closed versus fail-open behavior based on control severity; for security-critical guardrails, fail-closed is generally appropriate. Signed policy bundles can be cached to avoid network dependencies on every evaluation.

## 17. Policy Bundles, Versioning, and Rollout

Policies are software too and can contain bugs. A faulty policy change can block numerous releases or permit dangerous configurations.

Manage policies as artifacts:

- Assign explicit versions.
- Review via pull requests.
- Maintain positive, negative, and boundary tests.
- Pin versions or policy bundle digests in pipelines.
- Record policy versions in deployment evidence.
- Distinguish policies in draft, warn-only, and enforce states.
- Have a policy bundle rollback plan.
- Announce changes affecting multiple teams in advance.

### Phased Rollout

1. **Observe:** run policies against existing resources, logging findings only.
2. **Warn:** pipelines display warnings and remediation steps.
3. **Enforce on new resources:** block non-compliant new resources.
4. **Enforce on updates:** block updates that increase risk.
5. **Remediate legacy:** schedule remediation of older resources per SLA.
6. **Continuous enforcement:** scan for drift and re-evaluate periodically.

Do not turn on full deny enforcement for a new policy before knowing the volume of legacy violations and the remediation path. However, do not leave critical controls in warn-only mode indefinitely.

## 18. Runtime Drift and Continuous Compliance

IaC only describes desired state. Actual resources can be altered through the console, APIs, or another pipeline. This is configuration drift.

Examples:

- A developer opens public ingress to debug and forgets to close it.
- Wildcard permissions are manually added to a role.
- Log retention is shortened.
- A DLQ is deleted or an event source mapping's retry policy is altered.
- A secret reference is replaced with a plaintext environment variable.
- Max instances are raised beyond budget or database capacity.

How to control it:

- Collect actual configuration inventory by account/project/region.
- Normalize resources into the input schema.
- Run the same policy bundle used in CI.
- Record findings, severity, owner, and detection timestamp.
- Compare against IaC state and deployment records.
- Track remediation SLAs.
- Create tickets or auto-remediate when the action is safe.

Runtime scans should run on a cadence aligned with risk and after major changes. For public resources or sensitive IAM, event-driven detection may be necessary instead of waiting for a daily scan.

## 19. Controlled Policy Exceptions

Not every workload can comply with every rule. An unauthenticated public function might be a tightly scoped public health check endpoint; a batch function might need a longer timeout than the baseline.

Exceptions must include:

- Specific policy ID and resource scope.
- Business justification and accepted risk.
- Accountable owner.
- Approver matching the severity level.
- Compensating controls.
- Start date and expiration date.
- Related ticket or evidence.
- Plan to return to baseline.

Example:

~~~yaml
exception:
  policy_id: SVL-NET-004
  resource: production/health-probe
  reason: Public probe is required by an external monitoring provider.
  compensating_controls:
    - response_contains_no_sensitive_data
    - strict_rate_limit
    - dedicated_health_route
  owner: platform-operations
  approved_by: security-team
  expires_at: 2026-12-15
~~~

This is an internal metadata example. Exceptions must be verified by a validator and tied to the exact resource; disallow wildcard scopes or infinite durations. Upon expiration, pipelines and runtime scans must automatically flag a violation if the resource has not returned to baseline.

### Never Use Exceptions to Bypass Every Policy

A policy cannot be waived if doing so violates laws, contracts, or mandatory organizational requirements. Non-waivable controls must be explicitly categorized, and the engine must reject exceptions for them.

## 20. Audit Evidence and Compliance Reporting

To make a decision reconstructible for audits, retain:

- Source commit and pull request.
- Terraform plan digest or deployment manifest.
- Artifact digest/provenance.
- Policy bundle version/digest.
- Sanitized input resource snapshot.
- Allow/deny/warn outcome and finding IDs.
- Exception and approval records.
- Human or workload identity performing the deployment.
- Timestamp, environment, account/project, and region.
- Post-deploy scan results and remediation status.

Never store secrets or raw sensitive payloads in evidence. Use immutable storage or an audit service aligned with retention and access requirements.

Evidence must link the policy decision to the exact deployed artifact and resource. If a pipeline evaluates plan A but deploys plan B, the evidence fails to prove the live resource was checked.

## 21. Testing Policies

Policies must be tested like application code.

### Positive Tests

- Compliant function with proper auth, timeout, role, and logging.
- Event consumer with retry/DLQ matching its profile.
- Secret referenced through a secret manager.
- Runtime and region in the allowlist.
- Valid, non-expired exception scoped to the right resource.

### Negative Tests

- Unauthenticated public production HTTP function.
- Execution role with unapproved admin permissions.
- Environment variable containing a test secret marker.
- Storage made public outside policy.
- Function missing logging or exceeding timeout limits.
- Event source lacking required failure handling.
- Artifact using a mutable tag or lacking provenance.
- Resource deployed to a disallowed region.
- Expired or overly broad exception.

### Boundary Tests

- Timeout at exact min/max bounds.
- Memory right at the threshold.
- Resource missing optional fields.
- Non-production environment.
- Internal-only function without a public endpoint.
- Policy input containing resources being replaced or deleted.
- Two policies simultaneously producing findings for one resource.
- Old and new policy bundles evaluating the same plan.

OPA can use `opa test` to run Rego unit tests. Beyond unit tests, include integration tests verifying that the pipeline actually fails when a policy denies and passes when compliant.

## 22. Common Policy as Code Implementation Mistakes

- **Policies living only in documentation:** hard to check consistently; move automatable rules into the engine.
- **One blanket policy for all workloads:** ends up too strict or too loose; use workload classes and data classifications.
- **No owner:** findings go unaddressed; assign an accountable team.
- **Unstable input schema:** the same policy gives different results across pipelines; standardize the contract.
- **Missing fields defaulting to allow:** unclear configurations slip through; fail closed on critical controls.
- **Checking only Terraform plans:** misses console drift; add runtime scans.
- **Scanning only at runtime:** detects issues too late after resources are public; use preventive gates.
- **Denials without remediation guidance:** developers do not know what to fix; return specific findings.
- **Unpinned policy versions:** hard to reconstruct past decisions; record bundle digests.
- **Enabling enforcement abruptly:** blocks many legacy workloads; roll out observe/warn/enforce in phases.
- **Non-expiring exceptions:** exceptions become permanent configurations; require owners and expiration dates.
- **Searching only for wildcards in IAM:** creates false positives and false negatives; evaluate action/resource semantics.
- **Treating passing policies as full compliance:** policies only verify codified controls; audits and process reviews are still required.
- **Storing secrets in policy inputs/evidence:** creates a new leak vector; redact and minimize data.
- **Not testing policy engine failures:** pipelines can fail open unexpectedly; define behavior when the engine is unavailable.
- **Not tying results to the actual artifact:** scanning one artifact while deploying another; use digests/provenance.

## 23. Rollout Process for Policy as Code in Java Serverless

You can roll out in this order:

1. Inventory functions, APIs, event sources, identities, data stores, and network dependencies.
2. Classify workloads by environment, criticality, and data classification.
3. Define security, reliability, privacy, and cost baselines for each profile.
4. Author policies with ID, owner, severity, scope, and remediation.
5. Standardize the IaC/runtime input schema.
6. Write positive, negative, and boundary tests.
7. Run policies in observe mode to assess legacy violations.
8. Integrate policies into pull requests and Terraform plans.
9. Block production deployments on critical policy denials.
10. Attach policy bundle digests and results to artifacts/deployments.
11. Scan runtime environments to detect drift.
12. Manage exceptions with approvals, scopes, and expiry dates.
13. Build compliance dashboards and track remediation SLAs.
14. Review policies when runtimes, providers, threat models, or regulations change.
15. Periodically drill policy engine outages and bundle rollback procedures.

## 24. Key Takeaways

Policy as code converts serverless governance requirements into rules that can be reviewed, tested, and enforced automatically. Policies must span IaC, IAM, networking, API triggers, event sources, data protection, runtimes, artifacts, observability, and cost guardrails.

Combine preventive checks in pull requests/CI with detective scans at runtime to catch both new misconfigurations and drift. Use a policy engine like OPA/Rego with a stable input schema, pinned bundle versions, and findings with clear remediation steps. Roll out in phases to handle legacy resources, while managing exceptions with owners, approvals, and expiration dates.

Retain evidence linking policy decisions to the exact plan, artifact, and deployed resource. Passing policies demonstrate that a set of technical controls was evaluated; they do not replace identifying legal obligations, risk assessments, and comprehensive audits. For Java serverless, policy as code helps HTTP, message, and event functions deploy consistently, remain verifiable, and stay safe as the system scales.
