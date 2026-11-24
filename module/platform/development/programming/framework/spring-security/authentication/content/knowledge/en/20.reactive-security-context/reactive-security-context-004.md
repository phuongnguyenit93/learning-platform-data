# NoOpServerSecurityContextRepository: Not Persisting SecurityContext Across Requests in Spring Security WebFlux

## 1. Goal and Context

In a **reactive Spring Security (Spring WebFlux)** application, a request may authenticate successfully, yet the application does not necessarily have to write the authentication result into a session for reuse on a subsequent request. `NoOpServerSecurityContextRepository` is the choice for a policy of **not saving/not restoring `SecurityContext` between HTTP requests**.

After this lesson, you can:
- Explain the responsibility of `ServerSecurityContextRepository` and its relationship with `ReactiveSecurityContextHolder`.
- Understand the `load`/`save` behavior of `NoOpServerSecurityContextRepository`.
- Configure WebFlux HTTP Basic so that each request supplies its own credentials without reusing context from a previous request.
- Verify with real requests and distinguish not persisting context from the absence of all types of sessions/cookies.

**Scope:** reactive APIs using `ServerHttpSecurity`, `SecurityWebFilterChain`, and `ServerWebExchange`. Servlet APIs such as `HttpSecurity`, `SecurityContextRepository` (without the `Server` prefix), or `SessionCreationPolicy.STATELESS` are a different configuration branch.

## 2. Where Does SecurityContext Live in a Reactive Flow?

- `Authentication` describes the authenticated identity, principal, and authorities; `SecurityContext` holds the current `Authentication`.
- `ReactiveSecurityContextHolder` supplies context to Reactor sequences (`Mono`/`Flux`), typically accessed while processing **the current request**. You should not assume this context is a `ThreadLocal` variable pinned to a single thread: a reactive pipeline can switch threads.
- `ServerSecurityContextRepository` is the strategy for **saving and restoring** `SecurityContext` across HTTP requests. Two key methods:
  - `Mono<SecurityContext> load(ServerWebExchange exchange)`: looks up saved context for the request; `Mono.empty()` means none was found.
  - `Mono<Void> save(ServerWebExchange exchange, SecurityContext context)`: persists the context and emits a completion signal.
- `ReactorContextWebFilter` uses the repository to restore context into the processing flow. An authentication filter such as `AuthenticationWebFilter` can create a new `Authentication` from the current request's own credentials and place it into the reactive context, even when no prior context was loaded.

**Two concepts must be kept separate:** context existing **within the current request** and context being **written for reuse in the next request**. NoOp eliminates the second behavior; it does not prevent an authentication filter from creating context within the current request.

## 3. What Does NoOp Actually Do?

Class `org.springframework.security.web.server.context.NoOpServerSecurityContextRepository` implements `ServerSecurityContextRepository` in a "do nothing" manner:

| Operation | Behavior | Meaning |
| --- | --- | --- |
| `load(exchange)` | Returns `Mono.empty()` | No previous `SecurityContext` is restored from the repository. |
| `save(exchange, context)` | Returns a `Mono<Void>` that completes without storing anything | Successful authentication is not recorded by the repository for later reuse. |
| `getInstance()` | Returns a shared instance | Reuse instead of creating a new repository per request. |

This is suitable when every request carries authentication credentials such as `Authorization: Basic ...` or `Authorization: Bearer ...`. A second request succeeding because it **sends credentials/tokens again** is different from succeeding because it **was restored from a session**.

Illustrative flow:

~~~text
Request #1: Authorization: Basic ...
    -> repository.load(): empty
    -> HTTP Basic authenticates request #1's username/password
    -> Authentication is present in request #1's Reactor Context
    -> endpoint is allowed to process
    -> repository.save(): persists nothing

Request #2: without Authorization
    -> repository.load(): empty
    -> no authenticated identity to reuse
    -> endpoint requiring authenticated => HTTP 401
~~~

**Exact boundary:** NoOp governs only where `SecurityContext` is saved/loaded at the points configured to use this repository. It does not automatically disable `WebSession` mechanisms for other components, does not delete all cookies, does not disable CSRF, does not change authorization policies, does not validate tokens, and does not automatically revoke issued tokens.

## 4. Complete Example: WebFlux + HTTP Basic Without Saving Context

The example uses **Java 17+, Spring Boot 3.3.12 / Spring Security 6.x**, a pure WebFlux application, one test user, and a `GET /me` endpoint. To run the example standalone, create a Gradle project with the following files; if integrating into an existing build module, only the equivalent dependencies are needed.

**`build.gradle`**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.12'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

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
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**`src/main/java/demo/StatelessWebfluxApplication.java`**

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StatelessWebfluxApplication {
    public static void main(String[] args) {
        SpringApplication.run(StatelessWebfluxApplication.class, args);
    }
}
~~~

**`src/main/java/demo/SecurityConfig.java`**

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    public SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        var noOp = NoOpServerSecurityContextRepository.getInstance();

        return http
                // Specifies where ReactorContextWebFilter looks up prior context.
                .securityContextRepository(noOp)
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/me").authenticated()
                        .anyExchange().permitAll())
                // Also specifies the repository for the HTTP Basic filter when saving.
                .httpBasic(basic -> basic.securityContextRepository(noOp))
                .formLogin(form -> form.disable())
                .build();
    }

    @Bean
    public ReactiveUserDetailsService users() {
        UserDetails reader = User.withUsername("reader")
                .password("{noop}demo123")
                .roles("READER")
                .build();
        return new MapReactiveUserDetailsService(reader);
    }
}
~~~

**`src/main/java/demo/MeController.java`**

~~~java
package demo;

import org.springframework.http.MediaType;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class MeController {

    @GetMapping(value = "/me", produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(authentication -> "Hello, " + authentication.getName());
    }
}
~~~

**Why does the configuration use `noOp` in two places?** `ServerHttpSecurity.securityContextRepository(noOp)` configures the repository for `ReactorContextWebFilter` when **reading context**, whereas `httpBasic(basic -> basic.securityContextRepository(noOp))` specifies where the HTTP Basic filter **saves the authentication result**. These two places are not automatically linked across all configurations; setting both explicitly makes the example's objective easy to verify. HTTP Basic also defaults to NoOp for saving in corresponding Spring Security versions, but writing it explicitly clarifies intent.

`formLogin` is disabled because the example uses credentials on every HTTP request rather than a session-based browser login flow. `{noop}` in the password is for demo purposes only: this encoder marker accepts **unhashed** passwords and must never be used for real accounts. Real applications use an appropriate password encoder (such as BCrypt), a secure user store, and HTTPS connections.

### Running and Observing

With the Gradle Wrapper created for the project, run:

~~~bash
./gradlew bootRun
~~~

On Windows use `gradlew.bat bootRun`. Do not include the servlet/MVC starter alongside this pure WebFlux example.

Open another terminal and invoke three **independent** requests:

~~~bash
# 1. Without credentials: the endpoint is protected.
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/me

# 2. Supply Basic credentials on this request itself.
curl -s -u reader:demo123 -w '\n' http://localhost:8080/me

# 3. Omit Authorization: request #2 is not inherited.
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/me
~~~

Corresponding outputs (one line per command):

~~~text
401
Hello, reader
401
~~~

Request #2 succeeds because Spring Security authenticates the Basic header and places `Authentication` into **the same request's** Reactor Context; `MeController` reads the identity via `ReactiveSecurityContextHolder`. Request #3 has no header and the repository cannot restore any context, so it returns 401. If you invoke request #2 twice, both may return 200: each request sends credentials again, **which does not indicate session persistence**.

## 5. Automated Testing of Non-Persisted Authentication Behavior

Add the file **`src/test/java/demo/NoOpSecurityContextTest.java`**; uses the declared `spring-boot-starter-test` dependency:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class NoOpSecurityContextTest {

    @Autowired
    WebTestClient client;

    @Test
    void previousAuthenticationIsNotReused() {
        client.get()
                .uri("/me")
                .headers(headers -> headers.setBasicAuth("reader", "demo123"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("Hello, reader");

        client.get()
                .uri("/me")
                .exchange()
                .expectStatus().isUnauthorized();
    }
}
~~~

Run `./gradlew test` (or `gradlew.bat test`). The test verifies immediate access when the Basic header is present and that the subsequent request does not automatically inherit authentication. It does not prove "the application never creates any session/cookie"; verifying a broader claim requires inspecting individual components and behavior.

## 6. When Should You Use It and When Should You Avoid It?

| Scenario | Assessment |
| --- | --- |
| WebFlux API authenticating each request independently with HTTP Basic (over HTTPS) | Appropriate; the request carries credentials every time. |
| Resource Server validating Bearer/JWT for an API | Usually appropriate in principle for not persisting `SecurityContext`; token validation/inspection is a separate responsibility. |
| Browser logging in via form, expecting subsequent requests to stay recognized solely via session | Not appropriate: context is not remembered; consider `WebSessionServerSecurityContextRepository` and a consistent login configuration. |
| Workflows needing to maintain login state across requests without the client resending credentials | Not appropriate with NoOp alone; another persistence/restoration strategy is required. |

**Comparison with `WebSessionServerSecurityContextRepository`:** that repository uses `WebSession` to store context and retrieve it on subsequent requests while the corresponding session remains valid. NoOp avoids doing that, reducing reliance on sessions for identity restoration at the cost of requiring the client to re-authenticate on each request. Using NoOp does not reduce password/token verification cost by itself; every authentication still incurs cost that must be planned for.

## 7. Misconceptions and Security Notes

1. **"NoOp disables authentication."** False. Authentication and authorization still run; NoOp merely does not save/load `SecurityContext` between requests at the configured filters.
2. **"Setting the repository on `ServerHttpSecurity` controls all save operations."** Do not assume that. `ReactorContextWebFilter` loads context via the repository configured at the HTTP level, whereas each `AuthenticationWebFilter` has its own repository configuration for saving. Check the actual authentication mechanism (HTTP Basic, form login, OAuth2, etc.) and configure the repository in the right place.
3. **"Because context exists in Reactor, context is remembered on the next call."** False. Reactor Context holds data for the current processing sequence; it is not durable storage across two HTTP requests.
4. **"NoOp guarantees zero `WebSession`, `Set-Cookie`, or CSRF."** False. Other components can still use sessions/cookies, and CSRF is a separate protection concern. Only disable CSRF after analyzing client types, credentials automatically sent by browsers, and the attack surface—never out of habit.
5. **"HTTP 403 proves the repository failed to load."** Not necessarily. 401 usually reflects missing/invalid authentication; 403 typically relates to access permissions or CSRF. Inspect the actual configuration and logs.
6. **"Using Basic with plaintext passwords is enough for a stateless API."** False. The `{noop}` example is for demos only. Use TLS, hashed passwords in storage, and access control; if using Bearer/JWT, verify issuer/audience/signature/expiration and design revocation when needed.
7. **"NoOp automatically handles logout or token revocation."** False. With no session context to remove, client-side logout may mean stopping token transmission; invalidating already-issued tokens early requires another mechanism.

### Quick Selection Guide

- Question "Can this request prove its own identity?" -> If **yes**, a policy that does not persist `SecurityContext` across requests is usually appropriate.
- Question "Does the user need to be recognized on the next request without resending credentials?" -> If **yes**, using NoOp alone will not satisfy this.
- Question "Is the entire application guaranteed to be stateless?" -> You must evaluate sessions, cookies, request caches, CSRF, login, and other state stores separately; do not infer it from a single repository.

## 8. Self-Check

**Scenario A:** Send `GET /me` with a valid Basic header, then send it again without the header. Why does the second request receive 401? Because NoOp does not save context to reload later; the second request carries no new credentials.

**Scenario B:** Two consecutive requests both send a valid Bearer token, and both succeed. Is NoOp failing to work? No. Each request can be authenticated independently using its own token.

**Scenario C:** You build a custom `AuthenticationWebFilter`, call `setSecurityContextRepository` with a repository that persists to session, yet only set NoOp on `ServerHttpSecurity`. Is it certain the system as a whole does not persist context? No; you must inspect the filter's own repository used at `save`, because reading and writing can be configured in different places.

## 9. Official Documentation

- Spring Security API: [`NoOpServerSecurityContextRepository`](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/context/NoOpServerSecurityContextRepository.html).
- Spring Security API: [`ServerSecurityContextRepository`](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/context/ServerSecurityContextRepository.html).
- Spring Security API: [`ServerHttpSecurity`](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html), especially `securityContextRepository` and `httpBasic` configuration.
- Spring Security: [WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html).

**Key takeaway:** NoOp does not prevent authentication from producing a `SecurityContext` within the current request; it ensures the configured repository does not persist context for reuse on subsequent requests.