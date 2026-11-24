# Building a WebFlux REST API with HTTP Basic and Role-Based Access

## 1. Lab Requirements and Final Outcome

This integrated lab builds a REST API with **Spring Boot WebFlux** and secures the API with **Spring Security Reactive**. The two security requirements are identity authentication using **HTTP Basic** and **Role-Based Access Control (RBAC)** authorization per HTTP method and path. Upon completion, learners can run a Java 17+ application, send requests with an HTTP client, understand why a request is allowed or denied, and test with `WebTestClient`.

The lab simulates an article management API `/api/articles`:

| Method and endpoint | Anonymous | READER | EDITOR | ADMIN |
| --- | --- | --- | --- | --- |
| `GET /api/public/ping` | 200 | 200 | 200 | 200 |
| `GET /api/articles` | 401 | 200 | 200 | 200 |
| `GET /api/articles/{id}` | 401 | 200/404 | 200/404 | 200/404 |
| `POST /api/articles` | 401 | 403 | 201 | 201 |
| `DELETE /api/articles/{id}` | 401 | 403 | 403 | 204/404 |
| Undeclared method/endpoint | Denied | Denied | Denied | Denied |

The three accounts have usernames `reader`, `editor`, `admin` and corresponding authorities `ROLE_READER`, `ROLE_EDITOR`, `ROLE_ADMIN`. Passwords are read from environment variables when running the lab rather than hardcoded as real values in the repository.

Demonstration scope: Java 17+, Spring Boot 3.3.x, Spring Security 6.x, Reactor, JUnit 5. The lab uses `ConcurrentHashMap` instead of a database to focus on authentication/authorization; this is temporary storage and data is lost on restart. In production, replace it with reactive persistence, dedicated user/secret management, and TLS protection.

## 2. Background Knowledge: HTTP Basic, Roles, and the Reactive Security Chain

HTTP Basic uses a header in the form:

~~~http
GET /api/articles HTTP/1.1
Host: localhost:8080
Authorization: Basic <base64(username:password)>
~~~

The string `<base64(username:password)>` is **illustrative notation**. Base64 **does not encrypt secrets**; the server decodes this representation to verify the username/password, so **HTTPS/TLS** must be used over the network. In browsers, HTTP Basic credentials can be cached and resent automatically; never confuse an HTTP Basic API with OAuth2 Bearer tokens, JWTs, or session-based login mechanisms.

Spring Security WebFlux flow:

~~~text
HTTP request
  -> WebFilterChainProxy / SecurityWebFilterChain
  -> HTTP Basic filter reads Authorization
  -> ReactiveAuthenticationManager
  -> MapReactiveUserDetailsService loads UserDetails
  -> PasswordEncoder matches password against hash
  -> Authentication containing principal + granted authorities
  -> authorizeExchange matches method/path and role
  -> controller Mono/Flux if permitted
  -> WebFlux subscribes to Publisher and writes HTTP response
~~~

**Authentication** answers “who is calling?”. Missing or invalid credentials on a protected endpoint typically return **401 Unauthorized** with `WWW-Authenticate: Basic...`. **Authorization** answers “is the authenticated user allowed to perform this operation?”. Insufficient permissions typically return **403 Forbidden**. When security checks pass but the resource does not exist, the controller returns **404 Not Found**. An invalid POST body returns **400 Bad Request**. Do not collapse these cases into a single error type.

In Spring Security, `User.withUsername(...).roles("READER")` generates the `ROLE_READER` authority. Configuring `hasRole("READER")` checks that authority; do not pass the string `ROLE_READER` into `hasRole`. For `hasAuthority("SCOPE_read")` or custom authorities, the mechanism is different: pick one model and apply it consistently.

In WebFlux, use `ServerHttpSecurity` and `SecurityWebFilterChain`; **do not use** Servlet `HttpSecurity`, `SecurityFilterChain`, blocking `UserDetailsService`, or `MockMvc` to implement a reactive lab. `SecurityContext` in a reactive flow is bound to the Reactor Context.

## 3. Preparing the Gradle Project, Package, and Configuration

Project structure:

~~~text
webflux-basic-rbac/
  settings.gradle
  build.gradle
  gradlew / gradlew.bat
  src/main/java/example/webfluxbasic/
    BasicRbacApplication.java
    ApiSecurityConfig.java
    ArticleController.java
    PublicController.java
  src/main/resources/application.yml
  src/test/java/example/webfluxbasic/
    BasicRbacIntegrationTest.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'webflux-basic-rbac'
~~~

File `build.gradle` for a standalone application:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
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
~~~

If using a Gradle repository that already has conventions/plugins managing dependencies, declare only the missing dependencies; do not overwrite the entire build configuration of an existing module. With Spring Boot 3.3.x, Java 17 is the compatible baseline; the plugin versions above illustrate a specific 3.3 release.

File `src/main/java/example/webfluxbasic/BasicRbacApplication.java`:

~~~java
package example.webfluxbasic;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BasicRbacApplication {

    public static void main(String[] args) {
        SpringApplication.run(BasicRbacApplication.class, args);
    }
}
~~~

File `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

demo:
  users:
    reader-password: ${DEMO_READER_PASSWORD}
    editor-password: ${DEMO_EDITOR_PASSWORD}
    admin-password: ${DEMO_ADMIN_PASSWORD}
~~~

The `DEMO_*` variables are for the lab only and must be set when starting the server. Do not set public default “passwords” for production. When running the tests in section 6, the `demo.users.*` properties are overridden by the test, so you do not need to export these environment variables to run the tests.

## 4. Configuring SecurityWebFilterChain and Reactive Users

File `src/main/java/example/webfluxbasic/ApiSecurityConfig.java`:

~~~java
package example.webfluxbasic;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

@Configuration
@EnableWebFluxSecurity
public class ApiSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(
            PasswordEncoder encoder,
            @Value("${demo.users.reader-password}") String readerPassword,
            @Value("${demo.users.editor-password}") String editorPassword,
            @Value("${demo.users.admin-password}") String adminPassword) {

        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode(readerPassword))
            .roles("READER")
            .build();

        UserDetails editor = User.withUsername("editor")
            .password(encoder.encode(editorPassword))
            .roles("EDITOR")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode(adminPassword))
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(reader, editor, admin);
    }

    @Bean
    ReactiveAuthenticationManager authenticationManager(
            MapReactiveUserDetailsService users, PasswordEncoder encoder) {

        UserDetailsRepositoryReactiveAuthenticationManager manager =
            new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        return manager;
    }

    @Bean
    SecurityWebFilterChain apiSecurity(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager authenticationManager) {

        return http
            .authenticationManager(authenticationManager)
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .logout(ServerHttpSecurity.LogoutSpec::disable)
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .authorizeExchange(ex -> ex
                .pathMatchers(HttpMethod.GET, "/api/public/ping")
                    .permitAll()
                .pathMatchers(HttpMethod.GET,
                    "/api/articles", "/api/articles/**")
                    .hasAnyRole("READER", "EDITOR", "ADMIN")
                .pathMatchers(HttpMethod.POST, "/api/articles")
                    .hasAnyRole("EDITOR", "ADMIN")
                .pathMatchers(HttpMethod.DELETE, "/api/articles/**")
                    .hasRole("ADMIN")
                .anyExchange().denyAll())
            .build();
    }
}
~~~

Explanation:

- `PasswordEncoderFactories.createDelegatingPasswordEncoder()` uses BCrypt by default and adds the `{bcrypt}` prefix when generating a hash. Passwords are never compared in plaintext; `ReactiveAuthenticationManager` uses the encoder to verify them.
- `MapReactiveUserDetailsService` is the reactive user source in this lab, taking three `UserDetails` instances assigned roles via `.roles(...)`. There is no implicit “role inheritance”: admin can perform GET and POST because the matchers explicitly allow the ADMIN role, not because it automatically inherits READER/EDITOR.
- `httpBasic(...)` enables Basic header authentication; form login/logout are disabled for the API by default. There is no need to write a custom `WebFilter` to parse `Authorization`.
- `NoOpServerSecurityContextRepository` does not persist the `SecurityContext` across requests. Basic credentials must still be sent in subsequent requests. This configuration **does not prove** that the entire application will never use `WebSession` from other components.
- The `pathMatchers(HttpMethod,...)` rules constrain both the HTTP verb and the URL. Public rules are stated explicitly; `anyExchange().denyAll()` blocks every method/route not granted. As the API grows, update the permission matrix and tests accordingly.
- `csrf(...disable)` is only for **labs using command-line/non-browser clients**. With browsers, Basic credentials can be stored and sent automatically, so **never disable CSRF by default solely because an API does not use cookies**. Systems serving browsers must evaluate CSRF, Origin, and appropriate filter chain configurations.
- In real environments, Basic auth is kept over TLS and access logs must not record credentials. Passwords created at startup are for demo purposes; production account management requires a secure authentication store, rotation, and auditing.

## 5. Reactive REST API: Controllers and Sample Data

File `src/main/java/example/webfluxbasic/ArticleController.java`:

~~~java
package example.webfluxbasic;

import java.net.URI;
import java.util.Comparator;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/articles")
public class ArticleController {

    private final AtomicLong sequence = new AtomicLong(1);
    private final Map<Long, Article> articles = new ConcurrentHashMap<>();

    public ArticleController() {
        articles.put(1L, new Article(1L, "First article"));
    }

    @GetMapping
    public Flux<Article> all() {
        return Flux.defer(() -> Flux.fromIterable(articles.values())
            .sort(Comparator.comparingLong(Article::id)));
    }

    @GetMapping("/{id}")
    public Mono<Article> one(@PathVariable long id) {
        return Mono.defer(() -> Mono.justOrEmpty(articles.get(id)))
            .switchIfEmpty(Mono.error(new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Article not found")));
    }

    @PostMapping
    public Mono<ResponseEntity<Article>> create(
            @RequestBody Mono<ArticleInput> body) {

        return body.flatMap(input -> Mono.defer(() -> {
            if (input.title() == null || input.title().isBlank()) {
                return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "title must not be blank"));
            }

            long id = sequence.incrementAndGet();
            Article article = new Article(id, input.title().trim());
            articles.put(id, article);

            return Mono.just(ResponseEntity
                .created(URI.create("/api/articles/" + id))
                .body(article));
        }));
    }

    @DeleteMapping("/{id}")
    public Mono<ResponseEntity<Void>> delete(@PathVariable long id) {
        return Mono.fromSupplier(() -> {
            ResponseEntity<Void> response =
                articles.remove(id) == null
                    ? ResponseEntity.notFound().build()
                    : ResponseEntity.noContent().build();
            return response;
        });
    }

    public record Article(long id, String title) { }

    public record ArticleInput(String title) { }
}
~~~

The example seeds initial data with ID 1 and title `First article`. `GET /api/articles` returns a JSON array; `GET /api/articles/1` returns the object or 404 if it has been deleted. `POST` validates that `title` is non-null/non-blank, generates a new ID, and returns `201 Created` with `Location: /api/articles/{id}`; DELETE returns 204 when deleted and 404 when the ID does not exist.

`Mono.defer` and `Mono.fromSupplier` ensure read/write operations happen at subscription time instead of executing eagerly before the Publisher is consumed. `ConcurrentHashMap` is used because multiple WebFlux requests can execute concurrently; do not assume multi-step business data updates are transaction-safe solely because the Map is thread-safe. With a real database, choose R2DBC or an appropriate reactive driver; avoid JDBC and calling `block()` directly on the event loop.

File `src/main/java/example/webfluxbasic/PublicController.java`:

~~~java
package example.webfluxbasic;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class PublicController {

    @GetMapping("/api/public/ping")
    public Mono<Map<String, String>> ping() {
        return Mono.just(Map.of("status", "ok"));
    }
}
~~~

Do not add `@PermitAll` or extra authorization annotations just to “bypass” `SecurityWebFilterChain`; the public rule is already expressed at `GET /api/public/ping`. Every sensitive endpoint should be tested with both valid requests and requests missing the required role.

## 6. End-to-End Testing with WebTestClient

Use `@SpringBootTest(webEnvironment=RANDOM_PORT)` and `@AutoConfigureWebTestClient` to boot the WebFlux application with the real security chain and send Basic credentials through the HTTP test client. Using `mockUser()` or `mockJwt()` only tests mocked authorization and **does not verify the HTTP Basic username/password step**; here we must send `setBasicAuth` to exercise `ReactiveAuthenticationManager`.

File `src/test/java/example/webfluxbasic/BasicRbacIntegrationTest.java`:

~~~java
package example.webfluxbasic;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "demo.users.reader-password=reader-test-pass",
        "demo.users.editor-password=editor-test-pass",
        "demo.users.admin-password=admin-test-pass"
    })
@AutoConfigureWebTestClient
class BasicRbacIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicRouteIsAccessibleWithoutCredentials() {
        client.get().uri("/api/public/ping").exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.status").isEqualTo("ok");
    }

    @Test
    void protectedRouteWithoutCredentialsReturns401() {
        client.get().uri("/api/articles").exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().exists(HttpHeaders.WWW_AUTHENTICATE);
    }

    @Test
    void incorrectPasswordReturns401() {
        client.get().uri("/api/articles")
            .headers(h -> h.setBasicAuth("reader", "incorrect"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void readerCanReadSeedArticle() {
        client.get().uri("/api/articles/1")
            .headers(h -> h.setBasicAuth("reader", "reader-test-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.title").isEqualTo("First article");
    }

    @Test
    void readerCannotCreate() {
        client.post().uri("/api/articles")
            .headers(h -> h.setBasicAuth("reader", "reader-test-pass"))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new ArticleController.ArticleInput("Forbidden"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void editorCannotDelete() {
        client.delete().uri("/api/articles/1")
            .headers(h -> h.setBasicAuth("editor", "editor-test-pass"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void editorCreatesAndAdminDeletes() {
        ArticleController.Article article = client.post()
            .uri("/api/articles")
            .headers(h -> h.setBasicAuth("editor", "editor-test-pass"))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new ArticleController.ArticleInput("Temporary"))
            .exchange()
            .expectStatus().isCreated()
            .expectHeader().exists(HttpHeaders.LOCATION)
            .expectBody(ArticleController.Article.class)
            .returnResult()
            .getResponseBody();

        assertNotNull(article);

        client.delete().uri("/api/articles/" + article.id())
            .headers(h -> h.setBasicAuth("admin", "admin-test-pass"))
            .exchange()
            .expectStatus().isNoContent();
    }

    @Test
    void unknownMethodIsDeniedEvenForAdmin() {
        client.put().uri("/api/articles/1")
            .headers(h -> h.setBasicAuth("admin", "admin-test-pass"))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new ArticleController.ArticleInput("Updated"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void authenticatedReaderGets404ForMissingRecord() {
        client.get().uri("/api/articles/999999")
            .headers(h -> h.setBasicAuth("reader", "reader-test-pass"))
            .exchange()
            .expectStatus().isNotFound();
    }
}
~~~

The test deletes only the record **created by the test itself**, never deleting the seed record ID 1. This prevents tests from depending on execution order. The test suite covers public 200, anonymous/wrong password 401, reader/editor missing role 403, editor create 201 and admin delete 204, missing ID 404, and ungranted method 403. You can also add a test where POST with a blank title receives 400 to prove validation runs after authorization.

In real REST APIs, 401 can include a `WWW-Authenticate` challenge, 403 means authenticated but lacking permission, and 404 means the record is missing after GET authorization succeeds. When a test fails, read the exact request and check whether `SecurityWebFilterChain` was actually initialized and applied the right matchers; do not simply weaken the assertions to make the test pass.

## 7. Running the Lab and Verifying with curl

You can run the tests using the Gradle Wrapper:

~~~text
Linux/macOS: ./gradlew test
Windows:     .\gradlew.bat test
~~~

To run the actual application on localhost, set the passwords in your terminal and then run `bootRun`. For example, in **PowerShell**:

~~~powershell
$env:DEMO_READER_PASSWORD = 'reader-local-pass'
$env:DEMO_EDITOR_PASSWORD = 'editor-local-pass'
$env:DEMO_ADMIN_PASSWORD = 'admin-local-pass'
.\gradlew.bat bootRun
~~~

Open another terminal, set those environment variables again if you want to reference them in `curl.exe` commands, and send sequentially:

~~~powershell
curl.exe -i http://localhost:8080/api/public/ping
curl.exe -i http://localhost:8080/api/articles
curl.exe -i -u "reader:$env:DEMO_READER_PASSWORD" http://localhost:8080/api/articles
curl.exe -i -u "editor:$env:DEMO_EDITOR_PASSWORD" -X DELETE http://localhost:8080/api/articles/1
~~~

Expected status codes in order: `200`, `401`, `200`, `403`. To test POST in PowerShell, create a local `article.json` file containing JSON:

~~~json
{"title":"Secured WebFlux"}
~~~

Then run:

~~~powershell
curl.exe -i -u "editor:$env:DEMO_EDITOR_PASSWORD" -H "Content-Type: application/json" --data-binary "@article.json" http://localhost:8080/api/articles
~~~

Expected result: `201 Created`, with a `Location` header containing the new ID and a JSON body with `id` and `title`. Using the admin account to call `DELETE` with the **ID just returned** will return `204` if the record still exists. Do not hardcode the ID after sending multiple POSTs. When using `curl` in PowerShell 5.1, invoke `curl.exe` to avoid the `Invoke-WebRequest` alias.

The passwords above are **placeholder values for lab use**. Do not run HTTP Basic over a real network without TLS. Do not store real credentials in command scripts, terminal history, source code, URL queries, or logs; production systems require managed credential provisioning and rotation.

## 8. Explaining Security Behavior and Common Pitfalls

**Method-level authorization**: Security matchers distinguish `GET /api/articles/1` from `DELETE /api/articles/1`; sharing a URL does not imply sharing permissions. `hasAnyRole("READER", "EDITOR", "ADMIN")` is the allowlist for GET, `hasAnyRole("EDITOR", "ADMIN")` for POST, and `hasRole("ADMIN")` for DELETE. `ROLE_*` is attached via `User.roles`, so role names in matchers omit the prefix.

**Deny by default**: `anyExchange().denyAll()` at the end ensures unregistered methods are blocked. If you add `PUT`, you must declare an explicit matcher and add negative tests for reader. Never place an `/api/**.permitAll()` matcher before protection rules or configure an overly broad chain that accidentally skips checks.

**Password hashing**: Never use `{noop}` for real passwords. `PasswordEncoderFactories.createDelegatingPasswordEncoder()` produces `{bcrypt}...` hashes; `UserDetailsRepositoryReactiveAuthenticationManager` is configured with the matching encoder. If every password returns 401, check for a missing prefix, password configuration, username, encoder mismatch, or stray whitespace in environment variables.

**Unencrypted HTTP Basic**: Base64 can be read when traffic is intercepted over a non-TLS connection. A browser can also retain Basic credentials and attach them automatically, so **disabling CSRF is not automatically safe**. For APIs serving browsers alongside sessions/cookies or browser Basic auth, you must re-evaluate CSRF, CORS, Origin, and the corresponding chains. CORS is not authentication/authorization and does not replace CSRF.

**Do not block the event loop**: `Mono` and `Flux` do not automatically make JDBC or blocking APIs non-blocking. Avoid `block()`, `Thread.sleep()`, and blocking file I/O inside WebFlux handlers. With a real DB, prefer R2DBC/reactive drivers or isolate blocking workloads onto an appropriate scheduler while managing resources and latency.

**Choose the right security stack**: If both `spring-boot-starter-web` and `spring-boot-starter-webflux` are added, Spring Boot may select MVC depending on configuration; this lab requires WebFlux only. If the application has multiple `SecurityWebFilterChain` beans, check `@Order` and `securityMatcher` to verify requests hit the intended chain.

**Role policy is not object-level authorization**: Admin in this lab can delete any article. When tenant/ownership rules exist, add service-layer checks for the specific data and owner rather than relying solely on routes. Services behind a gateway must also protect their own trust boundary.

**In-memory data and races**: `ConcurrentHashMap` is for demo purposes only, is not durable, and is not shared across instances. `AtomicLong` generates IDs in-process and does not replace database transactions. Real tests should verify concurrency, permission boundaries, post-error responses, and data-store integration in subsequent extensions.

## 9. Acceptance Matrix and Extension Exercises

| Test case | Caller | Request | Expected |
| --- | --- | --- | --- |
| Public ping | Anonymous | GET `/api/public/ping` | 200 |
| Missing Basic | Anonymous | GET `/api/articles` | 401 |
| Wrong password | reader / invalid password | GET `/api/articles` | 401 |
| Read authorized | reader | GET `/api/articles/1` | 200 |
| Insufficient create role | reader | POST `/api/articles` | 403, no record added |
| Insufficient delete role | editor | DELETE `/api/articles/1` | 403, no record deleted |
| Create authorized | editor | POST valid body | 201, Location |
| Delete authorized | admin | DELETE newly created id | 204 |
| Ungranted method | admin | PUT `/api/articles/1` | 403 |
| Missing resource | reader | GET `/api/articles/999999` | 404 |
| Blank title body | editor | POST body `{"title":""}` | 400 |

Extend on your own through valuable learning steps:

1. Implement `PATCH /api/articles/{id}` only for editor/admin; add tests for reader 403, editor success, and admin success.
2. Add `ROLE_AUDITOR` with read-only access and verify it is not granted POST/DELETE permissions.
3. Enforce owner/tenant authorization: editors can only modify their own articles, while admins have management access; do not trust an `ownerId` sent in the caller's request body.
4. Switch the user source to a `ReactiveUserDetailsService` backed by a non-blocking data store; store pre-generated password hashes and do not keep plaintext passwords.
5. Enable reactive method security for sensitive operations and test both HTTP protection and service-layer protection. Do not use `@PreAuthorize` as a replacement for all object-level permission checks.
6. Separate configurations for API and UI if browser sessions are used, evaluate CSRF, and test the difference between cookie/browser and Basic API flows.
7. Add minimal auditing including username, action, status, and request ID without logging the Authorization header or password. Add rate limiting and brute-force protection according to deployment requirements.

## 10. Knowledge and Secure Implementation Checklist

- [ ] WebFlux uses `ServerHttpSecurity` and `SecurityWebFilterChain`, without mixing Servlet security APIs.
- [ ] HTTP Basic works via `setBasicAuth` in `WebTestClient`, verifying 401 on missing/wrong passwords.
- [ ] Passwords are hashed, usernames are loaded via `MapReactiveUserDetailsService`, and verified by `ReactiveAuthenticationManager`.
- [ ] Roles `READER`, `EDITOR`, `ADMIN` map explicitly to `ROLE_*` authorities.
- [ ] GET/POST/DELETE routes enforce the right roles, and public routes expose only approved endpoints.
- [ ] `anyExchange().denyAll()` acts as the default-deny fallback.
- [ ] Both positive tests (200/201/204) and negative tests (401/403) exist, plus 400/404 per the API contract.
- [ ] Reactive controllers return `Mono`/`Flux` and do not call blocking APIs on the event loop.
- [ ] In-memory demo data is clearly distinguished from real transactional persistence.
- [ ] CSRF is disabled only in labs/APIs whose usage conditions have been evaluated, without assuming stateless Basic is always safe from CSRF.
- [ ] HTTP Basic is never sent over unencrypted networks; real secrets do not appear in Git/logs/production test samples.
- [ ] Owner/tenant permissions are checked at the business layer whenever data objects exist.

**Key takeaway:** Spring Security WebFlux handles authentication with HTTP Basic and authorization with `authorizeExchange` before routing requests to controllers. A REST API is only secure when **each method and resource has a clear policy**, under-privileged users are blocked, passwords are handled safely, and every decision is proven by both positive and negative tests.

## References

- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [Spring Security — CSRF in WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html)
- [Spring Boot — WebFlux Testing](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/autoconfigure/web/reactive/WebFluxTest.html)
