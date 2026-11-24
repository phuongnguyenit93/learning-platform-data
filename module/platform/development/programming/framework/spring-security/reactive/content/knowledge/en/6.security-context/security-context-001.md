# Authentication, principal, credentials, and GrantedAuthority in SecurityContext

## 1. Objectives and big picture

In Spring Security reactive (Spring WebFlux), the application needs to answer two questions for every request:

1. **Authentication:** who is sending the request, and has the login proof been verified?
2. **Authorization:** is the authenticated identity allowed to access this resource or perform this operation?

The objects in the title have the following relationship:

~~~text
Reactor Context of the request/subscription processing flow
└── Mono<SecurityContext> (managed by Spring Security)
    └── SecurityContext
        └── Authentication
            ├── principal           Who is logged in? (UserDetails, Jwt, ...)
            ├── credentials         Proof: password/token/... (may be erased)
            ├── authorities         Granted GrantedAuthority values
            ├── authenticated       Trust state of the authentication token
            └── details             Additional details, not permissions
~~~

**`SecurityContext` holds an `Authentication`**, while `Authentication` groups identity, proof, and permission information. `GrantedAuthority` does not verify identity on its own; it describes permissions assigned to the user by a trusted authentication source.

In WebFlux, a decisive difference from Servlet is that the security context is accessed via **`ReactiveSecurityContextHolder` and the Reactor Context** along the reactive chain; it does not rely on every operation of a request always running on a single ThreadLocal.

After this lesson, you will be able to:
- Distinguish `SecurityContext`, `Authentication`, and `java.security.Principal`.
- Understand `getPrincipal()`, `getCredentials()`, `getAuthorities()`, `isAuthenticated()`, `getName()`, and `getDetails()`.
- Explain the authentication token lifecycle before/after verification, credential erasure behavior, and anonymous semantics.
- Retrieve the identity inside a `Mono`/`Flux` without calling `block()` in a WebFlux handler.
- Write and test an endpoint with `ROLE_READER` / `ROLE_ADMIN` using Spring Boot WebFlux.

## 2. What is `SecurityContext`?

`org.springframework.security.core.context.SecurityContext` is the interface responsible for holding the current `Authentication` information. Its two main methods are:

~~~java
Authentication getAuthentication();
void setAuthentication(Authentication authentication);
~~~

`SecurityContextImpl` is the common implementation. `getAuthentication()` can return `null` when the context does not yet contain authentication information; moreover, in reactive, reading `ReactiveSecurityContextHolder.getContext()` can return `Mono.empty()` if there is no context in the Reactor Context.

**Do not equate "having a `SecurityContext`" with "being logged in".** A context may not yet contain an authentication, or it may contain an authentication representing an anonymous user. Access decisions must be made by Spring Security authorization, according to rules and application policies.

A pure API example (to illustrate structure, **not a login operation**) is:

~~~java
SecurityContext context = new SecurityContextImpl();
Authentication token = UsernamePasswordAuthenticationToken.unauthenticated(
    "linh", "mat-khau-chua-xac-minh"
);
context.setAuthentication(token);
~~~

Here `token.isAuthenticated() == false`: the token is only an **authentication request**, not proof of being logged in. Creating and placing an object into the context does not verify the password itself. In a normal WebFlux request, let the security filters and authentication manager manage the context.

## 3. `Authentication`: the central object of authentication

`org.springframework.security.core.Authentication` extends `java.security.Principal`. It has two roles depending on the stage:

- **Before authentication:** represents a request for `ReactiveAuthenticationManager` to verify; may contain username/password/token provided by the client, with `isAuthenticated() == false`.
- **After successful authentication:** represents a trusted identity along with resolved authorities; an appropriate implementation has `isAuthenticated() == true`. Spring Security places this result into `SecurityContext` via the filter/context repository mechanism.

Core APIs:

| API | Meaning | What to avoid |
| --- | --- | --- |
| `getPrincipal()` | Verified identity or identifying object in the request | Casting every principal to `String` or `UserDetails` |
| `getCredentials()` | Proof such as password, token; may be `null` after authentication | Returning in APIs, logging, or retaining passwords long in memory |
| `getAuthorities()` | Granted `GrantedAuthority` instances | Trusting self-declared permissions from the client |
| `isAuthenticated()` | State indicating the authentication token is trusted by the framework; not sufficient for all permission decisions | Using this boolean alone as the sole authorization check |
| `getName()` | Identifier name at the `Principal` level, suitable for general username needs | Assuming the name is an immutable ID or email address |
| `getDetails()` | Metadata depending on the authentication mechanism (for example, web authentication info) | Confusing metadata with permissions or verified data |

`Authentication` is **not** a JSON record with a fixed structure. Depending on the login method, the token type and principal type vary greatly. When writing reusable code, work with the interface first and only cast after checking the type.

### 3.1. Principal is identity, not "password"

Some practical forms of `getPrincipal()`:

- Username/password: usually `UserDetails` after successful authentication.
- Bearer JWT: may be a `Jwt` object inside `JwtAuthenticationToken`; `getName()` is typically tied to `sub` or a configured claim name.
- OAuth2 login: may be `OAuth2User` or `OidcUser`.
- A custom authentication: may be a principal type defined by the application.

Therefore:

~~~java
Object principal = authentication.getPrincipal();

if (principal instanceof UserDetails userDetails) {
    String username = userDetails.getUsername();
    // Only use fields that have been verified by a trusted authentication source.
}

String displayName = authentication.getName(); // Common API.
~~~

`getName()` is often more convenient when only the identity name is needed. However, names can be reused or changed; if the system needs a stable identity key, choose a reliable identifier from the verified principal type, such as the token's subject and issuer, or an internal user ID.

Do **not** assume `principal.toString()` is safe to log or return to the client; many implementations may contain additional attributes that should not be exposed.

### 3.2. Credentials are proof, not identity

Before authentication, `credentials` may be a raw password; in a bearer mechanism, it may be a token or another form of proof. After authentication, many implementations erase sensitive information via `eraseCredentials()`; `getCredentials()` may then return `null`. **There is no guarantee that every implementation/mechanism erases all credentials**.

Typical flow:

~~~text
Client sends username/password
   ↓
Unauthenticated UsernamePasswordAuthenticationToken
   principal = username
   credentials = raw password
   authenticated = false
   ↓ ReactiveAuthenticationManager checks
Authenticated Authentication
   principal = UserDetails or domain principal
   credentials = usually erased / null
   authorities = granted permissions
   authenticated = true
   ↓
SecurityContext stores Authentication for authorization to use
~~~

Distinguish between:
- **Password hash** in the database: data used to verify a password, not a plaintext password.
- **Raw password/secret** entered from the client: do not store/log/serialize or use as user profile information.
- **Credentials in `Authentication`**: value depends on the mechanism and stage; may be `null`.
- **Session ID/JWT**: have different ways of being stored, transmitted, and verified; do not automatically include them in responses/debug output just because `getCredentials()` returns data.

### 3.3. `isAuthenticated()` is not equivalent to `authenticated()` in every case

`isAuthenticated()` is a status flag on the authentication token. For example, `AnonymousAuthenticationToken` can have `isAuthenticated() == true` at the implementation level, yet Spring Security does **not** treat anonymous as a logged-in user when evaluating `authenticated()` via the default authorization mechanism.

Therefore, a custom authorization filter written like this:

~~~java
if (authentication != null && authentication.isAuthenticated()) {
    // Allowing sensitive data yourself: NOT RECOMMENDED.
}
~~~

is incomplete: it can handle anonymous users unintendedly. Use `authorizeExchange(...).authenticated()` / `hasRole(...)`, method security (`@PreAuthorize`), or the corresponding trust/authorization API instead of a single boolean check.

## 4. What is `GrantedAuthority`? Role, permission, and scope

`GrantedAuthority` is the interface representing a granted permission. Core method:

~~~java
String getAuthority();
~~~

`SimpleGrantedAuthority` is a common implementation holding a permission name string. For example:

~~~java
new SimpleGrantedAuthority("ROLE_READER");
new SimpleGrantedAuthority("ROLE_ADMIN");
new SimpleGrantedAuthority("SCOPE_orders.read");
~~~

These are **three different string values**, and do not automatically carry the same meaning. Some complex implementations may return `null` from `getAuthority()`; such implementations require dedicated handling rather than assuming every authority is a string.

### 4.1. How do role and authority differ?

By default convention in Spring Security:

- `hasRole("ADMIN")` usually checks the `ROLE_ADMIN` authority; developers **do not pass `ROLE_` up front** when calling `hasRole("ADMIN")`.
- `hasAuthority("ROLE_ADMIN")` checks the exact string `ROLE_ADMIN`.
- `hasAuthority("orders:read")` checks the exact `orders:read`; no prefix is added automatically.
- `hasAuthority("SCOPE_orders.read")` checks the permission with the `SCOPE_` prefix, commonly seen in OAuth2 resource server mechanisms when scopes are converted according to the corresponding default configuration.

| Authorities in `Authentication` | Rule | Result |
| --- | --- | --- |
| `["ROLE_READER"]` | `hasRole("READER")` | Allowed |
| `["ROLE_READER"]` | `hasRole("ADMIN")` | Denied |
| `["ROLE_ADMIN"]` | `hasAuthority("ROLE_ADMIN")` | Allowed |
| `["SCOPE_orders.read"]` | `hasAuthority("SCOPE_orders.read")` | Allowed |
| `["ROLE_ADMIN"]` | `hasAuthority("ADMIN")` | Denied (string mismatch) |

The JWT example is illustrative only: not every scope/role claim automatically becomes a `GrantedAuthority`. Converting `scope`/`scp` to `SCOPE_*`, or a custom claim to `ROLE_*`, depends on the converter/config and the chosen authentication mechanism. Learners must verify the **actual authorities list** of the verified authentication.

### 4.2. Never accept self-declared authorities from the client

For example, a client sending JSON `{"username":"linh","roles":["ROLE_ADMIN"]}` does **not** prove that person has admin rights. Only grant permissions after the backend verifies the identity and looks up a trusted policy/authority source or verifies valid signed claims according to configuration.

Normally `Authentication` contains permissions populated by a verified manager/provider. Authorization uses those permissions to make decisions. Do not write code like:

~~~java
UsernamePasswordAuthenticationToken.authenticated(
    request.username(), request.password(), request.authorities()
);
~~~

on unverified input. The static factory `authenticated(...)` is an API for creating a token that is **already trusted**; calling it on unvalidated input is a security bug. Pass an unauthenticated token to the manager, or let the framework handle the request itself.

## 5. Where does `SecurityContext` live in WebFlux?

### 5.1. Comparing Servlet and reactive

| Model | Where context is usually retrieved | What to watch out for |
| --- | --- | --- |
| Spring MVC/Servlet | `SecurityContextHolder.getContext()` with default ThreadLocal strategy | Servlet filters manage the context on the processing thread |
| Spring WebFlux/Reactor | `ReactiveSecurityContextHolder.getContext()` returning `Mono<SecurityContext>` | Reactor Context is attached to the subscriber, flowing across compatible reactive operators |

In WebFlux, do not read `SecurityContextHolder.getContext()` assuming ThreadLocal will always be accurate when a request switches threads across `flatMap`, `publishOn`, or async I/O. You should also not manually call `subscribe()` inside a handler to "fetch authentication" and run logic outside the request lifecycle.

Correct API:

~~~java
Mono<Authentication> currentAuthentication =
    ReactiveSecurityContextHolder.getContext()
        .flatMap(context -> Mono.justOrEmpty(context.getAuthentication()));
~~~

Key points to understand:
- `ReactiveSecurityContextHolder.getContext()` returns a **publisher**; it does not necessarily have a value yet when you construct the chain.
- When no context exists, the publisher can complete empty; if `context.getAuthentication() == null`, `Mono.justOrEmpty(...)` is also empty.
- When authentication is present, use `map` / `flatMap` on the `Mono` to continue processing **without blocking the thread**.
- Spring Security WebFlux usually populates the context for a request through security filters/repositories when an authentication mechanism succeeds.
- Reactor Context is part of the subscription chain; it is not synonymous with a server-side session persisted across multiple HTTP requests. HTTP Basic, session login, and Bearer JWT have different ways of persisting/reconstructing identity across requests.

### 5.2. Reading identity properly in a reactive chain

~~~java
Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
        .flatMap(context -> Mono.justOrEmpty(context.getAuthentication()))
        .map(Authentication::getName)
        .switchIfEmpty(Mono.error(
            new IllegalStateException("No authentication in Reactor Context")));
}
~~~

The snippet above is an illustrative method in an application with `reactor-core` and Spring Security dependencies; it emits an error if authentication is missing. In a real web handler, let `SecurityWebFilterChain` reject unauthenticated requests at the HTTP layer, while business logic processes the delivered valid identity.

Do **not** do this in a reactive handler:

~~~java
// Wrong context in WebFlux: ThreadLocal may not hold the request identity.
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

// Wrong lifecycle: block() inside the event loop can cause errors/block the request.
String username = currentUsername().block();
~~~

The snippets above are included to recognize anti-patterns, not for use in a complete program.

### 5.3. Attaching a temporary context with `contextWrite`

When writing a test or an illustrative pipeline, `ReactiveSecurityContextHolder.withAuthentication(authentication)` returns a Reactor `Context` to attach to the subscription:

~~~java
Mono<String> lookup = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName)
    .defaultIfEmpty("<none>");

Authentication trusted = UsernamePasswordAuthenticationToken.authenticated(
    "linh",
    null,
    List.of(new SimpleGrantedAuthority("ROLE_READER"))
);

Mono<String> withIdentity = lookup.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(trusted)
);
~~~

`lookup` without a context emits `"<none>"`, whereas `withIdentity` can emit `"linh"`. Placing `contextWrite` at the end of a pipeline segment affects **upstream** operators within the same subscription. `withAuthentication(...)` does not verify passwords; here `trusted` is a fixture for testing. Do not construct such a fixture from a client request and treat it as a successful login.

The context can continue flowing across `flatMap`/`publishOn` while still in the same managed Reactor pipeline. It is **not guaranteed** to propagate across detached chains where you manually call `subscribe()`, self-created threads, or arbitrary third-party library callbacks not participating in Reactor; those boundaries require an appropriately designed context propagation solution.

## 6. Complete demo project: Java 17+, WebFlux, Spring Security

The following example uses **Spring Boot 3.3.13**, Spring Security version-managed by Boot, Java 17+, and Gradle. It displays **name, principal type, and authorities** of the authenticated user, while **never returning credentials**.

### 6.1. Structure

~~~text
reactive-security-context-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── SecurityContextDemoApplication.java
    │   ├── SecurityConfig.java
    │   └── IdentityController.java
    └── test/java/demo/
        ├── IdentityControllerTests.java
        └── ReactorContextScopeTests.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'reactive-security-context-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

If the project has a Gradle Wrapper, use the wrapper; this example only lists the files needed for learning and uses an installed Gradle. Boot manages the Spring Security and Reactor versions, so do not pin versions manually for these dependencies.

### 6.2. Bootstrapping the application

`src/main/java/demo/SecurityContextDemoApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityContextDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityContextDemoApplication.class, args);
    }
}
~~~

### 6.3. Configuring authentication and authorization

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
class SecurityConfig {

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public").permitAll()
                .pathMatchers("/admin").hasRole("ADMIN")
                .anyExchange().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService userDetailsService(
            PasswordEncoder encoder) {

        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-pass"))
            .roles("READER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }
}
~~~

In the demo:
- Basic authentication accepts username/password and uses the user store to verify; upon success, Spring Security has an `Authentication` with the appropriate principal and authorities.
- `reader` receives `ROLE_READER`; `admin` receives `ROLE_ADMIN` because `roles(...)` applies the `ROLE_` prefix convention.
- `/admin` requires `ROLE_ADMIN`. `/public` simply passes the `permitAll()` rule; `/me` and all remaining URLs require login.
- Form login is disabled so the unauthenticated API response is clearly observable as HTTP 401 when using Basic.
- Passwords in the example are local values for testing; BCrypt hashes passwords in the user store. In production, do not hard-code credentials and use HTTPS.

**Note:** `@EnableWebFluxSecurity` makes explicit where WebFlux security is enabled; in Spring Boot with the appropriate starter, auto-configuration usually handles this already. `SecurityWebFilterChain`'s role is HTTP rules; `MapReactiveUserDetailsService`'s role is the demo identity source. Do not confuse the two responsibilities.

### 6.4. Handler reading only safe data from `SecurityContext`

`src/main/java/demo/IdentityController.java`:

~~~java
package demo;

import java.util.List;
import java.util.Objects;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
class IdentityController {

    public record IdentityView(
        String name,
        String principalType,
        boolean authenticated,
        List<String> authorities
    ) {}

    @GetMapping("/public")
    Mono<String> publicInfo() {
        return Mono.just("public");
    }

    @GetMapping("/me")
    Mono<IdentityView> currentUser() {
        return ReactiveSecurityContextHolder.getContext()
            .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()))
            .map(this::safeView)
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(HttpStatus.UNAUTHORIZED)
            ));
    }

    @GetMapping("/admin")
    Mono<String> adminOnly() {
        return Mono.just("admin");
    }

    private IdentityView safeView(Authentication authentication) {
        String principalType = authentication.getPrincipal() == null
            ? "<none>"
            : authentication.getPrincipal().getClass().getSimpleName();

        List<String> granted = authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .filter(Objects::nonNull)
            .sorted()
            .toList();

        return new IdentityView(
            authentication.getName(),
            principalType,
            authentication.isAuthenticated(),
            granted
        );
    }
}
~~~

Reading the `/me` flow:
1. `getContext()` retrieves `Mono<SecurityContext>` **from the request's Reactor Context**.
2. `flatMap(... Mono.justOrEmpty(...))` converts the context into `Mono<Authentication>`, emitting nothing if missing.
3. `map(this::safeView)` converts `Authentication` into a DTO with name, principal type, status flag, and authority list.
4. `switchIfEmpty` is a defensive measure in the controller; most unauthenticated requests are rejected by security filters **before reaching the controller**.
5. The controller **does not read `getCredentials()`**, does not return the entire `UserDetails`, and does not log raw tokens/passwords.

`IdentityView.authenticated` is useful for observing the example, **not** an API for making standalone permission decisions. Real authorization is configured in `SecurityWebFilterChain` via `authenticated()` and `hasRole("ADMIN")`.

When authenticating via Basic with `MapReactiveUserDetailsService` in the example, `principalType` is usually `"User"` (class `org.springframework.security.core.userdetails.User`). If you switch the mechanism to JWT/OIDC or a custom principal, this field changes; that is why the code only reads the type name rather than hard-casting.

### 6.5. Running and observing responses

From the project directory, requiring JDK 17+ and a compatible Gradle:

~~~bash
gradle bootRun
~~~

If a wrapper is present, use `./gradlew bootRun` on Linux/macOS or `gradlew.bat bootRun` on Windows. In a bash/Git Bash shell, run:

~~~bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/public
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/me
curl -s -u reader:reader-pass http://localhost:8080/me
curl -s -u reader:reader-pass -o /dev/null -w '%{http_code}\n' http://localhost:8080/admin
curl -s -u admin:admin-pass -o /dev/null -w '%{http_code}\n' http://localhost:8080/admin
~~~

The HTTP status results of commands 1, 2, 4, and 5 in order are:

~~~text
200
401
403
200
~~~

Command 3 returns JSON with data corresponding to the following (whitespace and JSON property order may vary):

~~~json
{
  "name": "reader",
  "principalType": "User",
  "authenticated": true,
  "authorities": ["ROLE_READER"]
}
~~~

Command 4 returns **403** because `reader` is logged in but lacks `ROLE_ADMIN`. Command 2 returns **401** because no credentials were provided and the demo enables HTTP Basic while disabling form login. These numbers are expectations for the sample configuration and should not be generalized to every deployment (exception handlers, authentication entry points, CORS, and other mechanisms can alter the HTTP behavior).

Do not look for a password in the JSON: credentials must be verified and then have their lifetime minimized, not exposed to the client. If running on Windows PowerShell, use `curl.exe` instead of the `curl` alias; depending on the system, `/dev/null` may need to be changed to `NUL`.

## 7. Testing context and authorization

### 7.1. HTTP testing with `WebTestClient`

`src/test/java/demo/IdentityControllerTests.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class IdentityControllerTests {

    @Autowired
    WebTestClient client;

    @Test
    void unauthenticatedCannotReadIdentity() {
        client.get().uri("/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void readerCanInspectTrustedIdentityAndAuthorities() {
        client.get().uri("/me")
            .headers(headers -> headers.setBasicAuth("reader", "reader-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.name").isEqualTo("reader")
            .jsonPath("$.principalType").isEqualTo("User")
            .jsonPath("$.authenticated").isEqualTo(true)
            .jsonPath("$.authorities[0]").isEqualTo("ROLE_READER")
            .jsonPath("$.credentials").doesNotExist();
    }

    @Test
    void roleBasedAccessIsEnforcedBySecurityFilters() {
        client.get().uri("/admin")
            .headers(headers -> headers.setBasicAuth("reader", "reader-pass"))
            .exchange()
            .expectStatus().isForbidden();

        client.get().uri("/admin")
            .headers(headers -> headers.setBasicAuth("admin", "admin-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin");
    }

    @Test
    void publicEndpointNeedsNoLogin() {
        client.get().uri("/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");
    }
}
~~~

The tests verify an identity authenticated by HTTP Basic in a real request, where Spring Security builds `Authentication`, assigns authorities, and applies HTTP rules. Do not simulate "logged in" by manually setting a boolean on a client object.

### 7.2. Testing Reactor Context scoped per subscription

`src/test/java/demo/ReactorContextScopeTests.java`:

~~~java
package demo;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

import static org.assertj.core.api.Assertions.assertThat;

class ReactorContextScopeTests {

    private Mono<String> currentName() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName)
            .defaultIfEmpty("<none>");
    }

    @Test
    void contextIsScopedToEachSubscription() {
        // Trusted fixture ONLY for tests, must not be constructed from client input.
        Authentication fixture = UsernamePasswordAuthenticationToken.authenticated(
            "linh",
            null,
            List.of(new SimpleGrantedAuthority("ROLE_READER"))
        );

        Mono<String> read = currentName();

        assertThat(read.block()).isEqualTo("<none>");
        assertThat(read.contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(fixture)
        ).block()).isEqualTo("linh");
        assertThat(read.block()).isEqualTo("<none>");
    }

    @Test
    void contextSurvivesAReactorSchedulerChange() {
        Authentication fixture = UsernamePasswordAuthenticationToken.authenticated(
            "mai",
            null,
            List.of(new SimpleGrantedAuthority("ROLE_READER"))
        );

        Mono<String> readOnOtherScheduler = Mono.just(1)
            .publishOn(Schedulers.parallel())
            .flatMap(ignored -> currentName())
            .contextWrite(ReactiveSecurityContextHolder.withAuthentication(fixture));

        assertThat(readOnOtherScheduler.block()).isEqualTo("mai");
    }
}
~~~

In the tests, `block()` is a synchronous test-boundary wait operation; do not copy `block()` into a WebFlux handler. The two checks clarify:
- **Having a context** or **not having a context** is determined per subscription; the same publisher can produce different results if the context of each subscription differs.
- `publishOn` changes the scheduler without inherently losing the Reactor Context within a valid Reactor chain. Conversely, spawning threads manually / detached subscriptions or crossing libraries without propagation support may require a dedicated context bridge.

Run all tests:

~~~bash
gradle test
~~~

Or `./gradlew test` / `gradlew.bat test` if using the wrapper. All six tests across the two classes are expected to PASS, with Gradle returning exit code 0. Specific logs vary by machine, so no fixed Gradle output line is listed.

## 8. JWT authentication and non-username/password principals

With a reactive Resource Server, Spring Security can create a `JwtAuthenticationToken` after verifying the signature, expiration, and conditions of the JWT decoder. In that case:
- `getPrincipal()` is typically `Jwt` rather than `UserDetails`.
- `getName()` is typically tied to the subject or configured claim.
- `getAuthorities()` depends on the mechanism converting claims/scopes into `GrantedAuthority`; for example `SCOPE_read`.
- `getCredentials()` depends on the authentication type; do not assume `null` or try to read the token and return it in the API.

**Illustrative type-safe access example** (valid only when resource server is configured and JWT authentication is present):

~~~java
if (authentication instanceof JwtAuthenticationToken jwtAuth) {
    String subject = jwtAuth.getToken().getSubject();
    // Use verified subject + issuer/tenant or ID
    // according to application policy; do not put raw JWT in logs.
}
~~~

This snippet requires importing `org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken` and the Spring Security OAuth2 Resource Server dependency; **it is not part of the Basic sample project in section 6**. It illustrates why type checking is necessary before accessing details specific to an authentication mechanism.

Do not grant admin permissions just because a token contains a text claim self-declared by the client: the JWT must be fully verified, claim mapping must be defined by the backend, and authorization must rely on trusted authorities.

## 9. Common mistakes when working with `SecurityContext`

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| Using `SecurityContextHolder.getContext()` as a fixed ThreadLocal in WebFlux | May be empty, read the wrong context, or lose identity on thread switches | Use `ReactiveSecurityContextHolder.getContext()` inside the Reactor pipeline |
| Calling `.block()` / manual `subscribe()` in a handler to get the username | Blocks the event loop, detaches logic from the request lifecycle | Return `Mono`/`Flux` and continue with `map`/`flatMap` |
| `(UserDetails) auth.getPrincipal()` without type checking | `ClassCastException` when switching to JWT/OIDC/custom auth | Use `getName()` or `instanceof` per mechanism |
| Reading and returning `getCredentials()` in DTOs/logs | Leaks raw passwords, bearer tokens, or secrets | Do not return credentials; only use controlled public data |
| Treating `isAuthenticated()` as always meaning "real logged-in user" | Anonymous may be misidentified | Use `authenticated()` rules and framework authorization |
| Trusting roles/authorities sent in client JSON | Privilege escalation | Only accept authorities from a verified manager, user store, or verified claims |
| Using `hasRole("ADMIN")` while granting `"ADMIN"` instead of `"ROLE_ADMIN"` | Permission mismatch | Stay consistent with the prefix convention or use `hasAuthority` with the exact string |
| Creating an authenticated authentication via `authenticated(...)` from unverified input | Bypasses the authentication step | Only use after trusted verification; in tests use explicit fixtures |
| Assuming Reactor Context persists across new requests | Confuses login persistence mechanisms | Sessions or tokens must be loaded/authenticated by the security mechanism on each request |
| Assuming `getDetails()` or `principal.toString()` is always safe to log | May leak metadata/secrets | Log only minimal, non-sensitive information |
| Relying on identity from an independently subscribed publisher | Context may not propagate to the detached chain | Stay in the same pipeline or use a supported context propagation solution |
| Passing a `SecurityContext` with `null` `Authentication` into authorization and treating it as success | Bypasses identity checks | Check for empty/anonymous signals; use web security filters to decide |

### 9.1. Why should `Authentication` not be cached globally?

`Authentication` carries identity and permissions **per request/user**. Storing it in a static field, singleton state, or shared cache without binding to the proper principal/session risks mixing permissions across users. If user data needs caching, cache by identity key and appropriate policy; never take a current `SecurityContext` object and apply it to all requests.

### 9.2. Distinguishing `SecurityContext` from HTTP session

- `SecurityContext` is the object holding authentication at execution time.
- **Reactor Context** is the mechanism for propagating data along a reactive subscription.
- **HTTP session** is a mechanism that can store state across multiple requests, depending on security configuration.
- **Bearer token/JWT** is typically sent per request for the server to verify and reconstruct `Authentication`; the architecture can be stateless.

A system can use Reactor Context **alongside** a session, or Reactor Context with a bearer token; do not conflate them.

## 10. Check-up questions and answers

1. **What object does `SecurityContext` usually hold?** `Authentication`; it may not have an authentication yet.
2. **Is `principal` always a username string?** No. It can be `UserDetails`, `Jwt`, `OAuth2User`, or a domain principal.
3. **Does `getCredentials() == null` mean authentication failed?** No. Credentials may have been erased after successful authentication.
4. **Does `getAuthorities()` make an authentication valid on its own?** No. Authorities must come from a trusted source after authentication.
5. **What authority string does `hasRole("ADMIN")` usually require?** `ROLE_ADMIN`.
6. **Can an `AnonymousAuthenticationToken` have `isAuthenticated() == true`?** Yes; do not use that flag as a standalone authorization check.
7. **In WebFlux, where is the context read from?** `ReactiveSecurityContextHolder.getContext()`, returning `Mono<SecurityContext>`.
8. **Why not use `SecurityContextHolder` ThreadLocal like in Servlet?** WebFlux can switch threads within the same pipeline; Reactor Context is attached per subscription.
9. **Does `contextWrite(ReactiveSecurityContextHolder.withAuthentication(...))` verify passwords itself?** No; it only attaches a fixture/context. Only use it with trusted authentication.
10. **Why does a request to `/me` as reader return 200 while `/admin` returns 403?** Reader is authenticated, but lacks `ROLE_ADMIN`.
11. **Does `@EnableReactiveMethodSecurity` replace `SecurityWebFilterChain`?** No; method security is an additional layer that can rely on the authentication in Reactor Context.
12. **Should the raw `Authentication` object be returned in an HTTP response?** No. Create a DTO exposing only the minimum required information, omitting credentials and sensitive data.

## 11. Official documentation

- Spring Security, `Authentication` API: https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/core/Authentication.html
- Spring Security, `SecurityContext` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/SecurityContext.html
- Spring Security, `GrantedAuthority` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/GrantedAuthority.html
- Spring Security, `ReactiveSecurityContextHolder` API: https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/core/context/ReactiveSecurityContextHolder.html
- Spring Security, reactive method security and Reactor Context: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Security, WebFlux security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html

**Remember:** `SecurityContext` is the container holding `Authentication`; `principal` answers "who?", `credentials` are proof to be protected, `GrantedAuthority` answers "what permissions are granted?", and reactive authorization uses that **verified** information through the request's Reactor context.
