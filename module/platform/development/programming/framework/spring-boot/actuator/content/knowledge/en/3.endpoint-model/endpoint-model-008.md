# Distinguishing Information-Only Endpoints from State-Changing Endpoints

## 1. From Observing to Controlling an Application

When an application is running, operators have two different needs: knowing how the system currently stands and actively making the system behave differently. Viewing the current log level belongs to the first need; changing the log level to DEBUG belongs to the second.

In Spring Boot Actuator, an endpoint is an identifiable management point, while an operation is a specific action invoked on that point. One endpoint can contain multiple operations. Therefore, you must examine **each operation and its effect**, rather than labeling an entire endpoint "read-only" based solely on its name.

In this lesson, "state" includes effective configuration values, temporary in-memory data, diagnostic buffers, and application lifecycle. Changing state does not necessarily mean updating a database or modifying a config file.

| Criterion | Information-providing operation | State-changing operation |
| --- | --- | --- |
| Main question | How is the system currently doing? | How should the system be adjusted? |
| Purpose | Observe, inspect, diagnose | Issue commands, update, delete, or trigger management actions |
| Example | View the log level of a logger | Set a new log level for that logger |
| Evidence to inspect | Returned data and scope of observed data | Before/after values, actual effect, and recovery method if any |
| Risks to evaluate | Data exposure, cost of collecting data | Risks of reading, plus behavior changes or service disruption |

For example, reading an `enabled` variable does not change its value. Assigning `enabled = true` changes state even though it creates no database record.

## 2. Relationship Between Annotations, HTTP, and Actual Behavior

For an endpoint using `@Endpoint` and exposed over HTTP, Actuator maps operation types as follows:

| Annotation | HTTP method | Intended role |
| --- | --- | --- |
| `@ReadOperation` | `GET` | Provide information |
| `@WriteOperation` | `POST` | Change state or execute a command |
| `@DeleteOperation` | `DELETE` | Delete or remove state per the designed contract |

This mapping belongs to the Actuator endpoint model, not a rule that every REST API must use POST for updates. With JMX, operations are invoked through the JMX management mechanism; there is no HTTP method.

Annotations help the framework route calls. They do not stop a read method body from writing data, do not make a write method transactional, and do not grant administrative permissions. Authors remain responsible for ensuring behavior matches the contract.

Example of a design mistake: a `@ReadOperation` method returns an item count while also calling `queue.clear()`. Even though invoked with GET, it is deleting state. A periodic monitoring tool reading it could accidentally wipe data. You must separate fetching the count and clearing into two distinct operations.

See [Actuator 3.3 operation model and HTTP mapping](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom).

## 3. Identifying via Built-In Endpoints

| Endpoint / call | Operation classification | What to recognize |
| --- | --- | --- |
| `GET /actuator/loggers/{name}` | Read | View configuration and effective log level |
| `POST /actuator/loggers/{name}` | Write | Set or clear the individually configured log level |
| `GET /actuator/startup` | Read | Fetch a snapshot of collected startup steps |
| `POST /actuator/startup` | Write | Fetch data and drain collected events from the buffer |
| `POST /actuator/shutdown` | Write | Request application shutdown |
| `GET /actuator/heapdump` | Diagnostic data read | Capture a heap dump; data can be large |

### 3.1. `loggers`: Same Path, Different Meaning

GET answers "what level does this logger currently have?". POST with the JSON property `configuredLevel` changes the logger's own configured level. Afterward, new log calls may be affected by the configuration just set.

`configuredLevel` is the explicitly set level, whereas `effectiveLevel` is the level actually applied, which may be inherited. Clearing a custom level via POST with `{}` means reverting to inheritance; it does not mean guaranteeing a reset to INFO. [REST contract of the loggers endpoint](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/loggers.html).

### 3.2. `startup`: Returning JSON Can Still Be a Write Operation

GET fetches a snapshot of startup data. POST both returns the collected steps and drains them from the buffer. A response that looks like report data can still come with a state change.

This endpoint requires the application to be configured to collect startup steps using `BufferingApplicationStartup`; adding the endpoint name to the exposure list alone is not enough. This lesson uses it to distinguish behavior, without assuming the endpoint is always present in every application. [GET and POST of the startup endpoint](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/startup.html).

### 3.3. `shutdown`: Changed State Can Be Lifecycle

POST to this endpoint requests stopping the application. There is no requirement that a database table must be altered for an action to count as a write operation. A successful response also does not guarantee the application can still serve subsequent requests. [shutdown endpoint contract](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/shutdown.html).

### 3.4. `heapdump`: Read Operations Still Require Control

The endpoint returns binary heap data, which can be large. Because the heap contains objects currently in memory, you must evaluate the risk of exposing application data when sharing a dump. Generating and transferring the dump also must be evaluated for resource usage; you should not put this call into a frequent polling loop just because it uses GET. The notes on sensitive data and operational cost here are consequences to evaluate from capturing a heap, not a promise of a fixed pause time on every JVM. [Return data of the heapdump endpoint](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/heapdump.html).

## 4. "Read-Only", Safety, and Idempotency

In HTTP semantics, safety means the caller is not requesting a state change. It does not mean the server does nothing: a read can still create access logs or consume resources. Idempotency refers to the intended effect of repeating the same request. [RFC 9110, section 9.2](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2).

You can use the following situations to separate the two concepts:

- Reading an `enabled` flag: two consecutive reads are not intended to alter the flag. The returned value can still differ if another actor updates the flag in between.
- Setting `enabled` to `true`: two assignments of the same value may leave the same final state, yet this is still a write operation.
- Toggling the flag via `enabled = !enabled`: calling twice returns the flag to its previous value. Automatically retrying when it is unclear whether the first call ran can produce unintended results.
- Deleting a custom setting: calling again may cause no further state change, yet that does not turn deletion into a read operation.

The examples of setting and toggling a flag analyze program behavior, not a universal guarantee for every POST. For management operations, you must analyze repeatability, side effects, and concurrent callers.

## 5. Experiment: An Endpoint with Read, Write, and Reset

The following small example runs with Java 21 and Spring Boot 3.3.0. The standalone project uses Maven so learners can copy and run all files; the same principles apply when a Boot application is built with Gradle.

The `maintenance` endpoint holds a flag in memory within one process. This flag is for experimentation only; it does not yet block business requests or put the application into real maintenance mode. Restarting the application creates a fresh flag initialized to `false`.

### 5.1. Creating the Complete Project

Directory structure:

```text
actuator-operation-demo/
├── pom.xml
└── src/main/
    ├── java/example/demo/
    │   ├── EndpointDemoApplication.java
    │   └── MaintenanceEndpoint.java
    └── resources/
        └── application.properties
```

File `pom.xml`:

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
    <artifactId>actuator-operation-demo</artifactId>
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

File `src/main/java/example/demo/EndpointDemoApplication.java`:

```java
package example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class EndpointDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(EndpointDemoApplication.class, args);
    }
}
```

File `src/main/java/example/demo/MaintenanceEndpoint.java`:

```java
package example.demo;

import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.boot.actuate.endpoint.annotation.DeleteOperation;
import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.boot.actuate.endpoint.annotation.WriteOperation;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "maintenance")
public class MaintenanceEndpoint {
    private final AtomicBoolean enabled = new AtomicBoolean(false);

    @ReadOperation
    public Map<String, Boolean> read() {
        return Map.of("enabled", enabled.get());
    }

    @WriteOperation
    public void write(boolean enabled) {
        this.enabled.set(enabled);
    }

    @DeleteOperation
    public void reset() {
        this.enabled.set(false);
    }
}
```

`read()` only retrieves the value. `write(boolean enabled)` assigns the requested value. `reset()` removes custom state by resetting the flag to default `false`; that is the meaning of DELETE defined by this example, not a rule that DELETE must always set `false`.

`AtomicBoolean` provides proper cross-thread visibility when reading and setting a single flag. It does not solve multi-step transactions, authorization, durable storage, or synchronization across multiple application replicas.

File `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=8080
management.endpoints.web.exposure.include=health,maintenance
management.endpoint.maintenance.cache.time-to-live=0ms
```

The sample adds no Spring Security and listens only on loopback for local experimentation. The configuration does not expose all endpoints. `cache.time-to-live=0ms` makes explicit the intent not to cache previous read results in the experiment.

The JSON input `enabled` is mapped to the parameter of the same name on the write method. Parameter name information must be retained during compilation (`-parameters`); Maven configuration using `spring-boot-starter-parent` already sets this up.

### 5.2. Starting Up and Calling Sequentially

Select JDK 21 for `JAVA_HOME`, check `java -version` and `mvn -version`, then run in the directory containing `pom.xml`:

```shell
mvn spring-boot:run
```

Open another command-line window and run the commands below in order. On Windows PowerShell, use `curl.exe` instead of `curl` if `curl` is an alias. The commands contain no JSON, so they do not depend on how the shell handles JSON quotes.

**Step 1 — read initial state:**

```shell
curl -sS http://127.0.0.1:8080/actuator/maintenance
```

Response body:

```json
{"enabled":false}
```

Repeating GET still shows `false` if no other actor updates it. You should not simply compare two different responses and conclude that the read operation wrote data.

**Step 2 — request changing the flag:**

```shell
curl -i -X POST -H "Content-Type: application/json" "http://127.0.0.1:8080/actuator/maintenance?enabled=true"
```

In the example configuration, Actuator reads the simple parameter from the query string and calls `write(true)`. The `Content-Type: application/json` header satisfies the input requirement of this POST operation, even when the example passes the parameter via the URL. The response has status `204 No Content` with no body because the Java method returns `void`. Headers depend on the server and do not need to match byte for byte.

You can also pass the value via JSON with `Content-Type: application/json` and body `{"enabled":true}`. Both ways are POST and both request changing the flag; where the parameter sits does not determine whether this is a read or write operation.

**Step 3 — read again to confirm the effect:**

```shell
curl -sS http://127.0.0.1:8080/actuator/maintenance
```

Response body:

```json
{"enabled":true}
```

**Step 4 — reset state:**

```shell
curl -i -X DELETE http://127.0.0.1:8080/actuator/maintenance
curl -sS http://127.0.0.1:8080/actuator/maintenance
```

DELETE returns `204 No Content`; the subsequent GET returns:

```json
{"enabled":false}
```

**Step 5 — test invalid input:**

```shell
curl -i -X POST -H "Content-Type: application/json" http://127.0.0.1:8080/actuator/maintenance
```

Because the required `enabled` parameter is missing, the response is `400 Bad Request`; the `write` method is not invoked. Call GET to confirm the flag is still `false` after the sequence above. There is no need to rely on a fixed error JSON structure because that structure can vary depending on the application's error handling.

When finished, stop the application with Ctrl+C in the window running Maven.

### 5.3. Reading Results by Effect

| Call in order | Flag value before → after | Main result |
| --- | --- | --- |
| GET | `false` → `false` | `200`, returns `{"enabled":false}` |
| POST with `enabled=true` | `false` → `true` | `204`, no response body |
| GET | `true` → `true` | `200`, returns `{"enabled":true}` |
| DELETE | `true` → `false` | `204`, no response body |
| POST missing `enabled` | `false` → `false` | `400`, write method not executed |

An empty response does not mean there was no effect: both POST and DELETE in the example return `204` yet changed the flag. Conversely, returning a JSON object does not prove an operation is read-only, as in the `startup` POST case.

## 6. Applying to Operational Configuration

In Boot 3.3, `enabled` determines whether an endpoint is enabled; `exposure` configuration determines exposure over HTTP/JMX. Only `health` is exposed by default over both channels; `shutdown` is disabled by default. Enabling or exposing an endpoint does not replace authentication and authorization. When Spring Security is present, write requests are also subject to CSRF checks per the security configuration. [Endpoint configuration and security in Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.security).

When deciding permissions, start from actual operational needs:

1. Which data do monitoring tools need, and do they need detailed data?
2. Which commands do on-call operators need, and is the impact scoped to one process or the whole system?
3. After a write command, how is the effect verified and how is it rolled back?
4. If a command is retried due to timeout, or invoked concurrently, what happens?

For an endpoint with both read and write like `loggers`, granting a group read permission does not mean that group needs permission to change log levels. Policies should distinguish operations. This is a permission design guideline; `exposure.include` alone does not express full read/write policies.

Error codes must also be interpreted in context. `404` may be due to an unexposed endpoint or mismatched path; `401`/`403` may relate to authentication, authorization, or CSRF; `400` may be due to invalid input; `415` may be due to an unaccepted `Content-Type`. A single error code does not prove an endpoint is read-only or write-capable. You must consult configuration and the operation contract.

## 7. Common Mistakes and Fixes

| Misconception | How to check or fix |
| --- | --- |
| "Actuator is only for viewing info" | Check each operation; there are also config-changing and lifecycle commands |
| "An endpoint named like a report does not write" | Check each method's contract; POST `startup` also drains events from the buffer |
| "With `@ReadOperation`, the framework forbids mutating data" | Inspect the method body; the annotation does not enforce pure read behavior |
| "If it does not modify a database, it does not change state" | Check memory, effective configuration, caches, and lifecycle as well |
| "Getting 204 means nothing happened" | Use a read operation or other observational evidence to check post-command state |
| "Every write operation returns 204" | In the example, 204 goes with a `void` method; operations returning result data can return 200 |
| "GET is always lightweight and safe to make public" | Evaluate data sensitivity and collection cost separately |
| "Retrying a command is definitely harmless" | Analyze value assignment, toggling, deletion, and side effects before adding retries |
| "If POST succeeds, all application replicas change" | Identify where state lives; the flag in the example lives only in the receiving process |

## 8. Self-Check

**Question 1.** An operation returns the number of items in a queue and then removes those items. Can it be considered information-only?

**Answer:** No. It also destroys existing state. If you need to read without losing data, separate the observation operation from the operation that pops and removes data.

**Question 2.** Setting the flag to `true` twice yields the same final state. Why is it still a write operation?

**Answer:** The caller is requesting a value update. Repeating it yielding the same final outcome relates to idempotency of the designed behavior; it does not change the write intent.

**Question 3.** After a POST changing the flag, GET returns a different value than before. What must you check before concluding the experiment succeeded?

**Answer:** Confirm you called the right process and path, no other actor updated it, and you are not reading a cached result. The example sets cache time-to-live to 0 to make observation clear.

**Question 4.** Should an account that only needs to view log levels automatically be granted permission to set DEBUG?

**Answer:** No. Observing and controlling are two different permission needs. Control permissions can alter log volume and affect operations.

**Question 5.** In the example, does DELETE remove the `maintenance` endpoint from Actuator?

**Answer:** No. It calls `reset()` to set the flag to `false`; the endpoint still exists and GET still works. What "delete" means is defined by the operation's contract.
