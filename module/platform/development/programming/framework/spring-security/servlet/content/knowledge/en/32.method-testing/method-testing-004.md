# @WithAnonymousUser and Unauthenticated Scenarios: Testing Method Security in Spring Security Servlet

## 1. Why Must You Test an Unauthenticated User?

In a Spring Security Servlet application, security testing cannot cover only logged-in users. An API typically must handle both public visitors and callers who have not provided credentials:

- News pages or status pages may be open to guests.
- Profile pages, transaction history, and account update operations must reject unauthenticated visitors.
- Endpoints requiring a specific role or permission may also reject **logged-in users who lack that permission**.
- Some logic tailored to anonymous users, such as showing a sign-in prompt, may use the `isAnonymous()` expression.
- Login, logout, session expiry, remember-me, CSRF, and invalid Bearer tokens all behave differently and need independent testing.

Spring Security Test provides the **`@WithAnonymousUser`** annotation to simulate **anonymous authentication** in a test running with Spring TestContext. This annotation is especially helpful for **method security**: calling a Spring bean protected by `@PreAuthorize` or `@PostAuthorize` and confirming permissions are enforced against an anonymous principal.

**Key takeaway:** "anonymous" in Spring Security is usually **an `AnonymousAuthenticationToken` created by the framework**, not necessarily `SecurityContextHolder.getContext().getAuthentication() == null`. Those two states must be distinguished when writing assertions.

Goals of this article:

1. Understand precisely what test condition `@WithAnonymousUser` sets up.
2. Test `isAnonymous()`, `isAuthenticated()`, `isFullyAuthenticated()`, and permission expressions in method security.
3. Compare testing a service bean directly against HTTP testing with `MockMvc`.
4. Distinguish HTTP `401`/`403`, expired sessions, remember-me, and failed authentication.
5. Avoid tests that "pass" without actually activating Spring Security.

## 2. What Is Anonymous Authentication?

A request carrying no login credentials can still be represented by Spring Security as an `AnonymousAuthenticationToken` inside the filter chain. This mechanism is typically configured by **`AnonymousAuthenticationFilter`** when no suitable `Authentication` is present in `SecurityContextHolder`.

With the default configuration, the anonymous token has a guest principal and typically authority `ROLE_ANONYMOUS`. Principal or authority details can change under custom configuration; policies should not treat the guest principal name string as a real identity.

| Scenario | `Authentication` in Context | Security Meaning |
| --- | --- | --- |
| No authentication context | May be `null` | No authentication object exists; do not access properties without a null check |
| Anonymous authentication | `AnonymousAuthenticationToken` | Framework represents an unauthenticated visitor with a dedicated token |
| Logged in with username/password | e.g., authenticated `UsernamePasswordAuthenticationToken` | Identity authenticated through the configured mechanism |
| Remember-me authentication | e.g., `RememberMeAuthenticationToken` | Identity restored from a remember-me cookie; not necessarily equivalent to a fresh login |
| JWT Bearer authentication | e.g., `JwtAuthenticationToken` | Identity or client authenticated via token and resource server validation |

### 2.1. Common Confusion: isAuthenticated() on the Token Differs from the isAuthenticated() Expression

A typical `AnonymousAuthenticationToken` **can return `true` when calling `Authentication.isAuthenticated()` directly**. However, Spring security expressions like method security's `isAuthenticated()` or `AuthenticatedAuthorizationManager` use logic that distinguishes anonymous via **`AuthenticationTrustResolver`**.

Therefore, in authorization policies:

| Expression | Anonymous | Normal Logged-In User | Remember-Me |
| --- | --- | --- | --- |
| `permitAll()` | Allowed | Allowed | Allowed |
| `denyAll()` | Denied | Denied | Denied |
| `isAnonymous()` | Allowed | Denied | Denied |
| `isAuthenticated()` | Denied | Allowed | Usually allowed |
| `isFullyAuthenticated()` | Denied | Allowed | Denied |
| `hasAuthority('REPORT_READ')` | Usually denied | Depends on authority | Depends on authority |

"Allowed" in the table means **that expression alone** is satisfied; other security gates such as CSRF, URL rules, tenant authorization, and business validation can still deny the request.

**Do not write** `if (auth != null && auth.isAuthenticated())` and treat it as checking whether a user is truly logged in across every Servlet context. When an anonymous token is present, that raw check is easily misinterpreted. Prefer explicit Spring Security policies: `.authenticated()`, `.fullyAuthenticated()`, `@PreAuthorize("isAuthenticated()")`, or checking the trust resolver when genuinely needed.

### 2.2. Anonymous Is Not a Shared User Account

An anonymous visitor does not have a verified user ID. Never use an anonymous `auth.getName()` as a key for sensitive data access or resource ownership. If a public endpoint needs temporary cart state, use an appropriate session/token and protect it separately; never turn an anonymous principal into a verified user.

Passing through the filter chain as anonymous also does not mean the framework proves the request is harmless. A `permitAll()` endpoint can still receive malicious input; apply validation, rate limiting, abuse prevention, and appropriate controls.

## 3. How Does @WithAnonymousUser Work in Spring Security Test?

`@WithAnonymousUser` resides in package:

~~~java
import org.springframework.security.test.context.support.WithAnonymousUser;
~~~

The annotation is used by Spring Security Test via **Spring TestContext** and the corresponding test execution listener. Before running the test, it sets up a `SecurityContext` simulating anonymous authentication so security-protected calls in the test observe an unauthenticated user state.

Example usage:

~~~java
@Test
@WithAnonymousUser
void anonymousCannotReadPrivateData() {
    // Call a service with method security enabled and assert denial.
}
~~~

This is only a **method inside a test class**, not a standalone Java program.

**What this annotation does NOT do:**

- Does not send a real HTTP request to the server.
- Does not execute a browser login flow or username/password authentication.
- Does not directly check expired cookies/sessions or invalid Bearer tokens.
- Does not guarantee `AnonymousAuthenticationFilter` ran during a real network request.
- Does not automatically enable `@PreAuthorize`; the application/test context still needs **`@EnableMethodSecurity`**.
- Does not automatically turn an object created with `new MyService()` or a Mockito mock into a secured Spring AOP proxy.

In a properly configured integration test, the context is set up per the test lifecycle. Spring Security Test also cleans up the context between tests; avoid switching `SecurityContextHolder`'s strategy to global, or holding the previous test's user in a static field.

### 3.1. Comparing Identity Testing Annotations

| Usage | Context Created | Suitable For Testing |
| --- | --- | --- |
| `@WithAnonymousUser` | Anonymous authentication | Methods denied to guests, guest-only methods, public methods |
| `@WithMockUser` | Mock authenticated user with configurable username/roles/authorities | Method authorization for logged-in users |
| `@WithUserDetails` | Loads user from `UserDetailsService` in the test configuration | Interaction with test user data |
| Custom `@WithSecurityContext` | Custom factory builds `SecurityContext` from test attributes | Specialized principals/tokens/claims/providers |
| `SecurityMockMvcRequestPostProcessors.anonymous()` | Anonymous for **one specific MockMvc request** | Guest state at Servlet filter/URL layer |
| `SecurityMockMvcRequestPostProcessors.user(...)` | Mock user for a MockMvc request | HTTP authorization for an authenticated user |

**Distinguishing annotations and request post-processors:** `@WithAnonymousUser` sets the context for the test method; `.with(anonymous())` explicitly attaches anonymous to a `MockMvc` request. For HTTP tests, specifying via a request post-processor directly often makes test cases clearer and less coupled to test-class state.

### 3.2. Placing the Annotation at Class or Method Level?

With multiple anonymous tests:

~~~java
@WithAnonymousUser
class AnonymousTests {
    @Test
    void firstCase() { /* ... */ }

    @Test
    void secondCase() { /* ... */ }
}
~~~

When using a class-level annotation, verify the test framework integrates the right listener. Methods can carry a different identity annotation to intentionally test exceptions.

Example with class-level `@WithMockUser` where one method requires a guest:

~~~java
@WithMockUser(username = "alice")
class ServiceSecurityTests {

    @Test
    @WithAnonymousUser
    void guestIsDenied() { /* ... */ }
}
~~~

The method-level annotation sets up the anonymous scenario for that test. Keep test names and assertions clear so nobody mistakenly thinks class-level `"alice"` is still active in that method.

## 4. Preparing a Method-Security Testing Project

Examples use **Java 17+, Spring Boot 3.x, Spring Security 6.x, and JUnit Jupiter**. Java snippets in sections 4–7 are parts of a **Spring Boot project** and will not compile standalone with `javac` without the dependencies and Spring container.

Gradle dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Note that `spring-security-test` must be on the **test classpath**. With Maven, declare `org.springframework.security:spring-security-test` in `test` scope matching the Spring Boot BOM. Without this dependency, `@WithAnonymousUser` and the `anonymous()` post-processor will not be recognized.

A sample project layout:

~~~text
src/main/java/com/example/demo/
  DemoApplication.java
  MethodSecurityConfig.java
  GreetingService.java
  WebSecurityConfig.java
  DemoController.java
src/test/java/com/example/demo/
  GreetingServiceSecurityTest.java
  AnonymousHttpSecurityTest.java
~~~

### 4.1. Application Entry Point

File `DemoApplication.java`:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 4.2. Enabling Method Security

File `MethodSecurityConfig.java`:

~~~java
package com.example.demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

In Spring Security 6, `@EnableMethodSecurity` is the standard way to turn on method-level authorization. Without it, `@PreAuthorize` can remain merely a passive annotation in source without being enforced on service calls.

Tests must obtain the **Spring bean** via dependency injection; method security normally relies on a Spring AOP proxy and does not apply automatically to objects instantiated with `new`.

### 4.3. Service with Different Policies

File `GreetingService.java`:

~~~java
package com.example.demo;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    @PreAuthorize("isAnonymous()")
    public String anonymousLanding() {
        return "guest";
    }

    @PreAuthorize("isAuthenticated()")
    public String memberProfile() {
        return "member";
    }

    @PreAuthorize("isFullyAuthenticated()")
    public String sensitiveSettings() {
        return "settings";
    }

    @PreAuthorize("hasAuthority('REPORT_READ')")
    public String report() {
        return "report";
    }

    @PreAuthorize("permitAll()")
    public String welcome() {
        return "welcome";
    }
}
~~~

Methods return constants so tests focus purely on authorization without mixing in database/API logic. In real production code, `memberProfile()` must also check that the resource belongs to the current user; `isAuthenticated()` never replaces data ownership checks.

**Why split the methods?** Each method highlights the difference between "guest only", "logged in", "fully authenticated", "specific permission", and "public". This also produces security tests with targeted assertions instead of only checking generic HTTP status codes.

## 5. Unit/Integration Testing the Spring Bean Directly with @WithAnonymousUser

File `GreetingServiceSecurityTest.java`:

~~~java
package com.example.demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;

@SpringBootTest
class GreetingServiceSecurityTest {

    @Autowired
    GreetingService service;

    @Test
    @WithAnonymousUser
    void guestMayCallAnonymousOnlyAndPublicMethods() {
        assertEquals("guest", service.anonymousLanding());
        assertEquals("welcome", service.welcome());
    }

    @Test
    @WithAnonymousUser
    void guestCannotCallMethodsRequiringLogin() {
        assertThrows(AccessDeniedException.class,
            service::memberProfile);
        assertThrows(AccessDeniedException.class,
            service::sensitiveSettings);
        assertThrows(AccessDeniedException.class,
            service::report);
    }

    @Test
    @WithMockUser(username = "alice")
    void authenticatedUserIsNotAnonymous() {
        assertThrows(AccessDeniedException.class,
            service::anonymousLanding);
        assertEquals("member", service.memberProfile());
        assertEquals("settings", service.sensitiveSettings());
        assertThrows(AccessDeniedException.class,
            service::report);
    }

    @Test
    @WithMockUser(username = "alice",
                  authorities = {"REPORT_READ"})
    void userWithExplicitAuthorityCanReadReport() {
        assertEquals("report", service.report());
    }
}
~~~

The methods use `assertThrows(AccessDeniedException.class, ...)` because they call the **method security proxy** with an anonymous context or an under-privileged user. When protected at the HTTP layer, that exception may be translated into a 401/403 response depending on the authentication entry point and trust resolver; do not infer HTTP status codes from this service test.

**When are the tests above trustworthy?**

- `@SpringBootTest` loads the Spring application context from `DemoApplication`.
- `@EnableMethodSecurity` enables pre/post method authorization.
- `GreetingService` is injected from the Spring container, so calls pass through the proxy.
- `spring-security-test` and the Spring TestContext listener build `SecurityContext` per annotation for each test.
- `GreetingService` itself is not replaced with a mock or created with `new`.

If you use `@MockBean GreetingService` or Mockito `@Mock GreetingService`, calls to the mock normally **do not run `@PreAuthorize` on the real bean**. A "passing" test in that situation does not verify the service's authorization policy. You may mock repositories/downstream dependencies, **but keep the service under test as a real bean/proxy**.

### 5.1. Why Does Default user("alice") Lack REPORT_READ?

`@WithMockUser(username = "alice")` normally creates a user with the default role (such as `ROLE_USER`), without adding authority `REPORT_READ`. Because the service uses `hasAuthority('REPORT_READ')`, the test must declare **`authorities={"REPORT_READ"}`**.

Do not confuse them:

- `roles={"ADMIN"}` typically becomes authority `ROLE_ADMIN`.
- `authorities={"ADMIN"}` is an authority with the **literal** name `ADMIN`.
- `hasRole('ADMIN')` and `hasAuthority('ROLE_ADMIN')` usually have equivalent meaning under the default role prefix; `hasAuthority('ADMIN')` is not the same.

When testing a logged-in user lacking permissions, do not substitute `@WithAnonymousUser`. You need a distinct authenticated user to verify the system does not confuse **"not logged in"** with **"logged in but unauthorized"**.

### 5.2. Annotations Can Be Applied at the Class Level

If most tests require a guest:

~~~java
@SpringBootTest
@WithAnonymousUser
class GuestMethodTests {
    @Autowired
    GreetingService service;

    @Test
    void publicMethodWorks() {
        assertEquals("welcome", service.welcome());
    }

    @Test
    @WithMockUser(username = "alice")
    void specialUserOverride() {
        assertEquals("member", service.memberProfile());
    }
}
~~~

The snippet above **illustrates a separate class**, needing the same imports as section 5; do not paste a duplicate class into another test file expecting it to run as one compilation unit. Method annotations override the test context as intended.

### 5.3. Missing Authentication Differs from @WithAnonymousUser

Some developers use `@WithAnonymousUser` to simulate **`SecurityContextHolder.clearContext()`**. That is inaccurate:

- When `SecurityContextHolder` is completely cleared, `getAuthentication()` can be `null`.
- With `@WithAnonymousUser`, the test builds anonymous authentication for security expressions.
- In a standard Servlet request, `AnonymousAuthenticationFilter` may create an anonymous token; yet before the filter runs, on background threads, or in a custom chain, `Authentication` can genuinely be null.

If your business logic cares about "no `Authentication` object", write a separate test for an **empty context**. However, method security tests should generally simulate the **realistic Servlet anonymous state** using `@WithAnonymousUser`. Never conflate the two contexts and claim `null == AnonymousAuthenticationToken`.

## 6. Testing the HTTP Layer with MockMvc: 401 and 403 Are Different Cases

`@WithAnonymousUser` is great for testing methods. However, to verify the **Servlet filter chain, status codes, entry point, and responses**, add HTTP tests with `MockMvc` or real integration tests.

Example configuration in `WebSecurityConfig.java`:

~~~java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/account").authenticated()
                .requestMatchers("/api/reports")
                    .hasAuthority("REPORT_READ")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

This is a simplified policy for learning purposes. Production typically involves more endpoints, CORS/CSRF, sessions, or bearer authentication; design it completely. `httpBasic()` is enabled so the example returns **401** for guests instead of redirecting to a login page. With form login, an anonymous request may receive a **302 redirect**; with Bearer APIs, the challenge is typically `WWW-Authenticate: Bearer`.

Controller file `DemoController.java`:

~~~java
package com.example.demo;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/api/public")
    public Map<String, String> publicData() {
        return Map.of("visibility", "public");
    }

    @GetMapping("/api/account")
    public Map<String, String> account() {
        return Map.of("visibility", "private");
    }

    @GetMapping("/api/reports")
    public Map<String, String> reports() {
        return Map.of("visibility", "reports");
    }
}
~~~

With Spring MVC, `/api/public` allows anonymous access; `/api/account` requires authentication; `/api/reports` additionally requires an exact authority.

### 6.1. MockMvc Testing HTTP Statuses

File `AnonymousHttpSecurityTest.java`:

~~~java
package com.example.demo;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.anonymous;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class AnonymousHttpSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousCanReadPublicButNotPrivate() throws Exception {
        mvc.perform(get("/api/public").with(anonymous()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.visibility").value("public"));

        mvc.perform(get("/api/account").with(anonymous()))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/reports").with(anonymous()))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedWithoutReportAuthorityIsForbidden()
            throws Exception {
        mvc.perform(get("/api/reports").with(user("alice")))
            .andExpect(status().isForbidden());
    }

    @Test
    void authenticatedWithReportAuthorityMayContinue()
            throws Exception {
        mvc.perform(get("/api/reports")
                .with(user("alice").authorities(
                    new SimpleGrantedAuthority("REPORT_READ"))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.visibility").value("reports"));
    }
}
~~~

**Note when copying Java imports:** for compatibility with all compilers/style checkers, put each `import static ...;` declaration on **a single line**. For example, the full import for `anonymous` is:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.anonymous;
~~~

Multi-line imports in the example are solely for Markdown readability; when placing them in actual Java files, normalize them to single-line imports. Line wrapping does not change class structure, though project formatters may enforce strict rules.

**How the test works:**

- `.with(anonymous())` applies anonymous to that request. It differs from placing `@WithAnonymousUser` on a JUnit method, even though both help simulate a guest.
- `.with(user("alice"))` creates a mock authenticated user; it **does not** send an HTTP Basic password over the wire and **does not** test `UserDetailsService` or password encoders.
- With `httpBasic()` and the policy above, guests on private routes typically receive `401 Unauthorized` (HTTP Basic entry point); authenticated users lacking `REPORT_READ` receive `403 Forbidden`.
- `@AutoConfigureMockMvc` paired with Spring Boot Test provides a `MockMvc` using the Spring Security filter chain when properly configured. If building a standalone `MockMvc` manually, apply Spring Security Test configuration properly; never assume the filter chain always runs.

**Do not turn `401/403` into a universal assertion for every app**: HTTP status depends on the entry point (Basic/form/OAuth), exception translation, URL rules, custom handlers, and proxies. In service-level tests, `AccessDeniedException` is not an HTTP response.

### 6.2. Is Unauthenticated Due to an Expired Session the Same as Anonymous?

When a browser holds a session cookie whose session has expired or no longer exists, a request to a protected endpoint may be handled as an anonymous guest **after filters read the session and set up the security context**. However, `@WithAnonymousUser` cannot test:

- Whether the browser actually sends the cookie.
- How the JDBC/Redis session repository handles a non-existent ID.
- Request cache, login redirect, or stale session CSRF tokens.
- Session fixation defense, logout invalidation, and concurrency control.

To test those aspects, write **`MockMvc` tests with explicit session lifecycles** or HTTP/browser integration tests with a cookie jar, not just annotations.

### 6.3. What About "Anonymous with an Invalid Token"?

A request completely lacking credentials differs from a request **supplying invalid credentials**. For instance, a Resource Server API receives:

~~~http
GET /api/account HTTP/1.1
Authorization: Bearer broken-token
~~~

The filter may attempt to decode the token and return an authentication error even if the endpoint uses `permitAll()`, because `permitAll` is only an **authorization** policy and does not necessarily disable **authentication filters**.

`@WithAnonymousUser` does not trigger JWT decoding or validate signatures, expiry, issuers, or introspection. To test invalid tokens, send the HTTP header with a decoder/mock or run appropriate Authorization Server/Resource Server integration tests, verifying `401 invalid_token` or the protocol-specific error code.

## 7. Testing Harder Unauthenticated Scenarios

### 7.1. No Auth, Anonymous, and Remember-Me

| State | Appropriate Test Setup | What the Test Must Assert |
| --- | --- | --- |
| Anonymous in method security | `@WithAnonymousUser` | `isAnonymous()` true; `isAuthenticated()`/roles protect properly |
| Anonymous in HTTP request | `.with(anonymous())` | Public OK; private blocked by entry point |
| Empty `SecurityContext` | Clear or configure empty context in a dedicated test | Code does not throw `NullPointerException`; policy fails closed |
| Logged-in user with valid password | `@WithMockUser` or `.with(user(...))` | Granted minimum access matching role |
| Remember-me | Create suitable `RememberMeAuthenticationToken` or cookie integration test | `isAuthenticated()` may be true while `isFullyAuthenticated()` is false |
| Logged-in user lacking authority | `@WithMockUser` without required authority | Access denied/HTTP 403, not treated as a guest |

**Remember-me** is especially important for sensitive actions: a remember-me cookie does not mean the user just verified their password/MFA. Test `fullyAuthenticated()` or step-up policies for actions like changing passwords, updating recovery email, or transferring funds.

Do not manually force `authenticated=true` on untrusted tokens just to make tests pass; create the proper authentication type and use standard test APIs to reflect the real security model.

### 7.2. Guests May Still Be Allowed to View Public Pages

A method annotated `@PreAuthorize("permitAll()")` is public at method authorization, even with an anonymous `SecurityContext`. Yet if the corresponding controller sits behind a URL rule `.authenticated()`, guest requests can still be blocked **before the method is called**. Conversely, a `permitAll()` URL endpoint calling a `@PreAuthorize("isAuthenticated()")` service can deny guests **inside the service**.

Therefore, test **both layers**:

- Service layer: `@WithAnonymousUser` and calls through the proxy.
- Servlet layer: `MockMvc` with anonymous requests, real filter chain, URL matchers, and HTTP entry point.

Data leaks often arise when developers test only one layer and assume the other layer is protected too.

### 7.3. Unauthenticated vs. Unauthenticated with Remaining Session Data

A session may hold UI state or a guest's shopping cart, yet **that does not make them an authenticated user**. In tests, do not use session attributes like `login=true`/`username="alice"` assuming Spring Security treats that as `Authentication`. Spring Security manages context through its own mechanisms/filters/repositories. When designing custom authentication, everything "placed in context" must originate from server-verified evidence.

If a session carries a stale `SecurityContext` whose credentials were revoked, appropriate revocation/session-invalidation policies are required. Testing only `@WithAnonymousUser` does not cover distributed sessions, logout, and production revocation.

### 7.4. Authentication Exceptions Differ from Authorization Exceptions

An `AuthenticationException` typically indicates authentication failed or valid credentials are missing; `AccessDeniedException` indicates access is forbidden. In the HTTP pipeline, `ExceptionTranslationFilter` normally uses a trust resolver and handlers to choose whether to return a challenge or a denied response.

In method tests, Spring Security can throw `AccessDeniedException` when an anonymous caller fails `@PreAuthorize`. In the HTTP pipeline, the same request may be translated to `401` by `AuthenticationEntryPoint`, because an anonymous visitor should be prompted to authenticate rather than just receiving a missing-permission error.

**Do not assert "a `@PreAuthorize` method always throws HTTP 401".** A method knows nothing about HTTP when called directly from a test/service outside the Servlet pipeline.

## 8. CSRF, HTTP Methods, and Anonymous

CSRF does not apply only to logged-in users. If an application uses cookies/sessions and exposes state-changing endpoints, test the CSRF policy. For example, `POST /signup` may be public for authentication yet still subject to CSRF protection or a specific exemption policy.

With `MockMvc`:

~~~java
mvc.perform(post("/public-action")
        .with(anonymous()))
    .andExpect(status().isForbidden());
~~~

This is an **excerpt of a test that already has `MockMvc mvc`, static imports, and matching endpoint/CSRF configuration**; status depends on URL and chain. If the route allows anonymous access while keeping CSRF enabled, a POST missing a CSRF token typically fails with `403` before reaching the controller. That does not prove the guest was denied for being unauthenticated.

To test a valid request with CSRF:

~~~java
mvc.perform(post("/public-action")
        .with(anonymous())
        .with(csrf()))
    .andExpect(status().isOk());
~~~

This example only works if `/public-action` is an actual POST endpoint configured with `permitAll()` whose controller returns 200; it is **not a route declared in `DemoController` in section 6**. Create the corresponding fixture before running.

Do not overlook this when writing guest tests. A `403` can come from **a missing CSRF token**, not from `@PreAuthorize` or URL authorization. Tests must pinpoint the denial reason at the right layer.

## 9. Common Testing Mistakes

| Symptom | Common Cause | Fix |
| --- | --- | --- |
| `@WithAnonymousUser` has no effect | Test does not run Spring TestContext/listener | Use Spring test integration, `@SpringBootTest`, or suitable context |
| Method has `@PreAuthorize` yet anonymous still invokes it | Method security not enabled, object created with `new`, self-invocation | Enable `@EnableMethodSecurity`, inject bean/proxy, call via proxy |
| Test passes with a Mockito mock of the service | Mock does not execute the method interceptor | Keep real service bean, mock only downstream dependencies |
| `getAuthentication() == null` assertion fails | `AnonymousAuthenticationToken` is already in context | Distinguish anonymous token from empty context |
| `Authentication.isAuthenticated()` is true despite guest not logging in | Raw token flag does not reflect trust resolver | Use `isAuthenticated()` expression or appropriate resolver |
| HTTP test expects 403 but gets 401 | Anonymous is routed to authentication entry point | Check Basic/Bearer/form login and authorization flow |
| HTTP test expects 401 but gets 302 | Form login redirects to login page | Assert redirect or switch test fixture to HTTP Basic |
| Guest test gets 403 on public POST | CSRF filter blocks before method/controller | Test `.with(csrf())` and isolate denial cause |
| `@WithMockUser(roles="ADMIN")` still fails `hasAuthority("ADMIN")` | `ROLE_` prefix differs from authority string | Use `hasRole("ADMIN")` or explicit authority matching policy |
| Public API with invalid Bearer token still returns 401 | Filter attempts authentication before `permitAll` authorization | Check `BearerTokenResolver`/resource-server filters |
| Service test shows right permissions yet HTTP still blocks | URL matcher/filter chain differs from service policy | Test both method and Servlet layers with MockMvc |
| One test is affected by previous test's user | Manually set holder/strategy without cleanup | Use test listener and clear context in `finally` when setting up manually |
| Guest sees account data in response | Endpoint/service missing check, or business object lacks ownership check | Apply URL + method/resource authorization; test concrete data |

### Illustrative Run Output

With a Gradle project containing the application/config/test files from sections 4–6:

~~~bash
./gradlew test
~~~

On Windows:

~~~powershell
.\gradlew.bat test
~~~

When testing in a Maven project with equivalent dependencies declared:

~~~bash
./mvnw test
~~~

Test runner output depends on Gradle/Maven/JUnit versions, so do not fabricate literal `BUILD SUCCESSFUL` lines or test counts without running them. What matters is verifying the test genuinely loads the Spring context, passes through the method security proxy, and asserts the expected behavior.

## 10. Additional Test Pattern: Anonymous Even When Class Default Is a User

A large test suite may put `@WithMockUser` at the class level to reduce repetition. When adding an anonymous test, mark it explicitly so it does not accidentally inherit the user.

The code below is a **separate illustrative class** with imports similar to section 5:

~~~java
@SpringBootTest
@WithMockUser(username = "tester", authorities = {"REPORT_READ"})
class DefaultLoggedInSuite {

    @Autowired
    GreetingService service;

    @Test
    void defaultUserCanReadReport() {
        assertEquals("report", service.report());
    }

    @Test
    @WithAnonymousUser
    void anonymousOverrideCannotReadReport() {
        assertThrows(AccessDeniedException.class,
            service::report);
    }
}
~~~

Key takeaway: `@WithAnonymousUser` on the **test method** prevents that individual test from using the class-level mock user. Ensure no `@BeforeEach` manually overwrites `SecurityContextHolder`, as that would cause the scenario to diverge from the test's name.

If a project supports multiple identity mechanisms (JWT, OAuth2 Login, SAML), create separate test cases for each principal/token type rather than using a single `@WithMockUser` to "prove" every login flow.

## 11. Variant: Testing Failures When SecurityContext Is Truly Empty

In some services/workers running **outside the Servlet filter chain**, `SecurityContextHolder.getContext().getAuthentication()` can be `null`. In that case, the goal is verifying the code fails closed without throwing an unexpected `NullPointerException`.

A runnable **plain Java 17** example, requiring no Spring, illustrating the distinction between `null` and an anonymous marker:

File `GuestStateDemo.java`:

~~~java
public class GuestStateDemo {
    enum AuthState {
        MISSING, ANONYMOUS, AUTHENTICATED
    }

    static boolean mayReadPrivate(AuthState state) {
        return state == AuthState.AUTHENTICATED;
    }

    static boolean mayReadPublic(AuthState state) {
        return state != null;
    }

    public static void main(String[] args) {
        System.out.println(mayReadPrivate(AuthState.MISSING));
        System.out.println(mayReadPrivate(AuthState.ANONYMOUS));
        System.out.println(mayReadPrivate(AuthState.AUTHENTICATED));
        System.out.println(mayReadPublic(AuthState.ANONYMOUS));
    }
}
~~~

Compile/run:

~~~bash
javac GuestStateDemo.java
java GuestStateDemo
~~~

**Exact** stdout:

~~~text
false
false
true
true
~~~

This example models only a minimal policy. In real Spring Security, state decisions must rely on verified authentication and framework authorization logic; never use a client-supplied enum to decide permissions.

With Spring, if you need to intentionally clear the context inside a narrow test, you can use:

~~~java
SecurityContextHolder.clearContext();
Authentication value =
    SecurityContextHolder.getContext().getAuthentication();
assertNull(value);
~~~

This is a **test snippet**, requiring static import `Assertions.assertNull` and Spring Security context imports; if the test configures a special holder strategy, manage its lifecycle and clean up in `finally`. Never take that empty-context behavior as proof that a real Servlet request passing through the anonymous filter has a null authentication.

## 12. Verifying the Difference Between @WithAnonymousUser and anonymous() with a QA Plan

**Group A – method authorization:** run `GreetingServiceSecurityTest`. Expected result: guests may invoke `anonymousLanding()` and `welcome()`, yet are denied at `memberProfile()`, `sensitiveSettings()`, and `report()`. Only a user granted `REPORT_READ` succeeds on `report()`. This tests **AOP method security**.

**Group B – HTTP authorization:** run `AnonymousHttpSecurityTest`. Expected result with HTTP Basic: `/api/public` returns 200, `/api/account` and `/api/reports` return 401 when anonymous, an authenticated user lacking the authority at `/api/reports` gets 403, and a user with the authority gets 200. This tests **filter chain, URL authorization, and entry point**.

**Group C – failure modes:** add tests for missing cookies, expired sessions, wrong Basic passwords, expired JWTs, POST missing CSRF, remember-me, and non-existent routes. These cases **cannot be replaced by a single `@WithAnonymousUser`**; they require proper fixtures and pipelines.

**Group D – preventing data leaks:** for guests, verify responses contain no other user's data, authorities, access tokens, stack traces, or session details. Returning a correct 401 is not enough if the body/logs leak sensitive information.

**Group E – test isolation:** run tests in random order or in parallel within supported configuration bounds, confirming no user from an earlier test leaks into a later test. When creating `SecurityContext` manually, clean up the right thread and avoid a global holder strategy.

## 13. Checklist Before Concluding Method Security Works

- [ ] Add `spring-security-test` with a version compatible with Boot/Security.
- [ ] Use Spring TestContext (e.g., `@SpringBootTest`) so `@WithAnonymousUser` executes.
- [ ] Enable `@EnableMethodSecurity` so `@PreAuthorize` is actually enforced.
- [ ] Inject the service bean from Spring, never calling a `new` instance or a Mockito mock in place of the service under test.
- [ ] Test `isAnonymous()`, `isAuthenticated()`, `isFullyAuthenticated()`, and authorities with accurate semantics.
- [ ] Do not treat `AnonymousAuthenticationToken` as a logged-in user just because raw `isAuthenticated()` can return true.
- [ ] Separate guest tests from authenticated-but-lacking-role/scope tests.
- [ ] For HTTP, use `MockMvc` and the `anonymous()` post-processor; test different Basic/Bearer/form entry points.
- [ ] Distinguish method exceptions from HTTP `401/403/302` codes translated by the filter pipeline.
- [ ] Do not take URL `permitAll()` as proof that underlying services are protected.
- [ ] Test invalid credentials, session expiry, remember-me, and CSRF if supported by the application.
- [ ] Ensure the test runner actually executes the security filter chain and security AOP rather than fixtures bypassing them.
- [ ] Tests must not leak private data in response bodies/logs, even when the server returns the right error status.
- [ ] Clean up `SecurityContext` after manual setup to avoid user leaks across tests/threads.

**Conclusion:** `@WithAnonymousUser` is a tool for testing **the anonymous context** in Spring Security Test, well suited for verifying that `@PreAuthorize` methods properly guard against unauthenticated callers. It is not synonymous with an empty context, nor does it simulate a complete failed HTTP request. For comprehensive Servlet security testing, combine **service tests via the Spring AOP proxy**, **`MockMvc` with `anonymous()`**, and dedicated cases for invalid credentials, session expiry, remember-me, CSRF, and authenticated users lacking permissions.
