# Distinguishing Technical Health, Readiness to Serve, and Business Correctness

An order service returns `{"status":"UP"}` from Actuator. The load balancer keeps sending requests to the service. However, an order with a 10% discount calculates the wrong payable amount. All three observations can be true simultaneously because they answer **three different questions**.

This lesson builds a way to read health signals in Spring Boot 3.3.x: understanding what the system is checking, which operational decisions can rely on that result, and what evidence is still missing to conclude a business flow works properly.

## 1. Three concepts to separate clearly

| Dimension | Core question | Example evidence | Typically related decisions |
| --- | --- | --- | --- |
| Technical health | Are the observed technical conditions operating within acceptable limits? | Process responds, database connection succeeds, sufficient disk space remains | Investigating failing components, assessing resources and dependencies |
| Readiness to serve | Should this instance receive and is it capable of handling the request type in question right now? | Initialization finished, essential data ready, not actively refusing traffic | Allowing new requests, temporarily draining from traffic routing |
| Business correctness | Do results and state changes obey the rules of the business domain? | Correct price calculation, no double inventory deduction, no duplicate payment recording | Accepting results, fixing logic bugs, reconciling or recovering data |

In this lesson, **technical health** is a perspective chosen by the designer; it is not the name of a separate Spring Boot standard status. Nor is it completely synonymous with liveness. A database connection is a useful technical signal, yet that alone does not mean it belongs in liveness.

**Readiness to serve** must be tied to a specific scope: serving which feature, for which caller, and at what quality level? An application might read catalogs from cache yet be unable to create orders when the database loses connectivity.

**Business correctness** requires a reference oracle. A fast response with no exception can still contain the wrong result.

### Relationship between the three dimensions

Technical conditions and readiness conditions support executing business logic. They do not automatically prove business rules were implemented correctly.

```text
Technical observation  → supports diagnosing operational conditions
Readiness policy       → supports deciding whether to accept new requests
Business verification  → compares results and side effects against rules
```

These three kinds of evidence complement one another. They do not form a guaranteed chain of inference that "good tech → ready → all results are correct".

## 2. Why can the same green indicator be misleading?

Consider three checks in an ordering service:

1. Check whether a database connection can be opened.
2. Check whether the instance is ready to accept requests.
3. Check that a unit price of 10,000 minor currency units, minus 10%, must leave 9,000.

The first check does not run the discount calculation. The second check may only read the application's lifecycle state. If the actual calculation returns 9,990, the first two checks can still succeed.

A health check always has an **observation boundary**:

- Which components and conditions does it inspect?
- Does it traverse the real user processing path?
- Does it check outcomes or only connectivity?
- At what point in time was the result observed?
- What action will success or failure trigger?

Without this information, an UP value is very easily interpreted more broadly than the actual evidence supports.

## 3. Scenarios showing the three dimensions can diverge

| Scenario | Technical observation | Readiness to serve | Business correctness |
| --- | --- | --- | --- |
| Application is loading startup data | Process and connections are working | May not be ready to receive requests yet | Not inferred from startup loading |
| Required database loses connection | Failure at technical dependency | Flows requiring writes may be unable to serve | Calculation logic may still be right in isolated unit tests |
| Product recommendation service fails with a fallback to skip recommendations | One dependency is not working | Order flow may still serve under chosen policy | Output of the degraded flow must be verified |
| Discount formula is implemented wrong | Connection checks may all pass | Instance may still be accepting requests | Incorrect billing calculation |
| Payment webhook processed twice | HTTP and database may look normal | Endpoint still accepts webhooks | May violate the record-once requirement |
| Response latency exceeds user target | Lightweight probe may still succeed | Service quality does not meet requirements | Result may be right yet arrive too late |

The business column should not default to "correct" simply because no error has been observed yet. **Unverified** is a valid and more accurate conclusion.

A logic bug can also cause requests to throw exceptions or fail. Separating the three dimensions does not mean they cannot influence each other; the goal is to know which conclusion each piece of evidence supports.

## 4. How does Spring Boot represent these signals?

### 4.1. The health endpoint is an aggregated result per configuration

A `HealthIndicator` contributes a `Health` result to the health endpoint. The indicator author decides the actual check, while configuration determines groups and how aggregation is used. [HealthIndicator Contract in Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/HealthIndicator.html).

Therefore:

```text
/actuator/health = result of the selected checks
                  and the active aggregation policy
```

The root endpoint can contain technical checks, lifecycle states, and application-authored indicators. It should not be treated by default as a complete certification of product quality.

For example, an "able to open database connection" check does not prove that:

- The ordering feature's query is correct.
- The caller has the right data access permissions.
- The transaction writing the order and decrementing stock preserves invariants.
- Schema and data satisfy every processing branch.
- The order was paid exactly once.

### 4.2. Liveness and readiness serve different decisions

Spring Boot has availability states in `ApplicationAvailability`:

| Type | Application state | Meaning to care about |
| --- | --- | --- |
| Liveness | `LivenessState.CORRECT` / `BROKEN` | Internal state allowing continued operation or broken enough to require intervention |
| Readiness | `ReadinessState.ACCEPTING_TRAFFIC` / `REFUSING_TRAFFIC` | Whether the application is accepting or refusing new traffic |

Boot provides mechanisms to read and update these states. They reflect states published by the lifecycle or application code, without automatically verifying every business rule. [Boot 3.3 ApplicationAvailability](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/availability/ApplicationAvailability.html).

A `ReadinessStateHealthIndicator` is an indicator that reads the application's readiness state. It does not execute an order transaction itself to verify outcomes. [ReadinessStateHealthIndicator](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/availability/ReadinessStateHealthIndicator.html).

In a typical lifecycle, the application may already be alive internally yet not accepting traffic while executing startup tasks. Boot considers the application ready after application runners and command-line runners have finished being called. An asynchronous data-loading task launched outside that boundary needs an appropriate readiness policy; do not assume Boot automatically knows when it finishes. [Application Availability and SpringApplication Lifecycle](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html#features.spring-application.application-availability).

### 4.3. Readiness is a signal for traffic distribution systems

In Kubernetes, a failing readiness probe removes the instance as an eligible endpoint for regular Service traffic. A failing liveness probe reaching the configured threshold can trigger container restarts according to the restart policy. Failing readiness does not automatically mean "must restart". [Kubernetes Probe Types and Actions](https://kubernetes.io/docs/concepts/workloads/pods/probes/).

Stopping new requests also does not mean all in-flight requests have already finished. Managing active requests and shutting down gracefully require appropriate mechanisms.

Outside Kubernetes, readiness only has operational impact if the load balancer or deployment platform is configured to consume that signal. A URL returning OUT_OF_SERVICE by itself does not configure the rest of the infrastructure.

## 5. Reading health groups without over-extrapolating scope

Suppose you have a Spring Boot 3.3.x application using Java 21, Spring Web, and Actuator. You can explicitly declare the two basic groups in `application.yml`:

```yaml
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
          include:
            - livenessState
        readiness:
          include:
            - readinessState
```

This is a configuration snippet for an existing Spring Boot application, not a standalone Java project.

Read the configuration within its exact scope:

- The liveness group reads `livenessState`.
- The readiness group reads `readinessState`.
- This configuration has not added a database check to readiness.
- It has not added any price-calculation or payment-rule verification.

In Boot 3.3, probes are supported via health groups; outside Kubernetes environments they can be enabled with `management.endpoint.health.probes.enabled`. By default, Boot does not automatically add external dependency indicators to either probe group. [Boot 3.3 Health Groups and Kubernetes Probes](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes).

With default address and PowerShell on Windows, you can call:

```powershell
curl.exe -i http://localhost:8080/actuator/health/liveness
curl.exe -i http://localhost:8080/actuator/health/readiness
```

On Linux/macOS, replace `curl.exe` with `curl`. If startup has finished, states are normal, default HTTP mapping is retained, and requests are authorized, each probe endpoint above returns HTTP 200 with status UP. That still does not verify the billing formula.

If the application uses a different port, context path, or authentication mechanism, call it per actual configuration. A 401/403 response indicates the request hit a security decision; you cannot conclude from that alone that a business dependency is broken.

### Is a failing database with readiness still UP a contradiction?

Not necessarily. If readiness includes only `readinessState` and the application's state is still ACCEPTING_TRAFFIC, a failing `db` indicator in another group does not automatically become a readiness member.

When interpreting both results, read the **group member list**, rather than just comparing two URLs that both contain the word health.

## 6. Choosing dependency checks based on the desired action

An external service failure does not always demand the same reaction.

### Case A: dependency required for every critical request

If the instance cannot perform essential functions without the database, the development team can consider adding that check to readiness.

Example replacement configuration for readiness:

```yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include:
            - readinessState
            - db
```

Only use the name `db` when the application actually has the corresponding contributor. This is a readiness policy change, not a way to automatically verify all business read/write operations.

### Case B: dependency with a degraded serving fallback

If the recommendation service fails yet placing orders without showing recommendations is still allowed, putting the recommendation service into readiness can take down the still-working ordering feature.

Clearly describe the degraded mode: which features remain supported, which outputs must change, and which quality limits are acceptable.

### Case C: dependency shared by all instances

If all instances lose connection to a shared database simultaneously, putting that dependency into readiness can pull all instances out of the serving pool together. Whether that is appropriate depends on product policy and upstream error handling.

Do not put external dependency checks into liveness simply because they are technical signals. If an external outage makes every container restart continuously, restarting usually cannot fix the external cause. Designing these decisions must be weighed against each probe's role.

## 7. Standalone Java example: healthy signals yet wrong result

The following program simulates three kinds of evidence, without connecting to a real database or calling Actuator.

Example-specific conventions:

- `technicalHealthy`: process responds and database is reachable.
- `readyForRequests`: the two conditions above hold and the instance allows receiving traffic.
- `businessRuleCheck`: whether the test case calculation yields the expected 9,000.

This is **the illustrative model's policy**, not Spring Boot's default algorithm. The technical indicator in the example is also not liveness.

Use minor currency units as integers. With subtotal 10,000 and 10% discount, the result must be 9,000. The intentional bug in `buggyPayableCents` subtracts the number 10 as an amount instead of computing 10% of the subtotal.

Save as `HealthMeaningDemo.java`:

```java
public class HealthMeaningDemo {
    record RuntimeSnapshot(
            boolean processResponsive,
            boolean databaseReachable,
            boolean acceptingTraffic) {
    }

    static boolean technicalHealthy(RuntimeSnapshot snapshot) {
        return snapshot.processResponsive()
                && snapshot.databaseReachable();
    }

    static boolean readyForRequests(RuntimeSnapshot snapshot) {
        return snapshot.processResponsive()
                && snapshot.databaseReachable()
                && snapshot.acceptingTraffic();
    }

    static long correctPayableCents(long subtotalCents, int discountPercent) {
        return subtotalCents * (100 - discountPercent) / 100;
    }

    static long buggyPayableCents(long subtotalCents, int discountPercent) {
        return subtotalCents - discountPercent;
    }

    static void report(
            String name,
            RuntimeSnapshot snapshot,
            boolean businessRuleCheck) {
        System.out.printf(
                "%s | technical=%s | ready=%s | ruleCheck=%s%n",
                name,
                technicalHealthy(snapshot),
                readyForRequests(snapshot),
                businessRuleCheck);
    }

    public static void main(String[] args) {
        long expectedPayableCents = 9000;
        long correctResult = correctPayableCents(10000, 10);
        long buggyResult = buggyPayableCents(10000, 10);

        report("normal",
                new RuntimeSnapshot(true, true, true),
                correctResult == expectedPayableCents);
        report("warming-up",
                new RuntimeSnapshot(true, true, false),
                correctResult == expectedPayableCents);
        report("database-down",
                new RuntimeSnapshot(true, false, true),
                correctResult == expectedPayableCents);
        report("business-bug",
                new RuntimeSnapshot(true, true, true),
                buggyResult == expectedPayableCents);

        System.out.println("actualPayableCents=" + buggyResult);
        System.out.println("expectedPayableCents=" + expectedPayableCents);
    }
}
```

Compile and run with JDK 21:

```shell
javac -encoding UTF-8 HealthMeaningDemo.java
java HealthMeaningDemo
```

Stdout:

```text
normal | technical=true | ready=true | ruleCheck=true
warming-up | technical=true | ready=false | ruleCheck=true
database-down | technical=false | ready=false | ruleCheck=true
business-bug | technical=true | ready=true | ruleCheck=false
actualPayableCents=9990
expectedPayableCents=9000
```

### How to explain each line

**normal:** technical and traffic-receiving conditions pass; the test case using the right formula also passes.

**warming-up:** technical conditions pass yet the instance is not accepting traffic yet. This is an example where "alive" and "should receive more requests" are not identical.

**database-down:** the database is unreachable, so the model's readiness policy returns false even though the traffic-acceptance flag is still true. The right-formula test case still passes because it does not depend on the database.

**business-bug:** all technical and readiness conditions in the model pass, yet the buggy calculation returns 9,990 instead of 9,000.

In particular, `ruleCheck=true` on the database-down line only states that **the test case under consideration for the formula passed**. It does not say an end-to-end order transaction across the current system can succeed while the database is down.

The example uses small numbers and a single simple discount case. Rounding rules, input bounds, taxes, multiple currencies, and overflow risks must be designed when implementing real billing.

## 8. HTTP 200 is not enough to conclude business correctness

Consider a hypothetical response from a price-quoting feature:

```json
{
  "subtotalCents": 10000,
  "discountPercent": 10,
  "payableCents": 9990
}
```

If the response carries HTTP 200, protocol-level observation tells us the request was served in the way the endpoint expresses success. To detect a business error, `payableCents` must be compared against the right result 9,000.

There are three different verification levels:

| Verification | Can detect | Insufficient to prove |
| --- | --- | --- |
| Checking HTTP 200 only | Some access, protocol, or processing errors expressed via error status codes | Correct billing content |
| Checking quote JSON | Wrong fields or wrong amount for a test case | Order persisted and paid properly |
| Checking result plus persistence/payment side effects | Some end-to-end bugs, duplicate transactions, or bad data | All input cases and all concurrency bugs |

Monitoring needs signals aligned with real user experience. Google SRE also distinguishes errors expressed via HTTP codes from cases where HTTP succeeds yet the content is wrong; those cases require checking outcomes rather than merely counting response codes. [Monitoring Distributed Systems](https://sre.google/sre-book/monitoring-distributed-systems/#xref_monitoring_golden-signals).

For asynchronous flows, HTTP 202 or enqueuing a message only proves the acceptance step under the system's contract. Final outcomes, processing deadlines, failure events, and reconciliation must be tracked to know the business work completed properly.

## 9. Which kind of evidence to use for each question?

| Question to answer | Appropriate evidence | Point to keep in mind |
| --- | --- | --- |
| Is the instance stuck enough to require restarting? | Liveness designed around internal state | Too light a check may miss some deadlock modes |
| Should more new requests be sent to this instance? | Readiness and traffic distribution policy | Request types and essential conditions must be defined |
| Are users receiving responses fast enough? | Actual latency measurement, percentiles, error rates, and saturation | Lightweight probes do not simulate full load |
| Is the discount rule right? | Tests with independent inputs and expected outputs | Do not rewrite the same buggy formula in the expected-value logic |
| Do orders and inventory update consistently? | Integration tests, transactions, and concurrency scenarios | Successful DB connection does not verify invariants |
| Does a retried webhook cause duplicate payments? | Idempotency tests, constraints, and reconciliation | HTTP 200 on each delivery does not prove processed once |
| Does a user flow work outside test environments? | External synthetic checks with safe data | Carries its own sample scope, cost, and impact risk |
| Does live data violate rules over time? | Invariant checks, reconciliation, and business outcome tracking | Detection latency and remediation handling must be defined |

Readiness to serve also has time and quality dimensions. Readiness is a point-in-time, per-instance signal; Service Level Indicators (SLIs) typically observe behavior over a time window. Success metrics must be defined around what users actually need, rather than merely reusing an UP label. [Google SRE Service Level Objectives](https://sre.google/sre-book/service-level-objectives/).

No finite test or monitor proves all cases work. State the verified scope, uncovered cases, and applicable environmental conditions.

## 10. Designing health checks so results are operationally meaningful

When adding a check, first write a brief description of its contract:

```text
Check: connection to database serving order writes
Scope: single instance, active connection path
Permitted conclusion: this dependency is reachable at check time
Unproven conclusion: order transactions work correctly in all cases
Action on failure: depends on chosen readiness or alerting policy
```

Next, review practical limits:

1. **Cost and time:** set appropriate limits; do not turn every probe into a chain of expensive operations.
2. **Side effects:** avoid creating orders, charging money, or sending real notifications just to satisfy high-frequency probes.
3. **Resource scope:** does the probe traverse the same port, connection path, and conditions close to the flow being observed?
4. **Freshness:** a cached result or earlier observation may not reflect an outage that just happened.
5. **Action:** should this failure drain traffic, alert, serve degraded, or restart? Do not assign one action to every failure.

For example, management and application traffic running on two different ports can create two different processing conditions. A responding management endpoint does not prove the user-facing port is receiving requests cleanly. When evaluating evidence, always ask which parts of the system the check path actually traversed.

A synthetic business check is valuable, yet should usually have its own frequency, data, environment, and handling policy. Wiring it directly into liveness must be weighed carefully because a sample transaction failure can trigger unintended restarts.

## 11. Common reasoning errors

| Inference | Why is it insufficient? | How to check further |
| --- | --- | --- |
| "Health is UP so business logic is definitely right" | Unknown whether the indicator checks that business rule | Read the check contract and verify actual outcomes |
| "Readiness is UP so all clients can use it" | Identity, permissions, network routes, and data per client may differ | Test from representative access paths and identities |
| "Dependency failed so liveness must go DOWN" | Restarting does not necessarily fix an external outage | Choose action based on self-recovery capability and dependency role |
| "Readiness failed so container will restart automatically" | Readiness primarily serves traffic-routing decisions | Inspect liveness, restart config, and actual platform |
| "Database connects so transactions are right" | Connectivity does not check logic, constraints, and concurrency | Test transactions, invariants, and race cases |
| "All unit tests pass so the system can serve" | Isolated tests may not use the deployment environment | Add integration tests and operational observation |
| "One sample request succeeded so the whole system is good" | Sample covers only one branch and one moment | Define sample scope and combine multiple evidence types |

During incidents, use statements with explicit bounds: "`readinessState` is `ACCEPTING_TRAFFIC`", "the connection check succeeded", or "the 10% discount case on 10,000 passed". Such statements prevent turning a narrow result into an overbroad promise.

## 12. Practice: choosing appropriate evidence and actions

For each scenario, write down three points: what is known, what is unknown, and what to do next.

### Scenario 1: receiving orders before data loading finishes

The process responds and the database is reachable, yet the pricing-rules table has not finished loading.

- Existing technical evidence does not prove the instance is ready to quote prices.
- Determine whether this data is a mandatory prerequisite before accepting requests.
- If mandatory, readiness policy must reflect the unready period; also verify results after loading.

### Scenario 2: wrong pricing despite all probes succeeding

Subtotal 10,000, 10% off, API returns 9,990.

- There is evidence of a business bug for that specific case.
- There is no basis to think a restart will fix the formula.
- Fix the logic, add test cases matching expected outcomes, and inspect affected data.

### Scenario 3: recommendation service lost, ordering still works

- A dependency failure was observed.
- Verify that the degraded feature satisfies its contract and acceptable experience.
- Do not automatically drain the entire instance if policy allows continuing orders.

### Scenario 4: money recorded twice after webhook redelivery

- HTTP success does not prove idempotent handling.
- Inspect transaction-ID keys, storage constraints, concurrency handling, and result reconciliation.
- Existing technical probes are only one piece of investigative information.

### Self-check

1. Why can a program have `technical=true` and `ready=true` yet still have `ruleCheck=false`?
2. Why is `ruleCheck=true` not enough to conclude real order transactions are succeeding?
3. When the database fails, what information decides whether to put the failure into readiness or only alert?
4. If a probe is called every few seconds, why should it not execute a real payment by default?
5. Before writing "the system works properly", which functional scope, inputs, outputs, and point in time must be stated?

A good design ties each signal to one clear question and one appropriate action. Technical health helps observe operational conditions, readiness supports traffic management, and business correctness must be verified against outcomes and the business's own invariants.
