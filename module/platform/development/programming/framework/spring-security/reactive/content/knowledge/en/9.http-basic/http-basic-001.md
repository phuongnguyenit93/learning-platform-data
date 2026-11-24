# HTTP Basic Mechanism and Authorization Header Structure

> **Topic:** Spring Security – reactive  
> **Knowledge group:** HTTP Basic  
> **Goal:** Accurately read, construct, and explain `Authorization: Basic ...` per RFC 7617; understand the `401/WWW-Authenticate` challenge, username/password/charset rules, and know how to integrate, test, and secure HTTP Basic in Spring Security WebFlux.

## 1. What problem does HTTP Basic solve?

HTTP Basic Authentication is an **HTTP authentication scheme** that uses a **user-id (username)** and **password** pair to prove identity to an HTTP server. Instead of sending a JSON login to exchange for a token, the client typically sends an HTTP header with requests that require authentication:

```http
GET /api/private HTTP/1.1
Host: example.test
Authorization: Basic QWxhZGRpbjpvcGVuIHNlc2FtZQ==
```

This is the standard example in **RFC 7617**: the Base64 value represents the string `Aladdin:open sesame`. It is **not** a standalone access token and is **not** encryption. Anyone who receives this Base64 string can decode it and recover the username/password; only HTTPS/TLS protects data in transit.

A server can ask a client to authenticate with a **401 Unauthorized** response:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="learning"
```

Afterward, the client can send credentials. Some HTTP clients send `Authorization` immediately on the first request (preemptive authentication), without waiting for a challenge. Both approaches use the same Basic structure.

Do not confuse:

- **Authentication:** Is the user/password pair real and valid?
- **Authorization:** Is the authenticated user allowed to perform this action / read this resource?
- **Authorization header:** The HTTP header name used to transmit credentials according to an authentication scheme. This header **does not grant permissions by itself**; the server must still authenticate and check authorization.

### After this lesson, you can

1. Construct `Authorization: Basic <base64(user-id:password)>` and accurately explain each part.
2. Distinguish the `Authorization` request header from the `WWW-Authenticate` response header, status **401** from **403**, and Basic from Bearer.
3. Properly handle the first colon, username character limits, and the challenge's `charset="UTF-8"` option.
4. Explain the roles of `AuthenticationWebFilter`, converter, `ReactiveAuthenticationManager`, `SecurityContext`, and authorization in WebFlux.
5. Run a Spring Boot WebFlux application using HTTP Basic and test multiple cases with `WebTestClient`.
6. Identify risks: Base64 is not secure, TLS, browser credential caching, logs/proxies, credential replay, CSRF, and operational limitations.

## 2. Dissecting the exact Authorization header structure

Conceptual syntax per RFC 7617:

```text
Authorization: Basic <token68>
                     |
                     +-- Base64(bytes(user-id + ":" + password))
```

Example:

```text
User-id:                Aladdin
Password:               open sesame
user-pass string:       Aladdin:open sesame
US-ASCII bytes:         41 6c 61 64 64 69 6e 3a 6f 70 ...
Base64 encoding:        QWxhZGRpbjpvcGVuIHNlc2FtZQ==
HTTP request header:    Authorization: Basic QWxhZGRpbjpvcGVuIHNlc2FtZQ==
```

| Component | Meaning | Notes |
| --- | --- | --- |
| `Authorization` | HTTP request header name | Not the response's `WWW-Authenticate` |
| `Basic` | Authentication scheme name | Scheme name matches case-insensitively; conventionally written as `Basic` |
| Space | Separates scheme and credentials | Do not insert `username=`, `password=`, or JSON |
| `QWxh...` | Base64 value using `token68` syntax | Not encryption, digital signature, or bearer token |
| `:` **before encoding** | Separates username and password | **The first `:`** is the separator |
| Trailing `=` in Base64 | Base64 padding character when needed | Do not strip or replace with incompatible URL-safe Base64 |

### 2.1. Steps to build the header

Given user-id `Aladdin` and password `open sesame`:

1. Concatenate in exact order: `Aladdin:open sesame`.
2. Encode this string into bytes using an appropriate character encoding; for the sample ASCII string, UTF-8 and ISO-8859-1 produce the same bytes.
3. Encode the bytes using **standard Base64**, not Base64URL.
4. Prepend `Basic `.
5. Put it in the `Authorization` request header, using **HTTPS** for real requests.

On the server side, the Basic converter reads the header, checks the scheme, Base64-decodes it, and extracts username/password by splitting at **the first colon**. Then the authentication component verifies the password against the user store; successful decoding **does not prove** the credentials are valid.

### 2.2. The colon: a special rule that is easy to get wrong

RFC 7617 specifies that **a username must not contain `:`**. A password **may contain `:`**. For example:

```text
Raw user-pass: reader:part:two:three
Username:      reader
Password:      part:two:three
```

Do not call `raw.split(":")` and require exactly two parts: doing so breaks passwords containing `:`. In self-written decoding examples, use `indexOf(':')` and split once. Do not assume the framework's server will accept every kind of username/password: there are still validation, charset, account state, and password encoder checks.

**A username containing `:` cannot be validly represented** in this user-pass syntax, even though Base64 can still encode the bytes. For example, `reader:team:secret` is always interpreted as username `reader`, password `team:secret` based on the first boundary.

### 2.3. Base64 is not secure encryption

Anyone can reverse it:

```text
"QWxhZGRpbjpvcGVuIHNlc2FtZQ=="
          |
          v
Base64 decode
          |
          v
"Aladdin:open sesame"
```

There is no secret key, IV, nonce, authentication tag, or cryptographic integrity check in the Base64 step. Base64 only converts bytes into characters safe to write in a header. Therefore:

- **Unencrypted HTTP** + Basic essentially sends the password in readable form to anyone observing the traffic.
- **HTTPS/TLS** protects the transport connection; however, reverse proxies, application gateways, servers, client plugins, or logging middleware at the TLS termination point can still access the header.
- Do not store Basic strings in source code, screenshots, tickets, logs, monitoring labels, or HTTP dumps.
- Do not use the Base64 of a password as a password hash stored in a database. Stored passwords need dedicated algorithms like BCrypt/Argon2id or an encoder approved by security policy.

## 3. HTTP challenge/response: who sends which header?

Two commonly confused headers:

| Header | Direction | Who sends it? | When is it used? |
| --- | --- | --- | --- |
| `Authorization: Basic ...` | **Client → Server** | Client | Provides credentials to the origin server |
| `WWW-Authenticate: Basic realm="..."` | **Server → Client** | Server | Challenge requesting authentication or retry on 401 |
| `Proxy-Authorization: Basic ...` | **Client → Proxy** | Client | Credentials for an HTTP proxy with its own authentication |
| `Proxy-Authenticate: Basic realm="..."` | **Proxy → Client** | Proxy | Proxy challenge, usually with status 407 |

Do not put username/password into `WWW-Authenticate`: that header describes the server-side challenge rather than carrying client credentials. Do not use `Proxy-Authorization` when a regular origin API expects `Authorization`.

### 3.1. Challenge flow

```text
      HTTP client                              API server
           |                                      |
           | GET /api/private                     |
           |------------------------------------->|
           |                                      | No credentials yet
           | 401 Unauthorized                     |
           | WWW-Authenticate: Basic realm="api" |
           |<-------------------------------------|
           |                                      |
           | GET /api/private                     |
           | Authorization: Basic <base64>        |
           |------------------------------------->|
           |                                      | Decode + authenticate
           |                                      | Then authorize
           | 200 OK / 403 Forbidden / 401         |
           |<-------------------------------------|
```

**Not every client waits for a challenge.** With `curl -u`, `HttpHeaders.setBasicAuth`, Postman, or API clients that already know the server requires Basic, they can send `Authorization` from the very first request. This does not change the meaning of the header.

### 3.2. 401 and 403 are not interchangeable

| Scenario | Typical result in a WebFlux API using Basic |
| --- | --- |
| No credentials sent, endpoint requires login | **401** with Basic challenge |
| Non-existent username / wrong password | **401**; authentication failed |
| `Authorization` header is not Basic when no other mechanism is enabled | No valid Basic authentication; protected endpoint usually returns **401** |
| Correct username/password, has required role | Controller can return **200** |
| Correct username/password, missing role/authority | **403**, not "wrong password" |
| `permitAll` path, no credentials sent | **200** if the controller succeeds |
| `permitAll` path, wrong Basic credentials sent | Basic filter may attempt authentication first and return **401**; `permitAll` does not mean ignoring submitted credentials |

**401 = valid authentication required** (the status name Unauthorized is HTTP history; do not assume it always refers to permissions). **403 = request understood but forbidden**; in the demo below, the principal is authenticated but lacks the role. Some systems intentionally return 404 to hide resources, but that is a different policy and does not change the nature of Basic.

### 3.3. What is `realm` used for?

In:

```http
WWW-Authenticate: Basic realm="internal-api"
```

`realm` is part of the **authentication challenge** and tells the client the protection space/resource group that requires credentials. Per RFC 7617, `realm` is **required** in a Basic challenge. The realm string is not a password salt, not a verified tenant ID, and not a JWT audience. Do not put sensitive data into the realm; a browser may display it in the login dialog.

## 4. Charset and Vietnamese/Unicode: distinguish the RFC from library defaults

For **US-ASCII-only** usernames/passwords, converting strings to bytes usually gives the same result between UTF-8 and legacy ASCII-compatible encodings. With Unicode characters (e.g., `Nguyễn`, `mật-khẩu`), charset mismatches produce different Base64 headers, causing authentication to fail.

**RFC 7617 does not mandate a single default charset** for historical user-pass strings; the default must be US-ASCII compatible. A server **may** advertise its UTF-8 expectation via a parameter on the **challenge**:

```http
WWW-Authenticate: Basic realm="api", charset="UTF-8"
```

Key points:

- In RFC 7617, the defined value for the `charset` parameter is **`UTF-8`**. This parameter belongs in `WWW-Authenticate`, **not** in the `Authorization: Basic ...` string.
- The RFC expects Unicode to be processed using **Normalization Form C (NFC)** before encoding into UTF-8 bytes. Two visually identical strings with different Unicode compositions may not produce the same bytes without consistent normalization.
- Older clients may ignore `charset` or use a legacy encoding. When designing an API that accepts non-ASCII credentials, document the charset, configure Spring Security/clients, and test interoperability.
- `HttpHeaders.setBasicAuth(username, password)` defaults to **ISO-8859-1** in Spring; the overload `setBasicAuth(username, password, StandardCharsets.UTF_8)` lets you choose UTF-8. Do not assume all Basic clients use UTF-8.
- Do not modify user passwords by arbitrarily trimming, lowercasing, or normalizing them. Any normalization rules must be consistent across account registration, password hashing, and authentication.

UTF-8 example from RFC 7617 itself: user `test`, password `123£`; the UTF-8 bytes of `test:123£` produce Base64 `dGVzdDoxMjPCow==`. This is a test vector illustrating how different encodings yield different bytes.

```http
Authorization: Basic dGVzdDoxMjPCow==
```

Note: **do not append** `charset=UTF-8` after the Base64 token on the request header; the Basic `Authorization` field uses `token68`, leaving no room for a `charset` parameter like the challenge.

## 5. Role of HTTP Basic in Spring Security WebFlux

In a reactive application, there is no Servlet `BasicAuthenticationFilter` running on `HttpServletRequest`. Spring Security uses a **`WebFilter`** system and reactive APIs.

Idealized flow:

```text
HTTP request: Authorization: Basic <encoded-user-pass>
         |
         v
Spring Security WebFilter chain
         |
         v
AuthenticationWebFilter  (HTTP Basic)
         |
         v
ServerHttpBasicAuthenticationConverter
    - Inspects Authorization header
    - Recognizes Basic scheme
    - Base64-decodes user-pass
    - Creates an UNAUTHENTICATED Authentication
         |
         v
ReactiveAuthenticationManager
    - Looks up UserDetails via ReactiveUserDetailsService
    - Matches password via PasswordEncoder
    - Checks account status
         |
       +-------------------------+
       |                         |
    Success                   Failure
       |                         |
       v                         v
Authenticated Authentication  AuthenticationException
       |                         |
       v                         v
SecurityContext/Reactor      Failure handler /
Context for downstream       authentication entry point
       |                         |
       v                         v
AuthorizationWebFilter          usually 401
       |
    +--+------------------------+
    |                           |
authorized                 unauthorized
    |                           |
controller                  AccessDeniedException
    |                           |
200/other                   ExceptionTranslationWebFilter
                                |
                             usually 403
```

The diagram intentionally omits many other filters (CSRF, headers, CORS, request cache, context persistence...) and does not claim every error comes from a single filter. In WebFlux:

- `ServerHttpSecurity`: where WebFlux security is configured.
- `SecurityWebFilterChain`: the WebFilter chain serving matched requests.
- `ServerHttpBasicAuthenticationConverter`: reads Basic credentials from the HTTP exchange.
- `AuthenticationWebFilter`: orchestrates the reactive authentication process.
- `ReactiveAuthenticationManager`: decides whether the username/password are valid.
- `ReactiveUserDetailsService` / `MapReactiveUserDetailsService`: user information source (in-memory for demos).
- `PasswordEncoder`: verifies the password against the stored hash. **Do not** compare raw Base64 with the DB.
- `ReactiveSecurityContextHolder`: helps read the authenticated `Authentication` in the downstream Reactor Context.
- `AuthorizationWebFilter`: enforces rules like `authenticated()`, `hasRole(...)`, `hasAuthority(...)`, etc.
- `ExceptionTranslationWebFilter`: handles authorization denial errors based on authentication state, usually routing to the challenge or 403.

**Key point:** `Authorization` is a header present on **every request that the client proactively sends**. The Basic protocol does not force the server to issue a JWT or session. Depending on configuration, Spring Security may integrate a context repository/session; do not assume every app with Basic enabled is automatically stateless.

### 5.1. Comparing Basic with Bearer and form login

| Criterion | HTTP Basic | Bearer token/JWT | Form login/session |
| --- | --- | --- | --- |
| Typical header/flow | `Authorization: Basic <base64(user:pass)>` | `Authorization: Bearer <token>` | Form POST login, then typically sends a session cookie |
| Credential sent on request | Username/password represented in Base64 | Access token | Session cookie/ID after login |
| Server-issued token required? | **No** | Usually **Yes** | Has session/cookie if session-based |
| How server verifies | Password hashing/user store or auth backend | Signature/introspection, expiry, scopes | Session store/identity |
| If compromised | Leaks the actual password (may be reused) | Leaked token can be used until expired/revoked | Leaked session/cookie can be hijacked |
| Suitable use cases | Tooling, internal APIs over HTTPS, simple controlled cases | APIs needing tokens, clear expiry/scopes | Browser-based web apps with sessions |

**Do not use Basic as a complete replacement for OAuth2/OIDC/MFA** in products needing modern login, federated login, mobile devices, token lifecycles, or cross-service authorization. Basic can fit certain cases but does not inherently provide rate limiting, session management, OAuth scopes, or MFA.

## 6. Plain Java 17: manually building and explaining the header per RFC 7617

This example runs **without Spring Boot**; the goal is to clarify the wire format. All credentials below are public RFC test vectors; **do not use them with real accounts**.

### File `BasicHeaderExample.java`

```java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public final class BasicHeaderExample {

    public static void main(String[] args) {
        String userId = "Aladdin";
        String password = "open sesame";

        String userPass = userId + ":" + password;
        String token = Base64.getEncoder().encodeToString(
            userPass.getBytes(StandardCharsets.UTF_8));
        String header = "Basic " + token;

        // Print the header only because this is a public test vector with no real secret.
        System.out.println("Authorization: " + header);

        String afterScheme = header.substring("Basic ".length());
        String decoded = new String(
            Base64.getDecoder().decode(afterScheme),
            StandardCharsets.UTF_8
        );

        int firstColon = decoded.indexOf(':');
        String decodedUser = decoded.substring(0, firstColon);
        String decodedPassword = decoded.substring(firstColon + 1);

        System.out.println("user-id=" + decodedUser);
        System.out.println("password-matches="
            + decodedPassword.equals("open sesame"));

        // Passwords containing colons are still valid: split only on the first one.
        String valueWithColons = "reader:a:b:c";
        int separator = valueWithColons.indexOf(':');
        String parsedUser = valueWithColons.substring(0, separator);
        String parsedPassword = valueWithColons.substring(separator + 1);

        System.out.println("colon-user=" + parsedUser);
        System.out.println("colon-password=" + parsedPassword);
    }
}
```

Save the file and run:

```bash
javac BasicHeaderExample.java
java BasicHeaderExample
```

**Exact stdout:**

```text
Authorization: Basic QWxhZGRpbjpvcGVuIHNlc2FtZQ==
user-id=Aladdin
password-matches=true
colon-user=reader
colon-password=a:b:c
```

**Lessons from the example:**

- `Base64.getEncoder()` uses standard RFC 4648 Base64.
- `getBytes(StandardCharsets.UTF_8)` chooses how text is converted to bytes. With the ASCII test vector, the result matches the RFC.
- Taking the substring after `"Basic "` only makes sense in an example where **the code builds a valid header itself**. For requests received over the network, you must safely handle whitespace/scheme/token, malformed Base64, header length limits, encoding, missing colons, and edge cases. **Do not build a production authenticator from just this snippet**.
- `decoded.indexOf(':')` finds the first separator instead of truncating the password at the second `:`.
- A decodable Base64 value **does not prove** the password is correct. Credentials must be handed off to an authentication manager and password encoder.
- Printing the token is strictly for the RFC test vector. **Never print real Authorization headers** to the console, logs, or exception messages.

## 7. Complete WebFlux Project: HTTP Basic on a reactive API

Choose Java **17+**, Maven, and Spring Boot **3.5.16** for a concrete release baseline; Spring Boot 3.5.16 is the final OSS-supported release of the 3.5.x branch, **not a choice for new production systems in 2026**. For real systems, pick a Spring Boot branch still under OSS support (e.g., 4.x), then update APIs/versions per the migration guide. The examples below use Spring Security 6.x as managed by Boot 3.5.x.

File structure:

```text
reactive-http-basic-demo/
├── pom.xml
└── src/
    ├── main/java/demo/basic/
    │   ├── BasicApplication.java
    │   ├── SecurityConfig.java
    │   └── ApiController.java
    └── test/java/demo/basic/
        └── BasicAuthenticationTests.java
```

### 7.1. `pom.xml`

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
    <artifactId>reactive-http-basic-demo</artifactId>
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
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
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

`spring-boot-starter-webflux` brings WebFlux/Reactor onto the classpath; `spring-boot-starter-security` integrates WebFlux security; `starter-test` and `spring-security-test` are used to run tests. Do not add Servlet's `spring-boot-starter-web` just for HTTP Basic; the goal of this lesson is **reactive WebFilter**.

### 7.2. `src/main/java/demo/basic/BasicApplication.java`

```java
package demo.basic;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BasicApplication {
    public static void main(String[] args) {
        SpringApplication.run(BasicApplication.class, args);
    }
}
```

### 7.3. `src/main/java/demo/basic/SecurityConfig.java`

```java
package demo.basic;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        // Hard-coded accounts/passwords are for learning environments only.
        // Passwords in UserDetails are still stored as BCrypt hashes.
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader123"))
            .roles("READER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin123"))
            .roles("ADMIN")
            .build();

        UserDetails colon = User.withUsername("colon")
            .password(encoder.encode("part:two"))
            .roles("READER")
            .build();

        return new MapReactiveUserDetailsService(reader, admin, colon);
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
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http, ReactiveAuthenticationManager manager) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public").permitAll()
                .pathMatchers("/api/admin").hasRole("ADMIN")
                .pathMatchers("/api/private", "/api/me").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(basic -> basic.authenticationManager(manager))
            .formLogin(form -> form.disable())
            .build();
    }
}
```

**Why is this configuration written this way?**

1. `@EnableWebFluxSecurity` configures Spring Security for **Spring WebFlux**; the output bean is `SecurityWebFilterChain`.
2. `httpBasic(basic -> basic.authenticationManager(manager))` enables Basic and specifies the **reactive authentication manager** that verifies credentials. This is the modern lambda DSL of Spring Security 6, not Servlet `HttpSecurity`.
3. `MapReactiveUserDetailsService` is an in-memory user store. `UserDetailsRepositoryReactiveAuthenticationManager` retrieves UserDetails and matches the password via `PasswordEncoder`.
4. `BCryptPasswordEncoder` hashes passwords in the demo's user store. The server receives the **raw password** via Basic and matches it against the **BCrypt hash**, never treating Base64 as a password hash.
5. `roles("ADMIN")` creates the `ROLE_ADMIN` authority; `hasRole("ADMIN")` requires this authority. A validly logged-in `reader` user still receives 403 at `/api/admin`.
6. User `colon` with password `part:two` illustrates that **colons in passwords remain valid**: Basic takes the username before the first colon, and the password is the remainder.
7. `formLogin(form -> form.disable())` disables form login redirects so the example focuses on Basic; the application remains protected at the HTTP layer.
8. The example only has GET endpoints, so CSRF is not disabled; if adding POST or browser apps that auto-send Basic credentials, evaluate CSRF according to the client model.

**Production note:** BCrypt hashing in the demo happens at startup because hard-coded passwords are only for practice. Real systems do not put actual passwords in source code; fetch hashes from a secure user repository, enforce HTTPS, monitor authentication failures, and protect against brute force.

### 7.4. `src/main/java/demo/basic/ApiController.java`

```java
package demo.basic;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class ApiController {

    @GetMapping("/public")
    public Mono<String> publicInfo() {
        return Mono.just("public OK");
    }

    @GetMapping("/private")
    public Mono<String> privateInfo() {
        return Mono.just("private OK");
    }

    @GetMapping("/admin")
    public Mono<String> adminInfo() {
        return Mono.just("admin OK");
    }

    @GetMapping("/me")
    public Mono<String> currentUser() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName)
            .map(name -> "user=" + name);
    }
}
```

In `/api/me`, the username is obtained from **Spring Security's Authentication**, rather than reading `Authorization` and manually Base64-decoding it in the controller. When `ReactiveAuthenticationManager` authenticates successfully, Spring Security provides the SecurityContext to the reactive chain. If you manually decode a Basic header inside a business controller, you risk bypassing hash verification, account status checks, authorization, and framework protections.

### 7.5. Which clients use this header?

There are three calls equivalent **in intent** when credentials are ASCII:

```bash
# Client automatically constructs the Basic header via curl.
curl -i -u reader:reader123 http://localhost:8080/api/private
```

```java
// Snippet inside a WebTestClient/WebClient request, not a standalone Java file:
.headers(headers -> headers.setBasicAuth("reader", "reader123"))
```

```http
GET /api/private HTTP/1.1
Host: localhost:8080
Authorization: Basic <base64-of-reader:reader123>
```

The final HTTP snippet is a **structural template**, not a header you can send verbatim: the placeholder must be replaced with the actual Base64 of `reader:reader123`. Use `HttpHeaders.setBasicAuth` or a client library to avoid formatting mistakes. Do not accidentally copy the test password `reader123` into other systems.

## 8. Testing HTTP Basic with WebTestClient

To test the Basic mechanism, you must send a **real Authorization header** or use the `setBasicAuth` helper; a `mockUser()` that already supplies an Authentication does not prove that the Base64 parser or password matching works.

The following test suite uses `@SpringBootTest` to load the real `SecurityConfig`, then `WebTestClient.bindToApplicationContext(...).apply(springSecurity())` to run the WebFilter chain in tests without opening a real network port.

### `src/test/java/demo/basic/BasicAuthenticationTests.java`

```java
package demo.basic;

import java.nio.charset.StandardCharsets;
import java.util.Base64;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class BasicAuthenticationTests {

    @Autowired
    ApplicationContext applicationContext;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient
            .bindToApplicationContext(applicationContext)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void publicGetWorksWithoutCredentials() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public OK");
    }

    @Test
    void protectedGetWithoutHeaderReturns401() {
        client.get().uri("/api/private")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().exists(HttpHeaders.WWW_AUTHENTICATE);
    }

    @Test
    void correctUsernameAndPasswordAreAccepted() {
        client.get().uri("/api/private")
            .headers(h -> h.setBasicAuth("reader", "reader123"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("private OK");
    }

    @Test
    void wrongPasswordReturns401() {
        client.get().uri("/api/private")
            .headers(h -> h.setBasicAuth("reader", "wrong"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void unknownUsernameReturns401() {
        client.get().uri("/api/private")
            .headers(h -> h.setBasicAuth("nobody", "reader123"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedUserWithoutRoleGets403() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth("reader", "reader123"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminWithCorrectRoleGets200() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth("admin", "admin123"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin OK");
    }

    @Test
    void basicHeaderCanBeBuiltByBase64() {
        String original = "reader:reader123";
        String encoded = Base64.getEncoder().encodeToString(
            original.getBytes(StandardCharsets.UTF_8));

        client.get().uri("/api/private")
            .header(HttpHeaders.AUTHORIZATION, "Basic " + encoded)
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("private OK");
    }

    @Test
    void passwordMayContainColons() {
        client.get().uri("/api/private")
            .headers(h -> h.setBasicAuth("colon", "part:two"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("private OK");
    }

    @Test
    void securityContextProvidesAuthenticatedName() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth("reader", "reader123"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("user=reader");
    }

    @Test
    void publicUrlWithWrongBasicCredentialsMayStillFail() {
        client.get().uri("/api/public")
            .headers(h -> h.setBasicAuth("reader", "wrong"))
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
```

These **11 tests** clearly separate three layers:

- **Wire format:** `basicHeaderCanBeBuiltByBase64` manually sends `Authorization: Basic <encoded>`, without using `mockUser`.
- **Authentication:** With/without credentials, unknown username, wrong password, password containing `:`.
- **Authorization:** Valid user missing `ROLE_ADMIN` returns 403; valid admin returns 200.
- **Reactive context:** `/api/me` reads the user authenticated by Spring Security.
- **Filter behavior:** A wrong Basic header on a `permitAll` path can still trigger the authentication filter and lead to 401. The test confirms behavior under the current configuration.

If you replace Basic with JWT or session login, you must change both how credentials are sent and how authentication is tested; testing only `mockUser` is insufficient to prove header parsing or password hash matching.

### 8.1. Expected response matrix

| HTTP request | Input | Expected HTTP status | Success body |
| --- | --- | --- | --- |
| `GET /api/public` | No Basic | 200 | `public OK` |
| `GET /api/private` | No Basic | **401** | Not fixed; has `WWW-Authenticate` |
| `GET /api/private` | `reader:reader123` | 200 | `private OK` |
| `GET /api/private` | `reader:wrong` | **401** | Not fixed |
| `GET /api/private` | `nobody:reader123` | **401** | Not fixed |
| `GET /api/admin` | `reader:reader123` | **403** | Not fixed |
| `GET /api/admin` | `admin:admin123` | 200 | `admin OK` |
| `GET /api/private` | Base64 of `reader:reader123` | 200 | `private OK` |
| `GET /api/private` | `colon:part:two` | 200 | `private OK` |
| `GET /api/me` | `reader:reader123` | 200 | `user=reader` |
| `GET /api/public` | `reader:wrong` | **401** | Not fixed |

Do not assert the JSON body of 401/403 errors in this example: Spring Security/Boot may change error bodies depending on exception handling and content negotiation. This lesson focuses on **Basic credentials and status/challenge**; if designing unified REST error JSON, configure a dedicated handler and test the corresponding headers/status/body.

## 9. Running with Maven and curl

### 9.1. Running the test suite

Requirements: **Java 17+** and Maven compatible with Spring Boot 3.5. From the directory containing `pom.xml`:

```bash
java -version
mvn -version
mvn clean test
```

Maven Surefire is expected to report **11 tests, 0 failures, 0 errors**, followed by `BUILD SUCCESS`. Timings, plugin output, and provider names may vary by environment. This is the **expected result from the code**, not a claim that it was executed in every environment.

If tests fail to start, check the Java version, `spring-boot-starter-webflux`, `spring-boot-starter-security`, `spring-boot-starter-test`, and `spring-security-test`. The classes reside under the same root package `demo.basic` as `@SpringBootApplication`.

### 9.2. Starting the WebFlux server

```bash
mvn spring-boot:run
```

By default in this example, the server listens on `localhost:8080` if the port is not changed in configuration.

Open a second terminal and call:

```bash
# No credentials: public -> 200; private -> 401.
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/private

# Valid/invalid Basic credentials.
curl -i -u reader:reader123 http://localhost:8080/api/private
curl -i -u reader:wrong http://localhost:8080/api/private

# Valid identity but missing role -> 403.
curl -i -u reader:reader123 http://localhost:8080/api/admin

# Admin with sufficient permissions -> 200.
curl -i -u admin:admin123 http://localhost:8080/api/admin

# Password containing :; username is colon, password is part:two.
curl -i -u colon:part:two http://localhost:8080/api/private

# Inspect the identity authenticated by Spring Security.
curl -i -u reader:reader123 http://localhost:8080/api/me
```

On Windows PowerShell, you may need to use `curl.exe` instead of `curl`. For real APIs, use HTTPS and secure client credential-supply mechanisms; `-u user:password` in a shell command can be saved in command history or exposed via process inspection. Do not use `curl -v`/debug proxies on real credentials if logs are collected; filter out sensitive headers.

### 9.3. Checking the challenge from the server

```bash
curl -i http://localhost:8080/api/private
```

A typical response:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Realm"
```

The `realm` value, extra headers, and body are not guarantees of the example; framework/configuration may differ. What the official test verifies is **401** and the presence of **`WWW-Authenticate`**, not a fixed realm.

### 9.4. Do not mistake `curl -u` for "password encryption"

When using `-u reader:reader123`, the client constructs the Basic header with Base64. This is **encoding of user-pass** for wire representation. There is no password hash from the client: **hashes are stored on the server**, while the server receives the password sent by the client over an HTTPS channel and verifies it with BCrypt. Only when TLS protects the connection are credentials encrypted in transit.

## 10. How to send Basic in Java HTTP clients

### 10.1. Spring's `HttpHeaders`

In Spring WebFlux `WebClient` or `WebTestClient`, prefer the header-building API instead of manually concatenating Base64:

```java
// Snippet used inside a WebClient/WebTestClient builder/request:
.headers(headers -> headers.setBasicAuth("reader", "reader123"))
```

For Unicode credentials, choose an explicit charset and verify the server actually supports it:

```java
.headers(headers ->
    headers.setBasicAuth("nguoi-dung", "mật-khẩu",
                         java.nio.charset.StandardCharsets.UTF_8))
```

This is a snippet placed inside a request call that exposes the `headers(Consumer<HttpHeaders>)` API, not a standalone Java file. If client/server want RFC-compliant Unicode support, verify both `WWW-Authenticate: Basic ..., charset="UTF-8"` and normalization. Do not assume `charset` is automatically added to the request header.

### 10.2. WebClient used for an HTTP Basic API

A snippet placed inside a service method can be written as:

```java
WebClient client = WebClient.builder()
    .baseUrl("https://api.example.test")
    .build();

Mono<String> response = client.get()
    .uri("/api/private")
    .headers(headers -> headers.setBasicAuth("reader", "reader123"))
    .retrieve()
    .bodyToMono(String.class);
```

This snippet **illustrates the API**, requiring imports for `org.springframework.web.reactive.function.client.WebClient` and `reactor.core.publisher.Mono`, along with credentials supplied through a secret management mechanism in a real application. `https://api.example.test` is a fake host, not a directly callable endpoint. Avoid attaching a Basic header as a default on a `WebClient` that may be used to call **multiple different origins**, due to the risk of sending credentials to the wrong destination.

### 10.3. `java.net.http.HttpClient` (Java 17)

The JDK does not require Spring to send the header:

```java
String encoded = java.util.Base64.getEncoder().encodeToString(
    "reader:reader123".getBytes(java.nio.charset.StandardCharsets.UTF_8));

java.net.http.HttpRequest request = java.net.http.HttpRequest
    .newBuilder(java.net.URI.create("https://api.example.test/api/private"))
    .header("Authorization", "Basic " + encoded)
    .GET()
    .build();
```

This snippet builds an `HttpRequest` and **does not perform a network request**. When actually sending the request, use `HttpClient` with appropriate default TLS, handle 401/403 statuses, and avoid logging the header. Prefer libraries/credential providers that support standard Basic when possible, rather than hand-rolling headers for every integration.

## 11. Security issues to address beyond Base64

### 11.1. Always use HTTPS/TLS and validate certificates

- Base64 is immediately reversible; **Basic over plaintext HTTP is insecure**.
- Use HTTPS with proper certificate and hostname validation. Avoid disabling certificate verification just to "make it work".
- In systems with reverse proxies/TLS termination, protect the hop from the proxy to the application and avoid logging `Authorization` at the proxy.
- Configure HSTS where appropriate for the website and infrastructure; HTTP → HTTPS redirects must be designed not to leak credentials in the initial HTTP request. Ideally, clients only send credentials to HTTPS URLs from the start.

### 11.2. Basic sends the password repeatedly, with no per-request expiry/scope

The client may send the same username/password on every protected request. If the password is compromised, an attacker can keep using it until the password is changed/account revoked or other controls take effect. HTTP Basic does not inherently issue short-lived tokens, refresh tokens, rotation, or scope differentiation.

Real systems should have password policies, MFA when required, brute-force protection/rate limiting, credential rotation, anomaly alerting, access restrictions, and ways to change/lock accounts.

### 11.3. Browsers can cache/replay credentials

Browsers can cache Basic credentials for the corresponding **protection space**. A "Basic logout" mechanism is not equivalent to clearing an explicit server session like form login. Sending 401 or changing the realm is not always a reliable logout method across all browsers.

If the frontend runs in a browser and requires logout, multi-session/multi-device support, MFA, or token policy enforcement, an architecture based on sessions/OIDC/OAuth2 is usually more appropriate than plain HTTP Basic.

### 11.4. CSRF and CORS do not disappear just because Basic is used

- **CSRF:** Browsers can automatically re-attach HTTP Basic credentials to requests within the protection space. For state-changing operations from a browser, CSRF still needs to be evaluated. Do not disable CSRF just because "the API uses Basic" or because a POST test returned 403.
- **CORS:** Cross-origin JavaScript with an `Authorization` header can trigger a preflight; configure `OPTIONS`, allowed origins, methods, headers, and credential policy properly. CORS is not authentication, and `Access-Control-Allow-Origin` does not prove identity.
- **XSS:** If a page has XSS or client JavaScript mismanages credentials, an attacker can hijack sessions/credentials. TLS does not fix XSS.

### 11.5. Common places secrets leak

| Place | Risk | Prevention |
| --- | --- | --- |
| HTTP access log / reverse proxy | Logs `Authorization: Basic <...>`, easily decoded | Redact the `Authorization` header; control log retention |
| APM/trace/spans | Collects all request headers as tags | Do not instrument secrets; use an allowlist |
| Shell history/process list | `curl -u user:password` stays in command | Use secure secret retrieval mechanisms; do not put passwords on production command lines |
| Ticket/screenshot | Attaches traces containing Base64 | Remove/redact headers before sharing |
| Source code/test fixtures | Committing real passwords | Use dummy credentials for tests; centralized secret management for production |
| HTTP redirect | Client might send credentials to unintended URLs if misconfigured | Restrict origins/redirects; do not auto-forward Authorization to other hosts |
| Non-TLS client connection | Eavesdropped on the network | Enforce HTTPS with certificate validation |

### 11.6. Rate limiting, user enumeration, and password storage

A Basic API often exposes authentication on many requests. You need to:

- Use appropriate slow **password hashing** such as BCrypt/Argon2id; never store raw passwords or raw Base64.
- Handle non-existent usernames and wrong passwords consistently, avoiding responses that leak information enabling account enumeration.
- Rate-limit and detect credential stuffing. Do not allow unlimited wrong-password retries from clients.
- Handle identity provider/database errors differently from wrong passwords; do not turn service outages into `401 BAD_CREDENTIALS` by default.
- Maintain HTTPS, encrypt connections to critical backends, and audit at a level that excludes secrets.

## 12. Common mistakes when writing and using Authorization: Basic

| Symptom | Typical cause | How to fix |
| --- | --- | --- |
| Sending `Authorization: reader:reader123` yields 401 | Missing `Basic` and Base64 | Use `setBasicAuth`/`curl -u` |
| Using `Authorization: Bearer <base64>` | Confusing Bearer scheme with Basic | Use `Basic <token>`; Bearer is for tokens |
| Header uses Base64 of **password** without username | Wrong user-pass structure | Encode `username + ":" + password` |
| Username containing `:` causes login failure | RFC uses the first `:` as separator | Choose a user-id without `:` |
| Password containing `:` gets truncated after it | Custom decoder improperly calls `split(":")` | Split only at the first `:` |
| UTF-8 credentials yield 401 | Client-server encoding/normalization mismatch | Check `charset="UTF-8"` challenge, `setBasicAuth(..., UTF_8)` overload, and test vectors |
| `charset=UTF-8` appended after Base64 in request | Confusing challenge param with credentials | Put charset only in `WWW-Authenticate` per RFC |
| Thinking readable Base64 means authenticated | Only decoded, password not verified yet | Use `ReactiveAuthenticationManager` and `PasswordEncoder` |
| Sending no Basic yields 401 | Protected endpoint requires authentication | Inspect `WWW-Authenticate`; supply valid credentials |
| Correct password still yields 403 | Login succeeded but missing role | Check authorities and `hasRole`/`hasAuthority` |
| `SecurityFilterChain` config does not run in WebFlux | Using Servlet API instead of reactive API | Use `SecurityWebFilterChain` and `ServerHttpSecurity` |
| Public endpoint with wrong Basic returns 401 | Authentication filter processes submitted credentials before controller | Test public+wrong credentials separately |
| `WWW-Authenticate` missing due to custom error handler | Handler creates 401 without keeping proper challenge | Restore proper Basic challenge and test the header |
| Browser API returns 403 on POST | Likely CSRF, not role | Identify the source of 403; use the proper CSRF strategy |
| Tests using `mockUser` always pass | Tests do not send a real Basic header | Add tests with `setBasicAuth`/real Base64 header |
| Request has right header but Basic does not work | Different security matcher/chain selected or Basic disabled | Check `.httpBasic(...)`, `securityMatcher`, chain order |
| 401 appears when sending Basic to HTTP | Credentials may still leak even if rejected | Switch to HTTPS immediately; rotate secrets sent over HTTP if exposed |
| Browser won't "logout" of Basic | Browser keeps credentials for the realm/protection space | Design a different auth/session mechanism if strict logout is required |

## 13. Self-check questions and exercises

**Question 1.** Which header belongs to the request, and which belongs to the response?

**Answer:** `Authorization: Basic ...` belongs to the request sent by the client; `WWW-Authenticate: Basic realm="..."` belongs to the server's response, typically paired with status 401.

**Question 2.** Is `QWxhZGRpbjpvcGVuIHNlc2FtZQ==` a securely encrypted secret string?

**Answer:** No. It is the Base64 of `Aladdin:open sesame`, which can be reversed immediately. Basic requires TLS to protect data in transit.

**Question 3.** Given the string `reader:pass:a:b`, what are the username and password?

**Answer:** The username is `reader`, and the password is `pass:a:b`. Only the first colon is the separator.

**Question 4.** Can you send user-id `team:reader` in Basic while preserving the exact username?

**Answer:** No. A username containing `:` is invalid per RFC 7617; the server interprets the part before the first colon as the user-id.

**Question 5.** Does the `Authorization: Basic <base64>` header contain the `charset=UTF-8` parameter?

**Answer:** No. The charset parameter is defined by RFC 7617 for the server's `WWW-Authenticate` challenge. The client uses the agreed-upon charset to produce bytes before Base64 encoding.

**Question 6.** Why might `reader:reader123` receive 403 on `/api/admin`?

**Answer:** Basic authentication may succeed, but `reader` only has `ROLE_READER`, not `ROLE_ADMIN`; authorization denies access.

**Question 7.** Why is `mockUser("reader")` insufficient to test the HTTP Basic mechanism?

**Answer:** Because a mock user supplies an already-authenticated principal, usually bypassing header reading, Base64 decoding, and password matching. You need tests sending real credentials via `setBasicAuth` or headers.

**Question 8.** If an API uses HTTP Basic over HTTPS, is the password automatically hashed on the client side before sending?

**Answer:** Not according to the Basic specification. The client sends the Base64 of the username/password pair; HTTPS encrypts the transport channel, while the server is responsible for verifying the password against the stored hash.

**Question 9.** Why can a request without `Authorization` still return 401, even though the authentication filter did not report "wrong password"?

**Answer:** A request without credentials can reach the authorization step and be rejected for lacking a valid identity; Spring Security's entry point generates 401/challenge. There was no failed authentication attempt from the Basic converter.

**Question 10.** Can you trust that using Basic makes browser-based POST requests immune to CSRF?

**Answer:** No. Browsers can re-send credentials, and CSRF must be evaluated based on actual browser/client behavior and the authentication mechanism in use; do not disable CSRF by default just because of Basic.

### Short exercises

1. Replace the `reader` account in `SecurityConfig` with another username (without `:`) and use a `setBasicAuth` test to verify.
2. Change user `colon`'s password to `a:b:c`; verify the endpoint still returns 200 with `setBasicAuth("colon", "a:b:c")`.
3. Call `/api/admin` with both `reader` and `admin`; explain why the statuses differ even though both authenticated successfully.
4. Add a test checking `WWW-Authenticate` in the 401 response when no credentials are sent; do not compare the exact realm if configuration may vary.
5. Try the `curl -i` command on localhost only with demo accounts. For external environments, switch to HTTPS and avoid exposing credentials in command history.

## 14. Checklist before using Basic in a real project

- [ ] There is a clear business requirement to use Basic instead of bearer tokens, OIDC, or sessions.
- [ ] **HTTPS/TLS is mandatory**; do not skip certificate verification.
- [ ] `Authorization` is redacted in application logs, reverse proxies, tracing, and error reporting.
- [ ] Password policy, password hashing, credential rotation, and rate limiting are in place.
- [ ] Usernames do not contain `:`; Unicode/charset rules between clients and server are tested.
- [ ] The API clearly defines 401/`WWW-Authenticate` and 403 across scenarios.
- [ ] WebFlux uses `SecurityWebFilterChain`, without mixing Servlet classes.
- [ ] Integration tests exist that send **real Basic headers**, testing wrong credentials as well as right role/missing role.
- [ ] Browser Basic caching, CSRF, CORS, and logout expectations have been considered.
- [ ] Do not store passwords, raw Base64, or raw tokens in production test artifacts/logs.
- [ ] Do not rely on Base64 as a security layer; authorization policies are tested independently of authentication.

## 15. Summary and official documentation

**One-sentence summary:** HTTP Basic converts `username:password` into bytes and then Base64, sending it via **`Authorization: Basic <token68>`** in an HTTP request; the server must use HTTPS, verify passwords, and enforce authorization, while **`WWW-Authenticate: Basic realm="..."`** is the challenge from the server when authentication is required.

| Property to remember | Rule |
| --- | --- |
| Scheme | `Basic` |
| String before Base64 | `user-id:password` |
| Colon `:` | First colon is separator; password may contain `:`, username may not |
| Base64 | Encoding, **not encryption** |
| Request header | `Authorization: Basic <encoded>` |
| Challenge response | `401` + `WWW-Authenticate: Basic realm="..."` |
| Wrong credentials | Usually 401 |
| Authenticated but missing role | Usually 403 |
| Unicode charset | Agree explicitly; server may challenge with `charset="UTF-8"` |
| Spring Security reactive | `AuthenticationWebFilter`, `ReactiveAuthenticationManager`, `SecurityWebFilterChain`, `ServerHttpSecurity` |
| Practical protection | TLS + password hashing + logging hygiene + authorization + rate limiting |

**Standard and official references:**

- RFC 7617 – The "Basic" HTTP Authentication Scheme (syntax, charset, realm, Base64): https://www.rfc-editor.org/rfc/rfc7617.html
- RFC 9110 – HTTP Semantics (authentication framework, Authorization, 401/403): https://www.rfc-editor.org/rfc/rfc9110.html
- RFC 4648 – The Base16, Base32, and Base64 Data Encodings: https://www.rfc-editor.org/rfc/rfc4648.html
- Spring Security 6.5 – WebFlux Security: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security 6.5 – `ServerHttpSecurity` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Security 6.5 – `ServerHttpBasicAuthenticationConverter` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/ServerHttpBasicAuthenticationConverter.html
- Spring Security – Password Storage: https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html
- Spring Security 6.5 – Reactive Security Testing: https://docs.spring.io/spring-security/reference/6.5/reactive/test/index.html
- Spring Boot 3.5.16 release notice (version baseline; 3.5 branch is past OSS support): https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/
