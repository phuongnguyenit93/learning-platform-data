# Coordinating Probe Period, Timeout, and Failure Thresholds with Startup Time

## 1. The Problem: Is the Application Starting Slowly or Broken?

A Spring Boot application can take time to create beans, open the HTTP server, run migrations, and load initial data. During that interval, connections to check endpoints may be refused or not yet report ready. If the platform treats every failed check as a reason to restart immediately, the application can be killed before finishing initialization and repeat that cycle indefinitely.

Conversely, stretching every threshold just to get past a slow startup can leave a hung process running far too long after normal serving has begun. Therefore, design three separate decisions:

| Probe type | Question to answer | Action when failures reach threshold |
| --- | --- | --- |
| `startupProbe` | Has the application reached the chosen startup milestone? | Kubelet stops the container; restarting follows the restart policy |
| `livenessProbe` | Is the process still in a state able to keep running? | Kubelet stops the container; with a Deployment, the container is typically restarted |
| `readinessProbe` | Should this replica receive requests via the Service right now? | Container keeps running, but is not considered ready to receive normal Service traffic |

When a startup probe is present, kubelet does not run liveness or readiness probes until the startup probe succeeds. The startup probe finishes its role after that first success; it does not keep monitoring throughout the container's lifetime. Liveness and readiness then operate independently: readiness failing does not automatically pause liveness checks.

These roles are described in the [Kubernetes probe documentation](https://kubernetes.io/docs/concepts/workloads/pods/probes/).

In this lesson, **Actuator provides the health signals; kubelet decides the check schedule and actions**. Editing Spring Boot's YAML does not automatically alter probe schedules in Kubernetes.

## 2. Understand Each Parameter Before Combining Them

The fields below belong to each probe configuration in a Kubernetes manifest. Time units are in seconds.

| Field | Practical meaning | Default value |
| --- | --- | --- |
| `initialDelaySeconds` | Delay before starting checks | `0` |
| `periodSeconds` | Expected interval between checks | `10` |
| `timeoutSeconds` | Maximum time to wait for one check before timing out | `1` |
| `failureThreshold` | Consecutive failures required to mark the probe failed | `3` |
| `successThreshold` | Consecutive successes required to mark the probe healthy after failure | `1` |

`periodSeconds`, `timeoutSeconds`, `failureThreshold`, and `successThreshold` have a minimum value of `1`; `initialDelaySeconds` can be `0`. For liveness and startup, `successThreshold` must be `1`. Readiness can use a higher value to require steadier recovery. See [Probe definition in the Kubernetes API](https://kubernetes.io/docs/reference/kubernetes-api/core/pod-v1/#Probe).

### 2.1. Timeout Is the Limit for One Check

For example, `timeoutSeconds: 2` means a single probe request cannot wait forever. It does not give the entire startup process two seconds, nor does it mean the container restarts every two seconds.

Two failure modes have different durations:

- Connection refused or endpoint immediately returns HTTP 503: the check can fail very quickly.
- Connection opens but endpoint does not respond: the check may have to wait until timeout.

Therefore, the same period and failure threshold can reach the threshold at different times.

HTTP probes evaluate the HTTP outcome, not the `status` field inside JSON, to make their decision. The endpoint must return an HTTP code matching the health status; do not turn every response into HTTP 200 and expect kubelet to inspect the body.

### 2.2. Failure Threshold Counts a Consecutive Streak

With `failureThreshold: 3`, the sequence below hits the threshold only on the final attempt:

```text
Result:               fail  fail  pass  fail  fail  fail
Consecutive failures:   1     2     0     1     2     3
```

It does not sum all failures since application startup. A single success resets the consecutive failure streak.

For readiness, `successThreshold: 2` helps avoid putting a replica back into service immediately after a single successful check. In exchange, the time to return to ready increases. Balance stability against quickly restoring serving capacity.

### 2.3. Shorter Periods Produce More Samples, Not Faster Endpoints

Reducing `periodSeconds` can detect changes sooner, but increases the number of check requests. If an endpoint runs heavy queries, frequent probing adds extra load precisely when the system is short on resources.

With 50 replicas, each with a 10-second liveness period and 5-second readiness period, the steady-state check rate is roughly:

```text
50 × (1/10 + 1/5) = 15 check requests/second
```

This is an illustrative load estimate. When not Ready, readiness may be polled outside the normal cadence to detect recovery earlier. Do not treat the period as an absolute wall-clock schedule.

## 3. Choosing the Right Startup Milestone in Spring Boot

For a web application with Actuator and probe support enabled, the two commonly used addresses are:

```text
/actuator/health/liveness
/actuator/health/readiness
```

You can enable them explicitly with `management.endpoint.health.probes.enabled=true`. If Actuator uses a separate management port, `management.endpoint.health.probes.add-additional-paths=true` also exposes `/livez` and `/readyz` on the main application port. That sends checks through the HTTP infrastructure serving the application. See [Spring Boot 3.3 — Kubernetes Probes](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes).

Distinguish two milestones:

1. **Liveness can return success:** the application context has initialized and the endpoint can be called.
2. **Readiness can return success:** the application has completed startup work required before receiving traffic.

In the standard lifecycle, Spring Boot considers the application ready after `ApplicationRunner` and `CommandLineRunner` beans finish. Thus, a long runner can create a substantial gap between the two milestones. If you offload mandatory work to a background thread so the runner returns early, manage the readiness signal yourself; the platform has no automatic way to know that background work is still missing. Refer to [Spring Boot — Application Availability](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.application-availability).

### 3.1. How Far Does a Startup Probe Using Liveness Protect?

If the startup probe calls `/livez`, it protects until the first time `/livez` succeeds. It **does not guarantee all data-loading steps have finished**. After that point, readiness can keep failing and blocking traffic.

Constructed example:

```text
Container starts                    t =   0 s
/livez starts returning success     t =  95 s
Runner completes; /readyz succeeds  t = 130 s
```

A startup probe calling `/livez` can finish around second 95, depending on probe timing. From then on liveness is active, while readiness keeps the replica unready until around second 130 or later depending on observation timing.

If the runner after second 95 saturates resources so heavily that `/livez` keeps timing out, the startup probe has already ended and no longer protects it. Address the resource contention, tune the check, or choose a better startup signal.

### 3.2. Should Readiness Be Used for the Startup Probe?

You can choose the readiness endpoint for the startup probe if you want the startup deadline to include business initialization. However, prolonged unreadiness then becomes a reason to stop the container.

Before choosing this, ask: "Will restarting the replica help satisfy this condition?" If readiness depends on a shared database that is down, every replica can enter a continuous restart loop without fixing the root cause.

A clean design uses the startup signal for local initialization that can complete, readiness for traffic-acceptance capability, and liveness for continued operability. Do not arbitrarily add every external dependency check to liveness or substitute overall aggregated health for the chosen signal.

## 4. Calculating Intervals: Starting from a Model with Assumptions

Notation:

- `P`: `periodSeconds`.
- `T`: `timeoutSeconds`.
- `F`: `failureThreshold`.
- `t0`: start time of the first check in a failure streak.
- `d`: duration of the final check, from near 0 up to about `T`.

If checks start evenly spaced by `P`, experience no scheduling delay, and each check takes less than one period, the detection time in the model is:

```text
t_detect ≈ t0 + (F - 1) × P + d
```

This is derived from an idealized schedule, not a real-time guarantee from Kubernetes. Node load, probe execution time, kubelet scheduling, and failure type can alter actual timing.

### 4.1. Same Configuration, Fast Failure vs. Timeout Give Different Timings

Suppose `P = 10`, `T = 2`, `F = 3`; the first failure starts at second 100:

| Check | Model start time | If 503 returns immediately | If unresponsive |
| --- | --- | --- | --- |
| 1 | 100 s | Fails near 100 s | Times out near 102 s |
| 2 | 110 s | Fails near 110 s | Times out near 112 s |
| 3 | 120 s | Hits threshold near 120 s | Hits threshold near 122 s |

The span from the start of the first failure to hitting the threshold is roughly 20 or 22 seconds in these two scenarios.

If a fault begins right after a successful check, you also wait nearly one full period before the first failing sample. With continuous failure and an even schedule as above, detection latency from fault onset is roughly:

```text
Immediate-response failure: 20 to 30 seconds
Always-timeout failure:     22 to 32 seconds
```

These ranges belong to the idealized model. Do not treat them as hard bounds for guaranteeing recovery time.

### 4.2. Why Is F × P Often Used to Estimate?

`F × P` is a quick way to approximate the nominal failure-tolerance window. Kubernetes also uses this product when illustrating startup probes for slow-starting applications. See [guide to protecting slow-starting containers](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/#protect-slow-starting-containers-with-startup-probes).

However, in the sample model starting at `t0`, there are only `F - 1` intervals between `F` checks. Therefore:

- Do not treat `F × P` as the exact timestamp at which the container is guaranteed to be stopped.
- Do not mechanically add `T` to every period as `F × (P + T)`.
- Do not use `F × T` as total tolerance time because that calculation ignores the intervals between checks.
- If `T` exceeds `P`, the evenly spaced start model may no longer hold; examine actual scheduling.

When designing, leave safety margin and verify on a real cluster rather than sizing expected startup tightly against a multiplication result.

### 4.3. Failure Detection Differs from Service Recovery

After liveness hits its threshold, the system can still spend time stopping the application, waiting through restart backoff, starting a new JVM, initializing, and reaching readiness.

```text
Replica recovery time
≈ wait for failure detection
+ container stop
+ restart backoff wait
+ startup to readiness
+ routing update propagation time
```

`terminationGracePeriodSeconds` belongs to the stop phase, not initial startup waiting. For containers that exit on their own or are terminated due to out-of-memory, handling can occur before probes ever reach their threshold.

The formula above describes one replica. User-facing impact duration also depends on the count of healthy replicas and remaining service capacity.

## 5. Choosing Parameters from Measurements and Operational Requirements

### Step 1 — Measure the Right Intervals

Measure multiple times under conditions close to the deployment environment:

- From container start until the chosen startup endpoint returns success.
- From container start until readiness returns success.
- Latency of the probe endpoint itself under normal and high load.

Include cold starts, migrations, CPU limits, memory limits, and node conditions. Pod scheduling time or image pull time occurs before the container runs and is not on the startup probe clock; they still affect total deployment time.

Use appropriate percentiles and observed slow cases, plus a safety margin. One fast run on a developer laptop is not a valid baseline. A high percentile also does not guarantee covering every future case.

### Step 2 — Size the Startup Window

Suppose the operations team measures p99 time to first `/livez` success at 95 seconds. The team sets a target budget of 120 seconds after adding a 25-second margin.

A trial configuration is:

```text
Startup: P = 5 s, T = 2 s, F = 30
Nominal window: 30 × 5 = 150 s
```

In the fast-fail model with the first check at second 0, the 30th check starts near second 145; this window still exceeds the 120-second target. Leaving extra headroom avoids relying on boundary timing. These numbers serve as an example, not default values for every application.

If the 95-second measurement was time to readiness while the startup probe calls liveness, parameter selection is using the wrong milestone. Keep the measured endpoint and probed endpoint aligned.

### Step 3 — Choose Timeout from Endpoint Latency

Suppose probes normally respond in under 100 ms and stay under 700 ms at high percentiles in load tests. A 2-second timeout can be a reasonable starting point to test, provided that wait fits incident-detection requirements.

If the endpoint calls external systems, internal connect/read timeouts must be bounded and fit within the endpoint's total budget. A kubelet timeout does not guarantee server-side work stops immediately.

Do not raise timeouts to tens of seconds just to hide a heavy health query. First reduce the work inside the probe and investigate causes such as CPU throttling, HTTP queueing, GC, or resource contention.

### Step 4 — Choose Liveness According to Self-Recovery Ability

Suppose a brief slowdown can still recover within a few seconds. You can start testing with `P = 10`, `T = 2`, `F = 3`, then inject faults to verify:

- Does a transient slowdown kill the container too eagerly?
- Is a prolonged hang detected within an acceptable window?
- Does restarting actually improve the condition?

A 150-second startup window does not need to become a 150-second liveness tolerance window. The two phases have different goals.

### Step 5 — Choose Readiness According to Bad-Traffic Tolerance

Readiness usually needs to remove a replica from routing sooner than the restart decision. For example, use `P = 5`, `T = 2`, `F = 2`, `successThreshold = 2`.

In the even-schedule model, two consecutive failures are noticed after roughly one period from the first failure, plus the final check's duration. Two consecutive successes make recovery steadier. However, readiness may be polled faster while unready, so do not claim recovery always takes exactly 10 seconds.

While waiting to hit the failure threshold and propagate routing state, the replica can still receive requests. Account for that exposure, especially with a single replica.

## 6. Combining Spring Boot and Kubernetes Configuration

The example below targets a Spring Boot 3.3 application with `spring-boot-starter-actuator` and a web starter. These are configuration snippets to integrate into an existing application/Deployment, not a complete project or manifest.

### 6.1. application.yml

```yaml
server:
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
      show-details: never
```

The example assumes no extra context path or base path. The probes below call port 8080 with `/livez` and `/readyz`. Configuration keys are listed in [Spring Boot 3.3 Actuator properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html#appendix.application-properties.actuator).

If the application has custom Spring Security rules, permit kubelet to reach the selected probe paths. 401/403 errors from access rules cannot be fixed by raising failure thresholds. Do not open all management endpoints to work around this.

### 6.2. Container Configuration Fragment

Add the following fields to the matching container entry under `spec.template.spec.containers` of a Deployment:

```yaml
ports:
  - name: http
    containerPort: 8080

startupProbe:
  httpGet:
    path: /livez
    port: http
  initialDelaySeconds: 0
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 30
  successThreshold: 1

livenessProbe:
  httpGet:
    path: /livez
    port: http
  initialDelaySeconds: 0
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3
  successThreshold: 1

readinessProbe:
  httpGet:
    path: /readyz
    port: http
  initialDelaySeconds: 0
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 2
  successThreshold: 2
```

Meaning of this configuration set:

- Before `/livez` succeeds, the startup probe has a nominal 150-second window; the other two probes are not running yet.
- After startup succeeds, liveness uses a shorter failure window to detect prolonged hangs.
- Readiness can continue failing while a runner is executing; this does not trigger restarts itself.
- There is no long fixed delay after every fast startup just to accommodate slow cases.

If you do not use a startup probe yet, you can combine liveness `initialDelaySeconds` with failure thresholds to avoid premature termination. That approach remains valid, though it trades off fixed waiting against detection speed. Once a startup probe is used, avoid keeping a very long initial delay on liveness without clear justification. Verify delay behavior against your cluster's Kubernetes version.

Deployment rollout timing policies must match as well: a rollout progress deadline shorter than the time needed for a replica to reach readiness can report rollout failure even before the startup probe hits its failure threshold. Rollout deadlines and probe thresholds are separate mechanisms; see [Kubernetes Deployment — Progress Deadline Seconds](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/#progress-deadline-seconds).

## 7. Scenario-Based Verification

Run in a staging environment with the configured application image; do not edit live production environments directly.

The commands below assume a Deployment named `actuator-demo` and container named `app` in the current namespace:

```bash
kubectl get pods -l app=actuator-demo -w
kubectl describe pods -l app=actuator-demo
kubectl logs deployment/actuator-demo -c app --timestamps
kubectl get endpointslices -l kubernetes.io/service-name=actuator-demo -o yaml
```

The selector `app=actuator-demo` must match Pod labels; the Service name in the last command must match your staging environment. These commands return cluster-dependent output; there is no fixed stdout to match verbatim.

| Test scenario | What to observe | Interpretation |
| --- | --- | --- |
| Fast startup | Startup succeeds early, readiness passes, probe-triggered restarts stay zero | No need to wait through the full nominal startup window |
| Slow startup within budget | Temporary startup failures occur, then success; not killed before startup milestone | Protection window fits this run |
| Startup never succeeds | Probe hits threshold, container stop/restart events appear | Hung startup is bounded |
| Long runner while liveness is healthy | Startup finishes, Pod stays unready until runner finishes | Liveness and readiness represent distinct milestones |
| Readiness fails after serving | Ready turns false, endpoint status updates; restarts do not increase from readiness alone | Traffic routing control works independently |
| Continuous liveness failure after startup | Threshold reached, container stopped/restarted | Process recovery mechanism works |
| Single failure followed by recovery | Failure streak resets, three-failure liveness threshold not reached | Isolated glitches are not accumulated |

Cross-check application log timestamps, kubelet events, Ready status, and `restartCount`. Events may be aggregated or shown with relative timestamps; do not rely solely on `describe` output to assert exact millisecond timing.

You can use port-forwarding to manually check paths and HTTP codes:

```bash
kubectl port-forward deployment/actuator-demo 8080:8080
```

In another window:

```bash
curl -i --max-time 2 http://localhost:8080/livez
curl -i --max-time 2 http://localhost:8080/readyz
```

Port-forwarding helps check endpoints, but does not reproduce the full network path from kubelet to the Pod. When kubelet still fails, keep checking port, bind address, path, network policies, and actual permissions.

## 8. Adjustments That Easily Defeat the Goal

| Adjustment | Problem | Appropriate approach |
| --- | --- | --- |
| Raising timeout alone to survive a 120s startup | Every check can hang too long, delaying fault detection | Use a startup probe and size timeout to endpoint latency |
| Setting a very high liveness threshold for all phases | Post-startup faults are detected slowly | Give startup a long window and size liveness separately |
| Expecting readiness to shield against liveness | Liveness can still hit its threshold while readiness is failing | Use a startup probe or size liveness delay appropriately |
| Startup calling liveness while measuring time to readiness | The two milestones are not equivalent | Measure the exact signal selected for startup |
| Setting thresholds tight against average startup time | Cold starts or CPU throttling easily breach the threshold | Measure time distributions and leave margin |
| Using overall health containing DB for liveness | DB outage can trigger fleet-wide container stops | Pick indicators reflecting self-recovery capability |
| Treating every HTTP 503 as requiring a process restart | Readiness 503 may only indicate not ready for traffic | Distinguish endpoints, probes, and their actions |
| Increasing frequency when probes are heavy | Adds load and worsens slowdowns | Reduce check cost before increasing frequency |

## 9. Applied Exercise

An application has the following measurements:

- Slowest HTTP liveness success in the current test batch occurred at second 80.
- A runner completes at second 115.
- The team wants at least 20 extra seconds of margin for the chosen startup milestone.
- Probes normally respond under 300 ms and occasionally near 900 ms under high load.

Explain your choices for `startupProbe`, `livenessProbe`, and `readinessProbe`, and predict what happens if the runner hangs while `/livez` keeps succeeding.

One solution approach:

1. If choosing `/livez` for startup, the measured target is 80 + 20 = 100 seconds. You can try `P = 5`, `F = 25`, nominal window 125 seconds, and verify in practice; this is not the only valid parameter set.
2. You can try a 2-second timeout based on latency measurements, then re-test under CPU throttling and high load. Do not derive a 115-second timeout from runner duration.
3. Choose liveness for a post-startup failure detection window acceptable to the service, such as the 10/2/3 set analyzed above, and verify with a prolonged fault.
4. Readiness keeps the replica out of service before the runner finishes. When the runner hangs while liveness succeeds, the Pod can stay unready without probes triggering a restart.
5. If an operational requirement demands bounding runner duration too, add timeouts on initialization work or a startup signal reflecting that completion; clearly assess whether restarting actually solves the cause.

When explaining a configuration, always state: **which signal is checked, how long it is allowed to wait, whether failure changes routing or stops the container, and which measurements justify the choice**.
