# Service Limits, Compartment Quotas, and Limit Increase Requests

## Lesson Objectives

In an Oracle Cloud Infrastructure (OCI) landing zone, creating compartments and granting IAM permissions only addresses how resources are organized and who can perform which actions. The platform team must also manage how many resources each environment is allowed to consume and reserve enough headroom for growth, new releases, or service recovery.

This lesson belongs to the **Resource Governance and Landing Zones** topic of the **CLOUD_PROVIDERS_ORACLE** module. After this lesson, you will be able to distinguish service limits from compartment quotas, read limits with their exact scopes, design quotas for OCI environments, and prepare well-justified limit increase requests. The examples connect Compute with VCN, storage, and database dependencies so you avoid situations where one component has sufficient limit while the overall system still fails to deploy.

**All limit numbers in the scenarios below are hypothetical for learning purposes**, not Oracle default limits, quotes, or provisioning guarantees. Always retrieve actual values from your tenancy for the exact region and resource type before applying them.

## 1. Distinguishing Easily Confused Control Layers

Oracle sets **service limits** on tenancy resources; administrators set **compartment quotas** to control consumption within the organization. Raising an internal quota does not raise a service limit. These two mechanisms address different governance responsibilities. [Oracle: Service Limits](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/overview.htm), [Oracle: Overview of Compartment Quotas](https://docs.oracle.com/en-us/iaas/Content/Quotas/Concepts/resourcequotas.htm).

| Mechanism | Question to answer | Example in a landing zone |
| --- | --- | --- |
| IAM policy | Does this principal have permission to act on the resource? | Application team can create VMs in the application compartment |
| Service limit | Up to how much of a resource may the tenancy consume in this scope? | OCPU limit for a Compute family in an AD |
| Compartment quota | How much may this environment or team consume at most? | Sandbox is allowed fewer OCPUs than production |
| Budgets and alerts | Are actual or forecasted costs exceeding governance thresholds? | Alert responsible owners when spending reaches a threshold |
| Host capacity | Can physical infrastructure satisfy the provisioning request right now? | Available hosts matching the requested shape and AD |

A budget is a cost-tracking threshold; a budget by itself does not stop resources from continuing to accrue spend. Therefore, a landing zone should combine budgets with quotas, usage tracking, and alert handling workflows. [Oracle: Track and Manage Usage and Cost](https://docs.oracle.com/en/solutions/oci-best-practices/track-and-manage-usage-and-cost1.html).

Service limits also differ from host capacity: a tenancy can have remaining limit while lacking suitable physical infrastructure to provision a VM. When Compute provisioning assurance is required, evaluate an appropriate capacity reservation option; reservations remain subject to relevant limits. [Oracle: Overview of the Compute Service](https://docs.oracle.com/en-us/iaas/Content/Compute/Concepts/computeoverview.htm).

From an operational standpoint, a provisioning request must simultaneously satisfy access permissions, applicable quantity limits, and service deployment requirements. Never infer that having IAM permission guarantees you can create a resource.

## 2. Reading Scope, Units, and Limit Names Accurately

### 2.1. A Number Must Carry Full Context

Instead of writing "Compute has 20 left," record an observation like this:

| Attribute | Illustrative value to record |
| --- | --- |
| Tenancy | Tenancy where the application is targeted |
| Subscription | Applicable subscription if required by the resource type |
| Service | Compute |
| Limit name | Technical name retrieved from Console or API |
| Unit | OCPUs, GB of memory, resource count, or service units |
| Scope | Global, region, AD, or specifically defined scope |
| Region and AD | Target region; exact AD name if applicable |
| Compartment | Where the resource is created and relevant parent compartments |
| Timestamp | Time when usage figures were collected |

Limit scopes vary by service. Do not use one AD's limit to infer availability in another AD, nor use primary region metrics to conclude that a recovery region is ready. Default values in documentation also depend on account type or billing model; active values must be checked inside the tenancy. [Oracle: Limits by Service](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/default.htm).

For example, the E4 series has OCPU quotas in the `compute-core` family and memory quotas in the `compute-memory` family. The name `standard-e4-core-count` measures OCPUs, not VM count; `standard-e4-memory-count` measures GB of memory. These quotas are AD-scoped. Eligible Container Instances resources may also share the corresponding Compute quotas. [Oracle: Compute Quotas](https://docs.oracle.com/en-us/iaas/Content/Quotas/Concepts/resourcequotas_topic-Compute_Quotas.htm).

### 2.2. A Concrete Calculation

Suppose Sandbox has an E4 quota of 16 OCPUs and 128 GB of memory in the selected AD. Each lab VM uses 2 OCPUs and 16 GB:

```text
VM count by OCPU   = floor(16 / 2)   = 8
VM count by RAM    = floor(128 / 16) = 8
Ceiling across both illustrative quotas = 8 VMs
```

If each VM is changed to 2 OCPUs and 32 GB, the memory quota only supports 4 VMs even though OCPU quota remains. If you switch to a different shape series, look up the limits that apply to that series; an E4 quota does not automatically cap all Compute shapes.

In a real deployment, also check boot volumes, block volumes, network addresses, load balancers, and database resources required by the configuration. Having enough OCPUs does not replace checking those dependencies.

## 3. Calculating Headroom Across All Applicable Constraints

Headroom is the remaining usable amount under a specific constraint. For one resource type within the same scope, you can use this planning model:

```text
Headroom of constraint i = max(0, ceiling_i - usage_i)
Available quantity headroom = min(applicable constraint headrooms)
```

In this model, the service limit uses the tenancy's corresponding usage; a parent compartment quota must include usage across child compartments within that scope. Do not subtract only one application's usage from a shared limit and assume the entire remainder is reserved for that application.

Assume every row below measures E4 OCPUs in **the same AD**, and all quotas apply to the new request:

| Constraint | Hypothetical ceiling | Used within constraint scope | Headroom |
| --- | ---: | ---: | ---: |
| Tenancy service limit | 128 | 108 | 20 |
| Parent compartment `Applications` quota | 64 | 60 | 4 |
| Child compartment `Applications:TeamA` quota | 24 | 12 | 12 |

`TeamA` wants to add one 8-OCPU VM. Although its own quota has 12 left and the tenancy has 20 left, `Applications` only has 4 left. The request fails the parent compartment constraint. Asking Oracle for a service limit increase will not clear that bottleneck.

If only 4 additional OCPUs are needed, the quantity calculation shows eligibility. That is still not a provisioning guarantee: IAM, memory, dependencies, and host capacity must also align.

Across multiple resource dimensions, calculate each dimension separately. Do not combine "4 OCPUs left" and "32 GB RAM left" into a single composite headroom number.

## 4. Writing Clearly Scoped Compartment Quotas

### 4.1. Three Core Operations

Quotas use their own declarative language, visually similar to IAM policies but not IAM permission statements:

```text
set <family> quota <quota-name> to <value> in compartment <compartment>
zero <family> quota <quota-name> in compartment <compartment>
unset <family> quota <quota-name> in compartment <compartment>
```

`set` defines a ceiling; `zero` sets allowed usage to zero; `unset` removes the quota setting so other applicable limits continue to govern. Supported conditions include `request.region` and `request.ad`. Statements within the same policy are evaluated in order; later statements replace earlier ones targeting the same resource. Across simultaneously applicable policies, the stricter constraint takes effect; service limits always remain binding. [Oracle: Quota Policy Syntax](https://docs.oracle.com/en-us/iaas/Content/Quotas/Concepts/quota_policy_syntax.htm).

### 4.2. Sandbox Limit Example

Suppose an organization has a `Sandbox` compartment allowed to run E4 labs in Phoenix. Two illustrative statements:

```text
set compute-core quota standard-e4-core-count to 16 in compartment Sandbox where request.region = 'us-phoenix-1'
set compute-memory quota standard-e4-memory-count to 128 in compartment Sandbox where request.region = 'us-phoenix-1'
```

Here, the region condition only selects where the statement applies. Because these two E4 quotas are AD-scoped, the values apply per matching AD, **not as a single combined total of 16 OCPUs and 128 GB across the entire region**. If the governance goal is total regional spend, plan across the number of ADs in use and add appropriate controls.

These statements also do not block E4 in other regions. Regions that do not match the condition remain governed by other applicable policies and service limits. To build an allowed-region list, design complete blocking and exception statements, then verify their ordering and interactions.

AD names in conditions or API calls must come from your own tenancy; do not copy AD names from another tenancy. For nested compartments, use properly qualified paths, such as:

```text
set compute-core quota standard-e4-core-count to 12 in compartment Applications:Development
```

Oracle's official quota samples demonstrate both nested compartment paths and combining `zero` with exceptions inside the same policy. [Oracle: Sample Quotas](https://docs.oracle.com/en-us/iaas/Content/Quotas/Concepts/sample_quotas.htm).

### 4.3. Intentional Ordering and Exceptions

Within a **single policy**, you can express the intent to block OCPU quotas in a family and then re-enable E4 for Sandbox as follows:

```text
zero compute-core quotas in compartment Sandbox
set compute-core quota standard-e4-core-count to 16 in compartment Sandbox
```

The second statement creates an exception for E4 within this policy. This is an example to test in a lab environment: it does not yet restrict memory, storage, or any other service in Sandbox. If the two statements are split into two separate policies, do not assume the exception will override the blocking policy.

Similarly, if policy A sets a quota of 8 and policy B sets a quota of 12 for the same resource, compartment, and scope, the effective constraint is 8. Raising policy B to 24 alone will not remove the limit from A.

`unset` is also not a way to bypass service limits, clear quotas in all other policies, or inherit another compartment's ceiling. When modifying quotas, review all statements affecting the compartment path and request scope.

### 4.4. Quotas Are Not a Resource Cleanup Mechanism

Do not use lowering a quota as an immediate environment cleanup or bill-reduction tactic. Decommissioning requires identifying resources, owners, data that must be retained, and proper lifecycle actions. Quotas control consumption; resource changes must be handled separately.

When a ceiling is below current usage, check the impact on subsequent creations, scaling, or replacements. The Console can show usage higher than the limit when a limit was lowered after resources were created. [Oracle: Viewing a Tenancy's Limits and Usage](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/view-tenancy.htm).

Therefore, before lowering production quotas, account for temporary resources needed during maintenance and recovery. A healthy running environment can still lose the ability to create replacement VMs if headroom is trimmed too tightly.

## 5. Incorporating Quotas into Landing Zone Design

An illustrative structure:

```text
Tenancy
├── SharedServices
├── Applications
│   ├── Production
│   └── NonProduction
│       ├── Development
│       └── Sandbox
└── Recovery
```

Quotas should reflect the operational role of each branch rather than dividing limits equally:

| Branch | Allocation intent | What to protect |
| --- | --- | --- |
| SharedServices | Enough for shared networking, monitoring, and platform services | Application scaling is not blocked by platform resources |
| Production | Covers target load, replacement deployments, and local recovery | Headroom exists when old and new versions run side by side |
| Development | Supports routine work with predictable ceilings | Prevent dev environments from exhausting shared limits |
| Sandbox | Small practice scope with an accountable owner and time limit | Blocking behavior can be verified while costs stay controlled |
| Recovery | Based on calculated recovery requirements | Recovery region and resources are validated independently |

This represents governance intent; it does not mean quotas reserve physical resources for each branch. Organizations must monitor both actual aggregate usage and scenarios that could occur simultaneously.

### Calculating Headroom for a Deployment Wave

Suppose production runs 12 E4 VMs at 4 OCPUs each in the same AD. A blue/green strategy creates all 12 new VMs before tearing down the 12 old VMs:

```text
Running production                      = 12 × 4 = 48 OCPUs
New production running in parallel      = 12 × 4 = 48 OCPUs
Illustrative recovery reserve           =          16 OCPUs
Production quota needed for scenario    =         112 OCPUs
Other compartments in the same scope    =          40 OCPUs
Tenancy total needed for scenario       =         152 OCPUs
```

If the current service limit is 128, setting the production quota to 112 is not enough for the deployment to succeed. As soon as both versions coexist, projected total usage is `48 + 48 + 40 = 136`, which exceeds 128.

The team can propose a new total limit of 160 OCPUs in this case, explaining the 152-OCPU requirement and remaining buffer. At the same time, calculate memory, boot volumes, and accompanying components; 160 OCPUs alone does not resolve other resource dimensions.

If VMs are distributed across multiple ADs, repeat the table per AD. If the deployment strategy only adds a subset of VMs per batch, use that strategy's peak concurrency rather than assuming full doubling.

## 6. Observing via Console and Automating via API

### 6.1. Checking the Exact Limit Row in the Console

In the OCI Console, open **Limits, Quotas and Usage**, select the target region, and filter by service, scope, compartment, and subscription if applicable. Record the technical name, service limit, usage, and available remainder. Not every service or resource displays complete usage details on this screen. [Oracle: Viewing a Tenancy's Limits and Usage](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/view-tenancy.htm).

To avoid selecting the wrong quota, you can start from the matching resource row and use **Create quota policy stub**. Then verify the generated statement against the intended compartment, value, and condition before saving. [Oracle: Overview of Compartment Quotas](https://docs.oracle.com/en-us/iaas/Content/Quotas/Concepts/resourcequotas.htm).

Do not treat the available column on a single row as a guarantee for the whole application. Cross-check parent compartment quotas and the requirements of the entire deployment configuration.

### 6.2. Reading Resource Availability with the OCI CLI

The PowerShell snippet below is an **example for learners to run in their own tenancy** once the OCI CLI and read permissions are configured. Replace all placeholders with real values; do not pass sample AD name strings to the API:

```powershell
$ociTargetRegion = '<region-id>'
$ociSandboxId = '<compartment-ocid>'
$ociTargetAd = '<availability-domain-name-from-your-tenancy>'

oci --region $ociTargetRegion limits resource-availability get --compartment-id $ociSandboxId --service-name compute --limit-name standard-e4-core-count --availability-domain $ociTargetAd
```

`GetResourceAvailability` looks up information by compartment, service, limit, and scope. The AD parameter is required for AD-scoped limits; do not pass an AD uniformly for every limit type. Not all limits support this API; missing data or unsupported responses must be recorded as unknown rather than interpreted as "unlimited." [Oracle: OCI CLI resource-availability get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/limits/resource-availability/get.html).

Limit-based availability is computed from usage, service limits, and applicable quotas; it is not a physical host capacity check. Some fields may be null when a service does not yet expose that data. [Oracle: Resource Availability](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/limits/resource-availability.html).

### 6.3. Separating Observer and Modifier Permissions

You can separate read-only observers from quota administrators. The two statements below illustrate permission to inspect limit definitions/values at tenancy level and read availability in Sandbox:

```text
Allow group LimitsViewers to inspect resource-availability in tenancy
Allow group LimitsViewers to read resource-availability in compartment Sandbox
```

Adjust group references to match your actual identity domain and IAM structure. Permission to read limits is not equivalent to managing quotas or creating Compute resources. [Oracle: Service Limits — Required IAM Policy](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/overview.htm).

Quota administrators require appropriate Quotas service permissions. In a landing zone, assign this responsibility to the platform team and restrict delegation scopes where possible. Allowing a team to edit the very quotas that constrain it must be evaluated against the organization's accountability model. [Oracle: Authentication and Authorization for Quotas](https://docs.oracle.com/en-us/iaas/Content/Quotas/Concepts/resourcequotas_authentication_and_authorization.htm).

### 6.4. Using Limit Checks in Pipelines

A pre-deployment check workflow can execute sequentially:

1. From the planned configuration, calculate the **peak incremental** resource demand, including temporary resources for replacement.
2. Map each requirement to the exact service, limit name, unit, and scope.
3. Collect limits, usage, and effective quotas at the target compartment; explicitly note any fields without data.
4. Compare demand against headroom plus an agreed safety buffer.
5. If insufficient or unknown, surface the specific cause and the accountable owner to resolve it.
6. After deployment, record new usage and reconcile against the estimate.

This is a decision-support check, not a reservation mechanism. Two pipelines can read the same headroom concurrently and both attempt to provision. In shared environments, coordinate large deployment waves; actual allocation outcomes still determine final success.

Alert thresholds should reflect lead time. For instance, alerting when headroom drops below the demand of one full deployment wave can be more actionable than applying a fixed percentage across every resource. Thresholds like 70% or 85%, if used, are organizational operational conventions and must be chosen based on workload and turnaround time.

## 7. Diagnosing Failures Before Requesting a Limit Increase

When a create or scale operation fails, capture the full error message, request ID, timestamp, region, AD, compartment, shape, and requested configuration. Then identify which layer blocked the request:

| Symptom | Check next | Appropriate resolution path |
| --- | --- | --- |
| Unauthorized or resource not visible | Principal, IAM policies, compartment, and access scope | Adjust permissions per accountability |
| Insufficient internal quota | Target quota, related policies, and parent compartment usage | Clean up appropriate resources or adjust internal quota |
| Insufficient service limit | Limit name, scope, subscription, and total corresponding usage | Reduce demand or submit a service limit increase request |
| `Out of host capacity` | Shape, AD, fault domain, and supply availability | Evaluate another configuration or deployment location |
| Throttling | API call rate, retries, and concurrency level | Tune retry/backoff and API call patterns |
| Invalid configuration | Shape, network, storage, and service parameter combinations | Fix configuration based on the error message |

For `Out of host capacity`, Oracle advises considering changing the shape, fault domain, or AD depending on application constraints. Raising a service limit does not add physical hosts to a constrained location. [Oracle: Resolving Out of Host Capacity](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/troubleshooting-out-of-host-capacity.htm).

For example, if TeamA is blocked by `Applications` quota as in Section 3, requesting a tenancy limit increase will not allow the 8-OCPU VM to be created. Conversely, if the team's own quota still has room but the tenancy has hit its limit in that AD, adjusting only the internal quota will not fix it.

Do not use deleting live workload-serving resources as a first troubleshooting step. Before reclaiming anything, verify who owns the resource, which applications depend on it, and whether upcoming deployments still require it.

## 8. Preparing a Service Limit Increase Request

### 8.1. Information for Oracle and Internal Teams to Evaluate Together

A useful request answers three questions: where is the limit hitting, what total is needed, and by when. An operational record can include:

| Item | Illustrative example |
| --- | --- |
| Tenancy and applicable subscription | Environment identifier; subscription if required by resource |
| Service, limit name, unit | Compute; `standard-e4-core-count`; OCPU |
| Region and AD | Exact values for the deployment scope |
| Current limit | 128 OCPUs |
| Current usage | 88 OCPUs at measurement time |
| Desired new total limit | 160 OCPUs, i.e., an increase of 32 over current |
| Peak demand | 152 OCPUs including parallel load and reserve |
| Target date | Expected date, preparation and deployment phases |
| Justification | VM count, OCPUs per VM, deployment strategy, non-production load |
| Point of contact | Lead who can explain the configuration and track the request |
| Dependencies | Memory, storage, networking, and databases to verify in parallel |

The number to enter is the **desired new total value** as defined by the form, not the incremental delta. In this example, `128 → 160` is completely different from requesting an increase to add 160.

Never put API keys, private keys, passwords, or application data into the request justification. Describe workload sizing and configuration specifically enough for review without exposing confidential details.

### 8.2. Request Justification Template

```text
Purpose: Prepare deployment of a new release for the ordering application.
Service/limit: Compute / standard-e4-core-count, unit OCPU.
Scope: <region-id>, <availability-domain-name>.
Subscription: <if applicable>.

Current limit: 128 OCPUs.
Observed usage: 88 OCPUs at <measurement-timestamp>.
Requested new total limit: 160 OCPUs.

Justification:
- Current production runs 12 E4 VMs at 4 OCPUs each: 48 OCPUs.
- Blue/green requires 12 additional VMs with identical config: 48 additional OCPUs.
- Recovery reserve during deployment: 16 OCPUs.
- Other compartments in the same scope consume: 40 OCPUs.
- Projected peak demand: 48 + 48 + 16 + 40 = 152 OCPUs.

Target activation date: <date-and-timezone>.
Post-deployment plan: Decommission old version after stability confirmation.
Point of contact: <accountable-team>.
```

The template ties current numbers to a usage scenario. It does not guarantee Oracle will approve 160 or guarantee corresponding physical capacity.

### 8.3. Submitting and Tracking

In the Console, the **Request a limit increase** workflow lets you enter a justification, add requested items, select service/limit, enter values per scope, and review before submitting. Some resources also require selecting a subscription or providing additional details. Turnaround time can range from minutes to days; do not plan assuming every request is processed instantaneously. [Oracle: Creating a Limit Increase Request](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/create-request.htm).

Organizations should store the request identifier alongside the deployment plan, track each item, and respond if Oracle requests clarification. Request details can be inspected in the Console or via the corresponding API/CLI. [Oracle: Getting Details for a Limit Increase Request](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/get-request.htm).

Submitting a request does not mean the new limit is already active. Once approved, read back the exact value in the tenancy, verify each item, and review internal quotas. Some limits cannot be raised or a request may be declined; always keep a fallback plan to adjust demand or deployment timing. [Oracle: Service Limits](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/overview.htm).

## 9. Controlled Hands-On Practice

Practice in a lab compartment using small resources approved by the owner. This section describes learning exercises; you are not required to hit real production limits or submit real limit increase requests just to complete the lesson.

### Part A — Build an Observation Record

1. Select a target region and AD for practice.
2. Choose a Compute series supported by the tenancy; identify the associated OCPU and memory quotas.
3. Record the service limit, usage, headroom, and quotas for the compartment and relevant parent compartments.
4. Pick one additional dependency such as boot volume and record its unit and scope.
5. Clearly mark any information that could not be retrieved; do not fill it in with default guesses.

The output should explain why a given VM configuration does or does not have sufficient headroom.

### Part B — Verify a Sandbox Quota

1. Calculate upfront the smallest demand needed to run the lab and its estimated cost.
2. An administrator authorized to create quotas records the initial state, then sets a tight quota for the exact resource and scope.
3. Create a configuration within the ceiling and record usage afterward.
4. In the lab, intentionally attempt a small request exceeding the quota; record the rejection reason without widening other permissions.
5. Verify that the error is quota-related rather than concluding based solely on creation failure.
6. Reclaim resources created by the lab according to lifecycle rules, check remaining storage resources, and restore the quota to its recorded initial state.

If provisioning resources is not permitted, complete the exercise using calculations and available observation records. Clearly state which parts were live verification and which were simulated.

### Part C — Draft a Request on Paper

Use the scenario of 128 current OCPUs and 152 peak OCPUs to draft a request raising the total to 160. Explain why the production quota needs 112, why current usage is 88, and why a quota of 112 does not automatically raise the 128 service limit.

Then change the strategy: add only 3 VMs per batch instead of all 12 VMs at once. Recalculate peak OCPUs with explicit assumptions about when old VMs are torn down. Compare the impact on limit demand, deployment duration, and rollback capability.

## 10. Self-Check on Applicability

| Scenario | Conclusion to draw |
| --- | --- |
| Sandbox still has OCPUs but ran out of memory quota | Check limits on every dimension, not just OCPUs |
| Child quota has 12 left, but parent quota only has 4 left | An 8-OCPU VM is blocked by the parent constraint |
| Oracle increased the limit, yet VM creation is still blocked by quota | Reconcile and adjust internal quotas accordingly |
| Both service limit and quota have room, yet host capacity is lacking | Address the capacity issue by shape and placement |
| Budget alert fires for threshold breach | Address spend; a budget alone does not stop resources |
| New deployment must run alongside the old version | Size for peak concurrency rather than steady-state load |
| Primary region has sufficient headroom | Not enough evidence to assume the recovery region also has enough |
| API returns no availability for a limit | Record as unknown and pick a supplementary verification method |

In landing zone operations, maintain an accountable owner for every quota, a cadence for reviewing headroom, a plan for limit increases ahead of scaling waves, and an audit trail of changes. Service limits define the tenancy's ceiling; compartment quotas allocate consumption rights within that ceiling. Combining them with IAM, cost visibility, and capacity planning enables controlled OCI deployments while preserving the ability to replace and recover resources when needed.