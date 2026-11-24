# From HTTP Request to Identity, Access Decision, and Response in Spring Security

> **Context:** Spring Security for Spring MVC/Servlet applications, Java 17+, and Spring Boot 3.x. This lesson traces **an HTTP request** from entering the application until it is permitted, prompted to log in, or denied. Specific filter names and ordering may vary by configuration.

## 1. Three Questions Every Request Must Pass Through

Suppose a client calls **GET /admin**. The application needs to clarify:

1. **Which protection layer does the request pass through?** The Servlet container routes the request through a filter chain; Spring Security selects a matching **SecurityFilterChain**.
2. **Who is sending the request?** **Authentication** describes the current identity. Identity may be loaded from a login session, authenticated from username/password, HTTP Basic, a bearer token, or remain anonymous.
3. **Does that identity have permission to execute the request?** **AuthorizationManager** applies rules; the request either proceeds to the controller or raises an access exception that becomes an appropriate HTTP response.

Two concepts must be separated:

| Concept | Question | Typical Outcome |
| --- | --- | --- |
| **Authentication** | Who are you? Is the proof valid? | An **Authentication** object containing principal and authorities; failure typically triggers an authentication-challenge mechanism. |
| **Authorization** | Is the current identity allowed to access this resource/action? | Allows the request to proceed or rejects it with **AccessDeniedException**. |

**Being logged in does not mean having sufficient permissions.** User **alice** with **ROLE_USER** can view **/me** but cannot by default view **/admin**, which requires **ROLE_ADMIN**.

## 2. Diagram of an HTTP Request's Path

~~~text
Client: GET /admin + Authorization header (if present)
  |
  v
Servlet container
  |
  v
DelegatingFilterProxy -> FilterChainProxy ("springSecurityFilterChain")
  |
  +-- Select first SecurityFilterChain matching the request
        |
        +-- SecurityContextHolderFilter: retrieve/initialize SecurityContext
        +-- Protection filters: headers, CORS/CSRF if configured
        +-- Appropriate authentication filter: Basic, form login, bearer... if applicable
        +-- AnonymousAuthenticationFilter: supply anonymous if no identity yet
        +-- ExceptionTranslationFilter: wraps downstream steps to catch security errors
        +-- AuthorizationFilter: queries AuthorizationManager
              |
              +-- PERMITTED ---> DispatcherServlet -> Controller -> Service
              |                         |
              |                         +--> HTTP 200/201/... or business error
              |
              +-- DENIED ------> AccessDeniedException
                                      |
                                      v
                            ExceptionTranslationFilter
                              |                    |
                       Unauthenticated       Authenticated,
                       / anonymous           lacks permission
                              |                    |
                       AuthenticationEntryPoint   AccessDeniedHandler
                              |                    |
                       401 + challenge,          usually 403
                       or 302 login
~~~

This is a **mental model**, not a fixed filter list for every application. Filters are chosen depending on configuration (HTTP Basic, form login, OAuth2 resource server, etc.). **ExceptionTranslationFilter sits ahead of AuthorizationFilter in the chain**, invoking the next part and catching security exceptions thrown from it. Only permitted requests continue to Spring MVC; a filter can also complete the response itself without calling the next filter.

### 2.1. From Servlet Container to SecurityFilterChain

- **DelegatingFilterProxy** connects the servlet container's filter to the **springSecurityFilterChain** bean in Spring.
- This bean is usually **FilterChainProxy**, holding multiple **SecurityFilterChain** instances; each chain has its own **RequestMatcher** and filter set.
- **FilterChainProxy selects the first matching chain**, then runs the filters in that chain. When configuring multiple chains, matcher order and scope are critical; requests matching no chain may not be protected by Spring Security.
- **securityMatcher(...)** chooses **which chain a request belongs to**, whereas **requestMatchers(...)** inside **authorizeHttpRequests(...)** chooses **authorization rules within the selected chain**. Do not confuse these two levels.

For example, if a system has an API chain for **/api/** and a web chain for everything else: selecting the API chain comes first; the rule requiring ADMIN for **/api/admin/** comes second.

### 2.2. How SecurityContext Is Established, Used, and Cleared

**SecurityContextHolder** holds the **SecurityContext** for the current processing thread (typically via ThreadLocal). **SecurityContext** may hold an **Authentication**. **SecurityContextHolderFilter** integrates with **SecurityContextRepository** to obtain the context at the start of a request; **FilterChainProxy** ensures the request's context is cleared when finished, preventing identity leaks across requests/threads.

Do not assume every request re-authenticates username/password: a login session can supply a saved context, whereas HTTP Basic or a bearer token typically supplies proof on each request. Whether **SecurityContext is saved for subsequent requests** depends on the login mechanism and repository/session configuration; in modern configuration, the filter/mechanism performing authentication must explicitly save the context when session persistence is desired, rather than assuming any update to ThreadLocal is saved automatically.

An **Authentication** typically has:

- **principal**: the identity, which may be a **UserDetails**, a username string, or another object;
- **credentials**: proof such as a password/token, usually erased or restricted after authentication;
- **authorities**: permissions as **GrantedAuthority**, such as **ROLE_USER**, **ROLE_ADMIN**, **SCOPE_read**;
- **authenticated**: internal state of the object; **do not rely solely on isAuthenticated() to conclude a user actually logged in**, because anonymous authentication can also report **true**. The framework provides mechanisms to distinguish anonymous/remember-me/full authentication.

## 3. Authentication: From Proof to Identity

With the **HTTP Basic** example, the typical processing sequence is:

1. Client sends **Authorization: Basic ...** (username/password Base64-encoded, **not secure encryption**).
2. **BasicAuthenticationFilter** extracts the credentials and creates an initial **Authentication** request.
3. **AuthenticationManager** processes authentication; the common implementation **ProviderManager** delegates to an **AuthenticationProvider** supporting that token type.
4. For example, **DaoAuthenticationProvider** uses **UserDetailsService** to look up the account and **PasswordEncoder** to verify the encoded password.
5. When valid, the resulting **Authentication** with identity and authority list is placed into **SecurityContextHolder**. If credentials are invalid, the authentication mechanism handles failure and may ask the client to resend credentials.

~~~text
HTTP Basic header
    -> BasicAuthenticationFilter
    -> AuthenticationManager (usually ProviderManager)
    -> AuthenticationProvider
    -> UserDetailsService + PasswordEncoder (username/password case)
    -> Authenticated Authentication
    -> SecurityContext
~~~

**Not all authentication uses UserDetailsService.** Bearer JWTs are typically verified by resource server components for signature, issuer, audience, expiration, and mapped from claims to authorities; form login typically flows through **UsernamePasswordAuthenticationFilter**. For this lesson, focus on the common pattern: a mechanism receives proof, verifies proof, and places **Authentication** into the context for authorization.

When no credentials are present and no identity exists yet, **AnonymousAuthenticationFilter** can insert an **AnonymousAuthenticationToken**. That allows uniform handling, but **anonymous is not treated as a logged-in user** for the **authenticated()** rule.

## 4. Authorization: From Authentication to an Allow Decision

When a request reaches **AuthorizationFilter**, the filter retrieves **Authentication** via **SecurityContextHolder** (potentially deferred) and passes it with the request to **AuthorizationManager**. Under **authorizeHttpRequests**, rules are evaluated in declaration order; **the first matching rule** decides access.

| Rule | Meaning |
| --- | --- |
| **permitAll()** | Allows access without requiring login; still passes through the protective filter chain. |
| **authenticated()** | Requires an identity considered authenticated by Spring Security. |
| **hasRole("ADMIN")** | Requires authority **ROLE_ADMIN** under the default prefix. |
| **hasAuthority("SCOPE_read")** | Requires the exact authority string **SCOPE_read**. |
| **denyAll()** | Denies every request matching the rule. |

Decisions follow two main paths:

- **Granted:** **AuthorizationFilter** invokes the next filter; the request reaches **DispatcherServlet**, controller, and service. The controller may then return JSON, text, a redirect, a business error, or call methods with additional protection.
- **Denied:** **AuthorizationFilter** throws **AccessDeniedException**; the upstream **ExceptionTranslationFilter** translates the security error into the configured HTTP response.

**URL authorization is only one layer.** If **GET /orders/123** requires ROLE_USER, the application must still verify whether that person has permission to view order **123** (ownership/tenant). This can be done in the service or via method security such as **@PreAuthorize** when **@EnableMethodSecurity** is enabled; a generic role does not automatically resolve data-level access permissions.

## 5. Why Do 401, 403, and Sometimes 302 Occur?

**ExceptionTranslationFilter** bridges security exceptions to HTTP responses:

- **AuthenticationException**, or **AccessDeniedException** from an **anonymous/unauthenticated** user: invokes **AuthenticationEntryPoint** to initiate authentication.
- **AccessDeniedException** from an **authenticated user lacking permission**: invokes **AccessDeniedHandler**, usually returning **403 Forbidden**.

| Scenario | Typical Result | Reason |
| --- | --- | --- |
| GET public endpoint, not logged in | 200 if controller succeeds | **permitAll()** rule allows proceeding. |
| GET login-required endpoint, no credentials, API using HTTP Basic | **401 Unauthorized**, usually with **WWW-Authenticate: Basic ...** | **AuthenticationEntryPoint** requests credentials. |
| GET login-required endpoint, web app using form login | **302** to login page | Form-based entry point chooses redirect instead of 401. |
| Wrong HTTP Basic credentials | Usually **401** | Authentication failed; no valid identity established. |
| Logged-in user with ROLE_USER accesses endpoint needing ROLE_ADMIN | Usually **403 Forbidden** | Has identity but lacks sufficient authority. |
| POST with session/cookie missing valid CSRF token when CSRF is enabled | Usually **403 Forbidden** | **CsrfFilter** blocks the request, potentially before the authorization step. |
| Permitted, but controller cannot find resource | May be **404 Not Found** | Application-layer condition/error, not an access decision. |

**Do not attribute every 401/403 to a single filter:** entry point, access denied handler, CSRF, error dispatch, and specific configuration all affect the response. 401/403 can also be returned by application code or upstream infrastructure; read logs to locate the source. With Basic, use **HTTPS** because Base64 does not protect passwords in transit.

## 6. Runnable Example: A Minimal API with Public, User, and Admin

Assume you already have a **Spring Boot 3.x + Java 17+** project using Spring MVC. Add the following dependencies to your existing **build.gradle** (plugin/BOM versions managed by the project):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Create three files in **src/main/java/com/example/securityflow/**, in package **com.example.securityflow**.

**SecurityFlowApplication.java**

~~~java
package com.example.securityflow;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityFlowApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityFlowApplication.class, args);
    }
}
~~~

**SecurityConfig.java**

~~~java
package com.example.securityflow;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
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
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
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
            .password(encoder.encode("alice123"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin123"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }
}
~~~

**DemoController.java**

~~~java
package com.example.securityflow;

import java.util.stream.Collectors;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping("/me")
    public String me(Authentication authentication) {
        String authorities = authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .collect(Collectors.joining(","));

        return authentication.getName() + " " + authorities;
    }

    @GetMapping("/admin")
    public String adminEndpoint() {
        return "admin-only";
    }
}
~~~

**Configuration explanation:**

- **/public** uses **permitAll()**; **/admin** requires authority **ROLE_ADMIN**; all remaining paths require **authenticated()**.
- **httpBasic(...)** enables HTTP Basic. Demo account **alice** has **ROLE_USER**; **admin** has **ROLE_ADMIN**. The **roles("ADMIN")** method automatically adds the **ROLE_** prefix.
- **BCryptPasswordEncoder** hashes passwords for safer comparison than plaintext storage; the two passwords in the example are strictly for learning environments and must be replaced by proper identity and secret management in real deployments.
- **DemoController.me(...)** receives the current **Authentication** from Spring MVC and displays the username and authorities, illustrating how post-authentication results are used by controllers.
- The example commands are **GET**, avoiding mixing the authorization lesson with CSRF requirements for state-changing methods. This configuration **does not automatically set sessions to stateless**.

Run from the project directory containing the Gradle Wrapper:

~~~bash
./gradlew bootRun
# On Windows: gradlew.bat bootRun
~~~

Send test requests against **localhost**:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u alice:alice123 http://localhost:8080/me
curl -i -u alice:alice123 http://localhost:8080/admin
curl -i -u admin:admin123 http://localhost:8080/admin
curl -i -u alice:wrong http://localhost:8080/me
~~~

Results to observe (status and **response body**; other headers may vary):

| Request | Expected HTTP status | Response body on success |
| --- | --- | --- |
| GET /public, anonymous | **200** | **public** |
| GET /me, anonymous | **401** | Body content not relied upon; observe **WWW-Authenticate** header. |
| GET /me, alice | **200** | **alice ROLE_USER** |
| GET /admin, alice | **403** | Body content not relied upon. |
| GET /admin, admin | **200** | **admin-only** |
| GET /me, wrong password | **401** | Body content not relied upon. |

These statuses assume **the application runs standalone with this exact example configuration**, without other custom chains, exception handlers, or reverse proxies. **curl -i** prints headers too; the text shown is the HTTP response body, not the Java program's stdout.

## 7. Tracing Three Representative Requests

### Case A: anonymous calls GET /me

1. The Servlet container routes the request through **FilterChainProxy** and the security chain.
2. With no credentials, **SecurityContext** does not yet hold an identity; **AnonymousAuthenticationFilter** may assign anonymous.
3. **AuthorizationFilter** evaluates **/me**: neither **/public** nor **/admin** matches, so it hits **anyRequest().authenticated()**.
4. Anonymous does not satisfy **authenticated()** and is denied.
5. **ExceptionTranslationFilter** catches the exception and invokes HTTP Basic's **AuthenticationEntryPoint**.
6. Client receives **401** and a challenge; **DemoController.me(...) does not run**.

### Case B: alice calls GET /admin with valid HTTP Basic

1. **BasicAuthenticationFilter** receives username/password, authenticates via the manager/provider, and produces an **Authentication** for **alice** containing **ROLE_USER**.
2. **AuthorizationFilter** selects the rule **/admin -> hasRole("ADMIN")**.
3. **ROLE_USER** does not satisfy **ROLE_ADMIN**, throwing **AccessDeniedException**.
4. Because alice is already authenticated, **ExceptionTranslationFilter** uses **AccessDeniedHandler** to return **403**; **adminEndpoint() does not run**.

### Case C: admin calls GET /admin

1. Valid credentials produce an **Authentication** for **admin** with **ROLE_ADMIN**.
2. **AuthorizationManager** allows it because the authority matches.
3. The request continues to **DispatcherServlet**, calling **adminEndpoint()**.
4. The controller returns the string **admin-only**, HTTP **200** if no other errors occur.
5. When the request ends, the thread-bound context is cleared in accordance with the filter lifecycle.

## 8. Targeted Automated Testing

With the two test dependencies declared, place **SecurityFlowTest.java** in **src/test/java/com/example/securityflow/**:

~~~java
package com.example.securityflow;

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
class SecurityFlowTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointIsAccessibleAnonymously() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void anonymousCannotReadMe() throws Exception {
        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void aliceCanReadMeButCannotEnterAdmin() throws Exception {
        mvc.perform(get("/me").with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(content().string("alice ROLE_USER"));

        mvc.perform(get("/admin").with(httpBasic("alice", "alice123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanEnterAdmin() throws Exception {
        mvc.perform(get("/admin").with(httpBasic("admin", "admin123")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-only"));
    }
}
~~~

Run **./gradlew test** (Windows: **gradlew.bat test**). The tests verify end-to-end HTTP behavior through the servlet filters; they do not need to call **AuthenticationManager** directly or manually populate **SecurityContext** to fake security outcomes. When testing service-level authorization, add dedicated tests for **@PreAuthorize**/ownership and same-role, different-owner cases.

## 9. Diagnosing Unexpected Status Codes

Enable security logging at DEBUG level in development:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

At startup, Spring Security logs can list the **filter chain**. When sending a request, check:

1. **Is the right chain handling the request?** Check matchers, chain order, actual path, and HTTP method.
2. **Is there an Authentication yet?** Check active mechanisms, valid credentials, session/context repository; do not log tokens/passwords.
3. **What are the authorities?** Distinguish **ROLE_ADMIN** from **ADMIN**, **SCOPE_read** from **read**; do not confuse roles and authorities.
4. **Which rule matches first?** An overly broad rule placed early can shadow a specific rule placed later.
5. **Who returned the status?** Distinguish authentication entry point, access denied handler, CSRF filter, controller advice, servlet error handling, and reverse proxy.

Common pitfalls:

- **Equating 401 and 403:** lacking valid identity differs from being authenticated without sufficient permission. Form login can also redirect **302**.
- **Checking roles only at URLs:** misses permissions on specific records (IDOR/BOLA). Ownership/tenant checks are needed in the business layer.
- **Using securityMatcher instead of requestMatchers or vice versa:** causes the chain not to protect the intended requests.
- **Confusing permitAll with bypassing Spring Security:** **permitAll()** still sends the request through filters such as security headers; do not casually exclude URLs from the entire chain.
- **Disabling CSRF to fix a 403:** first verify whether clients use cookies/sessions in a browser and what CSRF is protecting. With sessions/cookies, CSRF is usually an essential security requirement.
- **Reading isAuthenticated() manually without accounting for anonymous:** enforce permissions through policies/AuthorizationManager rather than guessing from a boolean flag.
- **Assuming SecurityContext saves automatically for every request:** understand the difference between a context active for the current request and one persisted to be restored later.
- **Writing a custom authentication filter without proper lifecycle/context management:** easily leaks identity or bypasses exception handling; prefer built-in Spring Security mechanisms.

## 10. Self-Check Your Knowledge

**Q1.** alice is logged in but encounters **403** at **/admin**. What should you check first?

**Answer:** The **hasRole("ADMIN")** rule requires **ROLE_ADMIN**, whereas alice only has **ROLE_USER**. A valid identity is not enough to grant permission.

**Q2.** Why does the same unauthenticated request return **401** in one app and **302** in another?

**Answer:** **AuthenticationEntryPoint** depends on the authentication mechanism/configuration: HTTP Basic typically returns 401 with a challenge; form login typically redirects to a login page.

**Q3.** Can you use **permitAll()** for **/public** while still applying security headers?

**Answer:** Yes. **permitAll()** is an authorization decision; the request still passes through the selected **SecurityFilterChain**.

**Q4.** If **ROLE_USER** can access **GET /orders/123**, does that prove they own order 123?

**Answer:** No. URL rules only check coarse permissions; the application must verify permission against that specific resource.

**Final takeaway:** For any request, trace **selected chain -> Authentication in SecurityContext -> AuthorizationManager rule -> proceed or handle exception -> HTTP response**. This core path helps you read configurations, debug 401/403 responses, and design security tests in the right place.

## Official References

- Spring Security — Servlet Architecture: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Cross Site Request Forgery (CSRF): https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
