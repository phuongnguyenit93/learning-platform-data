# Verifying the Application Using Browser, curl, and WebTestClient

**Topic:** Spring Security Reactive (Spring WebFlux) · **Context:** Application Bootstrap.

After creating a Spring WebFlux application and configuring Spring Security, two independent things must be verified: **does the application start and serve HTTP properly**, and **are authentication/authorization rules enforced correctly**. A browser helps observe end-user behavior; `curl` lets you inspect exact requests/responses; `WebTestClient` turns expectations into repeatable checks during development and CI.

This lesson provides a Java 17+ sample application, specifies expected outcomes, shows how to run all three channels, and explains how to distinguish startup, routing, authentication, authorization errors, and reactive-specific behaviors. All accounts/passwords in the sample are **for localhost learning only**, never reuse them in real systems.

## 1. Objectives and verification matrix

After this lesson, you can:

1. Run a WebFlux application with `SecurityWebFilterChain` and know when the server is truly ready to listen on its port.
2. Open endpoints in a browser and inspect HTTP status codes and response headers in DevTools rather than just looking at the rendered page.
3. Use `curl` to send requests without credentials, with valid/invalid credentials, and with credentials lacking a role; compare status, headers, and body.
4. Write `WebTestClient` tests that boot the Spring context and verify the entire HTTP path, including Spring Security `WebFilter`s.
5. Distinguish `200 OK`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found`, `302` redirects, and CSRF errors; know when a single status alone is insufficient proof.
6. Keep tests independent and stable, without calling `subscribe()` inside controllers or relying on external data/users.

Expected matrix of the **sample application below** (all are `GET`):

| Endpoint | Credentials | Result | Meaning |
| --- | --- | --- | --- |
| `/api/public` | None sent | `200`, body `public-ok` | Public route is genuinely accessible |
| `/api/me` | None sent | `401` and Basic challenge header | Route requires authentication |
| `/api/me` | `reader` / `reader123` | `200`, body `reader` | Authentication succeeds; principal read from Reactor Context |
| `/api/me` | `reader` / wrong password | `401` | Invalid credentials are rejected |
| `/api/admin` | `reader` / `reader123` | `403` | Authenticated, but lacking admin permission |
| `/api/admin` | `admin` / `admin123` | `200`, body `admin-ok` | User with role is permitted |
| `/api/admin` | None sent | `401` | Authentication required before checking roles |

**Note on HTTP codes:** `401` here indicates missing/invalid authentication; `403` means insufficient permissions after authentication. This is the expectation for the sample's HTTP Basic setup, not an immutable rule for every app: form login can return `302`, resource servers can use Bearer challenges, and a custom `authenticationEntryPoint` or `accessDeniedHandler` can alter responses.

## 2. Building a minimal WebFlux app to test

### 2.1. Tools and structure

Requires JDK 17+, Maven 3.9+, and `curl`. No database, Docker, or special browser plugins are needed. The sample uses **Spring Boot 3.5.16** so test APIs are reproducible; this is an example version, not a requirement that every project use this exact release.

```text
reactive-security-check/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/check/
    │   │   ├── ReactiveSecurityCheckApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── ProbeController.java
    │   └── resources/application.properties
    └── test/java/demo/check/
        └── ReactiveSecurityCheckApplicationTests.java
```

Create `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>reactive-security-check</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

Create `src/main/resources/application.properties`:

```properties
spring.application.name=reactive-security-check
server.port=8080
```

Keep only the WebFlux starter for this sample. If `spring-boot-starter-web` is accidentally added as well, Spring Boot may choose a Servlet/MVC application, causing behavior/filters and test types to differ from expectations. In projects having both stacks, you must confirm the application type before comparing results.

### 2.2. Startup entry point

`src/main/java/demo/check/ReactiveSecurityCheckApplication.java`:

```java
package demo.check;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveSecurityCheckApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveSecurityCheckApplication.class, args);
    }
}
```

`@SpringBootApplication` enables component scanning in package `demo.check` and subpackages. Security and Controller classes in the same package will be discovered by Spring.

### 2.3. Explicit security configuration

`src/main/java/demo/check/SecurityConfig.java`:

```java
package demo.check;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails reader = User.withUsername("reader")
            .password("{noop}reader123")
            .roles("READER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password("{noop}admin123")
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public").permitAll()
                .pathMatchers("/api/admin").hasRole("ADMIN")
                .pathMatchers("/api/me").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }
}
```

Explanation of choices affecting verification:

- `httpBasic(...)` accepts HTTP Basic and returns challenges for requests needing authentication. `formLogin(...disable())` makes API checks predictable (avoiding automatic redirects to a `302` login page).
- `permitAll()` applies to the public endpoint, `authenticated()` requires a valid identity, and `hasRole("ADMIN")` checks authority `ROLE_ADMIN` per the default prefix.
- `anyExchange().denyAll()` intentionally rejects every undeclared route. Therefore, **in this exact configuration**, even a nonexistent URL can receive `401`/`403` at the security layer before routing ever has a chance to return `404`. Do not use unknown URLs to infer whether a controller exists.
- `{noop}` stores plaintext passwords in the example to keep local execution simple. Real applications must use a proper password encoder, secret management, HTTPS, and isolated test accounts; never hardcode production passwords.

### 2.4. Three endpoints with stable responses

`src/main/java/demo/check/ProbeController.java`:

```java
package demo.check;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class ProbeController {

    @GetMapping("/public")
    public Mono<String> publicEndpoint() {
        return Mono.just("public-ok");
    }

    @GetMapping("/me")
    public Mono<String> currentUser() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);
    }

    @GetMapping("/admin")
    public Mono<String> adminEndpoint() {
        return Mono.just("admin-ok");
    }
}
```

`/api/me` reads `Authentication` from **Reactor Context** when the Publisher is subscribed by WebFlux; it does not rely on `ThreadLocal` and does not call `subscribe()` manually inside the controller. All three endpoints return string bodies, making verification straightforward without depending on a JSON serializer or database.

## 3. Running the application and confirming the server is ready

In the project directory:

```bash
java -version
mvn -version
mvn spring-boot:run
```

If a Maven Wrapper is present, replace `mvn` with `./mvnw` on macOS/Linux or `mvnw.cmd` on Windows. Startup succeeds when the process **stays running** and logs indicate WebFlux/Netty has started on port 8080. Log contents and timestamps vary by version, so do not use a single fixed log line as the sole criterion.

In **another** terminal, test a simple request:

```bash
curl -i http://localhost:8080/api/public
```

Expected output: status `HTTP/1.1 200 OK` (or equivalent HTTP format) and body `public-ok`; headers like `Date`, `Content-Length`, and `Content-Type` may vary by environment. On connection refused/timeout, first inspect the process, address, port, proxy, and startup logs before concluding security is wrong.

If port 8080 is already taken, change `server.port` to a free port and update all `curl`/browser URLs accordingly. Automated tests in Section 6 use a random port, so they do not depend on this port.

## 4. Manual verification with a browser

Open Chrome, Edge, or Firefox. First visit:

```text
http://localhost:8080/api/public
```

The page may simply display `public-ok` (with no HTML UI). This is a good sign: the controller was invoked and the body was returned. Open **DevTools → Network**, reload the page, and select the request to inspect `Request URL`, `Request Method`, `Status Code`, `Response Headers`, and `Response`.

Next, open an incognito/private window to limit cached Basic credentials in the browser, then go to `http://localhost:8080/api/me`. With a Basic challenge, the browser **may** show a username/password prompt; depending on the browser, it might also display a 401 response instead of a prompt. Enter `reader` / `reader123` if prompted; a valid request will display `reader`. Check Network again to confirm status `200` on the credentialed request, rather than relying only on page content.

Finally, access `http://localhost:8080/api/admin` as `reader`: the authenticated request is still rejected with `403`. Try `admin` / `admin123` in a **new login session/window** and the endpoint returns `admin-ok`. When switching users if the browser keeps sending the old account, close the incognito window, open a new session, or inspect `Authorization` in the request; HTTP Basic can cache credentials and the sample app has no default logout button.

**Reading signals accurately:** a browser can render an error message, blank page, or JSON depending on `Accept` headers and error handlers. A screen that "looks like an error" does not provide enough evidence of 401 vs. 403. Rely on Network and the actual response.

### 4.1. How does a browser differ from curl?

- Browsers can send cookies, cache HTTP Basic credentials, handle challenges automatically, follow redirects, and fetch subresources and JavaScript. A single page load can trigger **multiple requests**.
- A page running on another origin can hit **CORS**: the browser blocks JavaScript from reading the response even though `curl` calls the endpoint successfully. CORS and authentication are two separate policies.
- DevTools reveals redirect chains and the final response; always inspect the specific request that failed, not just the URL in the address bar.
- With default form login, an unauthenticated `GET` can often lead to `302`/a login page. The sample disables form login to focus on Basic auth. Do not mistake a `302` redirect for "access was granted".

## 5. Exact verification with curl

`curl` is ideal for scripting repeatable requests and receiving comparable output. Use `-i` to see the status line, headers, and body together; `-u` to send Basic credentials. On older Windows PowerShell, `curl` may be an alias for `Invoke-WebRequest`; in that case, invoke `curl.exe` explicitly.

### 5.1. Without credentials: public 200, protected 401

```bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/me
curl -i http://localhost:8080/api/admin
```

Verify:

- Public returns `200` and body `public-ok`.
- Both protected requests return `401` when unauthenticated.
- The `401` response for HTTP Basic includes a `WWW-Authenticate` header with scheme `Basic`. This invites the client to send credentials, not an authorization grant.

### 5.2. Valid and invalid credentials

```bash
curl -i --user reader:reader123 http://localhost:8080/api/me
curl -i --user reader:wrong http://localhost:8080/api/me
curl -i --user reader:reader123 http://localhost:8080/api/admin
curl -i --user admin:admin123 http://localhost:8080/api/admin
```

Compare in order: `200` + `reader`; `401`; `403`; `200` + `admin-ok`.

`--user` makes `curl` build the Basic header; there is no need to Base64-encode manually. Basic only encodes credentials in Base64 representation, **it does not encrypt data in transit**, so outside localhost you must use HTTPS. Running commands containing passwords can expose credentials in shell history and process lists; in real environments, use `curl --user reader` so `curl` prompts interactively for the password, test tokens/secure secret stores, or appropriate environment variables.

### 5.3. Separating status code from body for verification scripts

On systems with a suitable shell:

```bash
curl --silent --show-error --output /dev/null \
  --write-out '%{http_code}\n' \
  --user reader:reader123 \
  http://localhost:8080/api/admin
```

Expected output:

```text
403
```

This command form prints only the status for easy automated checks; to investigate failures, return to `curl -i` to see challenges/headers/body. `curl` **does not automatically treat HTTP 4xx as a process error** unless `--fail` is enabled, so do not use `curl`'s exit code 0 alone as proof that authorization passed. `--fail` alters body handling and exit codes for HTTP 4xx/5xx; decide whether to use it based on your script's purpose.

A good check always specifies **method + path + credentials + expected status + key body/headers**. Calling an API and seeing JSON or HTML returned is not enough to confirm permissions are right.

## 6. Turning expectations into WebTestClient tests

`WebTestClient` is Spring WebFlux's test client. It sends HTTP requests, subscribes for responses, and provides assertion APIs; application controllers/services must still **return Publishers** so the framework manages subscriptions. Here we choose `@SpringBootTest(webEnvironment = RANDOM_PORT)`: Spring starts a real server on a **random port** and configures `WebTestClient` to send requests to that server. Tests do not require an external `mvn spring-boot:run` process.

Create `src/test/java/demo/check/ReactiveSecurityCheckApplicationTests.java`:

```java
package demo.check;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ReactiveSecurityCheckApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointAllowsAnonymous() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public-ok");
    }

    @Test
    void protectedEndpointChallengesAnonymous() {
        client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().exists(HttpHeaders.WWW_AUTHENTICATE);
    }

    @Test
    void validReaderCanSeeOwnName() {
        client.get().uri("/api/me")
            .headers(headers -> headers.setBasicAuth("reader", "reader123"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("reader");
    }

    @Test
    void incorrectPasswordIsRejected() {
        client.get().uri("/api/me")
            .headers(headers -> headers.setBasicAuth("reader", "wrong"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedReaderCannotAccessAdmin() {
        client.get().uri("/api/admin")
            .headers(headers -> headers.setBasicAuth("reader", "reader123"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminCanAccessAdminEndpoint() {
        client.get().uri("/api/admin")
            .headers(headers -> headers.setBasicAuth("admin", "admin123"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin-ok");
    }

    @Test
    void adminRouteChallengesAnonymous() {
        client.get().uri("/api/admin")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
```

Run from the project directory:

```bash
mvn test
```

Expect Maven to report a successful build and **7 tests pass** (when only the test class above is present). Do not copy a fixed Maven output verbatim since timings, plugin versions, ordering, and report formats vary. If a test fails, inspect the assertion: *expected status*, *actual status*, response headers/body, and stack trace to tell whether the issue is in startup, filters, routing, or data.

**Explaining the assertion chain:**

1. `client.get().uri(...)` builds the request specification.
2. `headers(h -> h.setBasicAuth(...))` sends credentials like a real HTTP client; it does not inject `Authentication` directly into controller code.
3. `exchange()` actually executes the request and receives the response.
4. `expectStatus()` verifies the HTTP decision; `expectHeader()` verifies the Basic challenge; `expectBody()` proves the controller returned the right content after passing security.

In this exercise, asserting `200` **and** the right body matters more than `200` alone: another endpoint returning 200 or a handler returning wrong content must still fail the test. Conversely, `401` and `403` assertions are two critical negative tests ensuring security was not accidentally relaxed.

### 6.1. When to use RANDOM_PORT, mocked WebFlux, or layered tests?

| Approach | Scope | Things to watch out for |
| --- | --- | --- |
| `@SpringBootTest(RANDOM_PORT)` + `WebTestClient` (used in sample) | Real HTTP through server, filters, routing, serialization, and app context | Relatively slower than slice tests; well suited for end-to-end startup + security checks |
| `@SpringBootTest` + `@AutoConfigureWebTestClient`, appropriate mock environment | Tests WebFlux flows in the application context without opening a real server port | Must ensure security filters are applied and understand which beans are loaded |
| `@WebFluxTest` | Fast web/controller slice, can mock services | Does not automatically include all services/security configs depending on app; import needed configs and mocks |
| `WebTestClient.bindToServer()` | Manually configures client against an already-running server | Must manage base URL/port and server lifecycle |

For mock tests bound to a Spring context, `spring-security-test` supports `SecurityMockServerConfigurers.mockUser(...)` or OAuth2/JWT mocks for the respective mechanisms. **Do not use `mockUser` as if it transmits identity over an HTTP connection to a real server**: in `RANDOM_PORT` tests, send real client-like credentials/tokens, such as `setBasicAuth` in the example. When testing an OAuth2 resource server, replace Basic credentials with a Bearer token whose issuer/signature/claims are handled appropriately.

## 7. Verifying proper reactive flow without manual subscribe

WebFlux receives `Mono`/`Flux` from controllers and subscribes to produce the HTTP response. The right way:

```java
@GetMapping("/items/{id}")
public Mono<Item> one(@PathVariable String id) {
    return repository.findById(id);
}
```

Do not do the following:

```java
@GetMapping("/items/{id}")
public Mono<Item> wrong(@PathVariable String id) {
    repository.findById(id).subscribe(item -> audit(item)); // Detaches into an unmanaged task
    return Mono.empty();
}
```

These two fragments are illustrative only (requiring `Item`, `repository`, `audit`, and corresponding imports), not standalone Java files. Calling `subscribe()` manually in a handler lets work continue outside the HTTP lifecycle, and errors, cancellation, and security context are no longer managed along the request path as expected. `WebTestClient` verifies the HTTP response, yet **does not automatically prove** no detached async side effects remain outside the response. For business logic writing or processing sensitive data, test underlying dependencies and actual side effects as well.

If an endpoint does not return data as expected, distinguish **assembly** (building the Publisher) from **subscription** (running the cold source). Do not conclude "it did not run" just because logs do not appear before `exchange()`/before an HTTP request. When using `Mono.defer`, `fromSupplier`, or reactive repositories, work normally executes at subscription time. Security context in WebFlux is usually read via `ReactiveSecurityContextHolder` on the same reactive stream; do not rely on a `ThreadLocal` variable bound to an earlier request.

## 8. Reading errors: startup, endpoint, or security?

| Symptom | Possibilities to investigate | Next check |
| --- | --- | --- |
| `curl: (7) Failed to connect` or browser `ERR_CONNECTION_REFUSED` | Server not running, startup failed, wrong host/port | Check startup logs, `server.port`, listening process; try `/api/public` |
| `200` but wrong body | Different route, controller logic, mock, serialization, or stale deployment | Check exact response body, request URL, port, app instance |
| `401` on `/api/me` with seemingly right credentials | Wrong username/password, Basic header not sent, or different auth config | Use `curl -i -u ...`, check `WWW-Authenticate`, user store, and safe logs |
| `403` on `/api/admin` using `reader` | **Expected**: user is authenticated but lacks `ROLE_ADMIN` | Try user `admin` and check `hasRole`/authorities |
| `403` on POST/PUT/DELETE despite valid role | Likely missing CSRF token, beyond authorization error | Check method, CSRF config, token/cookie, and security logs; do not disable CSRF just to pass tests |
| `302` instead of `401` | Possibly form login, HTTPS redirect, or app/proxy | Use `curl -i` without following redirects; check `Location` and filter config |
| `404` on an expected endpoint | Mapping missing, wrong prefix/method, controller not scanned | Check `@RequestMapping`/`@GetMapping` and package scan; also check security rules |
| `403` on an unknown URL in this sample | `anyExchange().denyAll()` blocks before routing | Test known URLs; do not infer endpoint existence from 403 alone |
| Test `@Autowired WebTestClient` missing bean or running MVC | Wrong test dependencies/config, wrong web stack | Verify WebFlux starter, test environment type, Boot version, context startup |
| Tests fail intermittently in parallel runs | Shared state, test data, cache, fixed port, or external dependency | Use `RANDOM_PORT`, isolated fixtures, order-independent assertions |

**CSRF is a separate check.** In Spring Security WebFlux, CSRF is normally enabled by default and affects state-changing requests. This lesson only uses `GET` to clarify authentication/authorization. When expanding to `POST`, include tests for *valid token*, *missing token*, and *invalid token* per the application's mechanism, rather than conflating a 403 from CSRF with a 403 from a missing role. CSRF and CORS address different threats.

**Do not leak secrets while debugging:** avoid copying/pasting `Authorization`, cookies/sessions, JWTs, and passwords into logs, tutorial videos, or tickets. With HTTP Basic, header payloads can be Base64-decoded, so always use HTTPS outside local environments.

## 9. Verification workflow after every bootstrap/config edit

1. **Builds cleanly:** `mvn test` runs on the right JDK version; do not ignore compile/import errors.
2. **App starts cleanly:** `mvn spring-boot:run` does not exit with an exception and `/api/public` returns `200` on the expected port.
3. **From a browser:** at least one public route and one protected route are checked via DevTools Network; watch user state and cached credentials.
4. **From curl:** record comparison requests for `200`, `401`, and `403` with valid/invalid credentials and different roles, plus key bodies/headers.
5. **From WebTestClient:** have tests for public access, blocking unauthenticated requests, rejecting wrong passwords, rejecting insufficient permissions, and permitting valid roles; run automatically after config changes.
6. **Diagnose at the right layer:** do not "fix" the wrong filter just because a port is closed, do not remove security to avoid 403, and do not assume one 200 test proves the whole policy correct.

When moving from the sample to a real application, replace endpoints with key business routes, build a matrix by **method/path/role**, and add cases for *no permission*, *recently revoked permission*, *another user's data*, expired tokens, and equivalent paths (e.g., the same service reached through another endpoint). Check bodies and side effects alongside HTTP statuses; authorization policies specifically must be verified both at the web boundary and at the method/data layer where applicable.

## 10. Self-assessment practice exercises

**Question 1.** You open `/api/me` in a browser, see a login dialog, and then see `reader`. Does that already prove the initial 401? **No.** Inspect the uncredentialed request in Network or use `curl -i`; the browser can handle the challenge automatically and only display the final response.

**Question 2.** `curl` exits with code 0 yet the response status is 403. Did the test succeed? **No.** By default `curl` can exit 0 on HTTP 4xx; inspect status/body or use `--fail` policies appropriately.

**Question 3.** `reader` calls `/api/admin` and receives 403, while `admin` receives 200. What does the check prove? **It proves the authorization rule for that endpoint and the two credential types behave as expected.** It does not yet prove every other endpoint or underlying data is secure.

**Question 4.** Does a `RANDOM_PORT` test require opening a terminal running `spring-boot:run` first? **No.** The test starts its own server on a random port. If a test tries to hit `localhost:8080` with a hardcoded URL, that is a different client setup and needs review.

**Question 5.** After adding `POST /api/items`, requests as admin still receive 403. Should you disable CSRF right away? **No.** Determine whether a CSRF token is missing, then add token receipt/submission matching real clients and corresponding tests.

**Question 6.** Why not use only a browser or only `WebTestClient`? A browser reflects real behavior with cookies, caches, prompts, and redirects/CORS; `curl` gives reproducible requests and transparent responses; `WebTestClient` provides consistent, automated checks. All three complement each other when bringing an application online.

### Official reference documentation

- Spring Boot 3.5, *Testing Spring Boot Applications*: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Security, *WebFlux Security*: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Framework, *Testing with WebTestClient*: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Spring Security, *CSRF for WebFlux*: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
- curl, *Command line tool documentation*: https://curl.se/docs/manpage.html

**Outcome to achieve:** Regardless of whether you verify via browser, `curl`, or `WebTestClient`, the same request and credentials must consistently reflect **the right method, right endpoint, right authentication state, right permissions, and right expected response**. When discrepancies appear, narrow the cause by execution environment, headers/cookies, security filters, routing, and only then reactive logic.