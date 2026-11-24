# Why External Dependency Checks Must Be Considered Differently for Liveness and Readiness

An application may continue running normally in the JVM yet temporarily fail to complete requests because the database lost connectivity. Treating both conditions as the same can cause an orchestrator to restart applications en masse when the component that actually needs recovery is the database.

To choose the right health checks, start from **the action that will happen after a check fails**:

- **Liveness** drives the decision on whether to restart the container.
- **Readiness** drives the decision on whether to route new requests to this replica.
- **Dependency monitoring** indicates whether a database, cache, or other service is degraded for operational diagnostics and alerting.

These three purposes can share some observational data, but they should not automatically share the same pass/fail criteria.

## 1. Two Different Questions Lead to Two Different Actions

A **replica** is a running application instance, such as one Pod in a set of three Pods backing a Kubernetes Service. An **external dependency** is a resource outside the application process: a database, Redis, a messaging system, a payment service, or a partner API.

| Aspect | Liveness | Readiness |
| --- | --- | --- |
| Design question | Is internal state broken to the point of needing a restart? | Should this replica receive new requests right now? |
| Observation scope | Operability and self-recovery capability of the application itself | Ability of the replica to fulfill its serving contract |
| On failure | Can lead to container restart | Replica is removed from normal Service traffic targets |
| External dependencies | Do not include external outages directly in survival criteria | Include only after analyzing essentiality and blast radius |
| Example | Unrecoverable corrupted internal state | One replica cannot reach a required resource to serve |

Kubernetes applies probe results according to configured thresholds; one HTTP failure does not immediately restart the container. Readiness failure by itself is not a restart command. See [Kubernetes probe types](https://kubernetes.io/docs/concepts/workloads/pods/probes/).

In Spring Boot, internal availability is represented by `LivenessState` and `ReadinessState`. These are application signals, not a guarantee that no thread is blocked or every transaction will succeed. This mechanism is described in [Spring Boot 3.3 Application Availability](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.application-availability).

## 2. Why External Dependency Failures Usually Do Not Belong in Liveness

Suppose three replicas `orders-a`, `orders-b`, and `orders-c` share the `orders-db` database. The database experiences a one-minute outage.

If liveness is designed around "database query succeeds," all three replicas fail together:

~~~text
orders-db fails
    -> all three replicas report liveness failure
    -> containers are restarted
    -> replicas recreate connections and reload data
    -> orders-db is still down
    -> liveness keeps failing
~~~

**Restarting the orders process cannot fix orders-db.** Assuming the root cause lies entirely in the database, the chosen recovery action does not address the cause.

Worse, restarts can add extra cost:

- Losing warmed in-memory data inside each process.
- Aborting in-flight work or complicating retries.
- Creating a thundering herd of connections when all replicas start up together.
- Right as the database recovers, re-initialization tasks can compete for resources with user requests.
- Clouding diagnostics: operators see repeated restarts instead of one shared dependency failure.

This is a reasoning example from a hypothetical architecture; not every database outage produces all of the consequences above. The question to verify is: **does restarting the replica have a sound basis for restoring internal state, or does it just repeat failures of the same outbound call?**

If the application genuinely suffers corrupted internal state and cannot self-recover, that is a separate liveness concern. Do not infer that solely from a timeout to the database.

## 3. Readiness Can Check External Dependencies, With Good Reason

Readiness changes where traffic goes, so the key criterion is: **does taking this replica out of the request pool improve serving outcomes?**

### 3.1. Failure Affects Only One Replica

Suppose `orders-a` loses its network path to the database while `orders-b` and `orders-c` can still reach it. Every order operation strictly requires the database, with no valid fallback.

In this situation, failing readiness on `orders-a` is a sensible choice:

1. `orders-a` temporarily stops receiving new requests through the Service.
2. The remaining two replicas continue serving.
3. `orders-a` keeps running so its connection pool can self-recover.
4. Once serving conditions recover and probes meet the success threshold, the replica receives traffic again.

This fault does not necessarily require liveness to fail. The application is still alive and reconnection logic can handle recovery.

However, before adopting this, check whether the remaining replicas have enough capacity to absorb the extra load. Removing one replica from service shifts load onto the others; readiness does not create extra compute capacity.

### 3.2. Failure Happens in a Dependency Shared by All Replicas

Now suppose `orders-db` goes down for the entire application fleet. Putting `db` into readiness can make all three replicas go unready simultaneously.

This can fit when the service's contract is "do not accept requests if business operations are completely impossible." But you must intentionally accept the consequence: **zero ready replicas remain to receive requests via the Service**.

Conversely, if the application can still answer from cached data, enqueue requests into a durable queue, or return controlled business errors, removing all replicas can forfeit those capabilities too.

There is no blanket rule to "always include" or "always exclude" shared dependencies. Both options should be compared against the same contract:

| Option when shared dependency fails | What must be accepted and verified |
| --- | --- |
| Include dependency in readiness | The whole fleet can stop receiving traffic; upstream layers must behave properly when zero ready endpoints remain |
| Exclude dependency from readiness | The application keeps receiving requests; each operation needs clear timeouts, error responses, or fallbacks |

Do not promise users will always see HTTP `503` when every Pod is unready. External behavior also depends on Service, Ingress, and load balancers; the probe endpoint's HTTP status code is a separate matter.

### 3.3. Optional Dependencies or Dependencies With a Fallback

For example, a storefront service uses a product recommendation system. When recommendations fail, the application can still show products, prices, and checkout; recommendations are hidden by design.

If the service contract allows this degraded mode, do not turn recommendation failure into a readiness failure for the entire application.

Several scenarios require similar analysis:

- Redis only speeds up queries, and the application can still hit the database within acceptable load.
- An email service is temporarily down, while requests are persisted in a durable retry mechanism.
- A partner API serves only a secondary feature, while remaining features stay useful.

**Having a circuit breaker does not automatically mean the service is still operable.** A circuit breaker only stops calling a failing target. You need a fallback that fulfills business needs; returning wrong data or falsely reporting success for unfinished work is not a valid fallback.

The readiness choices in this section align with [Spring Boot guidance on external state checks](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes.external-state). Choosing the concrete contract remains an application design responsibility.

## 4. A Checklist for Deciding Each Dependency

Evaluate each dependency individually rather than feeding overall aggregated health into both probes.

1. **Which business capability requires this dependency?** If only a minor feature uses it, taking the whole replica down may be too broad.
2. **When it fails, can the replica still meet a minimal contract?** State clearly what it can and cannot do.
3. **Is the failure per-replica or fleet-wide?** Shifting traffic only helps if other targets are actually better off.
4. **What does restarting fix?** External system failures are rarely fixed by restarting the caller process.
5. **Does refusing traffic eliminate remaining useful capacity?** Especially when all replicas drop out together.
6. **How close is the check signal to actual business work?** Opening a socket does not prove real queries or transactions succeed.
7. **What are the check's cost and latency?** Probes themselves must not become a source of overload.
8. **What is the condition to return to service?** Test recovery too, not only fault detection.

Example decision table for a hypothetical application:

| Outage | Liveness | Readiness | Rationale |
| --- | --- | --- | --- |
| Recommendation API fails, storefront still meets contract | Keep succeeding if process is healthy | Keep succeeding | Fallback remains useful |
| One replica loses connection to mandatory DB, others are fine | Keep succeeding if able to self-recover | Fail on the affected replica | Shift requests to replicas that can handle them |
| Shared DB fails, all operations strictly require DB | Do not fail solely due to DB | Decide per chosen contract | Weigh halting fleet traffic vs. handling errors in the application layer |
| Permanent internal state corruption, restart can rebuild | May fail | Should not keep accepting requests | Restart action addresses the internal cause |

Cells in the table reflect design decisions under the stated assumptions, not automatic reactions by Spring Boot to every real outage.

## 5. Mapping Decisions to Spring Boot Actuator

The configuration snippets below target a Spring Boot 3.3.x web application that already has `spring-boot-starter-actuator`. These are snippets to merge into application configuration, not a standalone project.

### 5.1. Start with Two Separate Groups

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      probes:
        enabled: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState
~~~

Two default addresses:

~~~text
/actuator/health/liveness
/actuator/health/readiness
~~~

`probes.enabled: true` enables the probe groups even when testing outside Kubernetes. The two `include` lists specify the intended members of each group. This configuration does not yet select any external dependency as a readiness condition.

Spring Boot's default configuration also does not automatically include every dependency health indicator in the two probe groups. See [Kubernetes Probes in Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes).

### 5.2. Add DB to Readiness Only After a Business Decision

If the application has a `db` health contributor and policy requires removing replicas that cannot reach the DB from service, update the readiness list to:

~~~yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,db
~~~

This snippet **replaces the corresponding section** in the previous example; do not create two duplicate `management` keys in the same YAML document.

Apply only when `db` actually exists—for example, when the application configures a `DataSource` and its indicator is enabled. Do not copy contributor names missing from the application or disable group membership validation to hide configuration mistakes.

Keep `readinessState` so the application's lifecycle condition continues participating in the decision. Do not replace all of readiness with a DB ping.

With these members and default HTTP mapping, when the DB reports `DOWN` while the application stays alive:

~~~text
GET /actuator/health/liveness   -> 200
GET /actuator/health/readiness  -> 503
~~~

This is the conditional outcome of the described configuration; if you change the status aggregator or HTTP code mapping, verify again. HTTP `503` here is the response from the readiness endpoint, not a promise about the error code users see at Ingress.

**Do not point liveness at overall `/actuator/health`.** If overall health contains DB or Redis, they can inadvertently become restart conditions even when intended purely for monitoring.

### 5.3. Distinguishing Internal State from Group Aggregated Results

A `db` check reporting `DOWN` inside the readiness group does not mean Spring Boot automatically flips `ReadinessState` to `REFUSING_TRAFFIC`.

Two layers must be distinguished:

- Lifecycle or availability state managed by the application.
- Health result aggregated from the contributors selected by the group.

Therefore, when diagnosing, identify which member caused the group to fail. Do not conclude the JVM or the entire `ApplicationContext` is broken simply because a health group returns an unhealthy result.

## 6. Standalone Java 17+ Example to Verify the Reasoning

The program below models an **illustrative policy**:

- Liveness depends on internal health.
- Readiness requires the application to have finished startup.
- When a required dependency is down and no valid fallback exists, readiness fails.
- Optional dependencies do not make the whole application unready.

This is a self-written logic model; it does not run Actuator, make network calls, or simulate kubelet thresholds.

Save as `ProbePolicyDemo.java`:

~~~java
public class ProbePolicyDemo {
    record Situation(
            boolean internalHealthy,
            boolean startupComplete,
            boolean dependencyRequired,
            boolean dependencyReachable,
            boolean fallbackUsable) {
    }

    static boolean live(Situation situation) {
        return situation.internalHealthy();
    }

    static boolean ready(Situation situation) {
        boolean canServe = !situation.dependencyRequired()
                || situation.dependencyReachable()
                || situation.fallbackUsable();

        return live(situation)
                && situation.startupComplete()
                && canServe;
    }

    static void show(String name, Situation situation) {
        System.out.printf(
                "%s: live=%s, ready=%s%n",
                name, live(situation), ready(situation));
    }

    public static void main(String[] args) {
        show("required-db-down",
                new Situation(true, true, true, false, false));
        show("optional-api-down",
                new Situation(true, true, false, false, false));
        show("valid-fallback",
                new Situation(true, true, true, false, true));
        show("internal-broken",
                new Situation(false, true, true, true, false));
        show("starting",
                new Situation(true, false, true, true, false));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~shell
javac --release 17 ProbePolicyDemo.java
java ProbePolicyDemo
~~~

Stdout:

~~~text
required-db-down: live=true, ready=false
optional-api-down: live=true, ready=true
valid-fallback: live=true, ready=true
internal-broken: live=false, ready=false
starting: live=true, ready=false
~~~

The first line captures the main point: losing a required dependency can make a replica unready without implying the process needs a restart.

This program intentionally requires `internalHealthy` in readiness. That is a choice of this model; do not infer Spring Boot automatically puts `livenessState` into the readiness group by default. Likewise, the program does not model "single-Pod outage vs. fleet-wide outage"; that is an architectural fact to examine before selecting a policy.

## 7. Probes Also Generate Load and Can Amplify Incidents

Suppose there are 60 Pods, each checking a dependency every 5 seconds with one call per check. In steady state, ignoring check scheduling adjustments, the nominal load generated by probes is:

~~~text
60 Pods / 5 seconds = 12 calls per second
~~~

If three overlapping check groups exist and each call retries three times, total calls can be significantly higher. This is an illustrative capacity calculation, not a guarantee of kubelet's actual scheduling cadence.

When designing external dependency checks:

- Set finite timeouts for connection acquisition, network connect, and response reads; the total check budget must fit within the probe timeout.
- Avoid long retries inside probe execution; retries can turn a brief glitch into a pileup of hung checks.
- Do not run heavy queries or business writes just to prove "still alive."
- If using cached check results, document acceptable staleness and how stale results are handled; an old `UP` does not prove the dependency is currently healthy.
- When multiple checks exist, consider total group latency, not just individual call timeouts.
- Test recovery at realistic replica counts to prevent all replicas from simultaneously slamming a recovering dependency with connections.

Removing DB from liveness is **not enough** if business requests are tying up all server threads waiting indefinitely on the DB. In that case, HTTP liveness may not be served in time and will still fail. Bound wait times and isolate execution resources so a slow dependency cannot exhaust the application's responsiveness.

## 8. Configuring and Verifying Kubernetes Actions

This snippet goes under an item in `containers` of a Pod or Deployment. It assumes the Actuator endpoints are served on port `8080`:

~~~yaml
ports:
  - name: http
    containerPort: 8080

livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: http
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: http
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 3
  successThreshold: 2
~~~

The numbers are examples for discussion and must be tuned to actual response times and recovery targets. Readiness `successThreshold: 2` requires two consecutive successes to recover after failure; do not set a success threshold greater than one for liveness.

If the application starts slowly, consider `startupProbe` for an appropriate startup budget. Being unready does not automatically stop liveness from restarting the container. See [Kubernetes thresholds and startup probe configuration](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/).

If Actuator uses a separate management port, a green probe on that port does not prove the business port is still accepting connections. Verify the right serving path; do not check only the management server.

### Hands-On Scenarios with Observation Criteria

Run in a staging environment with at least two replicas while keeping liveness and readiness configurations separate:

| Fault injection step | Expected observation under the chosen policy |
| --- | --- |
| Block DB from only one Pod, mandatory DB in readiness | That Pod's readiness fails; other Pods keep serving; liveness does not fail solely due to the DB indicator |
| Restore connectivity on the affected Pod | The Pod returns to Ready after configured thresholds without redeployment |
| Block the shared DB | Verify whether you intentionally accept the whole group going unready or keep traffic so the app handles errors |
| Break the optional API | Fallback functionality actually works, not just probes staying green |
| Make a dependency respond very slowly | Probe duration is upper-bounded; no check request pileup occurs |

Assuming default ports, you can check HTTP status codes on the machine running the application with:

~~~shell
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/actuator/health/liveness
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/actuator/health/readiness
~~~

These two commands use Unix-style shell syntax. On Windows, invoke `curl.exe` and use an appropriate null output path. Endpoint access rules and authentication must allow probes to receive real results; `401` or `403` errors do not prove a dependency is broken.

Compare probe HTTP codes, Ready status, restart count, business errors, and latency together. Green probes only confirm the designed check conditions; they do not substitute for testing an actual business request.

## 9. Common Design Pitfalls

| Practice | Problem | Rethink |
| --- | --- | --- |
| Using overall health for every probe | Dependency outage can turn into fleet-wide restarts | Design each group's members around the action it triggers |
| Adding every DB, cache, API to readiness | One secondary feature can wipe out all serving capacity | Define the minimal contract and valid fallbacks |
| Assuming failing readiness will fix the application | Readiness only changes traffic routing | Design reconnection and recovery mechanisms separately |
| Keeping readiness green without handling business errors | Requests keep arriving and hang or fail uncontrollably | Add timeouts, error responses, and resource limits |
| Overly superficial connectivity checks | Connecting does not guarantee required operations succeed | Choose a sufficiently representative check at reasonable cost |
| Raising timeouts very high to reduce alerts | Delays detection and can hold resources longer | Set budgets from serving goals and test real slow faults |
| Testing only when the dependency breaks | Replicas might fail to return to service properly | Verify both disconnection and recovery |

## 10. Check Your Reasoning

**Scenario 1:** Redis is used only as a cache. When Redis fails, the application reads the DB directly, but the DB cannot handle the full load. Can readiness stay green simply because "a fallback exists"?

You cannot conclude that. You must test the fallback path's serving capacity and have appropriate load-shedding mechanisms. A fallback that exists in code yet collapses under real load does not uphold the serving contract.

**Scenario 2:** All five Pods simultaneously lose access to the payment service. Will restarting the five Pods bring the payment service back online?

Assuming the fault is in the payment service, no. Decide which capabilities can still be served and whether removing the whole group from traffic makes sense; do not wire payment outages directly into liveness.

**Scenario 3:** Readiness returns `503` because DB is `DOWN`, while liveness returns `200`. Do the two signals contradict each other?

No. A replica can be running and able to self-recover while temporarily failing the condition to accept new requests. Separating the two decisions prevents using restarts to treat an outage that restarts cannot solve.
