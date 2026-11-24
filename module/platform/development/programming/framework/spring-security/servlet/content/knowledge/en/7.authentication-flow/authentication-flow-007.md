# AuthenticationSuccessHandler and AuthenticationFailureHandler in Spring Security Servlet

## 1. What Problem Do These Two Handlers Solve?

In Spring Security running on the **Servlet stack** (Spring MVC, Tomcat, and equivalent Servlet containers), submitting a username and password is only the **input** to the authentication process. After an authentication filter processes the credentials, the application still needs to decide the **HTTP response for success or failure**: returning to the page the user requested, opening a dashboard, displaying an error message, returning JSON, or recording an audit event.

Two extension points commonly used with **form login** are:

- **`AuthenticationSuccessHandler`**: builds the response after the authentication step orchestrated by the authentication filter **succeeds**. For example, redirecting to a request saved before login or to `/dashboard`.
- **`AuthenticationFailureHandler`**: builds the response when that authentication step itself **fails** with an `AuthenticationException`. For example, redirecting to `/login?error` or returning HTTP 401 for an API.

**They are not** password verification mechanisms, URL authorization engines, or replacements for CSRF/session handling. Handlers decide the response at the *end of an authentication attempt*; they do not make a principal valid on their own.

Learning objectives:

1. Identify precisely when each handler is invoked in the Servlet authentication flow.
2. Distinguish form login failure from an unauthenticated request to a protected resource, and from a logged-in request lacking permissions.
3. Use `SavedRequestAwareAuthenticationSuccessHandler` and `SimpleUrlAuthenticationFailureHandler` instead of writing unsafe custom redirects.
4. Build a runnable Spring Boot 3.x / Spring Security 6.x, Java 17+ configuration and verify it with MockMvc without disabling CSRF for convenience.
5. Design responses/redirects appropriate for cookie/session web apps and JSON APIs while avoiding sensitive information leaks.

## 2. Handler Position in the `SecurityFilterChain` Flow

In standard form login, `UsernamePasswordAuthenticationFilter` handles the login request (defaulting to **POST `/login`**) and calls the configured `AuthenticationManager`/`AuthenticationProvider`s to verify credentials.

High-level flow:

```text
Browser                          Servlet / Spring Security
   |                                      |
   | POST /login + username/password     |
   |   + CSRF token + session cookie     |
   +------------------------------------->|
                                          |
                             FilterChainProxy selects SecurityFilterChain
                                          |
                                    CsrfFilter (if applicable)
                                          |
                              UsernamePasswordAuthenticationFilter
                                          |
                              AuthenticationManager / Provider
                                          |
                              +-----------+------------+
                              |                        |
                           success                  failure
                              |                        |
                   session strategy /         clear SecurityContext,
                   SecurityContext is         notify remember-me
                   set/saved appropriately    failure (if used)
                              |                        |
                   AuthenticationSuccessHandler   AuthenticationFailureHandler
                              |                        |
                        302 /dashboard               302 /login?error
                        or saved URL                 or HTTP 401 JSON
```

The diagram presents the **meaning of each step**; it does not enumerate every filter in strict order across all versions or authentication mechanisms. Filters preceding the authentication filter (especially CSRF) can block the request **before** success/failure handlers ever get a chance to run.

### Which Primary Methods Do the Interfaces Have?

```java
// Illustrative method signatures from the Spring Security Servlet API:
void onAuthenticationSuccess(
    jakarta.servlet.http.HttpServletRequest request,
    jakarta.servlet.http.HttpServletResponse response,
    org.springframework.security.core.Authentication authentication
) throws java.io.IOException, jakarta.servlet.ServletException;

void onAuthenticationFailure(
    jakarta.servlet.http.HttpServletRequest request,
    jakarta.servlet.http.HttpServletResponse response,
    org.springframework.security.core.AuthenticationException exception
) throws java.io.IOException, jakarta.servlet.ServletException;
```

The two signatures above are **method excerpts** for explanation, not a standalone compilable `class` declaration. An `AuthenticationSuccessHandler` receives the authenticated `Authentication`; an `AuthenticationFailureHandler` receives the authentication error. Do not try to use a failure handler to catch every `AccessDeniedException` on business requests.

### Distinguishing Four Commonly Confused Scenarios

| Scenario | Typical Handling Component | Common Web Response |
| --- | --- | --- |
| POST `/login` with valid credentials | Authentication filter → success handler | 302 to saved request or default page |
| POST `/login` with wrong password | Authentication filter → failure handler | 302 to `/login?error` |
| GET `/account` by unauthenticated user | Authorization → `ExceptionTranslationFilter` → `AuthenticationEntryPoint` | Redirect to login page or HTTP 401 |
| GET `/admin` by logged-in user lacking role | Authorization → `AccessDeniedHandler` | Typically HTTP 403 |

A CSRF error on POST is typically rejected by `CsrfFilter`, commonly returning 403; it is **not** a "wrong password" and is normally not routed to `AuthenticationFailureHandler`.

**Identify the exact failure before fixing:** `AuthenticationFailureHandler` handles failures **during the authentication step owned by that filter**. `AuthenticationEntryPoint` initiates the authentication flow when a resource requires login. `AccessDeniedHandler` handles rejected access for an already-authenticated caller. Three callbacks serve three distinct purposes.

## 3. Default Form Login Handlers

When enabling form login with `http.formLogin(Customizer.withDefaults())` in Spring Security Servlet, notable default behaviors include:

- If no custom login page is provided, Spring Security normally generates a **GET `/login`** page for browser interaction.
- The form submits credentials to **POST `/login`** using default parameters `username` and `password` (along with the CSRF token when CSRF protection applies).
- Success typically uses **`SavedRequestAwareAuthenticationSuccessHandler`**: prefers returning the user to the URL saved before login was required, or falls back to a default page.
- Failure typically uses **`SimpleUrlAuthenticationFailureHandler`**: redirects to `/login?error` in the default form login setup (exact behavior can be customized).

Do not think of `failureUrl` and `failureHandler` as two steps that always run sequentially. `failureUrl(...)` configures redirect behavior; when you supply a custom `failureHandler(...)`, that handler takes responsibility for producing the response. Likewise, `defaultSuccessUrl(...)` and `successHandler(...)` both configure the success branch, yet your registered handler dictates the final flow.

### Success Handler and "Saved Request"

An unauthenticated user tries to open `GET /account`. When session/request cache support is active, `ExceptionTranslationFilter` can save this request before redirecting to the login page. After successful login:

```text
GET /account (anonymous)
        |
        v
RequestCache saves original request
        |
        v
302 /login  ->  GET /login
        |
        v
POST /login + valid credentials
        |
        v
SavedRequestAwareAuthenticationSuccessHandler
        |
        +--> redirect back to /account (if a suitable saved request exists)
        |
        +--> redirect to defaultTargetUrl (if no saved request exists)
```

This gives a better experience than always sending users to `/`. The request cache is not a reason to trust arbitrary client-supplied URLs; redirects must still respect the application's safe URL/host policy. Stateless deployments may not have sessions/saved requests like web browsers.

`SimpleUrlAuthenticationSuccessHandler` is appropriate when you want to redirect to a fixed target URL or perform simple customization. `SavedRequestAwareAuthenticationSuccessHandler` extends that behavior to handle saved requests. **Never append `request.getParameter("next")` directly into `sendRedirect`** without validating the target, to prevent open redirects.

## 4. What Happens Before the Success Handler Runs?

Authentication handlers are normally the **final HTTP-response step** of an authentication attempt. In the `AbstractAuthenticationProcessingFilter` flow (basis of many form login filters), when authentication succeeds, Spring Security has already had the chance to execute tasks such as:

1. `AuthenticationManager` verified credentials and produced a successful `Authentication`.
2. The session authentication strategy handled session policies, such as **session fixation** protection when using sessions.
3. `SecurityContext` was populated and saved using the configured `SecurityContextRepository`.
4. Remember-me services, if configured, received the success notification; an authentication success event may have been published.
5. Then the success handler creates the redirect or response.

Exact ordering/details can differ across authentication filter types and custom setups. **Do not use the success handler to manually set `isAuthenticated=true`, store passwords in the session, or overwrite the security context** when the filter already did that work properly.

On the failure branch, steps typically include clearing the attempt's `SecurityContext`, notifying remember-me services if present, and invoking the failure handler. Do not assume a session always exists on failure; depending on login mechanism and configuration, no session may have been created yet.

### Why Shouldn't You Manage Sessions Manually in a Handler?

Calling `request.getSession().setAttribute("USER", username)` manually does not replace the security context model and easily conflicts with session fixation protection. A custom session attribute also does not make the next request authenticated for Spring Security. If you need display info after login, read from the framework-provided `Authentication` object or a dedicated business service—never copy passwords or sensitive tokens into the session.

## 5. Complete Spring Boot 3.x / Java 17+ Example: Delegating to Standard Handlers

A Spring Boot Servlet project (Spring Security 6.x) with build plugins and dependency management already configured needs two dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

Create **`src/main/java/example/loginhandlers/LoginHandlersApplication.java`**:

```java
package example.loginhandlers;

import java.io.IOException;

import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AuthenticationFailureHandler;
import org.springframework.security.web.authentication.AuthenticationSuccessHandler;
import org.springframework.security.web.authentication.SavedRequestAwareAuthenticationSuccessHandler;
import org.springframework.security.web.authentication.SimpleUrlAuthenticationFailureHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class LoginHandlersApplication {

    public static void main(String[] args) {
        SpringApplication.run(LoginHandlersApplication.class, args);
    }
}

@Configuration
class SecurityConfiguration {

    private static final Logger LOG =
        LoggerFactory.getLogger(SecurityConfiguration.class);

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationSuccessHandler loginSuccessHandler,
            AuthenticationFailureHandler loginFailureHandler
    ) throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/dashboard").authenticated()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .formLogin(form -> form
                .successHandler(loginSuccessHandler)
                .failureHandler(loginFailureHandler)
                .permitAll()
            )
            .build();
    }

    @Bean
    AuthenticationSuccessHandler loginSuccessHandler() {
        SavedRequestAwareAuthenticationSuccessHandler delegate =
            new SavedRequestAwareAuthenticationSuccessHandler();

        delegate.setDefaultTargetUrl("/dashboard");
        delegate.setAlwaysUseDefaultTargetUrl(false);

        return (request, response, authentication) -> {
            // Log only minimal event info; never log passwords/cookies/tokens.
            LOG.info("Form login success for principal type={}",
                authentication.getPrincipal().getClass().getSimpleName());

            // Delegate preserves safe redirect logic to the configured saved request.
            delegate.onAuthenticationSuccess(request, response, authentication);
        };
    }

    @Bean
    AuthenticationFailureHandler loginFailureHandler() {
        SimpleUrlAuthenticationFailureHandler delegate =
            new SimpleUrlAuthenticationFailureHandler("/login?error");

        return (request, response, exception) -> {
            // Do not send AuthenticationException messages out to the browser.
            LOG.warn("Form login rejected; exception type={}",
                exception.getClass().getSimpleName());

            delegate.onAuthenticationFailure(request, response, exception);
        };
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode("demo-pass"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("USER", "ADMIN")
            .build();

        return new InMemoryUserDetailsManager(learner, admin);
    }
}

@RestController
class SampleController {

    @GetMapping("/dashboard")
    String dashboard(Authentication authentication) {
        return "Hello " + authentication.getName();
    }

    @GetMapping("/admin")
    String admin() {
        return "Admin dashboard";
    }
}
```

Only `LoginHandlersApplication` is a `public` top-level class, so having three classes in one file is valid Java 17. `@SpringBootApplication` scans package `example.loginhandlers` and picks up the configuration and controller.

**Why is this example useful?**

- No custom login page needed: Spring Security provides GET `/login` when configured accordingly.
- `.formLogin(...permitAll())` permits access to URLs needed for the login page/login processing under form login; `anyRequest().denyAll()` still blocks undeclared endpoints.
- `SavedRequestAwareAuthenticationSuccessHandler` prefers the cached request URL; if none exists, it redirects to `/dashboard`.
- `SimpleUrlAuthenticationFailureHandler` sends the user back to `/login?error`, without revealing whether the user exists, the password was wrong, or the account is locked via detailed response messages.
- The logger records only the **principal type** or **exception type** for illustration. Real operations should design auditing per organizational policy, with correlation IDs and avoiding unnecessary PII storage.
- The two accounts are strictly for demo purposes, with passwords hashed by the encoder before in-memory storage. Never copy test accounts or passwords into production.
- CSRF is not disabled: the browser uses the default form login and Spring Security's CSRF token. Never transmit usernames/passwords over plain public HTTP in production.

### Running the Application

With a Spring Boot Gradle project containing the wrapper:

```bash
./gradlew bootRun
```

On Windows PowerShell, use `./gradlew.bat bootRun`. After starting on local port 8080, open in a browser:

```text
http://localhost:8080/dashboard
```

Expected: the browser is redirected to the login page. Enter `learner` / `demo-pass` in the Spring Security-generated form; upon success, the handler returns the browser to the **saved `/dashboard`**, and the controller responds:

```text
Hello learner
```

If you open `http://localhost:8080/login` directly first (no saved request), successful login still redirects to `/dashboard` due to `setDefaultTargetUrl`. If you enter a wrong password, the failure handler redirects to `/login?error`, where the default login page can display a generic error message.

**Note**: these are the **expected outputs and flow per configuration**, not stdout captured from an actual run. Redirects may use relative paths or absolute URLs depending on the Servlet container, context path, and how the app is deployed behind a proxy.

## 6. Testing with MockMvc: Success, Failure, Saved Request, CSRF

Merely observing a redirect in a browser is not enough to prove the boundaries. Tests must isolate: successful authentication, failed authentication, CSRF failure, and logged-in user lacking permissions.

In a Spring Boot project with test dependencies configured:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Create `src/test/java/example/loginhandlers/LoginHandlersSecurityTest.java`:

```java
package example.loginhandlers;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LoginHandlersSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void successfulLoginRedirectsToDefaultWhenNoSavedRequest()
            throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "demo-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string("Location", containsString("/dashboard")));
    }

    @Test
    void badPasswordUsesFailureHandlerRedirect() throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "not-the-password"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string("Location", containsString("/login?error")));
    }

    @Test
    void anonymousProtectedRequestStartsLoginRatherThanFailureHandler()
            throws Exception {
        mvc.perform(get("/dashboard"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string("Location", containsString("/login")));
    }

    @Test
    void savedRequestIsRestoredAfterSuccessfulFormLogin() throws Exception {
        MvcResult first = mvc.perform(get("/dashboard"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) first.getRequest().getSession(false);

        mvc.perform(post("/login")
                .session(session)
                .with(csrf())
                .param("username", "learner")
                .param("password", "demo-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string("Location", containsString("/dashboard")));
    }

    @Test
    void csrfFilterRejectsLoginPostMissingToken() throws Exception {
        mvc.perform(post("/login")
                .param("username", "learner")
                .param("password", "demo-pass"))
            .andExpect(status().isForbidden());
    }

    @Test
    void ordinaryUserCannotAccessAdmin() throws Exception {
        mvc.perform(get("/admin")
                .with(org.springframework.security.test.web.servlet
                    .request.SecurityMockMvcRequestPostProcessors
                    .user("learner").roles("USER")))
            .andExpect(status().isForbidden());
    }
}
```

Testing via `MockMvc` allows using `.with(csrf())` to supply a valid CSRF token for POST login; there is no need to disable this protection. The saved-request test carries the same `MockHttpSession` from the protected-page GET to the login POST, verifying URL restoration behavior. Once the session strategy processes login, the session ID may change per policy; the test asserts only `Location` rather than assuming an unchanged ID.

Run:

```bash
./gradlew test
```

The tests above are **suggested examples**, not executed in this document. When writing tests for production, add explicit assertions that authentication was stored in the right context/session and check `SecurityContextRepository` per design (stateful/stateless).

## 7. How to Customize Responses for the Right Client Type?

Traditional form login targets navigating browsers. For an SPA/API with its own login mechanism, the desired response may differ. Never return **HTTP 302** for every API authentication failure when the client expects status 401 and a JSON payload.

### 7.1. Success Handler for Browsers

Prefer delegates supported by Spring Security:

```java
SavedRequestAwareAuthenticationSuccessHandler success =
    new SavedRequestAwareAuthenticationSuccessHandler();

success.setDefaultTargetUrl("/dashboard");
success.setAlwaysUseDefaultTargetUrl(false);
```

This snippet illustrates creating the handler and belongs inside an appropriate method/class. `alwaysUseDefaultTargetUrl(false)` prioritizes a saved request if present. Conversely, set `true` when policy genuinely wants to **always** send users to a single destination and ignore saved requests.

**If the application is multi-tenant or needs an onboarding step**, the success handler can choose the destination using verified server-side data. Never blindly trust `?returnUrl=https://evil.example`; allow redirects only to valid internal paths or allowlisted origins.

### 7.2. Failure Handler for Browsers

```java
SimpleUrlAuthenticationFailureHandler failure =
    new SimpleUrlAuthenticationFailureHandler("/login?error");
```

The standard handler performs the redirect after failed login. `?error` is merely a **UI signal**, not necessarily describing a specific cause. Avoid displaying `BadCredentialsException.getMessage()` directly to users. For locked accounts, wrong passwords, or nonexistent accounts, messaging policy should balance UX against username enumeration risks.

### 7.3. JSON Response for API Login — Custom Fragment

If you have an **authentication filter handling POST API login** and have configured it to use success/failure handlers, you can return JSON instead of redirecting:

```java
AuthenticationSuccessHandler apiSuccess = (request, response, auth) -> {
    response.setStatus(HttpServletResponse.SC_OK);
    response.setContentType("application/json;charset=UTF-8");
    response.getWriter().write("{\"authenticated\":true}");
};

AuthenticationFailureHandler apiFailure = (request, response, exception) -> {
    response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
    response.setContentType("application/json;charset=UTF-8");
    response.getWriter().write("{\"error\":\"invalid_credentials\"}");
};
```

This is a **fragment** requiring an import for `HttpServletResponse` and placement in a suitable method/class; the example writes static JSON to avoid input-escaping bugs. Never echo verbatim exceptions, tokens, principals, or submitted passwords in the payload.

**Important:** Declaring an `AuthenticationSuccessHandler` bean does not automatically authenticate every API request. It runs only when a **specific authentication filter** handles the request and is wired to that handler. `httpBasic()`, OAuth2 login, bearer-token resource servers, and form login each have their own default entry points/filters; to change the response of a mechanism, configure that mechanism's exact extension point.

Do not take cookie/session browser code, convert it to a stateless API, and unconditionally disable CSRF. Evaluate credential transport (browser-auto-sent cookies vs client-attached bearer tokens, etc.), CORS, SameSite, session policy, and the CSRF threat model before designing.

## 8. What Handlers Do NOT Do

### Do Not Replace `AuthenticationProvider`

`AuthenticationSuccessHandler` does not verify passwords; by the time it runs, the authentication manager/provider has already decided success. If you need extra checks for disabled accounts or second authentication factors, pick the right spot in the authentication pipeline rather than having a success handler "re-authorize" with arbitrary `if` chains.

### Do Not Replace Authorization

Successful login only creates an `Authentication`; it does not mean the user may view every URL. `hasRole("ADMIN")`, `hasAuthority(...)`, ownership-based authorization, and domain policies still must be enforced. Handlers only decide the login response; they do not unlock admin access.

### Do Not Replace `AuthenticationEntryPoint`

When an anonymous user visits `GET /dashboard`, Spring Security normally triggers `AuthenticationEntryPoint` to redirect to `/login`. That is not a username/password verification failure. `AuthenticationFailureHandler` is not invoked merely because a user is not yet logged in.

### Do Not Replace `AccessDeniedHandler`

A logged-in user lacking `ROLE_ADMIN` who calls `GET /admin` typically gets 403 from access-denied processing. It does not go through the login failure handler. To customize the 403 page, configure exception handling / access-denied handling in the right place.

### Do Not Handle All Pre-Filter Errors

A `POST /login` request missing a CSRF token can be rejected before `UsernamePasswordAuthenticationFilter`. Malformed HTTP requests, paths not matching the login processing URL, or reverse-proxy redirect loops are likewise not cases where success/failure handlers are called.

### Do Not Automatically Provide Audit/Lockout/Rate Limiting

Logging "wrong password" inside a failure handler is **not enough** to stop brute-force, password spraying, or credential stuffing. You need corresponding controls in the authentication service, rate limiters, security monitoring, or gateways, with sensible resource limits and without accidentally enabling denial-of-service via mass account lockouts.

## 9. Choosing Between Custom Handlers and Standard Handlers

| Need | Common Solution | Considerations |
| --- | --- | --- |
| Return to previous protected URL on login success | `SavedRequestAwareAuthenticationSuccessHandler` | RequestCache and session must fit; public URLs must be trustworthy |
| Always go to dashboard on login success | `SimpleUrlAuthenticationSuccessHandler` or `defaultSuccessUrl(..., true)` | Will not restore saved requests if target is always forced |
| Light audit on login success, then standard redirect | Custom handler that **delegates** to saved-request handler | Do not write to the response before delegating a redirect |
| Return to login page on login failure | `SimpleUrlAuthenticationFailureHandler` or `failureUrl(...)` | Keep message generic to prevent username enumeration |
| Login API returns status and JSON | Handler attached to the corresponding authentication filter | Do not assume all auth mechanisms behave like form login |
| Anonymous caller hits protected resource | `AuthenticationEntryPoint` | Do not use failure handler |
| Logged-in caller lacks permission | `AccessDeniedHandler` and authorization rules | Do not use failure handler |

Pragmatic rule: **prefer built-in configuration or delegation; only code the policy you genuinely need**. A custom handler that simultaneously performs auditing, account updates, token issuance, redirects, cookie deletion, and multiple response writes is hard to test and prone to half-succeeded states.

## 10. Implementation Pitfalls and Fixes

### 10.1. Browser Caught in a Redirect Loop After Login

Symptom: POST login returns 302, yet the browser keeps bouncing back to `/login`. Possible causes: session/security context not persisted to the next request, missing/blocked cookies, mismatched redirect URL, target path denied, or proxy misinterpreting HTTPS.

Diagnostic steps: trace the HTTP status/`Location` chain in the Network tab, confirm the session cookie is sent back, verify the security chain covers the target URL, and check authorization policy on that URL. Do not fix it by haphazardly applying `permitAll()` across the whole app.

### 10.2. Login Succeeds Yet Does Not Reach `/dashboard`

If a saved request exists, `SavedRequestAwareAuthenticationSuccessHandler` **prioritizes the saved request** as configured. To always land on `/dashboard`, you can call `setAlwaysUseDefaultTargetUrl(true)`, while considering UX when a user specifically requested a protected page. A modified or disabled `RequestCache` also affects behavior.

### 10.3. Handler Configured Yet Never Runs

Check whether the request matches the authentication filter's **login processing URL**; whether the filter/chain is selected; whether credentials use the expected parameter names; whether CSRF blocked it earlier; and whether another form login config overrides the handlers. Creating a standalone `@Bean AuthenticationFailureHandler` will not automatically wire it unless attached to `formLogin`.

### 10.4. Failure Handler Returns HTML/302 to an API Client

API clients may not follow redirects like browsers; receiving an HTML login page instead of JSON breaks callers. Separate browser chains and authentication mechanisms from API ones, defining suitable status codes and content types. Never call `sendError(401)` after `sendRedirect`: the HTTP response may already be committed.

### 10.5. Logging Full Username/Password or Exception Messages

Usernames can be personal data; passwords, OTPs, session IDs, CSRF tokens, and bearer tokens are sensitive secrets. Never log `request.getParameter("password")`, raw `Authentication`, or `Authorization` headers. Audit logs should be designed with access controls, retention periods, and appropriate PII minimization.

### 10.6. Open Redirect via `?next=`

Dangerous example:

```java
String next = request.getParameter("next");
response.sendRedirect(next); // NEVER use when next is unvalidated.
```

A client could supply a URL to an attacker's site, redirecting post-login to an untrusted domain. When a return URL is needed, prefer server-side saved requests with host constraints, or allow only internal paths starting with `/` under strict validation (blocking `//`, abnormal encoding, control characters, unknown schemes, wrong context path). Never check only `startsWith("/")` and assume it is safe.

### 10.7. Disabling CSRF to Test Login

For form login relying on browser cookies/sessions, unconditionally disabling CSRF increases the risk of login CSRF and CSRF on other actions. In MockMvc, use `.with(csrf())`; in browsers, use the framework-issued login form and CSRF token. A tokenless `POST /login` failing does not mean the failure handler is misconfigured.

### 10.8. Storing Login State in a Custom Session Attribute

Calling `session.setAttribute("loggedIn", true)` inside a success handler does not replace `Authentication` in `SecurityContext`. Code checking custom session attributes easily falls out of sync with logout, session expiration, authentication failures, and concurrency control. Rely on configured Spring Security authentication and authorization.

## 11. Security Testing Beyond the Happy Path

An acceptance test suite should cover these cases:

| Test case | Expectation |
| --- | --- |
| POST login with valid credentials and valid CSRF | Success handler runs, produces expected response, valid identity established |
| POST login with wrong password and valid CSRF | Failure handler runs, response discloses no sensitive reasons |
| POST login missing CSRF token | CSRF filter blocks (typically 403), not treated as a password error |
| GET protected page while anonymous | `AuthenticationEntryPoint` triggers login challenge/redirect |
| GET admin while logged in without permission | `AccessDeniedHandler` handles, typically 403 |
| Login after a saved protected request | Redirects to saved URL if policy permits |
| Direct login from the login page | Redirects to fallback `/dashboard` |
| Target URL contains a disallowed hostname | Never generates redirect to an untrusted external host |
| Successful login followed by next request | `SecurityContext`/session persists per lifecycle |
| Session ID rotation under session-fixation policy | Does not retain old session ID against policy |
| Request behind an HTTPS reverse proxy | `Location`, scheme, host, and cookie policy reflect the public origin |
| Login API (if applicable) | Does not unexpectedly return HTML/302 when contract requires 401 JSON |

In production, add tests for brute-force resistance, locked accounts, expired passwords, uniform error messages, logout, and concurrent session handling per business requirements. Handlers do not enforce those policies themselves.

## 12. Review Questions (with Answers)

**Question 1.** A user enters a wrong password on POST `/login`. Which handler runs in standard form login?

**Answer:** The `AuthenticationFailureHandler` configured on the authentication filter handling POST login (assuming the request passed earlier filters and threw an authentication exception). It is not `AccessDeniedHandler`.

**Question 2.** An anonymous user accesses GET `/admin` and is redirected to `/login`. Was the failure handler called?

**Answer:** No. Spring Security normally invokes `AuthenticationEntryPoint` because the endpoint requires the user to be logged in; no password verification attempt failed.

**Question 3.** Why should a success handler delegate to `SavedRequestAwareAuthenticationSuccessHandler` instead of always hardcoding a redirect?

**Answer:** Delegation supports returning users to the resource they originally requested before logging in and falls back when no saved request exists. A fixed redirect can still be valid if the product intentionally ignores saved requests.

**Question 4.** In a session-based web app, POST login lacks a CSRF token and returns 403. Should you inspect the password encoder or failure handler first?

**Answer:** Check `CsrfFilter`/CSRF token first, because the request can be rejected **before** reaching the authentication filter. In MockMvc, use `.with(csrf())` when testing valid login paths.

**Question 5.** A user logs in successfully yet receives 403 on GET `/admin`. Should you redirect using the success handler?

**Answer:** No. Successful login and admin permission are two separate decisions. The `hasRole("ADMIN")` policy and access-denied processing handle authorization.

**Question 6.** A handler reads `?next=https://other.example` and redirects to that URL. What is the risk?

**Answer:** Post-login open redirect. Only redirect to server-controlled destinations or targets strictly validated against an allowlist.

**Question 7.** An API client requires JSON `401` errors on invalid POST login. Is declaring a single `@Bean AuthenticationFailureHandler` enough?

**Answer:** Not enough. There must be an authentication filter actually processing the login API, wired with that handler in the right filter/chain, while confirming the client contract as well as CSRF and session policies.

## 13. Key Technical Summary

- `AuthenticationSuccessHandler` receives a **successful** `Authentication` and decides the final redirect/response for an authentication attempt.
- `AuthenticationFailureHandler` receives an `AuthenticationException` **from the authentication step** and decides the failure response/notification.
- For Servlet form login, **`SavedRequestAwareAuthenticationSuccessHandler`** supports saved URLs; **`SimpleUrlAuthenticationFailureHandler`** supports redirecting to an error page.
- **`AuthenticationEntryPoint`** initiates login when an anonymous caller accesses a protected URL; **`AccessDeniedHandler`** handles denied authorization. Never mix the three flows.
- **CSRF, security context, session fixation, request cache, and authorization** each play distinct roles; handlers do not replace them.
- Prefer delegation and test status/`Location`/sessions per scenario. Never return raw exceptions to clients, never log credentials, and never redirect to unvalidated client-supplied URLs.

**Core principle:** Success/failure handlers are **customization points for the response after an authentication attempt**, not where you define whether a user's password is valid or which resources they are authorized to access.
