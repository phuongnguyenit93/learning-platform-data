# Handling Throttling, Service Limits, and Compute Capacity Shortages

In Oracle Cloud Infrastructure (OCI), a failed VM provisioning request can stem from API call rate, tenancy resource limits, compartment quotas, or available physical hardware at the deployment target. These causes may appear sequentially during a single scaling event, yet they require different responses.

This lesson belongs to the **Operations and Troubleshooting** chapter of the **CLOUD_PROVIDERS_ORACLE** module. The focus is on diagnosing and recovering Compute deployments in a controlled manner, while accounting for IAM permissions, VCN networking, storage, databases, monitoring, and cost. The figures, timeouts, and alert thresholds below are design examples; actual values must be taken from the tenancy and services in operation.

## 1. Learning Outcomes

After this lesson, learners can:

- Read HTTP statuses, error codes, and messages to distinguish throttling, service limits, compartment quotas, and host capacity shortages.
- Inspect the right service, region, availability domain (AD), compartment, and resource units.
- Design retries with backoff, jitter, deadlines, and mechanisms to prevent duplicate resource creation.
- Choose load-shedding, limit-adjustment, or placement/shape changes suited to application constraints.
- Prepare evidence for Oracle Support and verify recovery outcomes using both technical and cost signals.

Basic knowledge of tenancy, compartment, IAM policy, region, AD, fault domain (FD), shape, OCPU, image, subnet, and boot volume is expected. The lab commands use **Bash**, suitable for OCI Cloud Shell or a Bash environment with OCI CLI configured; do not paste multi-line Bash line-continuation syntax directly into PowerShell.

## 2. Distinguish the Four Layers of Constraints

### 2.1. Throttling: Requests Arriving Too Fast

Throttling controls the request rate against a service. A program may not have created any new resources yet still get throttled because it continuously calls list or status-check APIs. OCI describes a typical response as HTTP **429**, code **TooManyRequests**; the mitigation is spacing out calls using exponential backoff. Do not assume all APIs share the same thresholds or enforcement scope. See [REST APIs — Request Throttling](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/usingapi.htm).

For example: 30 pipelines simultaneously checking instances every second can generate high request volume even if the running VM count does not increase. Reducing polling frequency and coordinating pipelines directly addresses the source of this pressure.

### 2.2. Service Limit: Allowed Amount of Resources

A service limit is the allowance Oracle enforces on a resource. You must read the **limit name, unit, and scope**: region-level limits differ from AD-level limits; OCPU counts differ from instance counts; memory capacity differs from volume capacity. Do not treat default values in a documentation table as the guaranteed limit of your tenancy. Actual values depend on account type, subscriptions, and approved adjustments. See [Limits by Service](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/default.htm).

For example: having room for one instance does not mean having 16 OCPUs available for the requested shape. When real demand exceeds allowance, reduce demand, reclaim eligible resources, or request an increase for the exact limit.

### 2.3. Compartment Quota: Internal Allocation

Quota is a governance mechanism for allocating resources across compartments. When checking, consider policies inherited from parent compartments, conditions, and all interacting policies. Within a policy, statement order matters; across multiple policies applying to the same resource, the more restrictive rule takes precedence. Setting a quota higher than the service limit does not raise the service limit. See [Quota Policy Syntax — Evaluation and Precedence](https://docs.oracle.com/en-us/iaas/Content/Quotas/Concepts/quota_policy_syntax.htm).

For example: the tenancy still has resources, but the **dev** compartment has exhausted its allocation. Moving a workload to another compartment solely to bypass quota defeats governance; the quota owner should review allocations against real demand.

### 2.4. Compute Capacity: Whether Physical Hardware Can Fulfill the Request

Host capacity is the ability to place a request onto physical infrastructure. That availability varies by time, shape, and location. A tenancy with sufficient limits may still fail to find a host matching the requested configuration. Oracle recommends evaluating shape, FD, and AD options when encountering capacity shortages. See [Resolving Out of Host Capacity error](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/troubleshooting-out-of-host-capacity.htm).

You can picture a successful deployment needing to satisfy all conditions simultaneously:

~~~text
Valid request authorized by IAM
  + Accepted API call rate
  + Available service limit in the right scope
  + Available effective quota in the compartment
  + Available host capacity for the chosen config and placement
  + Satisfied network, image, and volume dependencies
~~~

These are necessary conditions for diagnostic reasoning, not an internal check order guaranteed by OCI.

## 3. Read the Error Before Choosing an Action

| Symptom | Initial Interpretation | Priority Action |
|---|---|---|
| 429 TooManyRequests | Request rate exceeds what the service accepts | Reduce rate, reduce concurrency, retry with backoff |
| 400 LimitExceeded | Exceeded Oracle's allowance for the resource | Check limit, usage, scope, and increase need |
| 400 QuotaExceeded | Exceeded administrator-defined quota | Identify quota policy and allocation owner |
| InternalError with Out of host capacity message on Compute launch | Cannot place a host for the current request | Check capacity and placement/shape alternatives |
| 401, 403, 404 NotAuthorizedOrNotFound | May relate to authentication, permissions, or identity/target | Check principal, policy, region, and OCID |
| Timeout or other server error | Outcome may be unknown or transient service error | Reconcile state before deciding to retry |

The first three error codes and authorization errors are described in [API Errors](https://docs.oracle.com/en-us/iaas/Content/API/References/apierrors.htm). Specifically for Compute, host capacity shortages can return **InternalError**, noted in [Known Issues for Compute](https://docs.oracle.com/en-us/iaas/Content/Compute/known-issues.htm). Therefore, read **both code and message**; do not classify every 5xx error as out of capacity.

Illustrative response example:

~~~json
{
  "status": 429,
  "code": "TooManyRequests",
  "message": "User-rate limit exceeded.",
  "opc-request-id": "example-request-id"
}
~~~

Do not log only "launch failed": that discards the facts needed to separate root causes. For asynchronous APIs, an accepted response also does not prove the resource is ready; keep tracking resource status and work requests if the operation produces one.

## 4. Diagnostic Workflow During an Incident

~~~mermaid
flowchart TD
    A[Deployment or scaling fails] --> B[Save error and request context]
    B --> C{Classify by code and message}
    C -->|TooManyRequests| D[Throttle rate and retry with limits]
    C -->|LimitExceeded| E[Check limit and usage in exact scope]
    C -->|QuotaExceeded| F[Check effective quota]
    C -->|Out of host capacity| G[Check capacity and alternatives]
    C -->|Other error| H[Investigate IAM, config, or service]
    D --> I[Reconcile resources and app status]
    E --> I
    F --> I
    G --> I
    H --> I
    I --> J{Target service level reached?}
    J -->|No| B
    J -->|Yes| K[Stabilize traffic and document root cause]
~~~

Before changing configuration, record at minimum:

| Fact Group | Content to Save |
|---|---|
| Timing | UTC timestamp, error window, last known success time |
| Identifiers | Tenancy, compartment, region, AD, FD if any, related resource/work request OCIDs |
| Request | API operation, shape, OCPU, memory, image, instance count, capacity type |
| Errors | HTTP status, code, message, opc-request-id of each key call |
| Client | Tool/SDK and version, profile or principal, timeout, retry config |
| Load level | Number of pipelines/workers, polling interval, request rate, retry counts |
| Dependencies | Subnet, volume, database endpoint, and placement constraints |

Share only necessary details through appropriate channels; strip private keys, tokens, and application data from log extracts. Clearly note whether a call returned an OCID so the next responder does not accidentally create another batch of resources.

## 5. Check Limits and Usage with OCI CLI

### 5.1. Prepare Context and Permissions

The values below are placeholders and must be replaced with real values. Choose a profile with appropriate observation permissions; avoid using a tenancy-wide admin account for routine read tasks.

~~~bash
export OCI_CLI_PROFILE='OPS_READONLY'
export TENANCY_OCID='<tenancy-ocid>'
export TARGET_COMPARTMENT_OCID='<workload-compartment-ocid>'
export REGION='<region-identifier>'
export AD='<availability-domain-name>'
~~~

For the Limits API, permissions to view definitions/services/values are evaluated at the tenancy level; checking resource availability requires read permission at the appropriate compartment. Example observation policy for admins to adapt to actual group structure:

~~~text
Allow group LimitsAndUsageViewers to inspect resource-availability in tenancy
Allow group LimitsAndUsageViewers to read resource-availability in compartment AppProd
~~~

These permissions do not grant rights to create instances, edit quotas, or manage capacity reservations. See [Service Limits — Required IAM Policy](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/overview.htm).

### 5.2. Find the Right Service and Limit Definition

List service names supported by the Limits API:

~~~bash
oci limits service list \
  --compartment-id "$TENANCY_OCID" \
  --region "$REGION" \
  --all
~~~

Take the **programmatic name** from the output, then inspect definitions:

~~~bash
export LIMITS_SERVICE='<service-name-from-result>'

oci limits definition list \
  --compartment-id "$TENANCY_OCID" \
  --service-name "$LIMITS_SERVICE" \
  --region "$REGION" \
  --all
~~~

Record the name, description, scope-type, and unit. Check are-quotas-supported if you intend to manage that resource with quotas. Do not guess limit names from commercial shape names. Refer to [service list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/limits/service/list.html) and [definition list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/limits/definition/list.html).

### 5.3. Retrieve Allowance Values

~~~bash
oci limits value list \
  --compartment-id "$TENANCY_OCID" \
  --service-name "$LIMITS_SERVICE" \
  --region "$REGION" \
  --all
~~~

Match the entry with the exact name and scope. When filtering with **--availability-domain**, the command only returns AD-scoped values; do not use that filter and then conclude regional limits have disappeared. See [limits value list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/limits/value/list.html).

### 5.4. Retrieve Usage and Availability at the Target Compartment

For an AD-scoped limit:

~~~bash
export LIMIT_NAME='<exact-limit-name>'

oci limits resource-availability get \
  --compartment-id "$TARGET_COMPARTMENT_OCID" \
  --service-name "$LIMITS_SERVICE" \
  --limit-name "$LIMIT_NAME" \
  --availability-domain "$AD" \
  --region "$REGION"
~~~

If the limit is region-scoped or global, omit the **--availability-domain** parameter. This API does not support every limit; documentation notes it may return 404 when values are unavailable. Distinguish that case from permission or OCID errors before drawing conclusions. See [resource-availability get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/limits/resource-availability/get.html).

**Availability in the Limits API is the remaining allocation permitted by limits/quotas; it is not the number of free physical hosts.** That concept is calculated from usage, service limits, and quotas, as described in [resource-availability](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/limits/resource-availability.html).

If results are confusing, build a comparison table at a single point in time:

~~~text
service | limit-name | unit | scope | usage | limit | available
~~~

Do not treat empty data as 0 or unlimited. When multiple pipelines provision concurrently, just-read data may no longer reflect the state when the next request is processed. Preflight checks help detect projected shortfalls, while actual operation responses show final outcomes.

## 6. Handle Throttling Without Adding Pressure

### 6.1. Reduce Generated Requests

Start at the calling source, even when the SDK already supports retries:

1. Limit the number of pipelines running concurrently in a rollout wave.
2. Use a queue and a bounded worker pool for resource create/update operations.
3. Reduce polling and widen wait intervals while resources remain in-progress.
4. Avoid having multiple workers each query all resources to find the same OCID; share results appropriately and use narrowly scoped queries.
5. Stagger schedules for inventory, sync, and periodic jobs to avoid piling onto the same minute.

Concurrency and request rate are related but distinct. Two workers can still generate a very high call rate if each request completes quickly. You can combine a semaphore capping in-flight requests with a token bucket capping requests started over time. If multiple processes share one allowance, the coordinator must account for their combined load.

### 6.2. Backoff, Jitter, and Retry Budget

Backoff increases the wait interval after consecutive failures. Jitter adds randomness so clients do not wake up and retry simultaneously. The OCI Python SDK presents several strategies, among which equal jitter keeps a minimum wait portion and adds a randomized portion; this is a solid choice to illustrate throttling handling. See [SDK Retry Behaviors](https://docs.oracle.com/en-us/iaas/tools/python/latest/sdk_behaviors/retries.html).

The design example below uses at most 6 calls including the initial call, with a total 120-second deadline. This is pseudocode, not an OCI default configuration:

~~~text
maxAttempts = 6
baseDelay = 2 seconds
maxDelay = 30 seconds
deadline = monotonicNow() + 120 seconds

for attempt in 1..maxAttempts:
    remaining = deadline - monotonicNow()
    if remaining <= 0:
        stop with RETRY_BUDGET_EXHAUSTED

    acquire rate/concurrency permit within remaining time
    recompute remaining time
    if no permit or remaining <= 0:
        stop with RETRY_BUDGET_EXHAUSTED

    result = callOnce(timeout bounded by remaining)
    release concurrency permit

    if result is success:
        return result

    if result is not the intended throttling condition:
        return result to the appropriate handler

    if attempt == maxAttempts:
        return result with ATTEMPTS_EXHAUSTED

    ceiling = min(maxDelay, baseDelay * 2^(attempt - 1))
    delay = ceiling / 2 + random(0, ceiling / 2)

    if a valid server Retry-After hint is present:
        delay = max(delay, parsed server delay)

    if monotonicNow() + delay >= deadline:
        stop with RETRY_BUDGET_EXHAUSTED

    wait interruptibly for delay
~~~

**callOnce** must be understood as a single call at the controlled layer. If the SDK retries internally, either include those calls in the budget or delegate full retry responsibility to the SDK. Do not assume every OCI response includes Retry-After; when present, the client must parse the format accurately. The deadline must encompass permit wait time, request time, and backoff time.

The equal-jitter intervals in the example fall within 1–2, 2–4, 4–8, 8–16, and 15–30 seconds respectively. In practice, a slow request can consume the deadline before reaching the final attempt.

### 6.3. Avoid Retrying at Too Many Layers

Suppose the pipeline retries 3 times, a wrapper retries 3 times, and the SDK retries 3 times for the same operation. In the worst case, up to **3 × 3 × 3 = 27 calls** can be generated for one original intent, if each layer allows 3 total attempts. Designate a single layer to own retries and record metrics for actual call counts.

Do not copy an entire retry policy from another SDK into the current application unchanged. Check the exact language, version, service operation, and enabled settings. For example, [OCI Python SDK Retry API](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/retry.html) distinguishes retry strategies, attempt counts, and time limits; those values do not represent every OCI tool.

### 6.4. Timeout Does Not Mean the Operation Did Not Happen

A resource creation request may have been accepted while the response was lost. Uncontrolled retries can create extra unintended instances or volumes. The workflow should store an application operation ID and link it to the OCID once received.

For operations supporting idempotency tokens, preserve the token across retries of **the same intent and same request payload**, per the API contract. If changing shape or AD, that is a different request requiring separate coordination. If the previous outcome is unclear, reconcile before launching a new plan. Identical display names do not guarantee resource uniqueness.

Principles for retry tokens are described in [REST APIs — Retry Tokens](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/usingapi.htm). Do not treat **opc-request-id**, which traces individual requests, as a duplicate-prevention token.

## 7. Handle Service Limits and Compartment Quotas

### 7.1. Calculate Incremental Demand in the Same Scope

Suppose the operations team wants to add 4 VMs, each using 4 OCPUs and 32 GiB memory. After normalizing metrics to the exact scope of each corresponding limit/quota, we have a hypothetical table:

| Constraint Considered | Ceiling | Used | Remaining | Need for 4 VMs |
|---|---:|---:|---:|---:|
| OCPU service limit in target scope | 64 OCPU | 52 OCPU | 12 OCPU | 16 OCPU |
| OCPU quota in target compartment | 32 OCPU | 24 OCPU | 8 OCPU | 16 OCPU |
| Effective memory allowance considered | 400 GiB | 320 GiB | 80 GiB | 128 GiB |

Based on the constraints in the table:

~~~text
Additional VMs allowed by allowance
  <= min(floor(12 / 4), floor(8 / 4), floor(80 / 32))
  = min(3, 2, 2)
  = 2
~~~

Even 2 VMs is only an upper bound for the allowances examined; you must still verify capacity and dependencies. Do not use this calculation when usages are not in the same scope as their respective ceilings, or when VMs belong to shape families counted against different limits.

### 7.2. When the Error Is LimitExceeded

Proceed in order:

1. Identify the exact resource hitting the limit, including dependent resources. Compute launch can involve boot volumes, IP addresses, and other resources beyond OCPUs.
2. Re-read limits and usage in the exact region/AD; inspect concurrent provisioning waves.
3. Inventory reclaimable resources with their owners. Do not delete a resource just because CPU is low: it may serve as standby or hold state.
4. If design adjustments make sense, shrink the batch or switch to a verified configuration whose separate allowance still has headroom.
5. If valid demand exceeds the ceiling, submit an increase request for the exact limit and monitor until the new value actually takes effect.

In the Console, use the **Limits, Quotas and Usage** page to inspect. The increase request flow is currently documented via **Help → Request a limit increase**; enter justification, select service/limit, target value, and required scope, then review before submitting. Do not assume requests will be approved immediately. See [Creating a Limit Increase Request](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/create-request.htm).

A helpful justification should include:

~~~text
Goal: add worker pool before monthly data processing run.
Location: region and AD corresponding to the limit to increase.
Current state: verified limit, usage, limit name, and unit.
Peak demand: existing load + expansion + rollout overlap.
Requested value: new total target value, not just the delta.
Needed by: deployment milestone and impact if unmet.
Workaround: batch splitting or using existing worker pool.
~~~

After the limit is increased, still check quota and capacity separately. Raising an allowance does not create extra physical hosts in an AD that lacks them.

### 7.3. When the Error Is QuotaExceeded

Have the quota administrator check:

- Which compartment the resource resides in, and whether it counts against a parent compartment's quota.
- Whether other policies apply simultaneously or location-based conditions restrict it.
- Whether usage grew from real demand, orphaned resources, or duplicate retries.
- Whether to increase the compartment's allocation, reclaim unused quota elsewhere, or adjust deployment strategy.

Quota changes must be managed as resource allocation changes: record purpose, new level, cost-bearing team, and review date. Do not patch policies in response to error strings while ignoring impacts on other teams. If infrastructure is managed as code, update the team's source configuration so the next deployment does not overwrite Console edits.

## 8. Handle Compute Capacity Shortages

### 8.1. Check Capacity for the Exact Configuration

A Compute capacity report is a different tool from the Limits API. The report is generated for an AD; the compartment parameter must be the **root compartment**, i.e., the tenancy OCID. Generating the report does not launch VMs and requires IAM permissions for capacity reports. See [compute-capacity-report create](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/compute/compute-capacity-report/create.html).

The example below uses **VM.Standard.E4.Flex** with 2 OCPUs and 32 GiB solely for illustration. Before applying, confirm the shape and configuration fit your region, image, and workload.

~~~bash
cat > shape-availabilities.json <<'JSON'
[
  {
    "instanceShape": "VM.Standard.E4.Flex",
    "instanceShapeConfig": {
      "ocpus": 2,
      "memoryInGBs": 32
    }
  }
]
JSON

oci compute compute-capacity-report create \
  --compartment-id "$TENANCY_OCID" \
  --availability-domain "$AD" \
  --shape-availabilities file://shape-availabilities.json \
  --region "$REGION"
~~~

Key fields to read include **availability-status**, **available-count**, and the corresponding shape configuration. Defined statuses include **AVAILABLE**, **OUT_OF_HOST_CAPACITY**, and **HARDWARE_NOT_SUPPORTED**; available count applies to the queried configuration. See [Capacity Report Shape Availability — Common Types](https://docs.oracle.com/en-us/iaas/Content/pl-sql-sdk/doc/core_t.html).

AVAILABLE is a point-in-time signal and does not reserve capacity for a subsequent launch. Oracle also notes this property when using capacity reports in [OCI Database with PostgreSQL Troubleshooting](https://docs.oracle.com/en-us/iaas/Content/postgresql/troubleshooting.htm). Generate reports at a reasonable cadence; polling the report itself too aggressively also adds API load.

### 8.2. Choose Alternatives Intentionally

| Option | Pre-Check Before Applying | Trade-offs to Monitor |
|---|---|---|
| Remove FD pinning when design permits | Fault distribution requirements and placement rules | Actual instance distribution may shift |
| Choose another FD in the same AD | Placement feasibility and placement dependencies | Fault isolation must be re-verified |
| Use a smaller Flex configuration | Minimum OCPU/memory floors and app performance | May need more instances or accept lower throughput |
| Use another shape family | CPU architecture, image, drivers, limits, and licensing | Cost, performance, and benchmark results change |
| Switch to another AD if region offers multiple | Subnet, volume, image, and data placement | AD-specific dependencies and latency change |
| Switch region per standby plan | Data sync, networking, IAM, endpoints, and residency rules | Recovery time and transfer/storage costs |
| Wait and retry with bounds | Business deadline and current impact | No guarantee of when capacity appears |

Selection order depends on the application. For a stateless Java service, switching to a benchmarked compatible shape may be faster than switching regions. For databases with dedicated volumes and replication mechanisms, coordinate data recovery alongside the application.

Do not remove FD pinning if it is part of fault-distribution requirements without re-evaluating the architecture. Do not assume every region has multiple ADs. Do not automatically switch from x86 to Arm just because capacity is available: JVM, native libraries, container images, and monitoring agents all require compatibility.

### 8.3. Review Networking and Data When Changing Placement

A VM that launches successfully but cannot reach its database is not a satisfactory recovery. Before changing AD or region, check:

- Whether subnets are regional or AD-specific; whether private IPs remain available and valid in the new placement.
- Route tables, NSGs/security lists, DNS, NAT/service gateways, and connectivity paths to other systems.
- Whether the image is available at the target placement and its architecture matches the shape.
- What placement constraints and backup/restore steps apply to boot/block volumes.
- Endpoints, wallets/certificates, secrets, and connection policies to Oracle database services.
- Whether RTO, RPO, latency, and traffic-shift plans still meet requirements.

This is a design review checklist. Database services, Exadata, Autonomous Database, or other managed services have their own placement and recovery procedures; do not apply VM shape/AD change steps directly to all database types.

### 8.4. Capacity Reservations for Advance Preparation

A capacity reservation reserves resources for future use tied to the appropriate AD/configuration. Upon creation, it may fulfill only partially, or even 0 instances if capacity is unavailable; always check the actual allocated count. Unused reserved capacity still incurs charges. Service limits and quotas continue to apply. See [Capacity Reservations](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/reserve-capacity.htm).

For DR plans or major scaling events, the operational workflow should include:

1. Finalize the required application configurations and standby scope.
2. Check allowance, budget, and permissions to use reservations.
3. Create in advance, verify actual allocated count, and test launching against the planned config.
4. Rehearse using the reservation alongside networking, data, and traffic shifting.
5. Track used/unused capacity and adjust as demand evolves.

Reservations must be prepared and validated before the time they are needed. Do not treat requesting a new reservation mid-shortage as a guaranteed immediate fix.

## 9. End-to-End Scenario: One Rollout Hits Three Obstacles

A Java order-processing application runs in compartment **AppProd**. The team wants to add 6 workers before peak hours. Each worker is planned with 4 OCPUs, 32 GiB memory, connecting to an Oracle database via a private endpoint. The numbers below are hypothetical scenario data.

### Stage 1: Pipelines Receive 429

Multiple pipelines poll status and call launch APIs simultaneously. The team temporarily reduces concurrent jobs, puts scaling requests into a queue, lengthens polling intervals, and enables deadline-bounded retries at a single designated layer.

Signs of progress include declining throttling rates and steadier request processing. Do not conclude capacity is sufficient merely because 429 errors stopped.

### Stage 2: After Slowing Down, LimitExceeded Appears

Additional demand is **6 × 4 = 24 OCPUs**, while remaining allowance for the limit in question is only 16 OCPUs. The team confirms limit name, scope, and usage, then checks memory, volumes, and quotas as well.

If remaining constraints permit, they can proceed with an initial batch of at most 4 workers by OCPU count, while requesting a limit increase for the remaining need plus rollout headroom. Choosing a smaller batch must be grounded in the application's minimum throughput; do not assume 4 workers can sustain peak hours.

### Stage 3: Allowance Suffices, but Launch Reports Out of Host Capacity

With the initial config pinned to one FD, the next launch returns an out-of-host-capacity message. The team pulls a capacity report for the target config and evaluates prepared alternatives.

If fault-distribution design allows, the team removes FD pinning for the new batch or switches to a benchmarked compatible shape. Before retrying, they reconcile earlier requests to avoid duplicates. If choosing another AD, they re-verify volumes, subnets, and database connectivity.

### Verify Recovery

Do not use having 6 instances in **RUNNING** state as the sole criterion. Verify that workers registered with the system, health checks pass, database connections work, queue depth drops, and error rates and latency meet targets. Also inventory actual provisioned resources and incremental costs from the attempts.

This scenario demonstrates that resolving one obstacle can expose the next obstacle. Every new error response must be re-classified.

## 10. Monitor to Detect Issues Before Incidents Occur

### 10.1. Client and Infrastructure Layer Signals

| Signal Group | Data to Collect | Decision Supported |
|---|---|---|
| API rate | Request rate, in-flight count, permit wait time | Tune concurrency/rate limiters |
| API errors | HTTP status, error code, operation, region | Select the right handling branch |
| Retries | Actual call count, backoff, deadline exhausted | Detect retry storms or overly long budgets |
| Allowances | Usage, allowance, headroom at corresponding scope | Plan limit/quota increases |
| Deployment | Desired count, actual count, time to ready | Detect scaling falling short of target |
| Capacity | Report results and launch outcomes by config/placement | Evaluate shape/placement alternatives |
| Application | Queue age, throughput, errors, latency, DB connections | Verify real user impact and recovery |

Do not assume a single standard metric captures every API error across all services. Applications/pipelines need client-side telemetry; you can emit custom metrics to OCI Monitoring and logs to OCI Logging per team standards. Audit helps correlate operations and actors, but does not replace client counters for requests, retries, and wait times.

Include full OCIDs/request IDs in logs for investigation, and avoid using them as high-cardinality metric labels. Group metrics by useful dimensions such as operation, service, error code, and region.

### 10.2. Alerts Tied to Scaling Demand

Example operational thresholds for teams to tune:

- Alert when throttling rate exceeds a chosen threshold continuously over a time window.
- Alert when headroom is insufficient for the next rollout batch or loss of a worker group.
- Alert when desired count exceeds actual count beyond the expected scaling duration.
- Alert when requests failing due to retry budget exhaustion rise alongside application queue age.

For a finite limit and same-scope usage:

~~~text
headroom = effectiveAllowance - usage

plannedPeak = steadyState
            + expectedGrowth
            + rolloutOverlap
            + recoveryBuffer
~~~

The plannedPeak formula is a planning model. Sum only components that can coexist in the scenario being calculated; calculate OCPUs, memory, instances, volumes, and dependent resources separately. If a limit has a special value or unsupported data, do not compute usage percentages as if it were an ordinary finite number.

## 11. Automation, Cost, and Stop Conditions

A solid orchestrator has explicit states:

~~~text
PENDING -> CALLING -> SUCCEEDED
                  -> RETRY_WAIT       on matching transient errors
                  -> NEEDS_LIMIT      when service allowance is insufficient
                  -> NEEDS_QUOTA      when internal allocation is insufficient
                  -> NEEDS_CAPACITY   when no host can be placed
                  -> FAILED           when other intervention is needed
~~~

This business state prevents the system from retrying the wrong error class. For NEEDS_LIMIT or NEEDS_QUOTA, park a work record that can resume after confirmed changes; do not let hundreds of workers repeatedly hammer the same blocked request.

Fallback options should be pre-configured per workload, such as primary shape, benchmarked alternate shape, and valid placements. Every option must have an instance cap, time limit, and stop condition. When the deadline expires, return an error with evidence to the operations team; do not continue scaling silently.

On cost, track new instances, retained boot/block volumes, snapshots/backups, IP addresses, and replicated data. A failed launch does not prove zero resources or zero cost were incurred; inventory by operation ID, tags, and OCIDs. Reclaim surplus resources according to the team's lifecycle and governance permissions.

OCI Budgets sets soft spending thresholds and alerts; a budget itself does not block resource creation operations. Combine budgets with quotas and orchestrator caps. See [Budgets](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/budgetsoverview.htm).

## 12. Practice Diagnosis and Result Documentation

This lab prioritizes the read commands in Section 5 and reports in Section 8. Do not try to flood requests to force a tenancy into returning 429, and do not launch masses of VMs to fill limits. Use simulated error responses to practice classification and retry logic; only launch resources when the lab environment has an explicit cost and cleanup plan.

### Step 1: Map Allowances

Select a workload and planned configuration. Record the service name, limit name, unit, scope, limit value, applicable quota, and usage you are authorized to inspect. Mark data unsupported by the API rather than entering 0.

The required output is a table complete enough for someone else to reproduce the headroom calculation in the same context.

### Step 2: Classify Three Simulated Responses

~~~text
A. HTTP 429, code TooManyRequests
B. HTTP 400, code QuotaExceeded
C. code InternalError, message Out of host capacity
~~~

For each response, record missing evidence, responsible owner, and next action. Expected outcome: A leads to rate control; B leads to checking compartment allocation; C leads to checking capacity/placement. Do not use the same unbounded retry loop for all three.

### Step 3: Calculate Peak Demand

Pick a steady-state worker count, rollout delta workers, and required recovery buffer. Calculate peak OCPU/memory and compare against available allowance. State which scope was used for each comparison and which dependencies remain unchecked.

### Step 4: Check a Capacity Option

If authorized, generate a report for an appropriate configuration in the target AD. Record timestamp, shape, OCPU, memory, returned statuses, and interpretation limits of the report. If unauthorized, record the exact error and request observation permissions; do not switch profiles to admin roles outside lab scope.

### Step 5: Draft a Sample Incident Record

~~~text
UTC timestamp and impact level:
Operation and tool/SDK:
Region / AD / FD:
Compartment and principal:
HTTP status / error code / message:
opc-request-id / resource OCID / work request if any:
Shape / OCPU / memory / needed count:
Limit name / scope / usage / allowance:
Checked quotas and capacity:
Tried options, timestamps, and outcomes:
Previous request status clear or still indeterminate:
Recommended action and recovery verification criteria:
~~~

The record meets requirements when a recipient can select the right investigative branch without guessing from "OCI cannot create machines". When Oracle Support is needed, send the relevant evidence bundle with clear impact, and avoid continuing unbounded retries while waiting.

## 13. Confusions to Avoid

| Misconception | Correct Verification |
|---|---|
| "Console shows available so launch will definitely succeed" | Determine whether that is a Limits API allowance or host capacity data |
| "Raising the limit will stop 429s" | Investigate call rate and throttling limits on the affected operation |
| "Tenancy has OCPUs left so any compartment can launch" | Check effective quota in the target compartment |
| "Just switch AD and it's fixed" | Check AD choice, limit scope, networking, and data placement |
| "After timeout, recreate with a new request" | Reconcile the previous request result and idempotency mechanism |
| "SDK retries, so wrapper retrying more is better" | Calculate total combined attempts and pick one owning layer |
| "Capacity report created means capacity is reserved" | Distinguish point-in-time reports from actual allocated reservations |
| "Enough RUNNING instances means recovered" | Verify application serving capability and data dependencies |

When operationalizing a runbook, store valid shape/placement options, peak-load allowances, retry budgets, and recovery criteria alongside the workload configuration. Update those values whenever architecture, demand, or allocation policies change.
