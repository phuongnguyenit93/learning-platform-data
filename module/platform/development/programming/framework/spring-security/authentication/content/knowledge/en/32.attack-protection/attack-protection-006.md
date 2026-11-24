# CSRF in login, logout, and browser-auto-sent credential mechanisms

## 1. The problem: browsers can send a user's authority without the user's intent

**Cross-Site Request Forgery (CSRF)** is an attack in which an untrusted website/page causes **the victim's browser** to send a request to another application. If the browser **automatically attaches a credential** that the target application accepts and the request performs a state-changing action, the server may mistake it for a legitimate request from the victim.

For example, An is logged into `https://app.example.com` via a session cookie. An opens an external page controlled by an attacker. That page tries to submit a `POST` form to `https://app.example.com/settings/email`. If the browser sends the cookie automatically and the server lacks origin/transaction verification, the attacker can alter An's account whenever cookie-sending conditions are met. The attacker **does not need to read the cookie or know the password** to attempt CSRF.

CSRF does not only apply to "money transfers" or profile updates. In Spring Security applications, it also covers **login CSRF**, **logout CSRF**, and requests using browser-auto-sent credentials such as session cookies, remember-me cookies, some HTTP Basic cases, or client-certificate authentication.

After this lesson you will:
1. Distinguish CSRF from XSS, CORS, and session hijacking.
2. Explain why **a login POST without an authenticated session yet still needs CSRF protection**.
3. Explain why **logout should use POST + CSRF token**, not GET as the logout action.
4. Determine CSRF exposure by whether credentials **travel automatically with requests**, not by labels like "REST", "JWT", or "stateless".
5. Configure and test Spring Security Servlet 6.x with Java 17+, Spring Boot 3.x, `CsrfFilter`, and `MockMvc`.
6. Distinguish **SameSite cookies, CORS, Origin/Referer, and Fetch Metadata** from the synchronizer CSRF token pattern.
7. Properly handle HTML forms, JavaScript SPAs, browser redirects/SSO, reverse proxies, and endpoints using manual Bearer tokens only.

**Scope:** **Spring Security Servlet/Spring MVC** applications. For WebFlux, use `ServerHttpSecurity` and reactive CSRF repositories/filters; do not copy `HttpSecurity` or `SecurityFilterChain` from these examples verbatim.

## 2. Threat model: what data does the browser send automatically?

A typical CSRF attack requires these conditions:
- The victim already has an **authenticated/stateful relationship** with the target site.
- The browser sends a usable credential to the target site **without the attacker needing to know it**, depending on cookie policy, domain/scheme, request context, and auth mechanism.
- The attacker can initiate a state-changing request along an allowed path.
- The server cannot verify that the request originated from a legitimate page/transaction, such as lacking a matching CSRF token.

Diagram:

~~~text
An logs into app.example.com
    |
    | Browser holds session cookie
    v
Victim visits attacker.example
    |
    | That page builds a POST form to app.example.com/settings/email
    v
Browser decides whether to attach cookie with the request
    |
    | If credential is attached and no CSRF defense exists
    v
Server may execute an update against An's wishes
~~~

**Important note:** cookies do not always accompany cross-site POSTs. `SameSite=Strict/Lax/None`, browser behavior, navigation type, and cookie attributes govern attachment. The example only describes one attack class **when the browser actually attaches credentials**. Never assume every cross-site POST always carries cookies.

### 2.1. CSRF does not mean the attacker reads the response

Even when Same-Origin Policy/CORS blocks malicious JavaScript from reading the response, an attacker can still trigger requests via browser-permitted mechanisms: HTML forms, navigation, and certain simple requests. **Not being able to read the result** does not mean **not being able to cause side effects**.

Frequently confused concepts:

| Concept | Main risk | Relation to CSRF |
| --- | --- | --- |
| **CSRF** | Exploits the victim's automatic auth context for unintended actions | Needs defense on state-changing requests |
| **XSS** | Malicious script runs in trusted origin, accesses DOM, sends same-origin requests | XSS can bypass many CSRF defenses; must still prevent XSS |
| **CORS** | Controls JavaScript cross-origin access and preflight | Does not block all HTML forms/navigation; does not replace CSRF |
| **Session hijacking** | Attacker steals/takes over session or credentials | CSRF may not require stealing the session |
| **Clickjacking** | Tricks users into clicking disguised/overlaid UI | Different mechanism; may need CSP `frame-ancestors` |
| **Login CSRF** | Forces browser to log into an attacker-controlled account | Can occur **before the user has a login session** |
| **Logout CSRF** | Forces browser to end session against user's wishes | Can disrupt workflows/security even without stealing data |

### 2.2. Illustrating a forged request

The HTML below merely illustrates the attack technique (endpoint, hostname, and data are synthetic):

~~~html
<form action="https://app.example.com/settings/email" method="post">
  <input name="newEmail" value="attacker-controlled@example.test">
  <button type="submit">Submit</button>
</form>
~~~

Another page can display this button for the user to click or use other mechanisms to submit the form. From the server's perspective, the request can look identical to a legitimate update if it **only checks cookies** without proof of valid intent/origin. A CSRF token unknown to the attacker leaves the request lacking that proof and gets blocked.

## 3. Credentials browsers can send automatically

**Base CSRF decisions on how credentials are sent**, not technology buzzwords.

| Mechanism | Can browser attach it automatically? | Must evaluate CSRF? |
| --- | --- | --- |
| Session cookie like `JSESSIONID` | Yes, per Domain/Path/SameSite/Secure and request context | **Yes**, for state-changing actions |
| Remember-me cookie | Yes, similar to session cookie | **Yes** |
| JWT/opaque token **inside a cookie** | Yes; JWT format does not alter cookie behavior | **Yes** |
| Browser-saved or cached HTTP Basic/Digest | Possibly, depending on browser and auth context | **Yes** if browser auto-attaches credential |
| TLS client certificate (mTLS) selected for site | Browser/client may send automatically on matching connections | **Possibly**; evaluate browser request context |
| Access token in `Authorization: Bearer ...` explicitly added by JS client | Browsers do not auto-attach it from another origin's JS variable | Lower traditional CSRF risk if relying **solely** on trusted client headers |
| API key explicitly attached in header by backend service | Victim's browser does not possess or auto-send API keys | Usually no browser CSRF if API accepts only this mechanism |
| No credential, public POST | No auth session to abuse | Still needs anti-abuse, automation, login CSRF, and business side-effect controls |

**Common misconception:** "My API uses JWT so I can disable CSRF." If the JWT is stored in an `HttpOnly` cookie, the browser still sends the cookie automatically when policy allows. The JWT signature is valid, yet the server does not know whether the user actually intended to change the shipping address. **CSRF remains a risk.**

Conversely, if an API **only** accepts Bearer tokens manually sent in the `Authorization` header by controlled clients—rejecting cookies, Basic, or any browser-auto-sent credentials—you may evaluate omitting CSRF tokens for that API scope. **Verify this condition across the entire filter chain**, not just one controller.

## 4. Login CSRF: why does POST /login need a token too?

CSRF is often described as attacking an **already logged-in** user. Yet **logging in also changes the browser's authentication state**.

A *login CSRF* scenario:
1. Attacker creates an `attacker-account` in the application.
2. Attacker prepares a login request with the **attacker account's** username/password.
3. Attacker induces the victim's browser to send that login POST to the application.
4. If accepted without CSRF verification, the victim's browser starts a session **under the attacker's account**.
5. Thinking they are using their own account, the victim enters personal data, documents, or transactions into the attacker-controlled account; the attacker can then access data in that account.

This is **not** guessing the victim's password. The password known to the attacker is **the attacker account's password**; the goal is forcing the victim onto the wrong identity.

Impact varies by application features, yet the lesson is clear: **login POSTs need CSRF protection even before the victim has an `Authentication`**.

Spring Security Servlet enables CSRF protection by default for unsafe methods, including `POST /login`. With default form login, Spring Security's GET `/login` page renders a form containing the right CSRF token. If you build a **custom login form**, render the CSRF token into the form properly or send it via a backend-accepted mechanism.

### 4.1. How can a pre-login token exist?

The browser may not be authenticated yet, yet already holds an anonymous/pre-auth session storing CSRF token state, or the app uses a differently configured CSRF token repository. `CsrfTokenRepository` stores/loads expected tokens; `CsrfFilter` validates requests.

**Do not enable CSRF only for `request.isUserInRole(...)` or post-login endpoints.** Exempting `POST /login` drops an important defensive layer.

After successful login, Spring Security can **clear/rotate the old CSRF token** via `CsrfAuthenticationStrategy`. JS apps must fetch the fresh token before the next POST. Pre-login tokens do not automatically stay valid forever in the post-login session.

## 5. Logout CSRF: why shouldn't GET /logout log users out?

If an app lets `GET /logout` actually destroy the session, a link, image, or navigation triggered by an external page can force users out without deliberate action. This can discard unsaved work, disrupt flows, or create confusion between login steps.

**Proper design:** logout changes state → use **POST** (or an appropriately designed unsafe method) and require a CSRF token. With Spring Security 6.x default CSRF enabled:
- `GET /logout` displays a **logout confirmation page**, without actually logging out.
- `POST /logout` with a valid CSRF token runs `LogoutFilter`, invalidates the session, and clears the security context and CSRF token per config.
- `POST /logout` missing/invalid CSRF token is blocked, typically HTTP **403**.
- On successful logout, defaults to redirecting to `/login?logout`.

For an HTML form page:

~~~html
<!-- Thymeleaf template fragment in a Spring MVC app with CSRF integration. -->
<form th:action="@{/logout}" method="post">
    <button type="submit">Log out</button>
</form>
~~~

With proper Spring MVC/Thymeleaf integration, `RequestDataValueProcessor` automatically injects the CSRF token field on `th:action` POST forms. Without that integration, manually render a field with the server-provided `parameterName` and `token`; **never hardcode token values**. A plain link `<a href="/logout">` should only navigate to the GET confirmation page, **not** perform logout.

**Warning:** tutorials advising turning off CSRF so "`GET /logout` works" trade away logout protection for UI convenience. Keep POST and tokens; JavaScript can submit a hidden form if a link/button look is desired.

### 5.1. App logout vs IdP logout are not identical

When using OIDC/SAML SSO, distinguish:
- **Local logout:** ends the RP/SP application's session/cookies.
- **Federated logout:** may also require notifying/redirecting to the authorization server or IdP per protocol.
- **CSRF protects local actions:** local POST logout still requires valid proof per threat model; federated protocols add their own state, return URL, issuer, and signature/binding checks.

Do not assume redirecting to the IdP for logout automatically protects all local actions from CSRF. At the same time, protocol callbacks from the IdP may use distinct verification mechanisms; never disable CSRF app-wide.

## 6. SameSite: an auxiliary defense, not a cure-all for CSRF

Cookies carry security-related attributes:

~~~http
Set-Cookie: JSESSIONID=sample; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

| Attribute | Main purpose | Does not guarantee |
| --- | --- | --- |
| `Secure` | Browser sends cookie only over secure transport | Does not stop CSRF when cookies still travel over HTTPS |
| `HttpOnly` | JavaScript cannot read cookie directly | Does not stop browser from **auto-attaching cookies** |
| `SameSite=Strict` | Restricts cookies on cross-site requests | Can hurt navigation/SSO UX |
| `SameSite=Lax` | Usually sends cookies on top-level safe-method navigations; restricts cross-site unsafe requests | Side-effect GETs remain dangerous; same-site subdomains may not be trusted |
| `SameSite=None; Secure` | Allows cookies in cross-site contexts per browser policy | Not a CSRF defense; requires other protections |
| `Path` / `Domain` | Scopes where browsers send cookies | Does not replace request origin/CSRF token verification |

**Same-site does not equal same-origin.** `https://app.example.com` and `https://blog.example.com` have different origins yet are typically same-site by registrable domain/scheme. If the blog hosts user-generated or third-party content, `SameSite` may not block requests from the blog to the app the way you expect. Evaluate all subdomains with differing trust levels.

Never rely on `SameSite=Lax` to allow state-changing GETs. Under HTTP semantics, **GET/HEAD/OPTIONS/TRACE must be safe**; Spring Security by default does not require CSRF tokens on safe methods. If a URL like `GET /delete-account` actually deletes an account, you created a dangerous bypass.

**Browsers differ in policies and historical exceptions**, especially for cookies omitting SameSite and newly created top-level POST handling. In production set explicit attributes, test on supported browsers, and still enforce CSRF tokens on session-based unsafe actions.

## 7. Synchronizer token pattern: proof browsers do not auto-send

Default CSRF protection in Spring Security Servlet typically uses the **synchronizer token pattern**:

1. The server generates an unpredictable CSRF value bound to the session context and stores the expected value via `HttpSessionCsrfTokenRepository`.
2. The server delivers the token to a trusted client inside an HTML form or an endpoint readable from the **same origin**.
3. When the client intentionally submits POST/PUT/PATCH/DELETE, the form or JavaScript sends the token back in a **request parameter** or **custom header**, such as `_csrf` / `X-CSRF-TOKEN`.
4. `CsrfFilter` extracts the request token and compares it to the expected token. Missing/mismatched → blocked **before the controller modifies data**.

Because browsers **do not automatically extract a valid hidden form field/JS header from the target site to attach to an attacker's form**, attackers can trigger requests yet typically **lack a valid CSRF token**. Auto-sent session cookies alone are treated by the server as insufficient.

Example Spring MVC form rendering the token from `CsrfToken`:

~~~html
<form method="post" action="/profile/display-name">
    <label for="name">Display name</label>
    <input id="name" type="text" name="value">
    <!-- Name/value must be server-rendered/escaped. -->
    <input type="hidden" name="_csrf" value="SERVER_RENDERED_TOKEN">
    <button type="submit">Save</button>
</form>
~~~

The string `SERVER_RENDERED_TOKEN` only marks where the template injects the value, **not a valid token**. In production, read `csrfToken.getParameterName()` and `csrfToken.getToken()` from the request/template integration (or let Thymeleaf inject them). Never place tokens in URLs/query strings because logs/history/Referer headers can record them.

### 7.1. Spring Security 6.x defaults and BREACH/deferred tokens

Spring Security 6 uses **deferred token loading** and response token masking to mitigate **BREACH**, so not every GET immediately touches the session or generates a token. Custom JS integrations must understand:
- Default repository: `HttpSessionCsrfTokenRepository`.
- `CsrfTokenRequestHandler` governs how tokens are resolved/made available on requests.
- CSRF tokens are cleared/rotated after login/logout; JS must fetch the new token.
- `CookieCsrfTokenRepository` differs from session repositories; if JS reads the token from a cookie, account for `XorCsrfTokenRequestAttributeHandler`/plain tokens and token refresh flows matching your exact Spring Security version.

Do not invent a custom `XSRF-TOKEN` cookie, compare it to a header via raw string equality, and assume CSRF is solved. For stateless designs, OWASP recommends **signed double-submit cookies** bound to sessions with cookie-injection protection, not naive "cookie == header".

### 7.2. Token cookies are not session cookies

In JavaScript applications:
- **Authentication** cookies (e.g., `JSESSIONID`) should be `HttpOnly` and `Secure`; the server validates them to identify sessions.
- A cookie used to **pass the CSRF token** to JS may need to be JS-readable (`HttpOnly=false`) under SPA patterns; that is CSRF data used to construct a header, **not** an auth cookie.
- When using cookie-to-header, the backend must verify the header/param actively sent by the client, not just the token cookie **that browsers attach automatically**.

Letting JavaScript read the CSRF cookie is not equivalent to letting JavaScript read the session cookie. Still, same-origin XSS can grab tokens and trigger actions, so **CSRF tokens do not cure XSS**.

## 8. Login, logout, and business endpoints: decision matrix

| Request | Changes state? | CSRF with session-cookie auth? | Notes |
| --- | --- | --- | --- |
| `GET /login` | No, renders form only | No token required for GET | Returned form contains token for POST |
| `POST /login` | Yes, creates authentication/session | **Yes** | Prevents login CSRF |
| `GET /logout` | Should not actually log out | Never let GET have side effects | Spring shows confirmation by default |
| `POST /logout` | Yes, invalidates session | **Yes** | Prevents forced logout |
| `GET /profile` | Read-only | Not per default matcher | Must not secretly update `viewedAt`/settings with major side effects |
| `POST /profile/display-name` | Yes, updates profile | **Yes** | Cookie auth alone is insufficient |
| `PUT /profile` / `DELETE /resource` | Yes | **Yes** | Unsafe methods |
| `POST /login/webauthn` / passkey registration | Creates session or credential | **Evaluate and protect** | WebAuthn ceremonies have challenges, session/correlation, and own policies |
| Browser POST to API accepting cookie JWT | Yes | **Yes** | Valid JWT signature does not replace CSRF |
| API POST accepting only client-set Bearer header | Yes | May exempt **strictly within Bearer-only scope** | Must reject cookie/Basic fallback paths |
| Public account registration POST | Yes | Depends on flow; protect appropriately | CSRF, rate limits, anti-automation, and email verification are separate layers |

Never exempt CSRF based solely on a path named `/api/**`. An app can serve `/api/**` with session cookies and therefore still require protection.

## 9. Spring Boot 3.3.x Java 17+ example: form login + POST logout + CSRF-protected profile update

This example focuses on **observing Spring Security's default behavior**. Uses Java 17+, Spring Boot **3.3.12**, Spring Security Servlet, and `spring-security-test`. Browsers can sign in via Spring Security's default page; the profile update endpoint only accepts requests with session auth **and a CSRF token**.

To stay self-contained, the profile is stored in an `AtomicReference` for **one** mock account. This is not how multi-user production data should be stored.

### 9.1. Structure and Gradle

~~~text
csrf-browser-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/csrf/
    │   ├── CsrfDemoApplication.java
    │   ├── SecurityConfig.java
    │   ├── ProfileStore.java
    │   └── ProfileController.java
    └── test/java/demo/csrf/
        └── CsrfSecurityTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'csrf-browser-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.12'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 9.2. Application

`src/main/java/demo/csrf/CsrfDemoApplication.java`:

~~~java
package demo.csrf;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CsrfDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CsrfDemoApplication.class, args);
    }
}
~~~

`src/main/java/demo/csrf/ProfileStore.java`:

~~~java
package demo.csrf;

import java.util.concurrent.atomic.AtomicReference;
import org.springframework.stereotype.Component;

@Component
public class ProfileStore {
    private final AtomicReference<String> displayName =
            new AtomicReference<>("Initial");

    public String get() {
        return displayName.get();
    }

    public void set(String value) {
        displayName.set(value);
    }

    public void reset() {
        displayName.set("Initial");
    }
}
~~~

**Lab limitation:** this global variable only simulates a side effect for testing. Production must store profiles by account ID/tenant with authorization and transactions, never letting all users share one `displayName`.

`src/main/java/demo/csrf/ProfileController.java`:

~~~java
package demo.csrf;

import java.security.Principal;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class ProfileController {
    private final ProfileStore store;

    public ProfileController(ProfileStore store) {
        this.store = store;
    }

    @GetMapping("/profile")
    public Map<String, String> profile(Principal principal) {
        return Map.of(
                "username", principal.getName(),
                "displayName", store.get());
    }

    @PostMapping("/profile/display-name")
    public Map<String, String> changeName(
            @RequestParam String value, Principal principal) {
        if (value.isBlank() || value.length() > 80) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid display name");
        }

        store.set(value);
        return Map.of(
                "username", principal.getName(),
                "displayName", store.get());
    }
}
~~~

The controller **does not manually read the CSRF token**; `CsrfFilter` blocks tokenless requests before reaching `changeName`. Business validation/authorization still remains required even when the CSRF token is valid.

### 9.3. SecurityFilterChain: keeping CSRF for login, logout, and state changes

`src/main/java/demo/csrf/SecurityConfig.java`:

~~~java
package demo.csrf;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("student")
                        .password(encoder.encode("local-test-password-123"))
                        .roles("USER")
                        .build());
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/error").permitAll()
                        .anyRequest().authenticated())
                .formLogin(form -> form.permitAll())
                .logout(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .build();
    }
}
~~~

This configuration **compiles** inside the project above:
- `formLogin()` generates the default GET `/login` page and processes `POST /login`.
- `logout()` preserves POST `/logout` behavior; GET `/logout` renders a confirmation page when CSRF is enabled.
- `csrf(Customizer.withDefaults())` **keeps CSRF enabled** (which is also Spring Security's default).
- `/profile` and `/profile/display-name` both require authentication; GET reads only, POST changes state.
- Passwords are encoded via `DelegatingPasswordEncoder`; the demo password is for local use only, not a production secret.

**No `csrf.disable()`, `ignoringRequestMatchers("/login", "/logout")`, or switching logout to GET**. Those shortcuts would disable the exact protections covered in this lesson.

### 9.4. MockMvc: experimenting with/without CSRF tokens

`src/test/java/demo/csrf/CsrfSecurityTest.java`:

~~~java
package demo.csrf;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfSecurityTest {
    @Autowired
    MockMvc mvc;

    @Autowired
    ProfileStore profiles;

    @BeforeEach
    void reset() {
        profiles.reset();
    }

    @Test
    void loginPageIsPublicAndHasCsrfForm() throws Exception {
        mvc.perform(get("/login"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        org.hamcrest.Matchers.containsString("_csrf")));
    }

    @Test
    void loginWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/login")
                        .param("username", "student")
                        .param("password", "local-test-password-123"))
                .andExpect(status().isForbidden());
    }

    @Test
    void loginWithCsrfIsProcessed() throws Exception {
        mvc.perform(post("/login")
                        .with(csrf())
                        .param("username", "student")
                        .param("password", "local-test-password-123"))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void unsafeProfilePostNeedsCsrfToken() throws Exception {
        mvc.perform(post("/profile/display-name")
                        .with(user("student"))
                        .param("value", "Forged"))
                .andExpect(status().isForbidden());

        org.junit.jupiter.api.Assertions.assertEquals(
                "Initial", profiles.get());
    }

    @Test
    void validCsrfAllowsAuthenticatedUpdate() throws Exception {
        mvc.perform(post("/profile/display-name")
                        .with(user("student"))
                        .with(csrf())
                        .param("value", "Approved"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.displayName").value("Approved"));

        org.junit.jupiter.api.Assertions.assertEquals(
                "Approved", profiles.get());
    }

    @Test
    void invalidCsrfTokenIsRejected() throws Exception {
        mvc.perform(post("/profile/display-name")
                        .with(user("student"))
                        .with(csrf().useInvalidToken())
                        .param("value", "Forged"))
                .andExpect(status().isForbidden());

        org.junit.jupiter.api.Assertions.assertEquals(
                "Initial", profiles.get());
    }

    @Test
    void logoutNeedsCsrfToken() throws Exception {
        mvc.perform(post("/logout")
                        .with(user("student")))
                .andExpect(status().isForbidden());

        mvc.perform(post("/logout")
                        .with(user("student"))
                        .with(csrf()))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/login?logout"));
    }

    @Test
    void profileReadRequiresAuthentication() throws Exception {
        mvc.perform(get("/profile"))
                .andExpect(status().is3xxRedirection());

        mvc.perform(get("/profile").with(user("student")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.displayName").value("Initial"));
    }
}
~~~

Key observations when running the tests:
- `.with(csrf())` is a `spring-security-test` helper; it supplies **a valid token to the test request**, not how browsers "magically have tokens".
- `.with(csrf().useInvalidToken())` simulates a wrong token; the result must be 403 with **no side effects**.
- `.with(user("student"))` **mocks Authentication in MockMvc** to isolate CSRF testing; it does not perform password login. The two `/login` tests exercise the form login flow directly.
- `POST /logout` missing a CSRF token does not run; a valid POST redirects per Spring Security defaults.
- GET `/profile` needs no CSRF token since it is read-only, yet still requires authentication.

Run:

~~~bash
# With matching Gradle installed:
gradle test

# If the project has Gradle Wrapper:
./gradlew test
# Windows:
# gradlew.bat test
~~~

**Expected:** 8 tests pass. Do not assume fixed Gradle stdout strings because output varies by version and environment. To observe in a browser, run `gradle bootRun` and open `http://localhost:8080/login` with username `student` / password `local-test-password-123`. Use HTTP and mock passwords only on localhost; real deployments must use HTTPS. Spring Security's default login/logout pages let you inspect how tokens are rendered without building forms yourself.

### 9.5. Why does a tokenless test return 403 instead of 401?

`CsrfFilter` checks tokens on unsafe requests before controllers run. If missing/invalid, Spring Security typically responds **403 Forbidden**; this is **not** a "wrong username/password" error. An unauthenticated endpoint might redirect to login or return 401/403 depending on configuration and filter ordering, so distinguish **CSRF rejection** from **authentication failure**.

In applications with multiple `SecurityFilterChain`s, verify which chain matches the request; if one chain disables CSRF or only matches part of a path, tests may hit the wrong chain.

## 10. How do HTML forms and JavaScript SPAs obtain tokens?

### 10.1. Server-rendered HTML forms

In a Spring MVC app using a template engine integrated with Spring Security:
- GET `/login` or a form page renders a CSRF token into a hidden input.
- Form POST keeps the same session cookie and submits `_csrf` in the body; `CsrfFilter` validates it.
- Logout forms must also POST with a token; never use a GET link that logs out directly.
- A CSRF token is **not a password** and does not replace session authentication; forms still need valid credentials/permissions.

Thymeleaf `th:action` integrated with Spring MVC's `RequestDataValueProcessor` can automatically insert the hidden CSRF field. If using plain HTML, custom React forms, or a template engine without integration, you must supply the token explicitly.

### 10.2. SPAs using cookie sessions

SPAs commonly send `fetch`/Axios calls to APIs using browser-managed cookies. With Spring Security 6, account for **deferred tokens, BREACH masking, and token clearing** after authentication/logout.

One official approach supports `GET /csrf` for clients to fetch tokens on demand:

~~~java
// Illustrative controller in a Spring MVC project with CSRF enabled.
package demo.csrf;

import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CsrfTokenController {
    @GetMapping("/csrf")
    public CsrfToken csrf(CsrfToken csrfToken) {
        return csrfToken;
    }
}
~~~

If tokens are needed **before login**, permit `GET /csrf` in `authorizeHttpRequests`, yet **never** open arbitrary CORS to the token endpoint, never cache tokens, and enforce proper session policies. This is an **optional extension** for JS frontend projects, unnecessary for the default form login demo.

A same-origin SPA can:
1. `GET /csrf` over a same-origin connection to obtain the token and header name (default `X-CSRF-TOKEN`).
2. When sending POST/PUT/PATCH/DELETE, include `X-CSRF-TOKEN` in the header alongside the valid session cookie.
3. After successful login/logout, **fetch a fresh token** because Spring Security may clear the old one.
4. On 403 errors from expired/rotated tokens, resynchronize per policy; **never** disable CSRF for endless retries.
5. Never attach CSRF tokens to requests to third-party domains, query strings, logs, or unrestricted global HTTP interceptors.

Client-side example **illustrating how to send** (assuming `csrfToken` was already fetched via a same-origin call):

~~~javascript
async function changeDisplayName(csrfToken, value) {
  const body = new URLSearchParams({ value });
  const response = await fetch("/profile/display-name", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      "X-CSRF-TOKEN": csrfToken
    },
    body
  });
  if (!response.ok) {
    throw new Error("Request rejected: " + response.status);
  }
  return response.json();
}
~~~

This JS only demonstrates token-sending logic, **not a complete standalone JavaScript app**. `credentials: "same-origin"` sends cookies for same-origin requests; real protection still comes from server-side token verification. If frontend and API truly sit on different origins, clear CORS and cookie policies **plus CSRF protection** are required, not blindly using `credentials: "include"` everywhere.

### 10.3. Cookie-to-header integration

Spring Security provides `CookieCsrfTokenRepository`. Some SPAs want JS to read a token from the `XSRF-TOKEN` cookie and send it back via `X-XSRF-TOKEN`. To let JS read that cookie, `CookieCsrfTokenRepository.withHttpOnlyFalse()` can be used **within a properly designed pattern**.

**Do not copy that single line and consider Spring Security 6.x configured**: Spring Security 6 uses BREACH/XOR request handlers and deferred loading; frontends sending plain cookie tokens via headers need the matching request handler and must refresh tokens after login/logout. Consult the official SPA guide for your **exact framework version** and test E2E in browsers.

Never set `HttpOnly=false` on the **session cookie** just because the CSRF cookie needs to be readable. The session cookie should remain `Secure`, `HttpOnly`, `SameSite` per threat model.

## 11. Separating Bearer-token APIs from cookie-session apps

A system may have:
- `/web/**` using session cookies, browser login/logout.
- `/api/**` accepting only OAuth2 access tokens explicitly placed in the `Authorization` header by clients.

If truly isolated, a Bearer-only API may omit synchronizer CSRF tokens because cross-origin browsers **do not automatically attach Bearer access tokens**. Still, you must prove:
- The API **does not** accept session cookies/remember-me/Basic as fallback credentials.
- The API's `SecurityFilterChain` matches every API endpoint accurately.
- Gateways/proxies do not "upgrade" authority upstream based on cookies.
- CORS does not carelessly allow credentialed cross-origin requests.
- JWT/opaque access tokens undergo full issuer/audience/expiry/scope validation.
- XSS and token theft remain defended against; dropping CSRF does not mean zero browser vulnerabilities.

**Boundary configuration illustration, not a standalone compilable project:**

~~~java
// In a Spring Boot app with OAuth2 Resource Server
// and two separate SecurityFilterChains ordered by @Order.
@Bean
@Order(1)
SecurityFilterChain bearerApi(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .sessionManagement(s ->
            s.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .csrf(AbstractHttpConfigurer::disable)
        .oauth2ResourceServer(o -> o.jwt(Customizer.withDefaults()))
        .authorizeHttpRequests(a ->
            a.anyRequest().authenticated())
        .build();
}

// Remaining chain serves browser HTML forms:
@Bean
@Order(2)
SecurityFilterChain browserWeb(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(a -> a.anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .csrf(Customizer.withDefaults())
        .build();
}
~~~

The code above is only a **pattern snippet**: it needs full imports, Resource Server dependencies, JWT decoder/issuer config, login/logout policies, and review of chain precedence/entry points. Disabling CSRF on `/api/**` is safe only if those endpoints **truly accept only** non-auto-sent credentials. If any `/api/**` also accepts session cookies, keep or redesign CSRF defenses.

**Common trap:** calling `csrf(csrf -> csrf.ignoringRequestMatchers("/api/**"))` because "REST API", while those APIs still use `JSESSIONID`. Route naming does not prove absence of CSRF risk.

## 12. CORS, Origin/Referer, Fetch Metadata, and defense in depth

### 12.1. CORS is not a complete CSRF mechanism

Browsers can submit cross-origin HTML forms qualifying as *simple requests* without preflight. Browsers that block attacker JavaScript from reading responses under Same-Origin Policy can still dispatch the request to the server.

For requests carrying custom headers like `X-CSRF-TOKEN`, browsers usually require a CORS preflight when cross-origin. That is a useful layer, yet:
- Preflights can be misallowed via wildcards or weak subdomain trust.
- Not every browser-sent request is AJAX with a custom header.
- The server must still verify the **real token** if using the synchronizer pattern.
- Client-side CSRF exists when trusted JS itself is tricked into sending requests to an attacker-controlled URL; JS can then attach the real token.

Never rely solely on `@CrossOrigin`/CORS to protect state-changing POSTs on browser sessions.

### 12.2. Checking Origin/Referer

Servers can inspect HTTP `Origin` or `Referer` to identify the initiating origin for defense in depth. You must:
- Match scheme/host/port exactly against trusted origins, never using weak suffix string checks.
- Handle absent/null headers per policy; **never** treat a missing header as proof of same-origin.
- Watch out for reverse proxies: public host differs from internal host; trust forwarding headers only from controlled proxies.
- Never log full Referers/queries holding sensitive tokens.

Origin checks help, yet cannot alone replace CSRF tokens across apps with diverse browsers/legacy clients or vulnerable same-site subdomains.

### 12.3. Fetch Metadata

Headers such as `Sec-Fetch-Site` (`same-origin`, `same-site`, `cross-site`, `none`), `Sec-Fetch-Mode`, and `Sec-Fetch-Dest` help servers classify requests by browser context.

For instance, a policy may block most **cross-site unsafe requests** when `Sec-Fetch-Site=cross-site`, while needing:
- Fallbacks for browsers not sending Fetch Metadata, also evaluating Origin/Referer/tokens.
- Documented exceptions for OAuth redirects/callbacks or valid cross-origin flows.
- Never equating `same-site` with `same-origin` when untrusted subdomains exist.
- Testing browsers, proxies, bot/API clients, and compatibility before enforcement.

**CSRF tokens + SameSite cookies + Origin/Fetch Metadata + reauthentication on sensitive actions** form defense in depth. No single header covers the entire threat model.

## 13. Sensitive actions needing extra protection

Even with a valid CSRF token, **reauthentication/MFA/transaction confirmation** may still be needed to change recovery emails, add passkeys, transfer funds, alter MFA, or delete accounts. Because:
- Same-origin XSS scripts can submit valid CSRF tokens.
- Users may be in long-lived sessions and sensitive actions demand fresh confirmation.
- CSRF tokens do not verify the user sees the true transaction details if UI spoofing occurs.
- Weak same-site subdomains can create attack paths beyond standard cross-site cases.

Depending on sensitivity, require recent password/passkey/MFA, one-time transaction tokens bound to action parameters, out-of-band confirmation, and auditing. **CAPTCHA** only helps deter bots; it is **not** a core CSRF defense.

## 14. Login/logout with OAuth2, OIDC, SAML, and passkeys

Some login protocols rely on browser redirects or POST callbacks, so you cannot impose a blanket rule "every callback POST must carry a form `_csrf`" while ignoring protocol bindings.

| Flow | Binding data to verify | Keep in mind |
| --- | --- | --- |
| Username/password form | CSRF token on `POST /login`; session policy | Login CSRF can establish an attacker-account session |
| Logout form | CSRF token on `POST /logout` | GET logout should have no side effects |
| OAuth2 Authorization Code | `state`, request correlation, redirect URI, PKCE, issuer/audience and ID token checks for OIDC | `state` protects callbacks against CSRF, **does not** exempt internal POSTs |
| OIDC RP-initiated logout | State/return URL, session, and provider-specific rules | Local logout and OP logout have distinct scopes |
| SAML Web Browser SSO | Signature, issuer, audience, recipient, `InResponseTo`, replay protection | SAML POST/ACS has its own validation; never blanket-exempt other URLs |
| WebAuthn/passkeys | Challenge, origin, RP ID hash, signature, user verification, session/account binding | Do not skip CSRF on credential registration/account linking just because passkeys are used |
| Remember-me | Auto-sent cookie, separately managed token | Still carries CSRF risk on unsafe methods |

**Especially for SAML/OIDC:** browser callbacks invoked by the IdP/AS may lack the app's CSRF token and use distinct verification mechanisms. Exempt **only the exact required endpoints/protocols** with proper Spring Security config, never `csrf.disable()` app-wide. Login initiation, account linking, logout, and internal actions still need dedicated policies.

## 15. Testing real paths

### 15.1. Spring Security matrix

| Test | Request | Expected |
| --- | --- | --- |
| Login page | `GET /login` | 200, renders token for form |
| Forged login | `POST /login` missing CSRF | 403; no authenticated session created |
| Valid login | `POST /login` with CSRF, valid credentials | Authenticates/redirects per config |
| Forged logout | `POST /logout` missing CSRF | 403; logout does not run |
| Valid logout | `POST /logout` with CSRF | Invalidates session/clears context, redirects |
| Logout GET | `GET /logout` | Confirmation page, **does not** log out immediately |
| State-changing POST | Cookie/session auth without CSRF | 403, no side effects |
| POST with wrong token | Invalid token | 403, no side effects |
| POST with valid token | Valid Authentication + CSRF | Proceeds to business authorization/validation |
| Cookie JWT API | Browser auto-attaches cookie | Still must protect against CSRF |
| Bearer-only API | Manual access token header | Verifies access token; decide CSRF by auth transport |
| Side effect via GET | `GET /delete` | Design flaw: switch to unsafe method with CSRF |

### 15.2. Real browser testing

Use browser DevTools + a test environment:
1. Verify session cookies carry proper `Secure`, `HttpOnly`, and `SameSite`.
2. Open GET login and verify the form contains hidden `_csrf` or a valid header-token flow.
3. Submit POST login/logout with missing/wrong tokens in a lab env, confirming rejection and unchanged session state.
4. Check tokens after login/logout (especially SPAs) and verify retry logic never disables CSRF.
5. Test cross-site/same-site subdomains per threat model; confirm whether cookies are actually sent by the browser.
6. Check reverse proxies, CORS, and Fetch Metadata: no bypass via client-asserted Origin/Host/forwarding headers.
7. Confirm `GET`/`HEAD` and safe-designated routes **perform no business state changes**.
8. Test federated login/logout flows for state/issuer/signature/callback rules.
9. Ensure CSRF tokens never appear in URLs, support tickets, logs, analytics, or third-party domains.
10. Test account recovery, email/password changes, and passkey enrollment as high-risk actions.

## 16. Common mistakes

1. **"CSRF only happens when a user is logged in."** False: login CSRF can force browsers onto an attacker's account.
2. **"GET /logout is more convenient than POST."** False: links/navigations can force logout; use POST + CSRF.
3. **"HttpOnly cookies already block CSRF."** False: browsers still **send cookies**; only JS cannot read them.
4. **"Properly signed JWTs prevent CSRF."** False if browsers auto-send the JWT in a cookie.
5. **"The app uses REST JSON so it doesn't need CSRF."** False if the API accepts auto-sent credentials and has simple-request or misconfigured content-type paths.
6. **"CORS blocks reading responses so POST won't run."** False: forms/navigations can still trigger side effects.
7. **"`SameSite=Lax` is an absolute guarantee."** False for GET side effects, same-site subdomains, and browser differences.
8. **"CSRF tokens can go in query URLs."** False: they leak via logs/Referer/history.
9. **"Disable CSRF to fix 403 errors on POST login."** False: put the token in the form and inspect requests.
10. **"Disable CSRF for all `/api/**`."** False when APIs accept cookies/Basic/remember-me.
11. **"Adding any `X-CSRF-TOKEN` header is enough."** False: token patterns must validate the value against the expected token, not just header presence.
12. **"Enabling CORS `*` prevents CSRF."** False; it can widen the attack surface.
13. **"After logout SPAs reuse old CSRF tokens forever."** False: tokens may be cleared and must be refreshed.
14. **"CSRF tokens cure XSS."** False: same-origin XSS can manipulate tokens and requests.
15. **"Browser HTTP Basic needs no CSRF."** False if browsers auto-attach credentials on eligible cross-site requests.
16. **"Missing Origin header means same-origin request."** True only as a mistake—actually false: missing Origin does not prove safety; define a clear policy.
17. **"POST is safe as long as it has a CSRF token."** False: business layers still need authentication, authorization, input validation, and anti-replay/abuse controls.
18. **"Testing `.with(user())` also verifies login/password."** False: that test helper injects Authentication; test `POST /login` separately.

## 17. Self-check exercises

**Q1.** A user opens `GET /logout` and is immediately logged out. What problem could this be?  
**Answer:** Potential forced logout because a safe HTTP method causes side effects. With Spring Security's default CSRF enabled, GET should only show a confirmation page; POST + token performs logout.

**Q2.** `POST /login` has no `JSESSIONID` yet and lacks a CSRF token. Should it pass because "the user isn't logged in yet"?  
**No.** Login alters authentication state; login CSRF is a distinct risk, and Spring Security protects against it by default.

**Q3.** An API uses JWTs, but stores the token in an `HttpOnly` cookie; does CSRF disappear?  
**No.** Browsers can still attach cookies automatically when policy allows. The server needs corresponding CSRF defenses.

**Q4.** An API accepts only OAuth access tokens placed in the `Authorization` header by a trusted JS client; no cookies/Basic accepted. Must it use synchronizer tokens?  
**Not necessarily**, if the threat model and filter chain prove the design. XSS, token theft, CORS misconfiguration, and authorization defenses are still required.

**Q5.** Does `SameSite=Strict` replace permission checks for account deletion?  
**No.** SameSite reduces cross-site cookie sending; permissions, re-authentication, and CSRF/transaction defenses remain essential.

**Q6.** An SPA sends a POST with a CSRF token before login, then gets 403 after login. What should be done?  
**Fetch a fresh CSRF token** per Spring Security integration, because the strategy may clear tokens upon Authentication success; never disable CSRF to "fix" it.

**Q7.** Can two origins `https://app.example.com` and `https://blog.example.com` be same-site?  
**Yes**, yet they have different origins. If the blog is untrusted, SameSite is not a safe origin boundary.

**Q8.** `MockMvc.post("/settings").with(user("student"))` without `csrf()` gets 403; is this a password error?  
**No.** `user()` already mocks an authenticated principal; 403 comes from `CsrfFilter` rejecting an unsafe request.

### Go-live checklist

- [ ] Login/logout forms and state-changing POSTs have CSRF defenses.
- [ ] Logout executes via POST + token; GET is confirmation/read-only only.
- [ ] No GET/HEAD/OPTIONS/TRACE endpoint causes business side effects.
- [ ] Inventoried cookies, Basic/Digest, remember-me, mTLS, bearer headers, and all auto-sent credential mechanisms.
- [ ] Session cookies have appropriate `Secure`/`HttpOnly`/`SameSite`; CSRF tokens never appear in URLs/logs.
- [ ] Spring Security `CsrfFilter` enabled on browser session routes; no blanket `/api/**` exemptions.
- [ ] Forms/SPAs fetch and submit CSRF tokens per exact Spring Security version, refreshing tokens after login/logout.
- [ ] CORS, Origin/Referer, and Fetch Metadata serve as supporting layers, not default replacements for CSRF tokens.
- [ ] Browser/API chains enforce exact boundaries when exempting CSRF for bearer-only endpoints.
- [ ] XSS/CSP, session fixation protection, and re-authentication for sensitive actions evaluated.
- [ ] Tested login/logout CSRF, invalid token, missing token, negative cases, and **zero side effects**.
- [ ] OAuth/OIDC/SAML callbacks have dedicated state/signature/correlation checks and exempt only the strict necessary scope.

## 18. Learning resources

- [Spring Security 6.5 — Cross Site Request Forgery (CSRF)](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html): `CsrfFilter`, session/cookie repositories, login/logout, SPA token rotation, and JavaScript integration.
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html): GET login page, `UsernamePasswordAuthenticationFilter`, and custom forms.
- [Spring Security 6.5 — Handling Logouts](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html): GET confirmation, POST logout, session invalidation, and default redirects.
- [Spring Security 6.5 — Testing with CSRF Protection](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html): `with(csrf())`, `asHeader()`, and `useInvalidToken()`.
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Request_Forgery_Prevention_Cheat_Sheet.html): synchronizer tokens, signed double-submit cookies, SameSite, Fetch Metadata, Origin/Referer, and client-side CSRF.
- [MDN — SameSite cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie#samesitesamesite-value): cookie attributes and cross-site boundaries.

**Takeaway:** CSRF is about **browser-auto-sent credentials** and **state-changing actions**. Protect both **POST login** and **POST logout**, avoid GET logouts; keep CSRF tokens for browser cookies/sessions, use SameSite/CORS/Origin/Fetch Metadata as supporting layers, and exempt CSRF only for APIs genuinely rejecting automatic credentials after full boundary verification.