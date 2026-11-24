# CSRF Attack Conditions When Browsers Auto-Send Cookies or Credentials

Someone has logged into `https://bank.example.test`. The browser holds a valid session cookie, such as `JSESSIONID`. While the session remains active, that person opens another page controlled by an attacker. That page can cause the browser to send a request to the banking system. **If the browser automatically attaches credentials, the receiving endpoint has a data-modifying effect, and the server fails to verify that the action truly originated from a trusted UI**, a **Cross-Site Request Forgery (CSRF)** attack can occur.

CSRF does not start with the attacker knowing the password or reading the cookie. The core issue is that the browser **can send held credentials on the user's behalf** when contacting the server that accepts those credentials, while the request was created from an untrusted context. Therefore, an API merely being "logged in" or "permission-checked" **is not enough to conclude the request is an intentional user action**.

This lesson belongs to the **CSRF** group of **Spring Security - fundamentals**. The focus is on **attack conditions when browsers auto-send cookies or credentials**: which credential types can be automatically attached, how `SameSite` cookies affect behavior, why CORS is not a CSRF solution, how Spring Security blocks requests, and how to test actions with and without CSRF tokens. The primary examples use **Java 17+, Spring Boot 3.3.x, Spring Security 6.3.x, and Spring MVC/Servlet**.

## 1. What Is CSRF and Where Does the Risk Lie?

**Cross-Site Request Forgery** is a situation where an untrusted party causes a victim's browser—already holding access privileges—to send an unintended request to a website or API. The target website may mistake that request for an action intentionally performed by the user.

Conceptual example:

~~~text
(1) User logs into app.example.test
        |
        | browser stores app.example.test session cookie
        v
(2) User opens attacker.example.org
        |
        | external page triggers a POST to app.example.test
        v
(3) Browser decides whether to send app.example.test cookie
        |
        | if cookie/credential conditions allow
        v
(4) POST /settings/email carrying the logged-in session
        |
        | server checks authentication: "this is account lan"
        | server checks CSRF/Origin: trusted request from valid flow?
        |
        +--> valid check present → forged request is blocked
        |
        +--> no check → risk of unwanted email change
~~~

The attacker **does not need to view the response** for an operation like changing settings, adding an item to a cart, or initiating a payment to cause side effects. The Same-Origin Policy generally prevents scripts from an external origin from **reading** data from the target origin; it does not by default prevent all ways of **sending** requests to the target origin.

The danger is not merely "having cookies" but that **credentials are automatically included by the browser in requests to the target**, allowing the server to verify identity without proof that the user actively chose the action.

## 2. Conditions That Must Align for a Successful Attack

A classic CSRF scenario requires the following conditions to align:

1. **An active identity or privilege exists:** the victim still has a valid session cookie, cached HTTP authentication credentials in the browser, or another credential that can be automatically used for the target server.
2. **The attacker causes the browser to generate a request to the target endpoint:** for instance, via an HTML form, navigation, auto-loaded resource, or another request mechanism permitted by browser policy.
3. **The browser actually attaches qualifying credentials:** the cookie must match domain/path, HTTPS/Secure, SameSite, and cookie-blocking policies; HTTP Basic/Negotiate or client certificates must be used by the browser under the corresponding circumstances.
4. **The endpoint permits a side-effecting action:** such as `POST /settings/email` changing an email, or worse `GET /account/delete` deleting an account.
5. **The server fails to require sufficient anti-CSRF proof:** missing or improperly checked synchronizer CSRF tokens, inadequate Origin/Referer/Fetch Metadata checks, or policy flaws.
6. **Current privileges suffice for that action:** if the user lacks permission on the resource, authorization may reject it; if the user has permission, the server must verify **request origin intent** beyond that permission.

These are **threat-model conditions**, not a claim that having a cookie and a POST means any arbitrary page can perform CSRF. For example, an explicitly declared `SameSite=Lax` cookie is typically not sent in a cross-site form POST; without an auth cookie and with no other auth mechanism, the request may fail at authentication.

### Distinguishing Necessary Conditions from Outcomes

| Question | If the answer is "no" |
| --- | --- |
| Is there an active credential usable for the target website? | May lack authority to modify data |
| Can the browser create a request to the target? | No forged request is sent |
| Are credentials automatically attached to that request? | Server may only see anonymous |
| Does the request meet the function's permissions? | Authorization may block it |
| Is CSRF validation missing/bypassable? | Forged request is rejected |
| Does the endpoint mutate state? | May have no side effect even if sent |

**Authentication answers "what identity does the request carry?". CSRF protection answers "does this state-changing request carry adequate proof that it came from a trusted flow?".** These are two independent questions, and both are needed when architecture relies on browser auto-sent credentials.

## 3. When Are Cookies Automatically Sent by Browsers?

Suppose the server issues a cookie after login:

~~~http
HTTP/1.1 200 OK
Set-Cookie: JSESSIONID=opaque-session-id; Path=/; Secure; HttpOnly; SameSite=None
~~~

The example illustrates a session cookie used at `https://app.example.test`, with `SameSite=None` permitting consideration of sending the cookie on qualifying cross-site requests. Whether the browser actually sends it also depends on third-party cookie policies, domain/path, expiration, Secure requirements, session state, and other constraints.

When the browser requests a matching domain/path to which the cookie applies, the header sent to the server may be:

~~~http
POST /settings/email HTTP/1.1
Host: app.example.test
Cookie: JSESSIONID=opaque-session-id
Content-Type: application/x-www-form-urlencoded

email=changed%40example.test
~~~

**The external page does not necessarily read this cookie.** The browser selects cookies based on the destination URL; the `Cookie` header normally cannot be set directly by JavaScript from an external page. The attacker only tries to **trigger a request** under conditions where the browser auto-attaches the cookie.

### 3.1. Cookie Attributes to Understand

- `Domain`: determines which hosts can receive the cookie. Omitting `Domain` usually creates a host-only cookie. Overly broad values like `Domain=example.test` can expand exposure across subdomains.
- `Path`: restricts the request paths to which a cookie may be sent; **not a strong security boundary between endpoints on the same origin**.
- `Secure`: normally sends the cookie only over HTTPS; **does not** prevent CSRF when the target request uses HTTPS.
- `HttpOnly`: prevents client-side JavaScript from directly reading the cookie via APIs like `document.cookie`; **does not** stop the browser from auto-sending the cookie over HTTP requests.
- `SameSite`: instructs the browser to restrict sending cookies in cross-site scenarios.
- `Max-Age`/`Expires`: relates to cookie lifetime; a cookie still present in the browser does not prove the server-side session has not expired.

Do not confuse **HttpOnly cookies** with **CSRF protection**: `HttpOnly` reduces the risk of JavaScript stealing the cookie, whereas CSRF relies on the browser **automatically sending the cookie** to the target server.

### 3.2. SameSite Table and Risks

| Target server cookie | Cross-site form POST | Cross-site top-level GET navigation | Meaning |
| --- | --- | --- | --- |
| `SameSite=Strict` | Usually not sent | Usually not sent | Strongly reduces sending cookies from other sites |
| Explicitly declared `SameSite=Lax` | Usually not sent | Can be sent on top-level safe-method navigation | GET must truly be non-state-changing |
| `SameSite=None; Secure` | May be sent if browser policy allows | Can be sent | Cross-site cookies can work; CSRF protection is needed |
| `SameSite` omitted | Depends on browser/current defaults | Depends on browser | Should not assume a uniform policy |

**Important exception:** some browsers apply *Lax-by-default* for cookies without `SameSite`, which may allow a brief relaxation window for POSTs right after the cookie is created. Therefore, **do not rely on default behavior when omitting SameSite**. Declare it intentionally and test on supported browsers.

`SameSite=None` in modern browsers generally requires `Secure`, though that does not mean every browser will always allow third-party cookies: many browsers also block or partition cookies by context.

### 3.3. Same-Site Does Not Mean Same-Origin

An **Origin** usually consists of **scheme + host + port**. A **Site** in "schemeful same-site" terms relies on scheme and registrable domain, without distinguishing every subdomain the way origins do.

Example:

~~~text
https://app.example.test
https://forum.example.test

Two URLs:
- different origins because hosts differ
- may be same site because they share scheme and registrable domain example.test
~~~

If an untrusted subdomain is compromised, requests from that subdomain to the app may be treated as **same-site**, even though they are **cross-origin**. Host-only cookies of `app.example.test` are not exposed to that subdomain, yet the browser **may still send cookies to the app host** when the destination URL is the app, per applicable policy.

This explains why **SameSite does not completely replace CSRF tokens and subdomain security**. Do not set `SameSite=Strict` and assume all attack vectors from another origin are neutralized.

## 4. What Other Credentials Can Browsers Auto-Send?

Besides session cookies, browsers can handle several credential types in CSRF-relevant ways:

| Mechanism | Can browser auto-use on target server requests? | Conditions/notes |
| --- | --- | --- |
| Session cookie `JSESSIONID` | Yes, depending on cookie and browser policy | Common CSRF scenario |
| Cookie containing JWT access token | Yes, if stored as a cookie and cookie qualifies | A token inside a cookie **is still an auto-attached credential** |
| Cached HTTP Basic in browser | Possible, depending on authentication protection space/browser | Do not assume CSRF-immunity just because cookies aren't used |
| HTTP Negotiate/Kerberos/NTLM | Can auto-negotiate per browser/enterprise config | Needs evaluation in intranet environments |
| TLS client certificate (mTLS) | Can be used by browser per config/certificate selection | Risk of unintended requests if endpoint relies solely on this credential |
| Bearer token set in Authorization header by valid JavaScript | Not auto-attached for an external site just because the browser holds a token in memory | Unlike cookies; still must protect against XSS and token storage risks |
| Password saved in password manager | Browser does not auto-send password on every request to domain | Only when actual login/form mechanism uses it |
| Static API key attached in header by a specific client | Browser does not auto-attach it to arbitrary cross-site forms | Evaluate how client/server transmit credentials |

The most important classification question is not the label "cookie", "token", or "password", but:

> **Can a document on an attacker's origin, without knowing a secret, cause the browser to send a request with valid credentials automatically attached?**

If **yes**, the CSRF threat model must be considered. If an API only accepts `Authorization: Bearer ...` **actively attached by trusted app JavaScript** (not stored in auto-sent cookies and without other ambient mechanisms), a normal cross-site HTML form **cannot automatically supply this header**. Classic CSRF risk drops significantly in a pure Bearer-header architecture, though **XSS/token theft** risks remain.

Do not conclude that "JWT is immune to CSRF"; a **JWT stored in an auto-sent cookie** still enables CSRF conditions.

## 5. A Forged Request Can Originate from an HTML Form

HTML can issue a request to another origin, even when JavaScript on that origin **cannot read the response** due to the Same-Origin Policy.

Simulated test model example in a **mock** environment:

~~~html
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Cross-site request simulation</title></head>
<body>
  <form action="https://app.example.test/settings/email" method="post">
    <input type="hidden" name="email" value="changed@example.test">
    <button type="submit">Send test request</button>
  </form>
</body>
</html>
~~~

This HTML page only demonstrates the ability to **originate a POST from a document on another origin**; it does not access a real service, cannot read cookies itself, and does not prove the request succeeds. If a user clicks the button in a local lab, the browser generates a request to the action URL. Whether `app.example.test`'s cookie is sent still depends on `SameSite`, `Secure`, domain/path, browser, and login state. If a cookie is sent, the server still needs to verify a valid CSRF token before mutating data.

### Why Does CORS Not Automatically Block HTML Forms?

Browsers have long permitted certain **simple cross-origin requests** such as form `POST`s with `application/x-www-form-urlencoded`, `multipart/form-data`, or `text/plain`. Scripts being barred from reading the result **does not mean the browser withholds the request**.

A simple form POST **does not require passing a CORS preflight to be sent**. Once the server has executed the state change, the browser later restricting response reading cannot undo the side effect.

For JavaScript `fetch` making cross-origin calls, separate rules apply regarding credentials mode, simple requests, and preflight. Do not extrapolate from a CORS-rejected `fetch` that cross-origin HTML forms/navigations cannot affect the server.

## 6. How Do CORS, SOP, SameSite, and CSRF Tokens Differ?

| Mechanism | Primary control | Does NOT guarantee by itself |
| --- | --- | --- |
| Same-Origin Policy (SOP) | Restricts scripts on another origin from reading/accessing target origin resources | Blocking all cross-origin requests from being sent |
| CORS | Allows/restricts scripts on other origins from reading responses and making certain cross-origin requests | Protecting all form POSTs or confirming user intent |
| `SameSite` cookie | Browser rule for attaching cookies on cross-site requests | Blocking all cross-origin requests or blocking same-site subdomains |
| `HttpOnly` | Reduces ability for JS to read cookies | Preventing the browser from sending cookies |
| `Secure`/HTTPS | Restricts cookie transmission and protects transport channel | Confirming a user intentionally submitted an action |
| `@PreAuthorize` / URL authorization | Does the user have permission on the action/resource? | Whether the request originated from a trusted context |
| Session/context-bound CSRF token | Does the request include proof not automatically sent by the browser? | Replacing authentication, authorization, XSS defense, or validation |
| `Origin`/`Referer` check | Is the request source in an accepted list? | Handling all missing-header cases, proxies, or subdomains/XSS alone |

For example, a server returning:

~~~http
Access-Control-Allow-Origin: https://trusted.example.test
Access-Control-Allow-Credentials: true
~~~

only governs CORS behavior. It does not mean requests from other origins cannot be sent or cause side effects. **Do not use CORS as your sole CSRF defense.**

### Does `fetch` Automatically Send Cross-Origin Cookies?

With `fetch`, the default `credentials` mode is normally `"same-origin"`: scripts do not automatically send cookies on a **cross-origin** request under the default mode. If code uses `credentials: "include"`, the browser may send cookies subject to limits like SameSite/third-party cookie policies; for scripts to read the response, the server must also allow CORS with matching credentials.

However, HTML forms work differently, and CSRF risk cannot be deduced from a single `fetch` snippet. Security reviews must consider **every way a browser can issue requests to an endpoint**, not only the product's official JavaScript SDK.

## 7. GET Is Dangerous When It Modifies Data

HTTP standards treat `GET`, `HEAD`, `OPTIONS`, and `TRACE` as **safe methods**: they are designed not to execute client-requested state changes. Spring Security by default applies CSRF protection to non-safe methods such as `POST`, `PUT`, `PATCH`, `DELETE`.

A poorly designed API:

~~~java
// DO NOT use this design in production:
@GetMapping("/account/remove")
public String remove() {
    accountService.deleteCurrentAccount();
    return "removed";
}
~~~

This is a **design-flaw illustration snippet**, not a standalone Java file. If a GET request can delete an account, a mere link or embedded resource can trigger the action, while `CsrfFilter` by default requires no token on GET.

Proper design must use a state-changing method, protect it with CSRF when using auto-sent credentials, and check permissions:

~~~java
@PostMapping("/account/remove")
public String remove() {
    accountService.deleteCurrentAccount();
    return "removed";
}
~~~

This is also a signature example; place it inside a Controller with a service layer in real use. **Changing GET to POST is not enough** if the server still skips CSRF checks or arbitrarily disables CSRF. Conversely, placing mutating actions on GET renders many default protections ineffective.

Good design ensures **safe methods produce no client-requested business side effects**, while checking CSRF on state-changing requests whenever appropriate for the authentication model.

## 8. How Does Spring Security Handle CSRF on Servlet?

Spring Security provides `CsrfFilter` and related components:

- `CsrfTokenRepository`: generates, stores, and loads the expected CSRF token. The default for session-based Servlet apps is typically `HttpSessionCsrfTokenRepository`.
- `CsrfTokenRequestHandler`: provides the token to views/requests and resolves the actual token from headers/parameters.
- `XorCsrfTokenRequestAttributeHandler`: default handler in Spring Security 6, adding randomization to mitigate BREACH risk and handling token representation exposed to responses.
- `CsrfFilter`: for requests needing protection, compares the client-submitted token with the expected token; if missing/invalid, the request is rejected.

High-level flow:

~~~text
HTTP request arrives at application
       |
       v
CsrfFilter
       |
       +--> Method considered safe? (GET, HEAD, OPTIONS, TRACE)
       |           |
       |           +--> Yes: no token required under default matcher
       |
       +--> Method needs CSRF protection?
                   |
                   +--> load expected token from CsrfTokenRepository
                   +--> read actual token from request parameter/header
                   |
                   +--> valid: continue down filter chain
                   |
                   +--> missing/invalid: AccessDeniedException
                                   → typically returns HTTP 403
~~~

For example, a valid HTML form typically includes a hidden field:

~~~html
<form action="/settings/email" method="post">
    <input name="email" type="email">
    <input type="hidden" name="_csrf" value="VALUE_FROM_SERVER">
    <button type="submit">Save</button>
</form>
~~~

`VALUE_FROM_SERVER` is only a placeholder for a server-rendered token, never hardcoded. Since the browser **does not fabricate a valid value here**, another origin normally cannot know the value bound to the victim's session.

In Spring MVC integrated properly with Thymeleaf/Spring Security, forms with `th:action`/POST can automatically receive the hidden CSRF input via `RequestDataValueProcessor`. For JavaScript SPAs, configuring the CSRF cookie and request handler must also account for **BREACH/XOR masking, deferred tokens, and token clearing/regeneration after login/logout** in Spring Security 6. Do not copy an old recipe using only `CookieCsrfTokenRepository.withHttpOnlyFalse()` assuming every SPA will work properly.

### A CSRF Token Is Not an Access Token

A CSRF token proves that a **state-changing request** carries a value not automatically attached by the browser. It is not used to log in instead of a password/session and does not grant permissions on its own. An attacker holding a CSRF token without qualifying credentials does not become an authorized user. Conversely, a logged-in user without a matching CSRF token can receive a 403 before reaching the Controller.

## 9. Hands-On Spring Boot App: Changing Email Requires Session and CSRF Token

To verify this yourself, let's build a learning application providing:

- `GET /`: public page.
- `GET /settings`: settings page for logged-in users.
- `POST /settings/email`: updates the email for the logged-in account.
- Default form login to create a user session in the browser.
- Default CSRF protection **not disabled**.
- An in-memory store to verify that requests missing a token **perform no mutation**.

The example uses Java 17+, Spring Boot 3.3.x, Spring Security 6.3.x. This is a lab with sample accounts; do not use real account data.

### 9.1. Project Structure

~~~text
csrf-browser-demo/
├── settings.gradle
├── build.gradle
├── src/main/java/example/csrf/
│   ├── CsrfBrowserApplication.java
│   ├── SecurityConfig.java
│   ├── ContactStore.java
│   └── SettingsController.java
├── src/main/resources/templates/
│   └── settings.html
└── src/test/java/example/csrf/
    └── CsrfBrowserTest.java
~~~

### 9.2. settings.gradle and build.gradle

File `settings.gradle`:

~~~groovy
rootProject.name = 'csrf-browser-demo'
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

This is a sample build file for a Java 17 Gradle project. Run from an environment with Gradle or a wrapper compatible with Spring Boot 3.3.x. If an application already has a build file, merge the required dependencies rather than creating duplicate plugin blocks.

### 9.3. CsrfBrowserApplication.java

File `src/main/java/example/csrf/CsrfBrowserApplication.java`:

~~~java
package example.csrf;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CsrfBrowserApplication {
    public static void main(String[] args) {
        SpringApplication.run(CsrfBrowserApplication.class, args);
    }
}
~~~

### 9.4. SecurityConfig.java

File `src/main/java/example/csrf/SecurityConfig.java`:

~~~java
package example.csrf;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
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
                .requestMatchers("/", "/login").permitAll()
                .requestMatchers(HttpMethod.GET, "/settings").authenticated()
                .requestMatchers(HttpMethod.POST, "/settings/email")
                    .hasRole("USER")
                .anyRequest().denyAll()
            )
            .formLogin(Customizer.withDefaults())
            .logout(Customizer.withDefaults());

        // Do not call csrf.disable(): keep default protection for unsafe methods.
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

Notes:

- `formLogin` enables the login form and browser session, so this is **precisely the case with auto-attached credentials** that requires CSRF protection.
- `.hasRole("USER")` requires the `ROLE_USER` authority by default convention.
- CSRF is enabled by default in Spring Security Servlet; calling `.csrf(Customizer.withDefaults())` is unnecessary, though allowed if desired. Here it is left at the default.
- `anyRequest().denyAll()` is a fallback rule for undeclared methods/paths.
- The demo account password is encoded with BCrypt. Real applications do not hardcode in-memory users in source code.

### 9.5. ContactStore.java

File `src/main/java/example/csrf/ContactStore.java`:

~~~java
package example.csrf;

import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Service;

@Service
public class ContactStore {

    private final ConcurrentHashMap<String, String> emails =
            new ConcurrentHashMap<>();

    public void save(String username, String email) {
        emails.put(username, email);
    }

    public String current(String username) {
        return emails.getOrDefault(username, "(unset)");
    }

    public void clear() {
        emails.clear();
    }
}
~~~

This is an in-memory store to easily verify whether a request produces a side effect. Production applications need a database, email validation, principal-based authorization, rate limiting on updates, and an email-change verification mechanism; do not treat `ConcurrentHashMap` as a real account system.

### 9.6. SettingsController.java

File `src/main/java/example/csrf/SettingsController.java`:

~~~java
package example.csrf;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;

@Controller
public class SettingsController {

    private final ContactStore store;

    public SettingsController(ContactStore store) {
        this.store = store;
    }

    @GetMapping("/")
    @ResponseBody
    public String home() {
        return "Public home";
    }

    @GetMapping("/settings")
    public String settings() {
        return "settings";
    }

    @PostMapping("/settings/email")
    @ResponseBody
    public String updateEmail(@RequestParam String email,
                              Authentication authentication) {
        store.save(authentication.getName(), email);
        return "saved:" + email;
    }
}
~~~

`settings()` returns a view name, not HTML content. `updateEmail(...)` creates a side effect **only after the request passes through the security filters**. Do not let the client send a `username` parameter and use it to update arbitrary accounts; the code takes the username from the `Authentication` verified by Spring Security.

### 9.7. settings.html

File `src/main/resources/templates/settings.html`:

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Update email</title>
</head>
<body>
    <h1>Account settings</h1>

    <form th:action="@{/settings/email}" method="post">
        <label for="email">New email</label>
        <input id="email" type="email" name="email" required>
        <button type="submit">Save email</button>
    </form>
</body>
</html>
~~~

With proper Spring MVC + Thymeleaf/Spring Security integration, `th:action` on a POST form goes through form processing and automatically appends the hidden CSRF field (usually named `_csrf`). When running for real, open DevTools and **verify the rendered HTML** contains the hidden token; do not assume every static HTML file gets it automatically.

Do not put `_csrf` into `Set-Cookie` and think that the browser auto-sending the CSRF cookie gives you a synchronizer token: **the actual value must be in a parameter/header that an attacker cannot know or validly submit**.

### 9.8. Running in the Browser

Once a suitable Gradle wrapper is available, run:

~~~bash
./gradlew bootRun
~~~

On Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Visit `http://localhost:8080/settings` while unauthenticated. The browser is redirected to the default login page. Log in using the demo account `lan / demo123`, return to `/settings`, and submit the form. The POST request is checked by Spring Security for the CSRF token and `USER` role, then the Controller returns `saved:...`.

**Browser expectation:** valid forms are processed; forged POST requests without a token are blocked with 403. The sample code is not an execution log from the reader's environment. Do not use sample accounts/passwords in public environments.

## 10. Testing Spring Security with MockMvc

This section proves important server-layer properties:

- Authenticated users **still receive 403** when a POST has a missing or wrong CSRF token.
- Users with a valid token and proper role are allowed to perform the update.
- Even with a valid CSRF token, users **lacking permissions** are still blocked.
- GET cannot be used to change the email.
- Adding an `Origin` header matching the legitimate site **does not replace the CSRF token** in this configuration.

File `src/test/java/example/csrf/CsrfBrowserTest.java`:

~~~java
package example.csrf;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.redirectedUrlPattern;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfBrowserTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ContactStore store;

    @BeforeEach
    void reset() {
        store.clear();
    }

    @Test
    void publicGetWorksWithoutAuthentication() throws Exception {
        mvc.perform(get("/"))
                .andExpect(status().isOk())
                .andExpect(content().string("Public home"));
    }

    @Test
    void anonymousUserIsRedirectedToLogin() throws Exception {
        mvc.perform(get("/settings"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void validUserReceivesFormWithCsrfInput() throws Exception {
        mvc.perform(get("/settings")
                .with(user("lan").roles("USER")))
                .andExpect(status().isOk())
                .andExpect(content().string(containsString("name=\"_csrf\"")));
    }

    @Test
    void authenticatedPostWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/settings/email")
                .with(user("lan").roles("USER"))
                .param("email", "forged@example.test"))
                .andExpect(status().isForbidden());

        assertEquals("(unset)", store.current("lan"));
    }

    @Test
    void invalidCsrfTokenIsRejected() throws Exception {
        mvc.perform(post("/settings/email")
                .with(user("lan").roles("USER"))
                .with(csrf().useInvalidToken())
                .param("email", "forged@example.test"))
                .andExpect(status().isForbidden());

        assertEquals("(unset)", store.current("lan"));
    }

    @Test
    void authenticatedPostWithValidCsrfCanUpdate() throws Exception {
        mvc.perform(post("/settings/email")
                .with(user("lan").roles("USER"))
                .with(csrf())
                .param("email", "lan@example.test"))
                .andExpect(status().isOk())
                .andExpect(content().string("saved:lan@example.test"));

        assertEquals("lan@example.test", store.current("lan"));
    }

    @Test
    void csrfTokenDoesNotReplaceAuthentication() throws Exception {
        mvc.perform(post("/settings/email")
                .with(csrf())
                .param("email", "anonymous@example.test"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void csrfTokenDoesNotReplaceAuthorization() throws Exception {
        mvc.perform(post("/settings/email")
                .with(user("visitor").roles("GUEST"))
                .with(csrf())
                .param("email", "visitor@example.test"))
                .andExpect(status().isForbidden());

        assertEquals("(unset)", store.current("visitor"));
    }

    @Test
    void originHeaderAloneDoesNotReplaceCsrfToken() throws Exception {
        mvc.perform(post("/settings/email")
                .with(user("lan").roles("USER"))
                .header("Origin", "https://app.example.test")
                .param("email", "forged@example.test"))
                .andExpect(status().isForbidden());

        assertEquals("(unset)", store.current("lan"));
    }

    @Test
    void getWithEmailParameterDoesNotUpdate() throws Exception {
        mvc.perform(get("/settings")
                .with(user("lan").roles("USER"))
                .param("email", "forged@example.test"))
                .andExpect(status().isOk());

        assertEquals("(unset)", store.current("lan"));
    }

    @Test
    void logoutPostWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/logout")
                .with(user("lan").roles("USER")))
                .andExpect(status().isForbidden());
    }
}
~~~

Run:

~~~bash
./gradlew test --tests '*CsrfBrowserTest'
~~~

On Windows:

~~~powershell
.\gradlew.bat test --tests "*CsrfBrowserTest"
~~~

**Expected result:** 11 tests pass under a compatible configuration and version. This is a **prediction per Spring Security's contract**, not a live Java/Gradle execution log. They verify that the server blocks requests missing tokens and preserves state, without testing `SameSite` cookies, SOP, or CORS in a real browser.

`MockMvc` is not a browser: `.with(user(...))` only fabricates a test identity for the request. It **does not prove the browser will auto-send cookies from another origin**. To test cross-site cookie conditions, you need a browser test with test origins/sites, HTTPS, and real cookie policies.

## 11. Separate Browser Testing for Auto-Sent Credential Conditions

Real-world CSRF testing must answer two independent questions:

1. **Does the browser automatically send credentials to the target website in the given scenario?**
2. **If the browser sends credentials, does the server reject requests lacking anti-CSRF proof?**

A safe observation workflow on **two test hosts you control**:

1. Run the sample app on a test origin with HTTPS and cookies matching the configuration under test.
2. Log in with a dummy account, verify the cookie exists, and check whether the browser attaches `Cookie` on same-site requests.
3. Open a test HTML page on **another origin**, submit a POST form to the test endpoint. Use only sample data.
4. In DevTools → Network, inspect whether the request to the target server includes a `Cookie` header. Do not record real values into documentation.
5. Check the response and state in `ContactStore`: if the CSRF token is missing, the system must reject it and leave data unchanged.
6. Repeat with `SameSite=Lax`, `Strict`, `None; Secure` cookies and compare across browsers. Frame the test as verifying **browser behavior**, without confusing it with changing authentication code.
7. Repeat with another origin on the same site (a test subdomain) to observe that "cross-origin" does not necessarily mean "cross-site".

Lab conditions must use domains and certificates you manage. Avoid altering cookies on production apps or testing against unauthorized systems.

### Expected Observation Matrix

| Test configuration | Cookie in cross-site POST? | CSRF token absent | Server expectation |
| --- | --- | --- | --- |
| `SameSite=None; Secure` cookie and browser permits | Possible | Yes | Blocked 403 |
| Explicit `SameSite=Lax` cookie | Usually absent | Yes | Unauthenticated/ineligible, and still not updated |
| `SameSite=Strict` cookie | Usually absent | Yes | Not updated |
| Same-site request, valid cookie | Possible | Yes | Blocked 403 |
| Same-site request, valid cookie | Present and valid CSRF token | No | Processed if authorized |

The table lists **expectations**, not measurements from a specific browser. Even when cookies are not sent in a given case, the server must still apply CSRF protection properly because cookie settings, browsers, subdomains, and credential delivery can change.

## 12. Bearer Token APIs: When May CSRF Not Be Needed?

An API accepting only a Bearer access token in a header:

~~~http
POST /api/items HTTP/1.1
Authorization: Bearer example-access-token
Content-Type: application/json

{"name":"demo"}
~~~

If the token is only **actively attached** to the header by the application's JavaScript and **no** browser auto-sent cookie/session/Basic/client certificate is accepted by the API, a typical cross-origin form cannot automatically add an `Authorization` header with an unknown token. Thus, the classic CSRF model diminishes significantly.

In a pure Bearer-header and stateless `oauth2ResourceServer` application, disabling CSRF may be appropriate after thoroughly evaluating the authentication model. Still, distinguish:

- **Bearer token in header actively added by app JavaScript:** a browser on a foreign origin does not automatically carry that header.
- **JWT in an HttpOnly cookie:** the browser **still auto-sends the cookie** if cookie policy permits; CSRF must still be evaluated.
- **API accepting both Bearer headers and session cookies:** an auto-attaching auth path can preserve CSRF risk.
- **XSS on the app's own origin:** malicious script can use the app's context to make requests; a CSRF token is never an XSS cure.

Do not apply a blanket rule like "JSON APIs cannot have CSRF." A server might accept simple form content types, expose a mutating GET endpoint, or use cookies. The decision to enable/disable CSRF must depend on **how credentials are sent by browsers across every endpoint**, not whether the path starts with `/api`.

## 13. Multiple Defense Layers Beyond Synchronizer Tokens

### 13.1. Session- or Context-Bound CSRF Tokens

For forms/session cookies, synchronizer tokens are an essential measure. Tokens must be unpredictable, the server must verify a value sent **non-automatically**, and tokens must not be passed in URLs where they can be logged. In Spring Security 6, token loading/generation can be deferred and rendered values masked to mitigate BREACH risk.

### 13.2. Appropriate SameSite Cookies

Set `SameSite=Lax` or `Strict` when compatible with user experience; use `None; Secure` only when genuine cross-site usage exists alongside other safeguards. With SSO, iframes, or embedded apps, test SameSite adjustments carefully to avoid breaking login flows.

### 13.3. Origin/Referer and Fetch Metadata Checks

For sensitive endpoints, verify `Origin`, fall back to `Referer` properly when needed, and consider `Sec-Fetch-Site` headers to distinguish same-origin, same-site, and cross-site requests. Do not blindly trust every request without `Origin` or every subdomain within the same site.

These checks are supplemental defense layers; they do not remove the need for authorization, validation, and CSRF tokens in high-risk designs.

### 13.4. No Side Effects in Safe Methods

Use appropriate POST/PUT/PATCH/DELETE methods for state-changing operations; avoid designs like `GET /delete` or `GET /transfer`. Combine auth and CSRF on unsafe methods. Do not infer safety from a controller name like "readOnly" if the actual code writes to the database.

### 13.5. Do Not Trust CORS as a CSRF Mechanism

Enable CORS only for trusted origins, while still protecting form POSTs and requests browsers can send without preflight. `Access-Control-Allow-Origin` governs script response-reading rights in many cases, not whether the user intended to transfer funds or change an email.

### 13.6. XSS Prevention and Untrusted Subdomains

XSS lets malicious scripts run in the same origin, read page contents, and extract CSRF tokens if JavaScript can see them. Measures such as output encoding, Content Security Policy, minimizing untrusted JavaScript, auditing dependencies, and isolating subdomains all need assessment. A compromised same-site host can weaken SameSite's effectiveness.

## 14. Common Misconceptions

1. **"An `HttpOnly` cookie makes CSRF impossible."** False. `HttpOnly` stops JS from reading the cookie, not the browser from sending it.
2. **"HTTPS prevents CSRF."** False. TLS secures the transport, not the intent/origin of the request.
3. **"Having Spring Security login and `hasRole` is enough."** False. Authentication/authorization do not replace CSRF protection.
4. **"If CORS blocks reading the response, the attacker causes no side effects."** False. Simple form POSTs can be sent before response-reading even matters.
5. **"Just change GET to POST."** False if POST still accepts auto-sent cookies without checking CSRF.
6. **"`SameSite=Lax` blocks all CSRF."** False. Top-level safe navigation can send cookies; same-site/cross-origin differences and cookie defaults also matter.
7. **"`SameSite=Strict` always blocks every foreign origin."** False when other origins belong to the same site or other attack paths exist.
8. **"JWTs are immune to CSRF."** False if the JWT is stored in a browser auto-sent cookie.
9. **"`Authorization: Bearer` appears automatically in HTML forms from foreign origins."** False for Bearer tokens actively set in headers solely by trusted apps.
10. **"Having a CSRF token authorizes any operation."** False. Tokens do not replace authentication/authorization.
11. **"You can mechanically read the CSRF token from a cookie and send it back alongside the cookie."** If both values are auto-sent or improperly validated, no independent proof is established; understand synchronizer/double-submit patterns and proper implementation.
12. **"A 403 proves CSRF is working."** A 403 can come from missing permissions, invalid CSRF, or another endpoint; inspect state and relevant logs/filters.
13. **"`MockMvc` fully simulates browser `SameSite` policies."** False. `MockMvc` tests the server, not real cross-site browser behavior.
14. **"State-changing GETs are still protected because default CSRF is enabled."** False under standard safe-method matchers.
15. **"A JSON API application cannot have CSRF."** Untrue if cookies are auto-sent or endpoints accept simple requests.
16. **"The browser auto-fills password managers into every POST to that domain."** Not equivalent to sending HTTP authentication: identify specifically which credentials the browser/endpoint uses.

## 15. Scenario Exercises and Answers

**Q1.** A user holds `JSESSIONID` and a foreign page creates a POST to `/settings/email`. What conditions determine whether the browser sends the cookie?

**Answer:** Destination URL, Domain/Path, Secure/HTTPS, SameSite, expiration, and browser cookie policy. A cookie existing does not mean it is sent on every cross-site POST.

**Q2.** The cookie is `HttpOnly; Secure; SameSite=None`, and the browser permits cross-site cookie delivery. The server only checks `authenticated()` for the email-change POST. What is the risk?

**Answer:** CSRF risk exists if the browser auto-sends the session cookie and the endpoint lacks CSRF token/Origin verification or equivalent proof. `HttpOnly`/`Secure` do not block forged actions themselves.

**Q3.** An API requires a Bearer token set in the `Authorization` header by same-origin JavaScript and rejects cookies/Basic. Will an HTML form from a foreign site automatically attach the token?

**Answer:** Not under that model. Classic CSRF risk is reduced, but XSS and Bearer token storage must be controlled.

**Q4.** A server configures CORS only for `https://trusted.example.test`. A simple form POST from another site targets the server. Can we assume the request is never sent?

**Answer:** No. CORS is not a firewall blocking all HTML forms; the request can reach the server, so the server still needs CSRF protection.

**Q5.** A cookie has `SameSite=Lax`. The user clicks a cross-site link to `GET /account/delete`. Why is this still concerning?

**Answer:** `Lax` can send cookies on top-level navigation using a safe method like GET; a side-effecting GET endpoint is a dangerous design. Never use GET to delete data.

**Q6.** Are `https://app.example.test` and `https://forum.example.test` same-site?

**Answer:** They can be same schemeful site, yet different origins. If `forum` is untrusted, `SameSite` alone is not a strong enough boundary.

**Q7.** In `MockMvc`, a POST with `with(user("lan"))` but without `with(csrf())` returns 403. What does this prove?

**Answer:** Under the test configuration, the server rejects POSTs missing a token even when authenticated. It does not prove whether a real browser sends cookies cross-site.

**Q8.** Why is `with(csrf())` without `with(user(...))` still insufficient to change the email?

**Answer:** A CSRF token does not replace authentication/authorization. The endpoint still requires an identity with the `USER` role.

**Q9.** A user is logged in and the API returns 403 for POST without CSRF, yet `GET /account/remove` deletes data successfully. Where is the bug?

**Answer:** State mutation is exposed via GET, a safe method for which Spring Security CSRF does not require a token by default. Fix the HTTP design and policy.

## 16. Pre-Deployment Checklist

- Have you listed every authentication mechanism browsers can auto-send (cookies, Basic/Negotiate, client certificates)?
- Have you identified which APIs use client-attached Bearer headers and which still accept cookies?
- Have you checked Domain, Path, Secure, HttpOnly, SameSite, and third-party cookie policies across target browsers?
- Have you clearly distinguished same-origin vs. same-site and secured untrusted subdomains?
- Do all HTTP GET/HEAD/OPTIONS/TRACE endpoints strictly avoid mutating state?
- Do POST/PUT/PATCH/DELETE endpoints using auto-sent credentials have server-verified CSRF tokens or appropriate safeguards?
- Have you avoided sending tokens in URLs and logs?
- Is CORS restricted to trusted origins while not treated as the sole CSRF defense?
- For SPAs, have you integrated CSRF cookies/request handlers properly for Spring Security 6 and refreshed tokens after login/logout?
- Have you tested with `MockMvc` for authenticated users missing/bad CSRF, valid token lacking permissions, and valid token with permissions?
- Have you observed browser behavior across two test origins/sites to verify cookies are actually attached per policy?
- Have you verified that data mutation **does not happen** when requests are rejected, rather than only checking for status 403?
- Have you verified logout, email change, password change, purchases, and sensitive transactions have proper protection layers?

**Summary:** CSRF can happen when **a request triggered by an untrusted source** still carries **auto-attached valid credentials** from the browser, the endpoint **performs state mutation**, and the server **lacks proper origin/CSRF token verification**. `HttpOnly` cookies, HTTPS, and CORS do not resolve this condition on their own. Proper defense requires combining **CSRF tokens, proper safe-method design, suitable SameSite cookies, origin checks where needed, authentication/authorization, and real browser testing**.

## References

- [Spring Security — Cross Site Request Forgery (Servlet)](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): `CsrfFilter`, `CsrfTokenRepository`, deferred tokens, BREACH, and forms/SPAs.
- [Spring Security — CSRF Overview](https://docs.spring.io/spring-security/reference/features/exploits/csrf.html): attack principles and synchronizer token pattern.
- [Spring Security — MockMvc CSRF Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html): `with(csrf())` and invalid tokens.
- [OWASP — CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): threat model, tokens, Origin, SameSite, Fetch Metadata, CORS.
- [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): attributes and SameSite behavior.
- [MDN — HTTP Cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies): cookies and differences between same-site and cross-site.
