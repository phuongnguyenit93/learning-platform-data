# `defaultSuccessUrl`, `successHandler`, and Redirect Target Selection

In **Spring Security for Servlet**, when a user submits a login form and authenticates successfully, the system must decide **where to go next**. One application may want to return the user to the page they just tried to open; another may always open a dashboard, or send admins to a dedicated page. Spring Security supports these policies via `defaultSuccessUrl(...)` and `AuthenticationSuccessHandler` configured inside `formLogin(...)`.

The easiest point to misunderstand is the word **default**: `defaultSuccessUrl("/dashboard")` **does not guarantee every login goes to `/dashboard` by default**. If `RequestCache` previously saved a request requiring authentication, the default form login handler usually prioritizes returning to that URL. To force always going to one path, use the `alwaysUse` parameter or implement an appropriate custom success handler.

This lesson explains the filter flow, URL selection order, the two `defaultSuccessUrl` overloads, the relationship between `SavedRequestAwareAuthenticationSuccessHandler` and `RequestCache`, writing a `successHandler` for custom rules, redirect vs. forward differences, open-redirect prevention, and testing with `MockMvc`. Framework examples target **Java 17+, Spring Boot 3.x, and Spring Security 6.x (Servlet)**; API/behavior details can vary when customized.

## 1. Where Does "Successful Login" Happen?

A typical form login:

~~~text
GET /orders/42 (unauthenticated)
  |
  v
SecurityFilterChain -> AuthorizationFilter
  | requires valid Authentication
  v
ExceptionTranslationFilter
  | delegates to AuthenticationEntryPoint
  | RequestCache may save GET /orders/42
  v
302 -> GET /login (login page)

User enters username and password
  |
  v
POST /login + CSRF token
  |
  v
UsernamePasswordAuthenticationFilter
  |
  v
AuthenticationManager / AuthenticationProvider
  | verification succeeds
  v
SecurityContext is updated/saved per configured mechanism
  |
  v
AuthenticationSuccessHandler.onAuthenticationSuccess(...)
  |
  +-- use saved URL?      -> redirect /orders/42
  +-- use default URL?    -> redirect /dashboard
  +-- custom policy?      -> redirect /admin/home ...
~~~

`UsernamePasswordAuthenticationFilter` handles the login request at the URL the filter is configured for, typically `POST /login`. After authentication succeeds, it delegates the success response step to `AuthenticationSuccessHandler`. Target selection **is separate from** username/password checking: authentication must succeed before the success handler runs.

With default form login, Spring Security normally uses `SavedRequestAwareAuthenticationSuccessHandler`. It relies on a saved request (if present) or a **default target URL** to issue a redirect. The response is usually HTTP 302 with a `Location` header. This triggers a new browser navigation, not the server invoking the target controller inside the same request.

### Distinguishing Four Configuration Points

| Component | Responsibility | Example |
| --- | --- | --- |
| `loginPage("/login")` | URL that **displays** the credential entry page | GET /login |
| `loginProcessingUrl("/login")` | URL where the authentication filter **processes POST login** | POST /login |
| `defaultSuccessUrl("/dashboard")` | Default URL **after successful authentication** | /dashboard |
| `failureUrl("/login?error")` | URL on **authentication failure** | /login?error |

These URLs serve distinct roles even though GET and POST may share the `/login` path under default settings. `defaultSuccessUrl` does not handle failed auth, logout, or visits to resources that do not require login.

## 2. `defaultSuccessUrl(String)`: "Default" in the Literal Sense

Common lambda DSL configuration:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/", "/about").permitAll()
            .anyRequest().authenticated())
        .formLogin(form -> form
            .defaultSuccessUrl("/dashboard"));

    return http.build();
}
~~~

This is a **Spring Security configuration snippet**; it needs `@Bean`, `HttpSecurity` and `SecurityFilterChain` imports, and a Spring Security project. With the default login page, you do not need to create an HTML form yourself; Spring Security can supply `GET /login` for enabled form login.

When configuring:

~~~java
.formLogin(form -> form.defaultSuccessUrl("/dashboard"))
~~~

the `/dashboard` path is a **fallback target**:

- User opens the login page directly and logs in; no prior request was saved → usually goes to `/dashboard`.
- User tries to open protected `/orders/42` and is prompted to log in; the prior request was saved → usually returns to `/orders/42`, **not** `/dashboard`.
- If the request cache is disabled, no saved request exists, or the saved request is no longer valid → uses the default target.
- If the app replaces the success handler with a different implementation, these rules may no longer apply.

Therefore, read the method name as **"set the default URL when no higher-priority redirect target exists"**, rather than "always redirect to this URL."

### `defaultSuccessUrl(String, boolean)`

The second overload lets you change the policy:

~~~java
.formLogin(form -> form.defaultSuccessUrl("/dashboard", true))
~~~

The second parameter is `alwaysUse`. When `true`, it configures the success handler to use the default target even when a saved request existed beforehand. When `false` (the single-argument overload's behavior), the saved request can take priority. With the standard handler, forcing the default also cleans up the no-longer-needed saved request.

Table:

| Configuration | Saved request `GET /orders/42` present | No saved request |
| --- | --- | --- |
| `defaultSuccessUrl("/dashboard")` | Usually redirects to /orders/42 | Redirects to /dashboard |
| `defaultSuccessUrl("/dashboard", false)` | Usually redirects to /orders/42 | Redirects to /dashboard |
| `defaultSuccessUrl("/dashboard", true)` | Redirects to /dashboard, ignoring saved request priority | Redirects to /dashboard |
| `successHandler(custom)` | Follows custom handler logic | Follows custom handler logic |

Table results assume the user logs in **successfully**, and the default handler and `RequestCache` are active unless noted otherwise. Request caches can have custom configs, expired sessions, or multiple security chains.

### When Should You Set `alwaysUse=true`?

Suitable when a product intentionally enforces a fixed entry point: a dashboard, organization selector, mandatory onboarding page, or policy confirmation screen. However, discarding the initial URL can frustrate users who clicked a deep link to a resource and must locate it again after login.

Do not use `alwaysUse=true` as a workaround to hide request cache bugs, authorization bugs, or routing bugs. If users keep getting bounced back to login, inspect authentication/session/authorization instead of forcing a redirect.

## 3. How Does `SavedRequestAwareAuthenticationSuccessHandler` Choose a URL?

The default handler is named `SavedRequestAwareAuthenticationSuccessHandler` because it is aware of `SavedRequest`. Idealized rule to learn:

~~~text
Login succeeds
       |
       v
SavedRequest present in RequestCache?
       |
       +---- no -----> default target (usually / or configured defaultSuccessUrl)
       |
       +---- yes
               |
               v
    alwaysUseDefaultTargetUrl = true
       |                 |
       +---- yes -------> default target, discard matching saved request
       |
       +---- no --------> SavedRequest redirect URL
~~~

This is a simplified version: `SavedRequestAwareAuthenticationSuccessHandler` also supports settings inherited from `AbstractAuthenticationTargetUrlRequestHandler`, such as `targetUrlParameter`. If an app uses a target parameter, precedence depends on configuration. Never rely on this diagram to allow arbitrary client-supplied URLs unchecked.

### What Does `RequestCache` Store?

A `RequestCache` can store request details before Spring Security sends the user to authenticate. In common stateful configs, `HttpSessionRequestCache` uses the session to hold a `DefaultSavedRequest`. Data can include URL, method, parameters, and headers needed to return to the protected request.

Example:

~~~text
GET http://localhost:8080/orders/42
    |
    | unauthenticated
    v
RequestCache.saveRequest(...)
    |
    v
GET /login
    |
    v
POST /login succeeds
    |
    v
SavedRequestAwareAuthenticationSuccessHandler
    |
    v
302 Location: http://localhost:8080/orders/42
    |
    v
Browser sends GET /orders/42 with new login state
~~~

URLs above are examples; actual scheme, host, port, and context path depend on the request and deployment. The handler **does not guarantee re-executing an entire prior HTTP POST/PUT**: a browser redirect issues a new request per HTTP semantics, not a verbatim replay of the original body. Never design features that implicitly depend on replaying sensitive write operations after login.

### Who Saves the Request, and Who Uses It?

Three roles to keep separate:

1. `ExceptionTranslationFilter` can invoke `RequestCache.saveRequest(...)` before commencing authentication when authentication is needed.
2. `SavedRequestAwareAuthenticationSuccessHandler` can read the saved request to pick the post-login URL.
3. `RequestCacheAwareFilter` can help restore request attributes when navigation matches the saved request in the appropriate flow.

Having a `RequestCache` does not mean every request gets saved. Request-saving policies, matchers, HTTP methods, session state, auth failures, and security chains all influence it.

### Why Does Opening the Login Tab Directly Go to the Dashboard?

When a user visits `GET /login` directly, there is usually no prior protected resource to save. The handler finds no matching saved request and falls back to the default target. This is expected behavior, not a bug.

### Why Does the Same User Sometimes Land on Different Pages?

A session can hold a saved request from an earlier navigation. If a user opens multiple tabs requesting protected pages, the session's saved request can be overwritten, leading to non-intuitive results. Sessions can also expire or request caches can be customized. Test the flow **from the initial URL through login**, rather than testing `POST /login` in isolation.

## 4. Writing a Complete Spring Boot Configuration to Experiment

The example below uses Spring Boot 3.x, Spring Security 6.x, Java 17+, an in-memory account, and **Spring Security's default login page**. It is a demo of post-login routing, not a production account management system.

### 4.1. Maven Dependencies

In a Spring Boot project with parent/BOM and run plugin configured, add dependencies:

~~~xml
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
~~~

Use the compatible Spring Boot BOM rather than mixing in an arbitrary Spring Security version. In newer Spring Boot versions, test helper packages may evolve; verify dependencies and imports against your project version.

### 4.2. Main Class

Create `src/main/java/com/example/login/LoginRedirectApplication.java`:

~~~java
package com.example.login;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LoginRedirectApplication {
    public static void main(String[] args) {
        SpringApplication.run(LoginRedirectApplication.class, args);
    }
}
~~~

### 4.3. `SecurityFilterChain`

Create `src/main/java/com/example/login/LoginRedirectConfig.java`:

~~~java
package com.example.login;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class LoginRedirectConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-only-password"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("demo-admin-password"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/about").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .formLogin(form -> form
                .defaultSuccessUrl("/dashboard")
                .permitAll());

        return http.build();
    }
}
~~~

`formLogin(...).permitAll()` allows the URLs needed by form login per config; it does not make all app URLs public. Demo passwords are **for local testing only**; real applications must use a proper user store, password policy, encoder, and secure secret management.

If you change `defaultSuccessUrl("/dashboard")` to `defaultSuccessUrl("/dashboard", true)`, the saved-request test later must change its expectation to `/dashboard`.

### 4.4. Endpoints to Test

Create `src/main/java/com/example/login/PagesController.java`:

~~~java
package com.example.login;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PagesController {

    @GetMapping("/")
    public String home() {
        return "public home";
    }

    @GetMapping("/about")
    public String about() {
        return "about";
    }

    @GetMapping("/dashboard")
    public String dashboard() {
        return "dashboard";
    }

    @GetMapping("/orders/{id}")
    public String order(@PathVariable long id) {
        return "order " + id;
    }

    @GetMapping("/admin/home")
    public String adminHome() {
        return "admin home";
    }
}
~~~

Here the controller returns plain text only to illustrate URLs. In a real MVC app, return Thymeleaf/JSP templates or views as needed. Once the success URL is chosen, **the target must still pass authorization** on the next request; a redirect grants no extra permissions.

### 4.5. Running and Observing

After preparing a compatible Maven wrapper:

~~~bash
./mvnw spring-boot:run
~~~

Open `http://localhost:8080/login` in a browser and sign in as Alice with the demo password. If you visited login directly, you typically land on `/dashboard`. Next, clear sessions/cookies or open a private window and visit `http://localhost:8080/orders/42` before logging in; after successful login, you typically return to `/orders/42` instead of the dashboard.

**Note on using `curl`:** submitting the default form POST requires a CSRF token and matching session cookie. A plain `curl -d username=...` command is normally blocked with 403 when missing the CSRF token; that is not evidence that `defaultSuccessUrl` is broken. Use a browser, or MockMvc integration tests with `csrf()` as in section 8.

## 5. What Is `successHandler` and When Is It Needed?

`AuthenticationSuccessHandler` is the Spring Security interface for handling a successful authentication in a web flow:

~~~java
// Abbreviated signature of the Spring Security interface:
void onAuthenticationSuccess(
        HttpServletRequest request,
        HttpServletResponse response,
        Authentication authentication)
        throws IOException, ServletException;
~~~

This signature is an **illustrative excerpt**, not a standalone class. `request` and `response` are Jakarta Servlet types in Spring Security 6.x. `authentication` is the valid authentication result returned by the provider.

An implementation can:

- Pick a target URL based on role/authority or onboarding state.
- Preserve saved-request priority or intentionally discard saved requests.
- Emit an appropriate JSON response when specially required (though browser form login usually redirects).
- Record safe audit events without leaking credentials.
- Send redirects via `RedirectStrategy`.

**Relationship with `defaultSuccessUrl`:** When you register a custom `successHandler(...)`, that handler itself decides the success response. Do not assume `defaultSuccessUrl(...)` runs afterward once your custom handler finishes. If you want to combine "return to old URL if present, otherwise pick destination by role," you must write/choose a handler that actually implements that order.

### When to Use `defaultSuccessUrl`?

Prefer `defaultSuccessUrl` when you only need one default URL with either "prioritize saved request" or "always go to the chosen page." It requires less code and leverages the framework's session, cache, and redirect handling.

### When to Use `successHandler`?

Use a custom handler when your post-authentication policy **cannot be expressed as a single default URL**—such as role routing, workspace selection, onboarding branches, frontend-contract responses, or picking targets from trusted business state. Keep the handler concise, policy-clear, and unit/integration tested across every branch.

## 6. Example Handler Choosing Target by Role

Suppose the application wants:

- Users with authority `ROLE_ADMIN` → `/admin/home`.
- Other logged-in users → `/dashboard`.
- Do not prioritize saved requests under this policy (post-login destination always follows role).

This is a **different rule** from `defaultSuccessUrl("/dashboard")`. Because it ignores saved requests, the handler should remove the saved request from the cache so old URLs do not cause side effects on later steps.

### 6.1. Custom Handler

Create `src/main/java/com/example/login/RoleBasedSuccessHandler.java`:

~~~java
package com.example.login;

import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;
import java.io.IOException;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.WebAttributes;
import org.springframework.security.web.authentication.AuthenticationSuccessHandler;
import org.springframework.security.web.savedrequest.RequestCache;
import org.springframework.security.web.DefaultRedirectStrategy;
import org.springframework.security.web.RedirectStrategy;

public final class RoleBasedSuccessHandler implements AuthenticationSuccessHandler {
    private final RequestCache requestCache;
    private final RedirectStrategy redirectStrategy = new DefaultRedirectStrategy();

    public RoleBasedSuccessHandler(RequestCache requestCache) {
        this.requestCache = requestCache;
    }

    @Override
    public void onAuthenticationSuccess(
            HttpServletRequest request,
            HttpServletResponse response,
            Authentication authentication)
            throws IOException, ServletException {

        // This policy does NOT return to the saved URL.
        requestCache.removeRequest(request, response);

        // Clear any authentication exception from an earlier failed login attempt.
        HttpSession session = request.getSession(false);
        if (session != null) {
            session.removeAttribute(WebAttributes.AUTHENTICATION_EXCEPTION);
        }

        boolean admin = authentication.getAuthorities().stream()
            .anyMatch(grant -> "ROLE_ADMIN".equals(grant.getAuthority()));

        String target = admin ? "/admin/home" : "/dashboard";
        redirectStrategy.sendRedirect(request, response, target);
    }
}
~~~

This is a Spring Security Servlet class with corresponding dependencies; `DefaultRedirectStrategy` performs the HTTP redirect. Calling `RequestCache.removeRequest(...)` matches the goal of **discarding saved requests**; in an app with a custom request cache, pass **the exact same instance** configured on the security chain.

What the handler does **not** do: verify passwords itself, grant `ROLE_ADMIN`, allow access bypassing `AuthorizationFilter`, or pull redirect targets from arbitrary user-editable query parameters.

### 6.2. Wiring into `SecurityFilterChain`

In the configuration class, add these beans:

~~~java
import org.springframework.security.web.authentication.AuthenticationSuccessHandler;
import org.springframework.security.web.savedrequest.HttpSessionRequestCache;
import org.springframework.security.web.savedrequest.RequestCache;

@Bean
RequestCache requestCache() {
    return new HttpSessionRequestCache();
}

@Bean
AuthenticationSuccessHandler loginSuccessHandler(RequestCache requestCache) {
    return new RoleBasedSuccessHandler(requestCache);
}
~~~

Then **replace the method** creating the security chain in section 4, without registering duplicate beans:

~~~java
@Bean
SecurityFilterChain securityFilterChain(
        HttpSecurity http,
        AuthenticationSuccessHandler loginSuccessHandler,
        RequestCache requestCache) throws Exception {

    http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/", "/about").permitAll()
            .requestMatchers("/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated())
        .requestCache(cache -> cache.requestCache(requestCache))
        .formLogin(form -> form
            .successHandler(loginSuccessHandler)
            .permitAll());

    return http.build();
}
~~~

Imports for `HttpSecurity` and `SecurityFilterChain` are the same as section 4. This code selects a **custom handler instead of `defaultSuccessUrl`**; do not set both expecting Spring Security to merge their results automatically.

Assuming Alice has `ROLE_USER` and admin has `ROLE_ADMIN`, expected outcomes:

| Logged-in user | Saved request before login? | Target URL per handler |
| --- | --- | --- |
| alice | None | /dashboard |
| alice | `/orders/42` present | /dashboard (saved request discarded) |
| admin | None | /admin/home |
| admin | `/orders/42` present | /admin/home (saved request discarded) |

URL selection here is purely a navigation policy. A post-redirect request to `/admin/home` is still checked by `hasRole("ADMIN")`; never treat redirects as an authorization layer.

## 7. Combined Policies: Saved Request First or Branch by Role?

There are at least three valid designs:

### Policy A: Prioritize the Original Journey

If the goal is "land on the page the user wanted to open," use `SavedRequestAwareAuthenticationSuccessHandler` and `defaultSuccessUrl("/dashboard")`. Roles are still enforced at the target page; unauthorized users receive `403` or the configured denial handling. This is the simplest pattern for server-rendered apps with deep links.

### Policy B: Always Land on a Role-Appropriate Page

Use `RoleBasedSuccessHandler` as in section 6. The handler clears saved requests and picks from a **fixed path list**, avoiding confusion between client-supplied URLs and authorization. Suited for portals with separate zones or onboarding.

### Policy C: Saved Request First, Otherwise Pick by Role

This is a custom rule that must be implemented explicitly:

~~~text
Authentication succeeds
         |
         v
Valid SavedRequest eligible for priority?
         |
     +---+---+
    Yes      No
     |         |
     v         v
Redirect    Check authority / account status
saved URL        |
                 +-- admin -> /admin/home
                 +-- others -> /dashboard
~~~

In practice, to implement Policy C, you can build a handler leveraging `SavedRequestAwareAuthenticationSuccessHandler` mechanisms with a managed `RequestCache`, or write explicit selection + cleanup logic with thorough tests. **Never mutate `defaultTargetUrl` on a singleton success handler per request** to pick a user-specific URL: the handler bean is invoked concurrently across threads, so mutating a shared field can cause Alice to receive Bob's target.

If prioritizing saved requests, clarify what happens when a logged-in user **lacks permission for the saved URL**: the redirect may still point to that URL, after which authorization denies it with 403. That is usually right; handlers do not need to pre-evaluate authorization for every endpoint. If UX requires avoiding redirecting to a denied page, design a finer-grained access/target policy and test every route.

## 8. Testing with Spring Security Test and MockMvc

Testing `defaultSuccessUrl` must cover **two distinct paths**:

1. Direct login, **with no saved request**.
2. Hitting a protected page first to create a saved request, then logging in with **the same HTTP session**.

If tests only send direct `POST /login`, they cannot prove the handler restores saved requests. With HTTP forms, remember the CSRF token.

### 8.1. Integration Tests for `defaultSuccessUrl`

Requires `spring-boot-starter-test` and `spring-security-test` as in section 4. Create `src/test/java/com/example/login/LoginRedirectTest.java`:

~~~java
package com.example.login;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LoginRedirectTest {

    @Autowired MockMvc mvc;

    @Test
    void directLoginGoesToDefaultPage() throws Exception {
        MvcResult loggedIn = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "demo-only-password"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        String location = loggedIn.getResponse().getRedirectedUrl();
        assertNotNull(location);
        assertTrue(location.endsWith("/dashboard"), location);
    }

    @Test
    void savedRequestWinsWhenAlwaysUseIsFalse() throws Exception {
        MvcResult beforeLogin = mvc.perform(get("/orders/42"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
                (MockHttpSession) beforeLogin.getRequest().getSession(false);
        assertNotNull(session);

        MvcResult loggedIn = mvc.perform(post("/login")
                .session(session)
                .with(csrf())
                .param("username", "alice")
                .param("password", "demo-only-password"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        String location = loggedIn.getResponse().getRedirectedUrl();
        assertNotNull(location);
        assertTrue(location.endsWith("/orders/42"), location);
    }
}
~~~

Assertions use `endsWith` so tests are not tied to a single absolute or relative redirect URL format when a mock server changes scheme/host. **This test requires the exact `defaultSuccessUrl("/dashboard")` config from section 4**. If switched to `alwaysUse=true` or the role-based `successHandler`, update the second test to match the new policy rather than treating the difference as a framework bug.

In the test, `csrf()` supplies a valid CSRF token so the filter accepts the login POST. In a real browser, Spring Security's default generated login form embeds the token automatically; if you write a custom login page, ensure the CSRF token is submitted properly when CSRF is enabled.

### 8.2. Testing `alwaysUseDefaultTargetUrl`

Change the configuration:

~~~java
.formLogin(form -> form
    .defaultSuccessUrl("/dashboard", true)
    .permitAll());
~~~

Running the exact saved-request scenario from the second test should now redirect to `/dashboard`, even though the user previously requested `/orders/42`. Tests should also confirm the saved request does not trigger an unexpected redirect later.

### 8.3. Testing Custom `successHandler`

For section 6's custom handler, test both accounts separately:

- Alice logs in → redirect ends with `/dashboard`.
- Admin logs in → redirect ends with `/admin/home`.
- Issue a protected request before login → handler still prioritizes role and does not restore the saved request.
- After redirect, Alice accesses the admin endpoint → still denied; the handler did not alter authorities.

You can check the redirect URL via `getRedirectedUrl()` and actual authorization via a follow-up HTTP request carrying the session. These are two separate assertions.

### Why Not Use `@WithMockUser` to Test `POST /login`?

`@WithMockUser` pre-populates authentication for tests, useful when testing authorization, yet **it does not prove `UsernamePasswordAuthenticationFilter` processed credentials and invoked the success handler as expected**. When testing form login, send username/password via POST while preserving session/CSRF to cover the real config.

## 9. Standalone Java 17 Program Simulating URL Selection Order

To verify the logic without the Spring framework, the snippet below models two policies: a default handler aware of saved requests and a handler always picking targets by role. This is an **algorithmic model** — it does not implement real filters, HTTP redirects, or `RequestCache`.

Save as `SuccessTargetDecisionDemo.java`:

~~~java
public class SuccessTargetDecisionDemo {

    static String savedAware(String savedUrl, boolean alwaysDefault) {
        if (alwaysDefault || savedUrl == null) {
            return "/dashboard";
        }
        return savedUrl;
    }

    static String roleBased(boolean hasAdminRole) {
        return hasAdminRole ? "/admin/home" : "/dashboard";
    }

    public static void main(String[] args) {
        System.out.println("direct -> " + savedAware(null, false));
        System.out.println("saved -> "
                + savedAware("/orders/42", false));
        System.out.println("always -> "
                + savedAware("/orders/42", true));
        System.out.println("admin -> " + roleBased(true));
        System.out.println("user -> " + roleBased(false));
    }
}
~~~

Run with JDK 17+:

~~~bash
javac SuccessTargetDecisionDemo.java
java SuccessTargetDecisionDemo
~~~

Exact stdout:

~~~text
direct -> /dashboard
saved -> /orders/42
always -> /dashboard
admin -> /admin/home
user -> /dashboard
~~~

This illustrates **target selection rules**, not a claim that every redirect in Spring Security shares identical status codes, schemes, context paths, or session interactions.

## 10. How Do Redirect, Forward, and Response Handling Differ?

Spring Security also offers APIs like `successForwardUrl(...)` for certain scenarios, fundamentally different from `defaultSuccessUrl(...)`:

| Criterion | Post-login redirect | Post-login server-side forward |
| --- | --- | --- |
| HTTP | Browser receives 3xx/`Location` and issues a new request | Servlet container dispatches internally |
| URL shown in browser | Usually updates to target URL | Usually stays on the login POST URL |
| Method / request | New request per HTTP redirect rules | Same server-side request; original method/parameters may remain |
| Page refresh | Usually refreshes target URL | May repeat POST handling or behave unexpectedly |
| Best suited for | Normal web app navigation | Carefully designed internal cases |

For traditional form login UX, **redirect is usually better** to avoid re-submitting POSTs on refresh, produce bookmarkable URLs, and clarify request lifecycles. Do not replace redirects with forwards just to keep form data alive. In UI design, use Post/Redirect/Get where appropriate and avoid putting sensitive data into query parameters.

`failureUrl(...)` or `AuthenticationFailureHandler` is the **failed login** path, unrelated to `AuthenticationSuccessHandler`. Similarly, `logoutSuccessUrl(...)` or `LogoutSuccessHandler` handles post-logout routing, not login `defaultSuccessUrl`.

## 11. Redirect Safety: Avoiding Open Redirects and Data Leaks

Post-login target selection has security implications. A dangerous mistake is taking a URL directly from the client:

~~~java
// DO NOT DO THIS: target could be an attacker-controlled URL.
String target = request.getParameter("next");
response.sendRedirect(target);
~~~

If `next` points to an attacker's website, the app becomes an **open redirect**. Users think they are following a legitimate login flow yet land on a phishing site right after authenticating. Even when modern browsers do not send cookies to another domain, phishing redirects remain a serious risk.

### Safer Design Patterns

- Prefer **server-defined fixed paths or an allowlist**, such as `/dashboard`, `/reports`, `/profile`.
- If the UI lets users pick a section, accept a **selection key** like `reports` or `profile` and map it to a controlled path.
- Never treat the `next` query parameter as proof the user is allowed to access that URL; the target URL must still pass authorization.
- If dynamic redirects are truly required, enforce strict canonicalization/allowlist validation on scheme, host, port, context path, encoding, and path; never invent a naive regex and declare it safe.
- Never place passwords, access tokens, session IDs, or sensitive identifiers in redirect URLs; query strings can appear in browser history, logs, and referrers.
- For multi-tenant apps, derive the allowed tenant from the authenticated source; never let clients assert a tenant or external domain for unverified handler redirects.

An example safely mapping a selection key against a closed list:

~~~java
String section = request.getParameter("section");

String destination = switch (section == null ? "" : section) {
    case "reports" -> "/reports";
    case "profile" -> "/profile";
    default -> "/dashboard";
};

redirectStrategy.sendRedirect(request, response, destination);
~~~

This is an **illustrative snippet inside `AuthenticationSuccessHandler`**, assuming `request`, `response`, and `redirectStrategy` are available. Even though the URL is allowlisted, `/reports` must still have proper security rules. Handlers must never trust client-supplied roles to skip rules.

### Post-Login Redirects and Context Paths

When running under `server.servlet.context-path=/portal` or behind a reverse proxy, root-relative `/dashboard` and absolute redirect URLs can behave differently. Check `RedirectStrategy` settings, trusted proxy forwarded headers, and context paths, and test in the target deployment environment. Never hardcode internal hosts or plain HTTP protocols in production redirects.

With `SavedRequest`, the original URL can include host/port captured from the HTTP request; misconfigured reverse proxies or untrusted forwarded headers can corrupt the redirect URL. Only trust forwarded headers when the proxy infrastructure is trusted and client-spoofed sources are blocked.

## 12. Cases That Make Redirect Outcomes Confusing

### 12.1. `RequestCache` Is Disabled

With `NullRequestCache` or a stateless/session policy that does not save requests, there is no saved request to prioritize. `defaultSuccessUrl("/dashboard")` then acts much like a fixed target for logins managed by the default handler. However, do not recklessly enable stateless mode for session-based form login; the app will lose its expected login persistence.

### 12.2. Multiple `SecurityFilterChain` Beans

If an API chain `securityMatcher("/api/**")` precedes a web chain, the API may use bearer/HTTP Basic while the web chain uses form login. Each request runs through **the first matching `SecurityFilterChain`**; not every 401/302 comes from the same form login success handler. Check chain order and matchers when destinations differ from expectations.

### 12.3. Expired Session or Different Session Between Requests

`HttpSessionRequestCache` normally stores saved requests in the session. If the browser fails to send the session cookie or the session expired, the subsequent login request cannot find the saved request. Re-run the scenario keeping cookies intact; do not judge the handler solely from an isolated POST lacking a session.

### 12.4. CSRF Rejected Before Authentication

If you hand-write a login form and forget the token, `CsrfFilter` can reject `POST /login` with 403. `AuthenticationSuccessHandler` **is never called**, because login did not succeed. Verify CSRF before debugging redirects.

### 12.5. Authentication Failure or Missing Permissions at Target URL

A wrong password goes through the failure handler, usually returning to `/login?error`. A valid login redirecting to a resource requiring an authority the user lacks can return 403 on the **new request**. Do not confuse post-redirect authorization denial with a login failure.

### 12.6. Custom `successHandler` Forgets to Clear Saved Request

If a custom handler intentionally ignores the saved URL without removing it from `RequestCache`, unexpected navigation or stale state can appear on subsequent requests. When overriding logic, understand `RequestCache` lifecycle and handle saved requests consistently.

### 12.7. Abusing `targetUrlParameter`

Success handlers extending `AbstractAuthenticationTargetUrlRequestHandler` can support a parameter specifying the redirect target. Enabling it and accepting unchecked URLs from requests increases open-redirect risk. Prefer server-defined targets or strict allowlists, and test malicious inputs like absolute URLs, `//host`, unusual encodings, and context-path traversal.

### 12.8. Customizing `successHandler` While Expecting `defaultSuccessUrl` to Still Run

Once a custom handler picks a URL and writes the response, Spring Security does not run an extra "default redirect pass" afterward. If you need a combined policy, implement the combined logic inside your handler. Avoid mutating a singleton bean per request to swap targets by user, which leaks URLs across concurrent requests.

### Quick Lookup Table

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| After login goes to `/orders/42` instead of `/dashboard` | `SavedRequest` was prioritized | Check `RequestCache`, `alwaysUse=false` |
| Always goes to dashboard even after opening a deep link | `alwaysUse=true`, custom handler, or empty cache | Check handler config, session, and request-saving matchers |
| Valid login still returns 403 | Target URL lacks authority or POST login blocked by CSRF | Distinguish 403 before vs. after authentication |
| No redirect after `POST /login` | Wrong `loginProcessingUrl`, auth failure, or handler sends different response | Inspect status/`Location` and filter processing |
| User occasionally lands on another tab's URL | `SavedRequest` overwritten in shared session | Test multi-tab behavior, define cache policy |
| Redirects to wrong host/scheme | Misconfigured proxy/context path/forwarded headers | Inspect reverse proxy and `RedirectStrategy` |
| Valid login produces empty or wrong post-login URL | Custom handler emits bad URL | Test handler and destination allowlist |
| Login succeeds then bounces back to `/login` repeatedly | Authentication/session not persisted or wrong security rule on `/login` | Inspect session cookie, context repository, `permitAll`, and redirect loop |
| Open redirect via `next` parameter | Client-supplied URL unvalidated | Replace with server-defined destination mapping |

## 13. Practice Exercises

**Exercise 1.** Alice visits `/orders/42` while unauthenticated, Spring Security saves the request, Alice logs in successfully, and config has `defaultSuccessUrl("/dashboard")`. Which target is typically chosen?

**Answer:** `/orders/42` takes priority because the default handler recognizes the saved request. Only when no eligible saved request exists does it use `/dashboard`.

**Exercise 2.** Same scenario, but configured as `defaultSuccessUrl("/dashboard", true)`. Which target?

**Answer:** `/dashboard`, even though a saved request existed before login. The "always use default" policy overrides saved-request priority.

**Exercise 3.** An app uses `successHandler(roleHandler)` picking URLs by `ROLE_ADMIN`. Can you still expect `defaultSuccessUrl("/dashboard")` to run automatically once the handler finishes?

**Answer:** No. The custom handler owns the response; if default fallback behavior is desired, the handler itself must implement or delegate to it.

**Exercise 4.** A user logs in successfully and is redirected to `/admin/home`, yet only holds `ROLE_USER`. Does the success handler have an authentication bug?

**Answer:** Not necessarily. The success handler only chooses a URL; the follow-up request still passes through authorization and can be denied with 403. Choose sensible targets, yet never replace security rules with target selection.

**Exercise 5.** A user passes `next=https://untrusted.example/phishing` in the login POST; the handler calls `sendRedirect(next)` directly. What is the risk?

**Answer:** Open redirect and phishing. Never trust arbitrary client URLs; use selection keys/allowlists or strict URL validation, and never put tokens/credentials in URLs.

**Exercise 6.** A MockMvc test sends `POST /login` without CSRF and gets 403 instead of a redirect. Should `defaultSuccessUrl` be changed?

**Answer:** No. When CSRF is enabled, login requests must carry a valid CSRF token; with Spring Security Test use `with(csrf())` or the proper form login test builder. When POST is blocked, the success handler never ran.

**Exercise 7.** A form login app deployed at `/portal` redirects to `/dashboard` on the root domain instead of `/portal/dashboard`. What should be checked?

**Answer:** Context path, `RedirectStrategy` configuration, forwarded headers from reverse proxies, and relative/absolute URL handling. Test against the real deployment URL without hardcoding internal hosts.

**Exercise 8.** A user opens two tabs: tab A requests `/orders/42`, tab B requests `/profile`, then the user logs in on tab A. Is `/orders/42` guaranteed?

**Answer:** No. Saved requests may be stored per session, and tab B overwrote the prioritized entry. If UX requires preserving journeys per tab, design suitable per-tab request caching/navigation while keeping targets within an allowlist.

## 14. Design and Verification Checklist

- Identify the **login mechanism**: genuine form login vs. Basic/Bearer/OAuth2; never mix handlers across mechanisms.
- Clarify what `loginPage`, `loginProcessingUrl`, `failureUrl`, and `defaultSuccessUrl` each handle.
- Explicitly choose a policy: **saved request priority**, **always default**, or **custom role/business handler**.
- When using `defaultSuccessUrl(..., true)`, review deep-link UX and saved-request cleanup.
- When using `successHandler(...)`, ensure the handler completely handles redirects, session state, and saved-request cleanup.
- Never mutate a shared singleton handler per request to swap targets.
- Choose redirect destinations from trusted sources; never redirect to arbitrary request URLs without an allowlist.
- Always protect target endpoints with authorization; redirects are not access permissions.
- Test **direct login**, **login after protected GET**, **with/without saved request**, **admin/user**, **CSRF**, **wrong login**, and **sessions**.
- With proxies/context paths, verify the `Location` header in the deployment environment.
- Avoid putting secrets/tokens in query strings or redirect logs.

**Conclusion:** `defaultSuccessUrl("/dashboard")` is a **fallback destination**, because `SavedRequestAwareAuthenticationSuccessHandler` normally prioritizes previously saved requests; the `defaultSuccessUrl("/dashboard", true)` overload forces a fixed target. When routing depends on roles or business state, `successHandler(...)` hands response control to application code. Good design aligns **URL precedence, session/request cache, authorization, and redirect safety**, tested end-to-end from protected requests through login POST.