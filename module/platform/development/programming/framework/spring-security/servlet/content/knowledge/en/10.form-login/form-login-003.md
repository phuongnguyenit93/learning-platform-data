# UsernamePasswordAuthenticationFilter and How Login Credentials Are Received

> **Topic:** Spring Security — Servlet stack. **Group:** Form Login. Examples use Java 17+, Spring Boot 3.x, and Spring Security 6.x.

## 1. The Big Picture: Receiving Credentials vs. Verifying Credentials

When a user submits a login form containing a username and password, Spring Security Servlet needs a component to **receive the HTTP request**, extract data by convention, construct an authentication request, and forward it to the authentication system. The component normally responsible for that in form login is **`UsernamePasswordAuthenticationFilter`**.

This filter does not query the database or compare passwords itself. It acts as the "intake gate" (authentication processing filter):

1. Determines whether the request is a **login attempt** this filter is responsible for.
2. Reads the username and password values from request parameters; by default `username` and `password`.
3. Creates a `UsernamePasswordAuthenticationToken` in an **unauthenticated** state.
4. Passes the token to `AuthenticationManager.authenticate(...)`.
5. Receives either a successful result or an `AuthenticationException`, then executes the success/failure branch according to the pipeline inherited from `AbstractAuthenticationProcessingFilter`.

Other critical responsibilities belong to other components:

- `AuthenticationManager` and `AuthenticationProvider`: verify credentials, account status, and matching authentication configuration.
- `PasswordEncoder`: matches the received password against the **hashed** password in the data store.
- `SecurityContextHolder`/`SecurityContextRepository`: manages the authentication result for the current request and subsequent requests, depending on session policy.
- `AuthenticationSuccessHandler`/`AuthenticationFailureHandler`: produces a redirect or HTTP response after a login attempt.
- `AuthorizationFilter`: decides whether a request reaching a resource is permitted based on authorities and rules.
- `CsrfFilter`: validates the anti-CSRF token for protected requests; it can block a login POST **before** the login filter runs.

**Short takeaway:** `UsernamePasswordAuthenticationFilter` reads *the input of a login attempt*, not a "password-handling controller," and it is not where you specify which endpoint requires `ROLE_ADMIN`.

## 2. Position in the Servlet `SecurityFilterChain`

A typical form login flow:

```text
Browser / client
  |
  | POST /login
  | Content-Type: application/x-www-form-urlencoded
  | username=alice&password=(user-entered value)
  | CSRF token + session cookie (when applicable)
  v
Servlet container
  |
DelegatingFilterProxy ("springSecurityFilterChain")
  |
FilterChainProxy selects the first matching SecurityFilterChain
  |
  +--> SecurityContext / CSRF / pre-login filters
  |       |
  |       +--> Invalid CSRF: may return 403, login filter does not run
  |
  +--> UsernamePasswordAuthenticationFilter
          |
          +--> Does RequestMatcher match login-processing URL + method?
          |       | No -> pass request down the filter chain
          |       | Yes
          |       v
          |   Read username/password from request parameters
          |       |
          |   UsernamePasswordAuthenticationToken (unauthenticated)
          |       |
          |   AuthenticationManager
          |       |
          |       +--> AuthenticationProvider (e.g., DaoAuthenticationProvider)
          |               |
          |               +--> UserDetailsService + PasswordEncoder
          |               +--> check credentials / account status
          |       |
          |       +--> OK: authenticated Authentication
          |       |         |
          |       |         +--> handle session/context/remember-me
          |       |         +--> AuthenticationSuccessHandler
          |       |                  |
          |       |                  +--> redirect or success response
          |       |
          |       +--> AuthenticationException
          |                 |
          |                 +--> AuthenticationFailureHandler
          |                          |
          |                          +--> redirect to login error page
          |
          v
    Does not necessarily reach a POST /login controller
```

This is a conceptual diagram; actual filter chains include many other security components and ordering can vary by configuration. The core point is that **a login request can be handled directly by a Servlet filter**, with no `@PostMapping("/login")` controller required at all.

### Two Layers of Matchers to Distinguish

- `HttpSecurity.securityMatcher(...)` decides whether **the entire `SecurityFilterChain`** applies to the request. If the login POST falls **outside** the scope of the chain containing `UsernamePasswordAuthenticationFilter`, that filter cannot receive the request.
- The matcher on `AbstractAuthenticationProcessingFilter` itself decides **which request within the chain** triggers an authentication attempt. For default form login, that is `POST /login`.
- Rules in `authorizeHttpRequests(...requestMatchers(...))` govern **authorization** when the request reaches that step; they do not replace the matcher that triggers login processing.

Therefore, writing only `requestMatchers("/login").permitAll()` does not mean you created a password verification mechanism. Conversely, merely configuring form login does not automatically protect every URL if you define multiple filter chains or leave certain paths uncovered.

## 3. Defaults: HTTP Method, URL, and Parameter Names

In a standard configuration with `formLogin` enabled, `UsernamePasswordAuthenticationFilter` uses these conventions:

| Component | Default/characteristic | Why it matters |
| --- | --- | --- |
| Login processing URL | `/login` | HTTP destination where the filter attempts authentication |
| HTTP method | `POST` | `GET /login` is for viewing the login page, **not** submitting a password to authenticate |
| Username parameter | `username` | Field name read via `request.getParameter(...)` |
| Password parameter | `password` | Field name holding the credential |
| Web form request body | Typically `application/x-www-form-urlencoded` | The Servlet container maps form fields to request parameters |
| Login page | May be a Spring Security-generated GET `/login` if no custom page is declared | Do not confuse the HTML page with the POST handler |
| Success response | Usually redirects to the saved request or default page | Depends on `AuthenticationSuccessHandler` |
| Failure response | Usually redirects to `/login?error` | Depends on `AuthenticationFailureHandler` |
| CSRF | Enabled by default in standard Servlet web configs | Form POST needs a valid CSRF token when CSRF applies |

Example form-style HTTP request:

```http
POST /login HTTP/1.1
Host: localhost:8080
Content-Type: application/x-www-form-urlencoded

username=alice&password=correct-horse-battery-staple
```

This example only illustrates **form content**, not a complete request for an app with CSRF enabled; a real request usually must carry a **valid CSRF token** and associated cookie/session. Do not use example passwords as real credentials.

### Why Is `GET /login` Not Treated as an Authentication Attempt?

GET usually renders the HTML form. The default filter only treats POST to the login processing URL as a credential-processing request. Putting username and password in the URL `/login?username=...&password=...` not only violates the default form login protocol, it also risks leaking passwords in URLs, access logs, browser history, and referrers.

Do not change the filter to accept GET just for "quick testing." Always use POST over HTTPS with proper CSRF token/policy handling.

### `/login` as Login Page vs. Login Processing URL Have Different Roles

In the default configuration, GET and POST can share the `/login` path with different methods:

```text
GET  /login -> DefaultLoginPageGeneratingFilter can generate login HTML
POST /login -> UsernamePasswordAuthenticationFilter attempts authentication
```

If you build your own login page, GET is served by an MVC controller/template, while POST can continue to be handled by `UsernamePasswordAuthenticationFilter`. You **do not need** to create a `@PostMapping` calling `AuthenticationManager` when `formLogin` is configured properly.

## 4. `attemptAuthentication`: What Does the Filter Actually Do with Parameters?

`UsernamePasswordAuthenticationFilter` extends `AbstractAuthenticationProcessingFilter`. When a request matches the matcher, it calls `attemptAuthentication(request, response)` to create an authentication attempt.

The Java pseudocode below describes the main typical behavior; **this is not verbatim source code from all Spring Security versions and does not compile standalone**:

```java
// Pseudocode inside UsernamePasswordAuthenticationFilter.
String username = obtainUsername(request);  // request parameter
String password = obtainPassword(request);  // request parameter

if (username == null) {
    username = "";
}
if (password == null) {
    password = "";
}

username = username.trim();                  // username only

UsernamePasswordAuthenticationToken attempt =
    UsernamePasswordAuthenticationToken.unauthenticated(
        username, password);

setDetails(request, attempt);                // authentication details
return getAuthenticationManager().authenticate(attempt);
```

Several details worth remembering:

- `obtainUsername(...)` reads the parameter name configured via `getUsernameParameter()`; `obtainPassword(...)` reads `getPasswordParameter()`.
- By standard behavior, the filter **trims the username** after reading it; it does not automatically trim the password. A password is secret data that may contain intentional whitespace and must not be silently altered, which would cause valid logins to fail.
- If a parameter is missing, the filter uses an empty string for the authentication attempt rather than creating a special "user session."
- The created token is **unauthenticated**. Only `AuthenticationManager` and the appropriate provider verify credentials and return an authenticated result.
- `setDetails` usually captures request metadata (such as connection/session info via `WebAuthenticationDetailsSource`), **not** a step that decides whether username/password are valid.
- Wrong password, locked account, disabled account, etc. belong to authentication provider/account checks; sending the user-facing response falls to the failure handler.

### Do Not Mark Client Input `authenticated=true` Yourself

The following snippet is **a trust-boundary violation** if code blindly accepts data from the request:

```java
// Do not use unverified input to assert that a user is already logged in.
String username = request.getParameter("username");
Authentication forged =
    new UsernamePasswordAuthenticationToken(
        username, null, java.util.List.of());
SecurityContextHolder.getContext().setAuthentication(forged);
```

The constructor taking an authorities collection creates a `UsernamePasswordAuthenticationToken` marked as authenticated; this code can cause Spring Security to trust an identity **whose password was never checked**. You must pass an unauthenticated token through `AuthenticationManager` instead of planting it directly in `SecurityContext`.

## 5. Difference Between `UsernamePasswordAuthenticationToken` and `UsernamePasswordAuthenticationFilter`

The two names sound similar, yet the objects perform different jobs:

| Component | Nature | Responsibility |
| --- | --- | --- |
| `UsernamePasswordAuthenticationFilter` | Servlet `Filter` dedicated to handling login attempts | Matches URL/method, reads request params, creates authentication attempt, calls manager, coordinates result via parent filter |
| `UsernamePasswordAuthenticationToken` | Implementation of the `Authentication` interface | Carries principal/credentials (and authorities once authenticated) |
| `AuthenticationManager` | Authentication API | Dispatches `authenticate(...)` to providers |
| `DaoAuthenticationProvider` | Provider for username/password with `UserDetailsService` | Loads user, checks account status, compares password via encoder |
| `UserDetailsService` | User retrieval API | Provides `UserDetails`; does not hash or compare passwords per its interface contract |
| `AuthenticationSuccessHandler` | Success response callback | Redirect, saved-request handling, or other response |
| `AuthenticationFailureHandler` | Failure response callback | Redirect/error payload when an authentication attempt fails |

When debugging, state clearly whether you mean **the filter receiving the request** or **the token carrying credentials**. An unauthenticated `UsernamePasswordAuthenticationToken` does not mean the user succeeded in logging in.

## 6. Success and Failure: The Parent Filter's Lifecycle

`AbstractAuthenticationProcessingFilter` manages the branches after `attemptAuthentication` returns:

**Success (overview):**

1. The provider verifies credentials and returns a valid `Authentication`.
2. The session authentication strategy is applied per configuration (e.g., session fixation protection for form/session-based login).
3. The framework updates `SecurityContext` and can persist it via the configured `SecurityContextRepository`.
4. Remember-me services and authentication event publishing are notified if configured.
5. `AuthenticationSuccessHandler` determines the HTTP redirect or response.

**Failure (overview):**

1. The authentication attempt throws an `AuthenticationException`.
2. The framework clears the context for the failed authentication attempt per the appropriate flow.
3. The remember-me service, if present, is notified of the failure.
4. `AuthenticationFailureHandler` determines the response/redirect.

Depending on the filter/version, auxiliary tasks have specific details; do not use this illustrative order to hand-roll replacements for the entire context/session machinery.

One important variation: `attemptAuthentication(...)` can return `null` when an authentication mechanism needs to **proceed through another step**; the parent filter then understands the process is not complete and skips the success/failure branch as it would for a returned authentication or thrown exception. With standard username/password form login, the normal branch completes within the same authentication attempt.

### When Are the Handlers Not Called?

If a POST is blocked by `CsrfFilter` due to a missing token, the request **may never reach** `UsernamePasswordAuthenticationFilter`, so no success/failure callback runs. If the wrong URL or wrong HTTP method is called, the login filter's matcher does not match; the request can pass on to other authorization/controllers and receive a redirect, 403, or 404 depending on configuration.

Hence, status 403 does not necessarily mean a wrong password; similarly, status 302 to `/login` does not prove a failed authentication attempt occurred.

## 7. Default and Custom Configuration with `formLogin`

The standard approach is configuring the DSL on `HttpSecurity`, **without manually registering `UsernamePasswordAuthenticationFilter`**:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/account").authenticated()
            .anyRequest().denyAll()
        )
        .formLogin(form -> form.permitAll())
        .build();
}
```

This is a `SecurityFilterChain` fragment; it needs imports and appropriate bean/configuration setup. If the application does not have a custom login page yet, Spring Security can generate a default login page. When the user submits the form, the filter handles the POST per configuration.

### Changing URL/Field Names Properly

You can change the login processing path and the field names read by the filter:

```java
.formLogin(form -> form
    .loginProcessingUrl("/auth/signin")
    .usernameParameter("email")
    .passwordParameter("passcode")
    .defaultSuccessUrl("/profile", false)
    .failureUrl("/login?error")
    .permitAll()
)
```

This configuration means:

- `loginProcessingUrl("/auth/signin")`: the filter **handles POST `/auth/signin`**; do not write a business controller for `/auth/signin`.
- `usernameParameter("email")`: the filter reads `request.getParameter("email")`; you can accept an email as the login identifier, provided `UserDetailsService` looks up that identifier.
- `passwordParameter("passcode")`: the filter reads `request.getParameter("passcode")`; it does not change the `PasswordEncoder` algorithm.
- `defaultSuccessUrl("/profile", false)`: uses `/profile` when there is no prioritized saved request; does not force discarding saved requests.
- `failureUrl("/login?error")`: redirects back to the login page with a generic error flag.
- `permitAll()`: permits the URLs needed by form login per configuration; does not make the entire application public.

If the frontend still submits fields `username`/`password` to `/auth/signin` while the server expects `email`/`passcode`, the filter will not receive the expected credentials and authentication will typically fail. Check **all three simultaneously: URL, method, and field names**.

### `loginPage` Is Not `loginProcessingUrl`

`loginPage("/signin")` indicates the HTML page URL that the browser requests via GET (and when using a custom page, you must serve that page yourself). `loginProcessingUrl("/auth/signin")` indicates the POST URL where the filter processes login credentials. They can be the same or different, but neither substitutes for the other's role.

When configuring `loginPage(...)` yourself, Spring Security **no longer auto-generates that login page**. You need a controller/template and must ensure the login page GET route, submission URL, and CSRF are all valid.

## 8. Complete Example: Spring Boot 3.x, Java 17+, Custom Login POST

The example below builds a runnable Spring MVC Servlet application with Spring Boot 3.x/Spring Security 6.x. Its purpose is to demonstrate:

- The Spring Security filter receives **POST `/auth/signin`**.
- The two configured parameters are `email` and `passcode`, rather than `username` and `password`.
- `AuthenticationManager` and `UserDetailsService` verify the account.
- Success redirects to `/profile` when there is no saved request.
- A wrong password returns to `/login?error`; anonymous `GET /profile` initiates the login flow.

In a Gradle Spring Boot project with plugins and dependency management already configured, include:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

Create the file `src/main/java/example/formfilter/FormFilterApplication.java`:

```java
package example.formfilter;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class FormFilterApplication {

    public static void main(String[] args) {
        SpringApplication.run(FormFilterApplication.class, args);
    }
}

@Configuration
class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/admin")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/profile")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .formLogin(form -> form
                // URL triggering UsernamePasswordAuthenticationFilter.
                .loginProcessingUrl("/auth/signin")
                // Request parameter names read by the filter.
                .usernameParameter("email")
                .passwordParameter("passcode")
                // If there is no saved request, go to /profile.
                .defaultSuccessUrl("/profile", false)
                .failureUrl("/login?error")
                .permitAll()
            )
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
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
class DemoController {

    @GetMapping("/profile")
    String profile(Authentication authentication) {
        return "Hello " + authentication.getName();
    }

    @GetMapping("/admin")
    String admin() {
        return "Admin only";
    }
}
```

**Explanation of why it runs:** only `FormFilterApplication` is a `public` class; the other two top-level classes are package-private, which is valid in a single Java 17 file. `@SpringBootApplication` scans package `example.formfilter`, finding the security configuration and controller. The example does not write `@PostMapping("/auth/signin")` because `UsernamePasswordAuthenticationFilter` in form login handles that request directly.

**About username "email":** changing `usernameParameter("email")` only changes **the request field name**; it does not enforce validation that the string is formatted as an email address. In the demo, `learner` and `admin` are usernames mapped onto the `email` field. If a real product logs in by email, `UserDetailsService`/the identity directory must support looking up accounts by email, normalizing input, and enforcing proper tenant boundaries.

**About the generated login page:** because `.loginPage(...)` is not called, Spring Security can auto-generate `GET /login` for form login in the standard setup. When changing parameter names or the login processing URL, inspect the actual HTML form to confirm its action and field names reflect your configuration. When building your own UI, you must render the exact names and action.

### Running the Application

In a Gradle Spring Boot project with the wrapper:

```bash
./gradlew bootRun
```

On Windows PowerShell: `./gradlew.bat bootRun`.

Once the server runs locally on `http://localhost:8080`, visit `/profile` in a browser while unauthenticated. Expected behavior is that the browser redirects to the login page. Submit the valid form with fields `email=learner` and `passcode=demo-pass`: if there is no other saved request, the app redirects back to `/profile`, and the controller returns:

```text
Hello learner
```

If the browser previously tried to open `/admin`, `SavedRequestAwareAuthenticationSuccessHandler` may prioritize the saved request and redirect to `/admin`. For regular user `learner`, that request is still denied by `hasRole("ADMIN")`. **Successful login does not imply having admin privileges**.

These are **expected results from the code**, not output captured from a live run; the HTTP `Location` may be a relative or absolute URL depending on container/proxy/context path.

## 9. Real HTTP Formats: form-urlencoded, JSON, and Mismatched Fields

### 9.1. Form-urlencoded Is the Default Path

Browsers normally submit `<form method="post">` using `application/x-www-form-urlencoded`; the Servlet container converts each field into a request parameter and the filter uses `request.getParameter(...)`.

An illustrative form when serving your own HTML page:

```html
<form method="post" action="/auth/signin">
  <label for="email">Account</label>
  <input id="email" name="email" autocomplete="username" required>

  <label for="passcode">Password</label>
  <input id="passcode" type="password" name="passcode"
         autocomplete="current-password" required>

  <button type="submit">Sign in</button>
</form>
```

**Warning:** the HTML fragment above only illustrates `action`/`method`/`name`; **it is not sufficient to submit to an app with CSRF enabled**. A real page must include the CSRF hidden input (with parameter name/token provided by the framework, plus the required session/cookie). If using Thymeleaf or a template engine integrated with Spring MVC CSRF, use the framework's CSRF rendering mechanism rather than crafting tokens client-side. Also properly escape server-rendered values to prevent XSS.

If the application uses a context path other than `/`, do not hardcode an action that breaks the prefix; use your template/framework URL generation.

### 9.2. Sending JSON Does Not Automatically Become Form Login

The following request looks reasonable for a JSON API, yet **is not parsed as JSON by the default `UsernamePasswordAuthenticationFilter`**:

```http
POST /auth/signin HTTP/1.1
Host: localhost:8080
Content-Type: application/json

{"email":"learner","passcode":"demo-pass"}
```

The default filter reads request parameters; it does not call Jackson to deserialize a JSON body. Changing field names via `.usernameParameter(...)` does not enable JSON parsing. If you genuinely need JSON login, design a dedicated authentication filter/converter or authentication endpoint wired properly to `AuthenticationManager`, security context, session policy, CSRF protection, and response handling. Do not read raw JSON in a controller and set `SecurityContextHolder` to authenticated while bypassing the authentication manager.

### 9.3. Do Not Send Credentials in Query Strings

With Servlet `request.getParameter(...)`, parameters can come from either the query string or form body depending on the request/container. **Design clients to send credentials only in the POST body**; do not treat the filter's ability to read a parameter as a guarantee that passwords only came from the body. URLs containing credentials can be recorded in logs, reverse proxies, monitoring, browser history, and referrers.

Therefore, to enforce strict policies, design request validation, log redaction, and (if needed) Content-Type checks at the proper boundary. Do not trust client-asserted metadata (headers, Content-Type, Origin) as proof of authentication.

## 10. CSRF and Form Login: Why a Missing Token Can Return 403

Form login is typically used with browser cookies/sessions. Browsers attach cookies automatically, so the POST login endpoint must be evaluated under the **CSRF threat model**. In standard Spring Security Servlet, CSRF protection is enabled by default and `CsrfFilter` can run before `UsernamePasswordAuthenticationFilter`.

Compare:

```text
POST /auth/signin
  method/path/fields all valid
  wrong password
  valid CSRF
    -> authentication attempt takes place
    -> provider throws AuthenticationException
    -> failure handler redirects /login?error

POST /auth/signin
  method/path/fields all valid
  correct password
  missing or invalid CSRF
    -> CsrfFilter rejects (typically HTTP 403)
    -> does not reach the login filter
    -> form login failure handler is not called
```

**Therefore, do not add `http.csrf(...disable...)` just to make a POST login test pass.** With `MockMvc`, Spring Security Test provides the `.with(csrf())` helper. With browsers, the form should be server-rendered with a CSRF token and consistent cookie/session. With APIs using bearer tokens and no browser-auto-attached credentials, CSRF can be designed differently, but analyze the actual mechanism and clients before disabling it.

Related yet independent concerns:

- **HTTPS/TLS:** passwords must travel over an encrypted channel in real deployments; TLS termination at a reverse proxy must be configured properly.
- **SameSite/HttpOnly/Secure cookies:** reduce certain session risks, but do not replace full CSRF protection.
- **Session fixation:** upon successful authentication, an appropriate session strategy can rotate the session ID; never copy session IDs into business logs or responses.
- **Rate limiting:** defend against brute force, password spraying, and credential stuffing at the identity service, filter, or gateway layer.
- **Do not log passwords:** never log `request.getParameter("passcode")`, raw form bodies, `Authentication`, or headers containing credentials.

## 11. Practical Testing with MockMvc

In the example app above, add the test dependencies:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Create `src/test/java/example/formfilter/FormLoginFilterTest.java`:

```java
package example.formfilter;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class FormLoginFilterTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousOpeningProfileStartsLogin() throws Exception {
        mvc.perform(get("/profile"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                "Location", containsString("/login")));
    }

    @Test
    void customFieldNamesAreAcceptedByLoginFilter() throws Exception {
        mvc.perform(post("/auth/signin")
                .with(csrf())
                .param("email", "learner")
                .param("passcode", "demo-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                "Location", containsString("/profile")));
    }

    @Test
    void wrongPasswordUsesAuthenticationFailureHandler() throws Exception {
        mvc.perform(post("/auth/signin")
                .with(csrf())
                .param("email", "learner")
                .param("passcode", "wrong-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                "Location", containsString("/login?error")));
    }

    @Test
    void defaultNamesNoLongerMatchCustomFieldNames() throws Exception {
        mvc.perform(post("/auth/signin")
                .with(csrf())
                .param("username", "learner")
                .param("password", "demo-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                "Location", containsString("/login?error")));
    }

    @Test
    void missingCsrfTokenIsRejectedBeforePasswordCheck()
            throws Exception {
        mvc.perform(post("/auth/signin")
                .param("email", "learner")
                .param("passcode", "demo-pass"))
            .andExpect(status().isForbidden());
    }

    @Test
    void regularUserCannotUseAdminRole() throws Exception {
        mvc.perform(get("/admin")
                .with(org.springframework.security.test.web.servlet
                    .request.SecurityMockMvcRequestPostProcessors
                    .user("learner").roles("USER")))
            .andExpect(status().isForbidden());
    }
}
```

Run tests with the Gradle wrapper:

```bash
./gradlew test
```

These tests are **expected code** for a project with the stated dependencies/versions and have not been executed inside this article. `MockMvc` supplies a valid CSRF token so the tests focus on the login filter. The last test uses a simulated authenticated principal with `ROLE_USER` to prove **authorization is not the same as authentication**; it does not re-verify passwords through `UsernamePasswordAuthenticationFilter`.

You can add tests that save the session after login, then `GET /profile` with the same cookie/session, and test session fixation separately. Avoid concluding that a single successful POST redirect proves every subsequent request stays authenticated; sessions and `SecurityContextRepository` have their own lifecycle.

## 12. Distinguishing Often-Conflated Errors

A scenario table for quick diagnosis:

| Request | Does the login filter try to authenticate? | Behavior / what to check |
| --- | --- | --- |
| GET `/login` | No | Login page is returned (default or custom) |
| POST `/auth/signin`, valid CSRF, right fields, right password | Yes | AuthenticationManager → success handler |
| POST `/auth/signin`, valid CSRF, wrong password | Yes | AuthenticationException → failure handler |
| POST `/auth/signin`, invalid CSRF | Usually no | CsrfFilter may return 403 first |
| POST `/auth/signin`, wrong field names | May attempt, but credentials are empty | Authentication fails under standard provider configs |
| GET `/auth/signin` | No under default POST matcher | Continues down chain; authorization or another handler decides status |
| POST `/other-login` | No if processing URL is `/auth/signin` | Request goes to other filters/authorization |
| GET `/profile` when anonymous | No | Authorization triggers AuthenticationEntryPoint, usually redirecting to login |
| GET `/admin` by logged-in user lacking role | No | Authorization → access-denied handling, usually 403 |
| POST login JSON body, valid CSRF | URL/method matcher may match, but params are not read from JSON | Provider gets missing/empty fields; JSON is not parsed automatically |

This distinction is essential when the frontend reports "login error" while the backend returns 403 or 404: the root cause could be **CSRF**, **wrong URL**, **wrong HTTP method**, **wrong field name**, **wrong Content-Type**, **chain selection issues**, or **genuinely invalid credentials**.

## 13. Advanced Customizations and Known Limits

### 13.1. When to Configure `UsernamePasswordAuthenticationFilter` Directly?

Filter methods like `setUsernameParameter(...)`, `setPasswordParameter(...)`, `setRequiresAuthenticationRequestMatcher(...)`, and `setAuthenticationDetailsSource(...)` can be used when you **truly manage the filter instance and its chain position**. Yet for standard Servlet form login, the `.formLogin(...)` DSL is far safer: Spring Security wires the manager, handlers, security context, and related components according to your configuration.

If instantiating the filter manually:

- You must explicitly define **which chain** it is added to, before/after which filters, and with which matcher.
- You must wire the proper `AuthenticationManager` and configure success/failure behavior.
- You must ensure context/session persistence matches Spring Security 6 and your application's repository setup.
- Do not accidentally register **two login filters** handling the same URL or shadowing each other.
- Test request methods, CSRF, sessions, logout, logging, and security thoroughly.

In particular, simply writing `new UsernamePasswordAuthenticationFilter()` inside a `@Bean` does not mean Servlet `FilterChainProxy` will automatically pick up and execute that bean in the right order; it must be registered and configured in the proper chain.

### 13.2. JSON Login or Multiple Login Mechanisms

If traditional form login does not fit, you can use an authentication filter with a custom `AuthenticationConverter` or a carefully designed controller calling `AuthenticationManager`, managing security context, session strategy, CSRF, and responses according to your security contract. The choice depends on Spring Security version, client type, and threat model.

Do not arbitrarily override `attemptAuthentication` just to read JSON by copying legacy authentication code that is no longer compatible. Whether choosing a filter or endpoint, the critical boundary remains **untrusted input → `AuthenticationManager` verifies → auth state is established properly**.

### 13.3. Multiple `SecurityFilterChain` Beans

When you have a chain for `/api/**` and a chain for the web UI, `POST /auth/signin` must belong to the chain containing the corresponding `formLogin` configuration. If a chain has `securityMatcher("/web/**")` while the processing URL sits outside `/web/**`, the request **will not pass through that chain's login filter**.

A catch-all chain with higher `@Order` precedence than a specialized chain can also shadow the intended login filter. When a request misses the filter, check chain selection **before** debugging username/password.

### 13.4. Forwarded Headers and Reverse Proxies

If the app sits behind a reverse proxy, post-login redirect URLs may have the wrong scheme/host/port (e.g., redirecting to HTTP even though the public request was HTTPS). This is usually a trusted forwarded headers, TLS termination, and server base URL configuration issue, **not a username/password parser bug**. Only accept forwarded headers from trusted proxies; never use client-supplied `X-Forwarded-Host` to build redirects.

### 13.5. Sessionless Configurations and Form Login

Traditional form login is normally tied to a browser session. If `SessionCreationPolicy.STATELESS` is configured, post-login requests are not automatically treated as authenticated from a session as before; you must design a mechanism to carry credentials on subsequent requests. Do not apply a resource server's stateless configuration to form login and expect the server to still remember login state.

## 14. Diagnostic Checklist When "The Filter Doesn't Receive Username/Password"

If credentials are not processed as expected, inspect in order:

1. **Chain:** does the request URL enter the right `SecurityFilterChain` containing `formLogin`?
2. **Method:** does the request send POST rather than GET?
3. **Processing URL:** does the form action match `.loginProcessingUrl(...)`? Is any context path or gateway prefix rewriting the URL?
4. **Input:** do field names match `.usernameParameter(...)` and `.passwordParameter(...)`? Is the body sent as form URL encoding?
5. **CSRF:** is a valid token sent and matched to the cookie/session? If 403 is returned, which filter produced it?
6. **Authentication manager/provider:** is there a provider supporting `UsernamePasswordAuthenticationToken`?
7. **UserDetailsService:** does it look up the right username/email, right tenant, account status, and authorities?
8. **PasswordEncoder:** does the hash stored in the database match the expected format/encoder? Is raw password comparison avoided?
9. **Handlers:** are credential errors handled properly by the failure handler; does the success handler redirect to a URL the user is permitted to access?
10. **Session/context:** do post-login requests retain the cookie and security context per configuration? Are login errors being confused with session persistence errors?
11. **Logging:** enable controlled debug logging to inspect filter chain selection and high-level reasons; never dump passwords/request bodies/tokens.
12. **Rate limit/TLS:** protect the endpoint against brute force and ensure credentials never travel over plain HTTP.

To temporarily enable logging in development:

```yaml
logging:
  level:
    org.springframework.security: DEBUG
```

Disable or lower the log level once done. Never post logs containing sensitive data to public channels.

## 15. Common Pitfalls

| Pitfall | Why it is wrong | Right approach |
| --- | --- | --- |
| Thinking `UsernamePasswordAuthenticationFilter` verifies passwords itself | The filter only receives the request and delegates to manager/provider | Distinguish filter, token, manager, provider, and encoder |
| Writing `@PostMapping("/login")` alongside default form login unintentionally | The request may be intercepted by the filter before the controller | Choose one clear authentication processing flow |
| Using GET to send passwords | Credentials leak into URLs/logs; default matcher requires POST | Use POST body over HTTPS |
| Changing UI field to `email` while server still expects `username` | `getParameter("username")` misses the new field | Keep `usernameParameter(...)` in sync |
| Changing `loginProcessingUrl` while form action stays `/login` | Request fails to match the configured login filter | Sync the action URL and test |
| Sending JSON assuming the default filter parses JSON | `getParameter(...)` is not a JSON parser | Use form-urlencoded or a suitable authentication converter/filter |
| Blaming password when POST login returns 403 | CSRF filter may reject before authentication | Check CSRF/session, use `.with(csrf())` in MockMvc |
| Putting an authenticated `Authentication` into context directly from form input | Skips credential verification, creating a vulnerability | Call `AuthenticationManager` |
| Thinking login success grants all permissions | Authentication and authorization are separate decisions | Use `hasRole`/domain authorization |
| No chain covering the login path | Login filter never runs if path is outside chain scope | Design consistent matchers and chain order |
| Disabling CSRF or session protection to simplify demos | Weakens browser login security | Configure per threat model and test properly |
| Printing raw request parameters to debug | Exposes passwords, cookies, and tokens | Log error type/status/correlation ID and redact secrets |
| Returning specific exceptions to users | Can reveal account existence/lock status | Use generic error messages with proper internal auditing |

## 16. Practice Exercises

**Exercise 1.** An app sets `loginProcessingUrl("/auth/signin")`, `usernameParameter("email")`, and `passwordParameter("passcode")`. A POST request arrives at `/auth/signin` with valid CSRF, but the body contains `username=alice&password=123`. Will the filter process credentials as intended?

**Answer:** The URL and method match so the filter attempts authentication, yet `email` and `passcode` are absent from the request parameters; username/password evaluate to empty strings. With standard providers, authentication fails. Either frontend field names or server parameter names must be aligned.

**Exercise 2.** A user submits POST `/auth/signin` with the correct password, but without a CSRF token in a cookie/session-based form login app. Why might the response be 403 instead of a success redirect?

**Answer:** `CsrfFilter` checks CSRF first, so the request is rejected before `UsernamePasswordAuthenticationFilter` calls the authentication manager. The password was not necessarily checked at all.

**Exercise 3.** Why is `@PostMapping("/login")` in a controller not invoked when default form login handles the same POST URL?

**Answer:** The authentication filter inside Servlet `FilterChainProxy` intercepts the request before Spring MVC's dispatcher/controller, typically ending the request with a success or failure redirect.

**Exercise 4.** When a client sends `Content-Type: application/json` with body `{"email":"alice","passcode":"secret"}`, is setting `.usernameParameter("email")` enough for the filter to understand JSON?

**Answer:** No. The default filter reads servlet request parameters and does not deserialize JSON. Either form-urlencoded formatting or a custom authentication conversion mechanism is required.

**Exercise 5.** After a successful login, a regular user visits `GET /admin` and receives 403. Is this a bug in `UsernamePasswordAuthenticationFilter`?

**Answer:** Not necessarily. Authentication succeeded, while authorization on `/admin` requires `ROLE_ADMIN`. Inspect authorization rules and user authorities rather than modifying the password filter.

**Exercise 6.** In a setup with two chains: the web chain is scoped to `/ui/**`, the login processing URL is `/auth/signin`, and no other chain enables form login for that URL. Why is the POST request not authenticated?

**Answer:** The login processing URL sits **outside** the web chain's scope, so that chain's login filter never executes. Choose consistent URLs/chain scopes or ensure an appropriate chain covers login.

**Exercise 7.** Should you call `trim()` on passwords in a custom filter because users sometimes type extra spaces?

**Answer:** Do not silently alter passwords. Spaces can be part of a valid password. You may trim/normalize usernames according to a consistent policy; passwords must be handled as the exact secret string the user supplied.

## Conclusion

`UsernamePasswordAuthenticationFilter` is the **intake component for form login attempts** in Spring Security Servlet: it matches requests, reads username/password by parameter names, creates an unauthenticated `UsernamePasswordAuthenticationToken`, and delegates to `AuthenticationManager`. Results are coordinated through the security context/session and success/failure handlers.

To configure it properly, always verify **chain → POST URL → form field names → CSRF → provider/encoder → handlers → session/authorization**. Most applications should use `.formLogin(...)` rather than instantiating filters manually; only customize deeply when you understand the lifecycle and have matching security tests.
