# Enabling the `httpexchanges` Endpoint with `HttpExchangeRepository`

## 1. From an HTTP request to diagnostic data

When testing an API, you often want to know which request the application just received, what status code it returned, and how long processing took. Looking only at the result of a single call makes it hard to compare multiple consecutive requests. Actuator can retain information about recent HTTP exchanges for you to inspect.

An **HTTP exchange** is information associated with a request–response pair. `httpexchanges` is the endpoint used to read the stored information. In Spring Boot 3.3, you must provide an `HttpExchangeRepository` bean to enable recording; merely adding Actuator or exposing the endpoint in configuration does not provide a place to store data. [Spring Boot 3.3 HTTP Exchanges Recording Documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/http-exchanges.html)

This lesson focuses on a Spring MVC application and how to wire all the components needed to read data at `/actuator/httpexchanges`. You should know how to declare a bean with `@Bean`, create a `@GetMapping` API, and configure YAML.

## 2. Roles of the repository, recorder, and endpoint

`HttpExchangeRepository` is an interface for storing and retrieving `HttpExchange` objects, with two main methods:

```java
void add(HttpExchange httpExchange);
List<HttpExchange> findAll();
```

This is a signature excerpt to explain the contract, not a standalone Java file. `add(...)` accepts one record; `findAll()` returns the records currently held by the repository. The word `Repository` here does not mean you must create a Spring Data JPA repository, database table, or query methods. [`HttpExchangeRepository` API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/web/exchanges/HttpExchangeRepository.html)

Conceptual flow in a Servlet application:

```text
HTTP request enters the application
        ↓
Filter records information around request handling
        ↓
HttpExchangeRepository.add(exchange)
        ↓
Data is held in the repository
        ↓
GET /actuator/httpexchanges
        ↓
Endpoint reads the repository and returns JSON
```

`HttpExchangesFilter` is the Servlet filter for this recording. With standard Spring Boot auto-configuration, you supply the repository and let Boot set up the recording infrastructure; you do not need to insert `repository.add(...)` calls into each controller. [`HttpExchangesFilter` API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/web/exchanges/servlet/HttpExchangesFilter.html)

`HttpExchangesEndpoint` receives `HttpExchangeRepository` via its constructor and provides the read operation. Therefore, the endpoint is the data-reading side, while the repository is the shared bridge between the recording side and the reading side. [`HttpExchangesEndpoint` API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/web/exchanges/HttpExchangesEndpoint.html)

To diagnose issues accurately, check each condition separately:

| Condition | Question to answer |
| --- | --- |
| Web and Actuator infrastructure present | Does the application run HTTP and have the Actuator dependency? |
| Repository bean present | Does Spring manage an `HttpExchangeRepository` object? |
| Recording enabled | Does any configuration disable recording? |
| Endpoint enabled | Is `httpexchanges` disabled at the endpoint level? |
| Endpoint exposed over HTTP | Does the exposure list include `httpexchanges` without excluding it? |
| Access permitted | Do security rules allow the caller to read the endpoint? |

In Spring Boot 3.3, this endpoint is enabled by default but not exposed over HTTP by default; HTTP exposes only `health` by default. `exposure.exclude` takes precedence over `exposure.include`. Exposing over HTTP also does not automatically grant access when Spring Security is present. [Endpoint Enabling, Exposing, and Security Rules](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)

## 3. Standalone example: provide the repository, then generate traffic

The example uses JDK 21, Spring Boot 3.3.0, and Gradle Wrapper 8.5. This is a standalone hands-on project. The paths below are relative to the sample project directory.

### 3.1. Structure and dependencies

```text
http-exchanges-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
└── src/main/
    ├── java/example/exchanges/ExchangeDemoApplication.java
    └── resources/application.yml
```

Wrapper 8.5 needs to be present in the sample project. If the wrapper is not yet present and Gradle is installed on the machine, create `settings.gradle` as below, run `gradle wrapper --gradle-version 8.5`, and then add `build.gradle` with the plugin configuration.

Contents of `settings.gradle`:

```groovy
rootProject.name = 'http-exchanges-demo'
```

Contents of `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

`spring-boot-starter-web` provides the Servlet application and Spring MVC; `spring-boot-starter-actuator` provides the Actuator components. The example omits Spring Security so you can observe the basic mechanism on a local machine.

### 3.2. Registering a bean of type `HttpExchangeRepository`

Full contents of `src/main/java/example/exchanges/ExchangeDemoApplication.java`:

```java
package example.exchanges;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.actuate.web.exchanges.HttpExchangeRepository;
import org.springframework.boot.actuate.web.exchanges.InMemoryHttpExchangeRepository;
import org.springframework.context.annotation.Bean;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ExchangeDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ExchangeDemoApplication.class, args);
    }

    @Bean
    HttpExchangeRepository httpExchangeRepository() {
        InMemoryHttpExchangeRepository repository =
                new InMemoryHttpExchangeRepository();
        repository.setCapacity(100);
        return repository;
    }

    @RestController
    public static class DemoController {

        @GetMapping("/demo/ping")
        public String ping() {
            return "pong";
        }
    }
}
```

The decisive point is the object returned from the `@Bean` method, not the variable name `repository`. Spring manages the bean with type `HttpExchangeRepository`; Boot can use that bean for the HTTP exchanges feature. If you only call `new InMemoryHttpExchangeRepository()` in a local variable inside a controller without registering a bean, auto-configuration does not receive the storage it needs.

`InMemoryHttpExchangeRepository` is the built-in in-memory implementation. By default it retains the 100 most recent exchanges; the `setCapacity(100)` line makes that choice explicit in the example and can be omitted when using the default. The API lets you change capacity with `setCapacity(...)` and reverse listing order with `setReverse(...)`. [Default Behavior](https://docs.spring.io/spring-boot/3.3/reference/actuator/http-exchanges.html), [In-Memory Repository API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/web/exchanges/InMemoryHttpExchangeRepository.html)

### 3.3. Exposing the endpoint and selecting data to record

Contents of `src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080

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

The three configuration branches have distinct responsibilities:

- `management.endpoint.httpexchanges.enabled` enables the endpoint with ID `httpexchanges`.
- `management.endpoints.web.exposure.include` allows mapping that endpoint over HTTP.
- `management.httpexchanges.recording` controls exchange recording and which optional information groups are included in records.

Notice the singular `endpoint` in the property enabling a single endpoint and the plural `endpoints` in the exposure section. The `management.httpexchanges` branch is for the recording mechanism and does not sit inside `management.endpoint`.

Both `enabled: true` values are written explicitly for clarity, even though in Boot 3.3's default configuration they are already enabled. Exposing `health,httpexchanges` is still required to access the new endpoint over HTTP. [Actuator Configuration Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html)

In the example, `recording.include` selects only `time-taken`: basic information to identify the request and status code is still included, while header groups are not requested. `TIME_TAKEN` is one option of `Include`; other options include request headers, response headers, remote address, principal, and session ID. Choose this list based on observability needs; do not confuse it with the list of exposed endpoints. [`Include` Options](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/web/exchanges/Include.html)

### 3.4. Starting and calling the API

On PowerShell, from the sample project directory:

```powershell
.\gradlew.bat bootRun
```

On Linux/macOS:

```bash
./gradlew bootRun
```

Wait for the application to finish starting, then open another terminal window. On PowerShell:

```powershell
curl.exe -s http://127.0.0.1:8080/demo/ping
```

Exact response body:

```text
pong
```

Read Actuator data:

```powershell
curl.exe -s http://127.0.0.1:8080/actuator/httpexchanges
```

On Linux/macOS, use `curl` instead of `curl.exe`. Because the sample configuration does not change the context path, base path, or a separate management port, the path is `/actuator/httpexchanges` on port 8080.

The endpoint returns an object with an `exchanges` array; each element contains request and response details. Key fields for locating the call just made are `request.uri`, `request.method`, `response.status`, and, when recorded, `timeTaken`. Timestamps and durations vary across runs, so do not compare the full JSON verbatim against a fixed sample. [HTTP Exchanges Response Structure](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/httpexchanges.html)

To verify results more reliably on PowerShell, filter specifically for the test path:

```powershell
$snapshot = Invoke-RestMethod http://127.0.0.1:8080/actuator/httpexchanges
$ping = @($snapshot.exchanges | Where-Object {
    ([uri]$_.request.uri).AbsolutePath -eq '/demo/ping'
})
if ($ping.Count -eq 0) {
    throw 'Record /demo/ping not found'
}
$ping[0].request.method
$ping[0].response.status
```

With the successful `/demo/ping` call above, the last two lines print:

```text
GET
200
```

This check filters by path instead of assuming the first element of all `exchanges` is always the target request. When there are other requests or you query Actuator multiple times, the list may contain additional records.

## 4. Experiments to distinguish each configuration layer

For each experiment, change only one factor, restart the application, and call `/demo/ping` again before reading the endpoint. Do not use in-memory data from a previous startup as evidence for a subsequent run.

| Change to the example | What to observe | Explanation |
| --- | --- | --- |
| Keep the sample configuration as-is | Finds record `GET /demo/ping` with status `200` | Recording side, storage, and reading side are all present |
| Remove the `@Bean` repository method, keep exposure | No auto-configured HTTP exchanges endpoint like the sample case | Exposure does not create a repository |
| Keep the bean, remove `httpexchanges` from exposure | Cannot read that endpoint via the default HTTP path | Having storage does not mean the HTTP read path is open |
| Keep bean and exposure, set `recording.enabled: false` | After restart, calling ping then reading shows no new ping record | Disabling recording differs from disabling the endpoint |
| Keep the rest, set `endpoint.httpexchanges.enabled: false` | No read operation for HTTP exchanges via the endpoint | Enabling recording does not re-enable a disabled endpoint |

Specifically for the experiment that disables recording, with a fresh in-memory repository and no code manually adding records, the read response is:

```json
{"exchanges":[]}
```

`management.httpexchanges.recording.enabled=false` turns off automatic recording; you should not infer that it deletes existing data in a custom repository implementation. Which data remains retained belongs to the repository's policy. [Recording Control](https://docs.spring.io/spring-boot/3.3/reference/actuator/http-exchanges.html)

## 5. Diagnosing when the endpoint is not working yet

| Symptom | Points to check |
| --- | --- |
| `/demo/ping` is also unreachable | Has the application started; are the address and port correct |
| HTTP `404` at `/actuator/httpexchanges` | Actuator dependency, repository bean, endpoint enabled, exposure include/exclude, and actual path |
| HTTP `401` or `403` | Authentication mechanism, access permissions, and Spring Security configuration |
| `exchanges` exists but the target call is missing | Did you call the right application process; is recording disabled; was the record evicted from the recent window |
| Missing headers or user principal | Does `recording.include` request that data group; did that info exist in the request |
| Data disappears after restart | Using an in-memory repository without durable storage |

Do not conclude from a `404` status that the bean is definitely missing: multiple different conditions can produce the same symptom. Nor should you fix it by exposing `*` from the start; keeping an explicit endpoint list helps pinpoint the exact missing condition.

If Spring Security is on the classpath, Boot secures endpoints other than `health` by default when no application-defined `SecurityFilterChain` exists. When a custom chain is present, you must inspect the application's own rules. Exposure and access control are two independent configurations. [Actuator Security](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.security)

## 6. Limitations and sensible usage

`InMemoryHttpExchangeRepository` is suitable for testing and diagnostics in development environments; Spring Boot documentation recommends an appropriate tracing/observability solution for production or an application-implemented repository. [In-Memory Repository Usage Scope](https://docs.spring.io/spring-boot/3.3/reference/actuator/http-exchanges.html)

When considering extending the example, concrete design questions must be answered:

- **Capacity:** keeping more records consumes more memory; you need to know how much history you genuinely need to observe.
- **Restarts:** if data must survive restarts, you must design durable storage rather than relying on an in-memory object.
- **Multiple processes:** if each application replica creates its own repository like the example, each replica holds only its own data; one call through a load balancer does not represent the whole system.
- **Sensitive information:** omitting headers does not automatically make URIs non-sensitive. URL parameters still require review; do not put secrets in URLs.
- **Audit purposes:** if long-term business evidence is needed, you must design appropriate events, retention periods, and read permissions. A window of recent HTTP exchanges does not satisfy that requirement on its own.

You do not need to implement a database repository just to make the endpoint appear. Get the in-memory example running first, confirm the record–store–read flow, and only then choose a storage policy suited to real needs.

## 7. Self-check

1. Why is adding `httpexchanges` to exposure without a repository bean still not enough?
2. How does disabling `management.endpoint.httpexchanges.enabled` differ from disabling `management.httpexchanges.recording.enabled`?
3. If you can read `exchanges` but `/demo/ping` is missing, what should you check first?
4. Why does the repository in the example not need Spring Data JPA?

Comparison: (1) exposure only controls exposing the endpoint over a technology and does not create storage; (2) one property controls the endpoint reading side while the other controls recording; (3) check that you called the right application and recording is enabled, then consider capacity or other traffic; (4) this is a bean implementing the `HttpExchangeRepository` contract, and the example uses memory rather than a database.
