# AuthenticationEntryPoint for Unauthenticated Users in Spring Security

In an application protected by Spring Security, a request to a resource requiring login may arrive when the user has not provided credentials, the session has expired, or the token is invalid. `AuthenticationEntryPoint` decides **how to commence the authentication process or how to inform the client that authentication is required**. It is part of the access denial handling mechanism at the HTTP layer, and is especially useful for distinguishing **unauthenticated** callers from callers who are **authenticated but lack permissions**.

This lesson focuses on **Spring Security Servlet** (`HttpSecurity`, `SecurityFilterChain`, `jakarta.servlet`). WebFlux applications use a different interface, `ServerAuthenticationEntryPoint`.

## 1. Role and Boundaries

`org.springframework.security.web.AuthenticationEntryPoint` has one main method:

```java
void commence(HttpServletRequest request,
              HttpServletResponse response,
              AuthenticationException authException)
        throws IOException, ServletException;
```

- `request`: the HTTP request that requires authentication.
- `response`: the HTTP response used to send a status, headers, or redirect to the client.
- `authException`: the authentication exception that triggered the entry point; internal exception messages should not be exposed directly to the client.
- `commence(...)` **does not verify passwords, does not decode JWTs, and does not grant permissions**. Those steps belong to authentication filters, `AuthenticationManager`/`AuthenticationProvider`, or the corresponding authentication mechanism.
- The entry point may return `401 Unauthorized` with `WWW-Authenticate`, redirect `302` to a login page, or perform another appropriate response. **There is no rule that every `AuthenticationEntryPoint` returns 401.**

Distinguish these components:

| Component | Responsibility |
| --- | --- |
| `AuthorizationFilter` / `authorizeHttpRequests` rules | Determines whether the current request has sufficient permissions to access the resource; may deny with `AccessDeniedException`. |
| `ExceptionTranslationFilter` | Translates certain authentication/authorization errors thrown within the portion of the filter chain it wraps into appropriate HTTP behavior. |
| `AuthenticationEntryPoint` | Commences authentication or returns a response prompting the client to authenticate. |
| `AccessDeniedHandler` | Handles cases where access is denied for a principal already considered authenticated, typically returning `403 Forbidden`. |

## 2. When Is `AuthenticationEntryPoint` Called?

Typical flow when an unauthenticated request accesses `/api/report` configured with `.authenticated()`:

1. The request passes through authentication filters. If there are no valid credentials, there is no real logged-in user; the anonymous mechanism may place an `AnonymousAuthenticationToken` in `SecurityContext`.
2. The authorization check concludes the request is not allowed and throws `AccessDeniedException`.
3. `ExceptionTranslationFilter` uses authentication state information (via `AuthenticationTrustResolver`) to determine that login should be requested. For an anonymous principal, it invokes `AuthenticationEntryPoint` instead of returning 403 by default.
4. The entry point produces a response matching the authentication mechanism: e.g., `401` for a REST API using Basic/Bearer, or a redirect to the login page for a web UI.
5. The client resends credentials; the authentication filter processes the credentials on the next request. Once authenticated, the authorization decision is re-evaluated.

`ExceptionTranslationFilter` can also call the entry point when it catches an `AuthenticationException`. Separately, some authentication filters (such as `BasicAuthenticationFilter`) can invoke the entry point themselves when authentication fails, so do not assume that **every** call to an entry point passes through `ExceptionTranslationFilter`.

Distinguish the scenarios:

| Request | Typical Outcome |
| --- | --- |
| Not logged in, accessing an endpoint requiring `.authenticated()` | Triggers `AuthenticationEntryPoint`; APIs typically return 401, form login apps typically redirect. |
| Logged in as `READER`, accessing an endpoint requiring `ADMIN` | Triggers `AccessDeniedHandler`, typically 403. |
| Sending wrong username/password via HTTP Basic | Authentication filter handles the failure and uses the appropriate entry point, usually 401 with an HTTP Basic challenge. |
| Expired or invalid-signature Bearer token | Resource server mechanism rejects authentication; response is typically 401 with corresponding Bearer error details. |
| POST missing CSRF token | May be 403 due to CSRF protection; you cannot look at the status code alone to conclude missing permissions or unauthenticated state. |

**Note:** `AnonymousAuthenticationToken` can have `isAuthenticated() == true` in the token's internal sense. Do not use this flag alone to conclude the user is logged in. Spring Security provides proper mechanisms to distinguish anonymous from authenticated/remember-me principals.

## 3. Choosing an Entry Point Type by Protocol

- **HTTP Basic:** `BasicAuthenticationEntryPoint` returns 401 along with `WWW-Authenticate: Basic realm="..."` so the client understands which mechanism to use. The challenge header is important for browser and Basic client behavior.
- **OAuth2 Resource Server:** `BearerTokenAuthenticationEntryPoint` follows the Bearer mechanism, sending `WWW-Authenticate: Bearer ...` with valid error info. Do not arbitrarily replace it with a generic JSON response if doing so drops headers required by the protocol.
- **Form login:** `LoginUrlAuthenticationEntryPoint` redirects to the login path; the response is usually 302. The login page must be permitted to avoid a redirect loop.
- **API needing a fixed status:** `HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)` is a concise option when only a status code needs to be returned.
- **Custom:** implement the interface yourself or use a lambda to produce a JSON error code, headers, and status consistent with the API contract.

Do not equate `AuthenticationEntryPoint` with a login page: the entry point only decides **how to commence authentication**. It also does not replace `AuthenticationFailureHandler`, which handles a failed form login submission.

## 4. Java 17+ Example with HTTP Basic and JSON 401

The following example runs in **a Spring Boot 3.x project using Servlet/MVC**, with starters `spring-boot-starter-web`, `spring-boot-starter-security`, and (to run the tests) `spring-boot-starter-test`, `spring-security-test`. This is a learning API example: user `reader` has role `READER`; `/api/report` requires login, while `/api/admin` requires role `ADMIN`. All test requests are GET, so CSRF does not need to be disabled.

Create `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Create `src/main/java/com/example/demo/ApiSecurityConfig.java`:

```java
package com.example.demo;

import java.nio.charset.StandardCharsets;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    AuthenticationEntryPoint apiAuthenticationEntryPoint() {
        return (request, response, authException) -> {
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setHeader(HttpHeaders.WWW_AUTHENTICATE,
                    "Basic realm=\"demo-api\"");
            response.setCharacterEncoding(StandardCharsets.UTF_8.name());
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.getWriter().write(
                    "{\"error\":\"authentication_required\"}");
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationEntryPoint apiAuthenticationEntryPoint)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .requestMatchers("/api/**").authenticated()
                .anyRequest().permitAll())
            .exceptionHandling(exceptions -> exceptions
                .authenticationEntryPoint(apiAuthenticationEntryPoint))
            .httpBasic(basic -> basic
                .authenticationEntryPoint(apiAuthenticationEntryPoint));

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("demo-pass"))
                .roles("READER")
                .build();
        return new InMemoryUserDetailsManager(reader);
    }
}
```

Create `src/main/java/com/example/demo/DemoController.java`:

```java
package com.example.demo;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/api/report")
    public String report(Authentication authentication) {
        return "report for " + authentication.getName();
    }

    @GetMapping("/api/admin")
    public String admin() {
        return "admin";
    }
}
```

Notable points of the configuration:

1. `authorizeHttpRequests` defines permissions. Matcher ordering matters: `/api/admin` requiring `ADMIN` must come before `/api/**`.
2. `exceptionHandling(...authenticationEntryPoint(...))` sets the authentication starting point when authorization checks in the filter chain require login.
3. `httpBasic(...authenticationEntryPoint(...))` ensures that invalid HTTP Basic credentials also share the defined response. Customizing only `exceptionHandling` may not cover the Basic filter's own error-handling path.
4. The header `WWW-Authenticate: Basic realm="demo-api"` is preserved because the example **intentionally uses HTTP Basic**. With JWT/Bearer, use the corresponding challenge rather than copying the Basic header.
5. `BCryptPasswordEncoder` is used for the authentication example. Accounts and passwords in the code are for test environments only; real applications must manage credentials securely.

Run the application with `./gradlew bootRun` (or `gradlew.bat bootRun` on Windows) if the project uses Gradle. When running on the default port 8080, try:

```bash
curl -i http://localhost:8080/api/report
curl -i -u reader:demo-pass http://localhost:8080/api/report
curl -i -u reader:demo-pass http://localhost:8080/api/admin
curl -i http://localhost:8080/public
```

Key results (omitting unrelated headers):

```http
GET /api/report
HTTP/1.1 401
WWW-Authenticate: Basic realm="demo-api"
Content-Type: application/json;charset=UTF-8

{"error":"authentication_required"}
```

```http
GET /api/report
Authorization: Basic <valid credentials>
HTTP/1.1 200

report for reader
```

```http
GET /api/admin
Authorization: Basic <reader credentials>
HTTP/1.1 403
```

```http
GET /public
HTTP/1.1 200

public
```

The example clearly distinguishes: missing credentials on `/api/report` causes **401 via the entry point**; valid credentials without the required role on `/api/admin` causes **403 via authorization**. The HTTP lines above illustrate the expected outcomes; actual header ordering and sets may vary by server/configuration.

## 5. When Is Built-in Configuration All You Need?

If you want a standard login form:

```java
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/login", "/assets/**").permitAll()
        .anyRequest().authenticated())
    .formLogin(form -> form
        .loginPage("/login")
        .permitAll());
```

This is a **configuration snippet inside an existing `SecurityFilterChain`**, not a standalone Java program. You must implement `GET /login` yourself when using a custom login page. Unauthenticated browser clients usually receive a redirect to `/login`; do not force HTML flows to return JSON 401 if the product wants to redirect users.

If you only need to return a status for an API, you can use:

```java
http.exceptionHandling(ex -> ex.authenticationEntryPoint(
        new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)));
```

The two snippets above are **alternatives** for entry point behavior; you need to import `org.springframework.security.web.authentication.HttpStatusEntryPoint` and `org.springframework.http.HttpStatus` for the second snippet. If using HTTP Basic/Bearer, consider keeping the proper `WWW-Authenticate` per the protocol; `HttpStatusEntryPoint` only sets the status.

When an application has both HTML pages and APIs, you can use multiple `SecurityFilterChain` beans with `securityMatcher(...)` and separate entry points for each request group, or select an entry point via `RequestMatcher`. Avoid applying an HTML redirect to all of `/api/**`, which causes REST clients to receive a login page instead of an authentication error they can handle.

## 6. Testing Denial Behavior Properly

With `spring-security-test`, `spring-boot-starter-test`, and the example in section 4, create `src/test/java/com/example/demo/AuthenticationEntryPointTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthenticationEntryPointTest {

    @Autowired
    MockMvc mvc;

    @Test
    void noCredentialsUsesEntryPoint() throws Exception {
        mvc.perform(get("/api/report"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                "Basic realm=\"demo-api\""))
            .andExpect(jsonPath("$.error")
                .value("authentication_required"));
    }

    @Test
    void validCredentialsCanAccessProtectedResource() throws Exception {
        mvc.perform(get("/api/report")
                .with(httpBasic("reader", "demo-pass")))
            .andExpect(status().isOk());
    }

    @Test
    void authenticatedUserWithoutAdminRoleGets403() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("reader", "demo-pass")))
            .andExpect(status().isForbidden());
    }
}
```

Run `./gradlew test` or `gradlew.bat test` depending on your operating system. The test suite should verify three independent outcomes: **401 + challenge + JSON** when unauthenticated, **200** when credentials are valid and authorized, and **403** when authenticated but missing the role. For Bearer apps, tests must verify `WWW-Authenticate` for Bearer as well as expired/invalid tokens.

## 7. Common Errors and How to Diagnose Them

- **Returning 403 for every unauthenticated request:** check the entry point, anonymous authentication, filter position/configuration, and matchers; do not write custom `isAuthenticated()` logic based on `AnonymousAuthenticationToken`.
- **Confusing 401 and 403:** an error originating from `AccessDeniedException` does not mean the response is always 403. `ExceptionTranslationFilter` also checks whether the user is actually authenticated.
- **Overriding the Resource Server entry point:** may drop `WWW-Authenticate: Bearer` and standard protocol `invalid_token` details. Replace it only after fully determining client and OAuth2 requirements.
- **Custom Basic 401 without `WWW-Authenticate`:** some clients/browsers will not know they need to perform a Basic challenge.
- **Infinite `/login` redirect loop:** unauthenticated users must be allowed to access the login page itself and the static assets it needs.
- **Catching errors with `@ControllerAdvice` but failing to handle them:** many security errors originate in servlet filters **before** the controller; handle them at the right layer with `AuthenticationEntryPoint`/`AccessDeniedHandler`.
- **Putting `authException.getMessage()` into the returned JSON:** may expose configuration or authentication details. Return a stable error code, log safely internally, and use a request ID if lookup is needed.
- **Seeing 403 and immediately disabling CSRF:** 403 can also be caused by a missing CSRF token. Check request type, logging, and CSRF configuration before changing security policies.
- **Response already committed:** you cannot reliably start a redirect or write a 401 body after the response is committed. Filter configuration and error handling must run before that point.

When debugging, enable Spring Security logs at `DEBUG` or `TRACE` in development, and observe the security filter order, endpoint matchers, Authentication state, and response headers. Do not enable detailed credential/token logging in production.

## 8. Knowledge Self-Check

1. An unauthenticated request accesses `/api/admin` requiring role `ADMIN`: why can it return 401 instead of 403? — Because the caller is unauthenticated, `ExceptionTranslationFilter` can translate the access denial into initiating authentication via the entry point.
2. Logged-in user `READER` calls the same endpoint: which component typically responds? — `AccessDeniedHandler`, normally returning 403.
3. Why might `AuthenticationEntryPoint` return 302? — Because with form login, commencing authentication can be a redirect to the login page.
4. Why not copy the JSON 401 + Basic header for a JWT API? — Bearer clients need a Bearer-compliant challenge and error information, which can be handled by `BearerTokenAuthenticationEntryPoint`.
5. When should you configure both `httpBasic` and `exceptionHandling`? — When you want a consistent response for unauthenticated requests rejected by authorization checks and for invalid HTTP Basic credential submissions.

## Official References

- [AuthenticationEntryPoint API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/AuthenticationEntryPoint.html)
- [ExceptionTranslationFilter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/access/ExceptionTranslationFilter.html)
- [Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Anonymous Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/anonymous.html)
- [HTTP Basic Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html)
- [OAuth2 Resource Server Bearer Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html)