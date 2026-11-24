# Controlling Storage Capacity, Sensitive Headers, and Personal Data in HTTP Exchanges

## 1. Choose what data to observe before choosing where to store it

An HTTP exchange record helps answer questions such as which path was just called, whether the response errored, and how long processing took. However, HTTP requests can also carry tokens, session cookies, emails, IP addresses, or customer identifiers. Collecting more does not automatically improve diagnostics if that information does not serve the question being investigated.

With `HttpExchangeRepository`, three separate concerns must be controlled:

| Concern | Design question |
| --- | --- |
| Capacity | At most how many records are retained and how much data does each record contain? |
| Content | Which fields must be kept, and which must be stripped or replaced with a coarse description? |
| Read permissions and lifecycle | Who may read, where is it read from, and how long does the data exist? |

`InMemoryHttpExchangeRepository` keeps data in memory and retains the most recent 100 exchanges by default. Spring Boot recommends using this class for development environments. This is a record-count limit on one repository, not a guarantee that all data inside is safe to store or share. [Recording HTTP exchanges in Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/http-exchanges.html)

This lesson uses Spring Boot 3.3 and JDK 21 to illustrate how to minimize data right before storing. The tokens, emails, and addresses in the code are dummy data for the experiment.

## 2. Controlling capacity by both count and size

For the in-memory repository, `setCapacity(...)` sets the maximum number of records when configured with a positive capacity at initialization time. Older records make room for newer ones when full.

Choosing 50 records does not mean:

- data only lives for 50 seconds;
- memory is bounded to an exact number of bytes;
- only 50 failed requests are retained;
- data is deleted from everywhere else after leaving the repository.

High traffic can turn over the entire window very quickly; when there is no new traffic, records can remain in the repository's memory. If a fixed time-based retention period is needed, that mechanism must be designed separately.

To estimate cost:

```text
C: maximum number of records
S: average data size of a single record

Retained data is approximately C × S, plus Java object overhead.
```

This is an estimation model, not an exact heap-measurement formula. Multi-valued headers or long URIs increase S. Simply lowering C while still keeping large headers does not fully solve the problem.

The practical approach is to choose a window just large enough to reproduce errors, drop unneeded fields, avoid copying unbounded long values, and measure memory under representative traffic. Do not use `capacity=0` to turn off recording; Boot provides `management.httpexchanges.recording.enabled=false` for that purpose. [Controlling the recording mechanism](https://docs.spring.io/spring-boot/3.3/reference/actuator/http-exchanges.html)

## 3. Knowing exactly which headers are collected

### 3.1. Behavior of the standard recording mechanism

In the Boot 3.3.0 version used for the experiment, the default selections from `Include.defaultIncludes()` include time taken, request headers, and response headers. When flowing through the standard exchange creation mechanism, request `Authorization` and `Cookie`, as well as response `Set-Cookie`, are excluded unless the corresponding sensitive options are enabled.

Key options:

| Option in `recording.include` configuration | Meaning |
| --- | --- |
| `time-taken` | Record processing duration |
| `request-headers` | Collect the request header group |
| `response-headers` | Collect the response header group |
| `authorization-header` | Allow retaining `Authorization` when collecting request headers |
| `cookie-headers` | Allow retaining `Cookie`/`Set-Cookie` in the respective header groups |
| `principal` | Collect the authenticated identity when present |
| `session-id` | Collect the session identifier when present |
| `remote-address` | Collect the remote address when present |

These are `Include` data groups, not an arbitrary list of header names. For example, `recording.include: X-Api-Key` is not how you declare an allowed header. [`Include` API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/web/exchanges/Include.html)

Excluding a few familiar headers does not mean there is a detector for every secret. When `request-headers` is selected, custom headers like `X-Api-Key`, `X-Customer-Email`, or `X-Access-Token` require their own policy. Responses can also carry sensitive info in `Location` or business headers.

### 3.2. Configure minimal data first

If you only need path, method, status, and duration, start with:

```yaml
management:
  httpexchanges:
    recording:
      enabled: true
      include:
        - time-taken
```

This explicitly declared list replaces the default groups, so it does not request collecting headers, principal, session ID, or remote address. It does not remove the URI from the baseline information of the exchange.

Data-group configuration is also not a filter applied to every object you construct manually. If application code calls the public constructor of `HttpExchange.Request`/`Response` with a header map and manually calls `repository.add(...)`, you must control that map yourself. Do not assume recording properties will automatically sanitize every manually added exchange. [`HttpExchange` constructors](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/web/exchanges/HttpExchange.html)

## 4. Personal data can live outside headers

| Location | Dummy data example | Applicable data minimization approach |
| --- | --- | --- |
| Query string | `?email=learner%40example.test` | Drop the entire query if not needed for diagnostics |
| Path | `/users/learner@example.test` | Use known path labels or replace with a generic label |
| Resource ID in path | `/orders/123` | Normalize to group `/orders/_id` when only distinguishing API categories |
| Principal | Account name | Do not collect if the diagnostic question does not require identity |
| Session | Session ID | Do not keep session IDs to avoid session linking or leakage |
| Remote address | IP address | Do not collect if network analysis is unnecessary |
| Custom headers | Email, business token | Drop all or allow only reviewed fields |

Do not sanitize URLs by merely removing a parameter named `password`: new parameter names or path data can still slip through. When there is no need to retain queries, dropping the entire query is simpler and easier to verify.

If headers must be kept, an allowlist must specify allowed names, value counts, lengths, and acceptable value contents. Header names are case-insensitive; `authorization` must not become a bypass past a filter that only matches the exact string `Authorization`.

Masking only the last few characters of an email or hashing an identifier is not enough to claim the data is completely anonymized. Describe accurately the operation performed and what information remains. OWASP recommends avoiding placing tokens, session IDs, and unnecessary sensitive data in logged records; that principle is equally helpful for HTTP diagnostic stores. [OWASP: data to exclude from logs](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html#data-to-exclude)

## 5. Placing a data-minimization boundary before storage

One centralized control point is implementing `HttpExchangeRepository` and delegating internally to an `InMemoryHttpExchangeRepository`:

```text
Incoming exchange
      ↓
Application's data-minimization policy
      ↓
Create a new exchange containing only permitted data
      ↓
Bounded in-memory repository
      ↓
Endpoint or diagnostic code reads minimized data
```

Masking data only in the UI or in the returned JSON still leaves the original data sitting in the repository. Minimizing data inside `add(...)` ensures the repository's storage boundary only receives the processed version.

Even so, the incoming exchange was already constructed before this method ran. This approach does not guarantee the original data never appeared in request memory, server logs, proxies, traces, or heap dumps. Other recording places must be governed according to application policy.

## 6. Complete example: a small store keeping only selected metadata

The following example chooses an intentionally simple policy:

- Retain at most C records; C between 1 and 500 is an example-specific limit.
- Drop all request and response headers.
- Drop principal, session, and remote address.
- Drop query, original host, and userinfo in the URI.
- Retain only two known path groups; other paths become `/redacted`.
- Keep timestamp, status, duration, and HTTP method within an allowed set.

In return, readers lose details needed to investigate individual accounts or individual orders. This is an appropriate choice when questions only concern API categories and processing outcomes, not a policy to copy verbatim for every application.

### 6.1. Repository class

File `src/main/java/example/exchangeprivacy/MinimizedHttpExchangeRepository.java`:

```java
package example.exchangeprivacy;

import java.net.URI;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

import org.springframework.boot.actuate.web.exchanges.HttpExchange;
import org.springframework.boot.actuate.web.exchanges.HttpExchangeRepository;
import org.springframework.boot.actuate.web.exchanges.InMemoryHttpExchangeRepository;

public final class MinimizedHttpExchangeRepository
        implements HttpExchangeRepository {

    private static final Set<String> METHODS = Set.of(
            "GET", "POST", "PUT", "PATCH", "DELETE",
            "HEAD", "OPTIONS", "TRACE", "CONNECT");

    private final InMemoryHttpExchangeRepository delegate;

    public MinimizedHttpExchangeRepository(int capacity) {
        if (capacity < 1 || capacity > 500) {
            throw new IllegalArgumentException("capacity must be between 1 and 500");
        }
        delegate = new InMemoryHttpExchangeRepository();
        delegate.setCapacity(capacity);
    }

    @Override
    public void add(HttpExchange exchange) {
        Objects.requireNonNull(exchange, "exchange");
        var originalRequest = Objects.requireNonNull(
                exchange.getRequest(), "request");
        var originalResponse = Objects.requireNonNull(
                exchange.getResponse(), "response");
        URI originalUri = Objects.requireNonNull(
                originalRequest.getUri(), "uri");

        String method = originalRequest.getMethod();
        String safeMethod = method != null && METHODS.contains(method)
                ? method : "OTHER";
        URI safeUri = URI.create(
                "http://diagnostics.invalid" + minimizedPath(originalUri));

        var safeRequest = new HttpExchange.Request(
                safeUri, null, safeMethod, Map.of());
        var safeResponse = new HttpExchange.Response(
                originalResponse.getStatus(), Map.of());

        var minimized = new HttpExchange(
                exchange.getTimestamp(),
                safeRequest,
                safeResponse,
                null,
                null,
                exchange.getTimeTaken());
        delegate.add(minimized);
    }

    @Override
    public List<HttpExchange> findAll() {
        return delegate.findAll();
    }

    private static String minimizedPath(URI uri) {
        String path = uri.getRawPath();
        if ("/catalog/items".equals(path)) {
            return "/catalog/items";
        }
        if (path != null && path.matches("/orders/[0-9]{1,18}")) {
            return "/orders/_id";
        }
        return "/redacted";
    }
}
```

`minimizedPath(...)` returns only one of three constant strings. It never returns an unrecognized path, even if that path contains an email, Unicode, or percent-encoded data. `/orders/_id` is an example diagnostic label, not a URL for calling an order again.

`http://diagnostics.invalid` is likewise a fixed placeholder address to preserve URI structure. It does not describe the request's actual host or scheme. If the use case requires distinguishing services, design a controlled service label instead of arbitrarily keeping the request-supplied host.

A new empty header map is created for the minimized record. Because no headers are copied, this policy also strips multi-valued headers, unexpected headers, and all uppercase/lowercase variants of sensitive names. The code does not log the original exchange during processing.

### 6.2. Standalone verification program

File `src/main/java/example/exchangeprivacy/ExchangePrivacyDemo.java`:

```java
package example.exchangeprivacy;

import java.net.URI;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;

import org.springframework.boot.actuate.web.exchanges.HttpExchange;

public class ExchangePrivacyDemo {

    public static void main(String[] args) {
        var repository = new MinimizedHttpExchangeRepository(2);
        String orderUri = "https://shop.example.test/orders/123"
                + "?email=learner%40example.test";

        repository.add(sample(200, orderUri));
        repository.add(sample(500, orderUri));

        List<HttpExchange> firstSnapshot = repository.findAll();
        HttpExchange latest = firstSnapshot.get(0);
        System.out.println("size=" + firstSnapshot.size());
        System.out.println("firstStatus=" + latest.getResponse().getStatus());
        System.out.println("uri=" + latest.getRequest().getUri());
        System.out.println("requestHeaders=" + latest.getRequest().getHeaders());
        System.out.println("responseHeaders=" + latest.getResponse().getHeaders());
        System.out.println("remoteAddress=" + latest.getRequest().getRemoteAddress());
        System.out.println("principal=" + latest.getPrincipal());
        System.out.println("session=" + latest.getSession());
        System.out.println("timeTaken=" + latest.getTimeTaken());

        repository.add(sample(204,
                "https://shop.example.test/users/learner%40example.test"));
        List<HttpExchange> secondSnapshot = repository.findAll();
        System.out.println("afterThirdSize=" + secondSnapshot.size());
        System.out.println("retainedStatuses=" + secondSnapshot.stream()
                .map(item -> item.getResponse().getStatus()).toList());
        System.out.println("unknownPath="
                + secondSnapshot.get(0).getRequest().getUri().getPath());
    }

    private static HttpExchange sample(int status, String uri) {
        Map<String, List<String>> requestHeaders = Map.of(
                "authorization", List.of("Bearer demo-only-token"),
                "Cookie", List.of("sid=demo-only-session"),
                "X-Api-Key", List.of("demo-only-key"),
                "X-Customer-Email", List.of("learner@example.test"));
        Map<String, List<String>> responseHeaders = Map.of(
                "Set-Cookie", List.of("sid=demo-only-session"),
                "Location", List.of("/next?email=learner%40example.test"));

        return new HttpExchange(
                Instant.parse("2025-01-01T00:00:00Z"),
                new HttpExchange.Request(
                        URI.create(uri), "192.0.2.10", "GET", requestHeaders),
                new HttpExchange.Response(status, responseHeaders),
                new HttpExchange.Principal("demo-user"),
                new HttpExchange.Session("demo-only-session"),
                Duration.ofMillis(10));
    }
}
```

The program uses the constructor directly to intentionally pass dummy sensitive fields as input, then tests the repository's storage boundary itself. It does not start an HTTP server and does not send data over the network.

### 6.3. Configuring and running the sample project

Use JDK 21 and a project with Gradle Wrapper 8.5 available. File `settings.gradle`:

```groovy
rootProject.name = 'http-exchange-privacy-demo'
```

File `build.gradle`:

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
    mainClass = 'example.exchangeprivacy.ExchangePrivacyDemo'
}
```

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
size=2
firstStatus=500
uri=http://diagnostics.invalid/orders/_id
requestHeaders={}
responseHeaders={}
remoteAddress=null
principal=null
session=null
timeTaken=PT0.01S
afterThirdSize=2
retainedStatuses=[204, 500]
unknownPath=/redacted
```

Thus, the first record was evicted after the third addition, and the retained data contains no email query, order ID, original headers, or excluded identity fields. Status and duration remain to serve the chosen diagnostic question.

## 7. Wiring the repository into a Boot application

In a Boot 3.3 web application that already has the Actuator dependency, place the following configuration class in a package scanned by the application. This snippet supplements an existing application; it is not the startup entrypoint for the standalone program above:

```java
package example.exchangeprivacy;

import org.springframework.boot.actuate.web.exchanges.HttpExchangeRepository;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@Profile("local-exchange-diagnostics")
public class HttpExchangePrivacyConfiguration {

    @Bean
    public HttpExchangeRepository httpExchangeRepository() {
        return new MinimizedHttpExchangeRepository(50);
    }
}
```

Register only one repository under this policy. The `delegate` object stays internal and must not also be registered as a public bean so other code cannot accidentally write raw data directly into it.

Put the properties in `application-local-exchange-diagnostics.yml`:

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

Activate the `local-exchange-diagnostics` profile when running the development application. Configuring only the duration group reduces collection up front; the repository continues enforcing the storage policy even if other code adds exchanges directly.

In a shared-server model using default configuration without a separate management port, binding `127.0.0.1` restricts the server to loopback. If the application has a separate management port, configure the management server's network scope accordingly.

Exposure only determines over which technology an endpoint is exposed; it does not authenticate or authorize readers on its own. If Spring Security is present, check the application's rules for this endpoint; do not open public read access merely for diagnostic convenience. [Actuator exposure and security](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)

## 8. Testing the policy with dummy data

Before using with real traffic, include test cases focused on the storage boundary:

| Input data | What to confirm after reading the repository |
| --- | --- |
| `Authorization`, `authorization`, and custom headers | No values remain if the policy drops all headers |
| Multi-valued or long headers | Not retained through a secondary copy path |
| Query containing dummy email/token | Query has been completely stripped |
| Path containing email, encoded characters, or unknown route | Returns generic label, not the raw path |
| Principal, session ID, and IP | Absent from stored records per the example policy |
| Add C+1 exchanges | Repository retains only C records at the fixed capacity |
| Different inputs in the same API group | Still enough info for the diagnostic question without accidentally keeping resource IDs |

Do not rely solely on a screenshot of a masked UI. Inspect the objects returned by the repository and, when web-integrated, the JSON response of `/actuator/httpexchanges`. This API includes URI, header, principal, session, and other fields depending on recorded data. [HTTP Exchanges schema](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/httpexchanges.html)

The limits of the example should stay explicit: timestamp and certain metadata remain; this is a chosen data-minimization policy, not a certification that nobody can correlate an exchange with another event. Fixed timestamps in the program only keep stdout deterministic, not an application policy to alter timestamps.

## 9. Common design mistakes

- **Leaving defaults and assuming all secrets are masked:** the standard mechanism excludes certain headers, but does not know every business header name.
- **Reducing capacity only:** fewer records can still contain tokens or personal data.
- **Dropping the query only:** paths, principals, sessions, and response headers can still leak information.
- **Sanitizing JSON only when reading:** original data was still stored internally.
- **Enabling `authorization-header` or `cookie-headers` for easier debugging:** can pull credentials into the diagnostic store; find ways to verify hypotheses without collecting real tokens.
- **Logging the raw exchange before minimizing data:** creates a copy outside the controlled boundary.
- **Treating restart or disabling recording as deleting every copy:** exported snapshots, logs, or heap dumps have their own lifecycles.

If HTTP exchanges are not needed for a run, disable recording instead of letting it collect and then trying to delete afterward. If durable history or distributed diagnostics are needed, choose a suitable observability architecture and apply the same data policy at the corresponding storage layer.

## 10. Self-check

1. Why does `recording.include: [time-taken]` still not address an email embedded in the URI?
2. Is an `X-Api-Key` header automatically protected simply because `Authorization` is excluded by default?
3. What does the example policy preserve and what does it trade off when turning `/orders/123` into `/orders/_id`?
4. Does a repository holding only 50 records prove that data does not remain for more than 10 minutes?

Comparison: (1) URI is part of baseline info, not the omitted header groups; (2) no, custom headers require their own policy; (3) the API category remains known, while the order ID for tracing individual resources is lost; (4) no, record count and retention duration are two different limits.
