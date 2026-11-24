# Invalidating HttpSession and Clearing Authentication from SecurityContext in Spring Security Servlet

**Context:** Java 17+, Spring Security 6.x, Spring Boot 3.x, and Jakarta Servlet. This lesson belongs to the **Logout** topic. The goal is to understand what actually happens when a user logs out of a cookie/session-based application, distinguish clearing per-request authentication from invalidating the server-side session, configure standard logout, and test that subsequent requests are no longer treated as logged in.

**Scenario:** A user has logged in via form login, and the server stored a <code>SecurityContext</code> containing an <code>Authentication</code> in <code>HttpSession</code>; the browser sends the <code>JSESSIONID</code> cookie on subsequent requests. If you merely clear a frontend variable or redirect to the login page, the server session may stay valid, allowing the browser to remain recognized whenever it resends the cookie.

Core principle: **proper logout invalidates the credentials accepted by the server**, rather than merely hiding the UI or clearing the username from the screen.

## 1. Three States Often Confused with Each Other

| Object | Where is it stored? | Role |
| --- | --- | --- |
| <code>Authentication</code> | Inside the request or session <code>SecurityContext</code> | Identity, authorities, and authentication status used by Spring Security for authorization. |
| <code>SecurityContext</code> | Accessed via <code>SecurityContextHolder</code>; can be persisted via <code>SecurityContextRepository</code> | Wraps the current Authentication and supports loading/saving across requests. |
| <code>HttpSession</code> | Servlet container or server-side session store; typically referenced by <code>JSESSIONID</code> | Holds cross-request state, potentially including SecurityContext and application data. |

You must distinguish **clearing the context**, **invalidating the session**, and **deleting cookies**:

- <code>SecurityContextHolder.clearContext()</code> removes the context from the strategy active for the current processing thread. It does not scan and delete previously persisted sessions.
- <code>request.getSession(false).invalidate()</code> destroys the **current HttpSession**, clears its attributes, and stops that session ID from pointing to a valid session. It does not automatically clear a context still held in the current request/thread unless handled accordingly.
- Deleting the <code>JSESSIONID</code> cookie in the browser stops the client from resending the old ID, yet **is not proof that the server destroyed the session**. A copy of that ID elsewhere could still be usable if the server session was never invalidated.

A standard Spring Security logout handler performs these coordinated steps consistently instead of letting a controller do only half the job.

## 2. Tracing a Request Before and After Logout

Before logout:

~~~text
Browser                          Servlet / Spring Security
  | Cookie: JSESSIONID=S1                   |
  | GET /me                                |
  |---------------------------------------->|
  |                    SecurityContextRepository loads context
  |                    Authentication(name=alice, authenticated)
  |                    AuthorizationFilter permits
  |<----------------------------------------|
  | 200, body alice                         |
~~~

During logout:

~~~text
Browser                          Servlet / Spring Security
  | POST /logout + Cookie S1 + CSRF token  |
  |---------------------------------------->|
  |                    CsrfFilter verifies request
  |                    LogoutFilter matches /logout
  |                    LogoutHandlers run:
  |                      - invalidate HttpSession S1
  |                      - clear SecurityContext
  |                      - clear authentication / save empty context
  |                      - clean up cookies, remember-me if configured
  |                    LogoutSuccessHandler decides response
  |<----------------------------------------|
  | 302 Location: /login?logout            |
~~~

Request after logout:

~~~text
Browser still tries sending JSESSIONID=S1
  |
  v
Server no longer has a valid HttpSession S1
  |
SecurityContext cannot load old Authentication
  |
GET /me must re-authenticate
  |
302 to /login (e.g., form login)
~~~

What needs testing is not just that the server returns “logout successful,” but that **the session was invalidated** and **a subsequent request with old state cannot read private resources**.

Note: HTTP status depends on the authentication mechanism. Form login normally redirects with 302, whereas REST APIs normally return 401 for anonymous requests. Do not mechanically apply form login's 302 to every API.

## 3. Spring Security's Default Logout Mechanism

Spring Security places <code>LogoutFilter</code> in <code>SecurityFilterChain</code> to recognize the logout URL and execute <code>LogoutHandler</code> instances. Common components:

- <code>SecurityContextLogoutHandler</code>: handles clearing authentication, clearing the context, and invalidating HttpSession as configured; also coordinates with <code>SecurityContextRepository</code> to avoid retaining the logged-out context.
- <code>CookieClearingLogoutHandler</code>: sends expired cookie headers so the browser stops sending specified cookies, if configured.
- <code>LogoutSuccessHandler</code>: decides the response after logout handlers finish, such as redirecting to the login page or returning HTTP 204.
- Remember-me logout handler (if remember-me is configured): cleans up required remember-me credentials on logout.
- <code>HttpSessionEventPublisher</code> (when registered): forwards Servlet container session-destroyed events into the Spring application context so mechanisms like <code>SessionRegistry</code> can clean up state.

With default form login and CSRF configuration, the logout operation is **POST /logout** with a valid CSRF token. Some Spring Security generated login setups may render a confirmation page on <code>GET /logout</code>, but GET should never execute a state-changing logout by itself.

### A Safe Default-Style Configuration

~~~java
http.logout(logout -> logout
    .logoutUrl("/logout")
    .logoutSuccessUrl("/login?logout")
    .invalidateHttpSession(true)
    .clearAuthentication(true)
    .deleteCookies("JSESSIONID")
    .permitAll());
~~~

The code above is **a snippet inside a SecurityFilterChain bean**, not a standalone class. In Spring Security, invalidating the session and clearing authentication are already typical defaults of <code>SecurityContextLogoutHandler</code>; here they are declared explicitly to show the decisions.

<code>.deleteCookies("JSESSIONID")</code> aids browser-side cookie cleanup, though effective deletion depends on the cookie Path/Domain stored by the browser and proxy routing. **Do not use cookie deletion as a substitute for server-side invalidation.**

<code>.permitAll()</code> ensures appropriate access to logout/success URLs; **it does not disable CSRF**. The logout URL can be handled by <code>LogoutFilter</code> before <code>AuthorizationFilter</code>, so avoid trying to fix issues by disabling CSRF protection or opening every route with <code>permitAll("/**")</code>.

## 4. SecurityContextHolder and SecurityContextRepository Are Not the Same Thing

During request processing, <code>SecurityContextHolder.getContext()</code> lets you read the current <code>Authentication</code>; the default strategy typically binds the context to the thread. On the next request, Spring Security filters can use <code>SecurityContextRepository</code> to restore the persisted context.

Illustrative example:

~~~java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

SecurityContextHolder.clearContext();
~~~

The second line **does not mean** the context inside HttpSession is automatically erased. If the repository still holds the old SecurityContext, a later request may reload the authenticated Authentication from the session.

In Spring Security 6, certain paths use <code>SecurityContextHolderFilter</code> with an **explicit SecurityContext save** policy. If you write a custom authentication/logout flow, you must understand the actual configured <code>SecurityContextRepository</code> and ensure empty state is saved or the session is invalidated properly. Do not merely call <code>setAuthentication(null)</code> on a retrieved context and hope all repositories and sessions are cleared.

**Recommendation:** use <code>LogoutFilter</code> and <code>SecurityContextLogoutHandler</code> instead of assembling small manual calls to mimic logout.

### The Session Store After Invalidation

Once <code>HttpSession.invalidate()</code> succeeds, the container/session store must treat that session as invalid; session attributes, including any SecurityContext stored inside, can no longer authenticate subsequent requests using the old session ID.

However, asynchronous operations or services already holding references to extracted data may still have work in flight; logout does not automatically cancel already-started tasks. If long-running sensitive jobs exist, the system needs separate controls (authorization at execution time, cancellation, or re-checking permissions).

## 5. When to Use `SecurityContextLogoutHandler` Manually?

Spring Security already provides <code>POST /logout</code>; there is no need to write a controller just to call invalidate. Still, if an application has a special authentication flow or a custom logout API, you might need to invoke <code>SecurityContextLogoutHandler</code> in **a fully protected endpoint**.

Non-standalone snippet example:

~~~java
@PostMapping("/account/logout")
public ResponseEntity<Void> logoutCurrent(
        HttpServletRequest request,
        HttpServletResponse response,
        Authentication authentication) {

    SecurityContextLogoutHandler handler =
        new SecurityContextLogoutHandler();
    handler.setInvalidateHttpSession(true);
    handler.setClearAuthentication(true);
    handler.logout(request, response, authentication);

    return ResponseEntity.noContent().build();
}
~~~

Here:
- The method executes **after** Spring Security has authenticated the request and verified CSRF when session cookies are used.
- <code>SecurityContextLogoutHandler.logout()</code> handles SecurityContext and HttpSession within the current request's scope, rather than just calling <code>request.getSession().invalidate()</code>.
- If the app uses remember-me, refresh tokens, or extra logout hooks, a custom controller must execute every required handler; this example **does not revoke other tokens**.
- Do not expose a logout URL over GET just for easy link clicking, especially in cookie/session apps.
- If using a custom <code>SecurityContextRepository</code>, make sure the logout handler coordinates with the repository as designed.

In production, integrate extra logic through <code>logout.addLogoutHandler(...)</code> or standard handlers rather than creating a second endpoint that accidentally behaves differently from <code>/logout</code>. When adding a <code>LogoutHandler</code> that calls external services, design proper error handling and idempotency; server logout must not leave the session valid simply because a remote audit system temporarily failed.

## 6. Runnable Example: Spring Boot Form Login + Logout

The sample project uses **Java 17+, Spring Boot 3.3.5, Spring Security 6.x, and Maven**. Demo user <code>alice</code> logs in via form login. When sending <code>POST /logout</code> with CSRF, the server invalidates HttpSession, clears Authentication from SecurityContext, and redirects to login. Subsequent private requests must require logging in again.

**Demo scope:** single JVM with the embedded Servlet container's HttpSession, in-memory account, and test password. Do not use this password or user store in production. The demo has no JWTs, refresh tokens, or Identity Provider.

Structure:

~~~text
spring-logout-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/logoutdemo/
    │       ├── LogoutDemoApplication.java
    │       └── SecurityConfiguration.java
    └── test/
        └── java/com/example/logoutdemo/
            └── LogoutSessionTest.java
~~~

### 6.1. pom.xml

~~~xml
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
    <artifactId>spring-logout-demo</artifactId>
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

### 6.2. Main Class and Private Endpoints

Create <code>src/main/java/com/example/logoutdemo/LogoutDemoApplication.java</code>:

~~~java
package com.example.logoutdemo;

import java.security.Principal;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class LogoutDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(LogoutDemoApplication.class, args);
    }

    @GetMapping("/public")
    public String publicInfo() {
        return "public";
    }

    @GetMapping("/me")
    public String me(Principal principal) {
        return principal.getName();
    }

    @GetMapping("/private")
    public String privateInfo() {
        return "private-data";
    }
}
~~~

<code>/public</code> can be read without logging in; <code>/me</code> and <code>/private</code> require authentication. There is no <code>/logout</code> controller: Spring Security's <code>LogoutFilter</code> handles that request directly.

### 6.3. SecurityConfiguration.java

Create <code>src/main/java/com/example/logoutdemo/SecurityConfiguration.java</code>:

~~~java
package com.example.logoutdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("local-password-1234"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(alice);
    }

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/login", "/error").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/login?logout")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .deleteCookies("JSESSIONID")
                .permitAll())
            .build();
    }
}
~~~

Configuration breakdown:
- Spring Security form login verifies the account and saves authentication via the appropriate session mechanism; session fixation protection remains managed by the framework.
- <code>anyRequest().authenticated()</code> forces <code>/me</code> and <code>/private</code> to require login.
- <code>logoutUrl("/logout")</code> is an endpoint for <code>LogoutFilter</code>, not an MVC method.
- <code>invalidateHttpSession(true)</code> destroys the current HttpSession; <code>clearAuthentication(true)</code> clears Authentication in the context.
- <code>deleteCookies("JSESSIONID")</code> helps prevent the browser from holding an unneeded session cookie. Cookie deletion does not replace server invalidation.
- <code>logoutSuccessUrl("/login?logout")</code> redirects on success; it does **not** imply the user is still authenticated.
- There is no <code>csrf().disable()</code>. Spring Security by default requires a CSRF token on POST, including login and logout.
- <code>permitAll()</code> allows access to required logout/success URLs, without granting anonymous access to <code>/private</code>.
- <code>PasswordEncoderFactories.createDelegatingPasswordEncoder()</code> creates password hashes with an algorithm prefix, suitable for demo UserDetails.

In real products, use accounts/credentials from an identity management source, configure HTTPS, appropriate Secure/HttpOnly/SameSite cookies, session timeouts, auditing, and authorization checks on business resources.

## 7. Testing with MockMvc: Logout Must Destroy the Session

Create <code>src/test/java/com/example/logoutdemo/LogoutSessionTest.java</code>:

~~~java
package com.example.logoutdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LogoutSessionTest {

    @Autowired
    MockMvc mvc;

    private MockHttpSession login() throws Exception {
        MvcResult result = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "local-password-1234"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) result.getRequest().getSession(false);
        assertThat(session).isNotNull();
        return session;
    }

    @Test
    void logoutInvalidatesSessionAndRequiresNewAuthentication()
            throws Exception {
        MockHttpSession session = login();

        mvc.perform(get("/me").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));

        mvc.perform(post("/logout")
                .session(session)
                .with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?logout"));

        // The HttpSession holding Authentication has been invalidated.
        assertThat(session.isInvalid()).isTrue();

        // A new request without an authenticated session must go back to login.
        mvc.perform(get("/private"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void logoutWithoutCsrfDoesNotDestroySession() throws Exception {
        MockHttpSession session = login();

        mvc.perform(post("/logout").session(session))
            .andExpect(status().isForbidden());

        assertThat(session.isInvalid()).isFalse();

        mvc.perform(get("/me").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
    }

    @Test
    void logoutOneBrowserDoesNotLogoutOtherBrowser() throws Exception {
        MockHttpSession browserA = login();
        MockHttpSession browserB = login();

        assertThat(browserA.getId()).isNotEqualTo(browserB.getId());

        mvc.perform(post("/logout")
                .session(browserA)
                .with(csrf()))
            .andExpect(redirectedUrl("/login?logout"));

        assertThat(browserA.isInvalid()).isTrue();
        assertThat(browserB.isInvalid()).isFalse();

        mvc.perform(get("/me").session(browserB))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
    }

    @Test
    void anonymousAccessRemainsPublicOnly() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));

        mvc.perform(get("/private"))
            .andExpect(status().is3xxRedirection());
    }
}
~~~

Run <code>mvn test</code>. The test suite should verify **three distinct things**:

1. Logout with an authenticated session and valid CSRF returns a successful redirect while <code>MockHttpSession.isInvalid()</code> becomes true.
2. Logout missing CSRF is rejected and the session is **not** destroyed. Checking only status 403 without checking the session would miss handlers running in the wrong order.
3. Logging out in browser A does not automatically log out browser B: this is a **current-session logout** policy, not “logout everywhere.”

The final test checks public/protected paths. The <code>get("/private")</code> call after logout creates a new request without attaching the old session; it illustrates requiring re-login, whereas <code>isInvalid()</code> is the direct proof in MockMvc that session A was destroyed.

**Limitations:** MockMvc does not fully simulate cookie Path/Domain, timeouts, and lifecycle events of a real Servlet container. To fully verify Set-Cookie and that an old JSESSIONID cannot be reused over the network, add integration tests on an embedded server or staging with two cookie jars. The Java code above is presented as a runnable example, though exact results must still be confirmed via <code>mvn test</code> in your project environment.

## 8. Manual Testing with a Browser and Cookie Jar

Start the app:

~~~bash
mvn spring-boot:run
~~~

Visit <code>http://localhost:8080/login</code>, log in with <code>alice</code> / <code>local-password-1234</code>, then open <code>/me</code> to see <code>alice</code>. Logging out via the form issues a POST request to <code>/logout</code> with a valid CSRF token. The server redirects to <code>/login?logout</code>. When revisiting <code>/me</code>, the browser must log in again.

**Do not test standard logout using GET expecting the same effect as POST.** With CSRF enabled, GET may show a logout confirmation page, whereas session-destroying logout must be sent via a valid request matching the configured matcher.

For example, with curl on Linux/macOS: testing login and logout requires keeping a cookie jar **and** passing the CSRF token generated by the server for the browser/form. A bare POST logout carrying the cookie **without a CSRF token** will typically return 403. That is the intended defense, not an unexpected LogoutFilter bug.

If testing manually on Windows PowerShell, use <code>curl.exe</code> to avoid PowerShell's alias. Never log or share raw JSESSIONID or CSRF tokens collected from real applications.

### Before/After Result Comparison

| Action | Result in the demo |
| --- | --- |
| GET /public when anonymous | 200, body <code>public</code> |
| GET /me when anonymous | Redirect to login |
| Valid POST /login with CSRF | Authentication succeeds, session created |
| GET /me with logged-in session | 200, body <code>alice</code> |
| POST /logout without CSRF | 403, session remains usable |
| POST /logout with valid CSRF | Redirect <code>/login?logout</code> and invalidate session |
| GET /me after logout with no valid session | Redirect to login |
| Browser B still holds its own session | Remains authenticated unless another revocation policy exists |

Do not infer “the session was destroyed” solely from a 302 response because redirects can stem from multiple paths. Verify session validity, SecurityContext, and subsequent requests together.

## 9. Why Should You Not Just Call `HttpSession.invalidate()`?

Sometimes developers write:

~~~java
HttpSession session = request.getSession(false);
if (session != null) {
    session.invalidate();
}
return "redirect:/login";
~~~

This is only a logic snippet, not a complete endpoint. It may invalidate the session, yet **does not proactively clear the current request's SecurityContext**. For instance, a service invoked later in the same request might still see Authentication if the strategy has not been cleared, and other logout handlers such as remember-me cleanup do not run.

Another mistake is:

~~~java
SecurityContextHolder.clearContext();
// Does not invalidate HttpSession, does not update the repository storing the context.
~~~

When the next request restores SecurityContext from the session store, the user may be treated as authenticated again. Similarly:

~~~java
response.sendRedirect("/login");
// Only changes the UI location; does not destroy authentication state.
~~~

Key differences:
- Invalidating HttpSession destroys the current server-side session, yet still requires appropriate context/handler cleanup.
- Clearing SecurityContext removes authentication from current processing, yet does not necessarily invalidate the copy stored in the session.
- Redirecting or deleting cookies only alters the client response and does not by itself prove server state is invalid.

Use <code>SecurityContextLogoutHandler</code> (via the built-in LogoutFilter whenever possible) so core responsibilities execute consistently.

## 10. `LogoutFilter`, `LogoutHandler`, and `LogoutSuccessHandler`

Put the three component types in their right roles:

~~~text
LogoutFilter: recognizes valid logout requests
    |
    +--> LogoutHandler #1: SecurityContextLogoutHandler
    |         invalidate session + clear context
    |
    +--> LogoutHandler #2: CookieClearingLogoutHandler (if configured)
    |         Set-Cookie / Max-Age=0 for cookies to clear
    |
    +--> LogoutHandler #3: remember-me/token cleanup (if configured)
    |         revoke additional credential types
    |
    '--> LogoutSuccessHandler
              redirect /login?logout or return JSON/204
~~~

Handlers do not necessarily always run in one fixed visual order; the framework and configuration determine the exact chain. What matters is that **logout handlers perform side effects**, while the success handler dictates the response.

If auditing is needed:
- Use a dedicated <code>LogoutHandler</code> injected into logout configuration, logging minimal data such as account ID, event type, and timestamp.
- Do not log raw session IDs, access tokens, passwords, or cookies.
- With external audit services, separate event delivery success from server logout completion; design proper queues/retries if durable auditing is required.
- If the logout protocol must invalidate refresh tokens or an IdP session, add dedicated logic and test the exact execution order.

Do not let an exception in a custom handler make the system return “logout failed” while part of the session was already invalidated and other credentials remain live, unless compensation or clear semantics exist.

## 11. `HttpSessionEventPublisher` and `SessionRegistry` After Logout

If the app uses <code>SessionRegistry</code> / <code>SessionRegistryImpl</code> to manage concurrent sessions, <code>HttpSessionEventPublisher</code> is normally registered to forward Servlet container session-destroyed events to Spring Security.

~~~text
Valid POST /logout
       |
SecurityContextLogoutHandler
       |
HttpSession.invalidate()
       |
Servlet container fires sessionDestroyed
       |
HttpSessionEventPublisher -> HttpSessionDestroyedEvent
       |
SessionRegistryImpl removes session ID record
~~~

This prevents the registry from continuing to count a logged-out session as active. Without the listener, stale entries can remain in the registry and cause a <code>maximumSessions(...).maxSessionsPreventsLogin(true)</code> policy to block subsequent logins.

Example listener registration in Spring Boot:

~~~java
@Bean
ServletListenerRegistrationBean<HttpSessionEventPublisher> sessionEvents() {
    return new ServletListenerRegistrationBean<>(
        new HttpSessionEventPublisher());
}
~~~

This is a **configuration snippet** requiring proper imports and bean setup; the section 6 demo does not enable concurrency so it does not need the listener solely for basic logout. Do not register the publisher twice via multiple mechanisms.

**Do not confuse <code>SessionInformation.expireNow()</code> with HttpSession.invalidate().** <code>expireNow()</code> marks a session in the registry as expired; the next request needs to pass through <code>ConcurrentSessionFilter</code> to be handled. Invalidating HttpSession directly renders the session invalid in the store, whereas merely removing a registry record does not have the same effect.

## 12. Logging Out One Session vs. Logging Out All Devices

Suppose a user has browsers A and B, both logged in with the same username:

~~~text
Account alice
  Session A = JSESSIONID:A1
  Session B = JSESSIONID:B2

A sends POST /logout:
  - HttpSession A invalidated
  - SecurityContext A cleared
  - B still holds a valid HttpSession B
~~~

Spring Security's default logout processes the **current request/session** and does not automatically scan all sessions of a user. To “log out all devices,” you need to:
- Identify the server-verified principal.
- Locate all sessions bound to that principal via a properly indexed registry/session store.
- Revoke or invalidate those sessions according to desired semantics.
- Concurrently handle remember-me tokens, refresh tokens, or other connections if the app uses them.
- Test with two browsers, multiple nodes, and concurrent login/logout.

<code>SessionRegistryImpl</code> is in-memory for a single JVM; in multi-replica systems, it is unaware of sessions on other nodes. Spring Session Redis/JDBC can provide a shared session store; however, adding a shared session store while keeping an in-memory registry **does not automatically create** cluster-wide logout everywhere. You must configure the corresponding registry/concurrency/revocation setup.

A stronger revocation approach uses a <code>securityVersion</code> or <code>credentialsChangedAt</code> stored per account and checked on later requests to reject old sessions even if a node missed a revocation event. Cache freshness, transactions, and failure handling must be defined.

## 13. Remember-me, HTTP Basic, JWT, and SSO Change What “Log Out” Means

Not every system authenticates using HttpSession.

| Mechanism | What must logout do? | Common misconception |
| --- | --- | --- |
| Form login + HttpSession | Invalidate session, clear SecurityContext, handle cookies | Deleting the browser cookie is insufficient if the server session remains alive. |
| Remember-me | Delete remember-me cookie/token, potentially revoke persistent token on server | Deleting only JSESSIONID may let the browser auto-login again. |
| HTTP Basic | Later requests may keep automatically sending Authorization header | Invalidating HttpSession does not stop browsers from resending credentials. |
| Bearer JWT API | Signed tokens can stay valid until expiry or explicit revocation by design | Clearing SecurityContext on one request does not invalidate client tokens. |
| OAuth2 refresh token | Revoke refresh token/grant or use Authorization Server mechanism | Local logout does not automatically revoke refresh tokens at the issuing server. |
| OIDC / SSO | Local logout plus IdP logout flow if required | Closing the local session does not mean the SSO session at the IdP ended. |
| WebSocket / long-lived connections | May need to close connections or re-verify permissions per message | HTTP logout does not always close open connections automatically. |

### HTTP Basic

A browser or client may automatically keep sending <code>Authorization: Basic ...</code> on new requests. Spring Security then re-authenticates on each matching request, so logging out the current session **does not guarantee the user will be prompted for a password again**. To end credential validity, you need a corresponding account/credential policy; you cannot promise “log out all Basic requests” using <code>clearContext</code>.

### JWT

JWT access tokens are typically verified independently of HttpSession. If a token has not expired and the server performs no revocation check, it will still be accepted even if a previous request called clearContext. Depending on architecture, you can use short TTLs, denylists, introspection, token versions, or refresh-token revocation. Always verify signature, issuer, audience, and timestamps before trusting a token.

### OIDC / SSO

An application can log out cleanly from Spring Security while the session at the Identity Provider persists. To log out in both places, consider RP-initiated logout, front-channel/back-channel logout, or equivalent mechanisms supported by the IdP. That is a separate protocol; never assume redirecting to the local login page suffices.

## 14. CSRF, Cookies, and Threats Around Logout

Logout can disrupt a user's active session; therefore, in cookie/session-based applications, Spring Security normally enforces CSRF on logout operations.

- **POST /logout + CSRF token** ensures requests originate from valid UI flows and reduces the chance of another website forcing a browser to log out.
- <code>GET /logout</code> should not perform state-destroying actions just because a user clicked a link; some setups show a confirmation page.
- <code>permitAll()</code> on the logout URL concerns authorization, not waiving CSRF checks.
- <code>HttpOnly</code> cookies reduce the risk of JavaScript reading session IDs, <code>Secure</code> restricts to HTTPS, and SameSite helps mitigate cross-site sending; they **do not replace CSRF** or server-side session invalidation.
- If the frontend is on a different origin, CORS is not authorization. Configure origins/credentials and CSRF mechanisms per your architecture.
- Browsers may cache HTML containing sensitive data after logout; use appropriate cache headers and avoid putting secrets in unprotected client-side storage.

Avoid logging <code>JSESSIONID</code>, cookies, CSRF tokens, or access tokens in request logs. A session ID is a secret sufficient to hijack a session as long as the server considers it valid.

## 15. Common Mistakes

| Mistake | Why it is wrong | Fix |
| --- | --- | --- |
| Only redirecting to /login | Does not destroy Authentication/HttpSession | Use LogoutFilter + SecurityContextLogoutHandler. |
| Only calling <code>SecurityContextHolder.clearContext()</code> | Old SecurityContext may still reside in session/repository | Invalidate HttpSession or save empty context per policy. |
| Only deleting the JSESSIONID cookie | Server session may still exist | Invalidate on the server; cookie deletion is only supplementary. |
| Only calling <code>request.getSession(false).invalidate()</code> | Current request context / other handlers may remain uncleaned | Use the standard logout handler. |
| Calling <code>request.getSession()</code> unnecessarily before logout | May create an unwanted new session | Use <code>getSession(false)</code> when only checking for an existing session. |
| Using GET for logout | Easily creates state-changing action without CSRF | Keep POST/CSRF and matching UI. |
| Logout test checking only 302 | Redirect does not prove the session was invalidated | Assert invalid session and that subsequent requests require login. |
| Assuming logging out A logs out B | Only destroys session A | Design dedicated global/session revocation. |
| Forgetting remember-me | Browser may auto-login again | Clean up remember-me cookies/tokens properly. |
| Treating HTTP Basic logout like session logout | Client keeps sending Authorization header | Design credential policies; don't promise Basic logout via clearContext. |
| Treating clearContext as JWT revocation | Client JWT may still be valid | Token expiry/revocation/denylist/refresh-token policy. |
| Ignoring SSO IdP session | User still has an SSO session | Integrate the IdP's logout protocol when needed. |
| Missing HttpSessionEventPublisher when using registry | Registry may retain destroyed sessions | Register the listener and test container lifecycle. |
| Custom filter failing to save/clear context properly | Authentication may reappear | Check SecurityContextRepository and explicit-save semantics. |
| Changing multiple SecurityFilterChains without testing logout URL | Requests may route through an unexpected chain | Check first-matching chain, logout matcher, and filter order. |

## 16. Testing Matrix in a Real System

| Scenario | Evidence to collect |
| --- | --- |
| Successful login | User has valid SecurityContext and private endpoints succeed. |
| Valid POST logout | Current session is invalidated; response succeeds per contract. |
| POST logout without CSRF | Rejected; previous session remains valid. |
| Browser sends old session ID after logout | Request cannot use old Authentication. |
| Two browsers logged in as same user | Logging out A does not break B under current-session policy. |
| Session timeout | Next request requires re-authentication; event cleanup works if registry exists. |
| Remember-me enabled | Logout prevents auto-login per policy and token repository. |
| App uses HTTP Basic | Clear understanding of browser Authorization resending behavior. |
| Stateless bearer JWT | Clear policy on token validity post-logout. |
| Multi-node cluster | Session invalidation/revocation takes effect consistently behind load balancer. |
| OIDC | Distinguish local logout and IdP logout; test both if product requires it. |
| Proxy / cookie Path / Domain | Cookie deletion matches set cookie; server invalidation remains source of truth. |

**Do not treat a MockMvc test as proof covering all cookie/network/cluster behavior.** MockMvc is suited for testing filter-chain behavior and MockHttpSession; verifying Set-Cookie, TLS termination, and real session stores requires an integration environment.

## 17. Self-Check Questions

**Question 1:** If you call <code>SecurityContextHolder.clearContext()</code> while keeping an HttpSession that holds SecurityContext, is the next request guaranteed to be anonymous?  
**Answer:** No. The repository may reload the old Authentication from the session; a logout handler or proper empty-context persistence/invalidation is needed.

**Question 2:** After <code>HttpSession.invalidate()</code> without yet clearing the current request's context, what must be noted?  
**Answer:** The session is destroyed, yet Authentication still exists in the current context until cleared; the full logout lifecycle and related handlers must run.

**Question 3:** Does <code>.deleteCookies("JSESSIONID")</code> replace <code>.invalidateHttpSession(true)</code>?  
**Answer:** No. Cookie deletion alters browser state; invalidation is what terminates the session on the server.

**Question 4:** Why must POST logout missing CSRF in the example return 403?  
**Answer:** Because state-changing requests in cookie/session apps require a valid CSRF token; never disable CSRF to make logout “easier.”

**Question 5:** If browser A logs out, is browser B still logged into the same account guaranteed to be invalidated?  
**Answer:** No. Default logout handles the current session. Logging out everywhere requires revoking multiple sessions and related tokens.

**Question 6:** Does a JWT bearer token lose validity simply by calling clearContext on a request?  
**Answer:** No. A JWT has an independent lifecycle and needs expiry/revocation/introspection or token versioning.

**Question 7:** An SSO user logs out of the application, but the Identity Provider still holds a session. What can happen?  
**Answer:** A subsequent visit to the app may re-authenticate through the IdP without re-entering credentials; if global logout is required, integrate the IdP's logout flow.

**Takeaway:** In a Servlet app using HttpSession, proper logout must **invalidate the server session**, **properly clear Authentication/SecurityContext**, and **respond appropriately to the client**; cookie cleanup is only supplementary. <code>LogoutFilter</code> and <code>SecurityContextLogoutHandler</code> coordinate these core actions. Logging out the current session does not mean logging out every session, remember-me, JWT, or IdP session.
