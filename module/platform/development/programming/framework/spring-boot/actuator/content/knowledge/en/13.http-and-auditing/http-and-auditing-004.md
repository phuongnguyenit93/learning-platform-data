# Selecting Recorded Request, Response, and Timing Information

## 1. Record enough to answer the question while knowing what data is retained

Suppose an API returns inconsistent errors. You want to know the HTTP method, path, response code, and processing duration. In another situation, you need to check `Accept` on the request and `Content-Type` on the response to diagnose a content-negotiation bug.

Those two questions require different sets of information. If you always record every header, the buffer may hold authentication credentials, cookies, or custom keys. If you drop timing information while still intending to investigate latency, the record lacks the needed evidence.

In Spring Boot Actuator, **selecting recorded information** is a decision made when creating an HTTP exchange record: which data groups of the request, response, and timing to retain. It differs from granting someone read access to the endpoint, bounding the record count, or choosing which requests to store.

This lesson uses the `HttpExchangeRepository` and `management.httpexchanges.recording.include` mechanism of **Spring Boot 3.3.x**. Do not use the `httptrace` endpoint configuration names from older Boot generations. [Spring Boot 3.3: Recording HTTP Exchanges](https://docs.spring.io/spring-boot/3.3/reference/actuator/http-exchanges.html).

## 2. Distinguishing baseline information from selectable information

An `HttpExchange` describes a request–response pair. Baseline fields such as start timestamp, method, URI, and response status identify the exchange being described.

Additional groups are selected using the `Include` set:

| Name in YAML | Java constant | Selected data | Considerations |
| --- | --- | --- | --- |
| `request-headers` | `REQUEST_HEADERS` | Request header group, with rules excluding certain headers | May contain sensitive custom headers |
| `response-headers` | `RESPONSE_HEADERS` | Response header group, with rules excluding cookies | May leak details via application headers |
| `time-taken` | `TIME_TAKEN` | Processing duration measured by the recorder | Not CPU time or total network time |
| `principal` | `PRINCIPAL` | Identity name attached to the exchange, if present | User-related data; not a copy of the full authentication object |
| `remote-address` | `REMOTE_ADDRESS` | Sender address as seen by the application | May be a proxy; requires understanding the observation point |
| `session-id` | `SESSION_ID` | Session identifier provided by the integration layer, if present | Sensitive identifier; not needed for every API |
| `authorization-header` | `AUTHORIZATION_HEADER` | Allows retaining the `Authorization` header when recording request headers | May hold actual authentication credentials |
| `cookie-headers` | `COOKIE_HEADERS` | Allows retaining `Cookie` on requests and `Set-Cookie` on responses in the respective groups | May hold sensitive session and cookie data |

YAML names use lowercase with hyphens; Java code uses uppercase enum names. These are selections by **data group**, not an arbitrary list of header names. [Spring Boot 3.3 Include API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/web/exchanges/Include.html).

There are no standard options named `request-body`, `response-body`, `all`, or `time-taken-ms` in this enum. Do not add them to YAML expecting Boot to store payloads or change time units.

### Default does not mean every field is recorded

The default set verified in the 3.3 branch in the example is:

```text
TIME_TAKEN
REQUEST_HEADERS
RESPONSE_HEADERS
```

When recording the default header groups:

- `Authorization` and `Cookie` are not retained in request headers.
- `Set-Cookie` is not retained in response headers.
- Other headers may still be retained, including custom headers carrying keys or private information.

This is a rule that excludes specific header names, not a mechanism that detects every secret. For example, `X-Api-Key` is not automatically masked merely because its value is an access key.

## 3. Choosing an include set intentionally

### 3.1. Configuration that retains only extra duration

When you only need method, URI, status, and duration, you can choose:

```yaml
management:
  httpexchanges:
    recording:
      include:
        - time-taken
```

This declared list **replaces the default set**; it does not append `time-taken` to the two default header groups.

With the configuration above, baseline information is still retained, while the header maps contain no selected data. Do not interpret "only time-taken" as a record containing nothing but a single timing number.

In particular, the URI can still contain a query string. Omitting `request-headers` does not make a token in the URL disappear.

### 3.2. Adding the two header groups to inspect protocol behavior

If investigating which format a client sends or receives:

```yaml
management:
  httpexchanges:
    recording:
      include:
        - time-taken
        - request-headers
        - response-headers
```

This set is suitable for observing fields like `Accept` and `Content-Type`, though it also selects other headers in the groups after applying specific name-exclusion rules.

The following configuration is **not** a way to record only two headers:

```text
include: [Accept, Content-Type]
```

`Accept` and `Content-Type` are not values of the `Include` enum. If you need a custom header allowlist, you must have a custom layer processing data under that policy; the standard `include` property does not provide per-header-name filtering.

### 3.3. Selecting identity details only when genuinely needed

For example, when correlating errors with an authenticated identity without needing to read headers:

```yaml
management:
  httpexchanges:
    recording:
      include:
        - time-taken
        - principal
```

`principal` is meaningful only when the integration layer has an identity to supply. Enabling the flag does not authenticate users, grant roles, or guarantee every record contains a principal name.

Similarly, `session-id` records a session ID only if one exists. Stateless APIs may not have that value. Do not add sessions just to make a diagnostic field appear.

`remote-address` is the address from the application's viewpoint, which may be a proxy address. Trusting forwarded headers must rely on trusted proxy configuration; do not treat a client-supplied address as proof of identity.

### 3.4. Avoid enabling credential data just for "completeness"

`authorization-header` and `cookie-headers` are options with a clear impact on sensitive data. They extend the behavior of the corresponding header groups; they should not be enabled as part of routine observability configuration merely to see every field.

If the problem is an expired token, you can usually log a controlled reason code or appropriate authentication outcome instead of storing the raw token. If sessions must be distinguished, evaluate a dedicated diagnostic identifier approach instead of distributing session IDs.

Do not put real tokens, cookies, or user data into test examples.

## 4. Timestamp and duration answer two different questions

### Timestamp: when did the exchange start?

`timestamp` is the start time recorded by the recording mechanism. It is useful for correlating with logs and data from other systems.

A value such as:

```text
2024-01-01T00:00:00Z
```

is a UTC point in time. It does not tell you how long the request lasted.

### Time taken: how long did the recorder observe?

When `time-taken` is included, the `timeTaken` field represents duration. For example:

```text
PT0.125S = 0.125 seconds = 125 milliseconds
```

Do not misread `PT0.125S` as 0.125 milliseconds. In Java, the corresponding type is `Duration`; when writing processing tools, parse it using duration APIs rather than slicing strings by position. [`httpexchanges` Data API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/httpexchanges.html).

If `time-taken` is not selected, no duration is present in the model built for that selection. This does not mean the request took 0 ms. How an absent value is represented in JSON also depends on serialization; distinguish unrecorded data from a measured value of 0.

### Do not over-extrapolate measurement scope

This duration is not:

- Total CPU time consumed.
- All DNS, connection, and network time from the user's device.
- Individual SQL query times or downstream service times.
- A p95/p99 percentile of overall traffic.

Recording boundaries depend on the Servlet/WebFlux integration layer and the actual execution path. With asynchronous processing or streaming responses, verify when the recorder considers an exchange finished; do not extrapolate from a short synchronous request to every response type.

The Java example below uses two fixed `Clock` instances to verify an exact duration of 125 ms. That is a model verification technique, not a benchmark or guarantee about clock precision in a running application.

## 5. Java experiment verifying each selection

### Preparing a test project with no HTTP server

The program uses `HttpExchange.start(...).finish(...)` directly with synthetic data. It sends no real requests, opens no network ports, and creates no login sessions.

The experiment uses Spring Boot 3.3.0 to reproduce the verified API and results, along with Java 17 or later. Create `pom.xml`:

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
    <artifactId>exchange-selection-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-actuator</artifactId>
        </dependency>
    </dependencies>
</project>
```

Save the code at `src/main/java/ExchangeSelectionDemo.java`:

```java
import java.net.URI;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.EnumSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import org.springframework.boot.actuate.web.exchanges.HttpExchange;
import org.springframework.boot.actuate.web.exchanges.Include;
import org.springframework.boot.actuate.web.exchanges.RecordableHttpRequest;
import org.springframework.boot.actuate.web.exchanges.RecordableHttpResponse;

public class ExchangeSelectionDemo {
    private static final Instant START = Instant.parse("2024-01-01T00:00:00Z");

    private static final RecordableHttpRequest REQUEST = new RecordableHttpRequest() {
        public URI getUri() {
            return URI.create("https://example.test/orders/42?view=summary");
        }
        public String getRemoteAddress() {
            return "192.0.2.10";
        }
        public String getMethod() {
            return "GET";
        }
        public Map<String, List<String>> getHeaders() {
            return Map.of(
                    "Accept", List.of("application/json"),
                    "Authorization", List.of("Bearer demo-token"),
                    "Cookie", List.of("sid=demo"),
                    "X-Api-Key", List.of("demo-key"));
        }
    };

    private static final RecordableHttpResponse RESPONSE = new RecordableHttpResponse() {
        public int getStatus() {
            return 200;
        }
        public Map<String, List<String>> getHeaders() {
            return Map.of(
                    "Content-Type", List.of("application/json"),
                    "Set-Cookie", List.of("sid=demo; HttpOnly"));
        }
    };

    public static void main(String[] args) {
        show("defaults", record(Include.defaultIncludes()));

        HttpExchange minimal = record(EnumSet.of(Include.TIME_TAKEN));
        show("minimal", minimal);
        System.out.println("minimal.uri=" + minimal.getRequest().getUri());

        show("identity", record(EnumSet.of(
                Include.TIME_TAKEN, Include.PRINCIPAL,
                Include.REMOTE_ADDRESS, Include.SESSION_ID)));

        HttpExchange noTime = record(EnumSet.noneOf(Include.class));
        System.out.println("noTime.timeTaken=" + noTime.getTimeTaken());
    }

    private static HttpExchange record(Set<Include> includes) {
        Clock begin = Clock.fixed(START, ZoneOffset.UTC);
        Clock end = Clock.fixed(START.plusMillis(125), ZoneOffset.UTC);
        return HttpExchange.start(begin, REQUEST).finish(
                end, RESPONSE, () -> () -> "demo-user", () -> "demo-session", includes);
    }

    private static void show(String label, HttpExchange exchange) {
        System.out.println(label + ".requestHeaders="
                + new TreeSet<>(exchange.getRequest().getHeaders().keySet()));
        System.out.println(label + ".responseHeaders="
                + new TreeSet<>(exchange.getResponse().getHeaders().keySet()));
        System.out.println(label + ".timeTaken=" + exchange.getTimeTaken());
        System.out.println(label + ".identity="
                + (exchange.getPrincipal() != null) + "/"
                + (exchange.getRequest().getRemoteAddress() != null) + "/"
                + (exchange.getSession() != null));
    }
}
```

All tokens, cookies, identities, and addresses in the program are dummy data. The program prints only header **names** and presence flags, not header values.

### Compiling and running

With Maven and JDK 17 or later:

```bash
mvn -q compile dependency:copy-dependencies
```

On Windows PowerShell:

```powershell
java -cp 'target/classes;target/dependency/*' ExchangeSelectionDemo
```

On Linux/macOS:

```bash
java -cp 'target/classes:target/dependency/*' ExchangeSelectionDemo
```

The classpath separator on Windows is `;`, and on Linux/macOS it is `:`. Maven needs access to dependencies if they are not already cached.

Exact stdout:

```text
defaults.requestHeaders=[Accept, X-Api-Key]
defaults.responseHeaders=[Content-Type]
defaults.timeTaken=PT0.125S
defaults.identity=false/false/false
minimal.requestHeaders=[]
minimal.responseHeaders=[]
minimal.timeTaken=PT0.125S
minimal.identity=false/false/false
minimal.uri=https://example.test/orders/42?view=summary
identity.requestHeaders=[]
identity.responseHeaders=[]
identity.timeTaken=PT0.125S
identity.identity=true/true/true
noTime.timeTaken=null
```

In the `identity` line, the three booleans indicate whether principal, remote address, and session are present, respectively. `TreeSet` is used when printing header names so stdout ordering is deterministic and independent of `Map` iteration order.

### Reading the output as concrete conclusions

| Result | What was proven |
| --- | --- |
| Defaults leave only `Accept` and `X-Api-Key` on request | Specific auth/cookie header names are filtered, but not every header that might carry a secret |
| Defaults leave only `Content-Type` on response | `Set-Cookie` is not selected by the default set |
| Minimal set has empty header lists | Selecting only `TIME_TAKEN` does not retain either header group |
| Minimal set URI still contains `?view=summary` | Omitting headers does not simultaneously strip the query string |
| Identity set produces `true/true/true` | Identity flags record data provided by the suppliers in the experiment |
| Set without `TIME_TAKEN` returns `null` in Java | Unrecorded duration differs from a measured duration of 0 |

Do not use the dummy suppliers in this program as a way to implement authentication in a real application. The web integration layer must supply context from the active request according to configured security and session mechanisms.

Constructing a record via the full constructor in a custom repository does not automatically reapply the `Include` set. If you build or reload records yourself, you must ensure the data already complies with the desired selection/sanitization policy.

## 6. Applying in a Spring Boot application

### A receiver for records is required

For a web application with Actuator, you can declare a repository for development:

```java
package example.httpcapture;

import org.springframework.boot.actuate.web.exchanges.HttpExchangeRepository;
import org.springframework.boot.actuate.web.exchanges.InMemoryHttpExchangeRepository;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class HttpExchangeStorageConfiguration {

    @Bean
    HttpExchangeRepository httpExchangeRepository() {
        var repository = new InMemoryHttpExchangeRepository();
        repository.setCapacity(50);
        return repository;
    }
}
```

This snippet is configuration integrated into a Spring Boot application with a web stack; it does not belong to the standalone program above.

Next, choose the `include` set in application configuration, such as `[time-taken]` to start with minimal extra data. The `httpexchanges` endpoint only reads the records currently held by the repository; HTTP access also requires appropriate exposure and read permissions.

A capacity of 50 means **50 records**, not 50 seconds, 50 MB, or a per-URI limit. An in-memory repository also does not automatically create a durable audit store for the entire service.

### Verifying with an identifiable test request

In a test environment with authentication already configured, you can perform a check as follows:

1. Use dummy data to send a request to an existing API, including `Accept` and a harmless test header.
2. Read `httpexchanges` using an authorized identity.
3. Locate the exact record for the test request; do not confuse it with the record of the endpoint read itself.
4. Check method, URI, status, header set, and timing info against the configuration.
5. Switch to the next include set in a separate test run and send a new request.
6. Inspect the new records instead of assuming the configuration mutated old data.

Example for reading the endpoint on a pre-configured HTTPS system:

```bash
curl --user exchange-reader --fail \
  -H 'Accept: application/json' \
  https://ops.example.test/actuator/httpexchanges
```

Replace the example address with an appropriate test environment; this command does not configure access permissions. On PowerShell use `curl.exe` and write it on one line if your shell does not support Bash line continuations. curl will prompt for a password when only a username is given as above.

Separate endpoint read permissions from the data collection policy: authorized readers should still receive only the dataset actually required.

### Changing include does not erase already-recorded data

In an application without a dedicated dynamic configuration refresh mechanism, YAML changes must be applied through an appropriate configuration/startup lifecycle. Do not assume editing the file immediately changes the running process's include set.

If a repository still holds old records, changing the selection set for new records does not automatically delete or sanitize old records. For durable stores or already-exported copies, a separate data-handling process is required.

With `InMemoryHttpExchangeRepository`, restarting the process clears the in-memory buffer. However, that does not retract records someone has already downloaded or saved elsewhere.

## 7. Selecting data groups differs from sanitizing data

### Headers: selecting a whole group is not an allowlist

Suppose the application uses:

```text
X-Api-Key: demo-key
X-Customer-Email: person@example.test
```

These are illustrative values. If `request-headers` is selected, you cannot rely on the default exclusion of `Authorization` to conclude these two headers were handled as well.

When a strict per-header policy is required, design a processing layer that allows only chosen names and values, bounds length/count, and strips sensitive information **before storing**. Masking only at the read screen does not remove data already sitting in the repository.

Do not assume recording full headers is necessary for every HTTP error. If you only check response codes and latency, dropping both header groups may be wiser than a masking rule that is hard to verify.

### URI and query string: still require a dedicated policy

A path may contain a customer ID; a query string may contain an email or token. The `Include` set is not a URL anonymizer.

If URIs need narrowing, you can design records normalized to a route pattern or retain only allowlisted parameters. When reconstructing URIs manually, handle encoding, user-info, and query properly; do not use simple string-replacement expressions and assume every URL form is clean.

### Identity, IP, and session ID: not harmless information

Principal names, IP addresses, and session IDs can tie activity to a specific person or session. For each field, define the use case, authorized readers, retention period, and deletion method when no longer needed.

Do not use an available field merely because it is easy to collect. The minimal set for protocol diagnostics is not necessarily the minimal set for authentication investigations.

## 8. Common configuration misconceptions

| Misconception | Accurate understanding |
| --- | --- |
| Adding only `principal` keeps default timing and headers | A declared include list replaces the default set; list all needed groups explicitly |
| Dropping request headers masks the URI too | The URI is a separate part; query/path require their own policy |
| Omitting `time-taken` means the request took 0 ms | No measurement recorded, not a measurement of 0 |
| Enabling `principal` authenticates requests | The flag only selects provided info; security uses its own mechanisms |
| Enabling `session-id` guarantees every API has a session | Without session data there is no ID to record |
| `request-headers` records only "safe" headers | Only certain specific names are excluded; custom headers still require review |
| The include set also filters routes, status, and sampling rate | It selects fields/data groups, not a request filter by those criteria |
| Changing include cleans all held records | The policy applies when creating new records; old records and copies have separate lifecycles |
| Enabling recording means anyone can read the endpoint | Recording, exposure, and authorization are separate layers |

Do not use `include: []` as a way to disable the entire recording feature. If the goal is to stop recording via standard configuration, use the explicit property:

```yaml
management:
  httpexchanges:
    recording:
      enabled: false
```

Stopping recording does not clear the repository, disable access logs, disable metrics, or retract already-exported data.

## 9. Self-check practice

1. You need method, URI, status, and duration, but not headers or identity. Write the appropriate include set and state which baseline data remains present.
2. Why can a configuration containing only `principal` cause `timeTaken` to stop being recorded?
3. In the test program, why did `X-Api-Key` stay in the default header group while `Authorization` was excluded?
4. If a secret is in the query string, does omitting both header groups solve the problem?
5. Distinguish timestamp, Duration `PT0.125S`, CPU time, and user network wait time.
6. To stop recording, should you change the include set or set `recording.enabled=false`? What data might still remain afterward?

Comparison for question 1: `include: [time-taken]` additionally selects duration; baseline fields remain present. Question 2 stems from replacing the selection set, not a timing bug. A sound configuration must clearly state **what data is kept, why it is needed, what data may still be sensitive, and how to verify it on new records**.
