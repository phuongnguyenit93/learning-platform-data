# BasicAuthenticationFilter and How It Calls AuthenticationManager

> **Scope:** HTTP Basic in **Spring Security Servlet** (Spring Security 6.x, Spring Boot 3.x, Java 17+). This lesson focuses on how `BasicAuthenticationFilter` extracts authentication credentials from an HTTP request, decides when to call `AuthenticationManager.authenticate(...)`, handles the result, and hands the request off to authorization. This is the Servlet `SecurityFilterChain` mechanism; WebFlux uses different components.

## 1. The Problem That BasicAuthenticationFilter Solves

HTTP Basic lets a client send a username and password in a header:

```http
GET /private HTTP/1.1
Host: localhost:8080
Authorization: Basic YWxpY2U6c2VjcmV0MTIz
```

The part after `Basic` is the Base64 encoding of the string `alice:secret123`. **Base64 is only a representation encoding, not password security.** HTTPS/TLS is mandatory in real applications; never put credentials into URLs, logs, or monitoring tools.

An `HttpServletRequest` containing the header above does not yet mean the user is authenticated. `BasicAuthenticationFilter` must turn those credentials into an initial `Authentication` object, ask `AuthenticationManager` to verify it, and place the successful authentication result into `SecurityContextHolder` so downstream filters know the user's identity.

**Separation of responsibilities:**

| Component | Responsibility |
| --- | --- |
| `BasicAuthenticationFilter` | Detects the `Authorization: Basic ...` header, converts it into an authentication request, calls the manager, updates/clears the context, and handles authentication failures. |
| `BasicAuthenticationConverter` | Converts a valid Basic header into an unauthenticated `UsernamePasswordAuthenticationToken`; returns `null` if there is no Basic header. |
| `AuthenticationManager` | Contract `authenticate(Authentication)`; returns an authenticated `Authentication` or throws `AuthenticationException`. |
| `ProviderManager` | Common `AuthenticationManager` implementation; tries matching `AuthenticationProvider` instances. |
| `DaoAuthenticationProvider` | Authenticates username/password using `UserDetailsService` and `PasswordEncoder`. |
| `SecurityContextHolder` | Holds the current `SecurityContext`/`Authentication` within the scope of processing the request. |
| `AuthorizationFilter` | Decides access permissions based on `Authentication` and rules such as `authenticated()`, `hasRole(...)`. |
| `AuthenticationEntryPoint` | Initiates the response when the client needs to authenticate, typically returning HTTP 401 and a `WWW-Authenticate` challenge for Basic. |

`BasicAuthenticationFilter` **does not check passwords itself via string comparison**, does not query the database itself, does not decide `hasRole(...)`, and is not a controller handling `/login`.

## 2. Call Flow Diagram for AuthenticationManager

```text
Client
  | GET /private
  | Authorization: Basic base64(username:password)
  v
Spring Security FilterChainProxy (Servlet SecurityFilterChain)
  |
  v
BasicAuthenticationFilter
  |-- BasicAuthenticationConverter.convert(request)
  |     -> UsernamePasswordAuthenticationToken(username, password)
  |        (not yet authenticated)
  |
  |-- if authentication is required:
  |     AuthenticationManager.authenticate(token)
  |       -> ProviderManager
  |            -> DaoAuthenticationProvider
  |                 -> UserDetailsService.loadUserByUsername(...)
  |                 -> PasswordEncoder.matches(raw, encoded)
  |            <- authenticated Authentication + authorities
  |
  |-- success: create SecurityContext, set Authentication,
  |            invoke remember-me hook if configured, optionally save context
  |-- failure: clear context, invoke failure hook,
  |            trigger AuthenticationEntryPoint (typically 401)
  v
Subsequent filters, including AuthorizationFilter
  |-- authorized -> Controller -> 200
  |-- insufficient permissions -> AccessDeniedHandler -> 403
```

The flow above summarizes the behavior of Spring Security 6.x rather than being a verbatim copy of the source code. Other filters, such as `SecurityContextHolderFilter` and `ExceptionTranslationFilter`, also participate in the overall chain. The exact order is determined by the `SecurityFilterChain` configuration.

### Step 1 — Read the Header and Create an Unauthenticated Token

`BasicAuthenticationFilter` uses `BasicAuthenticationConverter` to recognize headers with the Basic scheme, decode the credentials, and split username/password at the first `:`. For `alice:secret123`, the conceptual token is equivalent to:

```java
Authentication requestAuthentication =
        UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "secret123");
```

This is **an illustrative snippet inside the filter flow**, not a standalone Java program. The token carries `principal` (here, the username) and `credentials` (the password), but has no proof yet that the credentials are valid. Do not use `UsernamePasswordAuthenticationToken.authenticated(...)` to declare on your own that a request is authenticated.

If the header is absent or uses another scheme (such as Bearer), the converter does not create a Basic token and the filter lets the request continue. If the header declares Basic but is malformed, conversion may throw `AuthenticationException` to be handled as an authentication failure. A syntactically valid Basic header **does not mean** the password is valid.

### Step 2 — Decide Whether Calling authenticate Is Needed

Once the converter produces a token, the filter checks `authenticationIsRequired(username)`. Normally there is no authenticated user in the context yet, so it runs:

```java
Authentication authenticated =
        authenticationManager.authenticate(requestAuthentication);
```

This is also **an illustrative snippet**, where the `authenticationManager` variable is a dependency of the filter. If the context already holds a genuinely authenticated user with the same username, the filter may skip calling the manager again. Do not assume a Basic header always triggers exactly one user/password lookup: that depends on the context and provider/caching.

`http.httpBasic(...)` configures the filter with the `AuthenticationManager` used by `HttpSecurity`. Therefore, in typical configurations, **you do not need to instantiate or add `BasicAuthenticationFilter` manually**. Doing `new BasicAuthenticationFilter(...)` and `addFilter...` without controlling placement/manager wiring can cause double processing or break the security chain.

### Step 3 — AuthenticationManager Delegates to a Provider

`AuthenticationManager` is an interface:

```java
Authentication authenticate(Authentication authentication)
        throws AuthenticationException;
```

`ProviderManager` is usually the implementation behind it. It selects the `AuthenticationProvider` instances whose `supports(...)` matches the token type; in the username/password example, `DaoAuthenticationProvider` uses `UserDetailsService.loadUserByUsername("alice")` to fetch the account, then `PasswordEncoder.matches(rawPassword, encodedPassword)` to verify the password. The provider checks account state such as locked or disabled if the `UserDetails` data specifies it. When multiple providers participate, the outcome or exception depends on how `ProviderManager` delegates.

The manager **does not return `true`/`false`**. It returns an `Authentication` object (typically with `isAuthenticated()==true`, a verified `principal`, and a collection of `GrantedAuthority`) or throws `AuthenticationException`; for instance, `BadCredentialsException` when the password is wrong. Do not rely on detailed error messages to distinguish whether an account exists.

### Step 4 — Success: Place the Result into SecurityContext

When `authenticate(...)` succeeds, `BasicAuthenticationFilter` creates a `SecurityContext`, sets the returned `Authentication` on it, and places the context into `SecurityContextHolder`. It also invokes `RememberMeServices.loginSuccess(...)` if configured and uses the supplied `SecurityContextRepository` to persist the context according to the application's policy. Afterward, the request continues down the filter chain.

What goes into the context is **the result from the manager**, not the initial unauthenticated token. `AuthenticationManager` only authenticates; **the filter is responsible for updating the context**. Authorization filters read this information to evaluate access, and controllers can receive the authenticated `Authentication` as a parameter.

Common misconception: placing the result into `SecurityContextHolder` for the current request **does not automatically mean writing it to the HTTP session**. By default, `BasicAuthenticationFilter` does not persist the context across sessions; to persist it, you must configure an appropriate repository. With stateless APIs, clients typically resend the Basic header on every request.

### Step 5 — Failure: Clear Context and Request Re-authentication

When the converter or manager throws `AuthenticationException`, the filter clears the context, calls `RememberMeServices.loginFail(...)` if present, and—in the default mode that does not ignore errors—invokes `AuthenticationEntryPoint.commence(...)`. For HTTP Basic, the typical response is **401 Unauthorized** with a challenge such as `WWW-Authenticate: Basic realm="Realm"` (the actual realm/headers depend on configuration and request type). The filter does not forward to the controller after this 401 branch.

The path of a request **with no Basic header at all** is slightly different: the Basic filter simply passes it along; if the URL requires authentication, `AuthorizationFilter` denies access and `ExceptionTranslationFilter` uses the entry point to return a 401 challenge. A request that is **authenticated but lacks permissions** typically receives **403 Forbidden** via `AccessDeniedHandler`.

Note: some default HTTP Basic configurations have special behavior for `X-Requested-With: XMLHttpRequest` (which may omit the body/challenge on a 401 response), so when debugging you must inspect the actual request headers and entry point.

## 3. Runnable Example: Spring Boot 3.3.5, Java 17

The example is pinned to Spring Boot 3.3.5 (Spring Security 6.x branch). Run with Maven 3.9+ and JDK 17+. The demo has two users: `alice` with `ROLE_READER` and `bob` with `ROLE_VIEWER`, both using the demo password `secret123`. The passwords exist only in demo configuration; never put these values into production.

Structure:

```text
basic-auth-demo/
├── pom.xml
└── src/main/java/com/example/basicauth/BasicAuthDemoApplication.java
```

**`pom.xml`:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
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

**`src/main/java/com/example/basicauth/BasicAuthDemoApplication.java`:**

```java
package com.example.basicauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class BasicAuthDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(BasicAuthDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/private").hasRole("READER")
                .anyRequest().authenticated()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("secret123"))
            .roles("READER")
            .build();
        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("secret123"))
            .roles("VIEWER")
            .build();
        return new InMemoryUserDetailsManager(alice, bob);
    }

    @RestController
    static class DemoController {
        @GetMapping("/public")
        String publicPage() {
            return "public";
        }

        @GetMapping("/private")
        String privatePage(Authentication authentication) {
            return "Hello, " + authentication.getName();
        }
    }
}
```

Explanation of key configuration lines:

1. `httpBasic(Customizer.withDefaults())` enables Basic authentication and registers `BasicAuthenticationFilter` in the Servlet chain.
2. The `UserDetailsService` and `PasswordEncoder` beans provide data so Spring Security configures username/password authentication via the provider/manager. The demo uses `InMemoryUserDetailsManager`; it can be replaced with a repository or another source via a suitable provider.
3. `hasRole("READER")` requires the `ROLE_READER` authority. `roles("READER")` creates that authority; do not pass `"ROLE_READER"` into `hasRole`.
4. `SessionCreationPolicy.STATELESS` tells the application not to create or use a session to retrieve `SecurityContext` for requests. This makes it easy to observe each Basic request authenticating with its accompanying credentials.
5. `/public` requires no permissions, but a Basic header **if sent** can still be processed by the Basic filter before the `permitAll` check.
6. The demo only uses GET, so there is no need to disable CSRF. For state-changing endpoints in a real application, you must evaluate CSRF based on client type and credential mechanism before configuring the policy.

Run from the directory containing `pom.xml`:

```bash
mvn spring-boot:run
```

In another terminal, test sequentially (on Windows PowerShell use `curl.exe` if `curl` is an alias):

```bash
curl -s http://localhost:8080/public
# public

curl -i http://localhost:8080/private
# HTTP status: 401; typically includes WWW-Authenticate: Basic realm="Realm"

curl -s -u alice:secret123 http://localhost:8080/private
# Hello, alice

curl -i -u alice:wrong http://localhost:8080/private
# HTTP status: 401

curl -i -u bob:secret123 http://localhost:8080/private
# HTTP status: 403
```

Lines starting with `#` in the shell block only describe expected results. The output bodies of the two `-s` commands are literally `public` and `Hello, alice` (not necessarily with a trailing newline); the headers/bodies of error responses depend on server configuration and version. Depending on `curl`, you can use `-v` to inspect the `Authorization` header, but **do not share logs containing credentials**.

## 4. Automated Testing for 401 / 200 / 403

Add `src/test/java/com/example/basicauth/BasicAuthDemoApplicationTests.java` (test dependencies are already in the POM):

```java
package com.example.basicauth;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BasicAuthDemoApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void basicCredentialsAndAuthorities() throws Exception {
        mvc.perform(get("/private"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/private").with(httpBasic("alice", "secret123")))
            .andExpect(status().isOk())
            .andExpect(content().string("Hello, alice"));

        mvc.perform(get("/private").with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/private").with(httpBasic("bob", "secret123")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }
}
```

Run `mvn test`. This test exercises the application's actual Spring Security chain inside `MockMvc`: Alice's username/password is authenticated and has the right role, Bob authenticates successfully but lacks the role, a wrong password causes authentication failure, and an unauthenticated request to a protected endpoint gets 401.

## 5. Distinguishing Commonly Confused Branches

| Request/state | BasicAuthenticationFilter | Downstream | Typical outcome |
| --- | --- | --- | --- |
| No `Authorization`, calling `/public` | Does not create a Basic token | `permitAll` | 200 |
| No `Authorization`, calling `/private` | Skips | Authorization requires login, entry point generates challenge | 401 |
| `alice:secret123`, calling `/private` | Manager authenticates successfully, puts Alice in context | Alice has `ROLE_READER` | 200 |
| `alice:wrong`, calling `/private` | Manager throws `AuthenticationException`, filter handles error | Controller is not invoked | 401 |
| `bob:secret123`, calling `/private` | Bob authenticates successfully | Bob lacks `ROLE_READER` | 403 |
| `Authorization: Bearer ...`, no Bearer filter | Basic filter does not handle this scheme | Protected URL still requires authentication | 401 |
| Malformed Basic header | Converter may throw error | Filter invokes entry point | 401 |

**Why is 401 different from 403?** `401` usually means the client has not presented valid credentials; `403` means the server has verified the identity but does not permit the operation. Do not attribute every `403` error to a wrong password.

**Why can `permitAll` still see a 401?** A request to a public endpoint that proactively sends an invalid Basic header can be rejected by the Basic filter **before** `AuthorizationFilter` checks `permitAll`. `permitAll` only governs the authorization decision; it does not disable all authentication filters.

**When there are multiple `SecurityFilterChain` beans:** only the chain matching the request (selected by `FilterChainProxy`) is used. If `httpBasic()` is in a different chain, the current request might never pass through `BasicAuthenticationFilter` at all. Check `securityMatcher(...)` and chain ordering before suspecting the manager.

## 6. How to Read and Debug Real Calls

Set breakpoints or trace at the following points, in order:

1. `BasicAuthenticationFilter#doFilterInternal`: does the request have a Basic header? Does `BasicAuthenticationConverter.convert(...)` return `null`, a token, or an exception?
2. `BasicAuthenticationFilter#authenticationIsRequired`: does the current context already hold an authentication, and does it skip calling the manager?
3. `ProviderManager#authenticate`: which `UsernamePasswordAuthenticationToken` did it receive, and is there a matching provider?
4. `DaoAuthenticationProvider` / `UserDetailsService#loadUserByUsername`: was the user found? Did `PasswordEncoder.matches(...)` verify the hashed password properly?
5. Back in the filter: what `Authentication` did the manager return, what are `isAuthenticated` and `authorities`, and was the context updated?
6. `AuthorizationFilter`: does `hasRole("READER")` match `ROLE_READER` in the context? On failure, did the entry point or the access-denied handler respond?

Never log the `Authorization` string, raw passwords, or full `Authentication.credentials`. When debugging with logs, include minimal information such as token type, status, and provider name, with a sensitive-data masking policy.

### Common Configuration Mistakes

- **Forgetting `httpBasic(...)` when declaring a custom `SecurityFilterChain`:** Basic requests are not processed as expected. Declare it explicitly in the target chain.
- **No provider supporting username/password tokens:** the manager cannot find an authentication path. Verify `UserDetailsService`, `AuthenticationProvider`, and `AuthenticationManager` wiring.
- **Wrong `PasswordEncoder` or storing plaintext passwords then comparing against hashes:** `matches(...)` fails. Store proper hashes (such as BCrypt), encode passwords when creating users, and avoid `{noop}` in production.
- **Returning an `authenticated` token yourself without checking credentials:** introduces an authentication bypass vulnerability. Only trust results authenticated by the manager/provider.
- **Confusing permissions with passwords:** a valid password missing `ROLE_READER` results in 403, not 401.
- **Assuming one Basic login creates a long-lived login session:** HTTP Basic typically sends credentials on every request; persisting `SecurityContext`/sessions is a separate policy.
- **Skipping HTTPS:** Base64 does not hide passwords from anyone able to read network traffic.
- **Manually adding multiple Basic filters:** makes flow and manager wiring hard to control; use standard `httpBasic` configuration first.

## 7. Self-Check Questions

1. Which token goes **into** `AuthenticationManager.authenticate(...)`? Is it considered authenticated yet?
2. After a successful `authenticate(...)` call, which component places the returned `Authentication` into `SecurityContextHolder`?
3. If the Basic header is completely absent, why does a protected endpoint still return 401 even though the Basic filter skips it?
4. Why does `bob` get 403 in the demo, whereas `alice` with a wrong password gets 401?
5. Why does setting `.sessionCreationPolicy(STATELESS)` not mean skipping `AuthenticationManager`?
6. If an authenticated `Authentication` with the same username is already in the context, should you assume the manager is always called again?

**Core answers:** (1) An unauthenticated `UsernamePasswordAuthenticationToken`; (2) `BasicAuthenticationFilter`; (3) authorization denies access and `ExceptionTranslationFilter` invokes the entry point; (4) missing permissions vs invalid credentials; (5) stateless controls session/context policy, not password verification; (6) no, the filter checks the `authenticationIsRequired` condition.

## Official References

- Spring Security — Basic Authentication (Servlet): https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/basic.html
- Spring Security — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- Spring Security — DaoAuthenticationProvider: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html
- Spring Security — BasicAuthenticationFilter API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/www/BasicAuthenticationFilter.html
- Spring Security — Authentication Persistence / Session Management: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
