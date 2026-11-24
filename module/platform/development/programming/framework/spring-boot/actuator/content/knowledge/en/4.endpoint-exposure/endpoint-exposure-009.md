# Configuring cache.time-to-live for Eligible Read Operations

## 1. What Problem Does Caching Read Results Solve?

A management endpoint may have to aggregate data or build a report before responding. If many consecutive read requests re-run that same work, cost can rise while operators do not need data fresh to the millisecond.

Result caching allows reusing a generated result for a period of time. **Time to live (TTL)** specifies how long that result remains considered valid. In return, readers may receive a stale snapshot within that window.

In Actuator, the `cache.time-to-live` property configures retaining results for **eligible read operations**. It is not a switch turning every GET request in the application into a cached request.

This article uses Spring Boot 3.3.x; the experimental program and input cases below are tested with Boot 3.3.0 and Java 21.

## 2. Configuring the Right Endpoint and Duration

Example setting TTL for the `beans` endpoint:

```properties
management.endpoint.beans.cache.time-to-live=10s
```

In YAML:

```yaml
management:
  endpoint:
    beans:
      cache:
        time-to-live: "10s"
```

`management.endpoint` here uses **singular `endpoint`**, followed by the specific ID. Do not use the path `/actuator/beans` as part of the property name. HTTP exposure configuration belongs to a different branch, such as `management.endpoints.web.exposure.include`.

Boot documentation describes the basic case as a read operation without parameters; this property sets how long that endpoint's result is retained. [Configuring Endpoint Caching in Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.configuring).

| Illustrative value | Meaning |
| --- | --- |
| `500ms` | Half a second |
| `5s` | Five seconds |
| `1m` | One minute |
| `0ms` | Does not retain results via this TTL mechanism |

Explicitly specify units to avoid confusion when migrating configuration or reading it later. In YAML, `"5s"` is parsed as a duration string; the quotes are not part of the value after YAML parsing.

Standard TTL properties such as `management.endpoint.beans.cache.time-to-live` default to `0ms`. Therefore, an operation being cache-eligible does not mean it is retaining results with a positive TTL. [Defaults of Actuator 3.3 Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html).

### 2.1. Configuring TTL Does Not Automatically Expose the Endpoint

The following two lines handle two separate concerns:

```properties
management.endpoints.web.exposure.include=health,beans
management.endpoint.beans.cache.time-to-live=10s
```

The first line selects endpoints to expose over HTTP. The second configures how long eligible read results of `beans` are kept. TTL does not enable a disabled endpoint, add missing libraries, or replace access permissions.

### 2.2. Setting TTL to 0 to Observe Fresh Data Through the Operation

```properties
management.endpoint.beans.cache.time-to-live=0ms
```

This configuration does not retain result snapshots via the Actuator operation TTL cache. It does not promise that the underlying source data inside the application lacks another caching layer.

Under the experimental project's typical setup, the TTL value is read when initializing the endpoint mechanism. Editing the source file and continuing to call the old process is not a way to test a new TTL setting; rebuild if the file is inside a JAR and restart the application.

## 3. Understanding "Eligible Read Operations" Properly

The most recognizable case is a `@ReadOperation` method with no business inputs. If TTL is positive, the result can be reused for matching calls while still valid.

However, you should not classify solely by "is it GET?" or "how many parameters does the Java signature have?". In Boot 3.3.0, the execution mechanism also considers required parameters, actual call inputs, and framework-provided context.

| Operation / input type | Behavior to understand in Boot 3.3.0 |
| --- | --- |
| `@ReadOperation` with no business input | Basic case that can cache when TTL is positive |
| Read operation with a required business parameter, like `@Selector String key` | Not turned by this mechanism into a per-key cache |
| Read operation with an optional parameter, no value passed | Can use the cache for calls with no business input |
| Same optional operation, yet a value is passed | Calls with that input execute directly, not reusing the no-input cached snapshot |
| `@WriteOperation` or `@DeleteOperation` | Read TTL does not cache results to skip executing write/delete commands |

For example, a test operation with a `@Nullable String filter` parameter and a positive TTL yields the following observations:

```text
GET without filter            → executes method (call 1)
GET without filter            → reuses result from call 1
GET with filter=blue          → executes method (call 2)
GET with filter=blue again    → executes method (call 3)
GET without filter            → can still use cached result from call 1 if within TTL
```

This is the behavior of the standard mechanism tested with Boot 3.3.0, not a cache that generates keys for every parameter combination. Do not conclude that adding `@Nullable` makes every parameterized call cached.

### 3.1. Caller Context Must Also Be Kept Consistent When Testing

Boot 3.3.0's cache mechanism also distinguishes contexts such as caller and Actuator API version. Therefore, do not assume every user and every call form share a single cache entry.

When testing TTL effectiveness, keep the endpoint, caller, request format, and inputs constant. If those factors change simultaneously, the method running again is not enough to prove TTL is not working. In particular, do not claim that having authentication disables all read caching either.

## 4. TTL Operates On-Demand, Not on a Background Schedule

For an eligible call with the same context:

```text
No valid result yet
  → execute read operation
  → retain result

Valid result within TTL
  → reuse result

Result expired and new request arrives
  → execute read operation to create new result
```

TTL does not mean the framework executes the method every N seconds on a timer. If no new request arrives after the result expires, there is no reason from this mechanism to build a new report simply because time elapsed.

In Boot 3.3.0, reusing an unexpired result does not reset its age timestamp. This is not a sliding expiration based on the last read.

Example assuming fast computation, 5-second TTL, and calls sharing the same context:

| Relative time | Event | Result |
| --- | --- | --- |
| `t=0` | First read | Creates result snapshot A |
| `t=1s` | Read again | Uses A |
| `t=3s` | Read again | Still uses A; does not extend expiry by 5 seconds from this point |
| `t=5.5s` | Next read request arrives | A has expired, creates result snapshot B |

These timestamps illustrate the mechanism, not a millisecond-exact scheduling guarantee. Do not design operational checks that rely on results changing right on a clock boundary.

## 5. Write Operations Do Not Guarantee Immediate Reading of New Data

Suppose the first read creates a snapshot of value 100 and retains it for 5 seconds. Then a POST changes the source data to 200.

In the standard mechanism tested with Boot 3.3.0, the POST does not automatically evict the still-valid cached read result. A subsequent GET may still return 100 until the cache entry expires and a new read is performed.

```text
Read source = 100 → caches snapshot 100
Write source = 200 → source data changed
Read within TTL    → may still receive snapshot 100
Read after TTL     → creates new snapshot from source 200
```

Therefore, TTL must be chosen according to data freshness requirements. For information that must be confirmed immediately after a management command, a TTL of 0 or an appropriate verification mechanism may be necessary. Do not assume a GET immediately after a POST is proof of reading directly from the source.

## 6. Experimenting with a Snapshot-Creating Endpoint

The project below runs standalone with Java 21, Gradle 8.5, and Spring Boot 3.3.0. No Spring Security is added; the server listens only on loopback for local experimentation. The first build needs to download plugins and libraries.

`snapshot` has an initial source value of 100. When the read method actually runs, it increments a `sequence` counter and creates an immutable result snapshot. The counter only serves to observe the computation count in the experiment; it does not represent a business data mutation command.

### 6.1. Creating the Files

```text
actuator-ttl-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/lab/ttl/
    │   ├── TtlApplication.java
    │   └── SnapshotEndpoint.java
    └── resources/application.properties
```

File `settings.gradle`:

```groovy
rootProject.name = 'actuator-ttl-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}

tasks.named('bootJar') {
    archiveFileName = 'actuator-ttl-demo.jar'
}
```

File `src/main/java/lab/ttl/TtlApplication.java`:

```java
package lab.ttl;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TtlApplication {
    public static void main(String[] args) {
        SpringApplication.run(TtlApplication.class, args);
    }
}
```

File `src/main/java/lab/ttl/SnapshotEndpoint.java`:

```java
package lab.ttl;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.boot.actuate.endpoint.annotation.WriteOperation;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "snapshot")
public class SnapshotEndpoint {
    private final AtomicInteger sequence = new AtomicInteger();
    private final AtomicInteger value = new AtomicInteger(100);

    @ReadOperation
    public Snapshot read() {
        return new Snapshot(sequence.incrementAndGet(), value.get());
    }

    @WriteOperation
    public void update(int value) {
        this.value.set(value);
    }

    public record Snapshot(int sequence, int value) {
    }
}
```

`read()` takes no business parameters and returns a new `record`. When the cache reuses the old record, `sequence` in the JSON does not increment. `update(int value)` changes the source value, without mutating previously created records.

Using an immutable result helps the experiment separate source data from the cached snapshot. If a mutable object were returned and that same object continued to be modified, observing stale vs. fresh data would be harder to interpret.

File `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=8080

management.endpoints.web.exposure.include=health,snapshot
management.endpoint.snapshot.cache.time-to-live=5s
```

You do not need `@EnableCaching`, `@Cacheable`, Redis, or Caffeine to use Actuator's operation result caching mechanism in this example.

### 6.2. Building and Starting

Check JDK/Gradle, then run in the directory containing `build.gradle`:

```shell
gradle bootJar
java -jar build/libs/actuator-ttl-demo.jar
```

Keep that process running. Do not open any tool that automatically polls the `snapshot` endpoint before the test, as it could populate the first cache entry and shift the observed sequence numbers.

### 6.3. Testing the Read → Write → Read After TTL Sequence

The following block is for **PowerShell on Windows**. Copy and run the entire block in another window so the initial calls fall within the same TTL window. `curl.exe` avoids the case where `curl` is a PowerShell alias. Each `-w` option adds a newline or prints the HTTP status code.

```powershell
curl.exe -sS -w "\n" http://127.0.0.1:8080/actuator/snapshot
curl.exe -sS -w "\n" http://127.0.0.1:8080/actuator/snapshot
curl.exe -sS -o NUL -w "%{http_code}\n" -X POST -H "Content-Type: application/json" "http://127.0.0.1:8080/actuator/snapshot?value=200"
curl.exe -sS -w "\n" http://127.0.0.1:8080/actuator/snapshot
Start-Sleep -Seconds 6
curl.exe -sS -w "\n" http://127.0.0.1:8080/actuator/snapshot
```

From a fresh process, with no other calls and the first calls completing before the 5-second TTL expires, the output content is:

```text
{"sequence":1,"value":100}
{"sequence":1,"value":100}
204
{"sequence":1,"value":100}
{"sequence":2,"value":200}
```

Step-by-step explanation:

1. The first GET executes `read()`, creating a record with `sequence=1`, `value=100`.
2. The next GET reuses that record, so the sequence number stays 1.
3. POST updates the source to 200 and returns 204 because the write method returns `void`.
4. GET within TTL still reuses the record with value 100.
5. After waiting past TTL, GET executes `read()` again, creating a record with sequence 2 and value 200.

The `Content-Type: application/json` header in POST satisfies the write operation's input requirement; the simple `value` in the example is passed via query string. This is still a write command, not a cached read operation.

If the runner pauses too long between commands or another tool calls the endpoint, sequence numbers may differ. In that case, re-check timing and running processes before concluding there is a cache bug.

### 6.4. Comparing Against TTL of 0

Stop the previous process with Ctrl+C, then run the same JAR with an override argument:

```shell
java -jar build/libs/actuator-ttl-demo.jar --management.endpoint.snapshot.cache.time-to-live=0ms
```

Make two consecutive GET calls:

```powershell
curl.exe -sS -w "\n" http://127.0.0.1:8080/actuator/snapshot
curl.exe -sS -w "\n" http://127.0.0.1:8080/actuator/snapshot
```

From a fresh process with no intervening calls:

```text
{"sequence":1,"value":100}
{"sequence":2,"value":100}
```

The source value did not change yet `sequence` incremented, showing the read method was executed twice.

## 7. Scope and Limitations of This Cache

| Easy misconception | Actual scope |
| --- | --- |
| Browser, proxy, or CDN caching | This TTL belongs to Actuator operation execution on the application side; it is not a `Cache-Control: max-age` header for all HTTP responses |
| Business caching via Spring Cache | This is a different mechanism from `@Cacheable` and `spring.cache.*` configuration |
| `caches` endpoint | Do not assume operations managing business caches act as eviction commands for Actuator's TTL snapshots |
| Cache shared across multiple application instances | Each application process/context has its own memory and cached snapshots; this TTL does not create a shared store across machines |
| Lock preventing multiple concurrent computations | Do not use TTL as a guarantee that concurrent requests only run the method once |

The example in this article sends sequential requests. When evaluating real load, consider multiple callers, multiple application instances, and simultaneous cache misses. Two sequential requests reusing one snapshot does not prove the entire system executes at most once per TTL interval.

Caching also does not replace access control. An HTTP request still passes through security processing layers applied to the application; TTL configuration is not a way to allow unauthorized users to read data.

## 8. Choosing a TTL and Diagnosing Unexpected Results

Weigh three factors together: cost of computing the result, read frequency, and how much update lag users can tolerate. Reports expensive to aggregate that change rarely may suit a positive TTL; information needed immediately for verification after a change requires tighter freshness control.

TTL is not an absolute freshness guarantee for the entire system: source data may already be aggregated or cached in another layer. Before increasing TTL to reduce load, know what point in time the snapshot represents.

When results do not change or the method keeps re-running, check in order:

1. **Right property and ID:** `management.endpoint.snapshot.cache.time-to-live`, not confused with the `endpoints.web` branch or path name.
2. **Right effective value:** is TTL positive, or overridden by a profile or startup argument?
3. **Right operation:** are you actually calling an Actuator read operation, or an ordinary GET controller?
4. **Right inputs and context:** is a required business parameter or optional value passed; did the caller change?
5. **Right timing and process:** has TTL elapsed; are you calling the same application instance or going through a load balancer?
6. **Right cache layer:** does stale data come from Actuator or another component in the app, a proxy, or a browser?

Do not use two identical JSON payloads as the sole proof of caching: the method can run twice and still return the same data. The `sequence` counter in the experiment helps observe the actual computation count.

## 9. Common Mistakes

| Incorrect assumption | Correct understanding or fix |
| --- | --- |
| "Every GET is cached" | Check Actuator operation type and input conditions; controller GETs are not automatically covered by this property |
| "Having TTL in the file means caching is active" | Check effective TTL; `0ms` does not retain results via this mechanism |
| "All methods with parameters behave identically" | Distinguish required parameters, optional parameters, and framework context; inspect actual inputs too |
| "Calling continuously keeps the cache from expiring" | Cache hits do not extend expiry like sliding expiration in Boot 3.3.0 |
| "On expiry, a background task refreshes automatically" | A new read request after expiration is what triggers creating a new result |
| "After POST succeeds, GET definitely sees the written data" | An unexpired cached read snapshot may still be reused |
| "Increasing TTL exposes more endpoints" | Exposure and TTL are two separate configurations |
| "A repeated sequence number means all instances share a cache" | Check per process and context; TTL does not create a distributed cache |

## 10. Self-check

**Question 1.** A read method has no parameters, yet the effective TTL is `0ms`. Are two consecutive GETs expected to skip the second execution?

**Answer:** No. Eligibility does not replace the positive TTL requirement; with `0ms`, this result cache does not retain read snapshots.

**Question 2.** TTL is 5 seconds. Does reading again at second 3 automatically extend the snapshot by another 5 seconds?

**Answer:** Not under the standard mechanism tested with Boot 3.3.0. A cache hit does not reset the snapshot's age timestamp.

**Question 3.** Why can a GET after a successful POST still return the old value?

**Answer:** The POST changed the source, yet the cached read snapshot has not expired; the write operation does not automatically guarantee invalidating that cached snapshot.

**Question 4.** Do an omitted optional parameter and the same parameter passed as `filter=blue` necessarily use caching the same way?

**Answer:** No. In Boot 3.3.0, the call with no business input can cache, whereas the call with a filter value executes directly; this is not a cache keyed by every filter value.

**Question 5.** Are two GETs returning identical JSON enough to prove caching is occurring?

**Answer:** Not yet. Additional evidence of execution count or appropriate instrumentation is needed. Unchanged source data can also make two separate computations return identical results.

**Question 6.** Do you need to add `@EnableCaching` and a Redis server to run this example?

**Answer:** No. The example uses Actuator's operation result cache and does not require that business caching infrastructure.
