# Load Testing, Fault Injection, and Resilience Verification

A high-availability architecture is only valuable if the application keeps completing work while components fail. On Oracle Cloud Infrastructure (OCI), running multiple Compute instances, placing them across different fault domains, and placing them behind a Load Balancer only sets the preconditions for fault tolerance. To prove the design truly works, you must apply representative load, inject a bounded fault, and compare observed behavior against predefined criteria.

This lesson belongs to the **High Availability Architecture** topic and focuses on verifying OCI-hosted applications with proper permissions, observability, recoverability, and bounded testing cost. The running example is a product catalog API running on two Compute instances behind an OCI Load Balancer. Sections on Oracle Database and storage extend verification to data correctness rather than assuming application-tier tests prove the entire system.

After this lesson, you will be able to:

- Distinguish load testing, stress testing, and fault injection to pick the right experiment.
- Write fault-tolerance hypotheses using user-facing measurable metrics.
- Generate steady traffic, observe failed-backend removal, and verify N-1 capacity when losing an instance.
- Design blast radius, stop conditions, and rollback procedures.
- Collect evidence to state accurately what was actually verified.

## 1. Three Questions to Answer Separately

**Load testing** answers: at a defined load level, does the system meet throughput, latency, and correctness requirements?

**Fault injection** answers: when a specific failure occurs, do detection, isolation, and recovery mechanisms behave as expected?

**Resilience verification** combines both: while continuing to receive representative load, does the system maintain business outcomes and recover within acceptable bounds?

| Test Type | How Conditions Are Applied | What Outcome to Look For |
| --- | --- | --- |
| Smoke test | Very low load for a short duration | Whether scripts, data, auth, and network paths work |
| Load test | Representative or expected peak load | Whether service targets are met at that load |
| Stress test | Stepwise load increases beyond expected capacity | Where targets begin failing and how the system degrades |
| Spike test | Rapid load surge followed by drop | Ability to absorb bursts, queuing, and scaling |
| Soak test | Sustained load over an extended duration | Memory leaks, connection exhaustion, queue buildup, or cost drift |
| Resilience test | Maintain load while breaking a chosen component | User impact, data correctness, detection, and recovery |

Never start by ramping load heavily, blocking networks, and failing over the database simultaneously. When multiple variables change together, pinpointing the cause of failure becomes nearly impossible. Always run a fault-free baseline at the same load first, then change one condition.

A run showing zero errors is still not enough to conclude success: traffic may not have reached the system, the load generator may have throttled itself, or every request may have hit a cache instead of exercising the component under test.

## 2. Test Architecture on OCI and Its Boundaries

Use a dedicated lab compartment in your tenancy, such as `ha-lab`. Hypothetical setup:

- One VCN with controlled administrative access.
- One OCI Load Balancer with an HTTPS listener and one backend set.
- Two Compute instances A and B in a private subnet, both running `catalog-api.service` on port 8080.
- The API does not store mandatory session state in a single instance's local memory.
- Test catalog data resides in a pre-provisioned Oracle Database.
- An independent load generator accesses the exact endpoint users hit.
- Logs and metrics sufficient to correlate requests, backends, and fault events.

~~~mermaid
flowchart LR
    G["Independent load generator"] --> LB["OCI Load Balancer - HTTPS"]
    LB --> A["Compute A - catalog-api"]
    LB --> B["Compute B - catalog-api"]
    A --> DB["Lab Oracle Database"]
    B --> DB
    C["Experiment coordinator"] -. "Reversible service stop" .-> A
    A -. "Logs and metrics" .-> O["Observability and timeline"]
    B -. "Logs and metrics" .-> O
    LB -. "Health and metrics" .-> O
    G -. "Client-side results" .-> O
~~~

OCI regions contain one or more availability domains (ADs); each AD has three fault domains (FDs). Distributing instances across FDs reduces the impact of hardware failures or maintenance within an AD. Verify actual placement of A and B; never infer it from instance names. A multi-FD layout inside one AD still needs another plan if full-AD resilience is required. These placement concepts are described in [Oracle Regions and Availability Domains](https://docs.oracle.com/en-us/iaas/Content/General/Concepts/regions.htm).

In a lab, A and B can sit in two different FDs within one AD. If using multiple ADs, record actual distribution and ensure dependencies also match that goal.

**Stopping the service on A simulates losing only one application backend.** It does not create an FD power outage, AD network partition, or regional outage. Even if A sits in a different AD from B, stopping A does not verify AD-wide shared dependencies.

The database in the diagram is an application dependency, not proof that the data tier has HA. If the database remains a single point of failure, clean Compute-tier results do not eliminate that single point of failure.

## 3. From Service Objectives to Testable Hypotheses

### 3.1. Defining Success in Business Terms

Suppose the lab API exposes:

~~~http
GET /api/catalog
~~~

With the fixed lab dataset, a valid response must return HTTP 200 with JSON containing an `items` array including product `SKU-001`.

~~~json
{
  "items": [
    {
      "id": "SKU-001",
      "name": "Sample product"
    }
  ]
}
~~~

This is an illustrative contract to implement or adapt to your actual API before running scripts. HTTP 200 containing an HTML error page, malformed JSON, or missing seeded data must not count as a successful request.

Definition:

~~~text
Business success rate
  = requests receiving a contract-compliant response
    / total requests actually sent
~~~

The denominator must include timeouts and connection errors for sent requests. Iterations not started by the load generator must be tracked separately because they alter actual applied load.

### 3.2. Example Lab Criteria

The figures below are **illustrative experiment targets**, not OCI SLAs or guaranteed recovery times.

| Aspect | Illustrative Criterion |
| --- | --- |
| Offered load | 200 iterations started per second, each issuing one GET, no retries |
| Steady state | Business success rate >= 99.9% in every 60-second sliding window |
| Steady-state latency | p95 <= 500 ms and p99 <= 1,000 ms in the same windows |
| Transition post-injection | Only during the first 30 seconds post-fault, failure rate <= 1% in each 10-second sliding window |
| Transition latency | p99 <= 2,000 ms during transition windows |
| Failed backend detection | Backend A observed marked unhealthy within 20 seconds max |
| Service recovery | First continuous 30-second interval meeting steady-state criteria begins within 60 seconds post-fault |
| Redundancy restoration | A returns healthy and both backends serve steadily within 180 seconds post-fault |
| Load validity | Zero `dropped_iterations`; load generator not saturated |
| Whole-run aggregate | Business success rate >= 99.9%; aggregate thresholds must also pass |

Evaluate windows using an agreed slide step, such as 1 second, and record that step in the report. Steady-state windows must lie wholly inside their corresponding phase. Windows straddling phase boundaries must be tagged separately; never mix them into steady-state buckets and skew results.

After the 30-second transition, the system must return to steady-state criteria even while A remains stopped. Never stretch the transition window retroactively after observing bad numbers. Whole-run thresholds act as an extra constraint; per-phase checks alone do not guarantee aggregate thresholds pass.

Latency here is measured from just before the client sends a request until the client finishes receiving and validating the response. Track both successful and failed requests; counting only successful responses hides timeouts from latency charts.

### 3.3. Separating Detection, Service Recovery, and Redundancy Restoration

Define milestones:

- `t0`: when the fault actually takes effect.
- `t_detect`: when the health mechanism records backend A as failed.
- `t_good`: start of the first continuous 30-second interval meeting steady-state criteria.
- `t_redundant`: when both A and B are back serving normally.

Then:

~~~text
Detection time = t_detect - t0
Observed service recovery time = t_good - t0
Redundancy restoration time = t_redundant - t0
~~~

`t_good` can only be confirmed after observing the full 30-second window. Report both the start of the good interval and when confirmation completed, avoiding confusion between actual recovery and when an operator noticed it.

RTO is a pre-set recovery objective; measured durations are compared against that target. RPO relates to acceptable data loss on recovery. This GET-only test performs no write transactions and therefore **cannot measure RPO**.

A complete hypothesis can be written as:

> When the service on one backend stops while the system receives 200 requests/second, the Load Balancer removes that backend within the configured detection bound, the surviving backend satisfies steady-state targets, and the restored backend rejoins traffic without causing a fresh wave of errors.

## 4. Verifying Capacity When Losing One Component

Two instances able to handle normal load are not guaranteed to handle load when one instance is lost.

Suppose each instance is measured individually to sustain `C` requests/second at the latency target. With `N` equivalent instances, the preliminary condition to survive losing one instance is:

~~~text
(N - 1) × C >= peak load to serve
~~~

To retain a headroom fraction `h` on surviving capacity:

~~~text
peak load <= (N - 1) × C × (1 - h)
~~~

For example, with two instances each sustaining 300 requests/second and keeping 20% headroom:

~~~text
Remaining capacity with headroom
  = (2 - 1) × 300 × (1 - 0.2)
  = 240 requests/second
~~~

A load of 200 requests/second sits below this preliminary figure. However, the formula assumes equivalent backends and no shared bottlenecks. You must still check database connection pools, Load Balancer connection limits, bandwidth, GC pauses, queues, and storage throughput.

If one AD holds multiple backends, AD-loss sizing must subtract all capacity in that AD, not just one instance. Similarly, a system with many replicas that all share one failing dependency can still go down together.

Autoscaling can add capacity over time, yet cannot replace spare capacity needed immediately when a failure hits. Measure detection lag, instance launch, app startup, and backend registration together. For an initial test, hold instance count fixed to observe N-1 capacity cleanly; record and restore autoscaling settings if the lab modifies them.

## 5. Preparing a Tightly Scoped Experiment

### 5.1. Identities, Resources, and Rollback Path

Before running, record tenancy, region, compartment OCID, Load Balancer OCID, backend set, both instance OCIDs, and private IPs. Display names aid identification only; confirm target resources by exact identifiers.

Separate permissions for load generation, observability, and fault injection. Lab accounts need permissions scoped only to test resources; do not grant tenancy-wide admin rights just to stop a service over an authorized management session.

If automation calls OCI APIs, prefer workload identities appropriate to where it runs. OCI IAM permissions and OS `sudo` privileges are distinct layers: Compute management rights do not automatically grant command execution inside the guest OS, and vice versa.

Prepare additionally:

- Reconcilable synthetic test data; never use live production transactions.
- Pre-experiment configuration backup and a tested recovery path.
- An assigned owner able to abort the test plus a management path that stays usable when the service fails.
- Clock synchronization; use UTC for events and capture elapsed times.
- Verify the load generator is not hosted on the backend being stopped.
- Confirm all backends are healthy, properly configured, and free of background incidents.
- Bound duration, traffic rate, generator count, and retained log volume.

### 5.2. Hypothesis, Stop Conditions, and Rollback

A concise pre-run spec should include:

~~~yaml
experiment_id: oci-ha-001
scope: compartment ha-lab, backend A verified by instance OCID
hypothesis: losing one backend sustains the catalog API at 200 requests/second
fault: stop catalog-api.service on exact backend A
maximum_fault_duration: 120 seconds scheduled, with independent monitoring
stop_conditions:
  - backend B turns unhealthy
  - business failures exceed 5% in two consecutive 10-second windows
  - p99 exceeds 2000 ms in two consecutive 10-second windows
  - corrupt data or impact outside lab detected
rollback: restart service on A and verify readiness, health, and client results
evidence: timeline, client data, backend health, metrics, and logs
~~~

Abort thresholds protect the experiment and differ from pass/fail criteria. Failing a pass criterion can mark the result `FAIL` even if emergency stop conditions were never triggered.

When a stop condition triggers, end fault injection, restore the component, and reduce or stop load if needed. Stopping the load generator does not restore the backend. A complete rollback verifies service status, network paths, Load Balancer state, and client outcomes.

Never use instance termination, volume deletion, or modifying a shared security list for a first experiment. Those actions expand blast radius and can sever the recovery path itself.

## 6. Choosing a Fault Matrix Aligned with Architecture Goals

| Fault to Verify | Bounded Simulation | Key Evidence | Scope Limitations |
| --- | --- | --- | --- |
| Loss of one app backend | Stop only the service on A | Health transition, client errors, B's capacity | Does not represent full host failure |
| Loss of one Compute instance | Stop one lab instance with planned restart | Connection impact, guest and backend recovery | Does not simulate full AD loss |
| Slow dependency responses | Use a stub or test proxy on the chosen dependency path only | Timeouts, retries, circuit breakers, queues | Never alter shared networks to add latency |
| Database unreachable from one backend | Isolate test connectivity for that backend alone | Readiness, business errors, connection pools | Must keep separate management and rollback path |
| Database role switch | Use DB-service-supported operation in isolated lab | Reconnects, new role, transaction reconciliation | Results depend on DB service type and protection mode |
| Degraded storage path | Error stub or dedicated test path for Object/File Storage | Timeout/retry behavior, data consistency | Does not prove real storage service outage |
| Loss of FD/AD backend group | Isolate the entire defined app group | Surviving capacity, shared dependencies | Simulates only the isolated resource group |
| Failover to standby region | Drill DR runbook with standby endpoints and data | RTO, RPO, client routing, correctness | Separate experiment; never inferred from backend-loss lab |

Test each row independently before combining faults. For example, test slow database first, measure retry bounds, and only then consider combining slow database with losing a backend.

For network faults, remember one VNIC can attach multiple NSGs plus a subnet security list. Never assume removing an allow rule in one NSG blocks traffic if another allow rule remains. Prefer proxies or isolated test routes when the goal is simply injecting controlled timeouts.

## 7. Designing Load That Does Not Mask Degradation

### 7.1. Choosing the Load Model

In a closed model with fixed virtual users, each user typically waits for a response before sending the next request. When the system slows down, the generator sends fewer requests. Results can make the system look fine even as throughput collapses.

To test a near-constant arrival rate, use an open model. k6 provides `constant-arrival-rate`: it starts iterations at the configured rate independently of response time as long as virtual users (VUs) remain available. Never add `sleep()` at the end of iterations to throttle this executor. See [Grafana k6 constant-arrival-rate](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/constant-arrival-rate/).

One iteration equals one request only if the script actually sends one request. Retries, redirects, or multiple steps per iteration decouple requests/second from iterations/second.

Estimating concurrent in-flight iterations:

~~~text
Concurrent iterations ≈ arrival rate × iteration duration

200 requests/second × 0.5 seconds ≈ 100 concurrent iterations
~~~

This is an estimate for sizing VUs, not a default optimal setting. Allocate enough VUs to sustain offered load even when timeouts stretch, and verify the generator host has ample CPU, memory, sockets, and bandwidth.

If no VUs are available, the executor cannot start enough iterations. k6 reports this as `dropped_iterations`; causes include generator sizing or rising system response times. Monitor this metric alongside generator resources and target telemetry. See [Dropped iterations documentation](https://grafana.com/docs/k6/latest/using-k6/scenarios/concepts/dropped-iterations/).

### 7.2. Catalog Read Script in k6

The script below targets a lab implementing the API contract in section 3. Save it as `ha-read.js` in the practice environment. As authored in this lesson, commands are learner examples, not outputs from a live execution.

~~~javascript
import http from 'k6/http';
import { check } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const requestOk = new Rate('request_ok');
const clientElapsed = new Trend('client_elapsed_ms', true);

const baseUrl = (__ENV.BASE_URL || '').replace(/\/$/, '');
const runId = __ENV.RUN_ID;
const rate = Number(__ENV.RATE || 200);
const duration = __ENV.DURATION || '10m';

if (!baseUrl || !runId) {
  throw new Error('BASE_URL and RUN_ID must be set for the lab environment.');
}
if (!Number.isInteger(rate) || rate <= 0) {
  throw new Error('RATE must be a positive integer.');
}

http.setResponseCallback(http.expectedStatuses(200));

export const options = {
  maxRedirects: 0,
  tags: {
    run_id: runId,
  },
  scenarios: {
    catalog: {
      executor: 'constant-arrival-rate',
      rate: rate,
      timeUnit: '1s',
      duration: duration,
      preAllocatedVUs: 300,
      maxVUs: 1000,
      gracefulStop: '30s',
    },
  },
  thresholds: {
    request_ok: ['rate>=0.999'],
    http_req_failed: ['rate<=0.001'],
    client_elapsed_ms: ['p(95)<=500', 'p(99)<=1000'],
    dropped_iterations: ['count==0'],
  },
  summaryTrendStats: ['avg', 'p(95)', 'p(99)', 'max'],
};

export default function () {
  const startedAt = Date.now();
  const response = http.get(baseUrl + '/api/catalog', {
    timeout: '3s',
    headers: {
      Accept: 'application/json',
      'X-Test-Run': runId,
    },
    tags: {
      name: 'GET /api/catalog',
    },
  });

  let validBody = false;
  if (response.status === 200) {
    try {
      const body = response.json();
      validBody =
        body !== null &&
        Array.isArray(body.items) &&
        body.items.some((item) => item && item.id === 'SKU-001');
    } catch (_) {
      validBody = false;
    }
  }

  const ok = response.status === 200 && validBody;
  clientElapsed.add(Date.now() - startedAt);
  requestOk.add(ok);

  check(response, {
    'HTTP 200 and catalog matches lab data': () => ok,
  });
}
~~~

`request_ok` records one outcome per iteration, making it clean as a business success rate. `http_req_failed` helps spot HTTP or transport errors; it does not replace JSON body validation. Built-in metrics and failure rules are documented in [k6 Metrics Reference](https://grafana.com/docs/k6/latest/using-k6/metrics/reference/).

`client_elapsed_ms` measures elapsed time wrapping the client call and response validation. It is broader than `http_req_duration`, which excludes full client-side overhead such as connection setup. Threshold units in the script are milliseconds.

Thresholds in `options.thresholds` evaluate whole-run aggregates. They are part of the criteria and do not automatically check sliding windows or recovery timestamps from section 3. `check()` also needs a matching threshold if checks are meant to fail the run. See [k6 Thresholds documentation](https://grafana.com/docs/k6/latest/using-k6/thresholds/).

This script sets no `abortOnFail` and does not control backend rollback. An operator or separate orchestrator must monitor sliding-window stop conditions. Never rely on k6 exiting to assume the fault has been cleared.

### 7.3. Running Smoke, Baseline, and Fault Runs

These Bash examples run on a Linux load generator with k6 installed. Replace `.invalid` domains with a lab endpoint carrying a valid certificate; never skip TLS verification to make a test pass.

~~~bash
export BASE_URL='https://catalog-ha-lab.example.invalid'
export RUN_ID='oci-ha-001-smoke'
export RATE='2'
export DURATION='30s'
k6 run ha-read.js
~~~

After smoke passes, run the baseline at target load:

~~~bash
export RUN_ID='oci-ha-001-baseline'
export RATE='200'
export DURATION='5m'
k6 run --out json=oci-ha-001-baseline.json ha-read.js
~~~

Run the fault-injection run only after the baseline passes, offered load matches target, and no unexplained issues appear:

~~~bash
export RUN_ID='oci-ha-001-fault'
export RATE='200'
export DURATION='10m'
k6 run --out json=oci-ha-001-fault.json ha-read.js
~~~

Use `X-Test-Run` in access logs to separate runs; the `run_id` tag in k6 groups client-side data. Never put tokens, passwords, or sensitive data into correlation headers.

JSON outputs can grow large. Plan disk space, retention, and evidence storage before running. Record k6 version, script version, and config; when raising `RATE` significantly, re-evaluate VUs and generator capacity.

## 8. Observing Simultaneously from Client, Load Balancer, and Backends

A CPU chart alone cannot validate fault tolerance. You need at least three perspectives:

| Source | What to Collect | Question Answered |
| --- | --- | --- |
| Load generator client | Iterations started, business successes, errors, latency, dropped iterations | Were users impacted and was target load sustained? |
| Load Balancer | Backend health, timeouts, response codes, connection counts | How were failed backends removed and restored? |
| Compute and app | CPU, memory, GC, threads, connection pools, error logs | Did the surviving backend saturate or cascade errors? |
| Database/storage | Connections, latency, errors, queues, replication lag if any | Did shared dependencies become the bottleneck? |
| Coordination | Fault injection timestamp, rollback, alert delivery | Did operational mechanisms meet timing requirements? |

For OCI Load Balancer, the metric namespace is `oci_lbaas`. Relevant metrics include `unhealthyBackendServers`, `backendTimeouts`, and `httpResponses5xx`; select the exact resource, backend set, and dimensions when querying. Oracle publishes Load Balancer metrics on a 60-second cadence. Therefore, a one-minute aggregate chart cannot precisely prove an outage lasting only a few seconds; pair it with client data and timestamped logs. See [Load Balancer Metrics](https://docs.oracle.com/en-us/iaas/Content/Balance/Reference/loadbalancermetrics.htm).

OCI Monitoring lets you query metrics and create alarms routed to targets like Notifications topics. Resource metrics, custom metrics, and alarm conditions must be prepared beforehand. Verify notification delivery endpoints too, not just alarm state in the Console. See [Overview of Monitoring](https://docs.oracle.com/en-us/iaas/Content/Monitoring/Concepts/monitoringoverview.htm).

Distinguish three timestamps: when the backend began failing, when the health checker detected it, and when operators received the alert. An alarm with a long evaluation window can fire later than traffic rerouting without implying the Load Balancer detected slowly.

In the app, log backend identifier, request ID, and test run ID. OCI control-plane APIs and `systemctl` commands inside the guest OS do not share the same audit log source; guest commands need their own operational trail. Never assume guest actions automatically show up as OCI API events.

## 9. Reversible Fault Injection: Stopping One Service on Backend A

### 9.1. Verify Health Checks Before Injecting Faults

OCI Load Balancer probes backends per backend set policy using TCP or HTTP. With HTTP, it checks URI, status code, and response body. Unhealthy backends are temporarily removed from distribution; backends passing checks again return to service. See [Health Check Policies for Load Balancers](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/load_balancer_health_management.htm).

In the lab, configure an HTTP `/ready` check on the application port. This endpoint must reflect minimum required serving capability rather than always returning 200 from a static page.

Do not cram every optional dependency check into readiness. If a minor slow dependency makes all backends drop readiness together, health checks amplify the outage. Separate process liveness from serving readiness and external business checks.

Record interval, timeout, and retry counts. Never treat `interval × retries` as a guaranteed failover SLA: failure timing relative to the next probe, timeouts, and existing open connections all affect measured recovery.

### 9.2. Illustrative Run Schedule

A 10-minute fault load run:

| Elapsed Run Time | Activity |
| --- | --- |
| 0–120 seconds | Hold 200 requests/second; confirm both backends are steady |
| Around second 120 | Schedule rollback timer, confirm timer active, then stop service on A |
| From fault onset | Record `t0`, observe detection, traffic shift, and B's serving capacity |
| ~120 seconds after scheduling | Timer restarts service on A; operator may roll back sooner |
| Once A is active | Confirm readiness, backend health, load distribution, and client results |
| Until second 600 | Keep observing post-recovery steady state, then finish load |

The 120-second fault window measures capacity with only B serving; it is not an allowed outage window. Business recovery should happen while A is still down.

### 9.3. Example Commands on Exact Backend A

These commands assume a Linux guest with systemd, service `catalog-api.service`, and `systemctl` at `/usr/bin/systemctl`. Verify these assumptions in the lab. Execute inside a management session on **exact instance A**, verified against its OCID and private IP.

Schedule recovery before stopping the service. Use a unique unit name per run to avoid colliding with old timers.

~~~bash
set -eu

date -u '+%Y-%m-%dT%H:%M:%SZ'
hostname
sudo systemctl is-active catalog-api.service
curl --fail --max-time 3 http://127.0.0.1:8080/ready

sudo systemd-run --unit=oci-ha-001-rollback --on-active=120s --timer-property=AccuracySec=1s /usr/bin/systemctl start catalog-api.service
sudo systemctl is-active --quiet oci-ha-001-rollback.timer

date -u '+%Y-%m-%dT%H:%M:%SZ'
sudo systemctl stop catalog-api.service
date -u '+%Y-%m-%dT%H:%M:%SZ'
~~~

If creating or verifying the timer fails, `set -e` aborts the script before stopping the service. Separately verify the management path and `start` command can restore the app; the timer existing does not prove rollback will succeed.

`systemd-run` creates a transient timer invoking a service upon expiry, as described in [systemd-run documentation](https://www.freedesktop.org/software/systemd/man/latest/systemd-run.html). Because the schedule runs on host A, it still fires if SSH drops, yet offers no protection if host A or systemd dies. That is why this example stops only the service, not the whole host.

Exact timer firing also depends on the OS scheduler and host load; an observer must intervene if the deadline passes without recovery. When testing full-instance stops, use an external rollback mechanism outside the guest.

`systemctl stop` normally allows graceful shutdown per service configuration. Thus this test validates controlled service loss, not sudden process crashes or kernel hangs. Testing those failure modes requires separate experiments and external recovery.

Capture the actual instant the service stops serving via logs or probes; the two timestamps bracketing the command only bound the event. Never treat the moment an operator hits Enter as exact fault time when stop takes time to drain.

### 9.4. Rollback and Post-Recovery Verification

If a stop condition triggers or you wish to restore early, run on A:

~~~bash
sudo systemctl start catalog-api.service
sudo systemctl is-active catalog-api.service
curl --fail --max-time 3 http://127.0.0.1:8080/ready
~~~

Next, confirm via the Load Balancer that A returns healthy, logs show A receiving requests, and clients continue meeting thresholds. `systemctl` reporting active does not replace verifying readiness or business outcomes.

Once rollback is confirmed complete and the timer has not yet fired, cancel the pending timer:

~~~bash
sudo systemctl stop oci-ha-001-rollback.timer
~~~

If the timer already fired, inspect its unit status and journal instead of blindly recreating a timer with the same name. End the experiment only when configuration, backend counts, redundancy, and management paths have returned to expected state.

## 10. Reading Results via Timeline and Windows

### 10.1. An Illustrative Result Example

The table below uses hypothetical numbers to practice interpretation, not OCI measurements or live command outputs.

| Elapsed Run Second | Hypothetical Observation |
| --- | --- |
| 120 | Service A actually stops serving; recorded as `t0` |
| 131 | Backend A transitions to unhealthy |
| 139 | Start of first interval where client metrics return to steady-state criteria |
| 169 | 30 continuous seconds completed confirming good interval starting at second 139 |
| 240 | Rollback timer calls start on service A |
| 247 | Readiness passes on A |
| 253 | A returns healthy and receives traffic; recorded as `t_redundant` |
| 600 | Load duration ends; wait for in-flight requests to finish |

Derived timings:

~~~text
Backend fault detection: 131 - 120 = 11 seconds
Service recovery: 139 - 120 = 19 seconds
Recovery interval confirmed: 169 - 120 = 49 seconds post-fault
Redundancy restoration: 253 - 120 = 133 seconds
~~~

Suppose 120,000 requests were sent, 18 failed business validation, with zero dropped iterations:

~~~text
Failure rate = 18 / 120,000 = 0.015%
Success rate = 99.985%
~~~

The whole-run rate exceeds 99.9%, yet that alone is insufficient to conclude `PASS`. Still check:

- Whether the worst 10-second window during transition stayed within the 1% threshold.
- Whether steady-state windows with only B serving met success rate, p95, and p99.
- Whether A rejoining triggered extra errors, connection spikes, or database slowdowns.
- Whether script aggregate thresholds passed and actual offered rate stayed at 200 iterations/second.

For instance, if 12 out of 2,000 requests failed in the worst transition window, the rate is 0.6%, within the illustrative bound. If instead 40 failed in that window, the 2% rate marks the test `FAIL` even if the whole-run average looks good.

### 10.2. Processing Raw Data

From client timestamp logs, bucket results into defined windows and phases. For each window, compute at least:

~~~text
iterations started
completed and failed requests
business success rate
p95 and p99 latency
dropped iterations
~~~

For timeouts, a request completes only when the timeout expires. Agree upfront whether to bucket by start timestamp or end timestamp and state that choice explicitly. Bucketing by start time ties requests to the phase where they hit the fault, though you must wait for in-flight requests to finish before closing that window.

k6 metric outputs primarily record emission timestamps. If exact start-time bucketing is required, record start times explicitly or cross-check request logs; never assume every metric timestamp equals request send time.

Never compute a phase's p95 by averaging smaller windows' p95s. Compute percentiles over the raw observations of that dataset, or use histograms with mathematically valid aggregation.

If timing evidence is missing, the load generator saturated, or offered load fell short, mark conclusions requiring that evidence **INCONCLUSIVE**. Never flip it to `PASS` merely because few errors were seen.

### 10.3. Common Result Patterns

| Signal | Possibilities to Investigate | Remediation |
| --- | --- | --- |
| Backend A failed yet still receives many requests | Health check missed it or check config does not reflect service | Inspect probes, ports, URI, timeouts, and backend logs |
| A removed yet B's latency spikes sharply | Insufficient N-1 capacity or shared dependency bottleneck | Measure B and DB; resize capacity or bound resources |
| Client load drops when fault appears | Closed load model or generator lacked VUs/resources | Check started iterations, dropped iterations, and generator host |
| HTTP 200 yet business logic fails | Shallow health check or response validation | Add contract and data reconciliation checks |
| A turns healthy then flaps | Startup incomplete, cold cache, or unstable dependency | Improve readiness and gradual traffic re-admission |
| Retries surge and database stalls | Multi-layer retries amplifying load | Set retry budgets, timeouts, and concurrency limits |
| Alerts never arrived | Misconfigured Notifications target, alarm, or permissions | Trace alert pipeline end-to-end to receivers |
| Errors hit only long-lived connections | Existing connections unaffected by new-request routing | Test WebSockets, streaming, or long sessions separately |

## 11. Extending to Write Transactions and Oracle Database

A GET API demonstrates catalog read survival when a backend drops. It does not prove orders, payments, or inventory updates stay accurate across timeouts or database role transitions.

For write transactions, add a dedicated verification contract:

1. Each operation carries a unique business ID and idempotency key.
2. The generator persists a reconciliation ledger outside the components under fault.
3. Distinguish confirmed successes, explicit failures, and indeterminate outcomes.
4. Post-recovery, query by business ID to reconcile actual state.
5. Check for duplicate records, missing records, and business invariants such as non-negative stock.

A client timeout does not mean the database rolled back. The transaction may have committed while the response dropped. Resending with a new ID causes the test itself to create duplicates. Retries must keep the same identifier and the app must enforce proper idempotency.

To evaluate data loss, reconcile transactions confirmed before the fault against post-recovery state using reliable timestamps or sequences. Matching total row counts is not enough: one missing order plus one duplicated order leaves the total unchanged.

When using Oracle Data Guard or Autonomous Data Guard, distinguish **planned switchover** from **failover upon primary failure**. Autonomous Data Guard docs describe switchover swapping primary/standby roles with zero data loss. Meanwhile, Base Database failover docs warn that potential data loss depends on protection mode. Never extrapolate a successful switchover into an RPO = 0 guarantee for every failover. Refer to [Autonomous Data Guard Switchover and Failover](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/autonomous-data-guard-switchover-failover.html) and [OCI CLI: failover-data-guard](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/db/database/failover-data-guard.html).

In dedicated database tests, explicitly document service type, replication config, observed lag, role-switch command, and app reconnect behavior. Never use a generic failover command assumed to fit every Oracle service.

Restoring the old database after failover is also not as simple as turning it back into primary. Follow that configuration's runbook to verify roles, prevent dual writers, and re-establish replication before claiming restored redundancy.

With Object Storage or File Storage, test interrupted uploads, retries, and cases where the database saved a reference before the object upload completed. Having a data replica alone does not prove cross-system operations are atomic.

## 12. Automating Experiments and Controlling Cost

Once manual experiments are well understood, convert them into a guarded workflow:

~~~text
Verify resources and permissions
  -> Confirm steady-state health
  -> Run baseline
  -> Arm independent rollback mechanism
  -> Apply load and inject single fault
  -> Monitor stop conditions
  -> Roll back in finally block
  -> Verify app and redundancy restored
  -> Collect evidence
  -> Evaluate and clean up lab resources
~~~

In automated pipelines, the `finally` branch must run even when the load tool errors or evaluation fails. Still, a terminated runner cannot execute `finally`; an independent external rollback mechanism remains mandatory. For OCI resources, use explicit allowlists and verify OCIDs rather than matching by fuzzy display-name substrings.

Enforce hard caps on duration, `RATE`, generator hosts, VUs, and scalable resource limits. Those guardrails protect both test validity and budget.

Cost drivers to account for include app and generator Compute, Load Balancers, databases or standbys, storage, logs/metrics, recovery copies, and network transfer across involved paths. Never assume HA lab resources stay inside free tiers.

Keep infrastructure definitions reproducible and tag resources with owners and experiment IDs for cost tracking. Afterward, check leftover volumes, backups, logs, and auxiliary resources; stopping an instance does not stop charges on all attached resources.

Automation must snapshot pre-test config and verify post-rollback state. A pipeline checking only k6's exit code misses cases where the test passed yet backend A was never restored.

## 13. Reporting Results So Others Can Audit

An experiment report should clearly state:

- **Objective:** hypothesis, fault type, and actual blast radius.
- **Environment:** region, AD/FD placement, resource IDs, app version, and relevant config.
- **Load:** model, iterations/second, duration, dataset, retries, timeouts, and generator source.
- **Criteria:** per-phase thresholds, windows, slide steps, stop conditions, and recovery targets.
- **Timeline:** fault onset, detection, recovery interval, rollback, and redundancy restoration.
- **Evidence:** client data, metric queries, logs, backend states, and write reconciliation if applicable.
- **Outcome:** `PASS`, `FAIL`, or `INCONCLUSIVE` per hypothesis, with reasoning and limitations.
- **End state:** restored backends and configs, remaining resources, and follow-up actions.

Example conclusion properly scoped to the lesson:

> At 200 requests/second with the described dataset, the system met all criteria during a controlled service stop on one backend. The surviving backend sustained traffic, and the restored backend rejoined rotation within preset bounds. Results do not cover host crashes, AD loss, regional outages, or write-transaction integrity.

If a criterion fails, tie measurements directly back to the hypothesis: e.g., B lacked N-1 capacity, health checks missed readiness, or retries saturated the database. If offered load fell short, telemetry was missing, or fault occurrence could not be confirmed, state clearly which conditions remain unproven.

The value of verification lies in connecting **a concrete fault → architectural response → business impact → recovery evidence**. Repeat after significant changes to code, configuration, placement, or dependencies, keeping baseline conditions consistent to catch regressions.
