# Converting Username and Password into Authentication in HTTP Basic

**Topic:** Spring Security – Reactive (WebFlux)  
**Section:** HTTP Basic  
**Goal:** Accurately understand the path from the `Authorization: Basic ...` header to `Authentication`, distinguish an *unauthenticated* token from an *authenticated* result, configure WebFlux securely, and verify with Java 17+, `curl`, `WebTestClient`, and `StepVerifier`.

HTTP Basic is a mechanism where the HTTP client sends username/password in the header of each request. Spring Security does not take a username from the URL or a global variable to grant access: it must **read the header, convert credentials into an authentication request, verify against the user source, and only then produce a trusted identity**.

> **Key takeaway:** "Converting username/password into Authentication" does not mean "the user has logged in successfully". `ServerHttpBasicAuthenticationConverter` creates an `Authentication` used as an **authentication proposal**; `ReactiveAuthenticationManager` is the component that verifies it and returns an authenticated `Authentication`. Never trust roles or usernames asserted by the client solely because they were Base64-decoded.

## 1. Seeing the entire path before coding

With an HTTP Basic client, an example request (the string in angle brackets below is illustrative, not a valid header to copy verbatim):

```http
GET /api/me HTTP/1.1
Host: localhost:8080
Authorization: Basic <Base64-of-alice:alice123-string>
```

`Basic` indicates the authentication scheme name. What follows is the Base64 of the bytes representing `username:password`; Base64 **is not security encryption**—anyone who reads the header can recover the credentials. Therefore, HTTPS must be used outside localhost, and real credentials must never be logged or header-dumped.

**WebFlux** diagram, not Servlet flow:

```text
HTTP request
   |
   v
SecurityWebFilterChain with HTTP Basic
   |
   v
AuthenticationWebFilter
   |
   +--> ServerHttpBasicAuthenticationConverter
   |      reads Authorization; checks Basic scheme;
   |      decodes credentials and splits username/password
   |      |
   |      +--> No matching Basic -> Mono.empty()
   |      |                         (does not invoke manager for this request)
   |      |
   |      +--> Creates unauthenticated Authentication:
   |             UsernamePasswordAuthenticationToken
   |             principal = "alice"
   |             credentials = temporary raw password
   |             authenticated = false
   |             authorities = []
   |
   v
ReactiveAuthenticationManager.authenticate(requestToken)
   |
   +--> ReactiveUserDetailsService.findByUsername("alice")
   |      -> UserDetails: username, password hash, authorities, status
   |
   +--> PasswordEncoder.matches(raw, storedHash)
   |      + checks account enabled/locked/... per policy
   |
   +--> Invalid: error Mono with AuthenticationException
   |        -> handler / entry point, typically HTTP 401
   |
   +--> Valid: authenticated Mono<Authentication>
   |             authenticated = true
   |             authorities = permissions from trusted source
   |
   v
ReactiveSecurityContextHolder (per-request Reactor Context)
   |
   v
authorizeExchange(...) checks roles/authorities
   |
   +--> Allowed -> WebFlux controller -> Mono/Flux -> HTTP response
   |
   +--> Missing permission -> typically HTTP 403
```

Spring Security provides the filter and converter for HTTP Basic out of the box when calling `ServerHttpSecurity.httpBasic(...)`. **Most applications do not need to write their own Base64 parser or authentication filter**.

### 1.1. "Authentication" has two states

The same `org.springframework.security.core.Authentication` interface is used to represent both the authentication **request** and **result**. Important properties:

| Property | Immediately after Basic converter | After successful manager verification |
| --- | --- | --- |
| `getPrincipal()` | Usually the client-claimed username string, e.g., `"alice"` | Usually `UserDetails` or a trusted principal created by the manager |
| `getCredentials()` | Password sent by client; **sensitive** | May be cleared/short-lived depending on implementation; do not rely on it post-login |
| `isAuthenticated()` | **`false`** | **`true`** |
| `getAuthorities()` | Empty/untrusted | Authorities such as `ROLE_USER` loaded from user store/policy |
| `getName()` | Client-proposed name, **unverified** | Verified principal name |

`UsernamePasswordAuthenticationToken.unauthenticated(username, password)` is the explicit way to express a request token. The `UsernamePasswordAuthenticationToken.authenticated(principal, credentials, authorities)` API can create an authenticated token in **trusted code**, but **must never be used to directly trust usernames/roles from HTTP headers**. Authentication must go through a manager or a securely designed trust boundary.

### 1.2. Missing Basic header is a different case from wrong password

- Request **without `Authorization`**: the converter creates no token; the filter does not authenticate via Basic. Then, if the endpoint requires `authenticated()`, Spring Security rejects it and issues an HTTP Basic challenge.
- Header with another scheme, e.g., `Bearer`: the Basic converter does not turn that credential into a username/password. If the app needs Bearer tokens, configure a **different** OAuth2 Resource Server/manager instead of forcing tokens into the Basic parser.
- Basic header with a valid username but **wrong password**: the converter can still create a request token, but the manager rejects it after checking `PasswordEncoder.matches(...)`.
- **Malformed** Basic header (invalid Base64/missing separator): must be handled as an invalid/unauthenticatable request. The exact status/exception depends on the version and handler configuration; do not assume every malformed string reaches `findByUsername`.

For public endpoints, a client sending a **wrong** Basic header may still be rejected by the Basic filter before reaching the controller, even if the URL has `permitAll()`. `permitAll()` allows requests **without authentication**, not that Spring must ignore invalid credentials actively sent by the client.

## 2. Base64, colons, and charsets

HTTP Basic represents credentials as a `username:password` string encoded to bytes and then Base64:

```text
username   = alice
password   = alice123
raw        = alice:alice123
scheme     = Basic
header     = Authorization: Basic <base64(raw-bytes)>
```

**The first colon** separates username and password. Per Basic syntax, a username cannot contain `:`; a password **may** contain subsequent `:` characters, so parsers must split on the *first* `:`, not split every colon and just take the second element. For example, `alice:p:a:ss` means username `alice`, password `p:a:ss`.

### 2.1. Standalone Java 17 program: seeing the decoding step clearly

This is a **wire-format simulation for learning**, not parser code to put into production. The program uses purely dummy credentials locally, makes no network connections, and does not print the raw password.

Save as `BasicHeaderAnatomy.java`:

```java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public class BasicHeaderAnatomy {
    public static void main(String[] args) {
        String original = "alice:p:a:ss"; // Demo value only

        String base64 = Base64.getEncoder().encodeToString(
            original.getBytes(StandardCharsets.UTF_8));
        String header = "Basic " + base64;

        byte[] decoded = Base64.getDecoder().decode(header.substring(6));
        String pair = new String(decoded, StandardCharsets.UTF_8);
        int firstColon = pair.indexOf(':');

        String username = pair.substring(0, firstColon);
        String password = pair.substring(firstColon + 1);

        System.out.println("scheme=Basic");
        System.out.println("username=" + username);
        System.out.println("password-has-colon=" + password.contains(":"));
        System.out.println("password-length=" + password.length());
    }
}
```

Run:

```bash
javac BasicHeaderAnatomy.java
java BasicHeaderAnatomy
```

Exact stdout:

```text
scheme=Basic
username=alice
password-has-colon=true
password-length=6
```

Note: the demo only shows how splitting works; it **does not check whether the user exists or the password is correct**. It also lacks header validation, size limits, and exception handling, so **do not use it instead of Spring Security's converter**. In real apps, you rarely need to decode the header yourself.

### 2.2. Username/password encoding is not an arbitrary detail

Base64 operates on **bytes**, not Unicode strings directly. For ASCII characters like `alice:alice123`, UTF-8 and ISO-8859-1 produce the same bytes; for names/passwords with Vietnamese diacritics, the two charsets can differ and lead to 401 even when the user thinks the password is right. HTTP Basic has charset interoperability rules and Spring Security provides converter-related configuration. Establish a unified client/server policy and test with realistic data; do not alter passwords with `trim()`, lowercasing, or Unicode normalization changes during login without matching registration rules.

In Spring client code, `HttpHeaders.setBasicAuth(username, password)` has an overload accepting a `Charset`. If the system uses Unicode credentials, choose encoding matching the server, inspect the full `WWW-Authenticate` challenge and how the converter decodes; do not assume all browsers/curl behave identically across versions.

## 3. Four Spring Security components you must distinguish

### 3.1. ServerAuthenticationConverter

The `org.springframework.security.web.server.authentication.ServerAuthenticationConverter` interface takes a `ServerWebExchange` and returns `Mono<Authentication>`. For HTTP Basic, Spring provides `ServerHttpBasicAuthenticationConverter` (package `org.springframework.security.web.server.authentication`).

The converter is responsible for **interpreting HTTP credentials and creating a request token**. It does **not**:

- query the database;
- verify password hashes;
- grant trusted roles/authorities;
- place the principal into the Reactor Context itself;
- decide whether the client can access `/api/admin`.

When the converter emits `Mono.empty()`, that means **no conversion result** for this filter, not "authenticated anonymously with success".

### 3.2. AuthenticationWebFilter

`AuthenticationWebFilter` is a WebFilter in the Spring Security WebFlux chain. It takes a converter, calls a manager to authenticate the token, handles success/failure, and wires the result into the reactive security context. Key points:

1. Checks whether the request falls within the filter's authentication scope.
2. Calls `ServerAuthenticationConverter.convert(exchange)`.
3. If `Mono.empty()`, does not invoke the manager for this filter; continues the pipeline.
4. If a request token is produced, calls `ReactiveAuthenticationManager.authenticate(token)`.
5. On success, runs success handling and makes `Authentication` available in `ReactiveSecurityContextHolder`.
6. On failure, uses the appropriate failure handler/entry point; never lets an unauthenticated request token become a trusted identity.

Do not confuse **WebFlux**'s `AuthenticationWebFilter` with **Servlet**'s `BasicAuthenticationFilter`. Likewise, `SecurityFilterChain` + `HttpSecurity` are Servlet; this app must use `SecurityWebFilterChain` + `ServerHttpSecurity`.

### 3.3. ReactiveAuthenticationManager

`ReactiveAuthenticationManager` takes an unauthenticated `Authentication` and returns a resulting `Mono<Authentication>`. For username/password stored in a user store, `UserDetailsRepositoryReactiveAuthenticationManager` uses `ReactiveUserDetailsService` to look up the user and `PasswordEncoder` to compare the raw credential with the password hash.

The manager verifies **identity**, while Spring Security authorization checks **endpoint access permissions** after identity is trusted. Even a validly logged-in user can still get `403 Forbidden` when missing a role.

### 3.4. ReactiveSecurityContextHolder

After authentication, the authenticated `Authentication` is placed into `SecurityContext` via the subscriber's Reactor Context. Service/controller code reads it via `ReactiveSecurityContextHolder.getContext()`, rather than relying on a `ThreadLocal` holding the user from a previous request. In WebFlux, requests can interleave on the same event-loop thread or switch schedulers; reading the principal within the pipeline is far more reliable than storing it in a singleton field.

## 4. A runnable Java 17+ Spring Boot WebFlux application

The sample application demonstrates the real flow: HTTP Basic's default converter → `ReactiveAuthenticationManager` → hashed user store → authenticated result in Reactor Context → controller/authorization.

Endpoints:

| Method + path | Rule | Key outcomes |
| --- | --- | --- |
| `GET /public/ping` | `permitAll()` | Anonymous receives `200`, `pong` |
| `GET /api/me` | `authenticated()` | Anonymous receives `401`; valid Alice receives `200`, `hello:alice` |
| `GET /api/admin` | `hasRole("ADMIN")` | Valid Alice receives `403`; valid admin receives `200`, `admin-ok` |
| Any other path/method | `denyAll()` | Prevents accidentally exposing new routes |

Sample accounts: `alice / alice123` has `ROLE_USER` and `admin / admin123` has `ROLE_ADMIN`. **They are for localhost learning environments only.** Passwords are hashed using `DelegatingPasswordEncoder` (BCrypt per default policy) before being placed in `MapReactiveUserDetailsService`.

### 4.1. Structure

```text
basic-auth-conversion/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/basic/
    │   │   ├── BasicAuthApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── AuthController.java
    │   └── resources/application.properties
    └── test/java/demo/basic/
        └── BasicAuthConversionTests.java
```

Use **Spring Boot 3.5.7** as a reproducible dependency baseline and JDK 17+. This is an example version, not advice to keep old versions in production. In real deployments, choose a supported patch release and follow your project's security policy.

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>basic-auth-conversion</artifactId>
    <version>1.0.0</version>
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
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
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

**Why not add `spring-boot-starter-web`?** This lesson uses WebFlux. When both MVC and WebFlux starters are present, Spring Boot may prefer Servlet MVC, changing the filter chain and application type unexpectedly. No database, Docker, or custom WebClient is needed for this practice exercise.

`src/main/resources/application.properties`:

```properties
spring.application.name=basic-auth-conversion
server.port=8080
```

### 4.2. Entry point

`src/main/java/demo/basic/BasicAuthApplication.java`:

```java
package demo.basic;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BasicAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(BasicAuthApplication.class, args);
    }
}
```

The other Java classes are placed in package `demo.basic` so `@SpringBootApplication` component scanning discovers them.

### 4.3. Configuring SecurityWebFilterChain, user store, and manager

`src/main/java/demo/basic/SecurityConfig.java`:

```java
package demo.basic;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    ReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice123"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin123"))
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(alice, admin);
    }

    @Bean
    ReactiveAuthenticationManager authenticationManager(
            ReactiveUserDetailsService users,
            PasswordEncoder encoder) {

        var manager =
            new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        return manager;
    }

    @Bean
    SecurityWebFilterChain security(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager authenticationManager) {

        return http
            .authenticationManager(authenticationManager)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/public/ping").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .pathMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }
}
```

**What problem is each part solving?**

1. `@EnableWebFluxSecurity` enables Spring Security integration with WebFlux.
2. `PasswordEncoderFactories.createDelegatingPasswordEncoder()` applies a consistent hashing/verification policy. Demo hashes typically look like `{bcrypt}...`; encoding the same password twice yields different hashes due to salting.
3. `users(...)` holds `UserDetails` with **encoded** passwords, authorities, and user status. A real system uses a `ReactiveUserDetailsService` reading hashes from R2DBC/an appropriate data source, never storing raw passwords.
4. `authenticationManager(...)` is where the request token created by the Basic converter is **verified**. It looks up the username and calls `PasswordEncoder.matches(raw, encoded)`; only after passing does it return an authenticated result.
5. `http.authenticationManager(...)` wires this manager into the authentication mechanisms supported by the chain. `httpBasic(Customizer.withDefaults())` configures the built-in Basic filter/converter rather than manually decoding Base64 in controllers.
6. `formLogin(...disable())` disables form login for the API sample, letting you observe 401/403 via HTTP Basic. Do not assume "every app with HTTP Basic is sessionless": other configurations can add form login/sessions.
7. `anyExchange().denyAll()` prevents leaving unspecified methods/paths open.

**Important:** The code above does not declare a `ServerHttpBasicAuthenticationConverter` bean or write a custom `AuthenticationWebFilter`, **because Spring Security already handles that**. Adding a custom filter without understanding matchers, ordering, and success/failure handlers can create two conflicting authentication mechanisms or miss the security context.

### 4.4. Controller reading the verified Authentication properly

`src/main/java/demo/basic/AuthController.java`:

```java
package demo.basic;

import org.springframework.http.MediaType;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class AuthController {

    @GetMapping(value = "/public/ping",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping(value = "/api/me",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName)
            .map(name -> "hello:" + name);
    }

    @GetMapping(value = "/api/admin",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> admin() {
        return Mono.just("admin-ok");
    }
}
```

`/api/me` does not read the username from the URL, a query parameter, or an `X-User` header. It gets the principal **after Spring Security has authenticated it** from the request's own Reactor Context. When returning `Mono` to the framework, WebFlux subscribes and propagates context along the pipeline. Do not manually call `subscribe()` in a controller and do not use a `static currentUser` field to store the logged-in user.

## 5. Running live with curl and understanding the results

In the `basic-auth-conversion` directory:

```bash
java -version
mvn -version
mvn spring-boot:run
```

Once the logs show the Reactor Netty server listening on port 8080, open another terminal. If the port is occupied, update `server.port` and all corresponding URLs. On older Windows PowerShell, `curl` is sometimes an alias for `Invoke-WebRequest`; invoke `curl.exe` to run the real command.

### 5.1. Anonymous, right credentials, wrong credentials, and wrong role

```bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/me
curl -i --user alice:alice123 http://localhost:8080/api/me
curl -i --user alice:wrong http://localhost:8080/api/me
curl -i --user unknown:whatever http://localhost:8080/api/me
curl -i --user alice:alice123 http://localhost:8080/api/admin
curl -i --user admin:admin123 http://localhost:8080/api/admin
curl -i -H "Authorization: Bearer not-a-basic-credential" \
  http://localhost:8080/api/me
```

Matrix in command order:

| Request | Expected HTTP status | Explanation |
| --- | --- | --- |
| Public, no credentials | `200`, body `pong` | Neither converter nor manager needed for public access |
| `/api/me`, no Basic | `401` and usually `WWW-Authenticate: Basic ...` | Basic converter produces no token; authorization requires login |
| `/api/me`, valid Alice | `200`, body `hello:alice` | Converter creates request token; manager verifies; controller reads principal |
| `/api/me`, Alice wrong password | `401` | Token was converted, but `matches` failed |
| `/api/me`, non-existent username | `401` | No trusted account to authenticate |
| `/api/admin`, valid Alice | `403` | **Authentication succeeded, authorization failed** |
| `/api/admin`, valid admin | `200`, body `admin-ok` | Identity and permissions both match |
| `/api/me`, Bearer scheme when app only enables Basic | `401` | Basic converter does not interpret Bearer as username/password |

Exact error bodies/headers may vary across Spring Security versions and custom handlers, but this table represents the expected behavior for the sample configuration. To diagnose errors, inspect **method + path + Authorization scheme + status + WWW-Authenticate**; do not rely on a browser's HTML error page.

`curl --user username:password` constructs the Basic header automatically; **no need to manually Base64-encode and paste headers into configuration files**. To avoid leaving passwords in command history/process lists, you can pass `--user alice` and type the password at the prompt (support depends on the client). Never run demos over unencrypted HTTP exposed to the Internet.

### 5.2. Trying a request with a spoofed username header

```bash
curl -i --user alice:alice123 \
  -H "X-Authenticated-User: admin" \
  -H "X-Role: ADMIN" \
  http://localhost:8080/api/me
```

It must still return `hello:alice`, not `hello:admin`. Both `X-...` headers above are client-supplied, **not proof of authentication**. If the app sits behind a reverse proxy, trust identity headers only when the proxy/gateway has authenticated the caller, stripped client-supplied headers, and established an explicit trust boundary contract.

### 5.3. HTTP Basic sends credentials on every request

Basic does not "exchange" username/password for an automatic session token on the client. A subsequent request usually must send `Authorization: Basic ...` again. Browsers can cache Basic credentials and resend them automatically; inspect DevTools Network, and do not infer strict statelessness solely from using Basic. If the app also has sessions/cookies or another auth chain, the overall system may still hold state.

## 6. Testing the converter directly: before authentication happens

`WebTestClient` against a real server shows the final outcome, but to observe **the conversion stage** clearly you need to test `ServerHttpBasicAuthenticationConverter` directly with `MockServerWebExchange`.

We want to prove:

1. A valid `Basic` header produces an **unauthenticated** `UsernamePasswordAuthenticationToken`.
2. The token's `principal` is the username from the header, `credentials` is the temporary password, and **no roles** are granted by the converter.
3. Without a Basic header, the converter emits `Mono.empty()` instead of generating an authenticated "anonymous user".
4. Passwords containing `:` are preserved after the first colon.

These are **HTTP → token conversion** tests; they do not check hashes/passwords. The manager and integration tests handle that part.

## 7. Testing manager and HTTP with StepVerifier + WebTestClient

Create `src/test/java/demo/basic/BasicAuthConversionTests.java`. This test uses the same Spring Boot context, starts a real server on a **random port** with `@SpringBootTest(webEnvironment = RANDOM_PORT)`, and injects `WebTestClient`. Converter tests use pure mock exchanges; manager tests call `authenticate` directly; HTTP tests go through the full Spring Security WebFilter chain.

```java
package demo.basic;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.security.web.server.authentication.ServerHttpBasicAuthenticationConverter;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class BasicAuthConversionTests {

    @Autowired
    WebTestClient client;

    @Autowired
    ReactiveAuthenticationManager manager;

    private final ServerHttpBasicAuthenticationConverter converter =
        new ServerHttpBasicAuthenticationConverter();

    @Test
    void basicHeaderBecomesAnUnauthenticatedToken() {
        var request = MockServerHttpRequest.get("/api/me")
            .headers(headers -> headers.setBasicAuth("alice", "alice123"));

        var exchange = MockServerWebExchange.from(request);
        StepVerifier.create(converter.convert(exchange))
            .assertNext(auth -> {
                assertInstanceOf(UsernamePasswordAuthenticationToken.class, auth);
                assertEquals("alice", auth.getPrincipal());
                assertEquals("alice123", auth.getCredentials());
                assertFalse(auth.isAuthenticated());
                assertTrue(auth.getAuthorities().isEmpty());
            })
            .verifyComplete();
    }

    @Test
    void noAuthorizationHeaderCreatesNoBasicRequestToken() {
        var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get("/api/me"));

        StepVerifier.create(converter.convert(exchange))
            .verifyComplete();
    }

    @Test
    void theFirstColonSeparatesUsernameFromPassword() {
        var request = MockServerHttpRequest.get("/api/me")
            .headers(headers -> headers.setBasicAuth(
                "alice", "pass:with:colons"));

        StepVerifier.create(
                converter.convert(MockServerWebExchange.from(request)))
            .assertNext(auth -> {
                assertEquals("alice", auth.getPrincipal());
                assertEquals("pass:with:colons", auth.getCredentials());
                assertFalse(auth.isAuthenticated());
            })
            .verifyComplete();
    }

    @Test
    void managerTurnsCorrectCredentialsIntoVerifiedAuthentication() {
        Authentication proposed =
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "alice123");

        StepVerifier.create(manager.authenticate(proposed))
            .assertNext(verified -> {
                assertTrue(verified.isAuthenticated());
                assertEquals("alice", verified.getName());
                assertTrue(verified.getAuthorities().stream()
                    .anyMatch(role -> "ROLE_USER".equals(
                        role.getAuthority())));
            })
            .verifyComplete();
    }

    @Test
    void managerRejectsIncorrectPassword() {
        Authentication proposed =
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "incorrect");

        StepVerifier.create(manager.authenticate(proposed))
            .expectError(BadCredentialsException.class)
            .verify();
    }

    @Test
    void publicEndpointAcceptsAnonymous() {
        client.get().uri("/public/ping")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void protectedEndpointChallengesMissingCredentials() {
        client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().exists(HttpHeaders.WWW_AUTHENTICATE);
    }

    @Test
    void httpBasicProducesTheExpectedPrincipal() {
        client.get().uri("/api/me")
            .headers(headers -> headers.setBasicAuth(
                "alice", "alice123"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("hello:alice");
    }

    @Test
    void wrongPasswordFailsAuthentication() {
        client.get().uri("/api/me")
            .headers(headers -> headers.setBasicAuth(
                "alice", "wrong"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void unknownUsernameDoesNotAuthenticate() {
        client.get().uri("/api/me")
            .headers(headers -> headers.setBasicAuth(
                "unknown", "whatever"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void validNonAdminCredentialsFailAuthorization() {
        client.get().uri("/api/admin")
            .headers(headers -> headers.setBasicAuth(
                "alice", "alice123"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void validAdminCredentialsCanAccessAdmin() {
        client.get().uri("/api/admin")
            .headers(headers -> headers.setBasicAuth(
                "admin", "admin123"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin-ok");
    }
}
```

Run:

```bash
mvn test
```

With the exact test class above, **12 tests are expected to pass** when code/dependencies are right and the server starts. Do not hardcode Maven stdout because logs, test order, dependency download times, and response header details may vary. If a test fails, check the assertion's *expected/actual*, stack trace, and bean configuration. This lesson only provides **the code and expected results to run**, not a claim that the suite was executed in the reader's environment.

### 7.1. Reading each test group

- **Converter**: the first three tests show that a Basic header converts into an untrusted request `Authentication`, no header yields no token, and colons inside a password do not corrupt the password.
- **Manager**: the next two tests prove `PasswordEncoder`/user store/manager turn username-password into a principal with trusted roles, or error on wrong credentials.
- **HTTP**: the remaining tests prove the converter and manager are wired into real requests by the WebFilter; authorization sees the result and returns 200/401/403 per permissions.
- **Exact body**: status 200 alone is not enough. `hello:alice` proves the controller sees the right principal after authentication.
- **Do not trust mocked credentials when testing HTTP**: `WebTestClient` requests use `headers.setBasicAuth(...)`, just like a real HTTP client. Direct converter/manager tests do not replace integration tests through the WebFilter.

### 7.2. Separating "the converter works" from "the system is secure"

A converter test can pass even if the user store is broken, because the converter never touches the database. A manager test can pass even if the HTTP Basic filter isn't attached to the chain. A `200` endpoint test can pass even if the URL is accidentally public unless you have **negative tests** for `401` and `403`. Therefore, the three test layers complement one another and should be run together whenever changing login mechanisms.

## 8. Why is Reactor Context critical right after Authentication?

After the manager authenticates successfully, Spring Security Reactive propagates `Authentication` via `ReactiveSecurityContextHolder` along the request's subscription chain. This matters because a WebFlux event-loop thread can serve many interleaved requests; Servlet-style ThreadLocal `SecurityContextHolder` is not a suitable source of truth for reactive apps.

Recommended fragment in a service:

```java
Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
}
```

This is only **a method fragment**, not a standalone Java file; in the runnable example, the controller already has full imports and the enclosing class.

Another request sending a Basic header for `bob` must never read the username from `alice`'s prior request. Avoid these mistakes:

- Storing `Authentication` or the username in a mutable field on a singleton service and reading it after `Mono.delay` completes.
- Manually calling `subscribe()` to continue authentication/auditing outside the pipeline.
- Caching `Mono<Authentication>` under a global key without partitioning by user/tenant.
- Reading a `ThreadLocal currentUser` across scheduler switches assuming it remains bound to the request.

Asynchronous work detached completely from the Reactor pipeline may **no longer have the request's security context**; pass the verified identity via a trusted contract and enforce permissions at execution time rather than using client-claimed usernames.

## 9. Customizing conversion: when is it actually needed?

Usually all you need is:

```java
return http
    .authorizeExchange(exchanges -> exchanges
        .anyExchange().authenticated())
    .httpBasic(Customizer.withDefaults())
    .build();
```

This is a **fragment** inside a `SecurityWebFilterChain` bean, not a complete program. Spring Security configures the HTTP Basic converter automatically. Do not build a custom Base64 parser to push an authenticated user straight into SecurityContext.

If a real requirement demands a different header structure or special charset policy, Spring Security allows customizing `ServerAuthenticationConverter` on `AuthenticationWebFilter`. In API terms, the mechanism (fragment) is:

```java
AuthenticationWebFilter filter =
    new AuthenticationWebFilter(reactiveAuthenticationManager);
filter.setServerAuthenticationConverter(customConverter);
```

The snippet above **illustrates the API**, not a complete configuration: you must specify `reactiveAuthenticationManager`, `customConverter`, matchers, WebFilter placement in `SecurityWebFilterChain`, success/failure handlers, context repository, and HTTP Basic challenge behavior. If you only want standard Basic, stick with the `httpBasic` DSL rather than adding a filter manually, since misconfiguring a filter can cause bypasses or double credential processing.

A secure custom converter must:

1. Accept only the exact defined scheme/format; never trust arbitrary headers like `X-User` just because they carry a username.
2. Validate header length, valid Base64, separator, username, and charset; never fall back to a "default login" on error.
3. Return an `Authentication` with `authenticated=false` and no self-asserted authorities.
4. Let the manager handle verification and load roles from a trusted source.
5. Never log/echo passwords or persist passwords long-term.
6. Include negative tests for missing headers, wrong schemes, malformed Base64, non-existent users, wrong passwords, duplicate headers, and charset differences.

**If Bearer tokens/OAuth2/JWT are needed**, configure `oauth2ResourceServer(...)` with proper token verification components. Never grab the string after `Bearer` and turn it into a username/password or pass it to a password manager: the two authentication methods have different trust models.

## 10. Distinguishing Authentication from Authorization and HTTP statuses

| Outcome | Typical meaning in demo | What to check? |
| --- | --- | --- |
| `200 OK` on `/api/me` | Valid Basic header, manager authenticated, endpoint allowed | Body matches principal, no user mix-up |
| `401 Unauthorized` without credentials | Converter produced no request token; endpoint requires authenticated | `WWW-Authenticate`, whether it's the right Basic challenge |
| `401` wrong password | Converter created request token but manager rejected it | Hash, user store, account status, client password |
| `401` user does not exist | No trusted principal found | Avoid leaking user existence through errors |
| `403 Forbidden` for Alice on `/api/admin` | Authentication succeeded, insufficient role | `hasRole("ADMIN")`, trusted authority source |
| `302 Found` | Possible form login or other redirect | `Location`, login/session/HTTPS config; do not assume Basic authenticated |
| `404 Not Found` | Endpoint mapping may not exist | Mappings/controller; a deny-all fallback might block earlier with 401/403 |
| `403` on POST/PUT | Possibly missing CSRF token, not just permissions | Method, CSRF policy and token; do not blindly disable CSRF |

These statuses depend on configuration and HTTP challenges; they **do not prove the entire security architecture**. Measuring a 200 status without checking the body or authorization fails to catch per-user data exposure bugs.

### 10.1. Two different 401 cases must be investigated at different layers

1. **No `Authorization` sent:** the converter returns empty, and the manager step may not run. Investigate the client, proxies stripping headers, filter configuration, and matchers.
2. **Valid Basic header sent but password is wrong:** the converter creates a token, and the manager rejects it. Investigate `ReactiveUserDetailsService`, `PasswordEncoder.matches`, `{bcrypt}` prefixes, and user status.

Similarly, a header with the wrong charset can cause username/password to be interpreted differently from what the user typed. Do not work around it by bypassing the manager or setting `permitAll()`; align the client/server protocol and improve test coverage.

## 11. Common mistakes and how to fix them

### 11.1. Marking the token authenticated right inside the converter

**Wrong (intentionally dangerous fragment):**

```java
return Mono.just(
    UsernamePasswordAuthenticationToken.authenticated(
        usernameFromHeader, null, adminAuthoritiesFromHeader));
```

This code trusts `usernameFromHeader` and self-asserted authorities as authenticated, skipping password verification. Only create an **unauthenticated token** and let the manager verify it; authorities must come from the user store or a trusted identity system.

### 11.2. Storing plaintext passwords or re-hashing before matches

`PasswordEncoder.matches(rawPassword, storedHash)` is the right check. Never compare `encoder.encode(raw).equals(storedHash)` because salted hashes differ. Never store raw passwords in databases, logs, or responses. Use dedicated hashes like BCrypt/Argon2 per policy and resource limits.

### 11.3. Treating Base64 as security encryption

`Authorization: Basic ...` can be decoded by anyone reading traffic or logs. Never send over public HTTP; use appropriate end-to-end HTTPS, and keep raw headers out of logs, error telemetry, or tickets. Proxies/ingress must handle headers under tight control.

### 11.4. Extracting username manually by splitting the header

`String[] parts = decoded.split(":")` can lose parts of a password after the first colon. Custom parsers also easily miss malformed Base64, charsets, whitespace, and duplicate headers. Use Spring's standard converter, customizing only when truly necessary and backed by negative tests.

### 11.5. Treating getPrincipal() before authenticate as a trusted identity

In a request token, the principal is merely client-supplied text. Only the manager's successful authentication result is trustworthy. An `Authentication.isAuthenticated()` manually set to true by a developer is not proof the password was checked.

### 11.6. Confusing WebFlux with Servlet

`BasicAuthenticationFilter`, `HttpSecurity`, and ThreadLocal `SecurityContextHolder` appear in Servlet guides. In WebFlux, we use `AuthenticationWebFilter`, `ServerHttpBasicAuthenticationConverter`, `ServerHttpSecurity`, and `ReactiveSecurityContextHolder`. Do not copy Java configuration directly from Servlet to Reactor.

### 11.7. Turning 401 errors into open access

Switching to `anyExchange().permitAll()` just to avoid 401 can expose endpoints publicly. If credentials are wrong, fix the credentials/hash/manager. If matchers are wrong, fix the chain/filter. If a role is missing, fix the authorization policy and the account's legitimate roles; do not grant ADMIN to everyone.

### 11.8. Equating `{noop}` with strong hashing

`User.withUsername(...).password("{noop}secret")` is suitable only for very limited demos; `noop` accepts plaintext stored passwords. The complete example above uses `DelegatingPasswordEncoder` and BCrypt hashes to avoid this bad habit.

### 11.9. Assuming Basic automatically stores sessions and supports logout

Basic is a method of sending credentials via request headers. HTTP clients/browsers may cache credentials, but there is no magic logout command achieved by clearing one variable on the server. In systems with accompanying form login/sessions, cookies/sessions have their own lifecycle. For stateless APIs, consider tokens if the problem and threat model fit, rather than overusing Basic where user passwords are hard to protect.

## 12. Practical deployment checklist

1. **Choose authentication mechanisms clearly:** Is the API Basic-only or also Form Login/Bearer? Which chain takes which routes, per `securityMatcher`/`@Order`?
2. **Build a trusted user store:** `ReactiveUserDetailsService` returns valid users, intact hashes, and roles from a database/internal source. If a user does not exist, never synthesize a privileged "guest" user.
3. **Configure encoders consistently:** use the same policy to `encode` on save and `matches` on login; store hash prefixes if using Delegating. Upgrade password hashes only via trusted flows.
4. **Wire filter/manager properly:** `httpBasic` establishes the Basic flow; `ReactiveAuthenticationManager` authenticates; never stamp `Authentication` as authenticated based on HTTP client data.
5. **Default-deny authorization policy:** distinguish `authenticated()` and `hasRole(...)`, with a default deny for unpermitted paths.
6. **Protect secrets:** HTTPS, no raw passwords/Authorization headers printed, request size limits, secrets management, and log redaction.
7. **Defend against brute force:** rate limiting, failed-login monitoring, credential stuffing detection, and sensible lockout/captcha/risk-based policies; slow hashing does not replace online rate limiting.
8. **Never block the event loop:** query users with reactive repositories/drivers where appropriate, offload CPU-intensive password hashing to a scheduler per policy/benchmarks, and never call `block()` in handlers.
9. **Test all three layers:** converter outputs unauthenticated tokens; manager handles right/wrong credentials; HTTP returns 401/403/200 with expected roles and bodies.
10. **Test resource ownership:** after authentication, endpoints must still check resource ownership/tenant to prevent "Alice reads Bob's report".
11. **Before production:** remove hard-coded accounts/passwords, use real account management, review lifecycle, rotation/reset/MFA as needed, and keep Spring Boot/Security on supported versions.

## 13. Self-assessment questions

**Question 1.** When receiving `Authorization: Basic ...`, does Spring know the password is valid from Base64 alone?  
**No.** Base64 only represents bytes. The converter builds an unauthenticated request token; the manager verifies the user/hash/status.

**Question 2.** Can you trust `UsernamePasswordAuthenticationToken.getAuthorities()` from a token created by the converter?  
**No.** An unauthenticated request token must have no trusted authorities. Permissions are granted only by the manager and a trusted source.

**Question 3.** When no Basic header is present, why can a protected endpoint return 401 even though the manager never ran?  
Because the converter produced no token, yet authorization still requires an identity; the entry point sends a Basic challenge to the client.

**Question 4.** Alice logs in successfully, yet calling `/api/admin` returns 403: is the converter broken?  
**Not necessarily.** Authentication succeeded; authorization saw that Alice lacks `ROLE_ADMIN`.

**Question 5.** If the password is `p:a:ss`, can you use `decoded.split(":")[1]`?  
**No.** You must preserve everything after the first `:`; use the standard converter to avoid parser bugs.

**Question 6.** Why not use `ThreadLocal` to store the username in a WebFlux controller?  
Because requests can interleave on the same thread and a pipeline can switch schedulers. Use the request's Reactor Context via `ReactiveSecurityContextHolder`.

**Question 7.** Why are converter unit tests alone insufficient?  
Because the converter does not check passwords, wire the security filter into the web chain, or enforce permissions. Manager tests and HTTP integration tests are needed.

**Question 8.** Is HTTP Basic safe when sent over unencrypted HTTP?  
**No.** Base64 is trivially reversible; use HTTPS, protect credentials, and avoid logging headers.

**Question 9.** If the application uses Bearer JWT, should the Basic converter be reused to extract the "username" from the token?  
**No.** JWT/Bearer must have its signature/issuer/audience/claims verified as a resource server, not decoded as username/password via Basic.

**Question 10.** Is every 401 response caused by a wrong password?  
**No.** It could be a missing header, wrong scheme, charset mismatch, non-existent user, wrong password, or entry point configuration; investigate at the right layer.

### Official references

- Spring Security, *WebFlux Security*: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security API, `AuthenticationWebFilter`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html
- Spring Security API, `ServerHttpBasicAuthenticationConverter`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/ServerHttpBasicAuthenticationConverter.html
- Spring Security API, `UserDetailsRepositoryReactiveAuthenticationManager`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/UserDetailsRepositoryReactiveAuthenticationManager.html
- Spring Security, `Authentication` interface: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/Authentication.html
- Spring Security, *Password Storage*: https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html
- Spring Boot 3.5, *Testing Spring Boot Applications*: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- IETF RFC 7617, *The 'Basic' HTTP Authentication Scheme*: https://www.rfc-editor.org/rfc/rfc7617

**Key summary:** `Authorization: Basic ...` carries only **client-claimed credentials**. `ServerHttpBasicAuthenticationConverter` creates an **unauthenticated** `UsernamePasswordAuthenticationToken`; `ReactiveAuthenticationManager` checks the user and password hash to return an **authenticated** `Authentication`, which Spring Security then places into `ReactiveSecurityContextHolder` and checks against endpoint permissions. Keeping these two states distinct is the core principle to prevent identity spoofing when implementing HTTP Basic in WebFlux.