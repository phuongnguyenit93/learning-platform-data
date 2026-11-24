# ServerAuthenticationConverter and Converting Credentials from Requests

## 1. Problem and Objectives

In a **Spring Security Reactive** application running on Spring WebFlux, a client can send credentials via HTTP Basic, Bearer token, form data, client certificate, or a custom protocol. However, the part that **checks whether those credentials are valid** needs a common model so we do not have to write authentication logic in every controller.

`ServerAuthenticationConverter` solves the **step of converting HTTP input into an `Authentication` candidate**. It does not decide on its own that the user has logged in successfully. Actual verification usually belongs to `ReactiveAuthenticationManager`; `AuthenticationWebFilter` coordinates these steps and places the verified authentication into the request's reactive context.

After this lesson, you will be able to:

- State accurately the contract of `ServerAuthenticationConverter.convert(ServerWebExchange)` and its three outcomes: candidate present, no candidate, or error.
- Distinguish **extracting credentials**, **authenticating credentials**, **saving/propagating SecurityContext**, and **access authorization**.
- Explain that `Mono.empty()` means "do not perform this authentication attempt", **not** that the request is granted access.
- Recognize built-in converters such as HTTP Basic, Bearer, and form login, and when a custom converter is truly needed.
- Build a Java 17+ example comprising a converter, `ReactiveAuthenticationManager`, `AuthenticationWebFilter`, security chain, WebFlux endpoints, and tests.
- Spot mistakes regarding `isAuthenticated`, error handling, untrusted headers, `block()`, `subscribe()`, request body consumption, CSRF, and security filter ordering.

This lesson belongs to the **Reactive Authentication** group. The example demonstrates a credential-receiving mechanism defined for learning; in real systems, prefer standards supported by Spring Security and use HTTPS, password hashing, key/token management, and appropriate security policies.

## 2. Where the Converter Fits in the Authentication Flow

Overall flow:

~~~text
Client HTTP request
      |
      v
ServerWebExchange (request headers, cookies, query, body, TLS info...)
      |
      v
SecurityWebFilterChain / AuthenticationWebFilter
      |
      +--> Matcher: should authentication be attempted on this request?
      |
      v
ServerAuthenticationConverter.convert(exchange)
      |
      +--> Mono.empty()    : no matching credentials -> do not attempt this time
      +--> Mono.error(...) : request has malformed credentials -> error
      +--> Mono<Authentication> : creates unverified candidate
                                       |
                                       v
                         ReactiveAuthenticationManager
                                       |
                          +------------+------------+
                          |                         |
               Authentication failed     Authentication succeeded
                          |                         |
                    Failure handler          Trusted Authentication
                                                    |
                                                    v
                                     Reactive SecurityContext / Reactor Context
                                                    |
                                                    v
                                         Request Authorization
                                                    |
                                                    v
                                            WebFlux handler
~~~

**Separated roles:**

| Class | Question it answers | Example |
| --- | --- | --- |
| `ServerAuthenticationConverter` | Which credentials is the request presenting, and in what format? | Extracting username/password from a Basic header or a Bearer token string |
| `ReactiveAuthenticationManager` | Are those credentials/token valid, and which identity/authorities are granted? | Checking password, JWT signature/claims, IdP result |
| `AuthenticationWebFilter` | When are converter/manager invoked and how are success/failure handled? | Attaching context to the pipeline, calling success/failure handlers |
| `ServerSecurityContextRepository` | Should SecurityContext be saved/loaded across requests? | WebSession or no-op |
| `ReactiveSecurityContextHolder` | How does downstream read the subscription's SecurityContext? | `Mono<SecurityContext>` in the Reactor Context |
| Authorization | Is the authenticated identity allowed to perform this operation? | `authenticated()`, `hasRole("ADMIN")`, order ownership |

A converter returning an `Authentication` does not mean "logged in". It is only an **authentication request token** that needs to be verified by the manager. The name `Authentication` is used for both unverified and verified tokens because the interface represents both states.

## 3. Exact Contract of ServerAuthenticationConverter

The interface lives in package:

~~~text
org.springframework.security.web.server.authentication.ServerAuthenticationConverter
~~~

Conceptual signature:

~~~java
@FunctionalInterface
public interface ServerAuthenticationConverter {
    Mono<Authentication> convert(ServerWebExchange exchange);
}
~~~

Because it has only one abstract method, it can be implemented via a class, lambda, or method reference. The `ServerWebExchange` parameter allows reading the current HTTP request. The `Mono<Authentication>` return type expresses that conversion is part of the Reactor pipeline.

### 3.1. Three Important Outcomes

**Outcome A — `Mono.empty()`: no matching candidate**

For example, a converter targets `X-Learn-User` and `X-Learn-Key` headers, yet the request carries neither header. The converter should return `Mono.empty()` to state **there is no authentication attempt for that mechanism**. `AuthenticationWebFilter` continues the filter chain; if a protected endpoint requires login, the authorization layer/entry point can still reject it with 401.

**Outcome B — `Mono.just(authentication)`: credentials present to verify**

For example, the request carries both headers with valid structure. The converter creates a `UsernamePasswordAuthenticationToken` with `isAuthenticated() == false`. The manager will verify the actual values and only then create an authenticated token with appropriate authorities.

**Outcome C — `Mono.error(authenticationException)`: credentials present but malformed**

For example, the client sends `X-Learn-User` but omits `X-Learn-Key`, or a header lacks required data. Choose an error like `BadCredentialsException` to describe invalid input. When handled inside `AuthenticationWebFilter` with an appropriate failure handler, it leads to an authentication error response. Do not turn a parse error into `Mono.empty()` if doing so causes the system to ignore bad credentials and unexpectedly fall through to another mechanism.

| Situation | What should the converter emit? | Meaning |
| --- | --- | --- |
| No sign of this scheme | `Mono.empty()` | Do not attempt authentication for this scheme |
| Syntactically valid headers | `Mono.just(unauthenticatedToken)` | Send credentials to the manager |
| Scheme recognized but payload missing/malformed | `Mono.error(BadCredentialsException)` | Reject invalid input |
| Incorrect password | **Manager** emits `AuthenticationException` | Converter is not responsible for verifying passwords |
| Request authenticated but missing role | **Authorization** denies | Not a conversion error |

Some built-in converters/frameworks have specific rules for unsuitable headers or broken tokens; when using them, follow their specific contract and actual exception mapping rather than mechanically forcing every case.

### 3.2. Never Self-Elevate Authentication Status in a Converter

Wrong:

~~~java
// WRONG: reads client-sent username and treats it as already authenticated.
return Mono.just(
        UsernamePasswordAuthenticationToken.authenticated(
                username, null, List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))));
~~~

An attacker could simply send `username=admin`; if the converter self-grants `ROLE_ADMIN`, the application has **bypassed authentication**.

Correct pattern for a username/password request:

~~~java
return Mono.just(
        UsernamePasswordAuthenticationToken.unauthenticated(
                username, rawPassword));
~~~

`rawPassword` is then processed by the manager. In production, the manager must compare against a password hash using an appropriate `PasswordEncoder`, control failed logins, and avoid storing/logging sensitive data. With JWT, the converter usually builds a token representing the Bearer credential, while signature/claims verification and authority conversion belong to the authentication component.

### 3.3. `Mono.empty()` vs `Mono.just(null)`

Never use `Mono.just(null)`: Reactor does not allow `null` values in `Mono.just`. When there are no credentials, use `Mono.empty()`. When an authentication error needs to be signaled, use `Mono.error(...)`.

## 4. Built-in Converters and When Not to Write Your Own

Spring Security Reactive provides converters for common mechanisms, depending on version and dependencies:

| Converter | Kind of input read from request | Notes |
| --- | --- | --- |
| `ServerHttpBasicAuthenticationConverter` | `Authorization: Basic ...` | Converts username/password pairs per HTTP Basic |
| `ServerBearerTokenAuthenticationConverter` | Bearer token from HTTP request | Converts token into an authentication request; the converter itself does not prove the JWT is valid |
| `ServerFormLoginAuthenticationConverter` | Login form data | Suitable for form-login flows with CSRF/session mechanisms when needed |
| `ServerX509AuthenticationConverter` | Client certificate info in an SSL/TLS exchange | Requires proper TLS configuration and certificate identity verification |
| `DelegatingServerAuthenticationConverter` | Tries multiple converters in order | Avoid scheme conflicts or accidentally swallowing errors |

In OAuth2 Resource Server, you typically configure `oauth2ResourceServer(...jwt(...))` or opaque token using the Spring Security model, and do **not** parse JWTs manually in a controller or converter. Dedicated components handle validation and authority mapping. Basic/form-login configurations also usually register the appropriate converter inside the security filter chain.

**When is a custom converter needed?** When an API has an explicitly required custom credential scheme, or needs to convert a specialized input into an authentication request token that a manager understands. Before creating a new scheme in a real product, check whether HTTP Basic, OAuth2/OIDC, mTLS, or a built-in standard can be used.

`ServerAuthenticationConverter` in WebFlux is not Servlet's `AuthenticationConverter`. Correspondence:
- WebFlux: `ServerWebExchange`, `Mono<Authentication>`, `AuthenticationWebFilter`, `ReactiveAuthenticationManager`.
- Servlet: `HttpServletRequest` and corresponding `Filter`/`AuthenticationManager` components.

## 5. Handling HTTP Requests Properly

A converter typically reads `exchange.getRequest().getHeaders()`, `getCookies()`, query parameters, or TLS metadata. Key principles:

1. **Identify trusted sources accurately.** A client-supplied `X-User` header does not prove identity; if reverse-proxy infrastructure authenticates and injects user info into a header, you must ensure the proxy strips/overwrites external headers and enforces the trust boundary. Never trust self-declared user headers as authentication.
2. **Check for scheme indicators first.** Absence of credentials meant for the current converter should return `Mono.empty()` so other mechanisms or authorization can proceed.
3. **If the scheme is recognized but malformed, reject explicitly.** Do not use a fallback that lets the request proceed as anonymous when it is attempting to log in with invalid credentials.
4. **Validate format and size limits.** Avoid unchecked string splitting, oversized headers, invalid characters, or repeated values.
5. **Do not log secrets.** Even while merely parsing, tokens/passwords are sensitive data; do not put them into logs, metrics labels, or exception messages returned to clients.
6. **Do not block the event loop.** Converters must return `Mono`; if I/O is involved, use reactive APIs. Never call `block()` or `subscribe()` inside a converter.
7. **Do not self-grant authorities.** Providing an `Authentication` to send to the manager is enough; the authenticated result must be produced by the trusted verification step.
8. **Read the request body carefully.** WebFlux's request body is a data stream; consuming `getBody()` yourself can prevent downstream from reading it again. Prefer supported form converters/codecs, or use an approach that guarantees single body reads, size bounds, and memory control.

No single converter has to do all of these at once. A good converter is usually **small, easy to test, and responsible solely for format conversion**.

## 6. Runnable Example: A Converter Reading Two Learning Headers

This example uses Java 17, Spring Boot 3.3.13 (Spring Security 6.x line), and Gradle. We define a **learning-only** scheme:

~~~text
X-Learn-User: learner
X-Learn-Key: local-pass
~~~

The structural validity rule is **having exactly one non-blank value for each header**. The converter simply turns them into an unauthenticated token. The demo manager has two hard-coded accounts so you can distinguish authentication from authorization:

- `learner / local-pass` → `ROLE_USER`.
- `admin / admin-pass` → `ROLE_ADMIN`.

**Never apply this scheme directly to production.** It does not follow a standard authentication protocol, uses simple hard-coded credentials, and lacks password hashing, rotation, rate limiting, TLS termination, account lockout, and security auditing. Do not use these names/values as real secrets.

Structure:

~~~text
converter-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── DemoApplication.java
    │   ├── DemoHeaderAuthenticationConverter.java
    │   ├── SecurityConfig.java
    │   └── ApiController.java
    └── test/java/demo/
        └── DemoHeaderAuthenticationConverterTest.java
~~~

### 6.1. Gradle Configuration

`settings.gradle`:

~~~groovy
rootProject.name = 'converter-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot manages Spring WebFlux/Spring Security/Reactor library versions compatible with the chosen Boot version. For a real project, pick a supported branch with your organization's latest security patches; do not treat the illustrative version as a long-term operational recommendation.

### 6.2. Startup Application

`src/main/java/demo/DemoApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 6.3. Converter: Only Extracts and Creates an Unauthenticated Token

`src/main/java/demo/DemoHeaderAuthenticationConverter.java`:

~~~java
package demo;

import java.util.List;

import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.server.authentication.ServerAuthenticationConverter;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

public final class DemoHeaderAuthenticationConverter
        implements ServerAuthenticationConverter {

    private static final String USER_HEADER = "X-Learn-User";
    private static final String KEY_HEADER = "X-Learn-Key";

    @Override
    public Mono<Authentication> convert(ServerWebExchange exchange) {
        List<String> users = exchange.getRequest()
                .getHeaders().getOrEmpty(USER_HEADER);
        List<String> keys = exchange.getRequest()
                .getHeaders().getOrEmpty(KEY_HEADER);

        // Both headers are absent: this mechanism does not perform authentication.
        if (users.isEmpty() && keys.isEmpty()) {
            return Mono.empty();
        }

        // Signs of login present, but missing, duplicate, or blank data.
        if (users.size() != 1 || keys.size() != 1
                || users.get(0).isBlank() || keys.get(0).isBlank()) {
            return Mono.error(
                    new BadCredentialsException("Invalid demo headers"));
        }

        String username = users.get(0);
        String password = keys.get(0);

        // Candidate only; the manager will verify in the next step.
        Authentication candidate =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        username, password);
        return Mono.just(candidate);
    }
}
~~~

**Important line-by-line analysis:**
- `getOrEmpty` handles completely missing headers without hitting a `NullPointerException`.
- If both headers are absent, `Mono.empty()` signals **no authentication attempt** from the converter.
- If only one header appears, or there are multiple values, or empty/whitespace strings, `BadCredentialsException` reports a malformed payload.
- If a structurally valid header pair is present, the converter creates `UsernamePasswordAuthenticationToken.unauthenticated`, **without** querying a database or deciding password correctness.
- This is an introductory-level header-handling example; a real product must have size-limit strategies, header-smuggling defenses, proxy trust controls, and properly designed standard authentication.

### 6.4. ReactiveAuthenticationManager + AuthenticationWebFilter

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.SecurityWebFiltersOrder;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.AuthenticationWebFilter;
import org.springframework.security.web.server.authentication.HttpStatusServerEntryPoint;
import org.springframework.security.web.server.authentication.ServerAuthenticationEntryPointFailureHandler;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

import reactor.core.publisher.Mono;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    ReactiveAuthenticationManager demoAuthenticationManager() {
        return authentication -> Mono.defer(() -> {
            String user = authentication.getName();
            String password = String.valueOf(authentication.getCredentials());

            if ("learner".equals(user) && "local-pass".equals(password)) {
                return Mono.just(
                        UsernamePasswordAuthenticationToken.authenticated(
                                user, null,
                                List.of(new SimpleGrantedAuthority("ROLE_USER"))));
            }

            if ("admin".equals(user) && "admin-pass".equals(password)) {
                return Mono.just(
                        UsernamePasswordAuthenticationToken.authenticated(
                                user, null,
                                List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))));
            }

            return Mono.error(
                    new BadCredentialsException("Invalid demo credentials"));
        });
    }

    @Bean
    SecurityWebFilterChain securityFilterChain(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager demoAuthenticationManager) {

        AuthenticationWebFilter demoFilter =
                new AuthenticationWebFilter(demoAuthenticationManager);

        demoFilter.setServerAuthenticationConverter(
                new DemoHeaderAuthenticationConverter());

        demoFilter.setRequiresAuthenticationMatcher(
                ServerWebExchangeMatchers.pathMatchers("/api/**"));

        demoFilter.setSecurityContextRepository(
                NoOpServerSecurityContextRepository.getInstance());

        HttpStatusServerEntryPoint unauthorized =
                new HttpStatusServerEntryPoint(HttpStatus.UNAUTHORIZED);

        demoFilter.setAuthenticationFailureHandler(
                new ServerAuthenticationEntryPointFailureHandler(unauthorized));

        return http
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance())
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/api/public").permitAll()
                        .pathMatchers("/api/admin").hasRole("ADMIN")
                        .anyExchange().authenticated())
                .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .exceptionHandling(exceptions -> exceptions
                        .authenticationEntryPoint(unauthorized))
                .addFilterAt(demoFilter, SecurityWebFiltersOrder.AUTHENTICATION)
                .build();
    }
}
~~~

**Why each part is necessary:**

1. **The Manager** receives credentials from the candidate, checks them against demo accounts, and produces an authenticated token with `ROLE_USER` or `ROLE_ADMIN`; on mismatch it emits `BadCredentialsException`.
2. **`AuthenticationWebFilter`** is the orchestrating filter, not the converter. It invokes the converter first, invokes the manager when a candidate exists, processes the outcome, and supplies successful authentication to the downstream pipeline.
3. **`setRequiresAuthenticationMatcher("/api/**")`** limits which requests this filter inspects. The matcher does not grant access: the rules in `authorizeExchange` decide access.
4. **`setAuthenticationFailureHandler`** returns HTTP 401 when the converter/manager emits an appropriate authentication error. No credential details are returned to the client.
5. **`exceptionHandling(...authenticationEntryPoint(...))`** defines the 401 response when authorization requires authentication and no valid user is found.
6. **`addFilterAt(..., AUTHENTICATION)`** places the custom `AuthenticationWebFilter` at the authentication position of the reactive security chain; this API is for `WebFilter`, not Servlet `Filter`.
7. **No-op SecurityContextRepository** does not persist authentication between requests. Even so, the verified authentication is still attached to the Reactor Context of the **current request**.
8. **`httpBasic`/`formLogin` are disabled** so the demo flow uses only the new converter. If multiple schemes are needed simultaneously, you must design matcher/filter ordering and test for conflicts.
9. **`hasRole("ADMIN")`** checks the `ROLE_ADMIN` authority by convention; the demo manager grants that authority to the admin account.

The configuration intentionally has only GET endpoints, so the example does not disable CSRF. If adding POST/PUT/DELETE or browser auto-sent credentials, you must design CSRF according to the real threat model. This demo scheme is also **not a production authentication solution**.

### 6.5. WebFlux Controller

`src/main/java/demo/ApiController.java`:

~~~java
package demo;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/api/public")
    public Mono<String> publicEndpoint() {
        return Mono.just("public");
    }

    @GetMapping("/api/me")
    public Mono<String> currentUser() {
        return ReactiveSecurityContextHolder.getContext()
                .map(context -> "user:"
                        + context.getAuthentication().getName());
    }

    @GetMapping("/api/admin")
    public Mono<String> adminEndpoint() {
        return Mono.just("admin-only");
    }
}
~~~

`/api/me` reads the verified `Authentication` from `ReactiveSecurityContextHolder`. If the converter creates a token but the manager fails, the handler must not return `user:...`. Do not use Servlet-style thread-local `SecurityContextHolder` and do not call `block()` in the controller.

### 6.6. Running and Checking with curl

From inside the project directory, with JDK 17 and compatible Gradle. Run:

~~~bash
gradle bootRun
~~~

If Gradle Wrapper is present, you can run `./gradlew bootRun`. In another terminal:

~~~bash
# No credentials needed on the public endpoint.
curl -i http://localhost:8080/api/public

# No authentication headers at all.
curl -i http://localhost:8080/api/me

# Valid header pair: learner account.
curl -i   -H 'X-Learn-User: learner'   -H 'X-Learn-Key: local-pass'   http://localhost:8080/api/me

# Username present but missing secret.
curl -i -H 'X-Learn-User: learner'   http://localhost:8080/api/me

# Both headers present but wrong secret.
curl -i   -H 'X-Learn-User: learner'   -H 'X-Learn-Key: wrong'   http://localhost:8080/api/me

# Authenticated but insufficient role.
curl -i   -H 'X-Learn-User: learner'   -H 'X-Learn-Key: local-pass'   http://localhost:8080/api/admin

# Sufficient ADMIN role.
curl -i   -H 'X-Learn-User: admin'   -H 'X-Learn-Key: admin-pass'   http://localhost:8080/api/admin
~~~

**Expected results:**

| Request | Converter | Manager / Authorization | HTTP |
| --- | --- | --- | --- |
| `/api/public`, no headers | `Mono.empty()` | Route allows anonymous | **200**, body `public` |
| `/api/me`, no headers | `Mono.empty()` | Authorization requires login | **401** |
| `/api/me`, `learner/local-pass` | Unauthenticated candidate | Manager verifies USER | **200**, body `user:learner` |
| `/api/me`, missing key | `BadCredentialsException` | Failure handler | **401** |
| `/api/me`, wrong key | Syntactically valid candidate | Manager rejects | **401** |
| `/api/admin`, `learner/local-pass` | Candidate | USER lacks `ROLE_ADMIN` | **403** |
| `/api/admin`, `admin/admin-pass` | Candidate | ADMIN has sufficient authority | **200**, body `admin-only` |

Error responses may have different bodies/headers depending on configuration/version; the table pins down **the status and body of the success cases**. With real APIs, avoid passing demo secrets on shared terminals or storing them in shell history.

### 6.7. Why Does the Example Have Both 401 and 403?

- **401 Unauthorized:** no suitable credentials were present or authentication failed. Here the API entry point/failure handler explicitly uses HTTP 401.
- **403 Forbidden:** the manager verified the identity, but authorization does not grant `ADMIN` permission.

If you change the converter into a function that always returns a token with `ROLE_ADMIN` and `isAuthenticated=true`, you have accidentally bypassed the verification step; that is a security flaw, not a faster way to write a converter.

## 7. Standalone Unit Tests for the Converter

A converter should be tested **separately from the manager**. This lets you prove it only parses requests and returns an authentication candidate, while the manager verifies passwords. The test below uses `MockServerWebExchange`, JUnit 5, and Reactor `StepVerifier`.

`src/test/java/demo/DemoHeaderAuthenticationConverterTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class DemoHeaderAuthenticationConverterTest {

    private final DemoHeaderAuthenticationConverter converter =
            new DemoHeaderAuthenticationConverter();

    @Test
    void missingHeadersMeanNoAuthenticationAttempt() {
        var exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get("/api/me"));

        StepVerifier.create(converter.convert(exchange))
                .verifyComplete();
    }

    @Test
    void validShapeProducesUnauthenticatedCandidate() {
        var exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get("/api/me")
                        .header("X-Learn-User", "learner")
                        .header("X-Learn-Key", "local-pass"));

        StepVerifier.create(converter.convert(exchange))
                .assertNext(authentication -> {
                    assertEquals("learner", authentication.getName());
                    assertEquals("local-pass",
                            authentication.getCredentials());
                    assertFalse(authentication.isAuthenticated());
                })
                .verifyComplete();
    }

    @Test
    void partialHeadersAreRejected() {
        var exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get("/api/me")
                        .header("X-Learn-User", "learner"));

        StepVerifier.create(converter.convert(exchange))
                .expectError(BadCredentialsException.class)
                .verify();
    }
}
~~~

Run:

~~~bash
gradle test
~~~

**Expectation:** all three tests pass if files, classes, and dependencies are created exactly as in the example. This is a prediction based on the source code, not a claim that it was run on your machine.

The second test is especially important: `assertFalse(authentication.isAuthenticated())` guards against the risk of the converter self-verifying the user. The first test proves no credentials emit a **completion without items**. The third test proves a request with authentication signals but missing info is not silently ignored.

To test **`SecurityWebFilterChain` integration**, add WebFlux tests via `WebTestClient` covering the 200, 401, and 403 cases above. Unit tests only test the converter; they do not prove the filter is registered in the right order or that the manager has the right logic.

## 8. What Does AuthenticationWebFilter Coordinate?

For a request matching `setRequiresAuthenticationMatcher`, `AuthenticationWebFilter` conceptually:

1. Calls the converter to obtain an `Authentication` candidate.
2. If the converter returns `Mono.empty()`, does not attempt authentication with this filter; lets the request proceed through the chain.
3. If the converter emits a candidate, calls `ReactiveAuthenticationManager.authenticate(authentication)`.
4. If the manager authenticates successfully, Spring Security places Authentication/Context into the request's reactive stream, runs the success handler, and continues the chain.
5. If the converter or manager emits an `AuthenticationException` handled per the contract, calls the failure handler. Exact output depends on configuration, entry point, and exception type; system errors are not necessarily client credential errors.
6. Authorization runs at the appropriate part of the chain, deciding whether access to the resource is allowed.

**Extension points:** `setServerAuthenticationConverter`, `setRequiresAuthenticationMatcher`, `setAuthenticationSuccessHandler`, `setAuthenticationFailureHandler`, `setSecurityContextRepository`. You can use a manager resolver if each request needs to select a different manager mechanism by policy, but do not mix multiple custom filters/managers arbitrarily when the framework already supports a built-in scheme.

Differences between signals:

| Signal | Meaning to the filter |
| --- | --- |
| Converter `Mono.empty()` | Skip this filter's authentication attempt |
| Converter `Mono.just(candidate)` | Attempt authentication with the manager |
| Converter `Mono.error(BadCredentialsException)` | Handle as an appropriate authentication error |
| Manager `Mono.just(verified)` | Authentication succeeded, can proceed to authorization |
| Manager `Mono.error(BadCredentialsException)` | Invalid credential |
| Manager `Mono.empty()` | Manager did not provide an authentication result; exact behavior depends on manager/filter |
| Authorization denies | Caller is not allowed access, even though conversion may have succeeded |

In production, do not rely on a converter to enforce business authorization rules such as "does this order belong to this user"; those checks belong in authorization/services after the identity has been verified.

## 9. Mono.empty(), Syntax Errors, and Multiple Authentication Schemes

Suppose an API supports both Basic and Bearer. When a request carries `Authorization: Bearer ...`, a Basic converter needs to recognize that it **does not belong to its mechanism** and can return `Mono.empty()`. A dedicated Bearer converter receives that request and turns it into the appropriate token. If the Bearer scheme is present but the token is malformed, the corresponding converter/manager must reject properly; do not intentionally treat it as "no credentials" just to allow a less secure fallback.

A composite converter like `DelegatingServerAuthenticationConverter` can try multiple delegates, but you must understand how it stops on a result, continues on empty, and handles errors. Converter order can affect outcomes. With multiple `AuthenticationWebFilter`s, control matcher, authentication order, and failure handling for each filter.

**Pay special attention to dangerous fallbacks:**

~~~java
// Security WRONG if every malformed token is turned into "no information".
return parseBearer(exchange)
        .onErrorResume(error -> Mono.empty());
~~~

This approach even swallows unexpected errors. A malformed token might be ignored, allowing another mechanism or a public rule to process the request unexpectedly. Distinguish `Mono.empty()` when the scheme is absent, `AuthenticationException` when the scheme was recognized but credentials are bad, and infrastructure errors when authentication cannot be performed.

## 10. Request Body, Login Forms, and Asynchronous Data Sources

Many login APIs accept a JSON body such as:

~~~json
{
  "username": "learner",
  "password": "local-pass"
}
~~~

Technically, a converter can read the request body asynchronously and create an authentication candidate. However, in WebFlux, the body is a `Flux<DataBuffer>` with its own consumption lifecycle; never call `block()` to get JSON, never arbitrarily subscribe a second time, and never assume the body will automatically remain available downstream.

If using form login, prefer the mechanisms already provided by Spring Security. For a JSON login that truly needs customization, you should:
- Restrict request method/path/content type/size before parsing.
- Use an appropriate reactive codec/decoder and validate the payload.
- Avoid keeping the password in logs or overly long-lived state.
- Design the body to be read **once**, and if downstream needs to read it again, use a safe, size-bounded caching/decorating mechanism.
- Configure CSRF/CORS and cookie handling based on client type and how credentials are sent.

**Common trap:** the converter reads the whole body in one subscription, while the controller tries to read the body a second time; the result may be empty or fail because the body has already been consumed. Simply "switching from `block()` to `flatMap`" does not fix consuming the body twice.

## 11. Reactor Context, Sessions, and Principal Visibility

In WebFlux, after authentication succeeds, downstream code typically reads the context with:

~~~java
return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication().getName());
~~~

It depends on the Reactor Context of the running subscription, not Servlet's default `ThreadLocal`. Switching schedulers with `publishOn` or `subscribeOn` inside **the same pipeline** does not by default lose the Reactor Context.

However, a converter/service calling `subscribe()` itself can create an independent subscription that is not guaranteed to carry the request context and loses proper error/cancellation flow. Wrong example:

~~~java
converter.convert(exchange).subscribe(candidate -> {
    // WRONG: performing authentication yourself outside the security filter chain.
    audit(candidate);
});
return Mono.empty();
~~~

This snippet illustrates an anti-pattern, not a standalone program; `audit` is a hypothetical function. Let `AuthenticationWebFilter` manage subscription and authentication results, or compose necessary operations into the main chain's publisher.

**Saving `SecurityContext` differs from converting:** `ServerSecurityContextRepository` decides how authentication is loaded/saved across requests. The demo uses `NoOpServerSecurityContextRepository` because each request must resend the headers. That does not prevent `ReactiveSecurityContextHolder` from seeing the current request's authentication. If implementing login sessions (WebSession) or interactive OAuth2 login, design persistence appropriately and do not arbitrarily use no-op.

## 12. Ordering, Matchers, and HTTP Errors

In Spring Security Reactive, `SecurityWebFilterChain` can contain many filters. `SecurityWebFiltersOrder.AUTHENTICATION` defines the position reserved for authentication. When an application has multiple chains, `securityMatcher` and `@Order` on the chains decide which chain applies to a request.

Distinguish:
- **Filter matcher:** should this specific authentication filter try converting this request?
- **Security chain matcher:** which security chain is selected for the request?
- **Authorization rule:** after authentication, what permissions does the route require?
- **Failure handler:** how is a failed authentication attempt expressed as an HTTP response?
- **Authentication entry point:** when authentication is required and no valid identity exists yet, how should it respond?

If `/api/me` returns 401 despite sending valid headers, check not only the converter, but also the manager, filter registration, chain matcher, path matcher, filter order, exception handling, and context propagation.

If `/api/admin` returns 403 for the learner account, that is **expected** when the manager grants `ROLE_USER` while the URL requires `ROLE_ADMIN`. Do not relax `permitAll()` or add `ROLE_ADMIN` in the converter to "fix" a 403.

## 13. Common Mistakes to Avoid

| Mistake | Consequence | Right approach |
| --- | --- | --- |
| Converter sets `isAuthenticated=true` itself | Trusts client-declared info, skips verification | Create an unauthenticated token, let the manager verify |
| Returning `Mono.empty()` for all parse errors | Invalid credentials silently ignored | Only return empty when scheme is absent; use AuthenticationException if recognized but invalid |
| Manager also performs HTTP parsing | Tightly couples authentication to WebFlux requests, hard to reuse | Converter parses request, manager verifies token |
| Converter calls blocking DB on event loop | Reduces throughput or causes blocking errors | Reactive I/O; isolate legacy blocking properly if irreplaceable |
| Converter calls `block()`/`subscribe()` itself | Subscription/context/cancellation are no longer coordinated | Return `Mono` to the framework |
| Trusting client-sent `X-User` directly | Easy user spoofing | Use verifiable credentials or a tightly locked-down trusted proxy mechanism |
| Reading body twice | Empty body or errors, memory leaks from improper caching | Reactive decoder and single-consumption management |
| Mixing up authorization with authentication | Insufficient role checks, or granting roles in converter | Grant authorities only after verification; check permissions in authorization |
| Using Servlet `AuthenticationConverter` in WebFlux | Incompatible request/filter APIs | Use `ServerAuthenticationConverter` and `AuthenticationWebFilter` |
| Treating 401 and 403 as the same | Debugging the wrong layer | 401 usually means authentication; 403 usually means logged in but lacking permission |
| Testing `/api/me` only with valid credentials | Misses bypasses and malformed-payload cases | Test anonymous, missing/duplicate/malformed, wrong password, wrong role |
| Putting secrets into logs/exceptions | Credential leakage | Log error codes and correlation IDs, never raw credentials |

## 14. Self-Check Questions

1. Which object does `ServerAuthenticationConverter.convert(exchange)` receive and which Publisher type does it return?
2. Does `Mono.empty()` mean the request is authenticated and allowed? Who handles the access decision afterwards?
3. When sending `X-Learn-User` without `X-Learn-Key`, what does the demo return? When both headers are present with a wrong key, which step detects it?
4. Why is `UsernamePasswordAuthenticationToken.unauthenticated` more appropriate than an `authenticated` token when the converter only reads headers?
5. How do `AuthenticationWebFilter`, `ReactiveAuthenticationManager`, and `ReactiveSecurityContextHolder` differ in responsibility?
6. If a public endpoint has a bad login header and the filter still runs on that route, should you assume the result is 200 because of the `permitAll()` rule? Why?
7. When is `DelegatingServerAuthenticationConverter` needed? How do you avoid one scheme swallowing another scheme's errors?
8. Why is using Resource Server's built-in JWT converter usually safer and easier to maintain than parsing tokens manually in a controller?
9. In what case should you use `Mono.error(BadCredentialsException)` instead of `Mono.empty()`?
10. Why must a converter reading a JSON body manage body consumption and payload size?

**Brief suggested answers:** (1) `ServerWebExchange` → `Mono<Authentication>`; (2) no, it only skips the converter's attempt; authorization/entry point can still deny; (3) the converter signals an error for missing key, the manager rejects the wrong key; (4) the converter has not verified identity; (5) filter orchestrates, manager verifies, holder provides context in Reactor; (6) no, bad credentials can trigger the failure handler even if the endpoint has a public rule; (7) multiple schemes need clear ordering and error policies; (8) standard libraries handle validation/claims/key rotation per configuration; (9) scheme indicator present but payload malformed; (10) body is a reactive stream that gets consumed and risks memory leaks if cached arbitrarily.

## 15. Takeaways

**`ServerAuthenticationConverter` only turns HTTP request data into an authentication request; it does not prove identity.** A Spring Security Reactive pipeline has clear boundaries:

~~~text
ServerWebExchange
     -> ServerAuthenticationConverter
     -> unauthenticated Authentication
     -> ReactiveAuthenticationManager
     -> verified Authentication
     -> Reactor SecurityContext
     -> Authorization
     -> WebFlux handler
~~~

Use `Mono.empty()` when the scheme is absent; `AuthenticationException` when recognized credentials are invalid; let the manager verify and grant authorities; let `AuthenticationWebFilter` manage subscription/success/failure; and test all of 200, 401, and 403. This is the foundation for safely extending to Basic, JWT Bearer, form login, or other mechanisms in WebFlux.

### Official Documentation

- Spring Security — `ServerAuthenticationConverter` Javadoc: https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/web/server/authentication/ServerAuthenticationConverter.html
- Spring Security — `AuthenticationWebFilter` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html
- Spring Security — `ServerHttpSecurity` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Security — `ServerWebExchangeMatchers` Javadoc: https://docs.spring.io/spring-security/site/docs/6.3.4/api/org/springframework/security/web/server/util/matcher/ServerWebExchangeMatchers.html
- Spring Security — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Project Reactor — Context: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html