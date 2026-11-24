# AccessDeniedHandler for Unauthorized Users

> Scope: **Spring Security on Servlet/Spring MVC**, within the **Access Denial Handling** topic. The focus is on scenarios where an authenticated user **lacks sufficient permissions** to access a resource. The hands-on example uses Java 17, Spring Boot 3.5.x, and modern `SecurityFilterChain` configuration.

## 1. Problem to Solve

Suppose the system has an endpoint `GET /api/admin/report` reserved for administrators. Alice has logged in successfully with the `READER` role, but tries to call this endpoint. Spring Security must block access and send a clear, consistent response to the client, such as HTTP **403 Forbidden** with a JSON error code `ACCESS_DENIED`. That is the job of **`AccessDeniedHandler`**.

Distinguish between two security questions:

- **Authentication:** Who are you? Is the identity/session/token valid?
- **Authorization:** Does that identity have permission to perform the action on this resource?

`AccessDeniedHandler` **does not decide who is allowed access**. Rules like `hasRole("ADMIN")`, `hasAuthority("report:read")`, or `@PreAuthorize` decide that; the handler only **translates an access denial into an appropriate HTTP response**.

### Distinguishing 401 and 403

| Scenario | Component Typically Handling It | Typical Result |
|---|---|---|
| Unauthenticated, accessing a resource requiring login | `AuthenticationEntryPoint` | HTTP 401 with HTTP Basic/Bearer; or 302 to login page with form login |
| Authenticated with `ROLE_READER`, requires `ROLE_ADMIN` | `AccessDeniedHandler` | HTTP 403 |
| Sufficient permissions | Normal request processing flow | HTTP 2xx (depending on controller) |
| Wrong password/invalid token | Authentication mechanism and entry point | Typically HTTP 401; depends on authentication type |
| Request blocked by CSRF/CORS or another filter | Component generating the corresponding error | Possibly HTTP 403, though **not necessarily** by the handler configured here |

Therefore, **do not turn missing permissions into 401** just to unify JSON; 401 indicates that authentication or re-authentication is needed. Cases like remember-me or an insufficient authentication level may cause Spring Security to require additional authentication instead of going straight to the handler.

## 2. Where Does `AccessDeniedHandler` Sit in the Servlet Flow?

High-level flow of a request protected by `authorizeHttpRequests`:

```text
Client
  |
  v
SecurityFilterChain
  |-- authentication filters (depending on HTTP Basic, form, Bearer, ...)
  |-- ExceptionTranslationFilter
  |       |
  |       +-- calls downstream filters
  |                   |
  |                   +-- AuthorizationFilter
  |                          |
  |                          +-- sufficient permissions --> Controller --> response
  |                          |
  |                          +-- insufficient permissions --> AccessDeniedException
  |
  +-- ExceptionTranslationFilter catches the appropriate error:
         |-- unauthenticated/insufficient authentication --> AuthenticationEntryPoint
         +-- authenticated, insufficient permissions --> AccessDeniedHandler --> 403
```

Sequence to understand:

1. Authentication filters set `Authentication` in `SecurityContext` when valid credentials are present.
2. `AuthorizationFilter` applies rules matching the request. If denied, it throws an error in the `AccessDeniedException` hierarchy.
3. `ExceptionTranslationFilter` catches `AccessDeniedException` or `AuthenticationException` thrown from the downstream portion of the filter chain. This filter **does not check permissions itself**; it chooses how to respond.
4. When the caller is properly authenticated but lacks permission, `ExceptionTranslationFilter` calls `AccessDeniedHandler.handle(...)`. For anonymous/unauthenticated callers or cases requiring an authentication upgrade, it may use `AuthenticationEntryPoint`.
5. The handler sets the status, headers, body, or forwards to an error page. A denied request **does not proceed into business logic requiring permissions**.

The main interface resides in package `org.springframework.security.web.access`:

```java
public interface AccessDeniedHandler {
    void handle(
        jakarta.servlet.http.HttpServletRequest request,
        jakarta.servlet.http.HttpServletResponse response,
        org.springframework.security.access.AccessDeniedException exception
    ) throws java.io.IOException, jakarta.servlet.ServletException;
}
```

- `request`: HTTP request data to identify the resource being accessed.
- `response`: where HTTP status, `Content-Type`, and response body are written.
- `exception`: the access denial error. It can be logged safely on the server side, but **never return raw stack traces or internal rule details** externally.

Without customization, `AccessDeniedHandlerImpl` typically sends a 403 error using `sendError`; it also supports forwarding to a configured error page. When an API requires a stable JSON structure, we can implement a custom handler.

## 3. Runnable Example: Returning JSON 403 for Unauthorized Users

The sample project uses HTTP Basic to make it easy to observe three cases: not logged in, logged in without permission, and logged in with permission. HTTP Basic and in-memory passwords are **for illustration only**, and must not be used as a password storage approach in real production systems.

### 3.1. Structure and Dependencies

```text
security-denied-demo/
|-- pom.xml
|-- src/main/java/com/example/securitydemo/
|   |-- SecurityDemoApplication.java
|   |-- SecurityConfig.java
|   |-- JsonAccessDeniedHandler.java
|   +-- DemoController.java
+-- src/test/java/com/example/securitydemo/
    +-- AuthorizationResponseTest.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>security-denied-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>
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

Note that Spring Security 6+ uses the **`jakarta.servlet`** Servlet API, no longer `javax.servlet`. In a project that already has Spring Boot and equivalent dependencies, simply apply the Java classes below.

### 3.2. Starting the Application

`src/main/java/com/example/securitydemo/SecurityDemoApplication.java`:

```java
package com.example.securitydemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityDemoApplication.class, args);
    }
}
```

### 3.3. Custom Handler Returning a 403 Response

`src/main/java/com/example/securitydemo/JsonAccessDeniedHandler.java`:

```java
package com.example.securitydemo;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.stereotype.Component;

@Component
public class JsonAccessDeniedHandler implements AccessDeniedHandler {
    private final ObjectMapper objectMapper;

    public JsonAccessDeniedHandler(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public void handle(
            HttpServletRequest request,
            HttpServletResponse response,
            AccessDeniedException exception) throws IOException {
        response.setStatus(HttpServletResponse.SC_FORBIDDEN);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setHeader("Cache-Control", "no-store");

        Map<String, String> body = Map.of(
                "code", "ACCESS_DENIED",
                "message", "Bạn không có quyền truy cập tài nguyên này",
                "path", request.getRequestURI()
        );
        objectMapper.writeValue(response.getOutputStream(), body);
    }
}
```

Explanation of the choices:

- `SC_FORBIDDEN` is HTTP **403**; do not return 200 with an error in the body.
- `Content-Type: application/json` and UTF-8 help the client handle Vietnamese text.
- `ObjectMapper` provided by Spring Boot ensures JSON is properly escaped; `Map.of` does not guarantee JSON field order, so the client must check **field names** rather than relying on order.
- `Cache-Control: no-store` prevents caching of denied responses containing request info.
- The handler **does not call `filterChain.doFilter`**, does not dispatch to the controller, and does not write content twice.
- `exception` is received per the interface, but the example intentionally omits exception details from the client response. In real systems, you can log an event code/correlation ID on the server.

### 3.4. Configuring Rules and Attaching the Handler to SecurityFilterChain

`src/main/java/com/example/securitydemo/SecurityConfig.java`:

```java
package com.example.securitydemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            JsonAccessDeniedHandler accessDeniedHandler) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .exceptionHandling(ex -> ex
                .accessDeniedHandler(accessDeniedHandler)
            );

        return http.build();
    }

    @Bean
    UserDetailsService users() {
        UserDetails reader = User.withUsername("reader")
                .password("{noop}reader123")
                .roles("READER")
                .build();
        UserDetails admin = User.withUsername("admin")
                .password("{noop}admin123")
                .roles("ADMIN")
                .build();
        return new InMemoryUserDetailsManager(reader, admin);
    }
}
```

`hasRole("ADMIN")` requires an authority named **`ROLE_ADMIN`** by prefix convention. Thus `admin`'s `roles("ADMIN")` matches, while `roles("READER")` lacks permission. If the system assigns granular authority strings such as `report:read`, use `hasAuthority("report:read")`. **Do not write `hasRole("ROLE_ADMIN")`** with the default prefix configuration, because it will prepend the `ROLE_` prefix again.

Configuring `.exceptionHandling(ex -> ex.accessDeniedHandler(...))` sets the handler for this security chain. It does not replace `authorizeHttpRequests`, does not automatically grant permissions, and does not turn authentication errors into authorization errors.

### 3.5. Controller to Observe Results

`src/main/java/com/example/securitydemo/DemoController.java`:

```java
package com.example.securitydemo;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {
    @GetMapping("/api/admin/report")
    public Map<String, String> report() {
        return Map.of("report", "ready");
    }

    @GetMapping("/api/profile")
    public Map<String, String> profile() {
        return Map.of("profile", "visible");
    }
}
```

Only `admin` is allowed to access `/api/admin/report`. Both `reader` and `admin`, once authenticated, can access `/api/profile`.

### 3.6. Running and Testing via HTTP

Requires JDK 17+ and Maven 3.9+. Run from the directory containing `pom.xml`:

```bash
mvn spring-boot:run
```

Open another terminal (on Windows PowerShell use `curl.exe` if `curl` is aliased to another command):

```bash
# 1. Not logged in
curl -i http://localhost:8080/api/admin/report

# 2. Logged in with ROLE_READER, but endpoint requires ROLE_ADMIN
curl -i -u reader:reader123 http://localhost:8080/api/admin/report

# 3. Logged in with ROLE_ADMIN
curl -i -u admin:admin123 http://localhost:8080/api/admin/report

# 4. Reader is allowed to view profile
curl -i -u reader:reader123 http://localhost:8080/api/profile
```

Results to observe:

| Request | Expected Status | Notable Content |
|---|---|---|
| No credentials to report | `401 Unauthorized` | HTTP Basic entry point may send `WWW-Authenticate` header |
| Reader to report | `403 Forbidden` | JSON has `code = ACCESS_DENIED`, `path = /api/admin/report` |
| Admin to report | `200 OK` | JSON contains `"report":"ready"` |
| Reader to profile | `200 OK` | JSON contains `"profile":"visible"` |

Example **body** of the second call (key order may vary):

```json
{
  "code": "ACCESS_DENIED",
  "message": "Bạn không có quyền truy cập tài nguyên này",
  "path": "/api/admin/report"
}
```

If using form login instead of HTTP Basic, anonymous access is usually redirected to the login page with 302; do not hardcode tests assuming every Spring Security application returns 401 for anonymous users.

## 4. Automated Testing: Verifying 401, 403, and 200 Branches

Create `src/test/java/com/example/securitydemo/AuthorizationResponseTest.java`:

```java
package com.example.securitydemo;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationResponseTest {
    @Autowired
    MockMvc mvc;

    @Test
    void anonymousIsChallenged() throws Exception {
        mvc.perform(get("/api/admin/report"))
           .andExpect(status().isUnauthorized());
    }

    @Test
    void readerGetsCustomForbiddenBody() throws Exception {
        mvc.perform(get("/api/admin/report")
                .with(user("reader").roles("READER")))
           .andExpect(status().isForbidden())
           .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
           .andExpect(jsonPath("$.code").value("ACCESS_DENIED"))
           .andExpect(jsonPath("$.path").value("/api/admin/report"));
    }

    @Test
    void adminCanReadReport() throws Exception {
        mvc.perform(get("/api/admin/report")
                .with(user("admin").roles("ADMIN")))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.report").value("ready"));
    }

    @Test
    void readerCanReadProfile() throws Exception {
        mvc.perform(get("/api/profile")
                .with(user("reader").roles("READER")))
           .andExpect(status().isOk());
    }
}
```

Run:

```bash
mvn test
```

The `with(user(...))` test helper creates a mock principal for the MockMvc request and **does not verify passwords in `UserDetailsService`**; thus this test verifies **authorization + response format**, while the `curl -u` commands above test the actual HTTP Basic flow as well. If running MockMvc via `standaloneSetup`, you must integrate the Spring Security filter chain; `@SpringBootTest` + `@AutoConfigureMockMvc` in the example already includes that integration.

## 5. When to Apply and How to Extend

**JSON APIs:** Customize `AccessDeniedHandler` when frontend/mobile clients need a consistent error schema to display messages, redirect, or log event codes. Maintain status 403 and a stable error code; separate user-facing messages from internal technical details.

**HTML Applications:** `AccessDeniedHandlerImpl` can be configured to forward to an error page (preserving status 403). Choose forward/HTML when the browser needs a notification page, instead of forcing every request to receive JSON.

**Method-Level Authorization:** Add `@EnableMethodSecurity` and use `@PreAuthorize("hasAuthority('report:read')")` on Spring-managed methods when permissions depend on business logic or data. When the call passes through a suitable secured web flow, insufficient-permission errors can be translated into HTTP 403; method calls outside HTTP do not have an `HttpServletResponse` for `AccessDeniedHandler` to handle. Both service and endpoint layers should be tested.

**Multiple `SecurityFilterChain`s:** Each chain has its own `securityMatcher(...)` scope and configuration. A handler registered on chain A does not automatically apply to requests entering chain B; you must find which chain actually matches the endpoint under test.

**OAuth2 Resource Server/Bearer tokens:** A valid token with insufficient scope typically needs a protocol-compliant 403 response and a `WWW-Authenticate` header, which may contain `insufficient_scope`. Spring Security provides `BearerTokenAccessDeniedHandler` for this requirement. Before replacing it with a custom JSON handler, check and preserve standard headers/directives required by OAuth2 clients; the JSON handler in the HTTP Basic example does not cover all Bearer token behaviors.

## 6. Common Errors and Root Cause Identification

| Symptom | Cause to Check | How to Handle |
|---|---|---|
| Anonymous returns 401, 403 handler does not run | `AuthenticationEntryPoint` handles that branch correctly | Test with an **authenticated** account that lacks permissions |
| Logged in yet still able to access resource | Rule matches wrongly, broader rule placed earlier, or authorities differ from expected | Review `requestMatchers`, rule order, `hasRole`/`hasAuthority`, and actual authorities |
| 403 returned, but body is not custom JSON | Request entered another chain; error came from CSRF/CORS/other filter; response already committed | Identify the filter/chain raising the error, check logs, and test the exact path |
| `@RestControllerAdvice` does not catch errors from filters | Security errors may occur outside the MVC exception handling cycle | Configure `exceptionHandling` in `HttpSecurity` instead of relying only on controller advice |
| 500 response when customizing handler | JSON serializer throws an error or response has already started writing | Set status/headers before body; do not write twice or call `sendError` after writing JSON |
| Role "ADMIN" still gets 403 | Confusing `ROLE_ADMIN` with `ADMIN` or actual permissions not mapped | Check the `GrantedAuthority` list and avoid duplicating prefixes |
| POST API receives 403 despite correct permissions | May be missing CSRF token in a session/cookie-based app | Distinguish CSRF from authorization; configure CSRF per auth mechanism and threat model |
| Handler not called from custom filter | Exception thrown before `ExceptionTranslationFilter` or caught elsewhere | Check filter position and exception handling scope; do not assume all 403s go through one handler |

Some operational principles:

1. **Block at the rules, present in the handler:** never use the handler to relax permissions, alter `Authentication`, or continue a denied request.
2. **Do not leak data:** return a generic error code; do not send exception messages, stack traces, sensitive policy names, tokens, or lists of missing roles. Avoid putting URIs/queries with sensitive data in the response; the `path` field in the example is just the plain path.
3. **Preserve HTTP semantics:** 403 when authenticated but lacking permission; the entry point decides how to request login/authentication. For Bearer, preserve the OAuth2 protocol.
4. **Test the success branch too:** a test checking only 403 does not prove an authorized user can still get in. Always test at least 401/403/200 in the applicable application context.
5. **Do not mechanically disable CSRF to "fix" 403 errors:** state-changing requests using sessions/cookies generally still need CSRF protection.
6. **Separate technical messages from user messages:** logging/monitoring gets a correlation ID, while the client receives non-leaking content.

## 7. Self-Assessment Checklist

- [ ] Identify **who** lacks permission (authenticated) and **which** rule denied the request.
- [ ] Distinguish between `AuthenticationEntryPoint` and `AccessDeniedHandler`.
- [ ] Understand that `ExceptionTranslationFilter` only translates errors into HTTP responses; `AuthorizationFilter` enforces request rules.
- [ ] Register the handler in the right `SecurityFilterChain` using `exceptionHandling(...)`.
- [ ] Ensure the 403 JSON has proper status, charset, and content without leaking sensitive details.
- [ ] Test 401 (anonymous), 403 (reader lacking permission), and 200 (admin with permission).
- [ ] Additionally check CSRF, Bearer tokens, or method security if the application uses these mechanisms.

## Official References

- Spring Security — [Servlet architecture and ExceptionTranslationFilter](https://docs.spring.io/spring-security/reference/servlet/architecture.html).
- Spring Security — [`AccessDeniedHandler` API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/access/AccessDeniedHandler.html).
- Spring Security — [Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html).
- Spring Security — [Spring MVC Test and mocking users](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html).
- Spring Security — [Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html).
