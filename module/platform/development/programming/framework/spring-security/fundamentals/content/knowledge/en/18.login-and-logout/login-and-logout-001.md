# Form Login and the Browser Redirect Flow in Spring Security

When an unauthenticated user opens `/dashboard`, Spring Security typically **redirects the browser to the login page**, receives credentials from the form, authenticates the identity, and redirects back to the original page. However, this is not a single request: the browser and server perform multiple separate HTTP round trips, each with a different method, URL, cookie, and responsibility.

This lesson belongs to **Login and Logout** of **Spring Security - fundamentals**. The goal is to properly understand **GET login page, POST login processing, HTTP redirect, saved request, session, CSRF, success/failure handling, and logout**; and know how to implement, test, and debug the form login flow. The main examples use **Java 17+, Spring Boot 3.3.x, and Spring Security 6.3.x on Spring MVC/Servlet**. For WebFlux applications, configuration classes and context management differ; do not copy `HttpSecurity` patterns verbatim to `ServerHttpSecurity`.

## 1. Mental model: which HTTP requests actually happen?

Suppose a user types `http://localhost:8080/dashboard` while not logged in:

~~~text
Browser                                       Spring Security Application
    |                                                   |
    |  GET /dashboard                                   |
    |-------------------------------------------------->|
    |                                                   | Unauthenticated
    |  302 Location: /login                             | May save request
    |<--------------------------------------------------|
    |                                                   |
    |  GET /login                                       |
    |-------------------------------------------------->|
    |  200 HTML containing form                         |
    |<--------------------------------------------------|
    |                                                   |
    |  POST /login                                      |
    |  username=lan&password=...&_csrf=...              |
    |-------------------------------------------------->|
    |                                                   | Verify CSRF,
    |                                                   | authenticate password,
    |                                                   | save SecurityContext
    |  302 Location: /dashboard                         |
    |<--------------------------------------------------|
    |                                                   |
    |  GET /dashboard + session cookie                  |
    |-------------------------------------------------->|
    |  200 Dashboard content                            |
    |<--------------------------------------------------|
~~~

Here, **redirect** means the server returns an HTTP 3xx status code with a `Location` header, and then **the browser makes a new request**. A redirect does not automatically invoke a Controller within the same request like an internal Java call.

This example describes the Servlet flow with default form login. URLs, status codes, saving the previous URL, success targets, and session lifetime can all be customized. Do not treat every 302 redirect as a successful login: **a failed login also commonly returns 302**, but to a different destination.

Three phases to remember:

1. **Before authentication:** a request requiring authorization arrives, Spring Security denies access because the user is not logged in, and initiates the login flow.
2. **Executing authentication:** the form sends a POST with username/password and CSRF; the authentication filter communicates with `AuthenticationManager`.
3. **After authentication:** on success, the security context is saved, the success strategy selects a target URL, and the browser sends the next GET with the session cookie.

## 2. GET /login vs. POST /login

Spring Security Servlet with `formLogin(Customizer.withDefaults())` follows these conventions:

| HTTP request | Role | Typical handling component | Common result |
| --- | --- | --- | --- |
| `GET /login` | Display HTML form | Spring Security auto-generated login page when no custom page is configured | 200 |
| `POST /login` | Verify login credentials | `UsernamePasswordAuthenticationFilter` | 302 to target page or login error |
| `GET /login?error` | Display invalid login message | Login page | 200 |
| `GET /login?logout` | Display logout notice | Login page | 200 |
| `GET /dashboard` when anonymous | Request resource requiring login | Authorization + entry point | Usually 302 to `/login` |
| `GET /dashboard` after login | View protected content | Filter chain allows through, then to Controller | Usually 200 |

**You do not need to declare `@PostMapping("/login")` yourself** if the application uses the default `UsernamePasswordAuthenticationFilter`. The filter processes its login POST URL before the request reaches a Controller.

In the default form, the username field is named `username` and the password field is named `password`. If you write your own form with `name="email"` without setting `usernameParameter("email")`, the filter will not automatically read the new field name.

When calling `.loginPage("/signin")`, Spring Security **no longer auto-generates HTML for the custom signin page**. The application must provide the corresponding GET route and view/HTML; the POST URL for authentication can remain the default or be changed via `loginProcessingUrl(...)`.

## 3. Who sends an unauthenticated user to the login page?

In a Servlet chain, the roles of the key components are:

- **`AuthorizationFilter`**: enforces authorization rules such as `.requestMatchers("/dashboard").authenticated()`.
- **`ExceptionTranslationFilter`**: translates security exceptions into an appropriate handling path. For unauthenticated users, it can initiate the login process; for authenticated users lacking permission, it can handle access denial.
- **`LoginUrlAuthenticationEntryPoint`**: in form login, typically issues a redirect to the login page path.
- **`RequestCache`**: can hold the requested URL before redirecting so the user returns to it after login.
- **`UsernamePasswordAuthenticationFilter`**: intercepts POST at the login processing URL and invokes the authentication mechanism.
- **`AuthenticationManager`/`AuthenticationProvider`**: verifies identity and password against the user data source.
- **`AuthenticationSuccessHandler`**: chooses the response/target after successful authentication.
- **`AuthenticationFailureHandler`**: handles a failed authentication attempt, typically redirecting back to the login page with an error state.
- **`SecurityContextRepository`**: supports persisting and loading security information across requests.

Conceptual timeline:

~~~text
GET /dashboard
    |
    +--> Unauthenticated
    +--> AuthorizationFilter denies
    +--> ExceptionTranslationFilter / AuthenticationEntryPoint
    +--> (may) save SavedRequest
    +--> 302 Location: /login

GET /login
    +--> HTML form, including CSRF token

POST /login
    +--> CsrfFilter checks if CSRF applies
    +--> UsernamePasswordAuthenticationFilter
    +--> AuthenticationManager
           +--> success -> save SecurityContext
           |                  -> success handler
           |                  -> 302 Location: saved URL or default URL
           |
           +--> failure   -> failure handler
                              -> 302 Location: /login?error

GET saved URL
    +--> Session cookie, SecurityContext restored
    +--> Re-check authorization
    +--> Controller returns content
~~~

The exact order and present classes depend on chain configuration. This lesson uses them to explain **responsibilities**, not to claim the diagram is a filter-order dump for every version.

### 3.1. Unauthenticated is different from wrong password

Someone visiting `/dashboard` for the first time has not submitted a password. Spring Security redirects to login because **there is no valid identity yet**, not because of a wrong password. Only when submitting POST login is there an authentication attempt that can succeed or fail.

Conversely, a logged-in user without `ROLE_ADMIN` is blocked at `/admin` by `hasRole("ADMIN")`. With the default Servlet mechanism, the result is usually 403, because **the identity is known but lacks permission**. Whether this translates to 401/403/redirect depends on the entry point and access denied handler.

### 3.2. A redirect does not prove the target page is authorized

After login, the browser may receive `Location: /dashboard`; the subsequent GET request **still has to pass through the security filter chain**. If the account lacks permission to access the saved page, the server can still deny it. Authentication success does not automatically grant every permission in the application.

## 4. Saved request: returning to the page the user intended to open

Scenario:

~~~text
GET /orders/42                  not logged in
  → save request if applicable
  → 302 /login
POST /login                     valid username/password
  → 302 /orders/42
GET /orders/42                  with authenticated session
  → resource is viewed if authorized
~~~

`HttpSessionRequestCache` typically stores `SavedRequest` in the session. A success handler such as `SavedRequestAwareAuthenticationSuccessHandler` can prioritize this URL.

Limitations to understand:

- Saving the request depends on matchers, session policy, RequestCache, and version configuration.
- With multiple tabs or when the saved request has been replaced or is no longer valid, the chosen URL may differ from expectations.
- **Do not expect a POST with a body to be automatically replayed after login.** The most sensible return path is usually a GET page where the user can explicitly confirm a write action.
- If no suitable saved request exists, the handler usually uses the default URL.
- Some configurations can require the default URL to take precedence in all cases.

Example of controlling the default URL:

~~~java
.formLogin(form -> form
    .defaultSuccessUrl("/home", false)
)
~~~

Meaning of `false`: do not force the default URL if a prioritized saved request exists. With:

~~~java
.formLogin(form -> form
    .defaultSuccessUrl("/home", true)
)
~~~

meaning of `true`: always redirect to `/home` via this handler, rather than prioritizing a saved request.

If you allow a query string such as `returnUrl` as a redirect target, you must restrict it to valid URLs within the application. **Do not redirect directly to an arbitrary client-supplied destination**, as this can create an open redirect vulnerability.

## 5. How does the password pass through AuthenticationManager?

The default form submits data of type `application/x-www-form-urlencoded`:

~~~http
POST /login HTTP/1.1
Host: localhost:8080
Content-Type: application/x-www-form-urlencoded

username=lan&password=demo123&_csrf=VALID_CSRF_VALUE
~~~

Here `VALID_CSRF_VALUE` is only descriptive, not a usable token. A real CSRF token is issued by the server in the appropriate context.

`UsernamePasswordAuthenticationFilter` reads the parameters and creates an **untrusted** authentication object, then calls `AuthenticationManager.authenticate(...)`. For applications storing users in a database, `DaoAuthenticationProvider` typically coordinates `UserDetailsService` and `PasswordEncoder`.

~~~text
username/password from form
           |
           v
Unauthenticated UsernamePasswordAuthenticationToken
           |
           v
AuthenticationManager
           |
           v
Matching AuthenticationProvider
     - load user details
     - match password with PasswordEncoder
           |
           +--> valid: authenticated Authentication
           |
           +--> invalid: AuthenticationException
~~~

Do not compare raw password strings with `equals` and store plaintext in the database. In production, use an appropriate password encoder (BCrypt/Argon2 depending on the system) and a secure password change/recovery process.

## 6. Sample Spring Boot application: default login page

We build an application with `/` and `/public` public, `/dashboard` requiring login, `/admin` requiring role ADMIN, and one account `lan` with only USER. The application uses **Java 17+**, Spring Boot **3.3.x**, and Spring Security **6.3.x**. This is a learning example with an in-memory account.

### 6.1. Dependencies in build.gradle

For a Spring Boot project with plugins and versions already configured:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

This is the **dependencies section to merge into an existing build.gradle**, not a complete standalone build. The example does not need Thymeleaf when using the auto-generated login page.

### 6.2. FormLoginDemoApplication.java

File `src/main/java/example/formlogin/FormLoginDemoApplication.java`:

~~~java
package example.formlogin;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FormLoginDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(FormLoginDemoApplication.class, args);
    }
}
~~~

### 6.3. SecurityConfig.java

File `src/main/java/example/formlogin/SecurityConfig.java`:

~~~java
package example.formlogin;

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
                .requestMatchers("/", "/public").permitAll()
                .requestMatchers("/dashboard").authenticated()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .formLogin(Customizer.withDefaults())
            .logout(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails lan = User.withUsername("lan")
                .password(encoder.encode("demo123"))
                .roles("USER")
                .build();

        return new InMemoryUserDetailsManager(lan);
    }
}
~~~

The configuration above:

- `permitAll()` allows guests to view public URLs.
- `authenticated()` requires a valid identity at `/dashboard`.
- `hasRole("ADMIN")` checks `ROLE_ADMIN` by default convention, so account `lan` cannot access `/admin`.
- `anyRequest().denyAll()` denies undeclared URLs.
- `formLogin(Customizer.withDefaults())` enables the default login page and POST processing; `logout(...)` enables the logout mechanism.
- The test account has its password BCrypt-encoded at startup. Do not use demo accounts in production.
- CSRF keeps its default enabled configuration. Therefore, POST login/logout requests must carry a valid CSRF token.
- Spring Security generates the `GET /login` page in the default configuration; **there is no need to create a Controller for GET/POST login**.

### 6.4. PagesController.java

File `src/main/java/example/formlogin/PagesController.java`:

~~~java
package example.formlogin;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PagesController {

    @GetMapping("/")
    public String index() {
        return "Home (public)";
    }

    @GetMapping("/public")
    public String publicPage() {
        return "Public page";
    }

    @GetMapping("/dashboard")
    public String dashboard() {
        return "Dashboard (authenticated)";
    }

    @GetMapping("/admin")
    public String admin() {
        return "Admin area";
    }
}
~~~

The Controller returns plain text for easy observation. When starting the application and visiting `http://localhost:8080/dashboard` in a browser without a session: you should expect a redirect to login; logging in with `lan/demo123` redirects back to dashboard; `/admin` remains blocked due to missing ROLE_ADMIN.

Run command from a project with Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

This is an **expected scenario**, not a log from an actual execution. In production, remember to use HTTPS, a real user store, and appropriate session/cookie and login policies.

## 7. Testing both redirect and post-login session with MockMvc

A test that only sends POST login and receives 302 does not prove the user can open a protected resource. You must maintain the **same session** across the request sequence:

1. `GET /dashboard` as an unauthenticated user to create a saved request.
2. `POST /login` in that same session with CSRF and valid credentials.
3. `GET /dashboard` in the logged-in session to confirm SecurityContext is restored.

File `src/test/java/example/formlogin/FormLoginFlowTest.java`:

~~~java
package example.formlogin;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrlPattern;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class FormLoginFlowTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicPageNeedsNoLogin() throws Exception {
        mvc.perform(get("/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("Public page"));
    }

    @Test
    void protectedPageRedirectsAnonymousUser() throws Exception {
        mvc.perform(get("/dashboard"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void generatedLoginFormIsVisible() throws Exception {
        mvc.perform(get("/login"))
                .andExpect(status().isOk())
                .andExpect(content().string(containsString("username")));
    }

    @Test
    void badPasswordRedirectsBackToLogin() throws Exception {
        mvc.perform(post("/login")
                .param("username", "lan")
                .param("password", "incorrect")
                .with(csrf()))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/login?error"));
    }

    @Test
    void postingWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/login")
                .param("username", "lan")
                .param("password", "demo123"))
                .andExpect(status().isForbidden());
    }

    @Test
    void successfulLoginReturnsToSavedPageAndPersistsSession()
            throws Exception {

        MvcResult first = mvc.perform(get("/dashboard"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) first.getRequest().getSession(false);
        assertNotNull(session);

        MvcResult loggedIn = mvc.perform(post("/login")
                .session(session)
                .param("username", "lan")
                .param("password", "demo123")
                .with(csrf()))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrlPattern("**/dashboard"))
                .andExpect(authenticated().withUsername("lan"))
                .andReturn();

        MockHttpSession loggedInSession =
                (MockHttpSession) loggedIn.getRequest().getSession(false);
        assertNotNull(loggedInSession);

        mvc.perform(get("/dashboard").session(loggedInSession))
                .andExpect(status().isOk())
                .andExpect(content().string("Dashboard (authenticated)"));
    }

    @Test
    void directLoginWithoutSavedRequestUsesDefaultTarget() throws Exception {
        mvc.perform(post("/login")
                .param("username", "lan")
                .param("password", "demo123")
                .with(csrf()))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/"));
    }

    @Test
    void ordinaryUserStillCannotEnterAdminPage() throws Exception {
        mvc.perform(get("/admin").with(user("lan").roles("USER")))
                .andExpect(status().isForbidden());
    }

    @Test
    void logoutWithCsrfRedirectsToNotice() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                .param("username", "lan")
                .param("password", "demo123")
                .with(csrf()))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(post("/logout")
                .session(session)
                .with(csrf()))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/login?logout"));
    }
}
~~~

Test command:

~~~bash
./gradlew test --tests '*FormLoginFlowTest'
~~~

Windows:

~~~powershell
.\gradlew.bat test --tests "*FormLoginFlowTest"
~~~

**Expected result:** All 9 tests pass in an environment with the exact dependencies and configuration above. This is inferred from the API, **not a report from executed tests**. The tests use Spring Security MockMvc request post-processors to supply CSRF and mock identities. Real browsers still need verification of cookie attributes, HTTPS, session fixation, and multi-tab behavior.

## 8. Custom login page with Thymeleaf

To have a custom login interface, use one URL to **display the page** and one URL to **receive POST data**:

~~~java
// Snippet replacing the formLogin part of SecurityFilterChain.
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/", "/public", "/signin", "/css/**").permitAll()
        .requestMatchers("/dashboard").authenticated()
        .anyRequest().denyAll()
    )
    .formLogin(form -> form
        .loginPage("/signin")
        .loginProcessingUrl("/perform-login")
        .failureUrl("/signin?error")
        .defaultSuccessUrl("/dashboard", false)
        .permitAll()
    );
~~~

Explanation:

- `loginPage("/signin")` sets the GET URL for the browser to load HTML. When using a custom page, you must define the route and view yourself.
- `loginProcessingUrl("/perform-login")` is the POST URL processed by the **authentication filter**. Do not create an additional POST Controller for this same URL if you still use the standard filter.
- `failureUrl("/signin?error")` sets the redirect when credentials are invalid.
- `defaultSuccessUrl("/dashboard", false)` uses dashboard when no prioritized saved request exists.
- `.permitAll()` allows access to URLs needed for login; also make the page and required static resources public.

Add `spring-boot-starter-thymeleaf` to dependencies, then create the Controller:

~~~java
package example.formlogin;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class SignInController {

    @GetMapping("/signin")
    public String signin() {
        return "signin";
    }
}
~~~

Create file `src/main/resources/templates/signin.html`:

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Sign in</title>
</head>
<body>
    <h1>Sign in</h1>
    <form th:action="@{/perform-login}" method="post">
        <label for="username">Username</label>
        <input id="username" name="username" autocomplete="username">

        <label for="password">Password</label>
        <input id="password" type="password" name="password"
               autocomplete="current-password">

        <button type="submit">Sign in</button>
    </form>
</body>
</html>
~~~

In Spring MVC/Thymeleaf integration, processing a `th:action` form normally adds a hidden CSRF field automatically through Spring's mechanism. Inspect the generated HTML to ensure the token is sent. If using static HTML or a template engine without this support, retrieve the server-provided CSRF token and place it in the appropriate field. Do not fix 403 by disabling CSRF globally.

`@Controller` returns `"signin"` for the view resolver to load the template. `@RestController` writes the literal string `signin` into the response body and does not replace `@Controller`'s template rendering role.

### Redirect loop if the login page is not public

If `GET /signin` also requires authentication:

~~~text
GET /dashboard → 302 /signin
GET /signin    → 302 /signin
GET /signin    → 302 /signin
...
~~~

Make sure the login page path and required assets are accessible while unauthenticated, and that the GET signin handler exists. Loops can also occur when the cookie/session is not preserved after login.

## 9. CSRF: why can POST /login return 403?

Traditional form login operates in a browser and typically uses a session cookie. Spring Security protects state-changing requests by default with CSRF:

| Request | Condition | Common result |
| --- | --- | --- |
| `GET /login` | No need to submit username/password | Displays login page |
| `POST /login` | Valid username/password, valid CSRF | Authentication succeeds, redirect |
| `POST /login` | Wrong password, valid CSRF | Redirect to error page |
| `POST /login` | Missing/invalid CSRF | 403 before authentication step completes |
| `POST /logout` | Valid CSRF | Logs out and redirects |
| `POST /logout` | Missing/invalid CSRF | 403 |

A 403 response **does not prove the user entered the wrong password**. It can come from `CsrfFilter` before form login is processed. In MockMvc tests, `.with(csrf())` lets you test the actual authentication branch. In a browser, the token comes from the server-rendered page; never hardcode a token in production HTML.

Enable HTTPS, configure cookies and sessions appropriately, and keep CSRF protection active for browsers using cookies. For APIs not relying on session cookies, the protection approach may differ, but it must be based on the actual authentication architecture.

## 10. Session cookie, SecurityContext, and session fixation

Traditional form login typically stores authentication state in a server-side session. The browser carries the session identifier cookie on subsequent requests, usually `JSESSIONID` in a Servlet environment.

~~~http
HTTP/1.1 302 Found
Set-Cookie: JSESSIONID=example-session-id; Path=/; HttpOnly
Location: /dashboard
~~~

This is a **protocol illustration**, not a real cookie. The browser then sends the cookie on the next GET:

~~~http
GET /dashboard HTTP/1.1
Host: localhost:8080
Cookie: JSESSIONID=example-session-id
~~~

On the server, `SecurityContextRepository` handles saving/loading `SecurityContext`, which holds the `Authentication` information. Spring Security 6 requires explicit saving when creating authentication manually in a custom filter or Controller; **merely setting Authentication into `SecurityContextHolder` for one request does not guarantee subsequent requests remain logged in**. The standard form login filter performs its own context management/persistence step.

To defend against *session fixation* (an attacker pre-sets a session ID and tricks the user into logging in), Spring Security supports changing the session ID upon successful login. On modern Servlet containers, the typical strategy is `changeSessionId`. Therefore, do not treat a session ID changing after login as a bug.

In production, verify `Secure`, `HttpOnly`, `SameSite`, `Path`, `Domain`, HTTPS, and reverse proxy settings. If the browser does not send the session cookie after login, you can get redirected back to login even with the right password.

## 11. Logout and post-logout redirect

With `.logout(Customizer.withDefaults())`, a valid logout operation clears/releases the login state as configured (clearing context, handling session, etc.) and typically returns:

~~~http
HTTP/1.1 302 Found
Location: /login?logout
~~~

For browsers with CSRF enabled, send a POST logout with a valid token; an arbitrary GET link cannot substitute for a safe POST form:

~~~html
<form th:action="@{/logout}" method="post">
    <button type="submit">Sign out</button>
</form>
~~~

The snippet above is for Thymeleaf with proper CSRF integration. In applications with SSO/OIDC/remember-me, logout also involves issues such as the Identity Provider session and remember-me tokens; this example only describes basic Servlet form login.

## 12. Cases where redirect and login behave unexpectedly

| Symptom | Cause to check |
| --- | --- |
| GET /dashboard returns 302 /login | Unauthenticated; this can be the normal flow |
| GET /login returns 404 | Custom page has no handler/view yet; wrong login URL |
| GET /signin keeps redirecting to /signin | Login page is protected, missing `permitAll()` |
| POST /login gets 403 | Invalid or missing CSRF |
| POST /login redirects to /login?error | Wrong credentials or authentication failure |
| POST /perform-login returns 404 | Form action does not match `loginProcessingUrl` |
| Valid login returns to a different URL | SavedRequest missing/gone or configured success URL takes precedence |
| Login succeeds then redirects back to login | Cookie/session/SecurityContext not persisted across requests |
| Logged in but /admin returns 403 | User lacks `ROLE_ADMIN`, distinct from login failure |
| POST /logout returns 403 | Missing CSRF |
| SPA API receives login HTML | Page redirect mechanism does not match JSON API contract |

A 302 request can belong to the unauthenticated step, successful login, or failed login. Inspect the **target URL in Location** and verify the subsequent request sequence.

### Distinguishing multi-page websites from JSON APIs

Form login and redirects suit browsers navigating HTML. For SPAs/mobile clients calling `fetch` and expecting JSON, a redirect to an HTML login page can cause the client to mishandle the response. The application should define an appropriate `AuthenticationEntryPoint`/401 response for APIs or separate `SecurityFilterChain` configurations for web and API according to a clear design. If an API still uses cookies, CSRF must still be evaluated.

### Distinguishing redirect and forward

- **Redirect**: server returns 3xx and `Location`; browser sends a new request, and the URL can change.
- **Forward**: Servlet dispatches processing internally within the same request; the browser does not send a second request.
- `defaultSuccessUrl` usually controls redirects. Forward options in form login have different semantics; do not swap them arbitrarily.

## 13. Common security mistakes

1. **Writing a form that uses GET to send passwords.** Passwords can leak in URLs, history, and logs; use POST over HTTPS.
2. **Forgetting to enable formLogin after defining a custom SecurityFilterChain.** Do not assume the default login page always exists.
3. **Confusing GET /login with POST /login.** One returns HTML, the other receives authentication credentials.
4. **Failing to make the custom login page public.** Causes redirect loops or failure to load CSS/JS.
5. **Wrong form field names.** `name="email"` needs matching configuration `usernameParameter("email")` if not using the default username.
6. **Not sending CSRF.** POST login/logout can be blocked before credentials are checked.
7. **Storing plaintext passwords or comparing raw passwords manually.** Use an appropriate `PasswordEncoder`.
8. **Disabling session fixation protection.** Increases the risk of an attacker knowing the session ID used after login.
9. **Not saving SecurityContext in custom authentication mechanisms.** Subsequent requests can revert to anonymous state.
10. **Accepting unchecked redirect URLs from the client.** Can create open redirects.
11. **Assuming every resource is allowed after login.** The user still needs specific roles/authorities.
12. **Automatically replaying business POST requests after login.** Do not rely on saved requests to automatically resend bodies or confirm transactions.
13. **Testing only a single POST /login.** You must test the full sequence GET protected → POST login → GET protected in the same session.
14. **Equating the presence of a cookie with being authenticated.** The cookie may be invalid, expired, or fail to carry a SecurityContext.
15. **Observing only the final status.** Browsers follow redirects automatically; enable Preserve log to inspect each intermediate response.

## 14. Self-check exercises

**Question 1:** An unauthenticated user calls `GET /dashboard` and receives `302 Location: /login`. Who sends the next `GET /login`?

**Answer:** The browser, following the Location header. This is a new HTTP request.

**Question 2:** With the default form login configuration, do you need to write `@PostMapping("/login")` yourself?

**Answer:** No. `UsernamePasswordAuthenticationFilter` handles POST at the login processing URL.

**Question 3:** Logging in with the right password but missing CSRF returns 403. Can you conclude the password was wrong?

**Answer:** No. CSRF can block the request before authentication runs.

**Question 4:** A user opens `/dashboard` before logging in, logs in, and returns to dashboard. Which component typically helps remember the destination?

**Answer:** `RequestCache`/`SavedRequest` and the authentication success handler that prioritizes the saved request.

**Question 5:** What happens when an authenticated user with `ROLE_USER` accesses `/admin` protected by `hasRole("ADMIN")`?

**Answer:** The authorization condition is not met, typically resulting in a 403 denial. Successful login does not grant the ADMIN role.

**Question 6:** If you want to always redirect to `/home` after login even when a saved request exists, what do you configure?

**Answer:** `defaultSuccessUrl("/home", true)` and ensure the user is allowed to access `/home`.

**Question 7:** A custom login page redirects to itself infinitely. What should you check?

**Answer:** Whether the login route exists, has public `permitAll()` access, has matching loginPage/loginProcessingUrl configuration, and whether cookies/sessions are not being lost.

**Question 8:** Why does the same browser still get prompted to log in when doing a GET on another page after a valid POST login?

**Answer:** The session cookie is not being sent, SecurityContext is not being saved/read properly, or the application uses a stateless mode incompatible with that assumption.

## 15. Pre-production checklist

- Have the login display URL, POST processing URL, and post-login URL been clearly separated?
- Can the login page and essential assets load while anonymous?
- Do the username/password field names and form action URL match the filter?
- Are valid CSRF tokens included for login/logout forms?
- Do PasswordEncoder, account storage, password management, and error policies meet requirements?
- Have session fixation protection, timeout, and logout been tested?
- Do session cookies have appropriate Secure, HttpOnly, SameSite, Path, and Domain settings when using HTTPS?
- Do saved requests and the default URL behave properly with multiple tabs, nonexistent paths, and unauthorized URLs?
- Are redirect targets restricted to prevent open redirects?
- Have unauthenticated, wrong password, missing CSRF, valid password, missing role, and logout branches been tested?
- If there is a JSON API or WebFlux, have the authentication entry point and context mechanism been designed for the right application type?

**Key takeaway:** Servlet form login has **three distinct steps**: redirect to the login page, POST authentication, then redirect/continue the saved request. Inspecting each method, URL, status, Location, and cookie in the browser tells you accurately which step failed.

## References

- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/6.3/servlet/authentication/passwords/form.html): default and custom forms.
- [Spring Security — Persisting Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html): security context across requests.
- [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.3/servlet/authentication/session-management.html): sessions and session fixation.
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/6.3/servlet/exploits/csrf.html): CSRF for forms.
- [Spring Security — Logout](https://docs.spring.io/spring-security/reference/6.3/servlet/authentication/logout.html): logout and redirects.
- [Spring Security — MockMvc Integration](https://docs.spring.io/spring-security/reference/6.3/servlet/test/mockmvc/index.html): testing with the security filter chain.
