# AuthenticationWebDetailsSource and Additional Request Metadata in Spring Security

> **Scope:** Spring Security Authentication on the **Servlet stack** (Spring MVC), focusing on **authentication filter integration** and passing HTTP request metadata into `Authentication.getDetails()`. The topic title uses `AuthenticationWebDetailsSource`; in the **official Spring Security 6.5 API**, the class you are looking for is **`WebAuthenticationDetailsSource`**, implementing `AuthenticationDetailsSource<HttpServletRequest, WebAuthenticationDetails>`. This lesson explains the default mechanism, writing custom sources/details, configuring form login/filters, trust boundaries, and testing with **Java 17+, Spring Boot 3.5.7, Spring Security 6.5, and MockMvc**.

## 1. Learning Outcomes

After studying this lesson, you will be able to:

1. Locate the right classes: `AuthenticationDetailsSource`, `WebAuthenticationDetailsSource`, `WebAuthenticationDetails`, and `Authentication.getDetails()`; distinguish them from the non-official API name `AuthenticationWebDetailsSource`.
2. Explain where and when Spring Security obtains `HttpServletRequest` to construct additional details for **an authentication attempt**.
3. Know which fields `WebAuthenticationDetails` captures by default: **remote address** and **session ID if a session already exists**—building details **does not create a new session**.
4. Create a custom `AuthenticationDetailsSource` with controlled extra data, such as a **client-claimed** channel; recognize that it is not verified data.
5. Configure the source via `formLogin(form -> form.authenticationDetailsSource(...))` or `AbstractAuthenticationProcessingFilter.setAuthenticationDetailsSource(...)` when genuinely using a custom filter.
6. Distinguish **metadata/details**, **principal**, **credentials**, **authorities**, **UserDetails**, and **SecurityContext**.
7. Understand why `UserDetailsService.loadUserByUsername(username)` does not receive `HttpServletRequest` automatically and why details must not be used to self-grant permissions.
8. Test successful login, request metadata, pre-existing vs. absent sessions, requests missing CSRF, and spoofed-header requests.
9. Identify what may be logged and what must be redacted; handle IPs behind reverse proxies, session fixation, and stale metadata.
10. Use additional metadata for monitoring or risk assessment **only across appropriate trust boundaries**, never treating a client-sent HTTP header as proof of identity.

## 2. Getting the Name Right: WebAuthenticationDetailsSource, Not AuthenticationWebDetailsSource

In Spring Security 6.5, the primary classes and interfaces are:

| Component | Exact API name | Function |
| --- | --- | --- |
| Details factory interface | `org.springframework.security.authentication.AuthenticationDetailsSource<C,T>` | Builds a details object `T` from a context `C` |
| Default source for web | `org.springframework.security.web.authentication.WebAuthenticationDetailsSource` | Creates `WebAuthenticationDetails` from `HttpServletRequest` |
| Default details payload | `org.springframework.security.web.authentication.WebAuthenticationDetails` | Holds remote address and session ID if one exists |
| Authentication | `org.springframework.security.core.Authentication` | `getDetails()` returns implementation-specific metadata; not always `WebAuthenticationDetails` |
| Standard login filter | `org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter` | Reads username/password, builds token, and calls details source |
| Base login filter class | `AbstractAuthenticationProcessingFilter` | Provides `setAuthenticationDetailsSource(...)` and success/failure flow |

**Naming note:** "`AuthenticationWebDetailsSource`" in the topic title should be understood as referring to web authentication metadata sources; searching for that literal name in Spring Security 6.5 Javadocs will not find a standard class. The class name to use in code is **`WebAuthenticationDetailsSource`**. Do not change imports to a nonexistent name and conclude Gradle/Spring Boot is missing a dependency.

The generic interface has the form:

```java
public interface AuthenticationDetailsSource<C, T> {
    T buildDetails(C context);
}
```

This is a **signature excerpt**, not a file to redeclare. For web authentication, `C` is `HttpServletRequest` and `T` is typically `WebAuthenticationDetails` or a compatible subclass.

Example using the standard source:

```java
AuthenticationDetailsSource<HttpServletRequest, WebAuthenticationDetails>
        source = new WebAuthenticationDetailsSource();

WebAuthenticationDetails details = source.buildDetails(request);
```

This is a snippet assuming `HttpServletRequest request` and proper imports exist. If you only need the default IP/session ID, **there is no need to write a custom details source**.

## 3. Where Are Details Created in the Authentication Flow?

For username/password form login:

```text
Browser
    |
    | POST /login: username, password, CSRF token
    v
Spring Security filter chain
    |
    v
UsernamePasswordAuthenticationFilter
    | 1. extract username and password
    | 2. construct unauthenticated UsernamePasswordAuthenticationToken
    | 3. call authenticationDetailsSource.buildDetails(request)
    | 4. authRequest.setDetails(details)
    v
AuthenticationManager / ProviderManager
    |
    v
AuthenticationProvider (usually DaoAuthenticationProvider)
    | - UserDetailsService loads user and password hash
    | - PasswordEncoder checks password
    | - account-state checks and other provider rules
    v
Successful Authentication (or AuthenticationException)
    |
    +--> Authentication.getDetails() can preserve source details
    |
    v
SecurityContext + success/failure handling per configured mechanism
```

Specifically, `UsernamePasswordAuthenticationFilter` has `setDetails(HttpServletRequest, UsernamePasswordAuthenticationToken)` and invokes `authenticationDetailsSource.buildDetails(request)`. With `DaoAuthenticationProvider`/`AbstractUserDetailsAuthenticationProvider`, a successful authentication under the standard flow typically **copies the authentication request's details** onto the resulting authentication.

**Do not confuse responsibilities:** a details source only *constructs data describing the request*. It does not verify passwords, decide whether an account is enabled/locked, write sessions itself, grant `GrantedAuthority`, or replace `AuthenticationProvider`. Other providers/filters may use different token/details types; never assert that `getDetails()` on every authentication is always the same class.

### Distinguishing Properties of Authentication

| Property / API | Contents | Caution |
| --- | --- | --- |
| `getPrincipal()` | Identity: `UserDetails`, username, `Jwt`, etc. | May contain internal fields; do not serialize indiscriminately |
| `getCredentials()` | Evidence: password/token or already erased | **Do not store in details** or log |
| `getAuthorities()` | Permissions granted by a trusted source | Used for authorization, never taken from arbitrary headers |
| **`getDetails()`** | Mechanism-specific metadata, e.g., remote address/session ID | Primarily for event context; values may be untrusted |
| `isAuthenticated()` | Token state per contract | Never set to true manually from client data |
| `SecurityContextHolder.getContext()` | Container for current authentication | Thread/request scoped, not a permanent login database |

A request containing `X-Role: ADMIN` does not mean code is allowed to do:

```java
// NEVER DO THIS: a client header is not proof for granting permissions.
requestAuthentication.setDetails("ROLE_ADMIN");
```

Even if you place that string in details, Spring Security **does not automatically** turn it into a `GrantedAuthority`. However, if custom application code reads details and grants permissions from it, it can introduce a privilege escalation vulnerability.

## 4. What Does WebAuthenticationDetails Capture by Default?

Spring Security 6.5 Javadocs state that `new WebAuthenticationDetails(request)` records:

1. `getRemoteAddress()`: the remote address of the HTTP request as seen by the Servlet container, typically corresponding to `request.getRemoteAddr()`.
2. `getSessionId()`: the session ID **if the request already has an `HttpSession`**; otherwise, the value can be `null`.

It **does not trigger creating a new session** just to obtain an ID. Both values are **request metadata**, not verified identity.

```java
WebAuthenticationDetailsSource source =
        new WebAuthenticationDetailsSource();

WebAuthenticationDetails d = source.buildDetails(request);

String address = d.getRemoteAddress();
String existingSessionId = d.getSessionId(); // may be null
```

This is a snippet inside a Servlet context; do not print `existingSessionId` to logs. A session ID can act as a **session bearer secret**, so avoid exposing it in responses, analytics, dashboards, or exception traces.

### 4.1. What Does "Does Not Create a Session" Specifically Mean?

Suppose a request has no session:

```text
Before buildDetails:
    request.getSession(false) -> null

new WebAuthenticationDetailsSource().buildDetails(request):
    remote address = request.getRemoteAddr()
    session ID     = null
    does not create HttpSession

After buildDetails:
    request.getSession(false) is still null
```

However, **other components** may still create a session during the same HTTP request: the CSRF token repository, request cache, login/session strategy, controllers, or Servlet infrastructure. Hence "WebAuthenticationDetails does not create a session" **does not mean** "POST /login never creates a session".

### 4.2. The Session ID in Details May Be the Pre-Login ID

**Session fixation** defenses may rotate/migrate the session ID after credentials are verified. `WebAuthenticationDetails` captures the ID when **the filter builds details**, before subsequent success/session processing steps.

Therefore:

- `details.getSessionId()` does not necessarily equal the browser's final session ID after login.
- Do not use `details.getSessionId()` as a long-lived key for authorization, session fixation defense, or auditing "active sessions".
- To inspect the current session, use session management APIs at the right lifecycle point, not an ID captured at the attempt step.
- Do not copy the session ID from details into URLs, JSON, or metric labels.

### 4.3. Remote Address Behind a Reverse Proxy

If the app runs behind a load balancer or reverse proxy, `request.getRemoteAddr()` may be **the proxy's IP**, not the end user's IP. Headers like `Forwarded`, `X-Forwarded-For`, or `X-Real-IP` are trustworthy **only if a trusted edge/proxy strips client-supplied values and inserts normalized ones**.

**Do not manually read `request.getHeader("X-Forwarded-For")` and take the first element as an identity or trusted IP** when clients can send that header directly. An attacker can claim `127.0.0.1` or an "allowlisted" IP.

If you need end-user IPs for fraud detection or rate limiting:

1. Define the trusted proxy/load balancer boundary.
2. Accept forwarded metadata only over authenticated/protected network paths.
3. Configure Forwarded header handling through the container/framework (such as `ForwardedHeaderFilter` or native support) **only when proxy trust is properly configured**.
4. Distinguish the TCP peer address from the post-proxy client address. Name them clearly in logs.
5. Never use IP alone as proof of identity: NAT, VPNs, mobile networks, and proxies cause IPs to change or be shared.

## 5. When Do You Actually Need a Custom AuthenticationDetailsSource?

Some business scenarios need extra metadata at login time:

- A **client-claimed** channel (web/mobile), strictly for UI analytics/observability.
- A request correlation ID **generated by a trusted server/gateway** to link audit logs.
- Preliminary risk signals from an authenticated edge system, such as a risk tier in a request attribute attached by a trusted filter.
- Narrowly scoped device characteristics, avoiding overly detailed fingerprints or unnecessary private data.
- A tenant hint/organization slug for routing login, **while** still verifying tenant membership and validity in the provider/authorization layer.
- WebAuthn/OIDC/challenge flows may need request data, though default details should not be used to store raw tokens/OTPs.

**Classify sources before using them:**

| Data | Who controls it? | What can it be used for? | What must it NOT be used for by default? |
| --- | --- | --- | --- |
| `X-Demo-Client: mobile` | HTTP client | Normalized demo UI label/analytics | Proving real mobile app usage, granting roles |
| Self-sent `X-Request-Id` | Possibly the client | Low-trust display correlation | Unique trusted audit ID |
| Gateway-issued internal trace ID | Trusted edge if boundary is protected | Audit/trace correlation | Proof of username/permissions |
| `getRemoteAddr()` | Servlet container/trust chain | Contextual network signal | User ID, role, MFA proof |
| Existing session ID | Servlet/session infrastructure | Short-lived request/session info | Public value or authorization key |
| OTP/password/token | User secret | Must pass into controlled verifier/challenge flow | Long-term storage in details or logs |
| `X-Role` / `X-Tenant-Admin` header | HTTP client | Ignore or log controlled warning | Creating `GrantedAuthority` |
| Request attribute set by a verified trusted filter | Server | Risk/policy input if backed by a clear contract | Blindly trusting any same-named attribute regardless of origin |

### Minimalism Principles

Custom details should be **immutable after creation**, small in size, clearly meaningful, and safe for session serialization. Never hold `HttpServletRequest`, `HttpServletResponse`, `HttpSession`, `InputStream`, passwords, or raw header maps inside details. Do not place unnecessary PII into the principal or session.

## 6. Three Ways to Write Custom Source/Details

### 6.1. Option 1: Extend WebAuthenticationDetails and Add Fields

```java
final class RequestMetadataDetails extends WebAuthenticationDetails {
    private static final long serialVersionUID = 1L;

    private final String clientHint;

    RequestMetadataDetails(HttpServletRequest request) {
        super(request);

        String value = request.getHeader("X-Demo-Client");
        this.clientHint = "mobile".equalsIgnoreCase(value)
                ? "mobile-claimed"
                : "not-declared";
    }

    String getClientHint() {
        return clientHint;
    }
}
```

This is a snippet from a Java file with imports/Servlet dependencies. Accept values only from an **allowlist** and bound the content when constructing details. `mobile-claimed` means **claimed by the client**, not verified as an authentic mobile device by the server.

Extending `WebAuthenticationDetails` preserves `getRemoteAddress()`, `getSessionId()`, and your extra metadata. Calling `super(request)` does not create a new session. In real code, avoid letting a custom `toString()` print additional sensitive details.

### 6.2. Option 2: Implement AuthenticationDetailsSource

```java
final class RequestMetadataDetailsSource
        implements AuthenticationDetailsSource<
                HttpServletRequest, RequestMetadataDetails> {

    @Override
    public RequestMetadataDetails buildDetails(
            HttpServletRequest request) {
        return new RequestMetadataDetails(request);
    }
}
```

This is a snippet used in the complete project in section 7. The default source is stateless, so it can be reused across requests as long as the class itself holds no mutable per-user state. **Never** store `currentUsername`, `lastIp`, or `lastSessionId` in fields of a singleton details source—concurrent requests will mix up data.

### 6.3. Option 3: Just Use the Standard Source

If you have no custom metadata needs:

```java
http.formLogin(form -> form
        .authenticationDetailsSource(new WebAuthenticationDetailsSource()));
```

This is a snippet inside a `SecurityFilterChain` configuration, and in many cases it **does not even need to be declared**, because Spring Security configures the standard source by default for form login flows.

**Do not write a custom class just to copy `getRemoteAddr`/`sessionId` verbatim** if there is no new behavior. The less logic touches untrusted request inputs, the easier it is to control risk.

## 7. Runnable Example: Spring Boot Form Login with Custom Details

This project exercises **the real filter path**:

1. Standard form login accepts `POST /login`.
2. `UsernamePasswordAuthenticationFilter` invokes the custom `RequestMetadataDetailsSource`.
3. The details subclass stores the remote address, existing session ID if present, and `clientHint` from the header.
4. `DaoAuthenticationProvider` verifies the password as usual.
5. `Authentication.getDetails()` in subsequent requests retains the details from the login session.
6. MockMvc tests verify login success, CSRF, custom details, and that the standard source does not create a session.

**Demo security limitations:** only has an in-memory account `mai / demo-pass-123` and an **untrusted** test channel; never use demo passwords in production. Custom data exposed on `/whoami` is strictly for learner visibility; real apps should minimize returned metadata and avoid exposing session IDs or unnecessary network info.

### 7.1. Structure

```text
web-auth-details-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/dev/demo/details/WebAuthDetailsDemoApplication.java
    └── test/java/dev/demo/details/WebAuthDetailsDemoApplicationTests.java
```

`settings.gradle`:

```groovy
rootProject.name = 'web-auth-details-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.7'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'dev.demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot manages compatible Spring Security versions via its BOM; do not arbitrarily override another version. The project uses Java 17+, and the Servlet namespace is `jakarta.servlet.*`, not legacy `javax.servlet.*`.

### 7.2. Complete Java Application

Create `src/main/java/dev/demo/details/WebAuthDetailsDemoApplication.java`:

```java
package dev.demo.details;

import java.util.LinkedHashMap;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationDetailsSource;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.WebAuthenticationDetails;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class WebAuthDetailsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebAuthDetailsDemoApplication.class, args);
    }
}

@Configuration
class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder passwordEncoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("mai")
                        .password(passwordEncoder.encode("demo-pass-123"))
                        .roles("READER")
                        .build());
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/login").permitAll()
                .requestMatchers("/whoami").authenticated()
                .anyRequest().denyAll());

        http.formLogin(form -> form
                .authenticationDetailsSource(
                        new RequestMetadataDetailsSource())
                .permitAll());

        // Do not disable CSRF, do not build Authentication manually.
        // Form login and session management use standard mechanisms.
        return http.build();
    }
}

// Metadata source invoked when the form-login filter builds the request token.
final class RequestMetadataDetailsSource
        implements AuthenticationDetailsSource<
                HttpServletRequest, RequestMetadataDetails> {

    @Override
    public RequestMetadataDetails buildDetails(HttpServletRequest request) {
        return new RequestMetadataDetails(request);
    }
}

// Serializable because WebAuthenticationDetails supports session storage.
final class RequestMetadataDetails extends WebAuthenticationDetails {
    private static final long serialVersionUID = 1L;
    private final String clientHint;

    RequestMetadataDetails(HttpServletRequest request) {
        super(request);

        // Client-declared header; only used for display in the DEMO.
        String raw = request.getHeader("X-Demo-Client");
        this.clientHint = "mobile".equalsIgnoreCase(raw)
                ? "mobile-claimed"
                : "not-declared";
    }

    String clientHint() {
        return clientHint;
    }
}

@RestController
class CurrentAuthenticationController {

    @GetMapping("/whoami")
    Map<String, Object> whoami(Authentication authentication) {
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("username", authentication.getName());

        Object details = authentication.getDetails();
        response.put("detailsType", details == null
                ? "none"
                : details.getClass().getSimpleName());

        if (details instanceof RequestMetadataDetails metadata) {
            response.put("clientHint", metadata.clientHint());

            // Illustrative only; production should not return remote address.
            response.put("remoteAddress", metadata.getRemoteAddress());

            // DO NOT expose the actual session ID in JSON.
            response.put("hadSessionAtLogin",
                    metadata.getSessionId() != null);
        }

        return response;
    }
}
```

**Exact walkthrough of the processing path:**

- `SecurityFilterChain` permits `/login`, requires authentication for `/whoami`, and denies other endpoints. `formLogin(...)` registers the filter handling `POST /login` along with the default login page.
- `.authenticationDetailsSource(new RequestMetadataDetailsSource())` is configured on the **authentication filter**, not inside `UserDetailsService`.
- `RequestMetadataDetailsSource.buildDetails(request)` is invoked on the login request and returns a **fresh** object for that request.
- `RequestMetadataDetails` extends `WebAuthenticationDetails`: IP and session ID come from the Servlet request. `clientHint` is a **client-supplied claim**, normalized into two fixed values and never used to grant privileges.
- `InMemoryUserDetailsManager` provides the user/BCrypt hash; password verification belongs to Spring Security's provider, not the details source.
- On login success, details are typically retained on the authentication result and can appear at `/whoami` via the session.
- The controller only returns a **boolean** indicating whether a session existed at the attempt time, without exposing the actual session ID.
- Default CSRF remains enabled: browser POST form logins must supply a valid CSRF token. MockMvc uses `.with(csrf())` to supply the test proof.
- The standard login filter also handles success/failure, session strategy, and saving `SecurityContext` per config; if you write a custom filter/controller, session responsibilities may differ.

### 7.3. Testing Real Execution Through the Filter Chain with MockMvc

Create `src/test/java/dev/demo/details/WebAuthDetailsDemoApplicationTests.java`:

```java
package dev.demo.details;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.security.web.authentication.WebAuthenticationDetails;
import org.springframework.security.web.authentication.WebAuthenticationDetailsSource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class WebAuthDetailsDemoApplicationTests {

    @Autowired
    private MockMvc mvc;

    @Test
    void defaultSourceDoesNotCreateSession() {
        MockHttpServletRequest request =
                new MockHttpServletRequest("POST", "/login");
        request.setRemoteAddr("203.0.113.8");

        assertNull(request.getSession(false));

        WebAuthenticationDetails details =
                new WebAuthenticationDetailsSource()
                        .buildDetails(request);

        assertEquals("203.0.113.8", details.getRemoteAddress());
        assertNull(details.getSessionId());
        assertNull(request.getSession(false));
    }

    @Test
    void formLoginAttachesDetailsAndKeepsAuthentication() throws Exception {
        MockHttpSession session = new MockHttpSession();

        mvc.perform(post("/login")
                        .session(session)
                        .with(csrf())
                        .with(request -> {
                            request.setRemoteAddr("198.51.100.23");
                            return request;
                        })
                        .header("X-Demo-Client", "mobile")
                        .param("username", "mai")
                        .param("password", "demo-pass-123"))
                .andExpect(status().is3xxRedirection());

        // Different request using the same authenticated session.
        mvc.perform(get("/whoami").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("mai"))
                .andExpect(jsonPath("$.detailsType")
                        .value("RequestMetadataDetails"))
                .andExpect(jsonPath("$.clientHint")
                        .value("mobile-claimed"))
                .andExpect(jsonPath("$.remoteAddress")
                        .value("198.51.100.23"))
                .andExpect(jsonPath("$.hadSessionAtLogin")
                        .value(true));
    }

    @Test
    void clientHeaderDoesNotGrantAnyAdditionalRole() throws Exception {
        MockHttpSession session = new MockHttpSession();

        mvc.perform(post("/login")
                        .session(session)
                        .with(csrf())
                        .header("X-Demo-Client", "admin")
                        .param("username", "mai")
                        .param("password", "demo-pass-123"))
                .andExpect(status().is3xxRedirection());

        mvc.perform(get("/whoami").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.clientHint")
                        .value("not-declared"))
                .andExpect(jsonPath("$.username")
                        .value("mai"));
    }

    @Test
    void csrfIsStillRequiredForFormLogin() throws Exception {
        mvc.perform(post("/login")
                        .param("username", "mai")
                        .param("password", "demo-pass-123"))
                .andExpect(status().isForbidden());
    }
}
```

Run tests from the `web-auth-details-demo` directory:

```bash
gradle test
```

If using a Gradle Wrapper, run `./gradlew test` on macOS/Linux or `gradlew.bat test` on Windows.

Start the application to open the default login page:

```bash
gradle bootRun
```

Visit `http://localhost:8080/login`, sign in with the demo account, then open `http://localhost:8080/whoami` to inspect the JSON. Browser navigation **does not automatically send `X-Demo-Client`**, so `clientHint` defaults to `not-declared` unless a client/test sends the header. Do not manually issue a POST `/login` without a CSRF token and think the framework is broken—the standard browser login form embeds the token.

### 7.4. Expected Results

| Test | Condition | Result |
| --- | --- | --- |
| `defaultSourceDoesNotCreateSession` | Mock request with no session | `getSessionId() == null`; still no session after build |
| `formLoginAttachesDetailsAndKeepsAuthentication` | Valid login + existing session + mobile header | Login redirects; `/whoami` 200, user `mai`, custom `detailsType` |
| `clientHeaderDoesNotGrantAnyAdditionalRole` | Self-claimed `admin` header | No ADMIN role created; only `not-declared` |
| `csrfIsStillRequiredForFormLogin` | POST login without CSRF token | **403** |

Example JSON from `/whoami` on a valid login test:

```json
{
  "username": "mai",
  "detailsType": "RequestMetadataDetails",
  "clientHint": "mobile-claimed",
  "remoteAddress": "198.51.100.23",
  "hadSessionAtLogin": true
}
```

This JSON describes **a test request whose session was created prior to login** and whose remote address was set by MockMvc on the HTTP request; do not assume real IPs always take that value. Results are deduced from the code, **not output captured from running tests inside this document**.

**Distinguish two trusted facts:** the test proves the source is called and details appear after login; it **does not prove** that the mobile header came from a signed mobile app or that the IP is trustworthy for an allowlist.

## 8. Integrating with formLogin and Custom Filters: Pick the Right Extension Point

### 8.1. Best Way for Form Login: Use the DSL Directly

When the application uses `formLogin`:

```java
http.formLogin(form -> form
        .authenticationDetailsSource(
                new RequestMetadataDetailsSource()));
```

This is a snippet inside `SecurityFilterChain`. Spring Security creates and configures the login filter; you do not have to build `UsernamePasswordAuthenticationFilter` manually just to swap the details source.

`FormLoginConfigurer` extends a configurer providing `authenticationDetailsSource(AuthenticationDetailsSource<HttpServletRequest, ?>)`. This API is present in Spring Security 6.5.

### 8.2. When Using a Custom UsernamePasswordAuthenticationFilter

A custom filter can be configured:

```java
UsernamePasswordAuthenticationFilter filter =
        new UsernamePasswordAuthenticationFilter();

filter.setAuthenticationManager(authenticationManager);
filter.setAuthenticationDetailsSource(
        new RequestMetadataDetailsSource());

// Still must configure matching, success/failure handlers,
// SecurityContextRepository, session strategy, and filter order.
```

This is an **incomplete configuration snippet**; do not copy and add this filter to a chain that already has standard `formLogin`. Accidentally leaving **two filters** both handling `POST /login` can cause duplicate authentication attempts, conflicting handlers, and hard-to-debug session/CSRF saving.

`AbstractAuthenticationProcessingFilter` exposes an equivalent `setAuthenticationDetailsSource(...)` setter, which matching subclasses inherit. Always verify the flow of the exact filter handling the request.

If an application writes a custom `OncePerRequestFilter` instead of subclassing `AbstractAuthenticationProcessingFilter`, the source **is not called automatically**. You must build `Authentication` and set `details` yourself:

```java
UsernamePasswordAuthenticationToken token =
        UsernamePasswordAuthenticationToken.unauthenticated(
                username, password);

token.setDetails(detailsSource.buildDetails(request));

Authentication result = authenticationManager.authenticate(token);
```

This is only a **snippet creating the authentication attempt**. You still need real credential verification, error handling, security context setup, session fixation/CSRF, context persistence (Spring Security 6 explicit save for manual authentication), and proper filter placement. Merely attaching details does not make a token authenticated.

### 8.3. Differences in API/Token Filters

HTTP Basic, bearer JWT, API key, OAuth2 login, SAML, pre-auth, and custom credential converters construct `Authentication` in different places:

- Some filters use the default details source, some construct details themselves, and some attach no `WebAuthenticationDetails`.
- `Authentication.getDetails()` has no fixed return type beyond `Object`.
- `formLogin.authenticationDetailsSource(...)` **only configures the form-login filter**, and does not affect `BearerTokenAuthenticationFilter` or filters in other chains.
- If the app has multiple `SecurityFilterChain` beans, determine **which chain is selected** and which filter processes the path.
- In WebFlux, context normally lives in Reactor Context; you cannot copy `jakarta.servlet.http.HttpServletRequest` and servlet form-login sources verbatim into reactive authentication.

Do not write blind casts:

```java
// FRAGILE when Authentication comes from another token/flow.
WebAuthenticationDetails details =
        (WebAuthenticationDetails) authentication.getDetails();
```

Use `instanceof` or a specific contract if the application truly accepts only one token type.

## 9. Where Can Details Data Travel After Login?

In a session-based flow, `SecurityContext` holds `Authentication`, and `Authentication` may hold `details`. Consequently, details **can persist across multiple requests in the session**.

Consequences:

1. The IP in details may be **the login-time IP**, not the current request's IP.
2. `getSessionId()` may be the ID **before session rotation**; never treat it as the current session ID.
3. If custom details contain non-serializable objects, **Spring Session/distributed session storage** can fail to serialize/replicate.
4. If details hold raw tokens/passwords, secrets can linger in sessions, heap dumps, or logs longer than necessary.
5. When a user logs out, resets their password, or policy changes, the details snapshot does not automatically refresh per request.
6. With stateless JWT resource servers, `Authentication` is typically rebuilt from the token; there is no guarantee custom form-login details are present.

**Design lesson:** store only a few values needed for legitimate purposes, limit retention, and ensure serializability. For large, continuously changing risk data, store only a safe opaque reference ID rather than an object graph.

### Avoid Mixing Two Types of Request Metadata

- **Login-time metadata:** information at the moment of the authentication attempt.
- **Current-request metadata:** information from the HTTP request currently being processed after login.

If you want to rate-limit the current request or enforce network policy on each API call, read inputs from **the current request and trusted edge**, not from `Authentication.getDetails().getRemoteAddress()` captured hours earlier at login.

## 10. Is AuthenticationDetailsSource the Right Place to Decide MFA, Risk, and Tenant?

**Not by itself.** A details source can produce **input signals** for a risk-decision system. However, decisions to challenge, allow, or deny must belong to a layer with a trust contract, input validation, credential verification, and state management.

### 10.1. Example of a Trusted Risk Signal

Suppose a filter or trusted gateway verifies device attestation or computes a risk score. Instead of letting the client send arbitrary headers and treating them as verified, the architecture can do:

```text
Client HTTP request
      ↓
Trusted edge / attestation verification
      ↓
Edge strips spoofed headers, attaches trusted metadata
      ↓
Application filter verifies source
      ↓ request attribute: verifiedRiskTier = LOW / HIGH
AuthenticationDetailsSource.buildDetails(request)
      ↓
Custom auth/risk policy consumes typed risk signal
      ↓
AuthenticationProvider / MFA challenge / deny per policy
```

At the application layer, verify that `verifiedRiskTier` **was genuinely set by a trusted filter**, rather than a parameter filled in by the client. Do not expose a generic `request.getAttribute("verifiedRiskTier")` lookup assuming any filter or controller is allowed to set or overwrite it.

### 10.2. What If You Need to Add OTP?

An OTP is a **credential/challenge proof**, not metadata to store long-term inside `WebAuthenticationDetails` and expose in `SecurityContext` after login. Better approaches:

- An `AuthenticationConverter` or custom filter building a token with credential fields for the provider and ensuring cleanup.
- An `AuthenticationProvider` or multi-step authentication flow verifying the OTP/WebAuthn challenge at the proper boundary.
- Short-lived challenge state with TTL, CSRF/replay protection, failure/rate-limit handling, without granting full authentication prior to MFA completion.
- Erasing temporary evidence once verified; never serialize raw OTPs into session details objects.

**Never take an `mfaPassed=true` flag from a header, stick it in details, and consider MFA completed.**

### 10.3. What If You Need a Tenant ID?

A tenant slug may come from a path, subdomain, or login form; it is a **routing hint**, not proof that the user belongs to that tenant. You must bind the tenant ID to account lookup, credential validation, and authorization policies. After login, never allow clients to switch tenants via a header without a valid transition and authorization check.

When multi-tenant, clearly design cache keys, session isolation, audit namespaces, and every tenant-scoped query. Do not attach `tenantId` to details and then forget to enforce it inside the provider or service when checking data access.

## 11. Can UserDetailsService Access HttpServletRequest?

The `UserDetailsService.loadUserByUsername(String username)` contract takes **a single `username` parameter**—not `HttpServletRequest`, `WebAuthenticationDetails`, or `Authentication`. Therefore, implementations cannot assume request details are available to read.

Workarounds relying on `RequestContextHolder`/thread-locals or request-scoped beans can access the request on a web thread, but they tightly couple to Servlet APIs, complicate testing, fail in background tasks, and are **not the standard way to pass request data to a provider**.

If authentication policy **genuinely needs request metadata** (trusted IP, device proof, tenant, risk), clearer options are:

1. A custom `AuthenticationProvider` accepting an `Authentication` with details and enforcing extra policy checks.
2. A custom `AuthenticationConverter`/filter constructing a well-defined token that handles credentials/challenges from the proper source.
3. A risk service invoked at the right point in the authentication pipeline with typed context and a trust contract.
4. Standard authentication mechanisms (MFA/OIDC/WebAuthn) when appropriate, avoiding weak custom providers.

**Do not let `UserDetailsService` grant roles from request headers.** Its job is loading users from a trusted identity store, not evaluating client-asserted permissions.

## 12. Security, Privacy, and Auditing of WebAuthenticationDetails

### 12.1. Never Log Secrets or the Full Authentication

Default `WebAuthenticationDetails` contains the session ID and remote address. Calling `toString()` may output sensitive details depending on the implementation; never log raw `Authentication`/`details` objects unconditionally.

Avoid logging:

- Raw passwords, OTPs, recovery tokens, API keys, OAuth2 bearer tokens.
- Cookies, session IDs, `Authorization` headers, and CSRF tokens.
- Unnecessary fine-grained device identifiers/fingerprints.
- Unbounded or unsanitized client header strings (risk of log injection).
- High-cardinality IPs/client hints as metric labels.

If auditing is needed, prefer **internal account ID, event type, timestamp, a trusted issued correlation ID, result class**, and a policy-normalized network indicator. Enforce access controls, retention, and privacy policies.

### 12.2. There Is No Exact Authentication from IP Alone

`getRemoteAddress()` is a network attribute in the runtime environment. It does not prove:

- Which person is sitting at the device.
- That the session belongs to the same actor as the current IP.
- That the request came from the genuine mobile app.
- That the device passed MFA.
- That the user holds `ROLE_ADMIN` or belongs to a specific tenant.

Relying on IP to "skip passwords" or grant roles is fragile, especially with shared NAT, reverse proxies, VPNs, or attacker-controlled headers.

### 12.3. Never Create a Session Just to Put an ID in Details

Session ID can be null, and that is **valid**. Do not write:

```java
// Do not create a session unconditionally just to populate sessionId in details.
String id = request.getSession(true).getId();
```

This is an anti-pattern. Creating sessions increases memory/session-store pressure and emits unnecessary cookies for stateless requests. If the application requires session-based login, let Spring Security's session strategy/repository manage it when needed.

### 12.4. Header Data Must Have Length Limits and Trust Sources

The demo only allowlists `mobile`; all other values fall back to `not-declared`. Real applications should:

- Reject oversized requests/headers at the gateway and server.
- Normalize and validate against a schema, rejecting or ignoring invalid input.
- Never pass arbitrary headers into SQL, file paths, log formats, or unsanitized serialization.
- Explicitly distinguish whether metadata is `claimed`, `verified`, or `derived`.
- For forwarded headers, define the proxy trust chain and block clients from injecting values treated as "verified".

## 13. Common Mistakes

1. **Importing `AuthenticationWebDetailsSource` in code** and hunting for a nonexistent dependency. The API name is `WebAuthenticationDetailsSource`.
2. **Confusing `WebAuthenticationDetailsSource` with `WebAuthenticationDetails`:** one is a factory, the other is a value object.
3. **Thinking the details source verifies credentials:** authentication providers/managers verify passwords/credentials per contract.
4. **Assuming remote address is always the client's origin IP:** it may just be the reverse proxy's IP.
5. **Blindly trusting client-sent `X-Forwarded-For`:** enables IP spoofing without proxy trust enforcement.
6. **Assuming `buildDetails` creates an `HttpSession`:** the standard source does not create a session just to get an ID.
7. **Assuming the session ID in details is always the post-login session ID:** session fixation protection may rotate the ID.
8. **Logging `WebAuthenticationDetails.toString()` or actual session IDs:** can leak bearer secrets.
9. **Assuming details contain email, roles, or device ID by default:** by default it only contains remote address and an existing session's ID.
10. **Turning `X-Role: ADMIN` or `X-MFA: passed` into `GrantedAuthority`:** clients must never decide permissions.
11. **Putting raw passwords/OTPs into details:** secrets can persist in the authenticated session.
12. **Storing `HttpServletRequest` inside details:** request objects are unsafe to retain long-term or serialize.
13. **Keeping mutable `lastClientIp` fields on a singleton source:** mixes data across concurrent requests.
14. **Blindly casting `authentication.getDetails()` to a single subtype:** fails with Basic/JWT/custom providers.
15. **Configuring `formLogin`'s details source and expecting it to apply to JWT filters:** each authentication mechanism has its own pipeline.
16. **Manually adding `UsernamePasswordAuthenticationFilter` to a chain already using `formLogin`:** risks double authentication.
17. **Setting details only in the success handler after login:** too late if providers/risk checks need the data during the authentication attempt.
18. **Writing a custom filter without `setDetails`:** providers do not receive the expected request metadata.
19. **Manual authentication calling only `SecurityContextHolder.setContext` in Spring Security 6:** context may not persist without explicitly saving to the right repository.
20. **Using `UserDetailsService` to reach the Servlet request via ThreadLocal without good reason:** creates tight coupling and hard-to-test code.
21. **Testing details presence only within the same request:** does not prove session storage or availability in subsequent requests.
22. **Using login-time details for IP/rate-limiting on requests hours later:** the data is stale.
23. **Neglecting CSRF in cookie-based form login:** creates login CSRF risks and related vulnerabilities.
24. **Not protecting identity when a tenant hint changes:** headers do not verify membership or tenant isolation.
25. **Emitting metrics with username/IP/sessionId as labels:** causes leaks and high cardinality.
26. **Not checking `jakarta`/`javax` namespace versions:** Spring Security 6/Spring Boot 3 uses `jakarta.servlet`.
27. **Not testing reverse proxies/header spoofing:** leads to broken trusted-IP boundaries.
28. **Not defining what data belongs in the session:** can accidentally store PII or unnecessary secrets.

## 14. Practice Exercises

**Exercise A — Right API names.** Explain `AuthenticationDetailsSource<C,T>`, `WebAuthenticationDetailsSource`, `WebAuthenticationDetails`, and `Authentication.getDetails()`. State why `AuthenticationWebDetailsSource` is not a standard import in Spring Security 6.5.

**Exercise B — Default source.** Create a `MockHttpServletRequest` with no session, call `new WebAuthenticationDetailsSource().buildDetails(request)`, assert the IP and `sessionId == null`, and confirm `getSession(false)` remains null.

**Exercise C — Custom source.** Add an allowlist-normalized `clientHint` field, run tests with `X-Demo-Client=mobile` and an arbitrary value. Explain the difference between `mobile-claimed` and verified mobile.

**Exercise D — Filter pipeline.** Run `gradle test` from section 7, place breakpoints in `buildDetails`, `UsernamePasswordAuthenticationFilter.setDetails`, `DaoAuthenticationProvider`, and the controller. Record call order, `Authentication.getDetails()`, and behavior on a wrong password.

**Exercise E — Authentication failure.** Log in with a wrong password, verify no authenticated session exists, and ensure neither session ID nor password appears in responses/logs. Prove that creating details **does not mean credentials were accepted**.

**Exercise F — CSRF.** Verify POST `/login` without a CSRF token is rejected in the demo while form login with a valid token succeeds. Never disable CSRF just to simplify tests.

**Exercise G — Proxy.** Diagram the trust chain client → LB → gateway → app, test a client spoofing `X-Forwarded-For`, and specify the policy for stripping/normalizing headers at the trusted edge. Never treat a self-declared header IP as proof.

**Exercise H — Session fixation.** Observe `details.getSessionId()` before a successful login and the session ID after the strategy runs. Explain why that field must not be used as the active key; **never log actual IDs in shared environments**.

**Exercise I — Tenant/role spoofing.** Add `X-Role=ADMIN` or `X-Tenant=other` headers and prove user `mai` only has `ROLE_READER`. If real tenants exist, verify membership and object permissions in the trusted provider/service layer.

**Exercise J — Multi-chain.** Define a form-login chain and a JWT API chain, and trace which chain is selected for each path. Confirm `formLogin.authenticationDetailsSource` does not affect the JWT principal.

**Exercise K — Audit.** Design a `LoginAttempt` event with internal account ID (if known), outcome, timestamp, and trusted correlation ID; decide IP granularity and retention policy. Exclude passwords, session IDs, OTPs, and tokens from the event.

### Completion Criteria

You should be able to explain in your own words:

- Which class is actually named `WebAuthenticationDetailsSource`, and what to watch out for in the topic's naming?
- Which fields does the default source create, and is a session created just to fetch an ID?
- Does the filter build details before or after `AuthenticationManager.authenticate(...)`?
- How to configure a custom source in `formLogin` or a custom filter?
- Why doesn't `UserDetailsService` receive `HttpServletRequest` automatically?
- When is metadata trustworthy enough to serve as a risk signal, and when is it merely a client claim?
- Why must self-declared headers never be used to grant authorities, MFA, or tenant permissions?
- How to test real login paths, CSRF, sessions, privacy, and stale-metadata prevention?

## 15. Official References

- [Spring Security 6.5.11 — WebAuthenticationDetailsSource](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/WebAuthenticationDetailsSource.html): standard class, `buildDetails(HttpServletRequest)`.
- [Spring Security 6.5.11 — WebAuthenticationDetails](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/WebAuthenticationDetails.html): remote address, session ID, and no-session-creation rule.
- [Spring Security 6.5.11 — AuthenticationDetailsSource](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationDetailsSource.html): generic `buildDetails` contract.
- [Spring Security 6.5.11 — AbstractAuthenticationProcessingFilter](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/AbstractAuthenticationProcessingFilter.html): `setAuthenticationDetailsSource` and authentication lifecycle.
- [Spring Security 6.5.11 — AbstractAuthenticationFilterConfigurer](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/AbstractAuthenticationFilterConfigurer.html): `authenticationDetailsSource` DSL and default source.
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html): `UsernamePasswordAuthenticationFilter` and login flow.
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `Authentication`, providers, context, and authorities.
- [Spring Security 6.5 — Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): session fixation, context persistence, and login.
- [Spring Security 6.5 — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html): CSRF with browser sessions/form login.
- [Spring Framework — ForwardedHeaderFilter](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/filter/ForwardedHeaderFilter.html): handling forwarded headers and trusted proxy boundaries.

**Version note:** content follows Spring Security Servlet 6.5 / Spring Boot 3.5.7 and Java 17+. When using Spring Security 7, WebFlux, custom OAuth2/JWT providers, or different containers/proxies, verify the exact current classes and APIs. Above all, `Authentication.getDetails()` is not a new security principal and does not magically make HTTP request data trustworthy.