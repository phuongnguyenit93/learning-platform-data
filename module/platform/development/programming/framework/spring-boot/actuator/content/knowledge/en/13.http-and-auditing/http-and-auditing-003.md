# Using `InMemoryHttpExchangeRepository` for Bounded Diagnostics

## 1. A small observation window in memory

Suppose you just reproduced an HTTP error on your development machine. You want to inspect the few nearby requests: which paths were called, whether the responses succeeded or failed, and how long processing took. Keeping the entire history inside the application causes storage cost to grow over time; keeping a finite number of records makes inspection simpler.

`InMemoryHttpExchangeRepository` is the process-memory implementation of `HttpExchangeRepository`. Spring Boot provides it to store recent request–response exchanges, defaulting to 100 records. Boot documentation recommends using this class in development environments. [Recording HTTP exchanges](https://docs.spring.io/spring-boot/3.3/reference/actuator/http-exchanges.html)

**Bounded diagnostics** means drawing conclusions based on a data window with clear limits on count, lifecycle, and application scope. You need to know both what is visible and what may already have been evicted from that window.

| Component | Responsibility in the observation flow |
| --- | --- |
| Boot HTTP recording mechanism | Creates information about an HTTP exchange and passes it to the repository |
| `InMemoryHttpExchangeRepository` | Retains a bounded number of records in memory |
| `httpexchanges` endpoint | Allows reading the information retained by the repository |

The repository answers the question "which records are currently held?". Whether the endpoint is exposed over HTTP or the caller has read permission are separate conditions. This lesson focuses on how to use the repository and interpret its data.

## 2. Capacity is record count, not seconds

Two notable configuration methods are `setCapacity(int)` and `setReverse(boolean)`. Choose a positive capacity and configure both when initializing the bean, before traffic arrives. `setReverse` defaults to `true`. [`InMemoryHttpExchangeRepository` API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/web/exchanges/InMemoryHttpExchangeRepository.html)

In the Boot 3.3.0 example below, once capacity is fixed at 3 and the default order is kept, adding a new record causes the oldest record to be evicted:

| After adding | List read, newest added first | Just evicted record |
| --- | --- | --- |
| A | A | None |
| B | B, A | None |
| C | C, B, A | None |
| D | D, C, B | A |
| E | E, D, C | B |

Therefore, a capacity of 100 does not mean keeping data for the last 100 seconds, 100 users, or 100 errors. Successful requests also occupy slots if recorded; the repository does not reserve capacity exclusively for failed requests.

A useful estimate when traffic is relatively steady:

```text
C = capacity, in records
r = number of records actually added per second

Approximate history window ≈ C / r seconds
```

For example, C = 100 and r = 50 records/second gives a history window of only about 2 seconds. If r drops to 1 record/second, the window can be much longer. This is an inference for estimating from traffic, not a retention period guaranteed by the repository.

There is no automatic time-based expiration (TTL) mechanism in this example. When there are no new additions and the process remains alive, another minute passing on the clock does not automatically make records disappear. Conversely, a large burst of traffic can push out the target record very quickly.

A bounded record count also does not establish an exact byte limit in memory. The size of URIs, headers, and optional fields can vary across records. When increasing C, consider both the amount of data per exchange and the cost of building the response payload on read.

## 3. Runnable experiment: observing record eviction

This experiment creates synthetic `HttpExchange` instances and adds them directly to the repository. It tests storage behavior without starting a web server, making network requests, or needing a database.

The example uses JDK 21 and the Spring Boot 3.3.0 library. The public constructors of `HttpExchange`, `HttpExchange.Request`, and `HttpExchange.Response` let you build objects with given data. In a typical web application, you let Boot's infrastructure record exchanges instead of manually re-adding the same request inside a controller. [`HttpExchange` API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/web/exchanges/HttpExchange.html), [Request](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/web/exchanges/HttpExchange.Request.html), [Response](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/web/exchanges/HttpExchange.Response.html)

### 3.1. Minimal hands-on project

Create a standalone Java project with Gradle Wrapper 8.5 already available. The following paths are relative to the sample project directory.

Contents of `settings.gradle`:

```groovy
rootProject.name = 'bounded-http-exchanges'
```

Contents of `build.gradle`:

```groovy
plugins {
    id 'application'
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
    implementation 'org.springframework.boot:spring-boot-actuator:3.3.0'
}

application {
    mainClass = 'BoundedExchangeDemo'
}
```

This project uses the Actuator library directly; the `application` plugin is solely for running the `main` method. It is not a Spring Boot application with HTTP endpoints.

### 3.2. Complete program

Save as `src/main/java/BoundedExchangeDemo.java`:

```java
import java.net.URI;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;

import org.springframework.boot.actuate.web.exchanges.HttpExchange;
import org.springframework.boot.actuate.web.exchanges.InMemoryHttpExchangeRepository;

public class BoundedExchangeDemo {

    public static void main(String[] args) {
        var newestFirst = new InMemoryHttpExchangeRepository();
        newestFirst.setCapacity(3);

        newestFirst.add(exchange(1, 200));
        newestFirst.add(exchange(2, 500));
        newestFirst.add(exchange(3, 200));

        List<HttpExchange> snapshot = newestFirst.findAll();
        System.out.println("initial=" + paths(snapshot));

        newestFirst.add(exchange(4, 200));
        List<HttpExchange> current = newestFirst.findAll();
        System.out.println("after4=" + paths(current));
        System.out.println("oldSnapshot=" + paths(snapshot));

        long retainedServerErrors = current.stream()
                .filter(item -> item.getResponse().getStatus() >= 500)
                .count();
        System.out.println("retained5xx=" + retainedServerErrors);

        boolean unmodifiable = false;
        try {
            snapshot.clear();
        } catch (UnsupportedOperationException expected) {
            unmodifiable = true;
        }
        System.out.println("snapshotUnmodifiable=" + unmodifiable);

        var oldestFirst = new InMemoryHttpExchangeRepository();
        oldestFirst.setCapacity(3);
        oldestFirst.setReverse(false);
        for (int i = 1; i <= 4; i++) {
            oldestFirst.add(exchange(i, 200));
        }
        System.out.println("oldestFirst=" + paths(oldestFirst.findAll()));

        var defaults = new InMemoryHttpExchangeRepository();
        for (int i = 1; i <= 101; i++) {
            defaults.add(exchange(i, 200));
        }
        List<HttpExchange> defaultSnapshot = defaults.findAll();
        System.out.println("defaultSize=" + defaultSnapshot.size());
        System.out.println("defaultNewest="
                + defaultSnapshot.get(0).getRequest().getUri().getPath());
        System.out.println("defaultOldest="
                + defaultSnapshot.get(defaultSnapshot.size() - 1)
                        .getRequest().getUri().getPath());

        var freshInstance = new InMemoryHttpExchangeRepository();
        System.out.println("freshInstanceSize=" + freshInstance.findAll().size());
    }

    private static HttpExchange exchange(int number, int status) {
        var request = new HttpExchange.Request(
                URI.create("http://localhost/sample/" + number),
                null,
                "GET",
                Map.of());
        var response = new HttpExchange.Response(status, Map.of());

        return new HttpExchange(
                Instant.parse("2025-01-01T00:00:00Z").plusSeconds(number),
                request,
                response,
                null,
                null,
                Duration.ofMillis(10));
    }

    private static List<String> paths(List<HttpExchange> exchanges) {
        return exchanges.stream()
                .map(item -> item.getRequest().getUri().getPath())
                .toList();
    }
}
```

Fixed timestamps and numbered URIs make it easy to verify results; these objects do not represent real traffic. `null` in the example indicates no remote address, principal, or session is provided; headers are empty maps. Status `500` is assigned only to record number 2 to test a filter operation.

### 3.3. Running and reading the output

On PowerShell:

```powershell
.\gradlew.bat -q run
```

On Linux/macOS:

```bash
./gradlew -q run
```

Program stdout:

```text
initial=[/sample/3, /sample/2, /sample/1]
after4=[/sample/4, /sample/3, /sample/2]
oldSnapshot=[/sample/3, /sample/2, /sample/1]
retained5xx=1
snapshotUnmodifiable=true
oldestFirst=[/sample/2, /sample/3, /sample/4]
defaultSize=100
defaultNewest=/sample/101
defaultOldest=/sample/2
freshInstanceSize=0
```

The results show:

- Adding record 4 to a repository of capacity 3 removes record 1 from the new read.
- Setting `setReverse(false)` before adding data produces oldest-first ordering within the retained group; it does not increase capacity.
- A default repository retains 100 records after 101 additions, so record 1 has been evicted.
- Two separately created repository objects do not automatically share data.

With the Boot 3.3.0 implementation used in the experiment, `findAll()` returns an unmodifiable list snapshot: adding record 4 does not automatically update the `snapshot` variable, and calling `clear()` on that list throws `UnsupportedOperationException`. This is the behavior of the specific class tested; do not generalize it into a mandatory contract for every custom `HttpExchangeRepository`.

## 4. Interpreting ordering and snapshots accurately

### 4.1. "Newest" by insertion order, not a sort over all timestamps

In the experiment, chronological order and insertion order were intentionally aligned. The 3.3.0 repository does not run a sort query by `getTimestamp()` after every addition.

With concurrent requests, a request that started earlier can finish later. `HttpExchange.timestamp` represents when the exchange started; therefore, do not treat list position as absolute proof of start order for all requests. When investigating chronologically, read the timestamp field and related information. [Meaning of `HttpExchange` timestamp](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/web/exchanges/HttpExchange.html#getTimestamp())

Set the listing direction right when creating the repository. This lesson does not use `setReverse(...)` or change capacity while the repository already holds data; setters should not be treated as history-management operations to swap arbitrarily during diagnostics.

### 4.2. One read per analysis pass

If you need to count, filter, and display the same set of records, store the result of a single `findAll()` call in a variable and perform all analysis on that variable, like `current` in the program.

Reading the repository once for the size and a second time for the contents can return two different observation sets while the application continues receiving requests. In the 3.3.0 implementation, add and list-snapshot operations are synchronized; that protects internal operations, but it does not freeze the application or create a shared transaction across multiple reads.

Do not treat the returned list as an API for deleting or editing history. If data management is needed, design a repository with an appropriate contract instead of relying on mutating the `List`.

## 5. Configuring a diagnostic window in a web application

The following configuration snippet belongs in a Spring Boot 3.3 application using Spring MVC that already has `spring-boot-starter-web` and `spring-boot-starter-actuator`. This is a configuration class for an existing application, not the standalone `main` program from section 3.

Save the class in a package scanned by the application, such as `example.diagnostics`:

```java
package example.diagnostics;

import org.springframework.boot.actuate.web.exchanges.HttpExchangeRepository;
import org.springframework.boot.actuate.web.exchanges.InMemoryHttpExchangeRepository;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@Profile("local-http-diagnostics")
public class HttpExchangeDiagnosticsConfiguration {

    @Bean
    public HttpExchangeRepository httpExchangeRepository() {
        var repository = new InMemoryHttpExchangeRepository();
        repository.setCapacity(50);
        repository.setReverse(true);
        return repository;
    }
}
```

A profile ties bean registration to a specific development purpose. If the application already has a repository bean, adjust the configuration of the bean already in use; do not add a second bean just to change capacity.

Put the configuration below in `src/main/resources/application-local-http-diagnostics.yml`:

```yaml
server:
  address: 127.0.0.1

management:
  endpoint:
    httpexchanges:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health,httpexchanges
  httpexchanges:
    recording:
      enabled: true
      include:
        - time-taken
```

In a sample environment using the default web configuration without a separate management port, this bind address restricts the server to loopback. It does not replace authentication/authorization rules if the application integrates security.

With a web project that has Gradle Wrapper and the Boot plugin, activate the profile on PowerShell:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=local-http-diagnostics"
```

The configuration selects `time-taken` to add duration and does not request header groups, principal, or session ID. `recording.include` controls which optional fields are recorded, while `endpoints.web.exposure.include` controls which endpoints are exposed over HTTP. [Recording options](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/web/exchanges/Include.html), [Endpoint exposure and security](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)

Send a request to an existing application API, then read the snapshot:

```powershell
$snapshot = Invoke-RestMethod http://127.0.0.1:8080/actuator/httpexchanges
$snapshot.exchanges | ForEach-Object {
    [pscustomobject]@{
        Method = $_.request.method
        Uri = $_.request.uri
        Status = $_.response.status
        TimeTaken = $_.timeTaken
    }
}
```

This command assumes the default path and port configuration; adjust the URL if the application has changed them. There is no fixed stdout because the content depends on the application's own traffic. Field names come from the endpoint's response structure. [HTTP Exchanges REST API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/httpexchanges.html)

## 6. Diagnostic workflow with a bounded dataset

1. **Identify the right process.** Confirm which application replica you are calling and that the diagnostic profile is active.
2. **Pick a specific question.** For example: did the API call just reproduced return `500`? Collect only the fields needed to answer that question.
3. **Reproduce the error, then read promptly.** Avoid generating lots of unrelated requests before taking the snapshot.
4. **Save one snapshot for analysis.** Filter by path, timestamp, and status on the same snapshot; if saving to a file, review sensitive data before sharing.
5. **Conclude within the scope of evidence.** "In this snapshot there is one 500 response" is a valid conclusion; "the system has only ever had one error" goes beyond the data.
6. **End the observation session.** Once the development goal is resolved, remove the diagnostic profile in the next run if it is no longer needed.

In the section 3 program, `retained5xx=1` only counts errors among the three retained records. It is not a cumulative error counter and cannot serve as the error rate over the application's entire uptime. A burst of new successful requests can make old errors disappear from the repository.

Endpoint reads and management traffic can also pass through the application's recording infrastructure. When capacity is small, account for them instead of assuming every slot belongs to business APIs. Do not repeatedly query the endpoint and treat each read as an observation that does not affect subsequent records.

## 7. Limitations that change conclusions

| Limitation | Consequence during investigation |
| --- | --- |
| Finite number of records | Not seeing a request does not prove the request never occurred |
| Data lives in an in-memory object | When the object is replaced or the process restarts, the new repository does not automatically carry old history |
| Each process creates its own repository | Reading one replica does not provide the full history of other replicas |
| Recorded fields are selective | Missing headers, principal, or session may be due to collection configuration |
| No durable history store | Unsuitable for claiming long-term audit evidence |

Do not simply increase `capacity` when you genuinely need long-term history or cross-service journey correlation. Those requirements call for appropriate storage/observability design. Spring Boot recommends suitable tracing or observability solutions for production, and also allows implementing a custom `HttpExchangeRepository`. [Usage scope guide](https://docs.spring.io/spring-boot/3.3/reference/actuator/http-exchanges.html)

The data presented by the endpoint describes exchange metadata such as URI, method, status, and selected fields; do not expect it to be a full copy of request/response bodies. The endpoint schema does not provide body fields. [HTTP Exchanges data structure](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/httpexchanges.html)

Sensitive information must be considered even with a small window. URIs can contain sensitive query parameters; choosing not to record headers does not automatically make URIs safe to share. Increase capacity or enable additional data groups only after knowing which diagnostic question that information serves.

## 8. Self-check exercises

1. Keep capacity at 3, but add records 1 through 7. With the default ordering, what are the final three paths?
2. Why can an error record disappear even though you never called any delete API?
3. If there are three application replicas and you read 50 records from one replica, can you conclude the system handled exactly 50 requests?
4. If you want a minimum retention period of 10 minutes regardless of traffic, is merely raising capacity to 600 enough?

Comparison: (1) `/sample/7`, `/sample/6`, `/sample/5`; (2) new additions cause old records to be evicted when full; (3) no, the data is both count-bounded and belongs only to the replica that was read; (4) no, record count and minutes have no fixed relationship when the insertion rate changes.
