# HTTP Basic and the Mechanism for Sending Username and Password via the `Authorization` Header

> **Topic:** Spring Security – fundamentals → **Login and Logout**. This lesson explains HTTP Basic according to RFC 7617, the HTTP challenge–response flow, how Spring Security reads username/password from `Authorization`, configuration for Servlet and WebFlux applications, testing, error handling, and risks around TLS, credential storage, CSRF, and logout. Java examples use JDK 17+, Spring Boot 3.x, and Spring Security 6.x.

## 1. What is HTTP Basic Authentication?

**HTTP Basic Authentication** (shortened to **Basic Auth**) is an HTTP authentication mechanism in which the client sends a `username:password` pair in the `Authorization` header on protected requests. The credential pair is **represented using Base64 encoding**, not secretly encrypted by Base64.

```http
GET /api/me HTTP/1.1
Host: api.example.com
Authorization: Basic cmVhZGVyOnNlY3JldA==
```

In the example above, the Base64 string `cmVhZGVyOnNlY3JldA==` is simply the byte representation of `reader:secret`; anyone who obtains this string can decode it back to the original username and password. **Do not use HTTP Basic over unencrypted HTTP connections in production environments**. HTTPS/TLS is the essential safeguard to protect the header from being read in transit.

Distinguish clearly:

- **Authentication:** verifying whether the credential pair is valid. HTTP Basic is a **way of transmitting credentials**, not an account storage system or a password verification function.
- **Authorization:** which endpoints an authenticated account is allowed to call. Spring Security enforces this with `authorizeHttpRequests`, `authorizeExchange`, `hasRole`, `hasAuthority`, etc.
- **Session:** where the application may store login state. The Basic protocol **does not require** a session cookie; typically, the client can send credentials on every request. Whether an HTTP session is used or not depends on Spring Security and application configuration.
- **Logout:** HTTP Basic **has no standard logout protocol that forces browsers to clear cached credentials**; do not apply expectations of form login/session cookies to Basic.

### 1.1. When is Basic appropriate?

Basic Auth can make sense in constrained contexts such as internal admin tools, demos, scripts, or simple machine-to-machine APIs with HTTPS, user controls, rotation, and good auditing. For applications with multiple clients, delegated permissions, short-lived grants, SSO, MFA, or clear logout UX, consider other mechanisms such as form login/session, OAuth2/OIDC, or short-lived bearer tokens depending on architecture.

Do not choose Basic simply because `Authorization` is easy to construct: every request may resend the real password, so if the credential leaks, the impact can be more severe than leaking a scoped, short-lived access token.

## 2. Exact syntax of `Authorization: Basic ...`

According to **RFC 7617**, the client constructs `user-pass` in order:

1. Take the username and password.
2. Join them at the first colon: `username + ":" + password`.
3. Convert the string to bytes using a character encoding agreed upon by client and server.
4. Encode the bytes with **Base64**.
5. Send the `Authorization` header with authentication scheme `Basic` followed by a single space and the Base64 string.

Formula:

```text
username = "reader"
password = "secret"

user-pass = "reader:secret"
UTF-8 bytes = byte sequence of "reader:secret"
Base64 = "cmVhZGVyOnNlY3JldA=="

Authorization: Basic cmVhZGVyOnNlY3JldA==
```

**Separating colon:** a username **must not contain `:`** in Basic according to the RFC; the server splits at the **first colon**, while the password may still contain `:` afterward. For example, `reader:a:b` has username `reader` and password `a:b`, not username `reader:a` and password `b`.

**Charset is not automatically fixed to UTF-8 for all servers/clients:** RFC 7617 leaves the default encoding unspecified when undeclared for backward compatibility with legacy systems. The server may include the `charset="UTF-8"` parameter in the `WWW-Authenticate` **challenge** header to specify UTF-8 per the RFC; do not attach a `charset` parameter to the `Authorization: Basic ...` header itself. For usernames/passwords with Vietnamese diacritics or Unicode characters, check client, server, and normalization compatibility. ASCII examples like `reader:secret` avoid this issue.

**`Authorization` differs from `Proxy-Authorization`:** the former authenticates with the **origin server**; the latter serves an HTTP proxy requiring authentication and has a separate `407 Proxy Authentication Required` flow. Do not confuse the `WWW-Authenticate` challenge from a server with `Proxy-Authenticate` from a proxy.

## 3. The 401 challenge–response flow over HTTP

HTTP Basic is built on the **HTTP authentication framework**. A request without credentials to a protected resource typically follows this sequence:

```text
┌──────────────────────┐              ┌──────────────────────────┐
│ Client / browser     │              │ Server + Spring Security │
└──────────┬───────────┘              └─────────────┬────────────┘
           │ GET /api/me                           │
           │ (no Authorization)                    │
           ├───────────────────────────────────────►│
           │                                       │
           │ 401 Unauthorized                      │
           │ WWW-Authenticate: Basic realm="API"  │
           │◄───────────────────────────────────────┤
           │                                       │
           │ GET /api/me                           │
           │ Authorization: Basic <base64>         │
           ├───────────────────────────────────────►│
           │                                       │
           │ authenticate credentials → check permissions │
           │◄───────────────────────────────────────┤
           │ 200 OK, or 401/403 depending on result│
```

The diagram shows the **typical flow**, not a requirement that the client wait for 401 before sending credentials. `curl -u` and many HTTP clients can **preemptively send** `Authorization: Basic ...` on the very first request. Some clients/browsers cache credentials per protection space/realm and automatically resend them on later requests.

### 3.1. `WWW-Authenticate` and realm

The response to an unauthenticated client may contain:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Demo API"
Cache-Control: no-store
```

- `401` states that the request has not provided valid authentication for the resource, usually accompanied by a challenge.
- `WWW-Authenticate` indicates the server accepts the `Basic` scheme and may define the protection space (**realm**).
- `realm="Demo API"` is a label/protection space for HTTP authentication; it is **not** a Spring Security role, tenant, or permission.
- Browsers may display a username/password dialog based on the challenge; fetch/XHR and automated clients may handle it differently. Spring Security has specific behavior to avoid triggering browser prompts on certain AJAX requests.
- UTF-8 can be advertised via `WWW-Authenticate: Basic realm="Demo API", charset="UTF-8"` for supporting clients; do not assume every legacy client honors the charset.

### 3.2. Distinguishing 401, 403, and success

| Context | Common result | Explanation |
|---|---|---|
| No `Authorization` sent to protected endpoint | **401** and Basic challenge | No valid credentials yet |
| `Authorization: Basic ...` with wrong password | **401** | Authentication failed; may re-challenge |
| Malformed Basic header or invalid Base64 decoding | **401** or other error handling depending on filter/config | Does not produce valid authentication |
| Valid credentials, insufficient role | **403 Forbidden** | Authenticated, but authorization denies access |
| Valid credentials, authorized, handler succeeds | **2xx** | Allowed through; exact code depends on endpoint |
| Public endpoint with `permitAll()` | Usually no login needed | Still subject to other filters/security measures |

**Do not assume every 401/403 response comes from the Basic filter:** CSRF protection, entry points, custom exception handlers, reverse proxies, resource servers, or application logic can also affect the status. For example, on POST, a request with valid Basic credentials can still get **403 due to a missing CSRF token** if the CSRF guard is enabled.

## 4. Mechanism in Spring Security Servlet

In a Spring MVC/Servlet application using Spring Security 6.x, the main components are:

- `SecurityFilterChain`: the list of Servlet filters protecting requests according to `HttpSecurity` configuration.
- `BasicAuthenticationFilter`: looks for Basic credentials in the request, decodes username/password, builds an unauthenticated `Authentication`, and sends it to the authentication mechanism.
- `AuthenticationManager`: coordinates authentication, typically through `ProviderManager` with a provider supporting username/password.
- `DaoAuthenticationProvider`: can use `UserDetailsService` to locate the user and `PasswordEncoder` to verify the client-supplied password against the stored **hash**.
- `SecurityContextHolder`: provides the verified authentication during Servlet request processing.
- `AuthorizationFilter` or corresponding authorization components: enforces `authenticated()`, `hasRole(...)`, `hasAuthority(...)` rules before the request reaches the controller.
- `ExceptionTranslationFilter` and `BasicAuthenticationEntryPoint`: coordinate initiating the challenge when valid authentication is missing, and handling denial responses according to configuration.

Simplified flow:

```text
HTTP request
  │
  ▼
FilterChainProxy / SecurityFilterChain
  │
  ▼
BasicAuthenticationFilter
  ├─ No Basic header: let pipeline decide next
  └─ Has Basic header: decode username/password
             │
             ▼
         AuthenticationManager
             │
             ▼
        UserDetailsService
        + PasswordEncoder
             │
       ┌─────┴───────┐
       │ valid       │ invalid
       ▼             ▼
 Authenticated    Authentication failure
 Authentication    → 401/challenge
       │
       ▼
  Authorization rule
       │
   ┌───┴────────┐
   │ authorized │ unauthorized
   ▼            ▼
 Controller      403 (typical)
```

**Important:** Basic sends the **raw password inside Base64-encoded credentials** over HTTPS, yet the server **must not store raw passwords**. `PasswordEncoder` checks the request password against a stored hash (such as BCrypt or a recommended password hashing algorithm). Base64 **is not** a `PasswordEncoder` and does not replace BCrypt/Argon2/PBKDF2.

In Spring Security, reading username/password does not force the application to create a form login. Basic can be enabled independently:

```java
http.authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated())
    .httpBasic(Customizer.withDefaults());
```

This is an **excerpt**, not a complete runnable class. You must import `org.springframework.security.config.Customizer` and `HttpSecurity`, define a `SecurityFilterChain` bean, and provide a user/password verification mechanism.

## 5. Runnable Spring Boot MVC example: two users, three endpoints

The example uses **Java 17**, **Maven**, Spring Boot **3.5.7** (a pinned 3.x version for lesson reproducibility), and Spring Security 6.x managed by Spring Boot dependencies. In production deployments, upgrade to a supported, security-patched version; the passwords below are **demo data only**.

Structure:

```text
basic-auth-demo/
├── pom.xml
└── src/main/java/com/example/basicauth/
    ├── BasicAuthApplication.java
    ├── SecurityConfig.java
    └── DemoController.java
```

### 5.1. `pom.xml`

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

    <groupId>com.example</groupId>
    <artifactId>basic-auth-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

### 5.2. `BasicAuthApplication.java`

```java
package com.example.basicauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BasicAuthApplication {

    public static void main(String[] args) {
        SpringApplication.run(BasicAuthApplication.class, args);
    }
}
```

### 5.3. `SecurityConfig.java`

```java
package com.example.basicauth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/ping")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/admin/**")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .anyRequest()
                    .denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("demo-pass-123"))
            .roles("READER")
            .build();

        UserDetails admin = User.withUsername("ops")
            .password(encoder.encode("demo-admin-123"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(reader, admin);
    }
}
```

Configuration breakdown:

1. `.httpBasic(Customizer.withDefaults())` registers Basic authentication in the Servlet security chain.
2. `/public/ping` is `permitAll()`; does not require a Basic header.
3. `GET /api/me` requires `authenticated()`; both `reader` and `ops` pass if they enter the right password.
4. `GET /api/admin/**` requires `hasRole("ADMIN")`, corresponding to `ROLE_ADMIN` with the default prefix. `reader` only has `ROLE_READER` and is therefore denied.
5. `.anyRequest().denyAll()` does not automatically grant access to other endpoints or undescribed methods. This is a **deny by default** choice.
6. `formLogin(...disable())` disables form login in the demo to highlight Basic. It does not mean the app becomes stateless or CSRF is turned off.
7. `InMemoryUserDetailsManager` is used for demos, unit tests, or small scenarios. Both passwords here are **hashed with BCrypt at startup**, but the plaintext values written in source are for learning only. Production must retrieve credentials from a secure store and manage users/roles/rotation properly.
8. There is no `.csrf(csrf -> csrf.disable())`: the demo **keeps default CSRF enabled**. The tested routes use GET only, avoiding the misconception that enabling Basic lets you drop CSRF.

### 5.4. `DemoController.java`

```java
package com.example.basicauth;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/api/me")
    public Map<String, String> me(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }

    @GetMapping("/api/admin/report")
    public String adminReport() {
        return "admin-report";
    }
}
```

The controller only reads the username from the `Authentication` provided by Spring Security; **do not trust a username taken from a custom header or request body**. It does not directly decode the Basic header, because that belongs to the configured filter.

### 5.5. Running with Maven

Inside the `basic-auth-demo` directory:

```bash
mvn spring-boot:run
```

Requires **JDK 17+** and Maven installed. By default, the application runs on `http://localhost:8080` unless `server.port` is changed. Using HTTP here is **only for localhost learning**; production must serve over HTTPS/TLS and check proxy/security headers.

Testing the scenarios:

```bash
# 1. Public endpoint, no credentials required
curl -i http://localhost:8080/public/ping

# 2. Protected endpoint without Authorization
curl -i http://localhost:8080/api/me

# 3. reader with valid password (DEMO DATA ONLY)
curl -i --user reader:demo-pass-123 http://localhost:8080/api/me

# 4. reader without ROLE_ADMIN
curl -i --user reader:demo-pass-123 http://localhost:8080/api/admin/report

# 5. ops with ROLE_ADMIN
curl -i --user ops:demo-admin-123 http://localhost:8080/api/admin/report

# 6. Wrong password
curl -i --user reader:wrong-password http://localhost:8080/api/me
```

Expected result matrix, assuming no custom middleware or proxy modifies the response:

| Request | Credentials | Expected status | Main result |
|---|---|---|---|
| `GET /public/ping` | none | 200 | Body `pong` |
| `GET /api/me` | none | 401 | Basic challenge |
| `GET /api/me` | reader / demo-pass-123 | 200 | JSON containing `"username":"reader"` |
| `GET /api/admin/report` | reader / demo-pass-123 | 403 | Reader lacks `ROLE_ADMIN` |
| `GET /api/admin/report` | ops / demo-admin-123 | 200 | Body `admin-report` |
| `GET /api/me` | reader / wrong-password | 401 | Authentication failed |
| `POST /api/me` | reader / demo-pass-123 | denied | No POST rule; CSRF may also deny first |

**Note:** Never hardcode real passwords in shell commands, committed scripts, CI logs, or process arguments. `curl --user reader` can prompt interactively for a password; the `--user name:password` examples above are only for easy observation with **demo accounts never used outside localhost**. Depending on browser/client settings, challenge/response headers or error bodies may differ; do not assert the entire error message when a test only needs the status.

## 6. Standalone Java 17: constructing and reading a Basic string yourself

To understand Base64 clearly, the program below **does not use Spring** and can be compiled directly with `javac`. File `BasicHeaderDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public class BasicHeaderDemo {

    public static void main(String[] args) {
        String username = "reader";
        String password = "secret"; // Learning value only.

        String userPass = username + ":" + password;
        String token = Base64.getEncoder().encodeToString(
            userPass.getBytes(StandardCharsets.UTF_8)
        );

        System.out.println("Authorization: Basic " + token);

        byte[] decoded = Base64.getDecoder().decode(token);
        System.out.println("Decoded: "
            + new String(decoded, StandardCharsets.UTF_8));
    }
}
```

Compile and run:

```bash
javac BasicHeaderDemo.java
java BasicHeaderDemo
```

Exact standard output:

```text
Authorization: Basic cmVhZGVyOnNlY3JldA==
Decoded: reader:secret
```

Just two lines of Java prove that Base64 is **easily reversible**, with no confidentiality. Never write a production program that prints the `Decoded` line or stores plaintext passwords: this illustrates the risk. Secure password handling requires password hashing, TLS, restricted logging, and dedicated secrets management.

### 6.1. When the client sends Unicode

For example, username `nguyễn` and a password with Unicode: `getBytes(StandardCharsets.UTF_8)` produces UTF-8 bytes, but whether the server reads it properly depends on the agreed charset convention. RFC 7617 does not default all parties to UTF-8 without a charset challenge. If supporting Vietnamese diacritic names, test accented characters, normalization, and access across different clients; avoid decoding with a mismatched charset.

### 6.2. Do not write your own Basic parser in a controller

In practice, there is **no need** to call `Base64.getDecoder()` in a controller when Spring Security already has a Basic authentication filter. Writing a custom parser easily introduces bugs: insecure password comparison, forgetting byte/charset handling, bypassing locking/rate limiting, storing plaintext, hand-rolling challenges, and accidentally leaking credentials in logs. Let Spring Security handle Basic and keep business code working only with verified `Authentication`.

## 7. Real testing with `spring-security-test`

The `curl` requests demonstrate end-to-end behavior. For automated Servlet testing, use `MockMvc` and the `httpBasic(...)` helper from `spring-security-test`. The complete test class below matches the demo's three classes and the `spring-security-test` dependency in `pom.xml`.

File `src/test/java/com/example/basicauth/BasicSecurityTests.java`:

```java
package com.example.basicauth;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;

@SpringBootTest
@AutoConfigureMockMvc
class BasicSecurityTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointDoesNotRequireCredentials() throws Exception {
        mvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void protectedEndpointChallengesAnonymous() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validBasicCredentialsAuthenticateReader() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("reader", "demo-pass-123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("reader"));
    }

    @Test
    void wrongPasswordIsRejected() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("reader", "wrong-password")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedReaderCannotAccessAdmin() throws Exception {
        mvc.perform(get("/api/admin/report")
                .with(httpBasic("reader", "demo-pass-123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void authenticatedAdminCanAccessAdmin() throws Exception {
        mvc.perform(get("/api/admin/report")
                .with(httpBasic("ops", "demo-admin-123")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-report"));
    }
}
```

Run:

```bash
mvn test
```

**Testing significance:** `httpBasic(username,password)` creates a request with a **real `Authorization: Basic ...` header for the test's Spring Security filter**. By contrast, `with(user("reader"))` or `@WithMockUser` injects a mock authentication directly into the test context; those are useful for testing authorization, yet **insufficient** to prove that Basic header decoding + password verification work. Use the fixture that matches the question your test is checking.

Before using in a real product, add tests for:

- Malformed Basic header or invalid Base64.
- Disabled/locked/expired accounts and password rotation.
- Role/authority mapping and ADMIN-only endpoints.
- HTTPS/proxy preserving authentication without logging headers.
- CSRF tokens on unsafe methods when requests originate from a browser.
- Missing `Authorization` alongside another cookie/session: ensure the right authentication policy, avoiding surprises when multiple mechanisms coexist.
- Unicode client tests when the system accepts non-ASCII usernames/passwords.

## 8. HTTP Basic on WebFlux: same header standard, different filter chain

With Spring WebFlux, the **`Authorization: Basic ...` standard does not change**, but the configuration API differs:

| Servlet / MVC | Reactive / WebFlux |
|---|---|
| `HttpSecurity` | `ServerHttpSecurity` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `authorizeHttpRequests` | `authorizeExchange` |
| `requestMatchers` | `pathMatchers` |
| `UserDetailsService` | `ReactiveUserDetailsService` |
| `InMemoryUserDetailsManager` | `MapReactiveUserDetailsService` |
| `SecurityContextHolder` in Servlet | Reactor `Context` / `ReactiveSecurityContextHolder` |

Example configuration class using **Spring Security WebFlux**, not to be placed alongside the Spring MVC demo in a Servlet-running app:

```java
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

@Configuration
@EnableWebFluxSecurity
public class ReactiveBasicConfig {

    @Bean
    SecurityWebFilterChain webFluxSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/public/**").permitAll()
                .anyExchange().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("demo-pass-123"))
            .roles("READER")
            .build();

        return new MapReactiveUserDetailsService(reader);
    }
}
```

The class above is a **Spring configuration** that must live inside a WebFlux application with `spring-boot-starter-webflux` and `spring-boot-starter-security`; it cannot be compiled standalone with `javac` without dependencies. Spring WebFlux handles authentication in a **reactive WebFilter pipeline** instead of Servlet `BasicAuthenticationFilter`; read the current authentication using the appropriate reactive mechanism. If customizing database user lookup, do not manually `block()` or `subscribe()` inside the authentication manager or reactive filter.

Do not rename `httpBasic` when moving to WebFlux — both DSLs have a method named `httpBasic(...)`, but their builders, chains, and implementations are different.

## 9. HTTP Basic, HTTPS, and credential protection

**Why should Basic not be used over HTTP?**

The header:

```http
Authorization: Basic cmVhZGVyOnNlY3JldA==
```

does not hide the username/password. If sent over HTTP, any party able to read traffic on the wire can capture the credentials and reuse them. Even when transmitted over HTTPS, issues such as improper logging, malware-infected clients, untrusted TLS termination, or hardcoded secrets remain separate risks.

Minimum safeguards:

1. **End-to-end HTTPS suited to the infrastructure:** use TLS from client to a trusted origin/reverse proxy; restrict internal HTTP hops and audit ingress/load balancer policies. Proper HSTS helps browsers prefer HTTPS, though it does not replace TLS.
2. **Never log `Authorization`:** configure reverse proxies, application servers, APMs, tracing, exception handlers, HTTP debug logs, and customer support tooling to mask/redact credentials; never write raw Basic tokens to logs.
3. **Use server-side password hashing:** BCrypt/Argon2/PBKDF2 with appropriate policies and cost factors, never storing plaintext or Base64 as a hash.
4. **Rate-limit password attempts:** rate limiting, backoff, brute-force detection, reasonable account lockout; avoid responses that disclose "username exists but password is wrong."
5. **Use separate credentials per client with least privilege:** do not share one admin password across multiple services; maintain issuance, revocation, rotation, and leak-detection processes.
6. **Deny unauthorized endpoints:** having valid Basic credentials does not mean being allowed to call admin APIs. Use `hasRole`/`hasAuthority` and record-level permission checks when needed.
7. **Control HTTP clients:** do not place credentials in `https://user:pass@example.com` URLs, query strings, committed code files, shell history, logs, or untrusted frontend JavaScript.
8. **Do not forward credentials to other domains:** redirects, proxies, or intermediaries must avoid forwarding the `Authorization` header outside the trust boundary.
9. **Monitor and disable accounts:** when a password leaks, change the password, disable the user, and audit all legacy clients; Basic has no built-in token expiration.
10. **Prefer stronger measures when needed:** MFA, mTLS, OAuth2 client credentials, short-lived access tokens, and scoped service accounts may be better than Basic depending on the threat model.

### 9.1. Base64 is not security, even when the string is long

A Basic token is often long, ends with `=`, and looks like an obscure string, yet it is only data encoding. Using the same `username:password` produces the **exact same token** (assuming the same encoding). It adds no entropy, no digital signature, no expiration, and no integrity check. The primary security layer is TLS during transmission and authentication/authorization policy on the server.

### 9.2. Do not confuse with `Bearer`

`Authorization: Bearer <token>` carries an access token under a **different authentication scheme**; the token may be a JWT or opaque token with its own lifetime and authorization scope. Do not decode Bearer by splitting username/password at a colon; do not configure `httpBasic()` and expect it to verify Bearer tokens automatically. For Spring Security's OAuth2 Resource Server, use the appropriate resource server/decoder configuration.

## 10. HTTP Basic and sessions: what is stateless?

Basic does not require a session cookie for the client to prove its identity: each request can carry the username/password pair. Yet that **does not automatically guarantee the Spring application is stateless in every aspect**.

Separate three decisions:

- **Basic protocol:** how credentials are passed in headers and challenges are returned.
- **Spring Security session management:** whether `HttpSession` is created/read to store the security context or related data.
- **Application state:** whether controllers/services use sessions, shopping carts, workflow state, or other interactive state.

For APIs serving only non-browser scripts/clients where you want Spring Security not to use an HTTP session to store authentication, you can additionally configure:

```java
// Snippet inside securityFilterChain(HttpSecurity http).
http.sessionManagement(session ->
    session.sessionCreationPolicy(SessionCreationPolicy.STATELESS)
);
```

Remember to import `org.springframework.security.config.http.SessionCreationPolicy`. This tells Spring Security how to manage the security context/session; it **does not stop Basic passwords from being resent**, does not disable sessions created independently by other application components, and **is not by itself a sufficient reason to disable CSRF**.

### 10.1. Why might Basic need CSRF protection in a browser?

CSRF occurs when a browser **automatically attaches credentials** to a request sent to a server from a cross-site context. With Basic, once a user enters credentials via a browser challenge, the browser **can remember and automatically resend** Basic credentials to the matching protection space. Therefore, according to Spring Security guidance, **browsers using Basic can also be vulnerable to CSRF** even without relying on `JSESSIONID`.

Example:

1. The browser authenticated with Basic to `https://bank.example` and cached the credentials.
2. The user opens a malicious site.
3. That site attempts to trigger a state-changing request to the bank.
4. If the browser automatically sends Basic credentials and the server lacks a CSRF guard, the operation may execute on the user's behalf.

**Do not write `.csrf(csrf -> csrf.disable())` just because the app uses Basic or because you chose `SessionCreationPolicy.STATELESS`.** Evaluate the client environment, whether browsers can auto-send credentials, content types, and cross-site entry points. For pure service-to-service traffic with no browser involved, the CSRF policy may differ after threat-model analysis; document the rationale clearly and test before changing it. In the MVC demo above, keep CSRF enabled and only exercise safe GET/HEAD routes.

## 11. Login, logout, and browser credential caching

Basic differs from form login using a login page and session cookie.

| Aspect | HTTP Basic | Form login + session |
|---|---|---|
| Credential submission point | `Authorization: Basic ...` header | Usually POST login form |
| On subsequent requests | Client/browser may resend the same credentials | Browser sends session cookie |
| Does server need a session to verify user? | Not required | Usually uses a session |
| `WWW-Authenticate` challenge? | Yes, in a typical 401 flow | Usually redirect to login or app-specific response |
| Does standard logout make browser forget credentials? | **No standard guarantee** | Can invalidate server session and clear cookies appropriately |
| Suitable for clear "Logout" UX? | Harder | Usually better suited |
| Risk if credentials are stored long-term by client | Yes, because it is usually the raw password | Yes, though session IDs can be revoked/rotated separately |

**Common mistake:** calling `/logout` and assuming Basic credentials will no longer be sent. If the browser or client still caches the username/password pair, the very next request can immediately re-authenticate. Invalidating `HttpSession` does not clear credentials saved by the browser. Changing the realm, changing the password, or client-specific handling are possible workarounds, but none is a universal, reliable, or UX-friendly logout mechanism.

If true UI login/logout, multi-device security, MFA/SSO, and bounded sessions are required, choose a mechanism specifically designed for sessions or tokens with a proper revocation lifecycle.

## 12. Recognizing common mistakes

1. **Thinking Base64 is secure encryption:** easily decoded; use HTTPS and never expose headers.
2. **Encoding only the password and omitting username from the token:** standard Basic requires `username:password` before Base64.
3. **Sending malformed headers:** `Authorization: Basic token` has one space after the scheme; never send raw `Basic username:password`.
4. **Confusing `Authorization` with `WWW-Authenticate`:** the client sends the former, the server challenges with the latter.
5. **Confusing 401 and 403:** 401 typically requests valid credentials; 403 typically means authenticated but lacking permission or rejected by CSRF/another policy layer.
6. **Not using `PasswordEncoder`:** never store plaintext/Base64 passwords in a database or source code. `User.withDefaultPasswordEncoder()` is unsuitable for production.
7. **Equating Basic with absolute statelessness:** session and application state are separate configuration decisions.
8. **Disabling default CSRF for browser Basic:** browsers can automatically resend credentials, so CSRF risk may persist.
9. **Forgetting endpoint authorization:** `authenticated()` only requires login; `/api/admin/**` still needs `hasRole("ADMIN")` or an equivalent policy.
10. **Skipping negative tests:** testing a valid user does not prove wrong passwords are rejected or regular users are blocked from admin routes.
11. **Believing Basic has standard logout:** browsers/clients can keep caching and sending credentials.
12. **Putting credentials in URLs/curl CLI/logs:** risk of exposure via shell history, process lists, monitoring, access logs, or traces.
13. **Decoding Basic manually in controllers:** easily bypasses Spring Security's auth flow, password hashing, rate limiting, challenges, and auditing.
14. **Ignoring charset/Unicode:** mismatched client/server charsets can break login for accented usernames.
15. **Confusing Basic with Bearer:** do not use the Basic filter to verify OAuth2 JWTs.
16. **Thinking `permitAll()` disables filters:** the Basic filter may still process a sent Authorization header; `permitAll` only says the request needs no permission to pass the authorization gate.
17. **Relying on framework default users/passwords on deploy:** the demo uses fixed in-memory users; production needs real identities, user stores, password rotation, and monitoring.
18. **Porting MVC to WebFlux by copying config:** same header, but security layer, security context, and repository APIs differ.
19. **Overlooking reverse proxies:** an intermediary may log, strip, or mis-forward headers; test end-to-end over HTTPS.
20. **Pasting Basic headers into reports/tickets:** anyone viewing them can decode the password; always redact before sharing.

## 13. Checklist for deploying an API with Basic

- [ ] Identify the client: browser, script, mobile app, or service-to-service; is Basic truly a better fit than tokens/sessions?
- [ ] Enforce HTTPS/TLS along the path from client to trusted system; never transmit credentials over HTTP in production.
- [ ] Do not emit `Authorization` into logs, traces, metrics labels, error responses, or publicly accessible support artifacts.
- [ ] Username/password verified by `AuthenticationManager` and a proper provider; stored passwords use a strong hash.
- [ ] Accounts, roles, authorities, and resource-level permissions are enforced independently of Basic authentication success.
- [ ] Open only intended endpoints, specific matchers first; include `anyRequest().denyAll()` or an explicitly reviewed fallback.
- [ ] 401/WWW-Authenticate and 403 are tested for mechanism and authorization; errors do not leak account details.
- [ ] Have rate limiting, brute-force monitoring, credential rotation/revocation, and locked-account handling.
- [ ] If browsers can auto-send credentials, evaluate CSRF; do not disable it assuming Basic is inherently safe.
- [ ] Do not assume Basic has standard logout; logout UX needs another mechanism or client credential management policy.
- [ ] For stateless servers, configure session management explicitly, while still evaluating application state/CSRF separately.
- [ ] Test in Java/MockMvc with real Basic headers, not just mock users; cover wrong password and missing role cases.
- [ ] If using Unicode, standardize and test charset/normalization per RFC and real browsers/clients.
- [ ] If using WebFlux, use `ServerHttpSecurity` and a reactive user store without blocking the reactive pipeline.

## 14. References

- [RFC 7617 — The 'Basic' HTTP Authentication Scheme](https://www.rfc-editor.org/rfc/rfc7617): `username:password` format, Base64, realm, charset, and Basic security limitations.
- [Spring Security 6.5 — Basic Authentication (Servlet)](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/basic.html): `BasicAuthenticationFilter`, `WWW-Authenticate`, challenge handling, `AuthenticationManager`.
- [Spring Security — Username/Password Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/): `httpBasic`, `UserDetailsService`, and password verification mechanisms.
- [Spring Security — CSRF and stateless browser applications](https://docs.spring.io/spring-security/reference/features/exploits/csrf.html): browsers can automatically send HTTP Basic credentials and thus remain vulnerable to CSRF.
- [Spring Security 6.5 — WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html): configuring `SecurityWebFilterChain`, `ServerHttpSecurity`, and `httpBasic`.

**Key takeaway:** HTTP Basic transmits **Base64-encoded** `username:password` in the `Authorization` header, often repeated per request; **Base64 does not conceal passwords**. Spring Security uses filters, authentication manager/providers, password encoders, and authorization rules to process it. Only use Basic over **HTTPS**, never log the header, enforce roles/permissions on the server, and recognize that browser caching, CSRF, sessions, and logout are separate concerns that Basic does not solve on its own.