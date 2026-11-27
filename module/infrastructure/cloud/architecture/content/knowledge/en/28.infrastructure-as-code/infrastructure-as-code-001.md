# Infrastructure Declaration and Source Code Structure Design

## 1. What problem does Infrastructure as Code solve?

A cloud system is built from many components: network, subnet, firewall, identity, compute, load balancer, database, storage, queue, monitoring, and policy. If each component is created manually through a console, the configuration is often hard to repeat, hard to review, hard to trace, and prone to diverging across development, staging, and production.

**Infrastructure as Code (IaC)** is the practice of describing infrastructure using files that can be read, reviewed, tested, and executed by tooling. Infrastructure changes go through a workflow similar to software changes: stored in version control, reviewed, tested, planned, deployed, and monitored for drift.

IaC helps:

- Create consistent and reproducible environments.
- Review changes before they affect real resources.
- Reuse configurations through modules and shared conventions.
- Record change history and approvers.
- Automate provisioning, updates, and teardown.
- Support auditing, disaster recovery, and capacity planning.
- Reduce reliance on knowledge held by a single individual.

IaC does not automatically guarantee a correct or secure architecture. A misconfiguration deployed rapidly through automation can expand the blast radius faster than manual operations. Therefore, it must be combined with solid design, policy as code, testing, least-privilege deployment permissions, and operational processes.

In the **CLOUD_ARCHITECTURE** module, IaC serves as the bridge from architectural decisions to network, compute, data, security, and deployment. The design must balance **reliability, security, scalability, cost, and operations** following Well-Architected principles.

Running example: a booking platform has a network boundary, an application cluster, a private database, object storage, a queue, IAM roles, and an observability stack. The dev, staging, and prod environments share the same logical structure but differ in sizing, data, and policies.

## 2. Declarative vs. Imperative

| Approach | Description | Example |
| --- | --- | --- |
| Declarative | Declare the desired state; the tool compares the current state and determines how to reach that state | The network must have 3 subnets, a private database, and encryption enabled |
| Imperative | Describe each step or command to run in order to create/modify state | Run a command to create a VPC, then create subnets, then attach routes |

With declarative IaC, the designer focuses on the end state and the dependency graph. The tool plans the operations to execute. With imperative automation, the author controls the execution order and typically has to manage state, idempotency, and rollback manually.

There is no absolute choice. Declarative fits resource lifecycles supported by providers; imperative is useful for bootstrapping, migrations, or tasks that providers cannot yet model. They can be combined, but clear boundaries are needed so two tools do not manage the same resource.

### 2.1. Idempotency and convergence

An idempotent operation can be re-run without producing unintended side effects once the desired state is reached. With IaC, the goal is that a second apply does not keep making unnecessary changes if the configuration and environment have not changed.

Convergence is the ability to gradually bring the system into the declared state. This depends on the provider, API, and resource. Some attributes can only be updated in place; others force resource replacement; and some services are asynchronous and need time to stabilize.

Do not assume every resource can be updated safely. Always read the plan to identify create, update, replace, and destroy actions before deploying.

## 3. Separating architecture into source code layers

A good IaC repository helps readers quickly answer: which environments are being managed; where infrastructure components live; which values are environment-specific configurations; which modules are shared; where state resides; which pipeline deploys the code; and how verification/recovery works.

A reference structure:

~~~text
cloud-platform/
  README.md
  docs/
    architecture.md
    decisions/
  modules/
    network/
    identity/
    compute-service/
    database/
    object-storage/
    observability/
  environments/
    dev/
      main.tf
      variables.tf
      outputs.tf
      backend.hcl
      dev.tfvars
    staging/
      main.tf
      variables.tf
      outputs.tf
      backend.hcl
      staging.tfvars
    prod/
      main.tf
      variables.tf
      outputs.tf
      backend.hcl
      prod.tfvars
  policies/
  tests/
  scripts/
~~~

This is an illustrative Terraform-style layout. Pulumi, CloudFormation, Bicep, CDK, or other tools may have different file layouts and lifecycles. The goal is to maintain clear boundaries between reusable modules, environment composition, policies, tests, and documentation.

### 3.1. Modules and environment composition

- **Module:** encapsulates a piece of infrastructure with a stable input/output interface, such as a private database or compute service.
- **Environment composition/root stack:** wires modules together to instantiate a specific environment.
- **Policy:** validates or restricts what modules/environments are allowed to create.
- **Test:** verifies the expected contract and behavior.
- **Documentation:** explains purpose, assumptions, and operational procedures.

A module should not make all organizational decisions on its own. A network module may accept a list of CIDRs, while an organization policy defines allowed regions or shared mandatory rules.

## 4. Designing modules along architectural boundaries

A good module encapsulates a capability with high cohesion and low coupling. You should neither build a single monolithic module containing the entire system nor turn every tiny resource into its own module.

A database module can manage the database instance/cluster, subnet group, encryption settings, backup/retention, parameter group, required security rules, and monitoring outputs. A database module should not silently create business users, grant admin permissions to applications, or provision resources across multiple environments outside its scope.

### 4.1. Module interface

| Component | Role | Example |
| --- | --- | --- |
| Inputs | Values supplied by the caller or allowed to be customized | name, subnet IDs, engine version, size |
| Defaults | Safe, common, and intentional default values | encryption enabled, deletion protection |
| Validation | Input checks before creating resources | valid CIDR, retention within allowed range |
| Outputs | Information needed by other modules/callers | endpoint, resource ID, security group ID |
| Dependencies | Relationships to other capabilities | private subnets, KMS key, security boundary |
| Version | Contract and behavior of the module | semantic version or source revision |
| Documentation | Usage, limitations, examples, and migration notes | README/module docs |

Fewer, meaningful inputs make a module easier to use. A module with hundreds of configurable variables is often hard to control. Conversely, an overly rigid module pushes teams to fork or bypass it. Expose only the options that have a clear architectural reason.

### 4.2. Encapsulation and abstraction

A module hides implementation details, but it should not hide critical impacts. If a configuration change can trigger database replacement or storage deletion, the module must make that clear and the documentation must warn against it. Do not build abstractions that prevent users from seeing network exposure, encryption, backup, or cost tier.

### 4.3. Module versioning

Changing inputs, outputs, or semantics can break environments currently using the module. Modules should be versioned, breaking changes documented, backward compatibility maintained where possible, migration guides provided, representative consumers tested, and version upgrades rolled out via pull requests, plans, and controlled deployments.

Do not reference a continuously changing main branch for production without explicit pinning and verification processes.

## 5. Consistent resource naming and organization

Resource names aid search, auditing, cost allocation, and operations. A naming convention may follow:

~~~text
<organization>-<environment>-<region>-<domain>-<resource>
~~~

Examples:

~~~text
acme-prod-sea1-booking-db
acme-stg-sea1-platform-private-subnet-a
acme-dev-sea1-booking-api
~~~

Actual names must comply with each service's length limits and allowed character set. Never embed secrets, emails, usernames, or sensitive data into resource names.

### 5.1. Minimum tags/labels

| Tag | Purpose |
| --- | --- |
| application | System that owns the resource |
| environment | dev/staging/prod |
| owner | Responsible team |
| cost-center | Cost allocation |
| data-classification | Data classification |
| managed-by | Responsible IaC/pipeline |
| lifecycle | persistent/temporary/expiry |

Tags do not replace IAM or network policies. Never assume a resource tagged as production is automatically secure; policies must inspect actual configurations and boundaries.

## 6. Managing environment-specific configuration

Dev, staging, and prod usually share structure but differ in configuration:

| Attribute | Dev | Staging | Prod |
| --- | --- | --- | --- |
| Compute size | Small | Near-prod or representative of load tests | Per capacity plan |
| Data | Synthetic | Masked/synthetic | Real data under strict controls |
| Availability | Can be simpler | Simulates HA when needed | Per SLO |
| Backup | For experimentation | Restore testing | Per RPO/retention |
| Network | Environment-isolated | Similar to prod | Strict boundary |
| Access | Developer scope | Test/release scope | Separate workload/admin scopes |

Do not copy dev configuration verbatim to production without considering sizing, resilience, privacy, and access boundaries. Likewise, do not let staging diverge completely from production if the goal is to catch issues before release.

### 6.1. Separating code and data

Keep the same modules and pass different values per environment. Do not create three copy-pasted module copies when the only differences are sizing or subnet IDs.

Sensitive values such as database passwords, signing keys, or tokens should not be committed in tfvars/parameter files. Reference a secret manager instead and grant read access to the appropriate workload/deployment identity.

## 7. State: critical data of IaC

For many declarative tools, state stores the mapping between declared resources and real-world resources, along with metadata required for planning and updates. State can contain sensitive information depending on the resource/provider and should not be treated as a regular config file.

### 7.1. Local state vs. remote state

| Type | Advantages | Risks/trade-offs |
| --- | --- | --- |
| Local state | Easy to learn and run small experiments | Hard to collaborate, easy to lose or overwrite, manual backups |
| Remote state | Better collaboration and automation, can combine with locking/versioning | Requires managing the backend, permissions, encryption, availability, and cost |

Production typically requires a remote backend with appropriate access control, encryption, versioning/backups, and locking. Never commit state to public or broadly shared repositories.

### 7.2. State locking

Locking prevents two processes from modifying the same state simultaneously. Not all backends support locking in the same way; verify the semantics of both the tool and backend. When a pipeline is interrupted, a stale lock may need controlled handling. Never remove a lock manually without verifying the owning process and whether a write is actively in progress.

### 7.3. State separation

State can be split by environment, account/project, domain, or blast radius. Splitting too finely complicates dependencies and outputs; bundling too much means a single change can impact a wide scope and increases lock contention.

A practical principle is to split by lifecycle and owner: network foundation, shared platform services, workload stacks, and individual environments can each have separate state. Any cross-stack state reference must use least-privilege read access.

### 7.4. State backup and recovery

- Enable backend versioning or snapshots where supported.
- Restrict read/write access to state.
- Encrypt at rest and in transit.
- Do not log full state in CI.
- Test state restore and resource mapping procedures.
- Define procedures for handling state locks and state corruption.
- Audit import, move, remove, and recovery operations.

If state is lost while resources still exist, do not blindly recreate them. Import or restore the mapping using a tested procedure.

## 8. Dependency graph and deployment order

A cloud architecture has dependencies: network before compute, identity before service access, database before application endpoints, and monitoring and logging ready when workloads run.

~~~mermaid
flowchart TD
    ORG["Organization / IAM baseline"]
    NET["Network foundation"]
    SEC["Secrets / KMS / security policy"]
    DATA["Database / Object Storage"]
    COMPUTE["Compute / Container platform"]
    APP["Application services"]
    OBS["Monitoring / Logging / Alerts"]
    ORG --> NET
    ORG --> SEC
    NET --> DATA
    NET --> COMPUTE
    SEC --> DATA
    SEC --> COMPUTE
    DATA --> APP
    COMPUTE --> APP
    APP --> OBS
    DATA --> OBS
~~~

The IaC engine can infer dependencies from references between resources. When a dependency cannot be expressed via a reference, some tools support explicit dependency declarations. Add explicit dependencies only when truly necessary; unnecessary dependencies reduce parallelism and create artificial ordering.

### 8.1. Cross-stack/repository dependencies

When network and workloads live in separate states, establish a clear contract: the network stack provides subnet IDs, route tables, and security boundaries; the workload stack consumes those outputs. Avoid querying resources by ambiguous names or hardcoding IDs that can easily change.

Outputs can be published via remote state, a parameter store, a service catalog, or versioned configuration artifacts. Each mechanism must define access permissions, consistency, and how breaking changes are handled.

## 9. Terraform-style infrastructure declaration example

The following example illustrates the concept; it is not a complete production configuration and is not tied to a specific cloud provider:

~~~hcl
variable "environment" {
  type = string

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be dev, staging, or prod."
  }
}

variable "private_subnet_ids" {
  type = list(string)
}

module "booking_database" {
  source = "../../modules/database"

  name                 = "booking-" + var.environment
  environment          = var.environment
  subnet_ids           = var.private_subnet_ids
  encryption_enabled   = true
  public_access        = false
  backup_retention_days = var.environment == "prod" ? 14 : 2
}

output "database_endpoint" {
  value = module.booking_database.endpoint
}
~~~

This example shows `environment` as a validated input, `subnet_ids` passed in from the foundation layer, and the database module invoked with explicit security intent. A real-world module also needs version pinning, provider configuration, password/secret handling, monitoring, parameter compatibility, deletion protection, and policy validation.

## 10. Provider, version, and dependency configuration

An IaC repository has external dependencies such as provider plugins, module registries, package libraries, or CLIs. Floating versions can cause plans to change even when the source code has not changed.

Pin tool/provider/module versions according to policy; commit lock files if supported by the ecosystem; review dependency changes like source code changes; verify checksums/signatures or artifact provenance when supported by the tooling; use trusted registries/repositories; and maintain a process for version upgrades and compatibility testing.

Do not lock every dependency forever. A regular upgrade cadence is needed to receive security fixes, bug fixes, and new APIs, but upgrades must be tested in a controlled manner.

## 11. Secrets, identity, and deployment permissions

IaC carries broad privileges because it can create databases, networks, IAM resources, and delete assets. Therefore, the deployment pipeline is a security boundary.

### 11.1. Never store secrets in source control

Do not commit passwords, private keys, access tokens, or provider credentials in tfvars/config files, variable defaults, outputs, unprotected plan artifacts, CI logs, or container images.

Use workload identity/federation or short-lived credentials for pipelines whenever possible. Runtime secrets are read by workloads from a secret manager under least privilege. Note that state and plans may still contain secrets if a provider/resource writes sensitive values into metadata.

### 11.2. Separating plan and apply permissions

- Pull requests can run validate/plan using the required read permissions.
- Production applies run only from protected branches/environments.
- The deployment identity only has permissions to modify resources within its assigned scope.
- Sensitive IAM/policy changes require independent review.
- Do not allow forks/untrusted PRs to receive production write credentials.
- Logs/audit records capture the principal, commit, plan, and deployment result.

Do not assume someone who authors modules should also hold organization admin privileges.

## 12. Testing IaC before and after deployment

| Layer | Objective | Example |
| --- | --- | --- |
| Format/lint | Style and structural errors | Formatter, linter |
| Validate | Schema, types, required arguments | Validate command |
| Unit/policy test | Contracts and guardrails | Input/output tests, policy rules |
| Static security scan | Detect dangerous configurations | Public storage, open firewall, unencrypted DB |
| Plan review | Inspect expected changes | Create/update/replace/destroy |
| Integration test | Verify resources work together | Service accessing private DB |
| Smoke test | Post-apply verification | Health check, DNS, auth, data access |
| Drift scan | Compare actual vs. desired state | Scheduled plan/config assessment |

### 12.1. Module testing

Modules should include tests for safe defaults; valid and invalid inputs; output contracts; security invariants such as non-public databases; key environment/plan scenarios; and version changes with backward compatibility.

Tests do not replace plan review. A module whose tests pass can still produce destructive changes when production inputs change.

## 13. Plan, apply, and change review

For plan/apply-style tools, the plan is a critical artifact for review. Approvers should inspect which resources are created, updated, replaced, or destroyed; sensitive resources; network impact; database replacement/downtime; new IAM permissions; cost estimates; and cross-module/environment impacts.

The plan should be generated from the exact same source commit, tool/provider versions, and inputs that the pipeline will apply. If code or variables change after approval, a new plan must be generated and reviewed again.

### 13.1. Destructive changes

Deleting a database, bucket, key, network, or stateful resource requires protective controls: deletion protection, verified backups, explicit approval, a maintenance window, and a recovery plan. Never rely on a single automated confirmation flag in a pipeline to delete critical resources.

## 14. CI/CD pipeline for IaC

~~~mermaid
flowchart TD
    PR["Pull request"]
    FMT["Format / lint / validate"]
    SEC["Policy and security scan"]
    PLAN["Generate plan"]
    REVIEW["Code review / approval"]
    APPLY["Apply with scoped identity"]
    POST["Smoke test / health checks"]
    DRIFT["Scheduled drift detection"]
    PR --> FMT --> SEC --> PLAN --> REVIEW --> APPLY --> POST
    POST --> DRIFT
    DRIFT -->|"Finding"| PR
~~~

A practical pipeline can check out the exact commit; install pinned tool/provider versions; run format/lint/validate; execute policy/security tests; initialize the backend and load state with restricted permissions; generate and store the plan artifact under access controls; obtain review/approval; apply the exact approved plan if supported by the tool; run smoke tests; store deployment evidence; and scan for drift periodically.

The pipeline must enforce timeouts, appropriate retries, state-level concurrency controls, and handling for mid-run job cancellation. Never run two concurrent applies against the same state unless the backend/locking guarantees safety.

## 15. Drift detection and managing out-of-band changes

Drift occurs when actual infrastructure differs from the desired configuration. Causes include console changes, external automation, changes made by cloud services, or out-of-sync state.

Handling options:

- **Reconcile:** update actual resources back to desired state via apply.
- **Import/adopt:** bring resources created outside IaC under management.
- **Update code:** accept valid changes and update the source code.
- **Revert:** restore the previous configuration if the change was unauthorized.
- **Exception:** grant a temporary exception with an owner, rationale, and expiry.

Do not automatically revert every drift. For example, an emergency change made to mitigate an incident may be valid; it must be verified, reflected in IaC, and audited. Auto-remediation can also cause downtime if it triggers unintended resource replacement.

### 15.1. Drift review

Detect drift and identify the resource/field; check the actor/change log; classify as valid or a violation; assess impact/severity; choose reconcile, import, code update, or exception; review and deploy; re-run the scan and retain evidence.

## 16. State migration, refactoring, and lifecycle

When reorganizing repository structure or renaming modules/resources, IaC may interpret the change as deleting the old resource and creating a new one. For databases, storage, or networks, replacement can cause data loss or downtime.

State move/import/remove operations require backing up state; understanding the old-to-new address mapping; using official move/rename features where appropriate; generating a plan to confirm no unexpected destroy/create operations; executing in small scopes with a rollback plan; and preserving commit history and evidence.

Lifecycle policies can prevent destruction or protect critical resources. These are an additional guardrail layer, not a substitute for backups and review. Retention policies can be configured for temporary environments, provided cleanup does not delete data that must be retained.

## 17. Cost, tagging, and long-term operations

IaC determines resource scale, count, and topology, directly affecting cost. Code can be syntactically valid yet overly expensive or lack an owner.

Reviews should examine instance sizing, autoscaling bounds, and idle capacity; database tier/storage/IOPS/backups/replicas; network egress and cross-zone/region data transfer; log/metric retention and ingestion; queue/cache/search capacity; resource tags/owner/cost center/expiry; and per-project/account budgets and limits.

Do not optimize solely for the lowest cost. A cheaper tier may fail to meet availability, latency, or RPO/RTO targets. Decisions should explicitly capture trade-offs between cost and SLOs.

## 18. Hands-on lab: building an IaC structure for the booking platform

**Scenario:** the team needs to create three environments—dev, staging, and prod—for the Booking Platform. Each environment includes networking, compute, a database, object storage, a queue, and monitoring. Prod requires a private database, encryption, backups, central logging, and workload identity.

### Tasks

1. Propose a repository structure containing modules, environments, policies, tests, scripts, and docs.
2. Define module boundaries for network, identity, database, compute, storage, and observability.
3. Design the input/output contract, defaults, and validations for the database module.
4. Separate environment configuration from reusable modules; identify environment-specific vs. shared values.
5. Choose state boundaries, remote backend, locking, versioning, backups, and access controls.
6. Draw the dependency graph and define the bootstrap order.
7. Design IAM/workload identity for CI plan/apply and runtime services.
8. Write policies checking encryption, private networking, regions, tagging, and public exposure.
9. Build a pipeline for format, validate, test, scan, plan, review, apply, and smoke tests.
10. Simulate drift caused by a console change and choose between reconcile/import/exception.
11. Inspect a plan with unexpected database replacement or storage destruction; design the approval flow.
12. Write ADRs for repository layout, state split, module versioning, and cost guardrails.

### Proposed structure template

| Directory | Contents | Owner |
| --- | --- | --- |
| modules/network | VPC/VNet, subnets, routes, security boundary | Cloud platform |
| modules/database | Database, backups, encryption, monitoring | Data platform |
| modules/compute-service | Runtime, autoscaling, health checks | Application platform |
| modules/identity | Workload roles, trust, scoped permissions | IAM platform |
| environments/dev | Composition and dev inputs | Development team |
| environments/staging | Composition and staging inputs | Release/platform |
| environments/prod | Composition and production inputs | Production owner |
| policies | Guardrails and compliance rules | Security/platform |
| tests | Module, policy, and integration tests | Module owner |
| docs/decisions | Architecture decision records | Architecture owner |

### Completion criteria

- The repository has clear module/environment/policy/test boundaries.
- Modules have small interfaces, validation, and output contracts.
- Environments share modules while using appropriate configurations and state boundaries.
- State is protected, backed up, and locked according to backend capabilities.
- The dependency graph accurately reflects ordering and cross-stack contracts.
- Secrets are never committed; pipelines use scoped identities.
- Format/validate/test/security scan/plan review/smoke tests are in place.
- Destructive changes require approval and a recovery plan.
- Drift has an owner and a reconciliation process.
- Cost tags, owners, and lifecycles are verified.

## 19. Well-Architected checklist before taking IaC to production

- [ ] Every resource belongs to the right module and has a clear owner/lifecycle.
- [ ] Repository structure separates reusable modules, environment composition, policies, tests, and documentation.
- [ ] Modules have clear interfaces, input validation, safe defaults, and output contracts.
- [ ] Module/provider/tool versions are pinned and updated in a controlled manner.
- [ ] Environments share the same modules with appropriate configurations, permissions, and data.
- [ ] Secrets are never committed; state/plans are protected as sensitive data.
- [ ] Remote state has appropriate access control, encryption, versioning/backups, and locking.
- [ ] State boundaries follow lifecycle/owner and minimize blast radius.
- [ ] Dependency graph and cross-stack outputs have explicit contracts.
- [ ] Pipeline/runtime IAM follows least privilege and workload identity.
- [ ] Policies verify network exposure, encryption, regions, backups, and tagging.
- [ ] CI runs appropriate format, validate, policy, security, plan, and integration checks.
- [ ] Plans are reviewed from the exact commit/versions/inputs that will be applied.
- [ ] Destructive replacements/deletions have approvals, backups, and rollback/recovery plans.
- [ ] Drift is continuously detected and classified prior to remediation.
- [ ] State moves/imports/refactors are backed up and verified against the plan.
- [ ] Cost, quotas, egress, retention, and resource lifecycles are evaluated.
- [ ] Audit evidence, runbooks, smoke tests, and operational owners are established.
- [ ] ADRs explicitly document trade-offs across reliability, security, performance, cost, and operations.

**Key takeaway:** IaC turns architecture into code that can be reviewed, tested, and reproduced. A solid structure separates modules by capability, composition by environment, state by lifecycle/owner, and policies/tests as guardrails. When combined with version control, plan review, least-privilege deployment permissions, state protection, drift detection, and recovery processes, IaC becomes a consistent cloud operating foundation rather than just a collection of configuration files.
