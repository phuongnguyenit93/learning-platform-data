# RequestCache, SavedRequest, and Restoring Requests After Login (Spring Security Servlet)

## 1. The Problem: Where Was the User Going Before Logging In?

Suppose an unauthenticated user opens a protected path:

```text
GET /private/report?tab=history
```

The application uses Spring Security Servlet and form login. Rather than losing where the user intended to go, the system can remember the initial request, send them to the login page, and **after successful authentication** redirect the browser back to the requested URL.

Three core concepts:

- **`RequestCache`** is the interface defining how to save, retrieve, match, and remove remembered requests.
- **`SavedRequest`** is a stored description of an HTTP request (typically including the original URL and certain necessary request attributes); it is not a clone capable of re-executing every HTTP operation.
- **Post-login restoration** in form login normally means **redirecting the browser to the saved URL**, after which the browser issues a new HTTP request; it does not mean the server replays the old request with its body, method, and side effects intact.

In the default processing path, `HttpSessionRequestCache` stores `SavedRequest` in `HttpSession`, `ExceptionTranslationFilter` participates in saving the request when authentication is required, and `SavedRequestAwareAuthenticationSuccessHandler` usually chooses the saved URL as the redirect destination after successful authentication.

**Scope:** this is the Spring Security **Servlet** flow with **form login and sessions**. Stateless APIs, HTTP Basic, or JWT flows do not necessarily use redirects/saved requests the same way.

## 2. Distinguishing Components and Responsibilities

| Component | What is it? | Role in the flow |
| --- | --- | --- |
| `RequestCache` | Interface | Saves requests, retrieves saved requests, gets matching requests, and removes them when appropriate. |
| `HttpSessionRequestCache` | `RequestCache` implementation | Typically stores `SavedRequest` in `HttpSession`. |
| `SavedRequest` | Interface | Represents information of the remembered request; exposes `getRedirectUrl()`. |
| `DefaultSavedRequest` | Common implementation | Holds details about the original request to support redirects and certain restoration operations. |
| `ExceptionTranslationFilter` | Security filter | On a security exception requiring authentication, can use `RequestCache` to save the request then trigger `AuthenticationEntryPoint`. |
| `LoginUrlAuthenticationEntryPoint` | Authentication entry point for form login | Redirects to the login page, e.g., `/login`. |
| `UsernamePasswordAuthenticationFilter` | Authentication filter | Processes POST login per configuration; authenticates username/password. |
| `SavedRequestAwareAuthenticationSuccessHandler` | Success handler | After successful login, prioritizes the saved request URL unless overridden by configuration options. |
| `RequestCacheAwareFilter` | Security filter | Queries `RequestCache` for a matching request and can wrap the request with saved attributes. |
| `SecurityContextRepository` | Context persistence interface | Persists `SecurityContext` upon login; a **separate** responsibility from saving the pre-login URL. |

The saved path and login state are stored **for two different purposes**:

- `SecurityContext` / `Authentication` answers "whose new request is this?".
- `SavedRequest` answers "before being prompted to log in, which resource did the browser want to open?".

Having a `SavedRequest` does not mean the user is authenticated. Having a valid `SecurityContext` also does not guarantee there is still a URL to redirect to.

## 3. Complete Flow: From Intercepted GET to Post-Login GET

A common progression:

```text
[1] Browser: GET /private/report?tab=history
             |
             v
    Spring Security filters
             |
     request requires authenticated
             |
             v
    ExceptionTranslationFilter
       | 
       +-- RequestCache.saveRequest(request, response)
       |     -> SavedRequest saved per cache policy
       |        (usually HttpSessionRequestCache)
       |
       +-- LoginUrlAuthenticationEntryPoint
                 -> HTTP 302 Location: /login

[2] Browser: GET /login
             |
             v
    Login page (default generated or custom page)

[3] Browser: POST /login
             | username/password + appropriate CSRF token
             v
    Authentication filter + AuthenticationManager
             |
         authentication succeeds
             |
             v
    Save Authentication/SecurityContext per policy
             |
             v
    SavedRequestAwareAuthenticationSuccessHandler
       |
       +-- RequestCache.getRequest(...)
       |       -> read SavedRequest if present
       |
       +-- HTTP 302 Location: /private/report?tab=history

[4] Browser: GET /private/report?tab=history
             |
             v
    Security filters restore Authentication from session
             |
    authorize new request
             |
             v
    Controller returns content, if request is permitted
```

The diagram shows the conceptual flow; exact ordering of other filters, session creation, query parameters used for request-cache optimization, and response decisions may vary by version/configuration.

Points to watch:

1. The original request is blocked **before controller execution** in the normal flow. The controller does not remember the URL itself.
2. Session/cookies must survive across the redirect to login and the redirect back. If cookies/session are lost, the server may be unable to locate the saved request.
3. If form login succeeds yet the user still lacks permission for the original URL, they can still receive HTTP 403; a saved request grants no extra privileges.
4. The handler redirect only instructs the browser. **The HTTP GET in step [4] is a brand-new request** and still passes through security filters.
5. When login fails, the success handler branch does not run; normally the user returns to the login page with an error message rather than going to the saved URL.

## 4. `RequestCache` Contract and Key Operations

Spring Security Servlet provides `org.springframework.security.web.savedrequest.RequestCache`, with core operations:

```java
// Conceptual method signatures of RequestCache; not a standalone runnable class.
void saveRequest(HttpServletRequest request, HttpServletResponse response);

SavedRequest getRequest(
    HttpServletRequest request,
    HttpServletResponse response
);

HttpServletRequest getMatchingRequest(
    HttpServletRequest request,
    HttpServletResponse response
);

void removeRequest(
    HttpServletRequest request,
    HttpServletResponse response
);
```

These methods represent the contract to understand rather than copying into a competing interface definition alongside Spring Security.

### 4.1. `saveRequest`: Remembering Eligible Requests

`saveRequest` is called when Spring Security needs to remember an interrupted request to initiate authentication. With `HttpSessionRequestCache`, details are normally placed in the session as a `SavedRequest`.

Not every request is saved: which chain handles it, the cache's matcher, session policy, and exception translation branch decide. An ordinary public GET does not need to be saved merely because it ran before login.

### 4.2. `getRequest`: Reading the Saved Request If Present

`getRequest` retrieves the `SavedRequest` for the current request/response and store. This is what `SavedRequestAwareAuthenticationSuccessHandler` uses to find the redirect URL.

Calling `getRequest` **does not mean** the browser is resending the original request. It simply reads stored information.

### 4.3. `getMatchingRequest`: Finding a *New* Request Matching the Saved Request

After the browser is redirected back to the old URL, `RequestCacheAwareFilter` can call `getMatchingRequest`. If the new request satisfies matching criteria, the repository may return a wrapped `HttpServletRequest` exposing selected saved details from `SavedRequest`, while handling/removing the cache entry per implementation.

In Spring Security 6 configurations, saved-request lookups can be optimized using a request identifier parameter (such as `continue`, depending on config). Therefore, **do not assume** `getMatchingRequest` always reads the session on every request, or that matching URLs alone make every implementation return a wrapper.

### 4.4. `removeRequest`: Clearing Unused Saved Requests

`removeRequest` deletes remembered info per the cache's semantics. This is useful when an application intentionally sends users elsewhere, cancels a flow, or wants to avoid reusing an old URL later.

**Calling `getRequest` does not immediately delete the entry.** Across a redirect flow, handlers may need the saved request to remain available for the next request; removal can happen at different points depending on handler and cache.

## 5. What Does `SavedRequest` Keep and Not Keep?

`SavedRequest` exposes `getRedirectUrl()` to direct the browser to the right URL; `DefaultSavedRequest` can also retain attributes like path, scheme, host/port, query, method, headers, parameters, locale, or cookies depending on implementation. Do not rely on an immutable fixed list without checking your version.

Example:

```text
Original:
  method: GET
  URL:    https://app.example.test/private/report?tab=history
  Accept: text/html
  Cookie: session=...

SavedRequest:
  redirect target ~= https://app.example.test/private/report?tab=history
  + metadata supporting matching/wrapping per implementation
```

Do not confuse stored metadata with data that can be **safely replayed**. Things you should not automatically expect to be restored intact:

- Single-stream request bodies (multipart uploads, large JSON payloads, form POSTs with side effects).
- Any server-side controller state or mid-flight database transaction.
- Authorization of the newly logged-in user: permissions are re-evaluated on the new request.
- Original POST outcomes, independent request CSRF tokens, or HTTP side effects.
- Every header generated by proxies/browsers on the initial request.

**`RequestCache` is not a transaction replay mechanism.** If a product needs to restore carts, drafts, or multi-step workflows after login, persist business data safely in an appropriate store; use saved requests strictly to assist navigation.

## 6. Redirecting Back to a URL Differs from Replaying an HTTP Request

A commonly misunderstood scenario:

```text
Unauthenticated:
  POST /checkout/confirm
  body: shippingAddress=...&paymentSelection=...

After successful form login:
  HTTP 302 Location: /checkout/confirm
  Browser typically issues GET /checkout/confirm
```

That **does not mean** the server replays the previous POST. With a normal 302 redirect, browsers typically switch to GET; exact behavior depends on status code and client. Do not force `307` or `308` to preserve method/body across an authentication flow without analyzing transaction replay risks.

Consequences:

- If an endpoint only supports POST, the post-login GET may return 405 or an unexpected response.
- Resubmitting sensitive bodies or mutating operations can cause errors or duplicate orders.
- CSRF tokens belong to a request with their own rules; do not rely on request caching to bypass CSRF.
- For a "POST after login" flow, a safer design guides users to a GET step/page of the transaction, verifies state, and lets them explicitly submit again.

A safer architecture:

```text
GET /checkout/confirm-page
    -> if unauthenticated: save GET, redirect login
    -> after login: return to GET page, rebuild data from server
    -> user confirms
POST /checkout/confirm (CSRF + authorization + idempotency check)
    -> process once under business controls
```

Do not use `SavedRequest` to hold payment details, passwords, tokens, or highly private information. Any draft storage needed must have proper expiration, access control, size limits, and security.

## 7. `RequestCache` and Sessions: Why Cookies Matter So Much

With `HttpSessionRequestCache`, the initial request and subsequent login request must link to the same `HttpSession`. Browsers normally use a session cookie to link them.

Suppose:

```text
GET /private/report
  -> server: saves saved request into session S1
  -> browser: receives cookie identifying S1

GET /login, POST /login
  -> browser: sends back matching cookie
  -> server: finds saved request in active session
  -> success handler: redirects to /private/report
```

If cookies are blocked, domain/path mismatches occur, or the session expires/invalidates, a successful login may use the fallback target instead of the original URL.

**Session fixation protection:** Spring Security may change the session ID upon successful login. This is a security safeguard and does not inherently erase the saved request. However, tests and real systems must use the post-authentication session for subsequent requests rather than relying on a hardcoded session identifier.

When running across multiple nodes, sessions need a suitable sharing/routing strategy; `RequestCache` alone does not guarantee all servers read the same session. In stateless apps, storing `SavedRequest` in an HTTP session contradicts the stateless policy.

## 8. Spring Security 6: Defaults, Request-Cache Optimization, and Alternatives

### 8.1. `HttpSessionRequestCache`

`HttpSessionRequestCache` fits session-based form login where redirecting back to the pre-auth requested URL is desired. In standard Spring Security Servlet configs, the framework can provide it by default.

In Spring Security 6, saved-request matching is optimized to reduce unnecessary session lookups. Some configurations use an identifying parameter such as `continue`. Exact parameter names and behavior must be verified against your version/config; **do not hardcode this parameter into every link** or manually rewrite saved URL queries without understanding request cache internals.

If special matching logic or optimization is needed, `HttpSessionRequestCache` can be configured explicitly; test the full redirect flow thoroughly on your target version.

### 8.2. `NullRequestCache`

`NullRequestCache` does not remember requests for session-based restoration. It is often a good fit for stateless REST APIs:

```java
// Configuration snippet inside a SecurityFilterChain bean, not standalone.
http.requestCache(cache -> cache.requestCache(new NullRequestCache()));
```

Requires importing `org.springframework.security.web.savedrequest.NullRequestCache` with `http` as the configured `HttpSecurity`.

However, **`NullRequestCache` alone does not make an entire application stateless**; you must also configure session management, security context, authentication entry point, and other filters. Conversely, setting `SessionCreationPolicy.STATELESS` while expecting browsers to return to session-saved URLs is usually contradictory.

### 8.3. JSON APIs and Form Login Are Different Experiences

For SPA/mobile APIs, an explicit 401 JSON response letting the client navigate to login and remember its own route is often better than HTML redirects. `RequestCache` remains a framework abstraction, yet not every API should enable request saving and redirects.

**Never treat a session saved-request as an unconditionally trusted redirect source for other clients.** If building a `returnUrl` query or header yourself, validate the target URL to prevent open redirects.

## 9. `SavedRequestAwareAuthenticationSuccessHandler`: Choosing the Post-Login Target

In default form login, a handler in the `SavedRequestAwareAuthenticationSuccessHandler` family typically handles success redirects. It can pull the URL from `RequestCache`, though configuration can change priority.

Basic decision tree:

```text
Authentication success
      |
      v
Configured "always go to default target"?
      |
      +-- Yes --> redirect to configured default URL
      |
      +-- No --> Allowed targetUrl parameter present?
                     |
                     +-- Yes --> redirect per configured policy
                     |
                     +-- No --> SavedRequest present?
                                   |
                                   +-- Yes --> redirect SavedRequest.getRedirectUrl()
                                   |
                                   +-- No --> redirect default target
```

Understand the two contrasting cases:

**Case A:** user opens `/private/report`, gets redirected to login, then logs in successfully. The saved request still exists and config does not override it ⇒ the handler typically redirects to `/private/report`.

**Case B:** user visits the login page directly and logs in with no saved request ⇒ the handler uses the default target (which may be `/` if not customized).

### 9.1. Customizing `defaultSuccessUrl`

Example:

```java
// A separate option for form login:
http.formLogin(form -> form
    .defaultSuccessUrl("/dashboard", true)
);
```

`true` here instructs it to **always use the default success URL**, thus **skipping the `SavedRequest` URL as destination**. If returning to the original location is the goal, do not accidentally configure "always use default target."

With `false` or the corresponding default, the handler can still prioritize the saved request when present. The above applies to standard form-login success handler rules, not when an app replaces it with a custom success handler.

### 9.2. Custom `AuthenticationSuccessHandler`

When replacing the success handler with a lambda writing a JSON response, the default handler's saved-request redirect logic **no longer runs**. To preserve restoration behavior, actively integrate `RequestCache` or delegate to an appropriate handler.

Never read `SavedRequest.getRedirectUrl()` and redirect to arbitrary hosts without verifying host/context path. Check reverse-proxy headers and trusted proxy settings to prevent Host header poisoning or open redirects in real deployments.

## 10. Runnable Spring Boot 3/Java 17 Example: Intercepted GET, Login, and Return to Original URL

The example uses **Spring Boot 3.3.5 + Spring Security Servlet + Maven + Java 17**. The goal is to declare an explicit `HttpSessionRequestCache`, a protected route, standard form login, and tests verifying saving/reading `SavedRequest`.

### 10.1. Project Structure

```text
saved-request-demo/
  pom.xml
  src/
    main/java/demo/savedrequest/
      SavedRequestDemoApplication.java
      SecurityConfig.java
      PageController.java
    test/java/demo/savedrequest/
      SavedRequestFlowTest.java
```

### 10.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>saved-request-demo</artifactId>
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
```

### 10.3. Bootstrap Class

`src/main/java/demo/savedrequest/SavedRequestDemoApplication.java`:

```java
package demo.savedrequest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SavedRequestDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SavedRequestDemoApplication.class, args);
    }
}
```

### 10.4. `SecurityConfig`

`src/main/java/demo/savedrequest/SecurityConfig.java`:

```java
package demo.savedrequest;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.savedrequest.HttpSessionRequestCache;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("lan")
            .password(encoder.encode("demo-password"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(learner);
    }

    @Bean
    HttpSessionRequestCache requestCache() {
        return new HttpSessionRequestCache();
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            HttpSessionRequestCache cache) throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public").permitAll()
                .anyRequest().authenticated())
            .requestCache(config -> config.requestCache(cache))
            .formLogin(form -> form.permitAll());

        return http.build();
    }
}
```

Explanation:

1. `HttpSessionRequestCache` is registered explicitly so tests can inspect the saved request via the same bean instance.
2. `authorizeHttpRequests` requires login for `/private/report`; `/` and `/public` allow anonymous access.
3. `formLogin(form -> form.permitAll())` enables form login and allows access to login endpoints; no `POST /login` controller is needed.
4. `BCryptPasswordEncoder` hashes the demo password when creating the user. This is a learning account, not how production accounts are provisioned.
5. Neither `defaultSuccessUrl("/dashboard", true)` nor a custom success handler is set, allowing us to observe saved-request behavior.
6. The example relies on sessions; `SessionCreationPolicy.STATELESS` is not configured alongside it.

### 10.5. Controller

`src/main/java/demo/savedrequest/PageController.java`:

```java
package demo.savedrequest;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PageController {

    @GetMapping("/")
    String home() {
        return "home";
    }

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/private/report")
    String report(Authentication authentication,
                  @RequestParam(defaultValue = "overview") String tab) {
        return "report:" + authentication.getName() + ":" + tab;
    }
}
```

`@RestController` simplifies response bodies for verifying the flow; default form login still provides Spring Security's generated HTML login page.

### 10.6. MockMvc: Proving Request Saving and Redirect Back to Original URL

`src/test/java/demo/savedrequest/SavedRequestFlowTest.java`:

```java
package demo.savedrequest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.web.savedrequest.HttpSessionRequestCache;
import org.springframework.security.web.savedrequest.SavedRequest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SavedRequestFlowTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    HttpSessionRequestCache requestCache;

    @Test
    void protectedUrlIsSavedAndRestoredAfterFormLogin()
            throws Exception {

        MvcResult first = mvc.perform(
                get("/private/report?tab=history"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        String loginRedirect = first.getResponse().getRedirectedUrl();
        assertNotNull(loginRedirect);
        assertTrue(loginRedirect.contains("/login"));

        SavedRequest saved = requestCache.getRequest(
            first.getRequest(), first.getResponse()
        );
        assertNotNull(saved);
        assertTrue(saved.getRedirectUrl()
            .contains("/private/report?tab=history"));

        MockHttpSession beforeLogin =
            (MockHttpSession) first.getRequest().getSession(false);
        assertNotNull(beforeLogin);

        MvcResult loggedIn = mvc.perform(post("/login")
                .session(beforeLogin)
                .with(csrf())
                .param("username", "lan")
                .param("password", "demo-password"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        String target = loggedIn.getResponse().getRedirectedUrl();
        assertNotNull(target);
        assertTrue(target.contains("/private/report?tab=history"));

        // Grab post-login session so we do not depend on session fixation ID.
        MockHttpSession afterLogin =
            (MockHttpSession) loggedIn.getRequest().getSession(false);
        assertNotNull(afterLogin);

        mvc.perform(get("/private/report?tab=history")
                .session(afterLogin))
            .andExpect(status().isOk())
            .andExpect(content().string("report:lan:history"));
    }

    @Test
    void publicUrlDoesNotRequireAuthentication() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void directLoginWithoutSavedRequestUsesFallback()
            throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "lan")
                .param("password", "demo-password"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/"));
    }

    @Test
    void wrongPasswordDoesNotEnterSuccessRedirectFlow()
            throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "lan")
                .param("password", "wrong-password"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"));
    }
}
```

Notable testing points:

- The first test sends a **real GET through the MockMvc filter chain**, rather than fabricating a `SavedRequest` in test code. `requestCache.getRequest(...)` verifies the cache holds the saved URL.
- The test preserves the session between the blocked request and login. After login, it reads the active session and sends a new GET to the destination; the controller receives principal `lan`.
- Uses `.with(csrf())` to simulate a form login with a valid CSRF token per Spring Security defaults.
- Avoids hardcoding scheme/host/port in `getRedirectUrl` assertions because the URL can be absolute with `http://localhost` inside MockMvc.
- The wrong-password test checks only the failure URL branch, not conflating it with the saved-request success flow.

### 10.7. Running the Example

In the project folder with `pom.xml`, JDK 17+, and Maven installed:

```bash
mvn test
mvn spring-boot:run
```

With a valid environment and dependencies, **all 4 tests are expected to pass**. Fixed Maven stdout is omitted since timestamps, JVMs, and environments differ.

HTTP results observable in the test suite:

| Step | Expected HTTP response | Notes |
| --- | --- | --- |
| Anonymous GET `/private/report?tab=history` | 302 to login | Original URL is saved into RequestCache. |
| POST `/login` with right password and prior session | 302 to saved URL | Success handler picks saved target. |
| Follow-up GET to original URL with post-login session | 200, body `report:lan:history` | A brand-new GET request; not a replay of the prior request. |
| GET `/public` | 200, body `public` | No authentication needed. |
| POST `/login` right password without saved URL | 302 to `/` | Default target. |
| POST `/login` wrong password | 302 to `/login?error` | Failure handler, no success redirect. |

The example intentionally omits any mutating POST endpoint in the tests to avoid confusing request caching with an automatic replay tool for side-effecting POSTs.

## 11. Standalone Java 17: Simulating URL Saving and Navigation

To observe the idea of a "saved URL" without running a server, you can use a plain Java model. **This is illustrative code, not Spring Security's `RequestCache` implementation**.

Create `SavedNavigationDemo.java`:

```java
public class SavedNavigationDemo {

    record SavedRequest(String method, String url) {}

    static class Session {
        private SavedRequest saved;

        void save(String method, String url) {
            this.saved = new SavedRequest(method, url);
        }

        String redirectAfterLogin() {
            return saved == null ? "/" : saved.url();
        }

        void clear() {
            saved = null;
        }
    }

    public static void main(String[] args) {
        Session session = new Session();

        session.save("GET", "/private/report?tab=history");

        System.out.println("saved method: " + "GET");
        System.out.println("redirect: " + session.redirectAfterLogin());
        System.out.println("browser request: GET " +
            session.redirectAfterLogin());

        session.clear();
        System.out.println("after clear: " +
            session.redirectAfterLogin());
    }
}
```

Run:

```bash
javac SavedNavigationDemo.java
java SavedNavigationDemo
```

**Exact** stdout with Java 17:

```text
saved method: GET
redirect: /private/report?tab=history
browser request: GET /private/report?tab=history
after clear: /
```

This model only stores a URL and clears the entry; it has no Servlet request wrapper, session cookie, CSRF, or real authentication. It helps separate **remembering the destination** from **the browser's new HTTP request**, while section 10 proves the actual Spring Security pipeline.

## 12. Common Configuration Choices

### 12.1. Avoiding Caching Unwanted URLs

If `favicon.ico`, `/error`, or auxiliary assets require authentication and trigger request caching, the user's intended URL can be overwritten by an auxiliary asset. Usually the best fix is configuring appropriate authorization/matchers for static resources and error handling, rather than just "cleaning up saved requests" after login.

`HttpSessionRequestCache` supports a matcher to restrict which requests get saved; when setting a custom `RequestMatcher`, ensure it only retains requests meaningful to restore after login, and test directly. Do not assume all GET requests should be cached.

### 12.2. When Using Multiple `SecurityFilterChain` Beans

`FilterChainProxy` selects the first matching chain, after which that chain's request-cache and login configuration take effect. A stateless API chain and a form-login chain can use different policies; do not accidentally disable caching on the form-login chain because `NullRequestCache` was set on another chain.

Conceptual example:

```text
/api/**:
  bearer token / stateless
  NullRequestCache
  401 JSON

browser pages:
  session + formLogin
  HttpSessionRequestCache
  redirect login + redirect saved URL
```

This is an **illustrative** two-chain design, not copy-paste-ready code. You must configure `securityMatcher`, `@Order` precedence, and a fallback properly.

### 12.3. Replacing the Success Handler or Entry Point

- A custom `AuthenticationSuccessHandler` must explicitly decide whether to use the saved request.
- A custom `AuthenticationEntryPoint` returning 401 JSON instead of a redirect changes the login experience completely.
- Non-form-login authentication filters may not use `SavedRequestAwareAuthenticationSuccessHandler`.
- `RequestCache` and `SecurityContext` persistence must work within the same session model, yet they remain two independent responsibilities.

## 13. Security: Do Not Turn Saved URLs into New Vulnerabilities

### 13.1. Open Redirects and Host/Proxy Headers

Any system where redirect URLs are influenced by query params, headers, or reverse proxies must guard against redirecting to disallowed domains. `SavedRequest` is built from the request the server received, yet never assume every external header value is trustworthy.

If writing a custom success handler:

- Prefer internal relative paths whenever possible; for absolute URLs, validate scheme/host/port against an allowlist.
- Trust `Forwarded` or `X-Forwarded-*` headers only from trusted proxies, configured properly at the container/framework level.
- Never concatenate unvalidated query-parameter URLs into `sendRedirect`.
- Test with malicious inputs, encoded paths, or tampered Host headers.

### 13.2. `SavedRequest` Does Not Replace Authorization

A user may be redirected back to `/admin` after login yet still lack `ROLE_ADMIN`. On the new request, `AuthorizationFilter` still enforces protection rules. Never add a rule to "bypass authorization if the URL came from `SavedRequest`," as that opens a vulnerability.

### 13.3. Session Data, Size, and Lifetime

A saved request can hold metadata reflecting the URL and HTTP details. Control oversized requests, URLs containing sensitive data, session expiration, write frequency, and multi-tab interactions.

Never place access tokens, passwords, or sensitive personal data in query strings to "recover after login." URLs can unexpectedly surface in history, logs, and referrers.

### 13.4. State-Changing Operations

Never use post-login redirects to automatically resubmit payment POSTs, deletions, or password changes. Side-effecting operations need proper CSRF protection, authorization, validation, and separate idempotency controls. To resume unfinished work, store a safe server-side draft and reopen it with GET.

## 14. Debugging: Why Did Login Succeed Without Returning to the Old URL?

Trace step by step along the flow:

1. **Was the original request actually blocked to initiate authentication?** If the endpoint is public or another filter blocks early, `ExceptionTranslationFilter` may not save the request as expected.
2. **Did it hit the right `SecurityFilterChain`?** Check `securityMatcher` and the request cache config of the actual chain.
3. **Was it saved into `RequestCache`?** After the protected GET, inspect the session and `getRequest` via tests or breakpoints rather than guessing.
4. **Did the session/cookie survive across GET login and POST login?** Check cookie policy, session expiration, proxy, `SameSite`, HTTP/HTTPS, and session fixation.
5. **Did authentication succeed?** If login failed, the success handler does not run; distinguish `/login?error` responses.
6. **Which success handler is active?** Is it `SavedRequestAwareAuthenticationSuccessHandler` or a custom handler? Does `alwaysUseDefaultTargetUrl` or a target parameter override it?
7. **What is the final redirect URL?** Read the HTTP `Location`; never log credentials or tokens.
8. **Does the post-redirect request have the right method/path/query?** The post-redirect GET is a separate request; do not expect the old POST body.
9. **Does the user have permission for the target?** Without sufficient authorities, a successful redirect still leads to 403.
10. **Did multiple tabs or auxiliary resource requests overwrite the cache?** Inspect matcher/cache policy and concurrent flows.
11. **Is stateless/`NullRequestCache` configured?** If so, not restoring via session may be intentional by design.
12. **Are there special requirements around `getMatchingRequest`?** In Spring Security 6, request-cache optimization and matching parameters can affect post-redirect wrapper/cache handling.

In development, you can inspect logs:

```properties
logging.level.org.springframework.security=DEBUG
```

DEBUG logs reveal authentication/redirect/filter activity in many cases, though they may not print full `RequestCache` state. To verify storage/retrieval directly, use a debugger breakpoint or integration test with `HttpSessionRequestCache`. Never emit cookies, session IDs, or passwords into production logs.

### Common Error Table

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| After login always goes to `/` even after opening a specific URL | No `SavedRequest`; cache did not save; success handler overrides target | Check `saveRequest`, session, `alwaysUseDefaultTargetUrl`, and custom success handlers. |
| After login goes to `/login` or `/error` | Auxiliary URL wasn't permitted, or another request overwrote saved target | Check matchers and asset/error routes. |
| Post-login target returns 403 | Login succeeded, yet user lacks permissions | Evaluate authorization on the new request; do not skip checks. |
| Post-login target returns 405 | Original request was POST, redirect issued GET | Redesign GET/POST workflow; do not expect request replay. |
| URL lost across domain/subdomain switch | Session cookie not sent properly | Check cookie `Domain`/`Path`/`SameSite`/`Secure` and proxy config. |
| Mobile API receives 302 HTML instead of 401 JSON | Passing through form login chain / web entry point | Separate API chain and authentication entry point cleanly. |
| Redirects to an unexpected host | Unsafe custom redirect logic or trusted-proxy/Host handling | Enforce allowlist and trust only valid proxies. |
| Saved request not removed as expected | `getRequest` doesn't necessarily remove; matching optimization/config differs | Understand `getMatchingRequest` / `removeRequest` and test lifecycle. |
| Two login tabs land on the "wrong tab's" URL | Session saved request can be overwritten by competing requests | Design multi-tab UX explicitly if needed rather than assuming per-tab caches. |

## 15. Self-Check Questions

**Question 1.** An anonymous user opens `GET /private/report` and gets redirected to login. Which component normally puts the request into the cache?

**Answer:** In a typical form login flow, `ExceptionTranslationFilter` calls `RequestCache.saveRequest(...)` when commencing authentication. `HttpSessionRequestCache` stores it in the session when used.

**Question 2.** Are `SavedRequest` and `SecurityContext` the same thing?

**Answer:** No. `SavedRequest` holds pre-login request details, whereas `SecurityContext` holds the `Authentication` state identifying the user for the current and subsequent requests per policy.

**Question 3.** After successful login, does the server automatically replay `POST /checkout/confirm` with its original body?

**Answer:** Not by default. The handler typically redirects the browser to the saved URL, and the browser sends a new request—usually GET with a 302 redirect. Side-effecting operations require dedicated design.

**Question 4.** A `SavedRequest` exists, yet the controller still does not run and the response is 403. Why?

**Answer:** A saved request grants no permissions. The post-redirect request still passes through authorization, and the user may lack the required authority.

**Question 5.** Why can `defaultSuccessUrl("/dashboard", true)` break returning to the previous page?

**Answer:** Because the `true` flag tells the corresponding success handler to always use the default target, overriding the saved target.

**Question 6.** Why is `NullRequestCache` suitable for many stateless APIs?

**Answer:** Because APIs usually need to return 401 and let clients manage login/routing themselves, without saving requests in a session. Session management and authentication must still be configured consistently.

**Question 7.** How do `getRequest` and `getMatchingRequest` differ?

**Answer:** `getRequest` returns the stored `SavedRequest` if present; `getMatchingRequest` looks up whether a current HTTP request matches the saved request, potentially returning a wrapper and managing cache lifecycle per implementation. Do not assume reading removes it.

**Question 8.** With multiple tabs sharing one session, is each tab guaranteed to return to its own URL?

**Answer:** Not with a simple `HttpSessionRequestCache`; other requests can overwrite the saved target. If UX requires distinguishing tabs/flows, design dedicated per-flow state.

## 16. Core Takeaways

- `RequestCache` manages interrupted request details; `SavedRequest` is the stored description; `HttpSessionRequestCache` typically uses the session.
- `ExceptionTranslationFilter` can save the request and commence login; `SavedRequestAwareAuthenticationSuccessHandler` redirects back to the saved URL after successful login per policy.
- The browser **sends a new HTTP request** to the redirected URL; the server does not re-execute a POST body or an already-started transaction.
- `RequestCacheAwareFilter`/`getMatchingRequest` assists matching and can manage `SavedRequest` lifecycle, though behavior depends on the cache implementation and Spring Security version.
- Session/cookies, success handler, default target, security chains, and request-cache matchers govern whether the original URL is restored.
- Saved requests **do not bypass authorization** and do not replace CSRF, idempotency, redirect URL validation, or draft data management.
- Test the real chain **protected GET → saved URL → POST login + CSRF → Location saved URL → new GET with session → authorization/controller**.
