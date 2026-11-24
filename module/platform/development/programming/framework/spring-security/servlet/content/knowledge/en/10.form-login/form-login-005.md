# CSRF Token in Login Forms — Spring Security Servlet

In a Spring MVC application using Spring Security, users typically open `GET /login` and submit a `POST /login` form with a username and password. A common misconception is that **you do not need a CSRF token before logging in**. In reality, the login operation changes the identity bound to the browser session. If CSRF protection is skipped, an attacker can attempt to force a victim's browser to log into an account controlled by the attacker — this is **login CSRF**.

With **Spring Security 6.x on the Servlet stack**, CSRF protection applies by default to state-changing HTTP methods, including the login-processing POST, unless the application alters the policy. Therefore, the login page must issue a valid token and the form must submit that token back in the same browser context; providing the right password alone is not enough.

This lesson uses Java 17+, Spring Boot 3.3.5, Spring MVC, Spring Security, and Thymeleaf. The APIs and paths shown apply to **form login + HTTP session**. Applications using SPAs, bearer tokens, or multiple security chains require evaluating their own authentication model; never copy a configuration that disables CSRF just to eliminate a 403 error.

## 1. Learning Objectives

After completing this lesson, you will be able to:

1. Distinguish **standard CSRF**, **login CSRF**, and invalid credentials errors.
2. Explain why `permitAll()` on the login page never disables `CsrfFilter`.
3. Describe the lifecycle `GET form → CSRF token → POST form + session cookie → CsrfFilter → authentication filter`.
4. Recognize `CsrfToken`, `CsrfTokenRepository`, `HttpSessionCsrfTokenRepository`, `CsrfTokenRequestHandler`, and Spring Security 6's token masking/deferred token mechanisms.
5. Include a CSRF token in forms using Thymeleaf; inspect the **rendered HTML**, not just the template source.
6. Write MockMvc tests for missing token, invalid token, valid token with wrong password, and successful login.
7. Analyze session timeout, login refresh, logout, multiple tabs, SPAs/cookies, and common 403 errors.

## 2. What Does CSRF Actually Attack?

**Cross-Site Request Forgery (CSRF)** occurs when an untrusted website tricks a browser into sending an unintended request to a target website. The browser may automatically attach identifying/authentication details such as a session cookie to the target request, depending on cookie settings, `SameSite`, and request context.

~~~text
User is browsing a malicious site
            |
            v
That page builds/triggers a POST request to the real site
            |
            v
Browser may automatically attach the real site's cookie
            |
            v
If the real site trusts only the cookie and lacks CSRF controls:
  a state-changing request can execute against the user's intent
~~~

The attacker **does not necessarily read** the real site's cookies, passwords, or responses. The crux is forcing the browser to send a request that did not originate from an intentional action on the trusted origin.

CSRF differs from:

- **XSS:** executing malicious JavaScript within the application's origin; XSS can also undermine CSRF defenses if scripts read tokens or issue same-origin requests.
- **Password guessing / credential stuffing:** trying leaked credentials; primary defenses include authentication, rate limiting, MFA, passkeys, and anomaly detection.
- **Session fixation:** attempting to fix/force a session ID before the victim logs in; session fixation protection does not replace blocking CSRF.
- **SQL injection:** injecting input to alter database queries; unrelated to the browser automatically attaching cookies.

### 2.1. Login CSRF Even When the Victim Is Not Logged In

Suppose an attacker owns the account `attacker-user` on a note-taking app. The attacker tries to make the victim's browser send:

~~~text
POST https://notes.example/login
username=attacker-user
password=<the attacker's own password>
~~~

If the server accepts the login POST without a protective token, the victim can be logged into **the attacker's account**. The victim continues writing notes thinking they are saved to their own account, while the attacker can read the data inside the account they own.

Thus, the impact of login CSRF **is not necessarily the attacker taking over the victim's account**; it can trick the victim into using the attacker's account by mistake, leading to data leakage or misassociation. Actual impact depends on product features.

An illustrative structural attack form:

~~~html
<!-- Threat model illustration only, not a feature to implement -->
<form action="https://notes.example/login" method="post">
  <input name="username" value="attacker-user">
  <input name="password" value="attacker-password">
</form>
~~~

This form **has no valid CSRF token**. Under a proper session-based CSRF policy, the request is rejected before the server completes login.

### 2.2. How Do Tokens Mitigate the Threat?

In the synchronizer token pattern, the server generates an unpredictable random token bound to the appropriate session/client state. When rendering the form, the legitimate site embeds the token in a hidden field. A malicious site on another origin cannot arbitrarily read the form/token if the same-origin policy is enforced properly and no other vulnerability exists.

When the browser submits the form, the server checks whether the token in the request matches the trusted data stored by the repository. A token from another session, a missing token, a tampered token, or an unresolvable token is rejected when CSRF protection applies.

Tokens are just one defense layer; you must still use HTTPS, proper cookie attributes, XSS prevention, session security, credential protection, and other authentication/authorization controls.

## 3. Request Sequence for `GET /login` and `POST /login`

~~~text
[1] Browser -> GET /login
      |
[2] Server creates/retrieves CsrfToken from repository when needed
      |
[3] Spring MVC + Thymeleaf render form with hidden CSRF field
    Browser receives HTML + matching session cookie
      |
[4] User enters username/password and submits
      |
      v
    POST /login
    Cookie: JSESSIONID=...  (when app uses sessions)
    Content-Type: application/x-www-form-urlencoded
    username=learner&password=...&_csrf=...
      |
      v
[5] CsrfFilter validates token
      |
      +--- missing/invalid token -----------> 403 Forbidden
      |
      +--- valid token
              |
              v
[6] Form-login authentication filter receives username/password
              |
              +--- wrong credentials -------> failure handler
              |                              (typically 302 /login?error)
              |
              +--- valid credentials -------> Authentication succeeds
                                              -> save SecurityContext per flow
                                              -> success handler (typically redirect)
~~~

This is a **logical diagram**, not an exact log trace of every release. Some deployments use custom entry points, JSON API responses, or other filters so status codes may differ. Keep the two steps clear: **CSRF validates the request** and **AuthenticationManager/Provider verifies the password**.

### 3.1. Why Does GET Usually Not Need a Token in the Request?

By Spring Security's default, methods considered safe (such as GET, HEAD, OPTIONS, TRACE) normally do not require a CSRF token **when sent to the server**. However, the `GET /login` response must supply a token for the client to **send back in the subsequent POST**.

There is no contradiction between the two:

- `GET /login` can be called before the browser has a session.
- While rendering the login page, accessing the token can trigger session creation to store the token when using a session-backed repository.

Never design session mutation, data deletion, or business state transitions using GET alone, because the default CSRF policy treats GET as safe.

### 3.2. Why Does `POST /login` Need a Token Before the User Is Authenticated?

The browser can hold a session **before login** solely to carry the CSRF token. `CsrfFilter` does not require an already-authenticated user before checking tokens: it evaluates the HTTP method/request per policy.

Within the same form, the three fields have distinct natures:

| Field | Purpose | Does it prove identity or request origin? |
| --- | --- | --- |
| `username` | User-claimed identity | Not yet proven |
| `password` | Credentials for the authentication provider to check | Verified only after the provider checks it |
| `_csrf` | Token for the server to verify the request fits the CSRF context | Does not prove who the user is |

A CSRF token **is not a password, access token, JWT, or role**. Having the right token does not mean the password is right. Having the right password is also not enough for a POST violating CSRF policy to pass.

### 3.3. `permitAll` Does Not Bypass `CsrfFilter`

Configuring:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/login").permitAll()
    .anyRequest().authenticated())
~~~

is an **authorization** rule answering "is the request allowed to access this URL by permissions?". It does not say "skip all security filters."

If a `POST /login` request is missing its token, `CsrfFilter` can still reject it **before** authorization even runs. When debugging, never look only at `permitAll` and conclude CSRF was disabled.

## 4. Related Spring Security Components

| API/Class | Role |
| --- | --- |
| `CsrfFilter` | Validates tokens on requests requiring CSRF protection |
| `CsrfToken` | Provides parameter name, header name, and token value |
| `CsrfTokenRepository` | Generates, stores, and loads tokens in the chosen state store |
| `HttpSessionCsrfTokenRepository` | Stores/retrieves CSRF tokens in the HTTP session |
| `CookieCsrfTokenRepository` | Uses a cookie to carry the token in suitable models, often discussed for SPAs |
| `CsrfTokenRequestHandler` | Determines how tokens are exposed/resolved on requests |
| `XorCsrfTokenRequestAttributeHandler` | Request handler using masking to reduce BREACH-related risks |
| `CsrfAuthenticationStrategy` | Refreshes CSRF state upon authentication events per built-in flow |
| `CsrfLogoutHandler` | Cleans up tokens during the logout flow |
| `UsernamePasswordAuthenticationFilter` | Handles username/password once the form login request reaches authentication |
| `SecurityFilterChain` | The filter chain built by the framework for matching requests |

**Do not invent a static CSRF token and embed it in HTML.** Tokens must be generated and verified consistently through the repository/handler between form GET and POST submission.

### 4.1. `HttpSessionCsrfTokenRepository`

For server-rendered form login using session cookies, an HTTP-session-backed repository is the common choice. The token is bound to the appropriate session, the browser saves the session cookie, and sends it back on submit.

Conditions typically required simultaneously:

1. The HTML form contains the server-rendered token.
2. The POST sends the token under the exact parameter/header name.
3. The browser sends the cookie matching the session holding the token.
4. The server can read the session consistently (critical in multi-node clusters).

Copying a token from browser A and submitting it with browser B's session cookie is not valid. Likewise, copying a token while omitting the cookie jar in `curl` prevents the server from finding the matching state.

### 4.2. Deferred CSRF Tokens in Spring Security 6.x

In modern Spring Security versions, token creation/loading can be **deferred** until actually needed, avoiding creating useless sessions for requests that do not use a CSRF token. When an HTML form references the token during rendering, accessing it triggers token creation/storage.

Therefore, do not assume "every GET creates a session." Observe which requests actually render the token and which repository is active.

### 4.3. Masking and BREACH

`XorCsrfTokenRequestAttributeHandler` can mask token values when exposed in responses, helping reduce risks of leaking repeated tokens in compressed data (part of BREACH mitigation).

Consequences:

- The hidden token in HTML can differ from the raw token stored in the repository.
- Tokens appearing across two HTML renders can differ even when the underlying token has not changed.
- Do not test rotation by comparing two hidden values and assuming a brand-new token was issued.
- For SPAs reading tokens from cookies and sending headers, configure a request handler compatible with your version; do not assume raw values are always accepted in every mode.

For learning server-rendered form login, it is best to use the official Spring MVC/Thymeleaf integration rather than manually manipulating raw/masked tokens.

## 5. How Does Thymeleaf Inject the Token into a Form?

A basic form:

~~~html
<form th:action="@{/login}" method="post">
    <label>
        Account
        <input type="text" name="username" required>
    </label>
    <label>
        Password
        <input type="password" name="password" required>
    </label>
    <button type="submit">Sign in</button>
</form>
~~~

When the template is processed by **Thymeleaf integrated with Spring MVC/Spring Security**, `RequestDataValueProcessor` normally adds a hidden CSRF input for POST forms with `th:action`. The rendered HTML semantically contains an input like:

~~~html
<input type="hidden" name="_csrf" value="server-generated-token">
~~~

`server-generated-token` is an illustrative placeholder, **not a real token**. Check Network/Elements or MockMvc to confirm the final HTML contains that input. The template source file itself does not necessarily have the hidden field written inside it.

If the template is served only as a **static HTML file** without passing through the processor, the CSRF input will not appear automatically. In that case `POST /login` may return 403. Fix view integration/form rendering instead of disabling CSRF.

### 5.1. Adding the Field Explicitly When Truly Needed

A template that already has the `_csrf` request attribute can render the field manually:

~~~html
<input type="hidden"
       th:name="${_csrf.parameterName}"
       th:value="${_csrf.token}">
~~~

This is an **illustrative snippet** for templates where the attribute is present; it is not standalone plain HTML. Do not add this snippet inside a form where `th:action` already auto-injects the token without checking, as you could emit duplicate `_csrf` fields that are hard to debug.

Other template engines, JSP, or JavaScript must pass tokens in a way compatible with the active repository and request handler. Note that the field name is configurable; not every system necessarily uses `_csrf`.

### 5.2. Changing the Login Paths

If you configure:

~~~java
.formLogin(form -> form
    .loginPage("/signin")
    .loginProcessingUrl("/session/login")
    .permitAll())
~~~

then `GET /signin` renders the page, while the credential-processing POST goes to `/session/login`. The CSRF token must be present on **the login-processing POST**, regardless of which URL you choose. Do not equate the login page URL with the login processing URL once customized.

## 6. Runnable Example: Java 17 + Spring Boot 3.3.5

The application consists of a login page, a profile page, and a logout form. Spring Security handles `POST /login` and `POST /logout`; the controller only renders GET pages. The example uses an in-memory user `learner / demo-pass` for local testing.

**Do not use hardcoded passwords in real products.** Production environments require user/secret management, HTTPS, rate limiting, safe logging, and additional security controls.

### 6.1. File Structure

~~~text
login-csrf-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/example/logincsrf/
    │   │   ├── LoginCsrfApplication.java
    │   │   ├── SecurityConfiguration.java
    │   │   └── PageController.java
    │   └── resources/templates/
    │       ├── login.html
    │       └── profile.html
    └── test/java/example/logincsrf/
        └── LoginCsrfTests.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'login-csrf-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '1.0.0'

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
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot's BOM selects compatible Spring Security versions. Do not pin an individual security module version separately when other modules are managed by Boot.

### 6.2. Application

File `src/main/java/example/logincsrf/LoginCsrfApplication.java`:

~~~java
package example.logincsrf;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LoginCsrfApplication {
    public static void main(String[] args) {
        SpringApplication.run(LoginCsrfApplication.class, args);
    }
}
~~~

### 6.3. SecurityConfiguration

File `src/main/java/example/logincsrf/SecurityConfiguration.java`:

~~~java
package example.logincsrf;

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

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login").permitAll()
                .anyRequest().authenticated())

            .formLogin(form -> form
                .loginPage("/login")
                .defaultSuccessUrl("/profile", true)
                .permitAll())

            .logout(logout -> logout
                .logoutSuccessUrl("/login?logout"))

            // Keep default CSRF protection: do not call disable().
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode("demo-pass"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(learner);
    }
}
~~~

Explanation:

- `requestMatchers("/login").permitAll()` lets unauthenticated users view the form. This is **only** authorization.
- `formLogin().loginPage("/login")` configures the form page, while `POST /login` is handled by the login filter.
- `defaultSuccessUrl("/profile", true)` redirects after successful login.
- `logoutSuccessUrl("/login?logout")` redirects after logout.
- Without calling `csrf(csrf -> csrf.disable())`, `POST /login` and `POST /logout` still must satisfy default CSRF protection.
- The password encoder verifies secrets after CSRF has let the POST through; it does not replace tokens.

### 6.4. Controller

File `src/main/java/example/logincsrf/PageController.java`:

~~~java
package example.logincsrf;

import java.security.Principal;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class PageController {

    @GetMapping("/login")
    public String login() {
        return "login";
    }

    @GetMapping("/profile")
    public String profile(Principal principal, Model model) {
        model.addAttribute("username", principal.getName());
        return "profile";
    }
}
~~~

Do not add `@PostMapping("/login")` to compare passwords manually. Spring Security's form-login filter intercepts the request and handles it before the controller under this configuration.

### 6.5. `login.html`

File `src/main/resources/templates/login.html`:

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Sign in</title>
</head>
<body>
    <h1>Sign in</h1>
    <p th:if="${param.error}">Invalid account or password.</p>
    <p th:if="${param.logout}">Signed out.</p>
    <form th:action="@{/login}" method="post">
        <label>Account
            <input type="text" name="username"
                   autocomplete="username" required>
        </label>
        <label>Password
            <input type="password" name="password"
                   autocomplete="current-password" required>
        </label>
        <button type="submit">Sign in</button>
    </form>
</body>
</html>
~~~

Thymeleaf processes `th:action` and normally auto-adds the hidden CSRF field via Spring MVC integration. Do not edit the template just to emit a fixed token value.

### 6.6. `profile.html`

File `src/main/resources/templates/profile.html`:

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Profile Page</title>
</head>
<body>
    <h1>Profile Page</h1>
    <p>Xin chào, <span th:text="${username}">user</span></p>
    <form th:action="@{/logout}" method="post">
        <button type="submit">Sign out</button>
    </form>
</body>
</html>
~~~

Logout mutates session state, so the `POST /logout` form also needs a token. Under default configuration with CSRF enabled, do not build a GET logout just for convenience.

## 7. Testing CSRF and Login with MockMvc

File `src/test/java/example/logincsrf/LoginCsrfTests.java`:

~~~java
package example.logincsrf;

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
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrlPattern;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LoginCsrfTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void loginPageRendersHiddenCsrfField() throws Exception {
        mockMvc.perform(get("/login"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                containsString("name=\"_csrf\"")));
    }

    @Test
    void loginWithoutTokenIsForbidden() throws Exception {
        mockMvc.perform(post("/login")
                .param("username", "learner")
                .param("password", "demo-pass"))
            .andExpect(status().isForbidden());
    }

    @Test
    void loginWithInvalidTokenIsForbidden() throws Exception {
        mockMvc.perform(post("/login")
                .with(csrf().useInvalidToken())
                .param("username", "learner")
                .param("password", "demo-pass"))
            .andExpect(status().isForbidden());
    }

    @Test
    void validTokenButWrongPasswordUsesFailureRedirect()
            throws Exception {
        mockMvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "wrong"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"));
    }

    @Test
    void validTokenAndPasswordRedirectToProfile()
            throws Exception {
        mockMvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "demo-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/profile"));
    }

    @Test
    void protectedProfileRedirectsAnonymousBrowserToLogin()
            throws Exception {
        mockMvc.perform(get("/profile"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void authenticatedSessionCanViewProfile() throws Exception {
        MvcResult result = mockMvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "demo-pass"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) result.getRequest().getSession(false);
        assertNotNull(session);

        mockMvc.perform(get("/profile").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string(containsString("Xin chào")));
    }

    @Test
    void logoutWithoutTokenIsForbidden() throws Exception {
        mockMvc.perform(post("/logout"))
            .andExpect(status().isForbidden());
    }
}
~~~

Tests pass through Spring Security filters because of `@SpringBootTest` and `@AutoConfigureMockMvc`. If you build MockMvc manually without applying security, tests can bypass `CsrfFilter` and give misleading results.

**Two important points when reading the tests:**

- `.with(csrf())` generates a valid token in the test request. It **does not prove** the template rendered a token; hence the HTML test at the top is needed.
- `.with(csrf().useInvalidToken())` simulates a wrong token, distinct from a completely absent token.

Expected outcomes:

| Request | CSRF | Credentials | Typical outcome |
| --- | --- | --- | --- |
| GET /login | Not sent | None yet | 200, HTML with hidden input |
| POST /login | Missing | Valid | 403 before login step |
| POST /login | Invalid | Valid | 403 |
| POST /login | Valid | Wrong | 302 to /login?error |
| POST /login | Valid | Valid | 302 to /profile |
| GET /profile when not logged in | Not needed | Unauthenticated | Redirect /login |
| GET /profile with authenticated session | Not needed | Authenticated | 200 |
| POST /logout | Missing | Irrelevant | 403 |

When changing authentication success/failure handlers or security entry points, status codes can differ. These expectations correspond to the **sample configuration**, not a universal contract for every project.

### 7.1. Running the Application

In the directory with Gradle and Java 17:

~~~bash
gradle test
gradle bootRun
~~~

If the project has a wrapper, use:

~~~bash
./gradlew test
./gradlew bootRun
~~~

On Windows use `gradlew.bat test` and `gradlew.bat bootRun`. Because this project uses Spring Boot dependencies, running bare `javac`/`java` will miss the classpath; fixed Gradle stdout is not shown since real environments vary.

## 8. Observing with a Browser and `curl`

### 8.1. Browser

1. Open `http://localhost:8080/login`.
2. In DevTools → Elements or Network, confirm the HTML response contains the hidden `_csrf` input and the form POSTs to the right URL.
3. Enter `learner / demo-pass` and submit; observe the POST includes the session cookie and valid token, followed by a redirect to `/profile`.
4. Temporarily tamper with the token in DevTools to observe 403.
5. From the profile page, submit logout via POST and observe returning to the login page.

Tokens and session cookies are contextually sensitive data. Mask actual values when sharing screenshots for support; never enable request-body logging that captures passwords.

### 8.2. `curl`: Must Carry Both the Token and Same-Session Cookie

Fetch the page and save the cookie jar:

~~~bash
curl -s -c cookie-jar.txt \
  http://localhost:8080/login \
  -o login-page.html
~~~

Open `login-page.html` in your learning environment to grab the **actual value** of the `_csrf` input. Then POST with the same cookie:

~~~bash
curl -i -b cookie-jar.txt -c cookie-jar.txt \
  -X POST http://localhost:8080/login \
  --data-urlencode "username=learner" \
  --data-urlencode "password=demo-pass" \
  --data-urlencode "_csrf=TOKEN_FROM_SAME_FORM"
~~~

`TOKEN_FROM_SAME_FORM` is a **placeholder to replace with the real token**; leaving that literal text will not form a valid request. Without the same-session cookie, or using a token from another browser, the request can return 403. Never place real tokens or passwords in shared scripts or application logs.

A `curl` command with `-d` or `--data-urlencode` typically sends `application/x-www-form-urlencoded`; the converter/form login reads parameter names defined by the framework. If switching to JSON, you cannot rely on hidden form fields without designing separate client/header CSRF integration.

## 9. Token Lifecycle: Login, Logout, Timeout, Multiple Tabs

Spring Security includes mechanisms to clear/rotate CSRF tokens when authentication/logout happens in the standard flow. If a user opens the login tab and then changes session state in another tab, the open form may hold an expired token.

~~~text
Tab A: GET /login -> form contains token A
Tab B: GET /login -> form contains current token (possibly masked differently)
Tab A: POST /login -> authentication succeeds
       -> session/auth state may change, old token may be cleared
Tab B: POST with earlier token -> may return 403
~~~

Do not infer solely from differing hidden strings that a token was rotated: Spring Security 6 can mask tokens per response. When analyzing, distinguish **raw token in repository**, **masked token placed in HTML**, **session id**, and **token clearing after authentication/logout**.

### 9.1. Session Fixation Differs from CSRF

Some session-based login configurations apply session fixation protection such as rotating the session ID after login. That protects the session from being reused under an old session ID. A CSRF token, on the other hand, checks whether a request matches the expected browser state. Both are needed when the threat model demands them.

### 9.2. Handling Stale Tokens

When a stale form returns 403:

- Check session timeout, cookies, application restarts, and whether the token was cleared/rotated.
- Consider instructing users to reload the form for a fresh token; avoid auto-resubmitting passwords repeatedly.
- For long forms, consider preserving non-sensitive fields for UX; **never store passwords in `localStorage`**.
- Test with two tabs and multiple backend nodes; if the session store is not shared, a POST may be rejected by another backend node.
- Never disable CSRF to resolve stale form errors.

## 10. `CookieCsrfTokenRepository`, SPAs, and Stateless Systems

CSRF relates closely to **ambient credentials** that browsers send automatically, rather than simply depending on buzzword labels.

| Application type | Assessment check |
| --- | --- |
| Server-rendered form login + session cookie | Usually needs CSRF tokens for login, logout, and unsafe methods |
| SPA using session cookies | Still carries CSRF risk; may need header tokens and compatible cookie repository/request handler |
| HTTP Basic in a browser | Browser may cache and auto-send credentials; not exempt from CSRF by default |
| JWT stored in an auto-sent cookie | Still needs CSRF evaluation, even though JWT is called a token |
| API using an explicit client-attached Authorization bearer header, no ambient cookies | Different CSRF threat model; adjusting CSRF requires verifying the entire auth flow |
| Stateless service with a login endpoint issuing cookies | Must separately evaluate endpoints that establish/change browser auth state |

`CookieCsrfTokenRepository` is an option when clients need to read the token from a cookie, such as an SPA. Names like `XSRF-TOKEN` and `X-XSRF-TOKEN` are commonly used. However, letting JavaScript read the cookie may require adjusting `HttpOnly` per policy; this carries a security trade-off because XSS could read the token.

In Spring Security 6, deferred tokens and XOR masking can require a suitable **SPA request handler**: reading a raw cookie and sending it as a header is not the right formula in every mode. Design per your framework version and verify real requests. Never switch to `CookieCsrfTokenRepository` just to make a regular Thymeleaf form login work.

### `SameSite` and CORS

`SameSite` cookies help reduce certain cross-site requests carrying cookies, yet browser/SSO/subdomain flows have differences and limits. CORS controls how JavaScript reads/sends certain cross-origin requests, yet **must not** be treated as a general replacement for CSRF tokens. An attacker can submit cross-site HTML forms without needing response-read permission. XSS controls remain mandatory.

### When Should You Consider Ignoring CSRF for an Endpoint?

`csrf(csrf -> csrf.ignoringRequestMatchers(...))` is a tool for very specific endpoints **after** the threat model proves they do not rely on ambient browser credentials, such as a webhook with its own cryptographic signature. Never apply it to cookie-session form login just because a valid password got a 403 on POST.

## 11. Diagnostic Procedure for 403 on a Login Form

When `POST /login` returns 403, inspect in order instead of immediately editing `UserDetailsService`:

1. **Method and endpoint:** does the POST hit the filter's exact `loginProcessingUrl`?
2. **Rendered HTML:** is there an actual token field? Did `th:action` run through Thymeleaf/Spring MVC integration?
3. **Field/header name:** does it match the active `CsrfToken.parameterName` or header name?
4. **Session cookie:** did the POST send the cookie from the form GET? Was it affected by `Secure`/`SameSite`/`Path`/`Domain`?
5. **Repository:** is the token stored and read consistently by the backend/session?
6. **Handler:** are raw/masked tokens handled as expected, especially with SPAs?
7. **Lifecycle:** did the session time out, did login/logout happen in another tab, or was the token cleared?
8. **Filter order:** was the request rejected earlier by `CsrfFilter`, or did it reach the login authentication filter?
9. **Authentication:** if CSRF passes, a wrong password usually triggers the login failure redirect; distinguish that from 403.
10. **Multiple chains:** could `securityMatcher`, `@Order`, or another filter configuration route `POST /login` into an unintended chain?

In a learning environment you can enable:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Do not expect every release to log identical strings. Never log raw tokens, `JSESSIONID`, passwords, `Authorization` headers, or responses containing sensitive data in public environments.

| "Quick fix" | Why it is dangerous or misguided |
| --- | --- |
| `csrf(csrf -> csrf.disable())` for the entire app | Disables protection against login CSRF and other state-changing requests |
| `permitAll("/login")` then omitting the hidden field | Authorization does not remove CSRF requirements |
| Switching login to GET | Makes GET mutate auth state, introducing risk |
| Hardcoding a fixed token in the template | Breaks per-session binding and lifecycle |
| Submitting a token from another session | Token does not match the request's context |
| Disabling sessions without redesigning login | Context/CSRF/session persistence can break |
| Sending the token in the query string | Risks leaking via history, logs, and referer |
| Skipping CSRF for every POST under `/api/**` | May leave cookie-backed endpoints exposed |
| Relying solely on `SameSite` and dropping tokens | Does not cover all flows and threat models |
| Testing with `with(csrf())` without testing rendered HTML | Integration tests can pass while the template fails to send a token |

## 12. Self-Check Exercises

1. Why can login CSRF occur when the victim is **not** logged in? Describe a scenario forcing login into an attacker-owned account.
2. With the exact same valid username/password, why can `POST /login` without a CSRF token return 403?
3. Distinguish the roles of `permitAll()`, `CsrfFilter`, and the form authentication filter.
4. For `GET /login`, why does the request not need to send a token while the HTML response must include one?
5. Explain how a masked token in responses can produce different strings across two renders without necessarily having two different underlying raw tokens.
6. Using MockMvc, write tests for: missing token → 403; invalid token → 403; valid token/wrong password → failure redirect; valid token/right password → success redirect.
7. Locate the hidden `_csrf` input in rendered HTML even though the Thymeleaf source lacks that input line.
8. Use `curl` to `GET` login + cookie jar, then `POST` with only the token and no cookie; analyze the error.
9. Open two login form tabs; log in on one tab, then submit the stale tab. What conditions can cause the old token to be rejected?
10. Why does `POST /logout` also require CSRF protection, and what goes wrong with logging out via GET?
11. An SPA uses session cookies, yet the API returns 403 when sending the raw XSRF cookie as a header. What must be checked regarding request handler/deferred/masked tokens?
12. Between a JWT in a cookie and a JWT in an `Authorization` header explicitly attached by the client, how are CSRF threat models similar and different?
13. If a custom `loginProcessingUrl` is `/session/login`, what must change in form action, matchers, and tests?
14. List information that is safer to log than raw tokens or session IDs while debugging.
15. In a multi-node cluster, why can lack of session stickiness/consistent distributed sessions cause CSRF errors after a form GET?

## 13. Secure Form Login Implementation Checklist

- [ ] **Login CSRF** is analyzed, not just post-login CSRF protection.
- [ ] Login-processing `POST` remains within the scope of an appropriate `CsrfFilter`.
- [ ] `GET` login page is public yet the form contains a server-generated CSRF token.
- [ ] **Actual rendered HTML** is verified and hidden field/header names match configuration.
- [ ] Session cookie and token belong to the same CSRF context; cookie attributes fit HTTPS, `SameSite`, and reverse proxies.
- [ ] Tests cover missing token, invalid token, valid token + wrong password, and valid token + right password.
- [ ] Logout uses proper HTTP method/CSRF policy, avoiding arbitrary state-mutating GETs.
- [ ] Tests cover stale tokens, multiple tabs, session timeout, and post-login session rotation.
- [ ] Tokens are never passed in query strings, and tokens, session cookies, or raw passwords are never logged.
- [ ] Complementary defenses exist: HTTPS, XSS prevention, rate limiting, and MFA where needed.
- [ ] If using an SPA, cookie repository/request handler config matches the Spring Security version.
- [ ] CSRF is not broadly disabled just to avoid 403s; any matcher exception has a clear threat model.
- [ ] `SecurityContext`, session persistence, and logout are tested rather than inferred from one HTTP status.
- [ ] Actual MVC/Thymeleaf rendering is tested together with Spring Security filters.
- [ ] Credentials are never hardcoded in real deployed systems.

## 14. Conclusion

**The CSRF token in a login form protects the identity-switching action of a browser session**, rather than replacing password verification. The standard flow is: **GET /login renders token → browser POSTs form with session cookie + token → CsrfFilter validates → authentication provider verifies credentials → success/failure handler redirects**.

If `POST /login` returns 403, examine token, cookie, session, view rendering, and request handler before touching the password encoder. With Spring MVC and Thymeleaf properly integrated, CSRF protection works without writing custom token generation logic — yet always test the rendered HTML and real requests to verify the system behaves properly.
