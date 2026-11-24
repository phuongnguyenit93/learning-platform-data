# Distinguishing Absent, Unsupported, and Invalid Credentials in Reactive Authentication

## 1. Three Distinct States

In a **Spring WebFlux + Spring Security reactive** application, an unauthenticated HTTP request does not necessarily have a "wrong password". You need to distinguish:

- **Absent:** the request does not carry the credentials a filter is looking for, for example no `Authorization` header.
- **Unsupported credential or mechanism:** data is present, but not of a type handled by the current converter or authentication manager—for example a Basic converter seeing a Bearer header, or a manager that only handles `UsernamePasswordAuthenticationToken` receiving a different Java token type.
- **Invalid:** the mechanism was recognized and verification of the credentials was attempted, yet rejected—for example wrong password, expired JWT, invalid token signature, or locked account.

**Important consequence:** all three cases may end up returning HTTP 401 on a route requiring login, yet they mean very different things for the Reactor flow, security, logging, and trying a subsequent authentication method.

The objective of this lesson is to explain `Mono.empty()`, `Mono.error(...)`, and `Mono.just(authentication)` accurately at both system boundaries, create a runnable Java 17+ example, and apply this to HTTP Basic, JWT/Bearer, and multi-manager setups.

## 2. Decision Points: Converter and Manager

~~~text
Client HTTP request
    |
    v
WebFlux SecurityWebFilterChain
    |
    v
AuthenticationWebFilter
    |
    +-- requiresAuthenticationMatcher does not match
    |     -> do not attempt authentication, continue WebFilterChain
    |
    v
ServerAuthenticationConverter.convert(exchange)
    |
    +-- Mono.empty()
    |     -> do not create an Authentication for this filter
    |
    +-- Mono.error(...)
    |     -> error detected while converting credentials
    |
    +-- Mono.just(unauthenticated Authentication token)
          |
          v
ReactiveAuthenticationManager.authenticate(token)
          |
          +-- Mono.empty()
          |     -> manager has no conclusion / unsupported token type
          |
          +-- Mono.error(AuthenticationException)
          |     -> authentication failed
          |
          +-- Mono.just(authenticated Authentication)
                -> succeeded, provides SecurityContext for the Reactor chain
    |
    v
Authorization: permitAll, authenticated, hasRole, ...
~~~

The two core interfaces have nearly identical signatures:

~~~java
// Abridged signatures, not full source:
Mono<Authentication> convert(ServerWebExchange exchange);
Mono<Authentication> authenticate(Authentication authentication);
~~~

However, **empty from the converter** means the filter has no authentication attempt to proceed with; per the `AuthenticationWebFilter` documentation, the filter skips authentication and continues the chain. **Empty from the manager** means an Authentication object was passed to the manager, yet the manager **could not determine** a result. This is useful so another manager can handle it if a delegation mechanism is configured.

There is no rule saying "every `Mono.empty()` means wrong password". Nor may empty be treated as authenticated success. You must check **which layer** the publisher comes from.

## 3. Case A: Absent Credentials

For example, an HTTP request without an Authorization header:

~~~http
GET /private HTTP/1.1
Host: localhost:8080
Accept: text/plain
~~~

If the application configures HTTP Basic, `ServerHttpBasicAuthenticationConverter` receives no Basic data to convert into a token. With a converter that skips missing input, the result is `Mono.empty()`, and `AuthenticationWebFilter` does not invoke the manager for that request.

**Whether the request is blocked depends on authorization.**

| Route | Security rule | Typical behavior when credentials are absent |
| --- | --- | --- |
| `GET /public` | `permitAll()` | HTTP 200 if the handler succeeds |
| `GET /private` | `authenticated()` | HTTP 401 via HTTP Basic entry point |
| `GET /admin` | `hasRole("ADMIN")` | Unauthenticated; typically prompted to log in |

With form login, the server may redirect to the login page instead of HTTP 401. With a Bearer resource server, the response/challenge may differ. A request sending no credentials is **not automatically an error** if the route is public.

**Anonymous does not mean logged in either.** Spring Security may use `AnonymousAuthenticationToken` to represent a request without a real identity; do not infer "authenticated" merely because an Authentication object exists. `authenticated()` enforces trust semantics, not simply `authentication != null`.

In a multi-mechanism application, lacking a Bearer token does not mean lacking a valid session cookie. Therefore, "absent credentials" is always a statement **relative to a specific filter/matcher**.

Snippet detecting missing input in a converter:

~~~java
ServerAuthenticationConverter converter = exchange -> {
    String header = exchange.getRequest()
            .getHeaders().getFirst("Authorization");
    if (header == null || header.isBlank()) {
        return Mono.empty(); // This filter does not attempt authentication
    }
    // Parse branch for the supported scheme...
    return Mono.empty();
};
~~~

This is a **non-standalone illustrative snippet** with a final branch to show flow, not a complete production converter. You need to import `ServerAuthenticationConverter` and `reactor.core.publisher.Mono`.

## 4. Case B: Unsupported Credential or Authentication Type

### 4.1. Unsupported Scheme in Converter

Example:

~~~http
GET /private HTTP/1.1
Host: localhost:8080
Authorization: Bearer example-token
~~~

If the application only configures HTTP Basic, the Basic converter **is not responsible for the Bearer scheme**. It can skip it with `Mono.empty()`. If there is no other Bearer filter and the route requires authentication, the client still normally receives HTTP 401.

**You cannot conclude from this situation that the JWT has a bad signature or is expired**, because the Bearer token has not been checked by a corresponding decoder. In an application supporting multiple mechanisms, having the Basic filter ignore Bearer is normal so that the Bearer filter can attempt authentication. If an API allows only one scheme, you can also design a policy rejecting unknown schemes, provided parser, matcher, filter, and entry point are consistent.

### 4.2. Unsupported Authentication Object Type in Manager

`ReactiveAuthenticationManager` receives a **Java object** such as `UsernamePasswordAuthenticationToken`, `BearerTokenAuthenticationToken`, or a custom token. A manager supporting only username/password may receive `TestingAuthenticationToken` and **reach no conclusion**:

~~~java
ReactiveAuthenticationManager manager = request -> {
    if (!(request instanceof UsernamePasswordAuthenticationToken)) {
        return Mono.empty();
    }
    // The manager is responsible for verifying username/password below.
    return Mono.error(new BadCredentialsException("Invalid credentials"));
};
~~~

This snippet is **not yet a valid manager for a real application**: the final branch intentionally simulates an error just to show how token types are separated. Distinguish clearly:

- `Authorization: Bearer ...` is the credential format over HTTP.
- `UsernamePasswordAuthenticationToken` is the Java class representing the authentication request/result.
- The **converter** chooses how to read the HTTP request.
- The **manager** decides whether it supports the converted token type and verifies credentials.

### 4.3. Multiple Managers and Fallbacks

`DelegatingReactiveAuthenticationManager` can hold multiple managers. A manager returning empty for an unsupported token lets subsequent delegates proceed. However, a manager returning `Mono.error(...)` after checking credentials and failing is **not like empty**: by default a delegating manager does not proceed to the next delegate after an error.

Some versions have `setContinueOnError(boolean)`, yet you should not reflexively enable "keep trying even on wrong password". That can weaken lockout controls, rate limits, or allow login data to be sent to a different provider. **Route by scheme/token type** rather than blindly trying every backend.

An authentication service losing connectivity, a database timeout, or a JWK endpoint going down is also not automatically unsupported. Those are infrastructure errors needing separate handling and monitoring.

## 5. Case C: Supported, Yet Invalid Credentials

Once the converter has recognized the scheme and created a token, the manager may determine the credentials are wrong. Examples:

- Password mismatch even though HTTP Basic parsed cleanly.
- Structurally valid JWT with invalid signature, expired timestamp, or unacceptable issuer/audience.
- Account disabled/locked if the manager has status data.
- Wrong, expired, or already-used OTP in an OTP-enabled system.

The signal inside a manager is typically `Mono.error(AuthenticationException)`, using subtypes such as `BadCredentialsException`, `LockedException`, `DisabledException`, or a token-specific exception. Example code branch:

~~~java
if (!validCredentials) {
    return Mono.error(new BadCredentialsException("Invalid credentials"));
}
~~~

`validCredentials` is an illustrative variable; this is **not a standalone Java class**. Crucially, **never turn a wrong password into `Mono.empty()`**: that behavior hides a rejected authentication attempt.

### 5.1. Structural Errors vs Value Errors

An `Authorization: Basic ???` header may fail Base64 decoding. That malformed error can occur in the converter and never reach the manager. A Basic header that parses, yet has the wrong user/password, is typically rejected by the manager.

Similarly, do not lump all Bearer failures into one cause: blank token, malformed format, unverifiable signature, and mismatched issuer can arise at different stages. All must be handled safely; do not invent an invariant exception class across all versions or configurations.

**Keep returned messages sufficiently generic.** Avoid letting responses reveal whether a username exists or whether the password was right or wrong. Security logs should only record event types/correlation IDs, never raw passwords, tokens, session cookies, or API keys.

## 6. Comparison Table of Reactive Values and HTTP

| Situation | Decision point | Typical publisher | Meaning |
| --- | --- | --- | --- |
| No Authorization header for Basic | Converter | `Mono.empty()` | No authentication attempt created |
| Bearer header entering Basic converter | Converter | Usually `Mono.empty()` | Scheme outside this filter's scope |
| Username/password manager receives another Authentication type | Manager | `Mono.empty()` | No conclusion / unsupported |
| Wrong username/password | Manager | `Mono.error(BadCredentialsException)` | Authentication failed |
| Checked token is expired/invalid signature | Decoder/manager | Appropriate error | Invalid credentials |
| Correct username/password | Manager | `Mono.just(authenticated)` | Authentication succeeded |

Missing header, unsupported scheme, and wrong password can all appear as HTTP 401 on a private endpoint using HTTP Basic. **The status code alone cannot distinguish internal paths.** HTTP 403 is usually a different story: the principal is authenticated, yet **authorization denied access**.

## 7. Runnable Spring Boot WebFlux Example with Java 17+

The example has two parts. The HTTP API demonstrates `/public`, `/private`, and Basic authentication outcomes; a `CommandLineRunner` calls the manager directly once to show concretely **unsupported type → empty**, **wrong password → error**, and **correct password → success**.

### 7.1. Maven Configuration

Create a project on [Spring Initializr](https://start.spring.io/) with Java 17+, Maven, group `com.example`, artifact `auth-states-demo`; add **Spring Reactive Web** and **Spring Security**. Minimal complete `pom.xml` using Boot 4.1.2:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>auth-states-demo</artifactId>
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
~~~

Let the Spring Boot BOM manage Spring Framework, Security, and Reactor versions; do not declare versions per sub-module.

### 7.2. One Complete Java Class

Create `src/main/java/com/example/authstates/AuthStatesDemoApplication.java`:

~~~java
package com.example.authstates;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class AuthStatesDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(AuthStatesDemoApplication.class, args);
    }

    @Bean
    ReactiveAuthenticationManager demoManager() {
        return input -> {
            if (!(input instanceof UsernamePasswordAuthenticationToken)) {
                return Mono.empty();
            }

            boolean userOk = "learner".equals(input.getName());
            boolean passwordOk = "correct".equals(input.getCredentials());
            if (!userOk || !passwordOk) {
                return Mono.error(
                        new BadCredentialsException("Invalid credentials"));
            }

            Authentication result =
                    UsernamePasswordAuthenticationToken.authenticated(
                            "learner", null,
                            List.of(new SimpleGrantedAuthority("ROLE_USER")));
            return Mono.just(result);
        };
    }

    @Bean
    SecurityWebFilterChain security(
            ServerHttpSecurity http, ReactiveAuthenticationManager manager) {
        return http
                .authenticationManager(manager)
                .authorizeExchange(rules -> rules
                        .pathMatchers("/public").permitAll()
                        .pathMatchers("/private").authenticated()
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    @Bean
    CommandLineRunner showOutcomes(ReactiveAuthenticationManager manager) {
        return args -> {
            Authentication unsupported =
                    new TestingAuthenticationToken("learner", "correct");
            Authentication invalid =
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            "learner", "wrong");
            Authentication valid =
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            "learner", "correct");

            System.out.println("UNSUPPORTED_TYPE -> "
                    + observe(manager, unsupported));
            System.out.println("WRONG_PASSWORD -> "
                    + observe(manager, invalid));
            System.out.println("CORRECT_PASSWORD -> "
                    + observe(manager, valid));
        };
    }

    private static String observe(
            ReactiveAuthenticationManager manager, Authentication input) {
        return manager.authenticate(input)
                .map(auth -> "SUCCESS:" + auth.getName())
                .switchIfEmpty(Mono.just("EMPTY"))
                .onErrorResume(BadCredentialsException.class,
                        e -> Mono.just("ERROR:" + e.getClass().getSimpleName()))
                .block();
    }

    @RestController
    static class DemoController {

        @GetMapping("/public")
        Mono<String> publicEndpoint() {
            return Mono.just("PUBLIC_OK");
        }

        @GetMapping("/private")
        Mono<String> privateEndpoint() {
            return ReactiveSecurityContextHolder.getContext()
                    .map(SecurityContext::getAuthentication)
                    .map(Authentication::getName)
                    .map(name -> "PRIVATE_OK:" + name);
        }
    }
}
~~~

The code includes full package, imports, and class. It only demonstrates signals; a manager hard-coding passwords is **not suitable for production**. Real applications must store passwords hashed with a password encoder, use a trusted identity source, HTTPS, timeouts, and monitoring.

`http.authenticationManager(manager)` wires the demo manager into the chain, specifying which mechanism authenticates HTTP Basic. `ReactiveSecurityContextHolder` lets the controller read the user from the Reactor Context.

**Why is `.block()` there?** It is used only inside the `CommandLineRunner` that executes once at startup to convert the probe's result into a printed string; **never use `block()` in a request handler, WebFilter, or manager on the event loop**.

### 7.3. Startup and stdout

In the directory containing `pom.xml`:

~~~bash
./mvnw spring-boot:run
~~~

On Windows use `.\mvnw.cmd spring-boot:run`; if there is no wrapper, use `mvn spring-boot:run`. The three lines printed by `showOutcomes` are:

~~~text
UNSUPPORTED_TYPE -> EMPTY
WRONG_PASSWORD -> ERROR:BadCredentialsException
CORRECT_PASSWORD -> SUCCESS:learner
~~~

Spring Boot startup logs may appear before/after. The probe does **not** simulate an HTTP request missing a header because in that case the converter does not build an Authentication and the manager is never invoked.

### 7.4. Testing HTTP with curl

Open another terminal while the server runs at `http://localhost:8080`:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/private
curl -i -H "Authorization: Bearer some-token" http://localhost:8080/private
curl -i -u learner:wrong http://localhost:8080/private
curl -i -u learner:correct http://localhost:8080/private
~~~

| Request | Typical HTTP status | Body on success | Explanation |
| --- | --- | --- | --- |
| No header, `/public` | 200 | `PUBLIC_OK` | Public route |
| No header, `/private` | 401 | — | No authentication |
| Bearer header, `/private` | 401 | — | Basic converter does not handle Bearer |
| Basic `learner:wrong` | 401 | — | Manager rejects password |
| Basic `learner:correct` | 200 | `PRIVATE_OK:learner` | Authentication succeeded |

401 headers and bodies vary by mechanism/version. You cannot deduce from a 401 response alone whether the converter or the manager emitted an error.

## 8. Custom ServerAuthenticationConverter: Classifying Before Checking

A custom converter can separate states clearly:

~~~java
ServerAuthenticationConverter demoConverter = exchange -> {
    String header = exchange.getRequest()
            .getHeaders().getFirst("Authorization");

    if (header == null || header.isBlank()) {
        return Mono.empty(); // ABSENT
    }
    if (!header.startsWith("Demo ")) {
        return Mono.empty(); // UNSUPPORTED SCHEME for this converter
    }

    String credential = header.substring("Demo ".length()).trim();
    if (credential.isEmpty()) {
        return Mono.error(new BadCredentialsException(
                "Malformed Demo credentials")); // INVALID FORMAT
    }

    return Mono.just(
            UsernamePasswordAuthenticationToken.unauthenticated(
                    "demo", credential));
};
~~~

This is an **illustrative snippet**, without a manager, matcher, failure handler, or HTTP config, so it is not a standalone program. You need to import `ServerAuthenticationConverter`, `UsernamePasswordAuthenticationToken`, `BadCredentialsException`, and `Mono`. The Demo scheme and hard-coded username are only to explain boundaries, not to be used as a real security mechanism.

Four branches:

1. Missing header → do not attempt authentication.
2. Unfamiliar scheme → this converter does not support it; another mechanism can only handle it if configured.
3. Matching scheme but malformed data → signal an error, do not turn into missing.
4. Matching scheme with data → create token for the **manager to verify valid/invalid**.

If an endpoint allows multiple schemes, each converter should ignore schemes outside its responsibility. If an endpoint accepts only one scheme, you can adopt a policy rejecting unknown schemes, provided it is explicit and tested.

## 9. Reactor Operator Mistakes to Avoid

### Swallowing BadCredentialsException into empty

~~~java
// Wrong when the password/token is actually invalid:
return verifyCredential(request)
        .onErrorResume(error -> Mono.empty());
~~~

`verifyCredential` is a hypothetical method. This snippet changes **FAILED** into **UNDETERMINED**; it can trigger unintended fallbacks, skew metrics, and bypass account lockout policies.

### Fabricating an authentication from empty

~~~java
// Wrong: authGuest is a hypothetical variable already marked authenticated.
return manager.authenticate(request)
        .defaultIfEmpty(authGuest);
~~~

Lack of a manager conclusion is **not grounds to grant an identity**. If fail-closed behavior is needed, use a denial policy or configuration error at the appropriate boundary; do not construct a privileged principal.

### Using switchIfEmpty in the Right Situation

You can use `switchIfEmpty(Mono.defer(() -> otherManager.authenticate(request)))` when the first manager does not support the token type and the second delegate has jurisdiction. It handles only **empty**, not **error**. A wrong password in the first manager must not silently turn into success in the second provider.

### Avoiding Blocking I/O on the Event Loop

~~~java
// Wrong: looking up the user synchronously before creating the Mono.
return Mono.just(blockingRepository.findUser(username));
~~~

`blockingRepository` and `username` are hypothetical examples. For database/HTTP auth, use appropriate reactive APIs or isolate blocking libraries on a bounded scheduler; `Mono.just(...)` does not turn a blocking call into a non-blocking one.

## 10. Authentication Result Differs from Authorization

`AuthenticationWebFilter` attempts authentication when the matcher and converter provide input. `ReactiveAuthenticationManager` returns a result/empty/error. `ExceptionTranslationWebFilter` and security handlers handle prompting for login or returning authorization errors downstream, depending on configuration.

- **ABSENT:** anonymous requests can still enter `permitAll` endpoints.
- **UNSUPPORTED:** the current filter neither proves the token right nor wrong; another appropriate mechanism must exist or authorization will demand login.
- **INVALID:** authentication errors from converter/manager must follow the failure path; Basic typically returns 401.
- **SUCCESS:** SecurityContext holds an authenticated principal; authorization can still return 403 if a role is missing.

`permitAll` does not necessarily let a request sending **invalid** credentials through: an authentication filter receiving bad credentials can reject it before URL authorization is checked.

## 11. Testing and Debugging

You should test these cases:

1. Converter receives a request with no header ⇒ `Mono.empty()`.
2. Converter receives another scheme ⇒ empty or error per application policy.
3. Converter receives the matching scheme but malformed ⇒ appropriate error.
4. Manager receives an unsupported Authentication token type ⇒ empty.
5. Manager receives wrong password ⇒ `BadCredentialsException`.
6. Manager receives correct password ⇒ authenticated Authentication with matching authorities.
7. HTTP public route anonymous ⇒ 200; private anonymous ⇒ 401 with Basic.
8. HTTP private with wrong password ⇒ 401; right password ⇒ 200.
9. With multiple managers ⇒ ensure real errors are not converted into unsafe fallbacks.

At the publisher level, use `reactor-test`/`StepVerifier` to verify empty/error/next signals; for WebFlux HTTP APIs, use `WebTestClient` and Spring Security test support.

Logging can be enabled in dev environments:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Categorize logs using internal event codes such as `credential_absent`, `unsupported_scheme`, `unsupported_authentication_type`, `authentication_failed`, and `authentication_success`. Never log passwords, tokens, Basic headers, cookies, or private keys. Use correlation IDs to trace requests across components.

## 12. Self-Check Questions

**Question 1.** The Basic converter returns empty due to a missing Authorization header; did the user enter a wrong password?

**Answer:** No. There was no authentication attempt; the authorization step decides whether anonymous access is allowed on that route.

**Question 2.** A username/password-only manager receives a different token type and returns empty. Is this a successful login?

**Answer:** No. The manager reached no conclusion; a matching delegate may try next if configured, but nobody has authenticated yet.

**Question 3.** Username/password were parsed and the password is wrong; return empty or error?

**Answer:** `Mono.error(new BadCredentialsException(...))` to signal a failed authentication attempt.

**Question 4.** A Bearer header hitting a Basic-only API gets 401. Does that prove the JWT has an invalid signature?

**Answer:** No. The Basic converter does not verify JWT signatures; without a configured Bearer authentication filter, the token was never verified.

**Question 5.** Why can `/public` without a header return 200 while a request sending wrong credentials to the same URL can get 401?

**Answer:** A missing header lets the Basic converter skip it; sending wrong credentials can trigger an authentication failure before `permitAll` at the authorization layer is evaluated.

**Question 6.** Why not use `onErrorResume(... -> Mono.empty())` for all authentication errors?

**Answer:** It erases the fact that credentials were checked and rejected, which can cause unsafe fallbacks and hide infrastructure errors.

## 13. Official Documentation

- [Spring Security — AuthenticationWebFilter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html)
- [Spring Security — ServerAuthenticationConverter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/ServerAuthenticationConverter.html)
- [Spring Security — ReactiveAuthenticationManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ReactiveAuthenticationManager.html)
- [Spring Security — DelegatingReactiveAuthenticationManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/DelegatingReactiveAuthenticationManager.html)
- [Spring Security — Reactive HTTP Basic](https://docs.spring.io/spring-security/reference/reactive/authentication/basic.html)
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security — OAuth2 Reactive Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)
