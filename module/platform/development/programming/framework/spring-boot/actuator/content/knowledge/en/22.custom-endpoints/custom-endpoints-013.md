# Controlling Caching, Execution Cost, and Safety of Management Operations

## 1. Why Does a Management Endpoint Need to Be Designed Like a Real Traffic Path?

A custom Actuator endpoint might return only a few JSON fields, yet behind the scenes scan thousands of objects, hit the database, or query a slow dependency. During an incident, multiple operators and tools often invoke diagnostics simultaneously. An endpoint built to observe the application can become a source of load that worsens the incident.

Management operations can also change configuration, stop a task, or trigger data reprocessing. Having an authorized caller does not mean every parameter is valid; a valid request can also arrive twice or race against another caller's request.

Separate three questions:

1. **Freshness:** how stale can the data be for operators?
2. **Cost:** how much time, memory, connections, and downstream work does each result generation consume?
3. **Safety:** who may call it, what may be changed, and what happens if a request is retried or arrives concurrently?

Caching solves part of read cost by reusing results. It does not replace load limits, permission checks, or state-update rules.

This lesson uses Spring Boot 3.3.x and Spring MVC. The practice example pins Spring Boot 3.3.0, run on JDK 21; application code also works with Java 17+ syntax. Do not apply endpoint permission property names from other Spring Boot versions to this example.

## 2. Understanding Actuator Operation Result Caching Correctly

### 2.1. Where Does the Cache Live?

For an eligible read operation with a positive TTL, Actuator's operation invoker layer can retain the result so subsequent calls reuse it instead of executing the method body.

You can picture the path:

```text
HTTP Request
  → authentication / authorization if configured by the application
  → locate Actuator operation
  → check operation result cache
      → still valid: return cached result
      → absent / expired: execute operation to produce result
  → convert result to HTTP response
```

This is a conceptual diagram for the lesson's read case, not a guarantee that every filter, extension, and converter shares the same ordering in every application.

| Mechanism | What Is Reused or Controlled | Automatically Replaces Operation Caching? |
| --- | --- | --- |
| Actuator operation caching | Result of an eligible read operation | Is the mechanism under consideration |
| Spring Cache, e.g. `@Cacheable` | Method results per application cache design | No; can create an extra cache layer |
| Client or proxy HTTP caching | Responses per HTTP headers and policies | No; is a different layer |
| Request rate limiting | Rate at which requests may be sent or processed | Does not create a data snapshot |
| Concurrency limiting | Number of tasks executing simultaneously | Does not determine result freshness |

Setting a TTL in Actuator does not mean setting `Cache-Control: max-age` for browsers. Sending a `Cache-Control: no-cache` header from a client is not a universal protocol to evict server-side operation caches either.

Similarly, evicting a business cache via the `caches` endpoint should not be assumed to clear result caches of custom operations. Before designing a “refresh” feature, identify exactly which cache layer needs refreshing.

### 2.2. Applicability Conditions and Configuration

The easiest case to control is a `@ReadOperation` with no input parameters. For example, with endpoint ID `opsdemo`:

```properties
management.endpoint.opsdemo.cache.time-to-live=5s
```

The property uses the **endpoint ID**, not the Java class name or the full path `/actuator/opsdemo`. Actuator documentation describes caching parameterless read operations via `cache.time-to-live`. [Endpoint caching configuration in Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

In the 3.3.0 implementation examined here:

- TTL must be positive for the operation invoker to be wrapped with caching.
- `0ms` does not mean keep results forever; it means this caching mechanism is not applied.
- Write and delete operations are not turned into cached operations simply by setting a TTL.
- Ordinary required parameters, such as a selector to read a single item, do not exhibit the same caching behavior as an inputless read operation.
- Calling `endpoint.summary()` directly in Java bypasses this operation invoker; do not use direct calls to prove HTTP TTL behavior.

Do not oversimplify to a rule like “any Java parameter definitely disables caching”. The implementation has special handling for invocation contexts and optional parameters. When results depend on `Principal`, permissions, tenant, or another implicit input, inspect the exact mechanism and version in use. In particular, never build a shared cache without a key distinguishing data scopes.

Conclusions about TTL, selectors, and direct calls here are re-observed in the section 5 experiment rather than inferred from a single method call.

### 2.3. TTL Is a Reuse Limit, Not a Background Collection Schedule

Suppose a read creates a snapshot at t₀ and the TTL is 5 seconds:

| Illustrative Time | Observable Behavior with Sequential Requests |
| --- | --- |
| t₀ | No result yet; operation executes |
| t₀ + 1 second | Can reuse the snapshot |
| t₀ + 3 seconds | Can still receive data from the previous execution |
| After expiration | Next request produces a fresh result |
| No subsequent requests | TTL does not re-run the operation just because time elapsed |

TTL does not guarantee a fresh snapshot every 5 seconds. Nor is it a method execution timeout, nor does it cancel hanging queries or automatically fall back to stale data if refresh fails.

When source data is already a slowly updated aggregate, user-visible staleness also includes that source's lag. You cannot claim “data is fresh within 5 seconds” solely from a 5-second TTL configuration.

### 2.4. Cache Scope and Concurrent Requests

Do not treat operation caching as a shared data store across application replicas. Two JVMs have separate memory and execution cadences; after a restart, in-memory cached results are not durable data.

Nor should you use TTL as a guarantee that “within each window, computation runs at most once”. When multiple concurrent requests hit an absent or expired result, check whether computation coalescing exists. The synchronous 3.3.0 implementation examined here provides no single-flight execution guarantee across that group of requests.

If generating the result is very expensive, design a concurrency limit on refreshes or read a snapshot collected elsewhere. That is application design, not something inferred from TTL alone.

Results retained for reuse should be stable snapshots. If you return a mutable `Map` and continue mutating that same instance, callers can see contents change even though the operation body has not rerun. A record containing only numbers, booleans, and strings as in the example avoids this issue.

## 3. Quantifying and Bounding Execution Cost

### 3.1. Count the Work to Produce Data, Not Just JSON Bytes

There are at least three categories of cost:

- **Collection:** database reads, network calls, memory scans, lock acquisition.
- **Building and sending results:** object allocation, JSON serialization, buffering, and transmission.
- **Indirect impact:** connection contention, lock contention, increased garbage collection, or load on dependent systems.

A 2 KB response can still be expensive if it requires a full table scan. Conversely, caching a huge snapshot may reduce scans while increasing memory usage and per-request serialization cost.

Illustrative calculation: suppose there are 20 requests per second total and each collection occupies one thread for 100 ms. If every call executes, total thread occupancy is roughly 2 thread-seconds per second, corresponding to an average of about 2 concurrent executions in steady state. This is not the peak thread count and ignores traffic bursts.

Under ideal conditions with one replica, one cache context, sequential requests, and a 5-second TTL, collection count can drop to about once every 5 seconds under steady polling. However, HTTP requests, security checks, and response serialization/sending can still occur 20 times per second.

### 3.2. Establish Dedicated Budgets for Each Load Source

| Cost Source | Decisions Needed |
| --- | --- |
| Database queries | Maximum rows, indexes, query timeout, allowed connection budget |
| External service calls | Connect/read timeouts, retry count, overall time budget |
| Data traversal | Element cap, depth limit, subtask count |
| JSON or file responses | Maximum size, item cap, how truncated results are indicated |
| Heavy operations | Concurrent execution cap, bounded queue, busy-rejection behavior |
| Long-running work | Task model with ID and status instead of holding an HTTP request open |

Do not add unbounded retry loops to a diagnostic endpoint calling a dependency that is itself failing. Retries must stay within defined time and attempt budgets.

An HTTP-layer timeout does not prove the underlying task has stopped either. Database drivers, network clients, and CPU work need appropriate deadlines or cancellation mechanisms. If the caller gives up while the task keeps running, retries can keep piling on load.

### 3.3. When Should You Pre-Collect?

If measurement is expensive yet operators only need recent figures, a collector component can update a bounded snapshot. The endpoint reads the snapshot and can also return collection timestamp, collection duration, and status of the latest collection if needed.

Decide clearly what happens when collection fails:

- No data yet: report no snapshot available yet.
- Stale snapshot exists: is reuse allowed, and how old at maximum?
- Source failed: return an error indicator or explicitly marked stale data, avoiding pretending it is freshly measured success data.

This is an application-designed background collection mechanism. It differs from simply enabling TTL on an operation.

## 4. Safety of Management Operations

### 4.1. Separate Observation from Mutation

`@ReadOperation` is exposed as GET; `@WriteOperation` as POST; `@DeleteOperation` as DELETE on the web. Use read operations for observation and avoid placing configuration changes or data deletions inside GET. Systems may repeat GET requests for monitoring, page refreshes, or connection retries.

Counters tracking read counts or audit logging are observational side effects. They differ from a GET request altering the application's management state. In the example, `readNumber` only observes how many times the method body ran; the `enabled` field changes only via the write operation.

### 4.2. Validate Before Causing Side Effects

A mutating request should pass through appropriate validation layers:

```text
Authenticate caller
  → check permissions on action and target
  → validate input / bounds
  → check current state or version
  → apply change atomically within the protected scope
  → record result and audit information
```

Management inputs should express clear intent, such as `enabled=true` instead of a `toggle` command. Setting the same target state twice is usually much safer to control than toggling twice.

Do not check syntax alone. A valid integer can still exceed operational limits; a valid path can still point outside allowed scopes. With sensitive source data, return just enough for authorized operators to act, without returning full configurations or raw internal error payloads.

### 4.3. Avoid Overwriting Someone Else's Change

Suppose two operators both read version 7:

- The first sends a change based on version 7, succeeds, and creates version 8.
- The second also sends a change based on version 7.
- If the second request is blindly applied, it can overwrite the decision just made.

One approach is requiring `expectedVersion` and checking it **together with the update operation**, not checking and then updating in two unprotected steps.

Within one JVM, for example, use `AtomicReference.compareAndSet` to swap an immutable state object only when the current reference is still the one read. This is an atomic update on the reference; it does not create a transaction across databases, files, or network calls. [Java 21 AtomicReference](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html).

When data is shared across multiple JVMs, check the version at the shared data store, such as conditional updates and checking affected row counts. In-process memory locks do not protect other processes.

### 4.4. Resending a Request Does Not Mean It Has Not Executed

If the caller times out, the change may already have been applied. Therefore:

- Do not automatically retry an action whose side effects cannot be safely repeated.
- Consider request IDs and result storage if duplicate requests must be recognized.
- Distinguish version conflicts from unexecuted failures.
- For long tasks, return a task ID to poll status instead of launching a new task after each lost response.

`expectedVersion` helps prevent updating from stale state; it is not yet a per-request-ID result store. A retry can receive a conflict even when the previous attempt succeeded. Callers must read the current result or look up the prior request rather than blindly incrementing the version and replaying commands.

## 5. Complete Example: Caching a Snapshot and Updating with Version Checks

### 5.1. Scope of the Experiment

The application simulates an in-memory `enabled` flag. The flag controls no external system. There are three operations:

| Request | Meaning |
| --- | --- |
| `GET /actuator/opsdemo` | Reads inputless summary, eligible for caching |
| `GET /actuator/opsdemo/live` | Reads state via required selector |
| `POST /actuator/opsdemo` | Sets desired state, with expected version |

The experiment runs on loopback to focus on observing TTL and updates. It does not include Spring Security yet; section 7 covers adding access control. Caching and `expectedVersion` must not be used as authentication mechanisms.

### 5.2. Project Files

```text
ops-cache-demo/
├── pom.xml
└── src/main/
    ├── java/example/opscache/OpsCacheApplication.java
    └── resources/application.properties
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>ops-cache-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=18081
management.endpoints.web.exposure.include=opsdemo
management.endpoint.opsdemo.cache.time-to-live=5s
```

`src/main/java/example/opscache/OpsCacheApplication.java`:

```java
package example.opscache;

import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.boot.actuate.endpoint.annotation.Selector;
import org.springframework.boot.actuate.endpoint.annotation.WriteOperation;
import org.springframework.boot.actuate.endpoint.web.WebEndpointResponse;
import org.springframework.boot.actuate.endpoint.web.annotation.WebEndpoint;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication(proxyBeanMethods = false)
public class OpsCacheApplication {
    public static void main(String[] args) {
        SpringApplication.run(OpsCacheApplication.class, args);
    }

    @Bean
    OpsDemoEndpoint opsDemoEndpoint() {
        return new OpsDemoEndpoint();
    }

    public record State(boolean enabled, long version) {
    }

    public record View(String source, long readNumber, boolean enabled, long version) {
    }

    public record Change(String result, boolean enabled, long version) {
    }

    @WebEndpoint(id = "opsdemo")
    public static class OpsDemoEndpoint {
        private final AtomicReference<State> state =
                new AtomicReference<>(new State(false, 0));
        private final AtomicLong cachedReads = new AtomicLong();
        private final AtomicLong liveReads = new AtomicLong();

        @ReadOperation(produces = "application/json")
        public View summary() {
            return capture("cached", cachedReads.incrementAndGet());
        }

        @ReadOperation(produces = "application/json")
        public View current(@Selector String view) {
            if (!"live".equals(view)) {
                return null;
            }
            return capture("live", liveReads.incrementAndGet());
        }

        private View capture(String source, long readNumber) {
            State current = state.get();
            return new View(source, readNumber, current.enabled(), current.version());
        }

        @WriteOperation(produces = "application/json")
        public WebEndpointResponse<Change> configure(boolean enabled, long expectedVersion) {
            State current = state.get();
            if (expectedVersion < 0) {
                return response("INVALID_ARGUMENT", current, 400);
            }
            if (current.version() != expectedVersion) {
                return response("CONFLICT", current, 409);
            }
            if (current.enabled() == enabled) {
                return response("UNCHANGED", current, 200);
            }
            State next = new State(enabled, current.version() + 1);
            if (!state.compareAndSet(current, next)) {
                return response("CONFLICT", state.get(), 409);
            }
            return response("APPLIED", next, 200);
        }

        private WebEndpointResponse<Change> response(String result, State current, int status) {
            return new WebEndpointResponse<>(
                    new Change(result, current.enabled(), current.version()), status);
        }
    }
}
```

`State` holds the real management state in the experiment. `View` is the snapshot for reading; `Change` is the receipt of a write operation. `source="cached"` simply names the read path eligible for caching; it is not an automatic indicator that a particular request was a cache hit.

`configure` uses a single compare-and-set. If someone else swaps the reference first, the operation fails with 409. Codes 400 and 409 are set explicitly via `WebEndpointResponse`; do not rely on having the word `CONFLICT` in JSON to alter the HTTP status automatically.

`UNCHANGED` appears only when the expected version is still current and the desired state is already the active state. It does not increment the version. A request with a stale version is still rejected even if the desired state happens to match the current one.

### 5.3. Compiling and Running

From the directory containing `pom.xml`:

```shell
mvn clean package
java -jar target/ops-cache-demo-1.0.0.jar
```

Use Maven with JDK 21. Maven handles classpath and Spring library packaging; a standalone `javac OpsCacheApplication.java` command lacks the dependencies to compile the project.

The following commands use PowerShell. `curl.exe` avoids confusion with the `curl` alias in some PowerShell versions.

### 5.4. Observing Reused Reads

Start a fresh application with no other requests hitting the endpoint. Run two consecutive read commands within the TTL window:

```powershell
curl.exe -sS http://127.0.0.1:18081/actuator/opsdemo
curl.exe -sS http://127.0.0.1:18081/actuator/opsdemo
```

Each response contains these values:

```json
{"source":"cached","readNumber":1,"enabled":false,"version":0}
```

`readNumber` does not increment on the second call because the `summary` body did not execute again. JSON property ordering is not something recipients should rely on.

If you stop the application and run with a zero TTL:

```shell
java -jar target/ops-cache-demo-1.0.0.jar --management.endpoint.opsdemo.cache.time-to-live=0ms
```

Two fresh reads will have `readNumber` values 1 and 2 respectively. The read path still writes `source="cached"` because the sample code sets that string, while caching is disabled.

### 5.5. Write Succeeds While Cached Snapshot Remains Stale

Restart with the default 5-second TTL. In one continuous run, read the snapshot, write immediately, and read again:

```powershell
curl.exe -sS http://127.0.0.1:18081/actuator/opsdemo
'{"enabled":true,"expectedVersion":0}' | Set-Content -Encoding ascii change.json
curl.exe -sS -i -X POST -H "Content-Type: application/json" --data-binary "@change.json" http://127.0.0.1:18081/actuator/opsdemo
curl.exe -sS http://127.0.0.1:18081/actuator/opsdemo
```

`change.json` is an input file created by the learner in the experiment directory; using a file avoids JSON quoting differences across PowerShell versions.

Relevant write response parts:

```http
HTTP/1.1 200
Content-Type: application/json

{"result":"APPLIED","enabled":true,"version":1}
```

If the final read still falls within the first read's TTL, it can still return:

```json
{"source":"cached","readNumber":1,"enabled":false,"version":0}
```

These are two simultaneously true facts:

- The state inside `AtomicReference` is already `enabled=true`, version 1.
- The cached read result still contains data from version 0.

The write operation does not automatically clear the read cache in this sample. Therefore, do not use a TTL-cached snapshot as the sole confirmation that a change just failed. The write receipt and stored state serve a different role from the summary snapshot.

### 5.6. Reading Live State and Checking Conflicts

```powershell
curl.exe -sS http://127.0.0.1:18081/actuator/opsdemo/live
curl.exe -sS http://127.0.0.1:18081/actuator/opsdemo/live
```

When no other calls have hit the `live` path, the two results are sequentially:

```json
{"source":"live","readNumber":1,"enabled":true,"version":1}
```

```json
{"source":"live","readNumber":2,"enabled":true,"version":1}
```

The required selector causes these two reads to execute the method body in the case under study. This is a cheap in-memory read path for observing the experiment; do not turn every expensive scan into an unbounded `live` path and assume the load problem is solved.

Now send a change based on the stale version 0:

```powershell
'{"enabled":false,"expectedVersion":0}' | Set-Content -Encoding ascii stale-change.json
curl.exe -sS -i -X POST -H "Content-Type: application/json" --data-binary "@stale-change.json" http://127.0.0.1:18081/actuator/opsdemo
```

Relevant response parts:

```http
HTTP/1.1 409
Content-Type: application/json

{"result":"CONFLICT","enabled":true,"version":1}
```

The state was not flipped to false. Operators must read and re-evaluate the situation, rather than automatically grabbing version 1 and replaying old commands.

If you send `enabled=true` with `expectedVersion=1`, the sample returns:

```json
{"result":"UNCHANGED","enabled":true,"version":1}
```

The version does not increment because no state change occurred.

### 5.7. After TTL Expiration and Under Contention

After obtaining the first snapshot, make no additional calls to the summary path while waiting:

```powershell
Start-Sleep -Seconds 6
curl.exe -sS http://127.0.0.1:18081/actuator/opsdemo
```

If only the described calls occurred, the new result is:

```json
{"source":"cached","readNumber":2,"enabled":true,"version":1}
```

If manual steps took longer than 5 seconds earlier, `readNumber` may be higher. That is due to recomputations after expiration, not a timer incrementing on a schedule. You can raise TTL to 30 seconds and wait longer for comfortable hands-on practice.

On a freshly started endpoint, have two threads concurrently send `enabled=true, expectedVersion=0`. Only one thread succeeds in applying version 0; the expected outcome is one HTTP 200, one HTTP 409, and final state at version 1. This is protected by `compareAndSet`, not by the cache.

If adding off-heap side effects such as calling another service, never place those side effects before the atomic check assuming CAS will undo them. Design transactions or task workflows suitable for those side effects themselves.

## 6. Choosing a Consistency Strategy After Write Operations

There are several ways to handle the lag between new state and cached snapshots:

| Need | Potentially Suitable Design | Trade-off |
| --- | --- | --- |
| Summary info tolerates being a few seconds stale | Short TTL, include snapshot timestamp/version | Has an observation lag |
| Must immediately confirm the change just written | Write receipt containing post-update state and version | Receipt only describes that operation's moment |
| Need to read current state at low cost | Cheap uncached read path | Each request still needs permission and load control |
| Expensive result needing coordinated refresh | Application-owned cache/snapshot with explicit refresh | Increases concurrency and failure-handling responsibility |
| Multiple replicas mutating state | Version check at the shared data store | Must consider consistency and transactions of that store |

A read endpoint can return `version` and collection timestamp so operators know which version the data describes. However, never use a version read from a cache to skip checking the true version where the change is applied.

A long TTL does not automatically make write operations safer. Zero TTL does not solve concurrent overwrites either; it only changes read-result reuse policy.

## 7. Protecting Caller Permissions and the Management Surface

### 7.1. Enabling, Exposing, and Authorizing Are Three Separate Steps

An endpoint must be enabled and exposed on the appropriate protocol to be reachable. Adding an ID to `management.endpoints.web.exposure.include` does not grant management permissions and does not establish an allowlist of callers.

In Spring Boot 3.3, when Spring Security is present and no custom `SecurityFilterChain` is declared, auto-configured rules protecting Actuator apply. When declaring a custom filter chain, you take responsibility for the remaining rules; do not let URLs outside your matchers fall out of intended protection. [Endpoint security in Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

Restricting the management address/port and allowed networks reduces exposure surface, but does not replace authentication and authorization. If an endpoint also uses JMX, check JMX permissions and access paths separately; securing HTTP alone does not prove all protocols are secured.

### 7.2. Example Rules for the Experimental Application

The snippet below illustrates a filter chain for an application dedicated solely to this experiment. It requires `spring-boot-starter-security` and an authentication setup providing the `OPS_ADMIN` role; this is an addition, not included in the security-free project in section 5.

```java
package example.opscache;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
public class DemoSecurityConfiguration {
    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers(EndpointRequest.to("opsdemo")).hasRole("OPS_ADMIN")
                .anyRequest().denyAll());
        http.httpBasic(withDefaults());
        return http.build();
    }
}
```

`hasRole("OPS_ADMIN")` checks authority `ROLE_OPS_ADMIN`. The `anyRequest().denyAll()` rule clarifies the policy for remaining URLs in the experimental application. In an application with other features, design rules for those URLs according to their requirements.

This configuration keeps CSRF at its default. Having an account and the right role is not enough for a POST missing a CSRF token to be accepted. When serving browser users, integrate tokens properly per the application's mechanism. Do not disable CSRF globally just so a test POST stops returning 403.

The default CSRF filter skips GET, HEAD, TRACE, and OPTIONS, protecting the remaining methods. Therefore, putting state-changing actions inside GET both violates operation semantics and can bypass protection meant for mutating requests. [CsrfFilter in Spring Security 6.3](https://docs.spring.io/spring-security/site/docs/6.3.4/api/org/springframework/security/web/csrf/CsrfFilter.html).

HTTP Basic in the illustrative snippet is an authentication choice for the experiment, not a justification for transmitting credentials over unprotected connections when deployed on a network. Credentials should come from secret configuration or the environment's identity system, not hardcoded in source or responses.

### 7.3. Audits Must Reflect Real Outcomes

For important changes, audit data typically needs: caller, action, target, timestamp, expected version, outcome, and request/task ID if any. Do not log tokens, passwords, or raw sensitive payloads.

Distinguish at least these cases: permission denied, invalid input, conflict, applied, nothing to change, and accepted but not yet completed. Returning 202 for a task, if the application chooses that model, does not mean the task has completed successfully.

The example in section 5 does not yet have a durable audit log, duplicate-request detection, or state persistence across restarts. Those responsibilities must be designed when moving from a simulated flag to real management operations.

## 8. Checks Before Putting an Endpoint into Production

Test groups should reflect the contract accurately:

| Group | Scenarios to Test |
| --- | --- |
| Cache | First call, cache hit, TTL expired, TTL 0, calls with selector |
| Post-write | Fresh receipt vs. stale snapshot; path to confirm state |
| Concurrency | Two requests with same version; one wins; final state consistent |
| Permissions | Unauthenticated, wrong role, right role; HTTP/JMX access paths if present |
| CSRF | Mutating request missing token, invalid token, valid token |
| Load and errors | Slow source, source failure, connection exhaustion, concurrency cap, oversized response |
| Retries | Lost response after already applied; duplicate ID handling if supported |
| Multiple replicas | Per-JVM caches and version checks at shared store |

When testing caching over the web, send requests through Actuator's mappings, such as MockMvc in a Spring MVC app or real HTTP. A test calling the method directly only tests that method; it proves nothing about caching, security, or HTTP statuses.

For TTL tests, prefer wait intervals with safe margins and inspect execution counters, avoiding millisecond-exact timing assertions. For load measurements, record collection duration, actual execution count, concurrent requests, response size, and downstream load. Measuring HTTP latency only on cache hits hides the cost of recomputation.

## 9. Self-Check Questions

1. **Does a 10-second TTL mean the operation runs in the background every 10 seconds?** No. A request needing the result after expiration triggers the next execution in the mechanism examined here.
2. **Does TTL make POST automatically execute at most once?** No. That is a problem of request retries and effect coordination.
3. **Does GET after POST still returning the old version prove POST failed?** No. Distinguish cached snapshots, write receipts, and state at the backing store.
4. **Does disabling cache prevent two users from overwriting each other?** No. You need atomic check/update or appropriate transactions.
5. **Does AtomicReference protect changes across the entire cluster?** No. It protects a reference within one JVM; shared data needs mechanisms at the shared store.
6. **Is every 403 error caused by the wrong role?** No. CSRF and other rules can also deny requests; inspect the cause without leaking sensitive data in responses.
7. **Can you increase TTL to replace concurrency limits for expensive scans?** No. Concurrent cache misses and response serialization costs still must be addressed.
8. **Can a cached management result be used to skip authentication on subsequent calls?** No. Reusing data does not grant permissions to new requests.
