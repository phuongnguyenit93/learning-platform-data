# Filtering auditevents Queries by Principal, Timestamp, and Event Type

## 1. From audit history to the question to answer

An audit event records that a user or service performed an action at a given time. During an investigation, we usually do not need to read the entire history, but want to answer a specific question:

> Which failed authentication events for account alice occurred after 10:02 UTC?

Spring Boot Actuator provides the `auditevents` endpoint to read events currently retained by `AuditEventRepository`. The lesson's three filters correspond to the three parts of that question:

- **Performing actor:** `principal`.
- **Lower time boundary:** `after`.
- **Event type:** `type`.

Understanding the filters helps narrow down data, yet is not enough to conclude history is complete. Results also depend on whether events were published, retained in the repository, and within the scope the reader is permitted to view.

## 2. Visualizing the path of a query

With default path configuration in a web application, a read request looks like:

```http
GET /actuator/auditevents?principal=alice&after=2026-01-01T10:02:00Z&type=AUTHENTICATION_FAILURE
```

The processing flow can be pictured as:

```text
HTTP GET and query parameters
    -> convert timestamp parameter
    -> AuditEventsEndpoint
    -> AuditEventRepository.find(principal, after, type)
    -> results placed in the events array
```

All three parameters are optional. Omitting a parameter means not filtering by that criterion; it does not mean the endpoint automatically selects the current account or limits results to the last hour.

The repository's Java contract is:

```java
List<AuditEvent> find(String principal, Instant after, String type);
```

This is an API signature for comprehension, not a standalone Java file. At the repository, `null` represents no restriction on the corresponding criterion. See [AuditEventRepository in Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/audit/AuditEventRepository.html).

The endpoint requires an `AuditEventRepository` bean and must be exposed over HTTP. Exposure configuration only opens the access path; it does not generate events or grant permissions to callers. See [Spring Boot 3.3: Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

## 3. Exact meaning of each filter

| Parameter | Meaning | Example | When no filter is needed |
| --- | --- | --- | --- |
| `principal` | Select events for an actor recorded in the event | `principal=alice` | Omit parameter |
| `after` | Select events occurring after a timestamp | `after=2026-01-01T10:02:00Z` | Omit parameter |
| `type` | Select one event type | `type=AUTHENTICATION_FAILURE` | Omit parameter |

For the in-memory repository used in the hands-on lab, principal and type use exact, case-sensitive matching. `alice` differs from `Alice`; `AUTHENTICATION_FAILURE` differs from `authentication_failure`. There is no automatic substring search, regex, or wildcard matching.

Event type names are strings set by the producer. Names in this lesson such as `AUTHENTICATION_SUCCESS`, `AUTHENTICATION_FAILURE`, and `AUTHORIZATION_FAILURE` are meaningful only if events were actually recorded with those exact names. Applications can also define custom business types.

If using a custom repository, verify how that implementation matches values, especially when database collations may be case-insensitive. Do not assume every backend behaves identically to the in-memory repository.

### 3.1. Conditions combine with AND

A query with all three parameters requires an event to satisfy all of them simultaneously:

```text
event's principal = alice
AND event's timestamp > 2026-01-01T10:02:00Z
AND event's type = AUTHENTICATION_FAILURE
```

An event for `bob` is excluded even if timestamp and type match. An event for `alice` after the boundary is also excluded if its type is `AUTHORIZATION_FAILURE`.

The order in which the three parameters appear in the URL does not change the meaning. They must not be read as OR conditions.

### 3.2. Omitting a parameter differs from sending the string "null"

If you want to view all principals, omit `principal` from the URL. `principal=null` sends the four-character string `null`; that is not Java's `null` value.

Similarly, to leave time unbounded, omit `after`. Do not send `after=null`, and do not expect empty parameters to be handled identically across every client, proxy, and converter layer.

Do not send `principal=*` or `type=*` to mean "all": `*` has no wildcard contract on this endpoint.

## 4. after is an exclusive boundary and must identify a specific instant

### 4.1. An event at the exact boundary is excluded

Suppose an event exists at `10:02:00Z`:

```text
timestamp <  after  -> excluded
timestamp == after  -> excluded
timestamp >  after  -> evaluated against remaining conditions
```

Therefore, `after=2026-01-01T10:02:00Z` does not return an event at exact `10:02:00Z`. Do not read "after" as "from this instant onward, inclusive".

If you need to query a range with exact inclusive/exclusive bounds such as `[start, end)`, a query service supporting that contract is required. The endpoint covered here provides only the lower bound `after`, with no matching `from/to` or `before` parameter.

### 4.2. Using ISO-8601 timestamps with offsets

These two representations express the exact same instant:

```text
2026-01-01T10:02:00Z
2026-01-01T17:02:00+07:00
```

`Z` denotes UTC. `+07:00` indicates local display time seven hours ahead of UTC. These are two representations of the same point on the timeline, not two different search ranges. See [Java OffsetDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/OffsetDateTime.html).

Use a complete representation such as `2026-01-01T10:02:00Z`. Date-only strings or local times missing an offset such as `2026-01-01T10:02:00` do not unambiguously specify the endpoint's target instant. In the Spring Boot 3.3.13 lab application, strings missing an offset or `not-a-time` return HTTP `400`.

`after` applies to the event's timestamp, not the moment we send the HTTP request. Clock skew at the producer or late-arriving events in the store can affect result interpretation.

## 5. Preparing an application with fixed data

This example uses Java 17+; JDK 21, Maven 3.6.3+, and Spring Boot 3.3.13 can be used. Versions are pinned to study behavior in the 3.3.x branch, not as a recommendation for selecting versions on another project.

Create a separate practice directory:

```text
audit-filter-lab/
├── pom.xml
├── BuildAuditQuery.java
└── src/main/
    ├── java/demo/AuditFilterApplication.java
    └── resources/application.properties
```

`BuildAuditQuery.java` is used in section 9; it is not needed yet to run the server.

### 5.1. Declaring dependencies

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.13</version>
    <relativePath/>
  </parent>
  <groupId>example</groupId>
  <artifactId>audit-filter-lab</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
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

The application needs the web starter to receive HTTP and Actuator to provide the endpoint. No new business controller is needed for this query lab.

### 5.2. Initializing the repository and six events

File `src/main/java/demo/AuditFilterApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.actuate.audit.AuditEvent;
import org.springframework.boot.actuate.audit.AuditEventRepository;
import org.springframework.boot.actuate.audit.InMemoryAuditEventRepository;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

import java.time.Instant;
import java.util.Map;

@SpringBootApplication
public class AuditFilterApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuditFilterApplication.class, args);
    }

    @Bean
    AuditEventRepository auditEventRepository() {
        var repository = new InMemoryAuditEventRepository(20);
        add(repository, "E1", "2026-01-01T10:00:00Z",
                "alice", "AUTHENTICATION_SUCCESS");
        add(repository, "E2", "2026-01-01T10:01:00Z",
                "alice", "AUTHENTICATION_FAILURE");
        add(repository, "E3", "2026-01-01T10:02:00Z",
                "bob", "AUTHENTICATION_FAILURE");
        add(repository, "E4", "2026-01-01T10:03:00Z",
                "alice", "AUTHORIZATION_FAILURE");
        add(repository, "E5", "2026-01-01T10:04:00Z",
                "alice", "AUTHENTICATION_FAILURE");
        add(repository, "E6", "2026-01-01T10:04:00Z",
                "ops+night@example.com", "AUTHENTICATION_FAILURE");
        return repository;
    }

    private static void add(AuditEventRepository repository, String ref,
                            String timestamp, String principal, String type) {
        repository.add(new AuditEvent(
                Instant.parse(timestamp), principal, type, Map.of("ref", ref)));
    }
}
```

Events are added directly to build a reproducible dataset. They are synthetic data; the program performs no real logins and has no Spring Security dependency.

Repository capacity is set to 20, enough for six events. Timestamps are fixed instead of using `Instant.now()` so all predicted results are independent of when the lab is run.

### 5.3. Exposing the endpoint in the practice environment

File `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=18084
management.endpoint.auditevents.enabled=true
management.endpoints.web.exposure.include=health,auditevents
```

The server listens only on `127.0.0.1` on the host running the lab. The example configures no authentication, so use it only in a local learning environment. In production applications, protect access to audit history according to system authorization policies.

Start from the project directory:

```powershell
mvn -q package
java -jar target/audit-filter-lab-1.0.0.jar
```

Wait for the application to start, then open a second terminal to send queries. Press `Ctrl+C` in the Java terminal to stop after finishing.

The HTTP commands below use `curl.exe` on Windows to invoke the real curl binary. On Linux/macOS, replace `curl.exe` with `curl`. If you change the server port, update the port in the commands and URL-building program as well.

### 5.4. Reference data table

| Label in data.ref | UTC Timestamp | Principal | Type |
| --- | --- | --- | --- |
| E1 | `2026-01-01T10:00:00Z` | `alice` | `AUTHENTICATION_SUCCESS` |
| E2 | `2026-01-01T10:01:00Z` | `alice` | `AUTHENTICATION_FAILURE` |
| E3 | `2026-01-01T10:02:00Z` | `bob` | `AUTHENTICATION_FAILURE` |
| E4 | `2026-01-01T10:03:00Z` | `alice` | `AUTHORIZATION_FAILURE` |
| E5 | `2026-01-01T10:04:00Z` | `alice` | `AUTHENTICATION_FAILURE` |
| E6 | `2026-01-01T10:04:00Z` | `ops+night@example.com` | `AUTHENTICATION_FAILURE` |

`ref` is custom supplementary data to make the example easy to read. It is not a mandatory event ID field generated by the endpoint. Events E5 and E6 share the same timestamp to illustrate that timestamps are not necessarily unique identifiers.

## 6. Sending queries from broad to narrow

### 6.1. Without filters

```powershell
curl.exe --silent --show-error "http://127.0.0.1:18084/actuator/auditevents"
```

With the exact sample data, the `events` array contains E1, E2, E3, E4, E5, and E6.

This means none of the lesson's three filter conditions are applied. It returns only the events currently retained by the repository, without restoring previously evicted events.

### 6.2. Filtering by principal only

```powershell
curl.exe --silent --show-error --get "http://127.0.0.1:18084/actuator/auditevents" --data-urlencode "principal=alice"
```

Results include E1, E2, E4, E5. We have narrowed by actor, without restricting type or time yet.

### 6.3. Filtering by timestamp only

```powershell
curl.exe --silent --show-error --get "http://127.0.0.1:18084/actuator/auditevents" --data-urlencode "after=2026-01-01T10:02:00Z"
```

Results include E4, E5, E6. E3 is excluded because it occurred at exact `10:02:00Z`.

### 6.4. Filtering by type only

```powershell
curl.exe --silent --show-error --get "http://127.0.0.1:18084/actuator/auditevents" --data-urlencode "type=AUTHENTICATION_FAILURE"
```

Results include E2, E3, E5, E6. These events can belong to different principals and timestamps.

### 6.5. Combining all three conditions

```powershell
curl.exe --silent --show-error --get "http://127.0.0.1:18084/actuator/auditevents" --data-urlencode "principal=alice" --data-urlencode "after=2026-01-01T10:02:00Z" --data-urlencode "type=AUTHENTICATION_FAILURE"
```

Only E5 satisfies all three conditions. JSON response, reformatted with whitespace for readability:

```json
{
  "events": [
    {
      "timestamp": "2026-01-01T10:04:00Z",
      "principal": "alice",
      "type": "AUTHENTICATION_FAILURE",
      "data": {
        "ref": "E5"
      }
    }
  ]
}
```

Read `events` to obtain the list. `timestamp`, `principal`, and `type` describe the event; `data` holds supplementary info supplied by the producer. Do not infer that every event type always has the same keys inside `data`.

The label sets in this lesson compare membership and do not promise element ordering across every repository. The `AuditEventRepository` interface has no `sort` parameter; clients should not rely on an order accidentally observed in the RAM store.

### 6.6. Zero matching records is still a successful query

Change the combined query's timestamp to `2026-01-01T10:04:00Z`:

```powershell
curl.exe --silent --show-error --get "http://127.0.0.1:18084/actuator/auditevents" --data-urlencode "principal=alice" --data-urlencode "after=2026-01-01T10:04:00Z" --data-urlencode "type=AUTHENTICATION_FAILURE"
```

E5 equals the boundary and is therefore excluded. The response has HTTP `200` with body:

```json
{"events":[]}
```

An empty list is not HTTP `404`. Nor does it prove on its own that the target action never happened in reality; it only shows no matching records exist in the current query result.

## 7. URL encoding: the plus sign easily breaks queries

### 7.1. Plus signs in timestamp offsets

You can replace the UTC boundary in the combined query with `2026-01-01T17:02:00+07:00`:

```powershell
curl.exe --silent --show-error --get "http://127.0.0.1:18084/actuator/auditevents" --data-urlencode "principal=alice" --data-urlencode "after=2026-01-01T17:02:00+07:00" --data-urlencode "type=AUTHENTICATION_FAILURE"
```

The result is still only E5.

In form-style parameter decoding, `+` can be interpreted as a space. Therefore, a literal plus sign in a value must be encoded as `%2B`. Simply wrapping the whole URL in quotes does not perform this encoding.

The corresponding encoded URL is:

```text
http://127.0.0.1:18084/actuator/auditevents?principal=alice&after=2026-01-01T17%3A02%3A00%2B07%3A00&type=AUTHENTICATION_FAILURE
```

If you concatenate a raw plus sign and send it through a decoder that treats it as a space, the timestamp string becomes invalid and can return `400`. That is a wire-encoding error, not a UTC conversion bug.

### 7.2. Plus signs in principal

The sample account `ops+night@example.com` also requires preserving the plus sign:

```powershell
curl.exe --silent --show-error --get "http://127.0.0.1:18084/actuator/auditevents" --data-urlencode "principal=ops+night@example.com"
```

The result is E6. The encoded value of this principal is `ops%2Bnight%40example.com`.

An encoding mistake in `principal` can silently produce an empty result: the server searches for `ops night@example.com` instead of the actor containing a plus sign. Not every encoding mistake returns `400`.

### 7.3. Using tools to encode once

`--get` turns the specified data into the query string of a GET request. `--data-urlencode` encodes values before appending them to the URL. These two options avoid replacing characters manually. See [curl documentation](https://curl.se/docs/manpage.html#--data-urlencode).

Practical rules:

- Pass the raw, unencoded value to `--data-urlencode`. Do not pre-encode `%2B` and double-encode it into `%252B`.
- Quote URLs when writing multiple parameters manually so the shell does not interpret `&`.
- Do not use `-X GET` with data in the request body expecting it to act like query parameters. Use `--get` for the pattern taught here.
- For Vietnamese characters or special characters in `principal`, use UTF-8 and an appropriate URL builder.
- Do not place credentials or tokens in the query string; `principal` here is an event search filter.

The rule converting `+` to a space and decoding `%xx` is documented in [Java URLDecoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLDecoder.html).

## 8. Reading and diagnosing responses at the right layer

| Observation | Interpretation and check steps |
| --- | --- |
| `200`, events present | Verify each record has the right principal, timestamp, and type |
| `200`, `events` empty | Check exact values, time boundary, offset, encoding, and data still retained by repository |
| `400` | Check unparseable parameters, especially `after` |
| `401` on an authenticated API | Verify valid credentials are supplied per configuration |
| `403` on an authorized API | Check endpoint read permissions; changing the filter principal does not grant extra permissions |
| `404` | Check host/port/base path, endpoint exposure, and repository bean; do not interpret as no events |
| `5xx` | Check server or repository errors; do not treat a read error as an empty history |

Exact status codes and error bodies can also be affected by proxies, login mechanisms, or custom error handlers. The table focuses on classification during investigation, rather than prescribing a fixed error JSON for every system.

Example checking an invalid timestamp:

```powershell
curl.exe --include --get "http://127.0.0.1:18084/actuator/auditevents" --data-urlencode "after=not-a-time"
```

With the sample application, the response status is `400`. A validly named parameter that fails conversion differs from a valid query that finds no records. Actuator's conversion-error rules are described in [Web Endpoint Response Status](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom.web.response-status).

## 9. Building URLs with a standalone Java program

When writing query tools, do not concatenate user inputs directly after `=`. The program below constructs the exact URL for the combined query, encodes each key/value individually, and verifies the equivalent UTC instant.

File `BuildAuditQuery.java`:

```java
import java.net.URI;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.time.OffsetDateTime;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.stream.Collectors;

public class BuildAuditQuery {
    public static void main(String[] args) {
        Map<String, String> parameters = new LinkedHashMap<>();
        parameters.put("principal", "alice");
        parameters.put("after", "2026-01-01T17:02:00+07:00");
        parameters.put("type", "AUTHENTICATION_FAILURE");

        String query = parameters.entrySet().stream()
                .map(entry -> encode(entry.getKey()) + "=" + encode(entry.getValue()))
                .collect(Collectors.joining("&"));

        URI uri = URI.create(
                "http://127.0.0.1:18084/actuator/auditevents?" + query);
        System.out.println("afterInstant="
                + OffsetDateTime.parse(parameters.get("after")).toInstant());
        System.out.println(uri);
    }

    private static String encode(String value) {
        return URLEncoder.encode(value, StandardCharsets.UTF_8);
    }
}
```

Compile and run from the directory containing the file:

```powershell
javac --release 17 BuildAuditQuery.java
java BuildAuditQuery
```

Exact stdout:

```text
afterInstant=2026-01-01T10:02:00Z
http://127.0.0.1:18084/actuator/auditevents?principal=alice&after=2026-01-01T17%3A02%3A00%2B07%3A00&type=AUTHENTICATION_FAILURE
```

The program only builds the URL without sending HTTP, so it runs independently of the server. You can use the printed URL to send a request while the sample application is running.

`URLEncoder` applies `application/x-www-form-urlencoded` rules, suitable when encoding query values decoded by those rules. Here it is applied per component, not to the whole URL. Encoding the entire URL would distort delimiters like `:`, `/`, `?`, and `&`.

`LinkedHashMap` simply keeps printed parameter order deterministic; the server does not require that exact order. Specifying `StandardCharsets.UTF_8` avoids depending on the host's default charset. See [Java URLEncoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLEncoder.html).

## 10. Calling the repository directly when already inside the application

If the repository bean is already injected in a Spring component, you do not necessarily have to make an HTTP call back to the same application just to filter the same data.

Illustrative integration snippet, assuming `repository` has been injected with type `AuditEventRepository`:

```java
Instant after = OffsetDateTime.parse("2026-01-01T17:02:00+07:00").toInstant();

List<AuditEvent> result = repository.find(
        "alice",
        after,
        "AUTHENTICATION_FAILURE");
```

Types to import are `java.time.Instant`, `java.time.OffsetDateTime`, `java.util.List`, `org.springframework.boot.actuate.audit.AuditEvent`, and `AuditEventRepository` in the same audit package. This snippet is not a standalone program.

With the sample dataset, the result contains only E5. To omit principal filtering at the Java layer, pass `null` as the first argument; do not pass the string `"null"`.

Calling directly avoids the URL and HTTP step, yet does not replace authorization in the service consuming the data. If a business API allows callers to pass an arbitrary principal and then queries the repository, that service must still check permissions and viewable data scope.

## 11. Limitations to know before using for continuous investigations

### 11.1. The filter principal is not the logged-in user

`principal=alice` means searching for events whose recorded principal is `alice`. It does not require the HTTP caller to be alice and does not automatically scope results to the currently logged-in identity.

For example, an operator granted audit permissions may need to query events for multiple accounts. Conversely, an ordinary user must not be allowed to view others' data simply by knowing how to change a query parameter.

In multi-tenant systems, the endpoint's three filters do not create tenant boundaries automatically. Enforce those boundaries in the permission design and query layer.

### 11.2. No contract for OR, pagination, or two-sided time ranges

The following syntax does not mean what many assume:

| Syntax | False assumption |
| --- | --- |
| `type=A,B` | Automatically searches type A or B |
| `type=A&type=B` | Automatically creates an OR condition |
| `principal=ali*` | Matches all principals starting with ali |
| `before=...` | Automatically sets an upper time bound |
| `page=0&size=20` | Automatically enables Spring Data-style pagination |
| `sort=timestamp,asc` | Automatically sorts ascending |

In the sample dataset, `type=AUTHENTICATION_FAILURE,AUTHORIZATION_FAILURE` is treated as one string value and matches no events. With repeated parameters, do not rely on how one version handles lists to infer OR support.

Parameters unused by the endpoint also do not necessarily fail. With Spring Boot 3.3.13 in this lesson, adding `before=2026-01-01T10:02:00Z` alone still returns all six events: the upper bound was not applied. Thus, HTTP `200` does not prove a custom parameter took effect.

If an extended search contract is needed, design a documented query API and verify it separately. Post-filtering on the client applies only to already-returned data and cannot recover history that was not returned or already evicted from the store.

### 11.3. after is not a lossless polling cursor

E5 and E6 share timestamp `10:04:00Z`. Suppose one read sees only E5 and the client saves this timestamp. Afterward E6 is added to the store with the same timestamp. The next read using `after=10:04:00Z` will exclude E6.

A late-arriving event with a timestamp earlier than the saved boundary can also be skipped. Do not advertise polling the endpoint by timestamp as a complete event-streaming pipeline.

Overlapping read windows can reduce risk, yet require stable identifiers for deduplication and rules for handling late events. `data.ref` in the example is not a guaranteed identifier across all Actuator events.

If the requirement is reliably exporting full history, you need a store and read protocol supporting ordering, cursors, pagination, and proper deduplication. Those are additional requirements beyond this lesson's three parameters.

### 11.4. Filters do not govern retention duration

The in-memory repository retains only data for the current process and configured capacity. Querying accurately does not turn it into a durable history store. Restarting the sample application recreates the six events from initialization code rather than proving old data survived.

With multiple application replicas holding separate repositories, reads through a load balancer can return different sets of events. When analyzing results, know which store the query hit and what data that store retains.

Do not use `events=[]` to conclude with certainty "no incident occurred". Check producer coverage, retention duration, and store readability as well.

## 12. Self-check with predicted results

Compare by `data.ref` sets, independent of JSON ordering:

| Condition | Result with sample data |
| --- | --- |
| No parameters | E1, E2, E3, E4, E5, E6 |
| `principal=alice` | E1, E2, E4, E5 |
| `after=2026-01-01T10:02:00Z` | E4, E5, E6 |
| `type=AUTHENTICATION_FAILURE` | E2, E3, E5, E6 |
| Three conditions: alice, after 10:02Z, auth failure | E5 |
| Three conditions above, change boundary to 10:04Z | Empty |
| Change 10:02Z to 17:02+07:00, properly encoded | E5 |
| `principal=ops+night@example.com`, properly encoded | E6 |
| `principal=Alice` | Empty in sample repository |
| `principal=null` | Empty; searching for string `null` |
| `after=not-a-time` | HTTP 400 |
| `after=2026-01-01T10:02:00` missing offset | HTTP 400 |

**Exercise 1:** Using only principal and type, find all of alice's authentication failures in the store.

**Answer:** omit `after`, keep `principal=alice` and `type=AUTHENTICATION_FAILURE`. Result is E2, E5. Do not send `after=null`.

**Exercise 2:** To get authentication failures for any actor after `10:01Z`, which parameters should be passed?

**Answer:** `after=2026-01-01T10:01:00Z` and `type=AUTHENTICATION_FAILURE`; omit principal. Result is E3, E5, E6. E2 is excluded at the boundary.

**Exercise 3:** Change E6's timestamp to `2026-01-01T17:04:00+07:00`, still representing the same instant. Should time-based query results change?

**Answer:** no, if data is converted properly to instants. The new representation equals `10:04:00Z`. In initialization code using `Instant.parse`, use `OffsetDateTime.parse(...).toInstant()` if you want to show parsing an offset string and converting to `Instant`.

**Exercise 4:** A request returns `200` when passing `size=10`. Can you conclude the endpoint returns at most ten events?

**Answer:** no. Verify the parameter contract and actual results; a success code does not confirm an out-of-contract parameter took effect.

When using `auditevents`, express the query in one clear sentence: whose events you are looking for, after which timestamp, and of which type. Then verify conditions, URL encoding, and the actual data scope retained by the repository before drawing conclusions.
