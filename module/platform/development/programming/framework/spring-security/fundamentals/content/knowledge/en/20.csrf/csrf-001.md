# What Is CSRF and Why Can a Browser Send Unintended Requests?

> **Topic:** Spring Security – fundamentals → **CSRF** (Cross-Site Request Forgery). This lesson targets Java 17+, Spring Boot 3.x, and Spring Security 6.x. Focus: explaining how browsers **automatically send credentials** in externally triggered requests, the conditions that make an application vulnerable to CSRF, how to defend against CSRF using tokens and other defense layers, Servlet/WebFlux configuration, and testing.

## 1. What Is CSRF?

**Cross-Site Request Forgery (CSRF)** is an attack that causes the browser of a user who is authenticated with website A to **send an unwanted request to website A** from a context controlled by an attacker, such as website B, an email, or embedded content. If website A only checks for a valid cookie/session without verifying the request's legitimacy, the server may execute an action chosen by the attacker under the user's identity.

CSRF does not require the attacker to **know the password**, **read the session cookie**, or **read the response** from the target website. The decisive condition is that the browser can **automatically send credentials** along with a request that the user did not actively authorize.

**Example:** Alice logs in to `https://accounts.example`, then opens `https://other.example`. The external page submits a POST form to change the email on Alice's account. When the browser automatically attaches the valid session cookie (if the cookie policy allows it) and `accounts.example` lacks CSRF defense, the system may accept the request as if Alice sent it.

Distinction:

- **Authentication:** Which user does the request belong to? The cookie/session identifies Alice.
- **Authorization:** Does Alice have permission to change her account email? Probably yes.
- **CSRF protection:** Did this email-change request actually originate from a trusted flow, with proof that an external site cannot forge? This is the missing check in the attack example.

An authenticated session **does not prove specific user intent**.

## 2. Step-by-Step Attack Flow

Suppose the target application has an endpoint `POST /account/change-email` that only checks the session cookie before writing data.

1. Alice logs in at `https://accounts.example`; the server issues a session cookie such as `JSESSIONID=opaque`. The browser stores the cookie and reattaches it when requests qualify.
2. Alice visits `https://other.example` controlled by an attacker; this page has a form whose `action` points to `https://accounts.example/account/change-email`.
3. The attacker's page causes the browser to submit a POST form containing `email=attacker-controlled@example.net`.
4. **If** SameSite/Domain/Path/Secure and the browser policy allow it, the browser attaches the `accounts.example` session cookie to the request sent to `accounts.example`. The attacker does not need to read the cookie.
5. If the server only checks the session and user permissions, without checking a CSRF token or request origin, the email can be changed without Alice actively doing so.
6. Even though the Same-Origin Policy prevents the attacker from reading the response body from `accounts.example`, the email-change action may already have completed.

Illustration of a request the browser may send under suitable cookie conditions:

```http
POST /account/change-email HTTP/1.1
Host: accounts.example
Cookie: JSESSIONID=opaque-session
Content-Type: application/x-www-form-urlencoded

email=attacker-controlled@example.net
```

Illustration of an HTML form hosted on an external site:

```html
<form action="https://accounts.example/account/change-email"
      method="post">
    <input type="hidden" name="email"
           value="attacker-controlled@example.net">
    <button type="submit">Continue</button>
</form>
```

This is an example to **understand the mechanism**, not a claim that every browser attaches session cookies to cross-site POSTs. An explicitly declared `SameSite=Lax` cookie is normally **not sent** in a cross-site form POST; `SameSite=Strict` is even more restrictive. However, if `SameSite=None; Secure` is used or other browser/architectural cases allow credentials, missing a CSRF guard remains a serious issue.

Decision diagram:

```text
External site (other.example)
       |
       | Creates POST form to accounts.example
       v
Alice's browser
       |
       | May auto-attach accounts.example cookie
       v
Spring Security / server
       |
       +-- Only checks session? --> Risk of accepting forged request
       |
       +-- Valid CSRF token? --NO--> Reject
                                  |
                                 YES
                                  |
                                  v
                    Check permissions and business logic
                                  |
                                  v
                           Execute action
```

## 3. Why Can a Browser Send Unintended Requests?

Browsers are designed to load resources, navigate, and submit HTML forms. Site A can trigger certain requests to site B. **The Same-Origin Policy (SOP) generally controls whether scripts can read data/responses from another origin**, rather than blocking all outgoing cross-origin requests before they are sent.

Separate three steps:

1. The external site **triggers the request** (form, navigation, or another request).
2. The browser **decides whether to attach credentials** based on the destination URL and cookie/HTTP authentication policy.
3. The server **decides whether to process the request** after authentication, authorization, and CSRF checks.

An external page does not need to read a successful response; simply causing the server to modify data already creates impact. Also note that an attacker can trick a victim into clicking a link or opening a form that is technically valid but violates business intent.

### 3.1. Ambient Credentials

**Ambient credentials** are credentials that the browser can automatically attach to a request when conditions match:

| Credential | Can browser auto-attach it? | CSRF implication |
|---|---|---|
| Session cookie | Yes, per Domain/Path/SameSite/Secure/browser policy | Classic risk |
| Cached HTTP Basic in browser | Possible, per HTTP protection space/client | Basic can also be CSRF-vulnerable in browsers |
| Client certificate | Possible, per TLS/browser configuration | Needs evaluation in browser context |
| Bearer token actively attached to header by JavaScript | Not automatically sent via cookie/form mechanism | Traditional CSRF risk can be lower; XSS/token theft still needs protection |
| JWT stored in an auto-sent cookie | Yes, per cookie policy | JWT signature does not prevent CSRF |
| API key only in server-to-server request header | Typically not auto-sent by browser | Traditional CSRF differs from session model; still needs authentication and signature verification |

**JWT is not a CSRF defense mechanism**: what matters is whether the token is **automatically** sent by the browser via a cookie or **actively** added to a header by a trusted client.

### 3.2. Secure and HttpOnly Do Not Block CSRF

`Secure` ensures a cookie is only sent over HTTPS according to browser policy. It protects transport, **not proving that the request came from a trusted UI**.

`HttpOnly` restricts JavaScript from reading the cookie directly. The browser can still automatically send that cookie in qualifying requests. Because an attacker **does not need to read the cookie** to exploit CSRF, `HttpOnly` is not a CSRF solution.

`SameSite` is a separate defense layer, analyzed later; it is helpful but has limits regarding safe methods, subdomains, and compatibility.

## 4. Conditions for CSRF to Succeed

CSRF does not succeed automatically just because a cross-site form exists. All conditions must be evaluated:

| Condition | Example | What if missing? |
|---|---|---|
| Target has a state-changing action | Change email, add address, transfer money, grant role | No useful side effect for the attacker |
| Victim has authentication with target | Valid session cookie | Server has no victim session |
| Browser sends credential in triggered request | Cookie matches SameSite and scope | Request may be anonymous or blocked |
| Attacker can craft a request matching endpoint | Method, path, form fields | Server does not accept the request |
| No valid CSRF defense | No token required; Origin not checked | Server may mistakenly trust the request |

Not every API is identical. A strict API accepting only `Content-Type: application/json` with a custom header and a proper CORS allowlist may be harder to attack via an HTML form. However, do not conclude "JSON APIs are definitely immune": you must check content-type fallback, misconfigured CORS, simple requests, untrusted subdomains, XSS, and any auto-sent credentials mechanism.

CSRF can force a user to **change passwords, update contact details, create transactions, subscribe, grant permissions, link accounts, log in to an attacker's account (login CSRF), or be forced to log out**. Impact is bounded by the functions the target exposes and the permissions the victim holds.

## 5. How CSRF, CORS, and Same-Origin Policy Differ

| Mechanism | What does it protect? | What it does NOT guarantee |
|---|---|---|
| **SOP** | Restricts script in origin A from reading/accessing resources of origin B | Does not forbid sending all cross-origin requests |
| **CORS** | Controls JavaScript cross-origin access and preflight/response sharing | Does not block all HTML form submissions or replace CSRF tokens |
| **CSRF token** | Verifies client has proof of a legitimate request rather than only auto-sent credentials | Does not replace authentication, authorization, or XSS defense |
| **SameSite cookie** | Restricts cookies in cross-site contexts | Does not solve all same-site subdomains and state-changing GETs |
| **CSP / XSS defenses** | Reduces ability for malicious script to run in the real origin | Does not replace CSRF defense for requests from other origins |

### 5.1. Why Can an "API Without CORS Enabled" Still Be Vulnerable to CSRF?

A traditional HTML form can send cross-origin requests with content types like `application/x-www-form-urlencoded`, `multipart/form-data`, or `text/plain` without needing JavaScript to read the response via CORS. If the backend accepts the request, checks the session, and performs a side effect, the request can still cause harm.

Cross-origin requests with custom headers or non-CORS-safelisted content types typically require preflight, and a proper CORS policy can make them fail. However, **preventing reading the response** does not mean **preventing all forms of sending requests**.

### 5.2. `fetch` Does Not Represent HTML Forms

`fetch` defaults to `credentials: "same-origin"`, so a cross-origin fetch normally excludes cookies unless code explicitly sets `credentials: "include"`. HTML forms/navigations follow different rules. Thus, testing a fetch request that does not send cookies **does not prove** a cross-site form cannot send cookies either.

### 5.3. CORS Credentials

When frontend and API are on different origins and need cookies, browser `fetch` may use `credentials: "include"`; the server must configure CORS for **specific trusted origins** and credentials. Credentialed CORS responses cannot normally use `Access-Control-Allow-Origin: *`. Overly broad origin allowlists (especially unmanaged subdomains) can negate defenses relying on custom headers/preflight.

## 6. SameSite: Benefits and Limitations

`SameSite` distinguishes requests by **site** (typically based on scheme and registrable domain), which is not strictly identical to origin (scheme, host, port).

For example, `https://app.example.com` and `https://api.example.com` are **different origins** but usually **same site**. If a same-site subdomain is compromised, SameSite may **not** block cookies in requests to another subdomain of the same site.

| Attribute | Cross-site top-level GET | Typical cross-site form POST | Notes |
|---|---|---|---|
| `SameSite=Strict` | Does not attach cookie | Does not attach cookie | Stronger protection, may affect UX when clicking external links |
| Explicitly declared `SameSite=Lax` | Usually sends cookie on navigation GET | Usually does not send | Side-effecting GETs remain dangerous |
| `SameSite=None; Secure` | Can send | Can send | Also depends on third-party cookie blocking/browser policy |

**Do not rely on browser defaults:** when `SameSite` is omitted, some browsers apply Lax-like behavior and may permit certain top-level cross-site POSTs shortly after a new cookie is created. This **differs** from explicitly declaring `SameSite=Lax`. Set the attribute explicitly and test in real browsers.

SameSite **is not a complete check of request intent**, especially in applications with untrusted subdomains or state-changing GETs. Use it as defense in depth alongside CSRF tokens/Origin/Fetch Metadata according to your threat model.

## 7. Why Must Safe HTTP Methods Truly Be Read-Only?

Spring Security by default **does not require a CSRF token** for safe HTTP methods such as `GET`, `HEAD`, `OPTIONS`, `TRACE`. It typically requires a token for `POST`, `PUT`, `PATCH`, `DELETE`. This relies on the principle that **safe methods do not change business state at a client's request**.

**Dangerous design:**

```http
GET /account/delete?id=42 HTTP/1.1
Host: accounts.example
Cookie: JSESSIONID=opaque
```

A browser can navigate to a GET URL from an external link; `SameSite=Lax` still commonly sends cookies on top-level navigation GETs. Therefore, do not design account deletion, email updates, payments, or role grants using GET.

**Better design:** use `POST`/`PUT`/`PATCH`/`DELETE` for state-changing actions, verify CSRF tokens if using browser ambient credentials, then verify authentication, authorization, and object-level permissions. **Switching the HTTP method without enabling a CSRF guard is not a complete solution**.

Some GETs may write logs or internal caches for system purposes; what matters is not letting GET perform business actions an attacker can actively exploit.

## 8. What Is a CSRF Token and How Does It Work?

The **Synchronizer Token Pattern** is a common model in session-based applications:

1. The server generates a hard-to-guess CSRF token bound to the session or a trusted expected source.
2. Legitimate pages/forms receive the token via HTML, request attributes, or a trusted bootstrap/endpoint.
3. When sending a state-changing request, the client submits the token **explicitly** via a hidden form field or custom header.
4. The server compares the client-submitted token against the expected value before executing the action.
5. Requests with a missing or invalid token are rejected, even if the session cookie is valid.

Example request containing a token:

```http
POST /account/change-email HTTP/1.1
Host: accounts.example
Cookie: JSESSIONID=opaque-session
Content-Type: application/x-www-form-urlencoded

email=alice-new@example.com&_csrf=token-created-for-this-session
```

An attacker page can craft a POST form, but under SOP it cannot read the token of Alice's session from the real `accounts.example` page. When the token is unpredictable and properly verified by the server, the attacker lacks the proof needed to forge the request.

**Do not check only a token cookie:** if the browser automatically sends an `XSRF-TOKEN` cookie and the server treats the cookie's mere presence as sufficient, an attacker can exploit automatic cookie transmission as well. The client must **actively present the token** via a header/field per policy, and the backend must verify it against a trusted source.

### 8.1. CSRF Token vs. Session Cookie

- **Session cookie:** authentication credential automatically sent by the browser when eligible.
- **CSRF token:** a value that the legitimate page/client must know and explicitly send back on unsafe requests.
- **Authorization:** determines whether the authenticated user has permission to perform the action.

Having a valid CSRF token without a valid session/permission still does not allow executing protected business operations.

### 8.2. Synchronizer Token and Double-Submit

| Pattern | Meaning | Risks to consider |
|---|---|---|
| Synchronizer token | Expected token stored in server session; client sends field/header | Token lifecycle/session timeout |
| Naive double-submit | Compares token in cookie and header/field | Vulnerable to cookie injection, especially via sibling subdomains |
| Signed double-submit | MAC binds token to session/random value | Requires proper key management and validation |
| Origin/Referer/Fetch Metadata | Relies on browser headers to detect cross-site requests | Needs proper fallback, trusted origin, and reverse proxy correctness |

OWASP recommends **synchronizer token** with session state and **signed double-submit cookie** in many stateless designs. Do not build a custom token generator/comparator from `Math.random()`; use tested security components.

### 8.3. Do Not Put Tokens in URLs

CSRF tokens can leak via browser history, proxy/access logs, `Referer`, analytics, or support captures if placed in the query string. Use hidden form fields/headers, HTTPS, and do not log raw tokens.

## 9. Spring Security Servlet: `CsrfFilter` Enabled by Default

In Spring Security Servlet/MVC applications, CSRF protection is enabled by default for unsafe HTTP methods. Components:

- `CsrfFilter`: determines whether a request requires a CSRF guard, extracts the client-submitted token, and verifies it before entering business flow.
- `HttpSessionCsrfTokenRepository`: default repository storing the expected token in `HttpSession`.
- `CsrfTokenRequestHandler`: exposes/resolves the token and parameter/header names.
- `XorCsrfTokenRequestAttributeHandler`: typically the default handler in Spring Security 6.x to help mitigate BREACH risk when exposing tokens in responses.
- `CookieCsrfTokenRepository`: option when an SPA needs cookie-based token delivery; requires proper integration for deferred tokens/masking.
- `AccessDeniedHandler`: handles requests with missing or invalid tokens, typically returning HTTP **403 Forbidden**.

Simple Servlet configuration:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(form -> form.permitAll())
            .csrf(Customizer.withDefaults());

        return http.build();
    }
}
```

This is a Spring configuration class in a Java 17+/Spring Boot 3.x application, **not standalone source for `javac`** because it requires Spring dependencies. `.csrf(Customizer.withDefaults())` merely states the **default behavior** explicitly. You do not need to disable CSRF to enable form login.

**`permitAll()` does not disable `CsrfFilter`.** For example, `POST /public/register` is permitted for authorization but may still require presenting a CSRF token because it is an unsafe method.

### 9.1. Default Matrix by HTTP Method

| HTTP method | Is CSRF token normally required? | Notes |
|---|---|---|
| `GET` | No | Must be read-only |
| `HEAD` | No | Must not cause business side effects |
| `OPTIONS` | No | Not used to mutate data |
| `TRACE` | No | Not used to mutate data; consider restricting TRACE separately |
| `POST` | Yes | Verifies token |
| `PUT` | Yes | Verifies token |
| `PATCH` | Yes | Verifies token |
| `DELETE` | Yes | Verifies token |

These are the **defaults**. If you have a custom matcher/chain, test against the actual configuration rather than inferring from the table after modifying rules.

### 9.2. HTML Forms and AJAX

Server-rendered forms use the CSRF token in a hidden field. The following HTML example shows **the header/body after the server has rendered a valid token**, not a static form containing a real token:

```html
<form action="/account/change-email" method="post">
  <input name="email" type="email" required>
  <input name="_csrf" type="hidden"
         value="the-session-specific-token-rendered-by-server">
  <button type="submit">Save</button>
</form>
```

In Thymeleaf with Spring Security integration, `th:action` and `RequestDataValueProcessor` can automatically include the hidden CSRF field. If building form templates manually, retrieve the token from the `_csrf` request attribute per framework docs; avoid inserting duplicate fields when the view layer already generates one.

In an SPA/fetch call, use the request header specified by the server, for example:

```javascript
// csrfToken is obtained from a trusted endpoint/bootstrap of the app.
await fetch("/api/profile", {
  method: "PATCH",
  credentials: "same-origin",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": csrfToken
  },
  body: JSON.stringify({ displayName: "Alice" })
});
```

Do not use a single hardcoded token string for all users. For cross-origin APIs, send the token only to trusted destinations, and review CORS/credentials and cookie policies.

### 9.3. SPAs and `CookieCsrfTokenRepository`

Spring Security Servlet provides `CookieCsrfTokenRepository`, typically using cookie `XSRF-TOKEN`, header `X-XSRF-TOKEN`, or form parameter `_csrf` depending on repository/config. If JavaScript genuinely needs to read the token cookie, you can use:

```java
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

// Snippet inside Servlet HttpSecurity configuration:
http.csrf(csrf -> csrf
    .csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse())
);
```

**Only the CSRF token cookie needs to be readable by JS** in this design; the session cookie should remain `HttpOnly=true`. Beyond the repository, Spring Security 6.x applications involve **deferred tokens, BREACH masking, and token rotation/clearing after authentication/logout**; SPAs must handle this accurately per version documentation rather than just copying one line.

## 10. Spring Boot MVC and MockMvc Demo: Requests With or Without a CSRF Token

This example uses Java 17, Spring Boot **3.5.7**, and Spring Security 6.x (dependencies managed by Boot). The POST endpoint **does not execute a real transaction**: it simply returns a string to demonstrate the filter. Passwords in source are for local use only, not production.

Project structure:

```text
csrf-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/csrf/
    │   ├── CsrfDemoApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/com/example/csrf/
        └── CsrfDemoTests.java
```

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>csrf-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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

File `CsrfDemoApplication.java`:

```java
package com.example.csrf;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CsrfDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CsrfDemoApplication.class, args);
    }
}
```

File `SecurityConfig.java`:

```java
package com.example.csrf;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(form -> form.permitAll())
            .csrf(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-password"))
                .roles("USER")
                .build()
        );
    }
}
```

File `DemoController.java`:

```java
package com.example.csrf;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/api/status")
    public String status() {
        return "read-only";
    }

    @PostMapping("/api/submit")
    public String submit() {
        return "accepted";
    }
}
```

Complete tests using `MockMvc` and `spring-security-test`. File `CsrfDemoTests.java`:

```java
package com.example.csrf;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

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
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfDemoTests {

    @Autowired
    MockMvc mvc;

    @Test
    void getWithUserDoesNotNeedCsrf() throws Exception {
        mvc.perform(get("/api/status").with(user("alice")))
            .andExpect(status().isOk())
            .andExpect(content().string("read-only"));
    }

    @Test
    void postWithUserButNoCsrfIsDenied() throws Exception {
        mvc.perform(post("/api/submit").with(user("alice")))
            .andExpect(status().isForbidden());
    }

    @Test
    void invalidCsrfTokenIsDenied() throws Exception {
        mvc.perform(post("/api/submit")
                .with(user("alice"))
                .with(csrf().useInvalidToken()))
            .andExpect(status().isForbidden());
    }

    @Test
    void validCsrfTokenAndAuthenticationSucceed() throws Exception {
        mvc.perform(post("/api/submit")
                .with(user("alice"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("accepted"));
    }
}
```

Run commands (JDK 17+ and Maven):

```bash
mvn test
mvn spring-boot:run
```

Test analysis:

- `.with(user("alice"))` creates mock authentication; **it does not check the form-login password**.
- `.with(csrf())` adds a valid token in `MockMvc` to test the CSRF filter; `.useInvalidToken()` simulates a bad token.
- Authenticated GET needs no token, POST with missing/invalid token gets **403**, authenticated POST with a valid token reaches the controller.
- A valid token **is not enough if the user is unauthenticated/lacks permissions**. To test anonymous access, test separately according to the form login entry point (which may redirect) rather than assuming it is always 401.
- The demo tests focus on the security chain and **do not simulate browser SameSite/CORS**. Browser-level tests must be added in real deployments.

## 11. Standalone Java 17: Modeling Two Server Types

The program below uses plain Java to compare a **weak server that only checks credentials** against a **server requiring a CSRF token for state-changing actions**. It is solely a learning model, does not generate real cookies/tokens, and does not replace security libraries.

File `CsrfDecisionDemo.java`:

```java
public class CsrfDecisionDemo {

    record Request(boolean credentialSent,
                   boolean stateChanging,
                   boolean validCsrfToken) {}

    static boolean vulnerableServerAccepts(Request request) {
        return request.credentialSent();
    }

    static boolean protectedServerAccepts(Request request) {
        return request.credentialSent()
            && (!request.stateChanging() || request.validCsrfToken());
    }

    static void show(String name, Request request) {
        System.out.println(name
            + " vulnerable=" + vulnerableServerAccepts(request)
            + ", protected=" + protectedServerAccepts(request));
    }

    public static void main(String[] args) {
        show("GET authenticated",
            new Request(true, false, false));
        show("POST with browser cookie, no token",
            new Request(true, true, false));
        show("POST with cookie and valid token",
            new Request(true, true, true));
        show("POST with token, no credential",
            new Request(false, true, true));
    }
}
```

Compile and run:

```bash
javac CsrfDecisionDemo.java
java CsrfDecisionDemo
```

Exact stdout produced by the program:

```text
GET authenticated vulnerable=true, protected=true
POST with browser cookie, no token vulnerable=true, protected=false
POST with cookie and valid token vulnerable=true, protected=true
POST with token, no credential vulnerable=false, protected=false
```

The program **does not claim browsers always send cookies for every cross-site POST**. The input `credentialSent=true` simply models a situation where a cookie/credential was sent. In practice, you also need to evaluate SameSite, browser policy, CSRF token generation/validation, and business authorization. This is a decision illustration, not production code.

## 12. Spring WebFlux: CSRF Protection in the Reactive Pipeline

With Spring Security WebFlux, `ServerHttpSecurity` and `SecurityWebFilterChain` replace the Servlet builder/filter chain. CSRF support **is enabled by default**; `WebSessionServerCsrfTokenRepository` uses `WebSession` to store tokens per Spring Security documentation. Reactive components should not be forced with manual `block()` or `subscribe()`.

Example:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/public/**").permitAll()
                .anyExchange().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .build();
    }
}
```

This is a **configuration for a separate WebFlux application**, not a standalone Java class runnable with `javac`. HTTP Basic in browsers can automatically send cached credentials, so CSRF must still be evaluated. For SPAs, `CookieServerCsrfTokenRepository.withHttpOnlyFalse()` can be used if JavaScript needs to read the **CSRF token** cookie; do not disable `HttpOnly` on the session cookie just for this need.

Test snippet with `WebTestClient` properly bound to Spring Security and real endpoints:

```java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;

webTestClient
    .mutateWith(mockUser("alice"))
    .mutateWith(csrf())
    .post()
    .uri("/api/submit")
    .exchange()
    .expectStatus().is2xxSuccessful();
```

A complete test also needs a **POST without a token** case and rejection assertion; success status depends on the actual handler/fixture. Do not assume WebFlux behaves identically to Servlet in every token lifecycle detail.

## 13. Additional Defense Layers: Origin, Referer, and Fetch Metadata

**Origin/Referer:** the backend can compare the exact `Origin` of an unsafe request against **trusted origins**. If `Origin` is absent, `Referer` can be evaluated per a defined fallback. Do not use loose string matching like `contains("accounts.example")` because `accounts.example.attacker.net` is a different origin. Handle proxy/forwarded host/scheme accurately and decide on appropriate fail-closed behavior when headers are missing or `Origin: null`.

**Fetch Metadata:** modern browsers can send `Sec-Fetch-Site`, `Sec-Fetch-Mode`, `Sec-Fetch-Dest`. The server can reject `cross-site` unsafe requests under a policy with exceptions for legitimate flows. This is a very useful signal, but you need to handle clients/browsers that omit these headers and test navigation/SSO flows.

**SameSite:** choose `Lax` or `Strict` intentionally when appropriate; `SameSite=None` must include `Secure`, though browsers may block third-party cookies. Same-site and same-origin are two different concepts; control subdomains sharing a registrable domain.

**CSRF token:** in stateful web apps, this is the default layer to keep. Additional layers do not replace owner/tenant authorization checks and do not eliminate XSS risk.

## 14. Login CSRF, Logout CSRF, and Token Lifecycle

- **Login CSRF:** an attacker forces a victim to log in to an account chosen by the attacker, after which the victim may unintentionally feed data into that account. Spring Security Servlet supports CSRF for login POST by default.
- **Logout CSRF:** an attacker forces a user to log out, causing disruption or workflow trickery. When CSRF protection is enabled, Spring Security Servlet requires POST logout by default (instead of unprotected GET logout).
- **Session timeout:** the expected token stored in the session can expire. Clients sending old tokens are rejected; UX should obtain a new token or prompt re-login.
- **Token rotation:** login/logout/session changes can lead to a new CSRF token; SPAs must refresh tokens via the proper flow.
- **Multiple tabs:** if the token or session changes, test scenarios where an old tab retains an invalid token.
- **Do not log tokens**; do not place tokens in URLs or analytics. A token is a request authenticity mechanism, not something to expose freely.

## 15. When to Consider CSRF Exceptions?

**Do not disable CSRF globally just to stop POSTs from returning 403.** If an endpoint **genuinely** does not rely on browser auto-sent credentials (e.g., a webhook with verified request signatures, or a service-to-service API using a dedicated bearer header), a narrowly scoped exception can be evaluated:

```java
// Snippet inside Servlet configuration; use only after a threat-model review.
http.csrf(csrf -> csrf
    .ignoringRequestMatchers("/webhooks/provider")
);
```

That webhook still needs to **verify signatures/timestamps/replay protection** or a separate authentication mechanism; exempting CSRF does not mean public requests execute unconditionally.

If an API uses a JWT **in a cookie**, from a CSRF standpoint it behaves like cookie authentication; the JWT signature does not prove request intent. If an API uses only a bearer header actively attached by the client with no ambient credentials, traditional CSRF may not apply in that way, though you must still protect against XSS, token theft, CORS issues, authorization flaws, and insecure token storage.

Do not conclude "`SessionCreationPolicy.STATELESS` means no CSRF", because browser HTTP Basic can cache credentials and a stateless app can still receive browser auto-sent cookies/tokens.

## 16. Test Matrix and Checklist

| Test case | Expectation under common policy |
|---|---|
| Authenticated read-only GET without CSRF token | Passes CSRF filter, still subject to authorization |
| Authenticated POST missing CSRF token | 403, business action does not run |
| Authenticated POST with wrong/different-session token | 403, no data written |
| Authenticated POST with valid token, sufficient permission | Proceeds; status depends on handler |
| Anonymous POST with valid token | Still cannot invoke endpoint requiring login |
| User with valid token but missing role | Denied by authorization |
| POST to change email after session timeout | Old token/session invalid; UX handling needed |
| GET accidentally mutating state | Design flaw detected, fix method |
| Cross-site form POST with SameSite=Lax | Cookie usually not sent, still verify threat model |
| Cookie SameSite=None; Secure in permissive browser | May be sent cross-site; CSRF token needed |
| Compromised same-site subdomain | SameSite alone may not prevent |
| JSON API using custom header and misconfigured CORS | Check preflight/origin/credential policy |
| Logout or login POST missing token | Should be protected per configuration |
| XSS running in real origin | CSRF token can be bypassed; defend against XSS separately |

**Production checklist:**

1. Accurately identify clients and authentication mechanisms, especially which credentials browsers auto-attach.
2. Use unsafe HTTP methods for state changes; do not use GET for delete/transfer/grant-role actions.
3. Keep Spring Security CSRF protection for browser cookie/session apps; do not disable it out of habit.
4. Send CSRF tokens via hidden fields/headers; backend verifies against the expected token and session/lifecycle.
5. Session cookies intentionally use `Secure`/`HttpOnly`/`SameSite`; test in real browsers.
6. CORS allowlist and Origin/Referer/Fetch Metadata checks match policy; do not trust wildcards or unknown subdomains.
7. Protect login/logout, handle rotation, session timeouts, and multi-tab behavior.
8. Do not log tokens, session IDs, or passwords; do not put CSRF tokens in query strings.
9. Enforce authorization, tenant/owner/state checks even when the token is valid.
10. Include negative tests for missing/invalid tokens, insufficient permissions, and wrong sessions; verify **no side effect occurs** when rejected.

## 17. Common Pitfalls

1. "If the attacker doesn't know the cookie, CSRF isn't possible." — False: the browser auto-attaches credentials.
2. "Disabling CORS blocks all cross-site requests." — False: form submissions can still reach the server.
3. "`HttpOnly` prevents CSRF." — False: it prevents JavaScript from reading the cookie, not the browser from sending it.
4. "HTTPS prevents CSRF." — False: TLS protects the transport channel, not request origin/intent.
5. "`SameSite=Lax` protects every action." — False: top-level GETs still carry cookies; same-site subdomains are not blocked.
6. "CSRF only happens when using sessions." — False: cached Basic credentials and JWT cookies can be ambient credentials.
7. "Enabling `permitAll` also bypasses CSRF." — False: authorization and the CSRF filter are separate layers.
8. "A valid CSRF token grants full permission." — False: authentication and object-level authorization are still required.
9. "Having an `XSRF-TOKEN` cookie means it's safe." — False: the client must explicitly present the verified token.
10. "A JSON website is definitely immune to CSRF." — False: depends on CORS/preflight, content-type, credentials, and all entry points.
11. "State-changing `GET` is fine because the browser only calls GET." — False: safe methods must be read-only.
12. "401 and 403 are both caused by wrong roles." — False: CSRF usually yields 403; login entry points may return 401/redirect.
13. "Copying `CookieCsrfTokenRepository.withHttpOnlyFalse()` finishes SPA setup." — Not necessarily; deferred tokens, BREACH, and lifecycle must be handled.
14. "With Spring Security `STATELESS`, CSRF is irrelevant." — False if browsers auto-send credentials.
15. "Disabling CSRF makes tests pass, so disable it in production too." — Unsafe without threat-model evaluation.

## 18. References

- [OWASP – CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).
- [Spring Security 6.5 – Servlet CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html).
- [Spring Security – Reactive/WebFlux CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html).
- [Spring Security – CSRF Threat Model](https://docs.spring.io/spring-security/reference/features/exploits/csrf.html).
- [MDN – Same-Origin Policy](https://developer.mozilla.org/en-US/docs/Web/Security/Same-origin_policy).
- [MDN – Set-Cookie / SameSite](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie).

**Key takeaway:** CSRF happens because browsers can **send requests from untrusted contexts while automatically attaching the target website's credentials**. The server sees an authenticated user yet **lacks proof that the request belongs to a legitimate flow**. Keep CSRF token protection for session/cookie-based apps, use SameSite/Origin/Fetch Metadata as defense-in-depth layers, and never forget authorization on real data.