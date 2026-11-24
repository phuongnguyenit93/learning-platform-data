# Configuring HTTP Basic, Realm, and WWW-Authenticate in Spring Security (Servlet)

## 1. Objectives and Scope

After this lesson, you will be able to:

- Enable HTTP Basic in a `SecurityFilterChain` using `HttpSecurity.httpBasic(...)`.
- Properly understand both directions of the protocol: the client sends `Authorization: Basic ...`; the server uses `WWW-Authenticate: Basic realm="..."` to request login credentials.
- Rename the `realm`, understand the role of `BasicAuthenticationEntryPoint`, and avoid confusing a realm with an authorization mechanism.
- Distinguish scenarios returning `401 Unauthorized`, `403 Forbidden`, and the fact that `permitAll()` endpoints do not require login.
- Test manually, write automated tests, and identify the specific security risks of Basic Authentication.

The examples use **Spring Security for Servlet/Spring MVC applications**, the modern `SecurityFilterChain` style, and **Java 17+ / Spring Boot 3.x**. Reactive/WebFlux configurations use `ServerHttpSecurity` and do not use the Servlet code below as-is.

## 2. What Does HTTP Basic Consist Of?

HTTP Basic (RFC 7617) is an HTTP-layer authentication mechanism using a **username/password** pair. It does not issue access tokens on its own, has no form-based login flow, and does not encrypt passwords. For each request requiring authentication, the client sends an HTTP header:

```http
GET /api/profile HTTP/1.1
Host: localhost:8080
Authorization: Basic <Base64(username:password)>
```

- The part after `Basic ` is the Base64 encoding of `username:password` (the first colon separates username from password). **Base64 is only representation encoding, not encryption**: anyone who can read the header can recover the login credentials.
- Clients such as `curl -u`, Postman, or browsers can construct the header automatically; you do not need to write Base64 by hand.
- The server verifies the username/password through `AuthenticationManager` and the corresponding `AuthenticationProvider`, and only then checks access permissions.
- Basic is suited for small systems, controlled integration tasks, or learning scenarios; in production, you must use HTTPS and consider mechanisms that do not resend long-lived passwords on every request.

### Two Easily Confused Headers

| Header | Sender | Purpose |
|---|---|---|
| `Authorization: Basic <credentials>` | Client → Server | Supplies the Base64-encoded username/password to authenticate the request |
| `WWW-Authenticate: Basic realm="Learning API"` | Server → Client, typically with `401` | Announces the authentication scheme required by the resource and the protection space (`realm`) |

A minimal exchange:

```http
GET /api/profile HTTP/1.1
Host: localhost:8080

HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Learning API"
```

The client can resend the request with `Authorization: Basic ...`. When the credentials are valid, the server continues processing the endpoint; if the password is wrong, the result is typically `401` again. The HTTP snippets above **illustrate the relevant lines**, not all actual headers or bodies.

## 3. What Does Realm Mean?

`realm` is a string describing the **protection space** advertised by the server in the challenge, such as `Learning API`, `Partner Portal`, or `Internal Reports`. Browsers can use the scheme, origin, and realm to distinguish or contextualize login prompts or reuse credentials.

Key points to understand correctly:

- `realmName("Learning API")` determines the realm string that appears in `WWW-Authenticate` when Spring Security issues a Basic challenge.
- Changing the realm **does not create** a separate user database, a separate `AuthenticationManager`, a new role, or a tenant boundary. Who can log in is still decided by the authentication system; who can access resources is still decided by authorization rules.
- The realm is not included in `Authorization: Basic ...` sent back by the client; `BasicAuthenticationFilter` validates credentials and does not use the realm as an identity proof field.
- If you need to separate API areas with different authentication methods or policies, design separate `SecurityFilterChain` beans with appropriate `securityMatcher` and ordering; do not rely on realm names.

In Spring Security, you can use the default Basic challenge name, though **you should set a clear realm** if clients are browsers or integration tools that need to distinguish environments.

## 4. Path of a Request Through Spring Security

1. The request enters `FilterChainProxy` and then the `SecurityFilterChain` applicable to that URL.
2. If `Authorization: Basic ...` is present, `BasicAuthenticationFilter` decodes the credentials, creates an unauthenticated `UsernamePasswordAuthenticationToken`, and passes it to `AuthenticationManager`.
3. In an example using `UserDetailsService`, the authentication provider can load the user, check the password with `PasswordEncoder`, and return an authenticated `Authentication` with authorities.
4. On success, `Authentication` is placed in `SecurityContextHolder` for the current request; `AuthorizationFilter` evaluates rules such as `authenticated()` or `hasRole("ADMIN")`.
5. When an endpoint requires login but the request is unauthenticated, `ExceptionTranslationFilter` uses the configured `AuthenticationEntryPoint` to initiate authentication. With HTTP Basic, `BasicAuthenticationEntryPoint` can return `401` and `WWW-Authenticate`.
6. When Basic credentials are invalid, `BasicAuthenticationFilter` handles the authentication failure and invokes the entry point; the client receives a prompt to authenticate again.
7. When credentials are valid but permissions are missing, authorization results in **`403 Forbidden`** under standard configuration. Changing the realm does not turn `403` into `401`.

**Do not confuse them:** `401` indicates the request lacks valid authentication or needs re-authentication; `403` indicates the request has been identified but is not permitted to perform the requested action (or another protection layer, such as CSRF, blocked the request). A `permitAll()` endpoint can return `200` even when no `Authorization` header is sent.

## 5. Practical Configuration with Spring Boot 3.x

Assume you have a Spring Boot Servlet application with Java 17+ and Spring Boot's dependency management plugin. At a minimum, the following two starters are required; integration tests use two additional test dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

If using Maven, add the corresponding starters to `pom.xml`. The example consists of three Java files in the same package `com.example.basicauth`.

### 5.1. Entry Point

File `src/main/java/com/example/basicauth/BasicDemoApplication.java`:

```java
package com.example.basicauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BasicDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(BasicDemoApplication.class, args);
    }
}
```

### 5.2. Define Users and Enable HTTP Basic

File `src/main/java/com/example/basicauth/SecurityConfig.java`:

```java
package com.example.basicauth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(basic -> basic.realmName("Learning API"))
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            );

        return http.build();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("alice-secret"))
                .roles("USER")
                .build(),
            User.withUsername("bob")
                .password(encoder.encode("bob-secret"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }
}
```

Explanation of decisions:

- `.httpBasic(basic -> basic.realmName("Learning API"))` activates `BasicAuthenticationFilter` and configures the realm name for challenges. If a custom realm is not needed, the minimal syntax is `.httpBasic(Customizer.withDefaults())` (import `org.springframework.security.config.Customizer`).
- Once you declare your own `SecurityFilterChain`, explicitly configure the authentication mechanism you want to use; do not rely on defaults that Spring Boot might supply only when **no** custom chain bean exists.
- The `UserDetailsService` in the example stores users in memory for learning and testing; real applications use a properly managed identity store or authentication method.
- `BCryptPasswordEncoder` matches passwords against hashes; **never store plaintext passwords** in a real data store. The two sample passwords are for local environments only.
- `roles("ADMIN")` creates the `ROLE_ADMIN` authority; therefore `hasRole("ADMIN")` matches user `bob`. User `alice` only has `ROLE_USER`.
- `SessionCreationPolicy.STATELESS` instructs Spring Security not to use `HttpSession` to store or retrieve `SecurityContext`. With Basic, the client must still send credentials on every request requiring authentication. This setting does not make HTTP Basic safe against CSRF when a browser automatically sends credentials.
- The example **keeps default CSRF protection enabled**. The demo endpoints are GET (non-state-changing). When adding POST/PUT/DELETE, you must decide the CSRF policy based on the actual client type; do not disable it globally merely because you use Basic or `STATELESS`.

### 5.3. Endpoints to Observe the Effect of Realm, 401, and 403

File `src/main/java/com/example/basicauth/ApiController.java`:

```java
package com.example.basicauth;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/api/public")
    public Map<String, String> publicEndpoint() {
        return Map.of("message", "public");
    }

    @GetMapping("/api/profile")
    public Map<String, String> profile(Authentication authentication) {
        return Map.of("user", authentication.getName());
    }

    @GetMapping("/api/admin")
    public Map<String, String> admin(Authentication authentication) {
        return Map.of("admin", authentication.getName());
    }
}
```

Run using the `bootRun` task in a Gradle project configured with the Spring Boot plugin:

```bash
./gradlew bootRun
```

On Windows PowerShell use `.\gradlew.bat bootRun`. If the project lacks a wrapper or the Spring Boot plugin, complete the build setup before running the command; the three Java files above are designed for a **Spring Boot 3.x application with an existing build**, not as standalone `javac` programs.

### 5.4. Testing with curl and Reading the Results

```bash
# No login required:
curl -i http://localhost:8080/api/public

# No credentials sent:
curl -i http://localhost:8080/api/profile

# Valid username/password:
curl -i -u alice:alice-secret http://localhost:8080/api/profile

# Wrong password:
curl -i -u alice:wrong http://localhost:8080/api/profile

# Valid password, missing ROLE_ADMIN:
curl -i -u alice:alice-secret http://localhost:8080/api/admin

# User with ROLE_ADMIN:
curl -i -u bob:bob-secret http://localhost:8080/api/admin
```

| Request | Expected outcome | Meaning |
|---|---|---|
| `GET /api/public`, no header | `200`, JSON `{"message":"public"}` | `permitAll()` |
| `GET /api/profile`, no header | `401` with `WWW-Authenticate: Basic realm="Learning API"` | Server sends Basic challenge |
| `GET /api/profile`, alice with right password | `200`, JSON `{"user":"alice"}` | Authentication succeeded |
| `GET /api/profile`, alice with wrong password | `401`, typically with Basic challenge | Not validly authenticated |
| `GET /api/admin`, alice with right password | `403` | Authenticated, but missing role |
| `GET /api/admin`, bob with right password | `200`, JSON `{"admin":"bob"}` | Sufficient role |

The table lists only **statuses and values to verify**; the status line, header order, error body, and additional headers depend on the environment. `curl -u` can expose sample passwords in shell or process history; never use real secrets this way in shared environments.

To inspect the challenge specifically, you can run:

```bash
curl -i http://localhost:8080/api/profile
```

The key line in the response is `WWW-Authenticate: Basic realm="Learning API"`. In a browser, this challenge can trigger a dialog asking for username/password. Some clients or requests carrying `X-Requested-With: XMLHttpRequest` may be configured by default to return `401` **without** the challenge so as not to pop up a browser dialog; therefore, inspect the actual client type and entry point in effect when debugging.

## 6. Customizing Realm and AuthenticationEntryPoint Properly

### Simple Realm Rename

Use the DSL directly when you only need to change the string:

```java
http.httpBasic(basic -> basic.realmName("Partner API"));
```

This is the cleanest way to preserve HTTP Basic's default behavior while changing the challenge details. Keep the realm string short and recognizable. Do not use the realm to store secrets or authorization codes.

### When a Custom Entry Point Is Needed

`BasicAuthenticationEntryPoint` is the `AuthenticationEntryPoint` implementation responsible for sending `401` and `WWW-Authenticate`. You can expose a bean with a configured realm:

```java
@Bean
BasicAuthenticationEntryPoint partnerEntryPoint() {
    BasicAuthenticationEntryPoint entryPoint =
        new BasicAuthenticationEntryPoint();
    entryPoint.setRealmName("Partner API");
    return entryPoint;
}
```

The imports for the snippet above are `org.springframework.context.annotation.Bean` and `org.springframework.security.web.authentication.www.BasicAuthenticationEntryPoint`. Because it is a Spring bean, the `afterPropertiesSet()` callback is invoked by the container on initialization; if instantiated manually outside the container, initialize/check its lifecycle accordingly.

To use this bean, **replace** the `httpBasic(...)` line in `SecurityFilterChain`, for example with a `BasicAuthenticationEntryPoint partnerEntryPoint` parameter injected into the chain factory method:

```java
.httpBasic(basic -> basic.authenticationEntryPoint(partnerEntryPoint))
```

This is a **configuration replacement snippet**, not a complete `SecurityFilterChain`. Avoid combining `realmName(...)` and `authenticationEntryPoint(...)` in the same configurer: a custom entry point decides the challenge itself; per the Spring Security API, calling `realmName` after setting a custom entry point can be rejected. When writing a custom entry point to return a JSON error body, if you still follow the Basic standard, you must preserve status `401` and the appropriate challenge header; returning a JSON body alone is not enough for clients to recognize the authentication scheme.

### Why Is WWW-Authenticate Sometimes Missing?

Not every HTTP error produces a Basic challenge:

- `200` on a public resource: no login needs to be requested.
- `403` for an authenticated user missing a role: usually handled by `AccessDeniedHandler`; no need to ask for credentials again.
- `401` from a custom entry point that only returns a status, or an AJAX request handled differently: the header may be omitted.
- The request matched a different `SecurityFilterChain`, or Basic was not enabled in that chain: behavior can differ completely.
- A proxy/gateway in front of the application may generate or alter the response; inspect logs and headers at the exact handling layer.

When using multiple chains, verify `securityMatcher(...)`, `@Order`, and the authentication mechanism on each chain. `requestMatchers(...)` inside `authorizeHttpRequests` only defines permissions for requests that have already entered the chain; it does **not** replace `securityMatcher` for chain selection.

## 7. Automated Testing of Key Behaviors

After adding `spring-boot-starter-test` and `spring-security-test`, create `src/test/java/com/example/basicauth/BasicAuthenticationTest.java`:

```java
package com.example.basicauth;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class BasicAuthenticationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void missingCredentialsReturnBasicChallenge() throws Exception {
        mvc.perform(get("/api/profile"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                "Basic realm=\"Learning API\""
            ));
    }

    @Test
    void validCredentialsReturnProfile() throws Exception {
        mvc.perform(get("/api/profile")
                .with(httpBasic("alice", "alice-secret")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("alice"));
    }

    @Test
    void validUserWithoutAdminRoleIsForbidden() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("alice", "alice-secret")))
            .andExpect(status().isForbidden());
    }

    @Test
    void incorrectPasswordIsUnauthorized() throws Exception {
        mvc.perform(get("/api/profile")
                .with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void publicEndpointNeedsNoCredentials() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk());
    }
}
```

Run `./gradlew test` (Windows: `.\gradlew.bat test`). These tests verify HTTP behavior from request to filter chain, including the actual realm string; they do not replace checking HTTPS and secret management in production deployments. When changing the entry point or using multiple filter chains, update the expected challenge for the chain under test.

## 8. Security and Common Pitfalls

### HTTPS Is Mandatory

Base64-encoded username/password values **are reversible**. Never send HTTP Basic over unencrypted HTTP in production, even when using `BCryptPasswordEncoder` for stored hashes: BCrypt protects **passwords stored on the server**, whereas TLS protects **credentials in transit** over the network. HTTPS must be configured with proper certificate verification, and `Authorization` must not be written into logs, tracing, exception messages, or URLs.

### Stateless Does Not Automatically Eliminate CSRF

Browsers can automatically attach remembered Basic credentials when sending requests to the same server. Therefore, web applications with state-changing operations **can still be vulnerable to CSRF**, even with `SessionCreationPolicy.STATELESS`. Spring Security enables CSRF protection by default for unsafe HTTP methods. If an API is strictly for non-browser clients and does not rely on automatically sent credentials, evaluate the threat model and restrict CSRF exemptions only to the necessary endpoints; do not copy `csrf.disable()` globally as a Basic ritual.

### Basic Has No Server-Side Logout Like Session Login

While the client/browser retains and keeps sending `Authorization`, the server can still re-authenticate on subsequent requests. Clearing the `SecurityContext` for a single request does not guarantee the browser forgets the credentials. To effectively revoke access, disable/rotate credentials or design an authentication mechanism with proper revocation support.

### Troubleshooting Checklist

| Symptom | Check first |
|---|---|
| `401` even though username/password were sent | Header must use the `Basic` scheme, credential pair must be correct, user must exist, password hash must match the encoder, and the account must not be locked |
| `401` without `WWW-Authenticate` | Is `X-Requested-With: XMLHttpRequest` used, or a custom entry point, gateway/proxy, or a different chain? |
| Wrong realm displayed | Is `realmName(...)` configured on the right chain? Is `authenticationEntryPoint(...)` overriding it? |
| `403` after logging in with valid credentials | Compare `ROLE_ADMIN` with `hasRole("ADMIN")`; check other authorization rules or CSRF for state-changing requests |
| `POST` gets `403` while `GET` succeeds | Check the CSRF token and policy for the client group; do not assume the password is wrong |
| Browser keeps sending an old account | Check the browser's HTTP Basic credential cache, origin/realm; use a private window or an independent test client |
| `.httpBasic(...)` has no effect | Verify the right `SecurityFilterChain`, `securityMatcher`, and order of multiple chains; enable Spring Security logging if needed |
| Cannot separate permissions between two realms | A realm is only a challenge name; configure authentication and authorization per actual URL area |

## 9. Takeaways When Applying

- **`httpBasic(...)` enables the authentication mechanism**, while **`realmName(...)` changes the protection space information** sent to clients on a Basic challenge.
- Clients send **`Authorization`**; the server requests authentication via **`401 + WWW-Authenticate`**. A challenge header is not proof that a user is logged in.
- Distinguish **`401` (needs authentication)** from **`403` (insufficient permissions or blocked by another policy)** before changing configuration.
- Use HTTPS, a `PasswordEncoder`, appropriate roles/authorities, proper filter chain scoping, and keep a CSRF policy suited to the client type.
- Test all cases: public, missing credentials, wrong password, valid password, missing role, and exact realm.

**Reference documentation:**

- [Spring Security — Basic Authentication (Servlet)](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html)
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [RFC 7617 — The Basic HTTP Authentication Scheme](https://www.rfc-editor.org/rfc/rfc7617)
