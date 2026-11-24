# ServerWebExchangeMatcher: Matching Paths and HTTP Methods in Reactive Spring Security

## 1. Objectives and Use Cases

A Spring WebFlux application often has multiple HTTP rules: `GET /api/items` allows public reading, `GET /api/items/{id}` requires an account with read permission, and `POST /api/items` is restricted to users with write permission. At the same time, the application may use a **separate security filter chain** for `/api/**` and another chain for the remaining URLs. To configure this properly, you must first determine **which requests match which conditions**.

`ServerWebExchangeMatcher` is the reactive Spring Security interface for answering that question. A matcher receives a `ServerWebExchange` (containing the request and response) and returns the match result as a `Mono<MatchResult>`. Spring Security uses matchers to **select a `SecurityWebFilterChain`** and **select authorization rules** by path, HTTP method, or other criteria.

After this lesson, you will be able to:
1. Describe `ServerWebExchangeMatcher`, `MatchResult`, and reactive results.
2. Use `ServerWebExchangeMatchers.pathMatchers(...)` to distinguish paths and HTTP methods.
3. Choose properly between `securityMatcher(...)` and `authorizeExchange(...).pathMatchers(...)`.
4. Understand the ordering of multiple filter chains and authorization rules.
5. Write a realistic WebFlux configuration and test `GET`, `POST`, `DELETE`, 200/401/403, and CSRF.
6. Identify mistakes such as overly broad matchers, method mismatches, missing fallbacks, or mixing up Servlet stack APIs.

Lesson scope: **reactive/WebFlux** Spring Security and HTTP request matching. Building production user stores, JWT, OAuth2, or detailed business logic are separate topics.

## 2. `ServerWebExchangeMatcher` and `MatchResult`

Core contract:

```java
public interface ServerWebExchangeMatcher {
    Mono<ServerWebExchangeMatcher.MatchResult> matches(
            ServerWebExchange exchange);
}
```

This is a condensed signature for **understanding the API**, not a class file you need to write yourself. Key types:
- `ServerWebExchange` in `org.springframework.web.server`: represents an HTTP exchange currently being processed by WebFlux.
- `Mono<MatchResult>`: the matcher evaluation is expressed reactively with Reactor. It does not return a `boolean` directly.
- `MatchResult.isMatch()`: indicates whether it matched.
- `MatchResult.getVariables()`: retrieves variables extracted from the pattern if the matcher provides them (e.g., `id` in `/api/items/{id}`). Not every matcher provides variables.

There are two factories commonly used in custom matchers:

```java
return ServerWebExchangeMatcher.MatchResult.match();    // Mono<MatchResult>, matched
// or
return ServerWebExchangeMatcher.MatchResult.notMatch(); // Mono<MatchResult>, not matched
```

Do not confuse `ServerWebExchangeMatcher` with Servlet's `org.springframework.security.web.util.matcher.RequestMatcher`. Both deal with matching HTTP requests, but they belong to different stacks, request types, and return styles.

### Role in the pipeline

```text
                    HTTP request
                         |
                         v
          Select SecurityWebFilterChain
          (securityMatcher + @Order)
                         |
                         v
          WebFilter handles authentication
                         |
                         v
         authorizeExchange / matcher rules
          (path + method + order)
                         |
                         v
           permitAll / denyAll / role
                         |
                         v
             Controller / Handler
```

The diagram depicts the **primary decisions**, without guaranteeing that every internal WebFilter runs in the exact order shown across all configurations. Route matching in WebFlux controllers is also a separate phase: a request can pass security and still receive 404 or 405 because no matching handler exists.

## 3. Matching paths with `ServerWebExchangeMatchers`

The `org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers` class provides common factories:

```java
ServerWebExchangeMatcher any =
        ServerWebExchangeMatchers.anyExchange();

ServerWebExchangeMatcher exact =
        ServerWebExchangeMatchers.pathMatchers("/api/items");

ServerWebExchangeMatcher subtree =
        ServerWebExchangeMatchers.pathMatchers("/api/**");

ServerWebExchangeMatcher either =
        ServerWebExchangeMatchers.pathMatchers(
                "/health", "/public/**");
```

These snippets can be placed inside a Java method or class that imports `ServerWebExchangeMatcher` and `ServerWebExchangeMatchers`. A factory taking multiple patterns like `pathMatchers("/health", "/public/**")` matches **if any one of the patterns matches**.

For paths using Spring `PathPattern`:

| Pattern | Example match | Notes |
| --- | --- | --- |
| `/api/items` | `/api/items` | A specific path |
| `/api/items/{id}` | `/api/items/42` | One path segment bound to variable `id` |
| `/api/items/*` | `/api/items/42` | `*` matches characters within a single segment |
| `/api/items/**` | `/api/items/42/details` | `**` matches the rest of the path; used at the end of a pattern |
| `/public/**` | `/public/docs/readme` | A path subtree |
| `/**` | Very many paths | Too broad if placed before specific rules |

`PathPattern` processes paths segment by segment, unlike arbitrary substring matching on a URL. Query strings such as `?page=2` **do not alter** path-matching results when the pattern only inspects the path. Behavior regarding trailing slashes, case sensitivity, encoded paths, and context paths should be verified against your actual Spring Framework configuration rather than guessed by visually inspecting URLs.

When you only need path matching, `ServerWebExchangeMatchers.pathMatchers(...)` is concise. When you want to express a single pattern explicitly and optionally pass a method condition via constructor, you can use `PathPatternParserServerWebExchangeMatcher`:

```java
ServerWebExchangeMatcher oneItem =
        new PathPatternParserServerWebExchangeMatcher(
                "/api/items/{id}");
```

Import: `org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher`.

## 4. Matching both HTTP method and path

One URL can simultaneously support different actions:

- `GET /api/items`: read the list.
- `POST /api/items`: create an item.
- `DELETE /api/items/42`: delete an item.

Security rules per method **differ even when the URL is the same**. The factory supports this overload:

```java
ServerWebExchangeMatcher canRead =
        ServerWebExchangeMatchers.pathMatchers(
                HttpMethod.GET, "/api/items/**");

ServerWebExchangeMatcher canCreate =
        ServerWebExchangeMatchers.pathMatchers(
                HttpMethod.POST, "/api/items");

ServerWebExchangeMatcher canDelete =
        ServerWebExchangeMatchers.pathMatchers(
                HttpMethod.DELETE, "/api/items/{id}");
```

Import `org.springframework.http.HttpMethod`.

The conditions of `pathMatchers(HttpMethod.GET, "/api/items/**")` require **both at once**:
1. The request method is `GET`.
2. The path matches `/api/items/**`.

If the path matches but the method is `POST`, `isMatch()` is false. If the method is `GET` but the path is outside the pattern, the result is also false. The overload `pathMatchers(String... patterns)` does not restrict the HTTP method; similarly, the overload taking `HttpMethod` accepts `null` to mean no method restriction per the API contract, though you should call the methodless overload when that is your intent.

Equivalent constructor example in purpose:

```java
ServerWebExchangeMatcher getOneItem =
        new PathPatternParserServerWebExchangeMatcher(
                "/api/items/{id}", HttpMethod.GET);
```

**Do not confuse matchers with handlers**: a matcher states whether a URL/method belongs to a security rule, whereas `@GetMapping`/`@PostMapping` decides which controller handles the request afterward.

### GET, HEAD, and OPTIONS

`GET`, `HEAD`, and `OPTIONS` are distinct HTTP methods. A rule using only `HttpMethod.GET` does not automatically grant the same permission to `HEAD` or `OPTIONS` requests. WebFlux handlers may support `HEAD` alongside `GET` per framework rules, but security matchers must still be considered separately. CORS preflight commonly uses `OPTIONS`; if an API serves cross-origin browsers, evaluate CORS configuration and appropriate security rules rather than opening the entire API just to fix preflight errors.

## 5. Two places where matchers are used: selecting a chain and authorizing inside a chain

This is the most important distinction.

### 5.1. `http.securityMatcher(matcher)`: selects the **entire chain**

```java
@Bean
@Order(1)
SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
    return http
        .securityMatcher(ServerWebExchangeMatchers.pathMatchers("/api/**"))
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

This is a **configuration excerpt**, requiring the full imports and authentication beans shown in the runnable example below. Only requests matching `/api/**` select this chain. Other requests are evaluated by the next chain in order, if one exists.

`@Order` determines the evaluation order across multiple `SecurityWebFilterChain` beans. Spring Security selects the first chain that matches the request; remaining chains do not stack cumulatively for that request. If none of the chains match, the request may **not be protected by these chains**: check scope and fallback very carefully.

### 5.2. `http.authorizeExchange(...).pathMatchers(...)`: selects a **rule inside the chosen chain**

```java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers(HttpMethod.GET, "/api/items").permitAll()
    .pathMatchers(HttpMethod.POST, "/api/items").hasRole("EDITOR")
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .anyExchange().denyAll())
```

Here, Spring Security evaluates authorization rules **in declaration order** and applies the **first matching rule** within the chosen chain. Put specific rules first, and `anyExchange()` last.

You can also pass a pre-built `ServerWebExchangeMatcher` using `matchers(...)`:

```java
ServerWebExchangeMatcher getOrder =
        ServerWebExchangeMatchers.pathMatchers(
                HttpMethod.GET, "/api/orders/{id}");

// Inside ServerHttpSecurity configuration:
http.authorizeExchange(exchanges -> exchanges
    .matchers(getOrder).hasRole("READER")
    .anyExchange().denyAll());
```

This is an **illustrative snippet inside a configuration method**; `http` must be a `ServerHttpSecurity` instance. Use `matchers(...)` when you already have a reusable or complex matcher. Use `pathMatchers(...)` when you only need simple path/method matching.

### 5.3. Comparison table

| Question | `securityMatcher(...)` | `authorizeExchange(...).pathMatchers(...)` |
| --- | --- | --- |
| Where is it placed? | Directly on `ServerHttpSecurity` | Inside the `authorizeExchange` block |
| What does it select? | The `SecurityWebFilterChain` to apply | The authorization rule within the active chain |
| When is order evaluated? | Across chains, via `@Order` | Across rules, by declaration order |
| If it does not match? | Tries the next chain | Tries the next rule |
| If there is no fallback? | Risk of requests falling outside all chains | Risk of configuration not covering intended requests |
| Recommendation | Narrow chains first, catch-all chain last | Specific rules first, `anyExchange().denyAll()` last |

**Note:** `permitAll()` means no authorization is required for that rule; it does not mean all security filters are removed from the request. Other concerns such as CSRF, headers, and authentication may still run according to the chain configuration.

## 6. Runnable Java 17+ / Spring Boot 3.3 project

This example presents a complete setup with **two filter chains**, path+method matching, sample accounts, and tests. Spring Boot `3.3.5`, Java 17+, and Gradle `8.5` (or a compatible Gradle Wrapper) are chosen for a consistent dependency set. Spring Boot manages Spring Security versions via its BOM.

Project tree:

```text
reactive-matcher-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/dev/example/matcher/
    │   ├── ReactiveMatcherApplication.java
    │   ├── SecurityConfig.java
    │   └── ApiController.java
    └── test/java/dev/example/matcher/
        ├── SecurityMatcherTests.java
        └── MatcherUnitTests.java
```

`settings.gradle`:

```groovy
rootProject.name = 'reactive-matcher-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'dev.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Only use `spring-boot-starter-webflux` for the web runtime in this example. If you add `spring-boot-starter-web`, Boot may select the Servlet stack instead, leading you to misunderstand how `ServerWebExchangeMatcher` works.

`src/main/java/dev/example/matcher/ReactiveMatcherApplication.java`:

```java
package dev.example.matcher;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveMatcherApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveMatcherApplication.class, args);
    }
}
```

### 6.1. Security configuration with two chains

`src/main/java/dev/example/matcher/SecurityConfig.java`:

```java
package dev.example.matcher;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("reader-pass"))
                .roles("READER")
                .build();

        UserDetails editor = User.withUsername("editor")
                .password(encoder.encode("editor-pass"))
                .roles("READER", "EDITOR")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("READER", "EDITOR", "ADMIN")
                .build();

        return new MapReactiveUserDetailsService(reader, editor, admin);
    }

    @Bean
    @Order(1)
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
                .securityMatcher(
                    ServerWebExchangeMatchers.pathMatchers("/api/**"))
                .authorizeExchange(exchanges -> exchanges
                    .pathMatchers(HttpMethod.GET, "/api/items")
                        .permitAll()
                    .pathMatchers(HttpMethod.GET, "/api/items/{id}")
                        .hasRole("READER")
                    .pathMatchers(HttpMethod.POST, "/api/items")
                        .hasRole("EDITOR")
                    .pathMatchers(HttpMethod.DELETE, "/api/items/{id}")
                        .hasRole("ADMIN")
                    .anyExchange().denyAll()
                )
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                    .pathMatchers(HttpMethod.GET, "/health").permitAll()
                    .anyExchange().denyAll()
                )
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }
}
```

Explanation:
- `@Order(1)`: `apiChain` is evaluated first, exclusively for `/api/**`.
- `@Order(2)`: `fallbackChain` declares no `securityMatcher`, so by default it matches all remaining exchanges; this avoids leaving out-of-scope requests unexamined by any chain.
- `GET /api/items` is public; `GET /api/items/{id}` requires `ROLE_READER`; `POST /api/items` requires `ROLE_EDITOR`; `DELETE /api/items/{id}` requires `ROLE_ADMIN`.
- `anyExchange().denyAll()` in each chain blocks requests without an allowing rule, including other HTTP methods on familiar paths.
- `GET /health` is permitted by the fallback chain without making the entire application public.
- `MapReactiveUserDetailsService` provides in-memory accounts; `PasswordEncoder` stores BCrypt hashes. Roles from `.roles("EDITOR")` are stored as the `ROLE_EDITOR` authority.
- `httpBasic(...)` enables HTTP Basic for testing credentials. Form login is disabled so the API example cleanly returns observable 401/403 responses.
- **CSRF remains enabled by default**. We keep it enabled intentionally so the tests clearly distinguish role errors from missing CSRF token errors.

The passwords `reader-pass`, `editor-pass`, and `admin-pass` are hard-coded as **test accounts**, not meant for public deployment.

### 6.2. Controller simulating request handling

`src/main/java/dev/example/matcher/ApiController.java`:

```java
package dev.example.matcher;

import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/health")
    public Mono<String> health() {
        return Mono.just("healthy");
    }

    @GetMapping("/api/items")
    public Mono<String> listItems() {
        return Mono.just("items");
    }

    @GetMapping("/api/items/{id}")
    public Mono<String> getItem(@PathVariable String id) {
        return Mono.just("item:" + id);
    }

    @PostMapping("/api/items")
    public Mono<String> createItem() {
        return Mono.just("created");
    }

    @DeleteMapping("/api/items/{id}")
    public Mono<String> deleteItem(@PathVariable String id) {
        return Mono.just("deleted:" + id);
    }
}
```

The handlers return `Mono` and **do not call `block()` or `subscribe()`**. The example does not actually modify a database; the goal is to verify matcher selection and authorization outcomes.

### 6.3. Table of requests and selected rules

| Request | Chain | Authorization rule | Result when requirements met |
| --- | --- | --- | --- |
| `GET /health` | Fallback | `GET /health -> permitAll` | 200, `healthy` |
| `GET /api/items` | API | `GET /api/items -> permitAll` | 200, `items` |
| `GET /api/items/42` | API | `GET /api/items/{id} -> READER` | 200, `item:42` |
| `POST /api/items` | API | `POST /api/items -> EDITOR` | 200, `created` with valid CSRF |
| `DELETE /api/items/42` | API | `DELETE /api/items/{id} -> ADMIN` | 200, `deleted:42` with valid CSRF |
| `PUT /api/items/42` | API | `anyExchange -> denyAll` | Denied regardless of other permissions |
| `GET /other` | Fallback | `anyExchange -> denyAll` | Denied |

The table describes the configuration when a handler exists. Requests without a handler may receive 404/405 after security checks; CSRF, authentication, HTTP method, or the security entry point also affect the actual status. Therefore, do not deduce every HTTP status from the matcher alone.

## 7. Running the app and testing GET with curl

From the `reactive-matcher-demo` directory:

```bash
gradle bootRun
```

If using the Gradle Wrapper, run `./gradlew bootRun` (Linux/macOS) or `gradlew.bat bootRun` (Windows). Once the server is ready on port 8080, open a second terminal:

```bash
curl -i http://localhost:8080/health
curl -i http://localhost:8080/api/items
curl -i http://localhost:8080/api/items/42
curl -i -u reader:reader-pass http://localhost:8080/api/items/42
curl -i -u reader:wrong http://localhost:8080/api/items/42
curl -i -u editor:editor-pass http://localhost:8080/api/items/42
```

**Expected** results:
1. `/health`: HTTP 200, body `healthy` (fallback chain).
2. `/api/items`: HTTP 200, body `items` (public API GET).
3. `/api/items/42` without credentials: HTTP 401 with HTTP Basic.
4. Same URL with `reader` and valid password: HTTP 200, body `item:42`.
5. Same URL with wrong password: HTTP 401.
6. Same URL with `editor`: HTTP 200 because editor also holds the READER role.

**Do not use a plain curl POST command to draw conclusions about the EDITOR role:** when CSRF is enabled, `curl -u editor:editor-pass -X POST http://localhost:8080/api/items` normally returns 403 due to a missing CSRF token. This does not prove `hasRole("EDITOR")` is wrong. The next section tests POST/DELETE with `WebTestClient` and valid CSRF.

## 8. Integration testing with `WebTestClient` and CSRF

`src/test/java/dev/example/matcher/SecurityMatcherTests.java`:

```java
package dev.example.matcher;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class SecurityMatcherTests {

    @Autowired
    ApplicationContext applicationContext;

    WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(applicationContext)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void healthIsPublicThroughFallbackChain() {
        client.get().uri("/health")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("healthy");
    }

    @Test
    void collectionGetIsPublic() {
        client.get().uri("/api/items")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("items");
    }

    @Test
    void itemGetNeedsAuthentication() {
        client.get().uri("/api/items/42")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void readerCanGetItem() {
        client.get().uri("/api/items/42")
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("item:42");
    }

    @Test
    void readerCannotCreateEvenWithCsrf() {
        client.mutateWith(csrf())
                .post().uri("/api/items")
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void editorCanCreateWithCsrf() {
        client.mutateWith(csrf())
                .post().uri("/api/items")
                .headers(h -> h.setBasicAuth("editor", "editor-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("created");
    }

    @Test
    void editorCannotCreateWithoutCsrf() {
        client.post().uri("/api/items")
                .headers(h -> h.setBasicAuth("editor", "editor-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void editorCannotDeleteEvenWithCsrf() {
        client.mutateWith(csrf())
                .delete().uri("/api/items/42")
                .headers(h -> h.setBasicAuth("editor", "editor-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void adminCanDeleteWithCsrf() {
        client.mutateWith(csrf())
                .delete().uri("/api/items/42")
                .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("deleted:42");
    }

    @Test
    void unlistedApiPathIsDenied() {
        client.get().uri("/api/unknown")
                .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }
}
```

In `setup()`, `springSecurity()` applies Spring Security test support to the client bound to the Spring `ApplicationContext`. `csrf()` supplies a valid CSRF token to simulated POST/DELETE requests; it **does not disable** CSRF in the application. `@SpringBootTest(...MOCK)` tests WebFlux using a mock HTTP exchange without starting a real server on port 8080.

Run:

```bash
gradle test
```

Expected: **10 tests pass** with compatible configuration and dependencies. This is an expectation based on the lesson code, not a claim that tests have already been executed on your system.

Analyzing three easily confused results:
- Reader + valid CSRF but POST gets **403**: wrong *authorization role* (`READER` lacks `EDITOR`).
- Editor + valid CSRF and POST **200**: passed both CSRF and `ROLE_EDITOR`.
- Editor + no CSRF and POST **403**: blocked by CSRF despite having the right role.

For production, CSRF must be evaluated according to how the application authenticates and how browsers automatically attach credentials. Do not disable CSRF simply to make POST return 200; if an API truly uses bearer tokens in headers and has its own threat model, evaluate the CSRF/CORS configuration alongside the authentication architecture.

## 9. Unit testing a matcher independently: right path but wrong method

A matcher can be tested directly without running a controller. This is an appropriate place to use `block()` in a **JUnit test on a test thread**, never inside a WebFlux request handler.

`src/test/java/dev/example/matcher/MatcherUnitTests.java`:

```java
package dev.example.matcher;

import java.util.Objects;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatcher;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class MatcherUnitTests {

    private final ServerWebExchangeMatcher matcher =
            ServerWebExchangeMatchers.pathMatchers(
                    HttpMethod.GET, "/api/items/{id}");

    @Test
    void getMatchingPathSucceedsAndExtractsVariable() {
        MockServerWebExchange exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get("/api/items/42"));

        ServerWebExchangeMatcher.MatchResult result =
                Objects.requireNonNull(matcher.matches(exchange).block());

        assertTrue(result.isMatch());
        assertEquals("42", result.getVariables().get("id"));
    }

    @Test
    void postSamePathDoesNotMatch() {
        MockServerWebExchange exchange = MockServerWebExchange.from(
                MockServerHttpRequest.post("/api/items/42"));

        ServerWebExchangeMatcher.MatchResult result =
                Objects.requireNonNull(matcher.matches(exchange).block());

        assertFalse(result.isMatch());
    }

    @Test
    void getWrongPathDoesNotMatch() {
        MockServerWebExchange exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get("/api/other/42"));

        ServerWebExchangeMatcher.MatchResult result =
                Objects.requireNonNull(matcher.matches(exchange).block());

        assertFalse(result.isMatch());
    }
}
```

Expected **3 tests pass**: one request matches and extracts variable `id=42`, while two requests do not match due to wrong method or path. When running the whole suite with `gradle test` alongside section 8's file, **13 tests are expected to pass**.

If a custom matcher does not populate path variables, `getVariables()` may be empty; in this example the factory creates a path matcher that supports extracting `{id}`.

## 10. Combining multiple matchers and writing custom matchers

When there are multiple conditions, clearly distinguish **OR** and **AND** relationships:

```java
ServerWebExchangeMatcher healthOrDocs =
        ServerWebExchangeMatchers.matchers(
                ServerWebExchangeMatchers.pathMatchers("/health"),
                ServerWebExchangeMatchers.pathMatchers("/docs/**"));
```

The `matchers(...)` factory creates a matcher that **matches if any input matcher matches** (OR). Do not mistake it for AND. For both path and method, the `pathMatchers(HttpMethod.GET, "/docs/**")` overload already provides AND logic between those two conditions.

Spring Security also provides `AndServerWebExchangeMatcher`, `OrServerWebExchangeMatcher`, and `NegatedServerWebExchangeMatcher` to express combined conditions when needed. Only add this complexity when rules are no longer clear using `pathMatchers(...)`.

### Custom matcher for non-path conditions

Illustrative example of a matcher that **only inspects a header** without granting permissions itself:

```java
ServerWebExchangeMatcher version2 = exchange -> {
    String version = exchange.getRequest()
            .getHeaders().getFirst("X-API-Version");
    return "2".equals(version)
            ? ServerWebExchangeMatcher.MatchResult.match()
            : ServerWebExchangeMatcher.MatchResult.notMatch();
};
```

Place inside a class/method that imports `ServerWebExchangeMatcher`. The return value is `Mono<MatchResult>`, non-blocking. This is a condition for **classifying requests**; client-sent headers can be forged, so **never** treat this value as proof of identity or permissions. To grant access, you must still authenticate identity and check appropriate authorities/roles.

As for query parameters like `?mode=preview`, normal path matchers do not inspect them. If you genuinely need to match queries, you can write a custom matcher that reads `exchange.getRequest().getQueryParams()` and returns a `MatchResult`. Likewise, never use client-controlled query strings as a substitute for authentication.

## 11. Ordering, fallbacks, and common vulnerabilities

### 11.1. Broad rule placed before narrow rule

```java
// WRONG in intent: the first rule catches every request under /api,
// causing the /api/admin/** rule behind it not to be evaluated.
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/**").permitAll()
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .anyExchange().denyAll())
```

For `GET /api/admin/report`, the first rule already allows it; Spring Security does not combine the `hasRole("ADMIN")` condition from the later rule.

Fix:

```java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .pathMatchers("/api/public/**").permitAll()
    .anyExchange().denyAll())
```

### 11.2. Broad chain placed before specialized chain

If an `@Order(1)` chain matches all URLs, an `@Order(2)` chain intended only for `/api/**` may **never be selected**. Attach `securityMatcher("/api/**")` to the specialized chain and place it before the fallback. With multiple chains, trace logic in order: **chain selection → authorization inside chosen chain**.

### 11.3. Declaring only an `/api/**` chain and forgetting other URLs

In that case, `/health`, `/admin`, or a new endpoint may sit outside all configured chains. Create a fallback that matches all requests and apply explicit rules, typically `denyAll` for URLs not explicitly designed to be permitted.

### 11.4. Checking only path and forgetting HTTP method

`.pathMatchers("/api/items").permitAll()` opens that path for **every method** within the rule's scope, including `POST` if no other condition matched earlier. When the policy distinguishes reads from writes, specify `HttpMethod.GET`, `HttpMethod.POST`, `HttpMethod.DELETE`, etc. explicitly.

### 11.5. Seeing 403 and assuming the matcher is wrong

403 can also be caused by:
- Authenticated user lacking the required role/authority.
- `anyExchange().denyAll()` being selected.
- Missing/invalid CSRF token on a state-changing request.
- CORS configuration, security exception handler, or custom authorization logic.

Verify the request method, path, selected chain, first matching rule, authentication, CSRF, and handler, in that exact order. Test each condition independently to pinpoint the true cause.

### 11.6. Seeing 404/405 and editing security rules unnecessarily

404/405 can originate from **handler mapping**, such as `POST /api/items/42` having no matching `@PostMapping`. Authorization does not create controllers. If security rejects earlier, you may also see 401/403 instead of 404/405. Test both security rules and actual routes.

### 11.7. Confusing WebFlux with Servlet

Correct component pairs:

| Reactive/WebFlux | Servlet/MVC |
| --- | --- |
| `ServerWebExchangeMatcher` | `RequestMatcher` |
| `SecurityWebFilterChain` | `SecurityFilterChain` |
| `ServerHttpSecurity` | `HttpSecurity` |
| `authorizeExchange` | `authorizeHttpRequests` |
| `ServerWebExchange` | `HttpServletRequest` |

Do not copy Servlet examples using `AntPathRequestMatcher`/`MvcRequestMatcher` directly to replace `ServerWebExchangeMatcher` in WebFlux.

## 12. Self-review checklist when designing HTTP rules

1. List every endpoint, **both path and method**: read/write/delete/admin/health.
2. Choose only as many chains as truly needed. One chain with multiple authorization rules suffices for many small apps; split chains when authentication mechanisms or scopes differ significantly.
3. With multiple chains: place specialized chains first, fallback last. Verify what happens when no chain matches.
4. Within each chain: specific rules first, `anyExchange()` last. Choose `denyAll()` for undeclared requests if an allowlist model is required.
5. Distinguish `permitAll` from bypassing all security filters.
6. Check permissions via `hasRole`/`hasAuthority` on an authenticated identity; never treat client-supplied paths/queries/headers as proof of authorization.
7. Test **200/401/403** statuses, existing/non-existing routes, wrong methods, CSRF, and CORS preflight when present.
8. Do not overlook `HEAD`, `OPTIONS`, path variables, context paths, and trailing slashes.

## 13. Self-check questions

**Question 1.** What return type does `ServerWebExchangeMatcher.matches(...)` have?  
**Answer:** `Mono<ServerWebExchangeMatcher.MatchResult>`, not boolean.

**Question 2.** Do `GET /api/items` and `POST /api/items` match the same rule if `pathMatchers("/api/items")` is used?  
**Answer:** Yes, they can both match because this overload does not restrict the HTTP method. To separate permissions, use `pathMatchers(HttpMethod.GET, ...)` and `pathMatchers(HttpMethod.POST, ...)`.

**Question 3.** How does `securityMatcher(...)` differ from `authorizeExchange().pathMatchers(...)`?  
**Answer:** The first selects the **filter chain** for the request; the second selects the **authorization rule** inside the chosen chain.

**Question 4.** If two rules match one request, which rule applies?  
**Answer:** The first rule according to configuration order in the chain; rules are not accumulated.

**Question 5.** If two chains match one request, which chain is used?  
**Answer:** The first matching chain according to `@Order`.

**Question 6.** Why does a `POST` with the proper EDITOR role still return 403?  
**Answer:** It may be missing a CSRF token. Distinguish CSRF from authorization.

**Question 7.** Does the query string in `GET /api/items/42?view=full` automatically prevent `/api/items/{id}` from matching?  
**Answer:** No; query strings are not part of the path compared by standard path matchers.

**Question 8.** Does `ServerWebExchangeMatchers.matchers(a, b)` mean AND or OR?  
**Answer:** OR; it matches if any one of the matchers matches.

### Suggested exercises

1. Create `GET /api/reports/{id}` restricted to role READER and `POST /api/reports` restricted to role EDITOR. Keep `/api/reports/public` publicly readable if required by the product.
2. Write the rules in an order that avoids accidentally opening `/api/reports/{id}`. Explain what happens to `GET /api/reports/public` when a public matcher is placed before vs. after the `/api/reports/{id}` matcher.
3. Add tests for `GET`/`POST`, successful login, missing role, and missing CSRF. Include an `OPTIONS` test if the app serves cross-origin browsers.
4. Move `.pathMatchers("/api/**").permitAll()` to the top; re-run the tests and identify which security requirements break. Then restore the correct policy.
5. Try a custom `ServerWebExchangeMatcher` checking `X-API-Version: 2` solely to **route** a rule, while keeping a separate role check. Explain why a client header is insufficient as authorization proof.

## 14. Official documentation

- [Spring Security — WebFlux Security, multiple chains](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html).
- [Spring Security — Authorize ServerHttpRequest](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html).
- [Spring Security — ServerWebExchangeMatcher API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/util/matcher/ServerWebExchangeMatcher.html).
- [Spring Security — ServerWebExchangeMatchers API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/util/matcher/ServerWebExchangeMatchers.html).
- [Spring Security — PathPatternParserServerWebExchangeMatcher API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/util/matcher/PathPatternParserServerWebExchangeMatcher.html).
- [Spring Security — Testing with CSRF in WebTestClient](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html).
- [Spring Framework — PathPattern](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-requestmapping.html).

**Remember:** `ServerWebExchangeMatcher` decides *whether a request matches a condition*; `securityMatcher` selects the *chain*; `authorizeExchange` selects the *rule*; both path **and** method must be expressed fully, and ordering, CSRF, and fallback must be tested to avoid accidentally exposing endpoints.