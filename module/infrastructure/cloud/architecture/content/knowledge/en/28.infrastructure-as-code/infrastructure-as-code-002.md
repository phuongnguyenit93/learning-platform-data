# Reusable Module Decomposition and Ownership Boundaries

## Learning Objectives

Infrastructure as Code (IaC) describes infrastructure in code that can be reviewed, versioned, tested, and deployed repeatedly. As the number of workloads, environments, accounts, and teams grows, organizing IaC into modules becomes a key architectural decision. If each team copy-pastes network, database, identity, and logging configurations, the system quickly accumulates variants that are difficult to control. Conversely, if everything is lumped into a single generic module with hundreds of parameters, small changes can affect multiple workloads and erode team autonomy.

A **reusable module** is a configuration unit with a well-defined interface, responsibility, and behavior that can be reused without duplicating implementation. A **module boundary** defines what belongs to a module, what the module owns, and how it interacts with the rest of the system. An **ownership boundary** defines which team or capability is responsible for designing, changing, operating, and supporting the module or the resources it creates.

This lesson focuses on how to decompose reusable modules and define ownership boundaries in IaC. A sound design balances reusability with clarity, change isolation, state control, security, deployment velocity, and operability. A module is not just a way to reduce lines of code; it is a technical contract between the platform team and the workloads consuming infrastructure.

This lesson belongs to the **Infrastructure as Code** chapter, focusing on **reusable module decomposition and ownership boundaries**. Within Cloud Architecture, modules must reflect business requirements and network, compute, data, and deployment boundaries while supporting reliability, security, scalability, cost, and operations according to Well-Architected principles.

After this lesson, you will be able to:

- Distinguish between module, root configuration, component, stack, workspace, and state.
- Define module boundaries by domain, lifecycle, ownership, and change coupling.
- Design input/output contracts with clear data types, validation, defaults, and semantics.
- Separate foundation modules, capability modules, and workload modules.
- Decide when to use shared modules, specialized modules, or composition.
- Avoid overly generic modules, premature abstraction, and copy/paste configuration.
- Design cross-module dependencies via output contracts, avoiding internal coupling.
- Manage versioning, compatibility, deprecation, and migration.
- Choose appropriate state boundaries, locking, permissions, and deployment ownership.
- Organize repositories, reviews, testing, releases, and cross-environment promotion.
- Design security guardrails, policies, and cost ownership inside modules.
- Write ADRs and evaluate module architecture using Well-Architected principles.

## 1. Why decompose into modules?

Suppose a company operates multiple cloud applications: a booking API, a payment service, a reporting platform, a data warehouse, and background workers. All workloads require networking, IAM, logging, encryption, monitoring, and compute, yet their requirements differ.

If every workload defines all of its resources independently:

- Network rules can diverge across environments.
- Encryption, backups, and logging are easily overlooked.
- Teams have to manually update the same configurations whenever a new security baseline rolls out.
- Cost tags and ownership become inconsistent.
- Misconfigurations can persist in some workloads undetected.

If all resources are placed inside a single monolithic module:

- Every team depends on one large release.
- A change for workload A can impact workload B.
- The module accumulates conditionals, flags, and special cases.
- Reviewers struggle to tell who a change affects.
- Teams cannot release independently.
- State and modification permissions become overly concentrated.

Thoughtful module decomposition produces reusable capabilities while keeping each capability's responsibilities and management lifecycle clear.

### 1.1. A module is a contract boundary

A module should answer four questions:

1. **What does it own?** Which resources, logic, and lifecycle fall within the module's scope?
2. **What does it need?** Which inputs are required from the caller or platform?
3. **What does it provide?** Which outputs are callers allowed to consume?
4. **Who is responsible?** Which team releases, supports, handles incidents for, and evolves the contract?

A module should not force callers to understand its internal structure. Callers should rely on the public interface rather than referencing internal resources or inferring generated resource names.

~~~mermaid
flowchart LR
    CALLER["Root / workload stack"] --> INPUT["Module inputs"]
    INPUT --> MODULE["Reusable module"]
    MODULE --> RES["Owned resources"]
    RES --> OUTPUT["Public outputs"]
    OUTPUT --> CONSUMER["Dependent module / workload"]
    OWNER["Module owner"] --> MODULE
    OWNER --> SUPPORT["Support / lifecycle"]
~~~

## 2. Key concepts to distinguish

| Concept | Role | Example |
| --- | --- | --- |
| Module | Configuration unit with an interface and responsibility | VPC module, managed database module |
| Root configuration | Entry point composing modules for a deployment | Production booking stack |
| Component | Architectural building block that may span multiple resources/modules | Application platform component |
| Stack | Set of resources deployed and managed together | Booking production stack |
| Workspace/environment | Deployment or configuration context | dev, staging, production |
| State | Metadata mapping resources to IaC configuration | Terraform state |
| Provider | Plugin interfacing with platform APIs | AWS/Azure/GCP provider |
| Module registry | Repository for storing and publishing versioned modules | Internal Terraform registry |

A module is not synonymous with a state. Multiple modules can be invoked from the same root configuration and share a state; conversely, each stack/module boundary can be deployed in its own state. State boundary decisions must consider access permissions, blast radius, locking, release cadence, and ownership.

### 2.1. Reusable module vs. deployment instance

A reusable module is a blueprint. Each module invocation creates a configured instance in a specific deployment. For example, a network module can be called in production and staging with different CIDRs, AZs, and tags. Those two instances have distinct resource identities and lifecycles even though they share the same implementation.

### 2.2. A module does not have to be a single resource

A module may bundle multiple resources to deliver a complete capability: a network module includes VPC, subnets, routes, and security baselines; a database module includes the database instance, subnet group, parameter group, monitoring, and backup settings. Boundaries should be drawn around responsibilities and what changes together, not around resource count.

## 3. Principles for defining module boundaries

### 3.1. Cohesion: things that change together belong together

If a group of resources is always created, tested, upgraded, and rolled back together, they likely belong in the same module. For instance, a database subnet group, parameter group, and database instance usually share a clear lifecycle relationship; splitting them into tiny modules creates excessive dependencies and hurts readability.

Conversely, the network foundation has a long lifecycle and is shared across many workloads, whereas a database instance follows the application's lifecycle. Separating them ensures database changes do not force a release of the entire network.

### 3.2. Loose coupling: callers depend on interfaces, not internals

Module A should expose meaningful outputs such as subnet IDs, endpoints, security group IDs, or role ARNs. Module B receives those outputs via inputs. Callers should not directly reference internal addresses such as local resource names, implicit map keys, or another module's raw state paths.

### 3.3. Ownership: every boundary needs a clear owner

If two teams co-own a module without clear decision rules, changes stall or conflict. Every module needs an owner accountable for its contract, releases, and support. Consumers can contribute code via review, while the owner remains responsible for release quality and compatibility.

### 3.4. Lifecycle: separate by cadence of change

Network foundations, identity baselines, and audit logging generally change less frequently than application deployments. Workload compute, autoscaling, and service-specific permissions move at a faster cadence. When lifecycles differ significantly, consider separating modules or states to reduce coupling.

### 3.5. Security boundary: separate by privilege and trust level

A module managing KMS keys, IAM policies, or network perimeters may require higher privileges than an application deployment module. Separating boundaries prevents workload teams and pipelines from needing account-wide administrative permissions. Any module modifying critical security resources requires commensurate review and approval.

### 3.6. Change impact and blast radius

Ask: if this module changes or is misdeployed, how many workloads are affected? A shared network module can impact many applications; a dedicated queue module has a smaller blast radius. Boundaries should make blast radius explicit and enable controlled rollout and rollback.

### 3.7. Do not split modules solely by resource type

Creating a separate module for every minor resource forces the root configuration to wire excessive inputs and outputs. For example, splitting security groups, rules, ingress, egress, and attachments into five modules complicates interfaces without improving ownership.

Instead, group by semantic capability—for instance, a service network policy module that accepts structured ingress/egress rules, validates them, and provisions the related resources.

## 4. Layered module model

A useful pattern organizes modules into three tiers: foundation, capability, and workload.

~~~mermaid
flowchart TB
    ROOT["Environment root / application stack"]
    ROOT --> WORK["Workload modules"]
    WORK --> CAP["Capability modules"]
    CAP --> BASE["Foundation modules"]
    BASE --> CLOUD["Cloud provider resources"]
    WORK --> CLOUD
    CAP --> CLOUD
~~~

### 4.1. Foundation modules

Foundations establish the shared base or baseline for an account, region, or environment:

- Network/VPC/VNet, subnets, routes, endpoints.
- Identity baselines, roles, policy boundaries.
- KMS/key management and encryption defaults.
- Audit logging, centralized log destinations.
- Shared DNS, certificates, and connectivity.
- Guardrails, tagging policies, and account baselines.

Foundations typically have a large blast radius, a long lifecycle, and owners from the platform, security, or networking team. They require cautious release processes, compatibility guarantees, and migration plans.

### 4.2. Capability modules

Capabilities provide reusable building blocks:

- Managed PostgreSQL with backup/monitoring baselines.
- Queues/topics with encryption, DLQ, and retention.
- Object storage buckets aligned with data classification.
- Container services or serverless functions.
- Observability integrations.
- Private service endpoints.
- Autoscaling profiles or workload identities.

Capability modules can be invoked by many workloads with varying configurations while maintaining shared guardrails and defaults.

### 4.3. Workload modules/stacks

A workload root composes capabilities to instantiate a concrete system: booking API, payment worker, analytics pipeline. It defines instance counts, sizing, scaling profiles, service-specific environment variables, integrations, and network connections to the foundation.

Do not push all business logic or every app-specific resource into a generic foundation module. Workload owners need control over settings tied to their specific needs.

### 4.4. Layering is not a mandatory hierarchy

One module can call another, but not every layer needs a wrapper. If a workload uses a single straightforward resource with no custom policy or contract, declaring the provider resource directly in the root can be clearer than creating a wrapper module that adds no value.

## 5. Example: network foundation module

Suppose multiple workloads need a private network with subnets across multiple AZs. The network module should own the network topology and return stable outputs.

Example layout:

~~~text
modules/
  network/
    main.tf
    variables.tf
    outputs.tf
    versions.tf
    README.md
    examples/
      basic/
      private-app/
    tests/
      network.tftest.hcl
~~~

### 5.1. Input contract

~~~hcl
variable "name" {
  description = "Stable name for the network deployment"
  type        = string
}

variable "cidr_block" {
  description = "Primary IPv4 CIDR for the network"
  type        = string

  validation {
    condition     = can(cidrnetmask(var.cidr_block))
    error_message = "cidr_block must be a valid IPv4 CIDR."
  }
}

variable "availability_zones" {
  description = "Availability zones used by the network"
  type        = list(string)

  validation {
    condition     = length(var.availability_zones) >= 2
    error_message = "At least two availability zones are required."
  }
}

variable "tags" {
  description = "Additional resource tags"
  type        = map(string)
  default     = {}
}
~~~

The contract should request only inputs the caller genuinely needs to decide. Do not expose dozens of provider-specific flags on the public interface if most workloads do not need them. Security baselines and naming conventions can be enforced by default inside the module.

### 5.2. Resource-owning implementation

~~~hcl
resource "aws_vpc" "this" {
  cidr_block           = var.cidr_block
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(var.tags, {
    Name = var.name
    ManagedBy = "terraform"
  })
}
~~~

This abbreviated example only creates a VPC. A production module typically also needs a subnet strategy, routes, endpoints, flow logs, IPv6 policy, IPAM, NAT topology, and security guardrails.

### 5.3. Public outputs

~~~hcl
output "vpc_id" {
  description = "ID of the created VPC"
  value       = aws_vpc.this.id
}

output "vpc_cidr_block" {
  description = "Primary IPv4 CIDR of the VPC"
  value       = aws_vpc.this.cidr_block
}
~~~

Callers depend on the output contract. Avoid forcing callers to rely on internal resource names like `aws_vpc.this` if the implementation might evolve.

### 5.4. Root configuration invoking the module

~~~hcl
module "network" {
  source  = "app.terraform.io/acme/network/aws"
  version = "2.3.0"

  name               = "booking-prod"
  cidr_block         = "10.40.0.0/16"
  availability_zones = ["ap-southeast-1a", "ap-southeast-1b"]

  tags = {
    Environment = "production"
    Owner       = "platform-network"
    CostCenter  = "CC-BOOKING"
  }
}
~~~

Registry names and versions are illustrative. Callers pin explicit versions and review the plan when upgrading.

## 6. Example: database capability module

A database module can own the database instance, subnet group, parameter group, monitoring, backups, and related security settings. The module should accept network identities from the foundation rather than creating a new network itself.

~~~hcl
variable "private_subnet_ids" {
  description = "Private subnets for database placement"
  type        = list(string)

  validation {
    condition     = length(var.private_subnet_ids) >= 2
    error_message = "Database must span at least two private subnets."
  }
}

variable "engine_version" {
  description = "Approved database engine version"
  type        = string
}

variable "backup_retention_days" {
  description = "Automated backup retention in days"
  type        = number
  default     = 14

  validation {
    condition     = var.backup_retention_days >= 7
    error_message = "Backup retention must meet the platform baseline."
  }
}
~~~

The root configuration composes the two capabilities:

~~~hcl
module "network" {
  source  = "app.terraform.io/acme/network/aws"
  version = "2.3.0"

  name               = "booking-prod"
  cidr_block         = "10.40.0.0/16"
  availability_zones = ["ap-southeast-1a", "ap-southeast-1b"]
}

module "booking_database" {
  source  = "app.terraform.io/acme/postgres/aws"
  version = "4.1.2"

  name                  = "booking-prod"
  private_subnet_ids    = module.network.private_subnet_ids
  engine_version        = "16.4"
  backup_retention_days = 14
}
~~~

Dependencies are expressed through output/input contracts. Terraform infers the dependency graph from those references. Avoid broad use of `depends_on` solely to force ordering when references already describe the relationship; the dependency graph should reflect actual relationships.

### 6.1. A module must not silently take over dependency ownership

The database module should not directly modify route tables or security groups owned by the network module without an explicit contract. When network rules are needed, options include:
- The database module exports a security group ID and requires the root to wire a rule module.
- The database module accepts source security group IDs and creates rules it owns.
- A network policy capability module owns the rules and accepts explicit inputs.

Pick one consistent model so two modules never manage the same resource or attribute.

## 7. Interface design: inputs, outputs, and validation

### 7.1. Minimal yet semantic inputs

Inputs should express intent rather than forcing callers to know excessive provider details. For example, accept `retention_days` instead of requiring callers to construct an entire lifecycle rule object if the module owns the lifecycle policy.

However, abstraction must not hide decisions with major consequences. Callers must know whether the module creates public or private subnets, what encryption type is used, how long backups are retained, and whether NAT gateways are provisioned when these affect security or cost.

### 7.2. Required, optional, and default values

- Required input: a decision the module cannot safely infer on its own.
- Optional input: a valid variation that not every workload requires.
- Default: a baseline chosen and maintained by the module owner.
- Derived value: computed internally by the module from validated inputs.
- Forbidden/unsupported: configurations blocked by policy or unsupported by the module.

Never use ambiguous defaults such as `false` for a security control if callers might interpret it as disabling encryption. For critical attributes, defaults should be secure and the contract must explain them clearly.

### 7.3. Validation and preconditions

Validation should catch errors early:
- Valid CIDRs that do not overlap known ranges.
- Sufficient AZ count for the availability target.
- Backup retention meeting policy.
- Engine version within the supported list.
- Instance sizing aligned with workload tier.
- Required tags including owner/environment/cost center.
- Public exposure requiring an explicit exception.
- Replica counts/concurrency within quotas.

Local validation cannot verify all runtime conditions; a policy engine or deployment pipeline may need to check cross-resource and account-wide constraints.

### 7.4. Outputs are an API

Outputs should:
- Have stable names and data types.
- Expose only what consumers need.
- Never return secrets/passwords/private keys.
- Have clear descriptions and semantics.
- Support deprecation under a versioning policy.
- Avoid exposing unnecessary resource internals.

Do not export extra outputs just because they are easy to grab. Every public output creates an ongoing compatibility obligation.

## 8. Module composition and avoiding dependency cycles

Module composition wires capabilities together to deploy a workload. The root configuration typically has full context and connects the modules.

~~~mermaid
flowchart TB
    ROOT["Root stack: booking-prod"]
    ROOT --> NET["Network module"]
    ROOT --> DB["Database module"]
    ROOT --> QUEUE["Queue module"]
    ROOT --> APP["Application module"]
    NET --> DB
    NET --> APP
    DB --> APP
    QUEUE --> APP
~~~

The diagram illustrates a directed acyclic dependency flow. Avoid circular dependencies—such as a network module requiring a database's security group while the database module requires the network's subnet outputs; if a cycle arises, separate the network foundation and security policy interfaces more cleanly.

### 8.1. Root module orchestration

The root module is responsible for:
- Selecting module versions.
- Passing environment-specific configuration.
- Wiring outputs to inputs.
- Selecting provider aliases, regions, and accounts.
- Defining naming, tags, and policy context.
- Orchestrating deployment order via the dependency graph.
- Recording stack ownership and releases.

The root should not contain excessive implementation detail; yet you also do not need a wrapper module for every single invocation if the wrapper adds no distinct contract or policy.

### 8.2. Data sources and cross-stack references

When a module needs resources managed by another stack, use a versioned contract with explicit read permissions: remote state outputs, service discovery, parameter store, resource registry, or explicit inputs. Remote state is convenient, but granting state read access can expose more metadata than the required outputs. For high-security boundaries, prefer publishing only the needed outputs via a registry or parameter store with scoped access policies.

### 8.3. Cross-account and cross-region

Modules can accept provider aliases or receive specific provider configurations from the root. Do not hardcode regions or accounts inside reusable implementations. The root or deployment pipeline determines the target account/region; the module validates resource compatibility and provisions resources within the supplied provider context.

## 9. Module versioning and compatibility

A reusable module is an API. When consumers adopt a module, they rely on its inputs, outputs, behavior, and lifecycle. Contract changes must be managed like API changes.

### 9.1. Semantic versioning

A common convention:
- **Patch:** bug fixes that do not alter the contract or caller-visible behavior.
- **Minor:** backward-compatible capabilities, optional inputs, or new outputs.
- **Major:** breaking changes such as changing input types, removing outputs, changing default behavior, or altering resource identities.

Semantic versioning must be applied consistently—not bumped arbitrarily. Provider or resource behavior can force a major upgrade even when the interface looks identical if the migration affects resource lifecycles.

### 9.2. Breaking changes

Examples:
- Changing default `backup_retention_days` from 7 to 1.
- Switching subnet selection from private to public.
- Changing engine family in a way that replaces the database.
- Renaming an output already used by consumers.
- Changing security group rule ownership.
- Changing encryption keys or KMS policies.
- Changing resource naming that triggers destroy/create.

Never assume a default change is non-breaking. Default behavior is part of the contract; changing it can affect security, availability, cost, or trigger resource replacement.

### 9.3. Deprecation policy

To remove an output or input:
1. Mark it deprecated and explain the replacement.
2. Provide a version/module migration guide.
3. Identify consumers using registry/usage inventory if available.
4. Provide a transition window per policy.
5. Release a major version to remove it.
6. Maintain older versions for the published support window.

### 9.4. Pinning versions and controlled upgrades

Production should pin specific module versions or immutable references. Upgrades proceed via pull request, changelog review, plan review, testing, and staged rollout. Avoid pointing sensitive deployments at a `main` branch or mutable tags.

## 10. State boundaries and resource ownership scope

State holds the mapping between configuration and real-world resources. Splitting modules does not require splitting state; splitting state is a decision about permissions, lifecycles, and blast radius.

### 10.1. One large state

Advantages:
- Cross-resource dependencies are managed directly by Terraform.
- Easy to apply a single consistent graph.
- Fewer remote-state interfaces.

Limitations:
- Large blast radius.
- Lock contention across teams.
- Broad state read permissions.
- A single change can impact multiple workloads.
- Long apply durations.

### 10.2. Multiple smaller states

Advantages:
- Isolation by team, environment, or domain.
- Independent locking and deployments.
- Easier to scope permissions.
- Smaller blast radius.

Limitations:
- Need to publish and consume interfaces across states.
- Ordering and orchestration become more complex.
- Partial deployments can occur.
- Refactoring resources across states requires controlled import/move steps.
- More backends, locks, and backups to operate.

### 10.3. Choosing boundaries by ownership

A practical guideline:
- Account/network foundation state: platform/network owner.
- Security baseline/identity state: security/platform owner.
- Shared data platform state: data platform owner.
- Each workload stack state: workload team.
- Ephemeral test state: pipeline/test owner with a TTL.

Do not share one state across all teams purely for initial convenience. Likewise, do not create one state per resource when orchestration overhead outweighs isolation benefits.

### 10.4. Resource ownership must never overlap

Every resource must have a single authoritative state owner. Two states or two tools managing the same resource will contend, accidentally destroy it, or continuously report drift. When transferring ownership:
1. Freeze related changes.
2. Plan the import/move steps.
3. Back up state and record the mapping.
4. Remove the binding from the old state safely without destroying the remote object.
5. Import into the new state.
6. Run a plan on both sides.
7. Verify there are no unintended create/destroy actions.
8. Re-enable pipelines and record the audit trail.

Direct state-manipulation commands must be reviewed and executed by an authorized owner.

## 11. Repository structure and team ownership

### 11.1. Illustrative mono-repo structure

~~~text
infrastructure/
  modules/
    network/
    postgres/
    queue/
    object-storage/
    workload-identity/
    observability/
  stacks/
    production/
      booking/
      payment/
      analytics/
    staging/
      booking/
      payment/
  policies/
    security/
    cost/
    compliance/
  tests/
    integration/
    policy/
  docs/
    architecture/
    module-catalog/
~~~

A mono-repo makes it easier to review dependencies/modules in one place and coordinate synchronized changes. It requires appropriate CI, ownership rules, and safeguards so a minor edit does not force every stack to redeploy.

### 11.2. Multi-repo

The module library and workload stacks can be split into separate repositories. Advantages include clearer module versioning/releases and separated permissions; drawbacks include needing a registry, dependency update automation, and cross-repo compatibility testing.

### 11.3. Ownership catalog

Every module should have a catalog entry:
- Module name and purpose.
- Owner team and contact/on-call.
- Repository/registry location.
- Supported providers/engines/versions.
- Input/output contract.
- Security/cost defaults.
- Dependencies and primary consumers.
- Version support/deprecation status.
- Test status and release cadence.
- Documentation/examples.
- Incident/runbook and escalation path.

Ownership should be encoded in repository metadata, CODEOWNERS, or a registry catalog so reviews automatically route to the right team.

## 12. Testing strategy for reusable modules

A widely reused module can amplify defects rapidly. Tests must verify contracts and behavior, not merely syntax.

### 12.1. Test layers

| Test level | Objective | Example |
| --- | --- | --- |
| Static/lint | Syntax and style | fmt, validate, lint |
| Unit/plan test | Inputs/outputs and resource intent | Check encryption, tags, backups |
| Policy test | Guardrails and security baselines | Public access denied |
| Integration | Real provider behavior in a test account | Provision VPC/database sandbox |
| Contract test | Consumer expectations | Output types/names unchanged |
| Upgrade test | Upgrading from previous versions | Plan causes no unexpected replacements |
| Destruction test | Safe teardown | Does not delete shared resources outside owner |
| Example test | Runnable documentation | Validate/apply example stacks |

### 12.2. Testing default behavior

Defaults matter just as much as explicit inputs. Tests should verify:
- Encryption is enabled by default.
- Public exposure is not enabled unintentionally.
- Backup retention meets baseline.
- Required logs/metrics are enabled.
- Owner/environment/cost-center tags are propagated.
- Quota and naming validations work.

### 12.3. Negative tests

Verify that invalid or dangerous inputs are rejected:
- Malformed or overlapping CIDRs.
- Engine versions outside the support matrix.
- Public subnets supplied for workloads requiring private placement.
- Backup retention below the minimum.
- Missing owner/cost center.
- Incompatible KMS keys.
- Ingress from any address on administrative ports.
- Tiers exceeding account quotas.

### 12.4. Integration tests with cost guardrails

Integration tests may create real resources, incurring costs or consuming quotas. They require dedicated accounts/projects, budgets, TTLs, tagging, cleanup, and concurrency limits. Never run destructive tests against production state.

## 13. Documentation and module contracts

A module's README should answer:
- What capability does the module provide?
- When should and shouldn't it be used?
- Who is the owner?
- Supported versions/providers/regions.
- Inputs/outputs and defaults.
- Which resources does the module create/own?
- Which resources are assumed to pre-exist?
- Security/cost implications.
- Upgrades/breaking changes.
- Minimal example and production-like example.
- Test commands and support path.

Usage examples in documentation should highlight critical decisions such as private/public placement, encryption, backups, and retention. Do not merely auto-generate variable tables without explaining semantics.

## 14. Security and policy in reusable modules

A widely adopted module becomes the default provisioning path across the organization. Security baselines should therefore live close to where resources are created, without turning the module into the sole policy system.

### 14.1. Secure defaults

Examples:
- Private-only databases, encryption enabled, backups enabled.
- Object storage with public access blocked and encryption enabled.
- Queues/topics with encryption, TLS, and DLQs as required.
- Least-privilege IAM roles.
- Log/audit destinations that workloads cannot delete.
- Restricted network ingress using explicit security groups.
- Owner/environment/data-classification tags.

### 14.2. Policy layering

- Module validation catches local input errors.
- IaC policy gates inspect the full stack plan.
- Organization policies block dangerous actions at the account level.
- Runtime configuration monitoring detects drift.
- Security monitoring inspects runtime behavior and exposure.

A private database module alone cannot guarantee total data security if account policies, KMS keys, identities, or network routing are misconfigured.

### 14.3. Never expose secrets via outputs or state

Terraform state can retain sensitive values even when outputs are marked `sensitive`. Avoid using outputs to pass unnecessary passwords or tokens; prefer secret manager references and workload identities. Restrict state access and plan/apply logs to prevent data leakage.

## 15. Cost ownership and tagging inside modules

Reusable modules should enforce a consistent tagging convention without guessing cost centers. Callers can pass `owner`, `environment`, `product`, `cost_center`, `data_classification`, and `managed_by`. The module can enforce required fields and propagate them to taggable resources.

### 15.1. Shared resources

For shared resources such as NAT gateways, centralized logging, shared clusters, or network hubs, costs require an explicit allocation rule:
- Direct allocation by tenant/workload.
- Usage drivers such as bytes, CPU, or request units.
- Fixed allocation by subscription/tier.
- Shared overhead surfaced separately.

Do not tag a shared resource serving hundreds of workloads with a single workload's tag if doing so distorts cost ownership.

### 15.2. Cost interface

Modules can expose outputs supporting cost visibility:
- Resource identifiers.
- Capacity/reservation parameters.
- Storage retention/size.
- Scaling bounds.
- Estimated cost metadata where a reliable source exists.

Do not claim exact costs solely from Terraform inputs; pricing depends on region, usage, and provider meters. Cost estimates are planning inputs that must be reconciled against billing exports.

## 16. Module migration and refactoring

Refactoring from copy/paste code into reusable modules carries the risk of altering resource identities or lifecycles.

### 16.1. Refactoring without altering resources

The goal is to preserve resource identities and state bindings while restructuring the code. In Terraform, a new module address changes the state address. Use `moved` blocks or supported state move procedures, then run a plan to confirm there are no unintended destroys or creates.

Example `moved` block:

~~~hcl
moved {
  from = aws_vpc.main
  to   = module.network.aws_vpc.this
}
~~~

Syntax and capabilities depend on the Terraform version. Always test on a state copy or staging environment before applying to production.

### 16.2. Migrations that change resources

If the new module changes resource types or architecture, split the migration into phases:
1. Provision the new capability in parallel.
2. Synchronize data/configuration if needed.
3. Cut over consumers or traffic.
4. Verify health and parity.
5. Remove legacy resources after approval.
6. Update state and documentation.

Do not combine pure code refactoring with major network, database, or security changes in a single hard-to-review apply.

### 16.3. Rollback and state recovery

Rolling back a module version does not always reverse resource changes. Older code may not recognize newer state schemas, or the provider may have altered the resource. Maintain state backups, migration guides, and recovery plans; prefer forward-fixes when a rollback could destroy resources.

## 17. Common anti-patterns

| Anti-pattern | Consequence | Remediation |
| --- | --- | --- |
| Copy/pasting modules across repos | Divergent baselines and inconsistent patches | Internal module registry and releases |
| Overly generic module | Excessive flags, conditionals, and complexity | Split by real capabilities and use cases |
| Overly granular module | Complex root wiring | Group resources with shared lifecycle/cohesion |
| One module owns everything | Huge blast radius and release coupling | Separate foundation/capability/workload |
| Multiple modules managing one resource | State conflicts and drift | Single authoritative owner |
| Outputs exposing implementation details | Consumer coupling | Stable, semantic output contracts |
| Module calling back to caller or creating cycles | Hard-to-deploy dependency graph | Compose at the root |
| Hardcoding account/region | Poor reusability and promotion | Pass provider context from root |
| Insecure default settings | Consumers inherit risky defaults | Secure defaults and policy tests |
| Unversioned breaking changes | Consumers break silently | Semantic versioning and migrations |
| Pinning `main` branch in production | Non-reproducible deployments | Pin immutable versions |
| Refactoring and replacing simultaneously | Hard-to-review plans, downtime | Separate migration into stages |
| Overly broad remote state usage | Metadata exposure and coupling | Publish minimal outputs |
| No owner/on-call | Broken modules go unowned | Ownership catalog/CODEOWNERS |

## 18. Case study: building a module library for the booking platform

### 18.1. Context

An organization runs 12 workloads across a shared cloud account family. Each workload defines its own VPC/subnets, managed database, queues, buckets, and IAM roles. After several quarters, network policies diverge, backup retention is inconsistent, and the security team struggles to determine resource ownership.

The goal is to create a shared module library while still allowing teams to deploy workloads independently.

### 18.2. Choosing module boundaries

The platform/network team owns the network foundation module: VPC, subnets, routes, endpoints, and flow logs. The security team owns the workload identity baseline, key integrations, and policy rules. The data platform team owns the PostgreSQL capability with encryption/backup/monitoring baselines. Platform messaging owns the queue capability with retention, DLQ, and encryption. Each workload team owns its root stack and application-specific settings.

### 18.3. Contracts and composition

The booking production root invokes the network module, database module, queue module, and application module. The database module receives private subnet IDs from network outputs. The queue module receives key references from the key service contract. The application module receives the database endpoint and queue ARN, but not passwords; the workload identity retrieves secrets/credentials via its runtime identity.

~~~mermaid
flowchart TB
    ROOT["Booking production root"]
    ROOT --> NET["Network foundation"]
    ROOT --> ID["Workload identity"]
    ROOT --> DB["PostgreSQL capability"]
    ROOT --> Q["Queue capability"]
    ROOT --> APP["Booking application"]
    NET --> DB
    NET --> APP
    ID --> APP
    DB --> APP
    Q --> APP
~~~

### 18.4. Ownership and state

- Network foundation state: platform-network team.
- Identity/security state: security-platform team.
- Shared key/logging state: security/platform owner.
- Booking production state: booking team.
- Staging booking state: booking team with separate permissions and backend.
- Module library releases: module owners via registry.

Each resource has a single authoritative state owner. Root stacks reference published outputs through authorized interfaces.

### 18.5. Versioning and rollout

Network module v2.0 changed naming/outputs and is therefore a breaking release. The owner publishes a migration guide, tests against the staging stack, adds `moved` blocks where resource identities can be preserved, and upgrades workloads in waves. A minor database module release adds a monitoring endpoint output without breaking consumers; workloads upgrade on their own cadence.

### 18.6. Metrics to track

- Reduction in duplicated configurations.
- Increase in workloads meeting encryption/backup/network baselines.
- Reduction in time to onboard a new workload.
- Module upgrade success rate.
- Number of breaking changes and impacted consumers.
- Drift and security findings by module version.
- Cost baseline and idle resources.
- Time to route incidents to the right owner.

These are post-rollout metrics to measure, not guaranteed outcomes merely from having a module library.

## 19. Process for designing and releasing a new module

1. Identify the capability and the problem to standardize.
2. Identify consumers, owners, and lifecycles.
3. List module-owned resources and external dependencies.
4. Design the input/output contract.
5. Define secure defaults, quotas, and cost tags.
6. Choose state/deployment boundaries.
7. Write example root configurations.
8. Write unit, policy, integration, and upgrade tests.
9. Review the plan to inspect create/update/replace/destroy actions.
10. Document limitations, support, and migration paths.
11. Publish an immutable version to the registry.
12. Roll out to canary/staging before production.
13. Monitor adoption, errors, drift, and feedback.
14. Deprecate old versions per policy.

## 20. Hands-on exercise

An organization has 8 microservices, 3 environments, and 2 cloud regions. All services require networking, workload identity, PostgreSQL or a key-value store, queues, object storage, and observability. Currently, every service copies IaC from another repository.

Complete the following:

1. Classify which modules are foundation, capability, and workload.
2. Define boundaries/owners for VPC, identity, KMS, database, queue, bucket, and service compute.
3. Write the contract for the network module including required/optional inputs, validations, and outputs.
4. Design a database module accepting private subnet IDs, backup policy, and encryption key reference.
5. Draw the dependency graph, ensuring there are no module cycles.
6. Propose mono-repo vs. multi-repo and explain the trade-offs.
7. Choose state boundaries by account/environment/team and define access controls.
8. Define semantic versioning, deprecation, and support policies.
9. Write test cases for secure defaults, invalid CIDRs, backup retention, and public exposure.
10. Design a migration process from copy/pasted resources to the module library without accidental replacements.
11. Define how to handle emergency changes and resource ownership transfers.
12. Design a dashboard tracking module adoption, versions, drift, deployment success, and cost.
13. Write an ADR detailing module boundaries, owners, state model, and refactoring criteria.

**Self-assessment guidance:** A strong solution has clear module capabilities/owners, contracts that do not leak implementation details, acyclic dependencies, a single state owner per resource, testable version upgrades, and workload teams retaining control over service-specific settings within guardrails.

## 21. Pre-production checklist

- [ ] The module solves a cohesive capability or lifecycle.
- [ ] Resource ownership and team owner are documented.
- [ ] The module defines an input/output contract, descriptions, types, and validations.
- [ ] Secure defaults and cost tags are enforced.
- [ ] Callers do not depend on internal resources.
- [ ] The dependency graph is acyclic and the root handles composition.
- [ ] Provider/account/region context is not hardcoded in reusable modules.
- [ ] State boundaries have clear owners, locking, backups, and permissions.
- [ ] Every resource has a single authoritative state owner.
- [ ] Versioning and breaking-change policies exist.
- [ ] Production pins immutable module versions.
- [ ] Appropriate unit, policy, integration, contract, and upgrade tests are in place.
- [ ] Examples validate cleanly and reflect supported usage.
- [ ] Migration/rollback plans and state recovery evidence exist.
- [ ] Exceptions and emergency changes are audited.
- [ ] The module catalog documents owners, support, changelogs, and deprecations.
- [ ] Cost attribution, tagging, and lifecycles are defined.
- [ ] Adoption, drift, failures, and costs are monitored post-release.

## 22. Well-Architected assessment

| Pillar | Questions when reviewing module boundaries |
| --- | --- |
| **Operational Excellence** | Does the module have clear owners, contracts, docs, CI, versioning, migrations, and support processes? |
| **Security** | Are state, IAM, secrets, network, and policies privilege-separated; are secure defaults and audits verified? |
| **Reliability** | Does the module have tests, rollback/migration plans, and an appropriate blast radius; do shared foundations release safely? |
| **Performance Efficiency** | Does the module support workload-appropriate scaling/capacity; does abstraction add unnecessary dependencies or overhead? |
| **Cost Optimization** | Are tags, lifecycles, sizing, shared-cost ownership, and quotas applied consistently? |
| **Sustainability** | Does the module reduce copy/paste duplication, orphaned resources, overprovisioning, and repetitive maintenance effort? |

**Conclusion:** Decomposing reusable modules is a decision about capabilities, contracts, lifecycles, and ownership. Modules should group resources with shared responsibilities that change together; callers interact through stable inputs/outputs; root stacks orchestrate composition; every resource has a single state owner; and versions and migrations are tested prior to production. Reuse what genuinely shares semantics and guardrails, keep business-specific differences in the workload layer, and continuously measure blast radius, adoption, drift, and cost in the spirit of Well-Architected.
