# Components Handling Success, Failure, and Login Challenges

A request to a Spring Boot application may be allowed, redirected to a login page, given a 401, or denied with a 403. These responses are not decided by a single component. Spring Security provides extension points with **distinct responsibilities**: `AuthenticationSuccessHandler`, `AuthenticationFailureHandler`, `AuthenticationEntryPoint`, `AccessDeniedHandler`, and `ExceptionTranslationFilter`. Understanding the boundaries between them helps you configure both form-login websites and REST APIs using HTTP Basic or Bearer tokens properly.

This lesson focuses on the **component map and processing flows** in modern Spring Security Servlet/MVC, along with a runnable example on Java 17 and Spring Boot 3.3.x. Exact behaviors depend on authentication type, `SecurityFilterChain` ordering, and application configuration; not every request passes through every handler.

## 1. Distinguishing Four Common Outcomes

Suppose an application exposes these resources:

- `GET /public`: anyone can view.
- `GET /user`: requires login only.
- `GET /admin`: must have role `ADMIN`.
- `GET /api/me`: requires HTTP Basic.
- `GET /api/admin`: requires HTTP Basic and role `ADMIN`.

A request falls into one of these scenarios:

| Scenario | What is happening | Typical response |
| --- | --- | --- |
| Accessing a public resource | Authorization rules permit without authentication. | 200 if Controller handles successfully. |
| Anonymous user accessing a resource requiring login | No suitable authenticated identity yet. | Browser form login: 302 to `/login`; HTTP Basic/Bearer API: typically 401. |
| User submits valid username and password via form login | An authentication filter completes successfully. | Success handler decides the redirect or response after login. |
| User submits wrong password via form login | The authentication filter catches `AuthenticationException` in that login flow. | Failure handler typically redirects to `/login?error` or returns an error. |
| Logged-in user lacks permission | Authorization denies the action. | Typically 403, handled via `AccessDeniedHandler` in that flow. |
| POST request blocked by CSRF | CSRF protection rejects the request. | Typically 403; error handling location may differ from URL authorization flow. |

**Crucial distinction:** "login failed" is an event during **credential verification**, whereas "login required to view a resource" is a **request to initiate authentication** when accessing a protected resource. The two scenarios can use two different handlers.

An anonymous `GET /user` request has not necessarily attempted a login; that is typically an **`AuthenticationEntryPoint`** case. A `POST /login` request with a wrong password is the classic **`AuthenticationFailureHandler`** case.

## 2. Map of Key Components

| Component | Role | When typically called | Example response |
| --- | --- | --- | --- |
| **AuthenticationSuccessHandler** | Decides the next step after **a successful authentication** in a filter flow using this handler. | Form login or interactive authentication filter completes authentication. | 302 to `/user`; redirect to saved request; return JSON by design. |
| **AuthenticationFailureHandler** | Handles **failure while executing an authentication flow** that uses a failure handler. | `POST /login` with wrong password, locked account, or invalid credentials in form login. | 302 to `/login?error`; 401 JSON in an API login depending on configuration. |
| **AuthenticationEntryPoint** | **Initiates an authentication mechanism** when a request requires identity without suitable authentication. | Anonymous visitor hitting a login-required page; API missing/invalid credentials when that mechanism uses an entry point. | Redirect to login page; 401 and `WWW-Authenticate`. |
| **AccessDeniedHandler** | Handles a request denied access in a flow requiring an access-denied response. | Valid principal lacking role/scope/permission; certain CSRF errors per filter. | 403; access-denied page; safe error JSON. |
| **ExceptionTranslationFilter** | Translates `AuthenticationException`/`AccessDeniedException` thrown **downstream** into appropriate HTTP behavior. | A downstream authorization filter reports missing authentication or insufficient permissions. | Calls entry point or access denied handler based on authentication state. |
| **RequestCache** | May remember the request that triggered authentication to return to the target after login. | Anonymous user visits a protected page, then logs in successfully. | `SavedRequestAwareAuthenticationSuccessHandler` uses saved request if appropriate. |

These components **do not replace** the authentication engine or the authorization engine. Other related components include:

- **AuthenticationManager / AuthenticationProvider**: verifies credentials and produces an authenticated `Authentication` on success, or throws an appropriate `AuthenticationException`.
- **Authentication (principal + authorities)**: represents the identity and permissions established by a trusted mechanism.
- **SecurityContextHolder / SecurityContextRepository**: how `SecurityContext` is accessed and saved/restored per configured mechanism and strategy.
- **UsernamePasswordAuthenticationFilter**: accepts form login POST on the default `/login` path, calls authentication, then invokes success/failure handlers.
- **BasicAuthenticationFilter**: handles HTTP Basic; its failure path typically calls `AuthenticationEntryPoint`, meaning it does not run form-login failure handlers.
- **AuthorizationFilter**: enforces configured access policies; denial can throw `AccessDeniedException`.
- **CsrfFilter**: validates tokens on requests covered by CSRF policy, usually before the Controller runs.
- **SecurityFilterChain / FilterChainProxy**: organizes the matching filter chain for a request. With multiple chains, the first matching chain determines the filters and policy for the request.

Component names indicate common roles, yet runtime behavior must be verified against actual configuration and call paths. For instance, **`AuthenticationSuccessHandler` is not a callback invoked after every HTTP request carrying a valid `Authentication`**.

## 3. Decision Diagram from Request to Response

This is a conceptual diagram for an application with both web form login and an API. It shows only main branches; in practice, multiple filters can reject early or provide dedicated entry points.

~~~mermaid
flowchart TD
    R["HTTP request"] --> C["Matching SecurityFilterChain"]
    C --> L{"Is the request performing login?"}
    L -- "Yes" --> A["Filter calls AuthenticationManager"]
    A --> AS{"Credentials valid?"}
    AS -- "Yes" --> SH["AuthenticationSuccessHandler"]
    AS -- "No" --> FH["AuthenticationFailureHandler"]
    L -- "No" --> P["Build / restore SecurityContext as appropriate"]
    P --> Z["Authorization check"]
    Z --> AU{"Permitted?"}
    AU -- "Yes" --> CT["Controller / Service"]
    AU -- "No" --> EX["AccessDeniedException or denial handling"]
    EX --> TYPE{"Principal sufficiently authenticated?"}
    TYPE -- "No / anonymous" --> EP["AuthenticationEntryPoint"]
    TYPE -- "Authenticated" --> DH["AccessDeniedHandler"]
~~~

In a typical authorization branch, **`ExceptionTranslationFilter`** is responsible for translating downstream exceptions into choosing `AuthenticationEntryPoint` or `AccessDeniedHandler`. Some authentication filters catch errors themselves and invoke an entry point/failure handler directly. There is no guarantee that every 401/403 exception passes through a single spot.

### 3.1. Flow A: Accessing a Protected Page While Unauthenticated

~~~text
GET /user (anonymous)
    -> Web SecurityFilterChain
    -> Authorization sees authenticated() required
    -> ExceptionTranslationFilter catches downstream exception
    -> AuthenticationEntryPoint for form login
    -> HTTP 302 Location: /login
    -> Browser GET /login
    -> Login page is rendered
~~~

**No password submission has occurred yet**, so `AuthenticationFailureHandler` is normally not called. In form-login setups with `RequestCache`, the application can also save the original request so that after login the user returns to the target resource; this depends on handler and session policy.

### 3.2. Flow B: Successful Form Login Submission

~~~text
POST /login (valid username/password + CSRF token)
    -> UsernamePasswordAuthenticationFilter
    -> AuthenticationManager / AuthenticationProvider
    -> Authentication succeeds
    -> Create/save SecurityContext per configured mechanism
    -> AuthenticationSuccessHandler
    -> e.g. HTTP 302 Location: /user
~~~

Here the success handler receives the successful `Authentication`. It decides navigation or response for the **login operation**; it does not grant roles itself and does not verify business-object permissions.

### 3.3. Flow C: Failed Form Login Submission

~~~text
POST /login (wrong password, valid request)
    -> UsernamePasswordAuthenticationFilter
    -> AuthenticationManager / AuthenticationProvider
    -> AuthenticationException
    -> AuthenticationFailureHandler
    -> e.g. HTTP 302 Location: /login?error
~~~

Failure due to bad credentials is handled by the failure handler **inside that login filter**. If `POST /login` is rejected by `CsrfFilter` **before the authenticator runs**, the outcome can be 403 rather than a redirect with a bad-password message.

### 3.4. Flow D: Logged In Yet Missing Role

~~~text
GET /admin (principal USER)
    -> Authentication is already valid
    -> Authorization requires ROLE_ADMIN
    -> Denied
    -> AccessDeniedHandler in that flow
    -> HTTP 403 Forbidden
~~~

This is not a wrong password, and there is no reason to re-prompt for login when the user is sufficiently authenticated yet lacks the role. Under some policies for private resources, apps mask existence with 404; what matters is returning no unauthorized data and executing no unauthorized side effects.

### 3.5. Flow E: API Using HTTP Basic

~~~text
GET /api/me, no Authorization
    -> Authorization requires authenticated()
    -> Basic AuthenticationEntryPoint
    -> HTTP 401 + WWW-Authenticate: Basic ...

GET /api/me, valid Authorization: Basic
    -> BasicAuthenticationFilter authenticates
    -> Authorization permits
    -> Controller returns HTTP 200
~~~

A successful Basic authentication **does not mean** a form-login `AuthenticationSuccessHandler` runs. `BasicAuthenticationFilter` follows its own mechanism and can authenticate on every request that lacks a suitable `Authentication` in context. Bearer tokens with an OAuth2 Resource Server also have their own entry point and error handlers; never think of them as form login.

## 4. AuthenticationSuccessHandler: When Authentication Succeeds

The **`AuthenticationSuccessHandler`** interface defines how an application responds after an authentication filter completes login successfully. For form login, common options are:

- **`SimpleUrlAuthenticationSuccessHandler`**: redirects to a default URL or permitted target configured on it.
- **`SavedRequestAwareAuthenticationSuccessHandler`**: prioritizes redirecting to the request saved in `RequestCache` if present, falling back to a default target.
- **Custom handler**: returns JSON or redirects per custom logic, while staying secure and keeping secrets out of responses/logs.

Example configuration fragment for web form login:

~~~java
.formLogin(form -> form
    .successHandler(new SimpleUrlAuthenticationSuccessHandler("/user"))
)
~~~

This is a **snippet inside `HttpSecurity` configuration**, not a standalone Java program. It navigates to `/user` after a successful form login. With this handler, the original request is not automatically prioritized as with `SavedRequestAwareAuthenticationSuccessHandler`; that is an intentional UX decision.

**A success handler does not prove access to `/admin`.** After the redirect, `GET /admin` or `/user` is still checked by the new request's authorization policy. If the user lacks the role, `GET /admin` must still be denied.

### 4.1. On Saved Requests and Redirects

When a visitor hits `/checkout` before logging in, `RequestCache` can store a request as a return target. `SavedRequestAwareAuthenticationSuccessHandler` can redirect after login to the saved URL.

Keep in mind:

- Never read a client-supplied `returnUrl`/`next` parameter and redirect arbitrarily; restrict targets to trusted destinations to prevent open redirects.
- Never blindly "replay" an old `POST` request with its body and side effects. `RequestCache` mainly serves navigating back to a resource; state-changing methods, payloads, and CSRF need dedicated design.
- For stateless REST APIs, `RequestCache` and login redirects are usually inappropriate; return explicit API responses rather than HTML redirects.
- Session fixation and security context persistence are separate concerns; a success handler does not replace Spring Security's session protections.

## 5. AuthenticationFailureHandler: When Authentication Fails

**`AuthenticationFailureHandler`** handles failure of an authentication flow configured with it, typically `POST /login` in form login.

Example:

~~~java
.formLogin(form -> form
    .failureHandler(
        new SimpleUrlAuthenticationFailureHandler("/login?error")
    )
)
~~~

When the password is wrong, the failure handler redirects to the configured URL. It receives the `AuthenticationException` describing the technical reason, yet public responses should limit information disclosure.

Related exceptions include `BadCredentialsException`, `DisabledException`, `LockedException`, or `CredentialsExpiredException` depending on the `AuthenticationProvider` and account state. **Do not return messages that let attackers distinguish "whether the user exists"** unless business requirements and appropriate mitigations exist. Log the internal cause per policy while showing a generic message to the user.

### 5.1. Not Every Error Invokes FailureHandler

Distinguish these cases:

| Scenario | Component typically handling it |
| --- | --- |
| Wrong password on `POST /login` through the form authentication flow | `AuthenticationFailureHandler`. |
| Accessing `GET /admin` while unauthenticated | `AuthenticationEntryPoint`. |
| Sending invalid HTTP Basic credentials to `GET /api/me` | `BasicAuthenticationFilter` typically calls `AuthenticationEntryPoint`. |
| Missing/expired Bearer token in Resource Server | Bearer entry point or matching auth failure mechanism. |
| Logged in yet lacking permission | `AccessDeniedHandler`. |
| `POST /login` missing CSRF token | `CsrfFilter` may return 403 before the login authentication filter runs. |
| Business exception thrown in Controller/service | Application exception handler; not automatically `AuthenticationFailureHandler`. |

If a custom failure handler writes a JSON response, set an appropriate status (e.g. 401 for wrong credentials in an API login), exact `Content-Type`, minimal error info, and never include passwords/tokens in the body. For websites, redirecting to the login page with a generic message is standard.

## 6. AuthenticationEntryPoint: When a Request Needs Authentication

**`AuthenticationEntryPoint`** initiates the "authentication challenge" when a request lacks proper authentication for a protected resource or an authentication mechanism needs to signal bad credentials.

Typical implementations:

| Implementation | Purpose | Typical behavior |
| --- | --- | --- |
| **LoginUrlAuthenticationEntryPoint** | Web apps using form login. | 302 redirect to `/login`. |
| **BasicAuthenticationEntryPoint** | HTTP Basic. | 401 with `WWW-Authenticate: Basic realm=...` |
| **BearerTokenAuthenticationEntryPoint** | OAuth2 Resource Server using Bearer tokens. | 401 and contextual Bearer challenge. |
| **HttpStatusEntryPoint** | Simply return a chosen status code. | e.g. 401 without rendering a login page. |

These are choices for **different authentication mechanisms**, not an arbitrary plug-and-play list. For example, HTTP Basic clients expect the proper challenge; replacing it with an empty 401 alters client negotiation/experience.

Conceptual example:

~~~text
Client GET /api/me without Authorization
           |
           v
Authorization requires user
           |
           v
AuthenticationEntryPoint for HTTP Basic
           |
           v
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="api"
~~~

**401** usually corresponds to missing or invalid credentials. If an API uses Bearer tokens, challenge/error headers must match the chosen Bearer scheme. **302** is a navigation response meant for browser form login. Never configure an HTML login redirect entry point for REST clients expecting JSON or 401.

### 6.1. How Does AuthenticationEntryPoint Differ from FailureHandler?

- **Entry point**: "This resource requires authentication; begin/challenge" — e.g. anonymous `GET /admin`.
- **Failure handler**: "An active login attempt in this flow failed" — e.g. `POST /login` with a wrong password.

Some filters like HTTP Basic call the entry point directly on bad credentials; hence the distinction is not by status code (both can yield 401), but by **position and event within the flow**.

## 7. AccessDeniedHandler: Authenticated Yet Lacking Permission

When an authenticated request is rejected by authorization, `AccessDeniedHandler` typically determines the response:

- HTTP 403 for a REST API; concise JSON if the API contract requires it.
- An "access denied" page for a web application.
- Appropriate denied audit/event logging without leaking data.
- Optionally 404 to avoid revealing resource existence under an agreed policy.

Example configuration snippet:

~~~java
.exceptionHandling(exceptions -> exceptions
    .accessDeniedHandler((request, response, denied) ->
        response.sendError(403)
    )
)
~~~

This snippet fits inside a `SecurityFilterChain` for flows needing a 403 response, though not every 403 passes through that handler. For example, `CsrfFilter` can handle denials via its own configured `AccessDeniedHandler`. Proxies or Controllers can also return 403 themselves.

**Route authorization differs from object authorization.** `GET /api/orders/42` may satisfy `authenticated()`, yet you must still check whether `order.ownerId` matches the current principal/tenant. The service must prevent returning data or executing side effects when permissions are lacking. Returning 403 after an unauthorized DB write already occurred is not proper protection.

## 8. ExceptionTranslationFilter: Bridge from Exceptions to HTTP

`ExceptionTranslationFilter` is not responsible for logging in or verifying passwords. It **catches certain `AuthenticationException` or `AccessDeniedException` instances thrown by filters downstream in the chain** and translates them into the matching HTTP action:

1. On **`AuthenticationException`**, trigger authentication via `AuthenticationEntryPoint`.
2. On **`AccessDeniedException`** when the principal is anonymous or insufficiently authenticated under that logic, trigger `AuthenticationEntryPoint`.
3. On **`AccessDeniedException`** when the principal is sufficiently authenticated, invoke `AccessDeniedHandler`.

This decision occurs at exception-handling time. Spring Security uses `Authentication` info and trust resolvers to distinguish anonymous or remember-me users when appropriate. Never roll your own "any non-null object in `SecurityContext` means fully logged in" check.

High-level flow:

~~~mermaid
flowchart TD
    E["ExceptionTranslationFilter catches downstream exception"] --> T{"Exception type"}
    T -- "AuthenticationException" --> P["AuthenticationEntryPoint"]
    T -- "AccessDeniedException" --> S{"Anonymous / insufficient authentication?"}
    S -- "Yes" --> P
    S -- "No" --> D["AccessDeniedHandler"]
    P --> R1["401 challenge or 302 login depending on mechanism"]
    D --> R2["403 or configured denied response"]
~~~

**Important boundary:** a filter positioned **before** `ExceptionTranslationFilter` may handle exceptions itself. `BasicAuthenticationFilter` or `UsernamePasswordAuthenticationFilter` has its own logic when authentication fails. Therefore, never claim "every 401/403 comes from `ExceptionTranslationFilter`" across all setups.

## 9. Complete Example: Web Form Login and HTTP Basic API in Spring Boot

This example lets you observe **success/failure handlers**, **entry points**, and **access denied handlers** without mixing up website and API behavior. Two `SecurityFilterChain`s use different matchers:

- The API chain matches `/api/**` and uses HTTP Basic.
- The default web chain handles remaining requests and uses form login.

The example runs locally with JDK 17+, Maven 3.9+, and Spring Boot 3.3.6 (illustrative version in the 3.3.x line). Accounts/passwords are strictly for learning; HTTP Basic uses Base64, does not encrypt credentials, and must use HTTPS over real networks.

### 9.1. Directory Structure

~~~text
security-handlers-demo/
  pom.xml
  src/main/java/com/example/handlers/SecurityHandlersApplication.java
  src/main/java/com/example/handlers/DemoController.java
  src/main/java/com/example/handlers/SecurityConfig.java
  src/test/java/com/example/handlers/SecurityHandlersTests.java
~~~

### 9.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.6</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>security-handlers-demo</artifactId>
    <version>1.0.0</version>
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
~~~

### 9.3. SecurityHandlersApplication.java

~~~java
package com.example.handlers;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityHandlersApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityHandlersApplication.class, args);
    }
}
~~~

### 9.4. DemoController.java

~~~java
package com.example.handlers;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public String home() {
        return "home";
    }

    @GetMapping("/user")
    public String user(Authentication authentication) {
        return "web:" + authentication.getName();
    }

    @GetMapping("/admin")
    public String admin() {
        return "web-admin";
    }

    @GetMapping("/api/public")
    public String apiPublic() {
        return "api-public";
    }

    @GetMapping("/api/me")
    public String me(Authentication authentication) {
        return "api:" + authentication.getName();
    }

    @GetMapping("/api/admin")
    public String apiAdmin() {
        return "api-admin";
    }
}
~~~

### 9.5. SecurityConfig.java

~~~java
package com.example.handlers;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.SimpleUrlAuthenticationFailureHandler;
import org.springframework.security.web.authentication.SimpleUrlAuthenticationSuccessHandler;

@Configuration
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .requestMatchers("/api/me").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .exceptionHandling(ex -> ex.accessDeniedHandler(
                (request, response, denied) ->
                    response.sendError(HttpServletResponse.SC_FORBIDDEN)
            ));

        // CSRF remains enabled by default; example only calls GET endpoints.
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .requestMatchers("/user").authenticated()
                .anyRequest().denyAll()
            )
            .formLogin(form -> form
                .successHandler(
                    new SimpleUrlAuthenticationSuccessHandler("/user")
                )
                .failureHandler(
                    new SimpleUrlAuthenticationFailureHandler("/login?error")
                )
                .permitAll()
            );

        // Uses default login page generated by Spring Security.
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password(encoder.encode("demo"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("demo-admin"))
                .roles("ADMIN")
                .build()
        );
    }
}
~~~

**Reading the configuration:**

1. **`@Order(1)` + `securityMatcher("/api/**")`** applies HTTP Basic to the API; API policy does not automatically use form-login handlers.
2. **`@Order(2)`** is the web chain with no narrow `securityMatcher`, acting as fallback for remaining paths.
3. **API Basic** returns a challenge when login is needed; valid user `reader` still gets 403 at `/api/admin`.
4. **Web form login** uses the success handler to redirect to `/user` after login, and the failure handler to `/login?error` if username/password is wrong.
5. **The `/login` page** is provided by the default `formLogin` configuration with `permitAll`. When a browser submits the form, it requires the CSRF token generated by the login page; a manual request missing the token can get 403 before reaching the failure handler.
6. **The custom API `AccessDeniedHandler`** calls `sendError(403)`, changing only how denials respond in that chain. The web chain uses default access-denied handling.
7. **Each mechanism's `AuthenticationEntryPoint`** is configured through `formLogin`/`httpBasic`. You do not need to write a custom EntryPoint just to observe default behavior.
8. **Never disable CSRF globally.** The demo only has business GET endpoints; adding POST/PUT/DELETE requires designing and testing CSRF matching your credential and client types.
9. **Role `ADMIN`** is checked by Spring Security against authority `ROLE_ADMIN` when using `hasRole("ADMIN")`.
10. Demo passwords are registered in `InMemoryUserDetailsManager` via `PasswordEncoder`; real apps must use a proper identity store and secret lifecycle.

### 9.6. Running and Observing with curl

From the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

In another terminal run (use `curl.exe` in PowerShell; Linux/macOS can use `curl`):

~~~powershell
curl.exe -i http://localhost:8080/
curl.exe -i http://localhost:8080/user
curl.exe -i http://localhost:8080/api/public
curl.exe -i http://localhost:8080/api/me
curl.exe -i -u reader:demo http://localhost:8080/api/me
curl.exe -i -u reader:demo http://localhost:8080/api/admin
curl.exe -i -u admin:demo-admin http://localhost:8080/api/admin
~~~

**Expected HTTP results:**

| Request | Status | Observation |
| --- | --- | --- |
| `GET /` | 200 | Body `home`, public web route. |
| Anonymous `GET /user` | 302 | `Location` header to `/login` from form-login entry point. |
| `GET /api/public` | 200 | Body `api-public`. |
| Anonymous `GET /api/me` | 401 | HTTP Basic authentication challenge. |
| `GET /api/me` as `reader`/`demo` | 200 | Body `api:reader`. |
| `GET /api/admin` as `reader`/`demo` | 403 | User has identity yet lacks `ROLE_ADMIN`. |
| `GET /api/admin` as `admin`/`demo-admin` | 200 | Body `api-admin`. |

Exact headers such as `Date`, `Cache-Control`, `Set-Cookie`, and `Location` vary by Servlet container and version. Read **status and cause** rather than depending byte-for-byte on every header.

To observe form login's **`AuthenticationSuccessHandler` / `AuthenticationFailureHandler`**, open `http://localhost:8080/user` in a browser. You will be redirected to `/login`. Submit **`reader` / `demo`** via the form: the browser redirects to `/user` and displays **`web:reader`**. Try a wrong password: the browser is sent to **`/login?error`** by the failure handler. While logged in as `reader`, opening `/admin` yields **403**. With `admin`/`demo-admin`, `/admin` returns body `web-admin`.

When submitting login manually with `curl`, you must handle the cookie jar and the login page's real CSRF token; skipping that step causes a 403 from CSRF, which is **not** evidence that the failure handler is broken.

## 10. Writing Tests Confirming the Right Handler per Scenario

Spring Security Test supports `MockMvc` to verify different responses. The test file below pairs with the example project above, using the test dependencies declared in `pom.xml`.

**SecurityHandlersTests.java**:

~~~java
package com.example.handlers;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityHandlersTests {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousWebUserIsRedirectedToLogin() throws Exception {
        mvc.perform(get("/user"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("http://localhost/login"));
    }

    @Test
    void anonymousApiClientGetsBasicChallenge() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void basicUserCanReadOwnApiIdentity() throws Exception {
        mvc.perform(get("/api/me").with(httpBasic("reader", "demo")))
            .andExpect(status().isOk())
            .andExpect(content().string("api:reader"));
    }

    @Test
    void basicUserCannotCallAdminApi() throws Exception {
        mvc.perform(get("/api/admin").with(httpBasic("reader", "demo")))
            .andExpect(status().isForbidden());
    }

    @Test
    void successfulFormLoginRedirectsToUser() throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "reader")
                .param("password", "demo"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/user"));
    }

    @Test
    void failedFormLoginRedirectsToErrorPage() throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "reader")
                .param("password", "wrong"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"));
    }

    @Test
    void loginWithoutCsrfTokenIsRejected() throws Exception {
        mvc.perform(post("/login")
                .param("username", "reader")
                .param("password", "demo"))
            .andExpect(status().isForbidden());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

The tests prove:

- Anonymous visitors on web routes redirect to login; the API returns 401 instead.
- Valid Basic user is authenticated, yet `USER` still cannot reach the admin API.
- Successful login runs through the success handler; wrong-password login runs through the failure handler.
- A login request missing a CSRF token is blocked, showing that **errors before the authentication filter** do not necessarily use the failure handler.

**Note on redirect URLs in MockMvc:** the test above expects an absolute redirect like `http://localhost/login` matching `LoginUrlAuthenticationEntryPoint` in default configuration. If configuring proxies, servlet context paths, or custom `Location` construction, assert against the URL your app actually produces rather than hardcoding assumptions across all environments.

A 403 test must also verify **no unauthorized side effects** occur if the endpoint writes to a DB, transfers money, or publishes messages. A handler returning the right status is not enough to prove authorization logic wasn't bypassed.

## 11. When an API Needs JSON Instead of a Redirect

Form-login websites sensibly redirect to a login page. REST APIs called by `fetch`, `curl`, or backend services normally need 401/403 statuses and concise JSON so clients can handle errors cleanly.

A custom `AuthenticationEntryPoint` can return 401 JSON per API contract:

~~~java
.exceptionHandling(ex -> ex.authenticationEntryPoint(
    (request, response, authenticationException) -> {
        response.setStatus(401);
        response.setContentType("application/json");
        response.getWriter().write("{\"error\":\"unauthenticated\"}");
    }
))
~~~

This snippet is an **illustration inside a dedicated API `SecurityFilterChain`**; do not paste it directly into section 9's HTTP Basic demo if you want to keep the `WWW-Authenticate` challenge. For Basic/Bearer, standard entry points that handle challenges and protocol-specific headers are usually better; any JSON response must be designed to preserve proper authentication semantics.

Similarly, a custom `AccessDeniedHandler` can return 403 JSON:

~~~java
.exceptionHandling(ex -> ex.accessDeniedHandler(
    (request, response, denied) -> {
        response.setStatus(403);
        response.setContentType("application/json");
        response.getWriter().write("{\"error\":\"forbidden\"}");
    }
))
~~~

This too is an **illustrative snippet**, and must not be pasted alongside another `exceptionHandling` configuration on the same chain without merging them. Production responses should use proper JSON serialization and consistent headers, avoiding raw exception details or untrusted inputs in the body.

In Spring Boot, handling exceptions in **`@ControllerAdvice`** fits errors thrown inside Controllers/Services, whereas requests blocked by security filters before reaching the Controller **do not necessarily** reach `ControllerAdvice`. To customize 401/403 responses from security filters, configure the entry point / access-denied handler in the right place.

## 12. Distinguishing Session, Basic, Bearer, and Remember-Me Flows

### 12.1. Form Login + Session

- Usually involves a `/login` page, session cookie, and redirects.
- After successful form login, Spring Security can update the session/security context per configuration.
- `AuthenticationSuccessHandler` controls post-login navigation.
- `AuthenticationFailureHandler` runs when a login attempt fails.
- `RequestCache` can save the pre-login target URL.
- CSRF protection is especially critical on form POSTs and state-changing requests with cookies/sessions.

### 12.2. HTTP Basic

- Each request may carry `Authorization: Basic ...`; credentials must be verified via an appropriate provider and password encoder.
- Typically uses 401 + `WWW-Authenticate` to challenge; invalid credentials are usually handled by the Basic filter/entry point.
- Does not invoke form-login success/failure handlers by default.
- Basic is only Base64 over credentials, requiring HTTPS on real networks.
- Never assume HTTP Basic is immune to CSRF; browsers can auto-send cached credentials depending on context. CSRF decisions must reflect how clients actually authenticate and send requests.

### 12.3. Bearer Token / Resource Server

- Clients send `Authorization: Bearer ...`; the Resource Server verifies the token via trusted configuration, including signature or introspection and required claims.
- When missing or invalid, the Bearer entry point typically returns 401 with the appropriate challenge.
- When authenticated yet lacking scope/authority, the access-denied handler typically returns 403 and may include the corresponding Bearer header.
- Interactive OAuth2 login differs from a Resource Server validating Bearer tokens on APIs; do not lump every mechanism under "formLogin handlers".

### 12.4. Remember-Me and Authentication Trust Levels

Some web apps support remember-me authentication. Depending on policy, Spring Security can treat that level as **insufficient for especially sensitive actions**, prompting a full login again. When debugging re-authentication prompts, do not check only whether `Authentication` is non-null; inspect trust level and specific policies.

## 13. Common Mistakes

1. **Using `AuthenticationFailureHandler` to catch 401s from every endpoint.** Failure handlers serve specific authentication flows like form login. Unauthenticated requests to protected resources are normally handled via `AuthenticationEntryPoint`.
2. **Assuming `AuthenticationSuccessHandler` runs after every GET carrying a valid token.** It runs in authentication filter flows designed to call that handler, not as a counter for every authenticated request.
3. **Confusing 403 with wrong password.** Invalid credentials typically return 401 or redirect to `/login?error`; missing roles or CSRF failures yield 403.
4. **Returning 200 JSON for login errors.** HTTP status codes must accurately reflect the outcome; success/failure handlers decide the client-appropriate response.
5. **Turning `BasicAuthenticationEntryPoint` into an HTML login redirect for backend APIs.** Clients may receive unexpected 302/HTML; separate `SecurityFilterChain`s and entry points by client type.
6. **Writing custom handlers and forgetting `SecurityContext`/sessions.** Redirecting after login does not replace saving/restoring `SecurityContext`, session fixation protection, or testing subsequent authenticated requests.
7. **Letting `AuthenticationEntryPoint` redirect to an arbitrary client-supplied URL.** This can introduce open redirects; allowlist/validate targets when supporting `returnUrl`.
8. **Failing to distinguish security filter errors from `ControllerAdvice`.** `@ControllerAdvice` does not automatically catch all errors originating in the filter chain.
9. **Disabling CSRF to make `curl` form-login POSTs easier.** A missing CSRF token is a scenario to understand properly; never disable defenses just to make a test pass.
10. **Protecting URLs while skipping object-level authorization.** Reaching `/api/orders/**` does not mean a user can read/edit every order; the Service must check owner/tenant.
11. **Treating `ExceptionTranslationFilter` as the handler for every `AuthenticationException`.** Upstream authentication filters can call failure handlers or entry points directly; position in the chain matters.
12. **Configuring multiple `SecurityFilterChain`s without a fallback or with wrong ordering.** Requests can match an unintended chain; verify `securityMatcher`, ordering, and admin endpoints.
13. **Exposing uncontrolled exception messages in responses/logs.** Avoid leaking user existence, passwords, tokens, stack traces, or sensitive policy details.
14. **Asserting only status codes without checking side effects.** Denied paths must never write data or emit unauthorized events.

## 14. Method for Debugging a 302, 401, or 403 Response

Start from the concrete request and walk through these questions:

**1. Which `SecurityFilterChain` is the request entering?** Verify method, path, HTTP host, gateway rewrites, and whether `securityMatcher` matches the chain you intended.

**2. Is it performing login or accessing a resource?** `POST /login` with credentials differs from anonymous `GET /admin`. Ask whether a failure handler or entry point should be responsible.

**3. Were credentials processed?** Does HTTP Basic/Bearer have the right `Authorization` scheme? Does form login have the CSRF token, username/password params, and required session?

**4. What is the current `Authentication`?** Is the principal authenticated, with matching roles/scopes? Never trust client-asserted headers like `X-Role`.

**5. In which filter did the exception occur?** Bad credentials in `UsernamePasswordAuthenticationFilter`, missing CSRF token, or `AccessDeniedException` from authorization? Each follows a different path.

**6. Is the HTTP response right for the client?** Browsers may expect 302 to `/login`; service APIs expect 401 challenges; authenticated users lacking a role typically get 403. Inspect `WWW-Authenticate`, `Location`, `Content-Type`, and body.

**7. Was there an unexpected redirect or saved request?** A final 200 response could be the HTML login page after a 302 redirect, not the original resource.

**8. Are there business-security defects?** Even when the handler returns the right status, verify no DB updates, false audit records, emitted messages, or data leaks occurred on denial.

You can enable controlled logging during local experiments, while strictly avoiding logging credentials, tokens, session cookies, or personal data. Never leave sensitive debug logging enabled in production just to trace a filter branch quickly.

## 15. Self-Assessment Exercises

1. An unauthenticated visitor calls `GET /user`. Which component typically initiates login, and why is **`AuthenticationFailureHandler`** not appropriate here? **Hint:** no wrong password was submitted yet; `AuthenticationEntryPoint` applies.
2. A visitor submits `POST /login` with a wrong password and a valid CSRF token. Which handler typically runs? **Hint:** `AuthenticationFailureHandler`.
3. A valid user calls `GET /admin` without `ROLE_ADMIN`. Which handler typically produces the 403? **Hint:** `AccessDeniedHandler` after authorization rejects.
4. An HTTP Basic API returns 401 for a request without `Authorization`. Must `AuthenticationFailureHandler` be called? **Hint:** no; Basic entry point/challenge.
5. `POST /login` returns 403 before verifying the password. Name one cause and which component likely blocked it. **Hint:** `CsrfFilter`.
6. After successful form login, the app wants to return to the pre-login URL. Which components help, and what must be guarded? **Hint:** `RequestCache` and `SavedRequestAwareAuthenticationSuccessHandler`; validate redirects.
7. A handler returns 403, yet the Service already wrote to the DB beforehand. Is that safe? **Hint:** no; prevent side effects before denial.
8. Why are one `SecurityFilterChain` using form login for web and another chain using Basic/Bearer for API easier to reason about when two client types expect different responses? **Hint:** separated entry points and request matchers.

### Quick-Memory Checklist

- **SuccessHandler:** after successful login in a flow supporting that handler.
- **FailureHandler:** after failure of a specific login attempt.
- **EntryPoint:** initiates/challenges authentication when needed, or in certain filters when credentials are invalid.
- **AccessDeniedHandler:** handles access denied for an appropriate principal, typically returning 403.
- **ExceptionTranslationFilter:** translates certain downstream exceptions into HTTP actions via entry point/denied handler.
- **SecurityFilterChain:** determines the filter set and policy applied to a request; verify which chain actually matches.

## Conclusion

In Spring Security, **login succeeded**, **login failed**, **unauthenticated access to a protected resource**, and **authenticated yet lacking permission** are four distinct situations. `AuthenticationSuccessHandler`, `AuthenticationFailureHandler`, `AuthenticationEntryPoint`, and `AccessDeniedHandler` respond at different moments; `ExceptionTranslationFilter` translates downstream authentication/authorization exceptions into HTTP behavior. Understanding these flows lets you design web form logins and REST APIs that respond properly to each client type, wire handlers into the right `SecurityFilterChain`, and accurately test both status codes and side effects.
