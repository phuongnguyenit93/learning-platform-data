# HttpSessionCsrfTokenRepository and Session-Bound CSRF Tokens (Spring Security Servlet)

## 1. What Does CSRF Protect Against?

CSRF (Cross-Site Request Forgery) occurs when an attacker tricks a logged-in user's browser into sending a state-changing request to an application. For example, the victim has an active login session with a banking website; a malicious page attempts to send a money-transfer POST. Depending on browser cookie rules (especially SameSite), the session cookie may automatically accompany the request. If the server only checks the authentication cookie, it may mistake this for the victim's genuine intent.

A secret, unpredictable **CSRF token** is issued by the server to legitimate pages and required back when performing dangerous operations. An attacker on another origin may trigger certain browser requests, but typically cannot read the token from same-origin page/JSON content due to Same-Origin Policy and proper CORS. The token therefore serves as additional proof that the operation originated from a legitimate UI.

In an HTTP session model:

- **Session cookie** (commonly JSESSIONID) carries the identifier for the server to look up the session; the browser may attach it automatically.
- **CSRF token** is a separate value stored server-side **in HttpSession**, and also provided to the same-origin UI.
- When sending POST/PUT/PATCH/DELETE, the UI must send both the session cookie and the token (form parameter or header). The submitted value must match the server-side token of **that exact session**.
- A CSRF token is **not a session ID**, does not encrypt the session ID, and does not replace authentication or authorization. Someone may not be logged in yet and still have a session and CSRF token (e.g., a login form).

## 2. What Does HttpSessionCsrfTokenRepository Do?

**org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository** is the **CsrfTokenRepository** implementation for Spring Security **Servlet** applications. Its three foundational methods are:

| Method | Meaning |
| --- | --- |
| **generateToken(HttpServletRequest)** | Generates an unpredictable random token and returns a CsrfToken object. |
| **saveToken(CsrfToken, request, response)** | Stores the token in an HttpSession attribute; pass null to remove the stored token. |
| **loadToken(HttpServletRequest)** | Reads the token from the existing HttpSession; returns null if there is no session/token. |

The default form parameter name is **_csrf**, and the default header name is **X-CSRF-TOKEN**; these names can be changed via **setParameterName** and **setHeaderName**. The token value resides in the server-side session; the browser only receives the token when the server actively puts it into HTML or an allowed response.

**Important point about session creation:** in Spring Security 6, CSRF token loading is typically deferred. A GET that does not actually use the token may neither generate/save a token nor create a session merely because CSRF is enabled. When a page calls **getToken()** to display an absent token, a new token is generated, saved into HttpSession, and may cause a new session to be created. Subsequent requests reusing that session will read back the saved token.

Spring Security Servlet normally enables CSRF and uses the HttpSession-backed repository by default; declaring the repository explicitly makes the mechanism visible while learning. Do not confuse this repository with **CookieCsrfTokenRepository** (which stores the token in a cookie) or WebFlux's CSRF solution.

## 3. Processing Flow of CsrfFilter

~~~text
Browser GET /csrf or GET form page
    └─ CsrfFilter prepares deferred token from HttpSessionCsrfTokenRepository
       └─ When page reads token: generate/save if absent, then return token in response
          └─ Browser holds session cookie and token exposed to the application

Browser POST /payments + session cookie + _csrf or X-CSRF-TOKEN
    └─ CsrfFilter retrieves expected token for the session from repository
       └─ CsrfTokenRequestHandler extracts token value sent by client
          ├─ Match: continue filter chain to controller
          └─ Missing/wrong/different session: reject, typically HTTP 403
~~~

By default, CSRF is enforced on HTTP methods capable of modifying data, such as **POST, PUT, PATCH, DELETE**; **GET, HEAD, TRACE, OPTIONS** are considered safe and do not require a token. Hence applications must never use GET to write/delete/transfer money. A **permitAll()** endpoint must still pass CSRF verification if it accepts a protected method: authorization and CSRF are two separate checks.

Conceptual order: **repository** holds the expected token; **request handler** exposes/reads the token in the request; **CsrfFilter** compares and decides whether to continue or block. The repository itself is not where 403 is enforced.

## 4. Runnable Example with Java 17, Spring Boot 3.4.5, and Spring Security Servlet

Create the Maven structure:

~~~text
session-csrf-demo/
├── pom.xml
└── src/
    ├── main/java/demo/csrf/SessionCsrfApplication.java
    └── test/java/demo/csrf/SessionCsrfApplicationTests.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>session-csrf-demo</artifactId>
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

**src/main/java/demo/csrf/SessionCsrfApplication.java**:

~~~java
package demo.csrf;

import jakarta.servlet.http.HttpServletRequest;
import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class SessionCsrfApplication {

    public static void main(String[] args) {
        SpringApplication.run(SessionCsrfApplication.class, args);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth.anyRequest().permitAll())
                .csrf(csrf -> csrf.csrfTokenRepository(
                        new HttpSessionCsrfTokenRepository()))
                .build();
    }

    @GetMapping("/csrf")
    ResponseEntity<Map<String, String>> csrf(HttpServletRequest request) {
        CsrfToken token = (CsrfToken)
                request.getAttribute(CsrfToken.class.getName());
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(Map.of(
                        "headerName", token.getHeaderName(),
                        "parameterName", token.getParameterName(),
                        "token", token.getToken()));
    }

    @PostMapping("/payments")
    Map<String, String> payments(@RequestParam String reference) {
        return Map.of("status", "accepted", "reference", reference);
    }
}
~~~

In this demo, **permitAll()** enables testing CSRF without logging in; real applications must still enforce authentication, authorization, and business validation. **GET /csrf** reads the token attribute attached to the request by Spring Security. Calling **token.getToken()** causes the deferred token to materialize when needed, and **Cache-Control: no-store** prevents caches from storing the sensitive response. The POST endpoint only simulates accepting a reference code and does not perform an actual payment.

### Testing with PowerShell

Start the app in the project directory with **mvn spring-boot:run**. In another PowerShell window:

~~~powershell
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$csrf = Invoke-RestMethod -Uri 'http://localhost:8080/csrf' -WebSession $session

# Missing token: POST is rejected
try {
    Invoke-RestMethod -Uri 'http://localhost:8080/payments' -Method Post -WebSession $session -Body @{ reference = 'INV-001' } | Out-Null
} catch {
    [int]$_.Exception.Response.StatusCode
}

# Same session cookie, with received token: POST is accepted
$headers = @{}
$headers[$csrf.headerName] = $csrf.token
$ok = Invoke-RestMethod -Uri 'http://localhost:8080/payments' -Method Post -WebSession $session -Headers $headers -Body @{ reference = 'INV-001' }
$ok.status
$ok.reference
~~~

Expected observed output:

~~~text
403
accepted
INV-001
~~~

**WebRequestSession** preserves cookies across commands; the **$csrf** variable holds the token received by that same session. If you create another **WebRequestSession** and send the previous session's token, POST must be rejected (typically 403). Trying to drop the cookie while keeping the token also grants no access to the original session.

### Automated Testing with MockMvc

**src/test/java/demo/csrf/SessionCsrfApplicationTests.java**:

~~~java
package demo.csrf;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class SessionCsrfApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void postWithoutTokenIsForbidden() throws Exception {
        mvc.perform(post("/payments").param("reference", "INV-001"))
                .andExpect(status().isForbidden());
    }

    @Test
    void postWithValidTokenSucceeds() throws Exception {
        mvc.perform(post("/payments")
                        .with(csrf())
                        .param("reference", "INV-001"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("accepted"))
                .andExpect(jsonPath("$.reference").value("INV-001"));
    }
}
~~~

Run **mvn test**. spring-security-test's **with(csrf())** constructs a valid token for the test request; it helps verify the filter's accept/reject branches, but **does not replace** integration tests covering real cookies, session timeouts, login/logout, or multiple server instances.

## 5. Embedding Tokens in HTML Forms and AJAX Requests

With Spring MVC and Thymeleaf (requiring **spring-boot-starter-thymeleaf**), a form processed by Thymeleaf can be written as:

~~~html
<form th:action="@{/payments}" method="post">
    <label>Reference code <input name="reference" required></label>
    <button type="submit">Submit</button>
</form>
~~~

When Spring Security and Spring MVC integrate **RequestDataValueProcessor**, Thymeleaf can automatically add a hidden input named **_csrf** to POST forms. Inspect the rendered HTML: the hidden field must contain the real token value from **request/session**, not a hardcoded handwritten string. With plain HTML forms or custom-rendered frameworks, developers must output the token into the form properly.

When JavaScript sends data-modifying requests, send the token received from the backend together with the session cookie, e.g., **X-CSRF-TOKEN** in a header. The browser must retain the right session cookie when fetch/XHR sends requests to the backend; for legitimate cross-origin requests, **credentials**, CORS, and SameSite policies must be designed consistently. **Do not** open CORS overly broadly on the token-issuing endpoint and do not put tokens into query strings, URLs, or application logs.

### Raw Token, Masked Token, and BREACH in Spring Security 6

This is an easy point to misunderstand: **HttpSessionCsrfTokenRepository** stores the **raw token** in the session, while **CsrfTokenRequestHandler** determines how the token is exposed to the request and read back. With modern Servlet configurations, the default handler is usually **XorCsrfTokenRequestAttributeHandler**: it outputs a token masked via XOR with random bytes to mitigate BREACH risk when tokens are reflected in compressed responses. Two token fetches in HTML/responses may show **different token strings despite having the same raw token in the session**; that does not necessarily mean the session changed.

In the demo, use **token.getToken()** directly as provided by Spring Security from the request; this is the presentation value matching the default handler. Do not read the raw token directly from HttpSession and assume every request handler accepts raw tokens everywhere. If building an SPA using a JavaScript-readable cookie/token mechanism, design a **CsrfTokenRequestHandler** suitable for raw headers, and ensure a step to reload the token after authentication/logout. Do not switch to **CookieCsrfTokenRepository.withHttpOnlyFalse()** just to avoid the raw/masked difference without evaluating the security model.

## 6. Token and Session Lifecycle

| Scenario | Consequence to understand |
| --- | --- |
| No session yet, request does not read token | Token/session may not have been generated yet due to deferred loading. |
| Page/form reads token for the first time | Token is generated and saved into HttpSession; may create a new session. |
| Multiple requests within the same session | Repository reuses the stored raw token; presented token may differ due to masking. |
| Token from session A sent with session B cookie | Does not match B's expected token; operation is rejected. |
| Session expired/invalidated | Token tied to old session is gone; client must obtain a new token from a valid session. |
| Login or logout | Standard CSRF strategies such as CsrfAuthenticationStrategy and CsrfLogoutHandler clear old tokens; UI must obtain a new token after state transition. |
| Changing session ID to prevent session fixation | Rotating session ID and rotating CSRF token are independent mechanisms; do not infer solely from the JSESSIONID value. |

**A token is bound to a session**, meaning the expected value is stored per session. That does **not** mean the token is cryptographically bound to IP address, User-Agent, an account, or individual HTTP requests. The default repository also does not set a separate token expiration: effective lifetime is governed by session lifecycle and token clearing/rotation actions.

In multi-replica systems, requests must observe **the same HttpSession data** (e.g., session affinity or Spring Session with a shared store). If a GET request obtains a token on node A but a POST hits node B which cannot read the same session, the user may receive 403 despite having the right header.

## 7. When to Use This Repository and When Not To?

**Suitable:** Servlet web applications with session/cookie login, MVC forms, or web UIs sending requests with session cookies. Natural protection model: the token is server-side data, requiring no separate CSRF cookie.

**Requires different consideration:** genuinely stateless APIs where clients authenticate via an Authorization header added manually per request and do not rely on browser auto-sent credentials. In that case, analyze CSRF risk from the concrete authentication mechanism before deciding. If the backend still uses cookies to authenticate, CSRF must still be evaluated, even if the UI is an SPA or the API returns JSON. Setting **SessionCreationPolicy.STATELESS** while expecting tokens to be stored via **HttpSessionCsrfTokenRepository** typically makes the model inconsistent; choose a compatible session/token strategy.

**CookieCsrfTokenRepository** stores the token in a cookie instead of a server-side session. This changes how the frontend reads tokens and requires raw/masked handling; do not treat the two repositories as equivalent merely because both support CSRF header names.

## 8. Diagnosing 403 Errors and Common Design Mistakes

1. **POST missing token**: confirm the form has hidden **_csrf** or AJAX has the **X-CSRF-TOKEN** header.
2. **Valid token yet wrong session**: verify the session cookie accompanies both the token-fetching request and the POST request; a new session or timeout invalidates the old token.
3. **POST right after login/logout returns 403**: the token may have been cleared by the authentication/logout strategy; fetch a new token before the next action.
4. **Header has token yet still invalid**: check header/parameter name, the actual configured repository, and how the request handler processes raw/masked tokens.
5. **Intermittent 403 on multi-node setups**: check HttpSession storage/routing and session store consistency.
6. **Disabling CSRF to fix 403**: identify the root cause first. For session-cookie-based apps, disabling CSRF usually removes a necessary defense layer.
7. **Letting GET mutate data or relying only on SameSite**: GET must preserve safe semantics; SameSite and Origin/Referer checks can strengthen defense but do not automatically replace tokens.
8. **Token leakage via XSS, URLs, logs, CDN cache, or misconfigured CORS**: CSRF tokens do not stop malicious JavaScript running on the same origin. Use HTTPS, prevent XSS, configure appropriate Secure/HttpOnly/SameSite cookies, and do not cache session-bound content in shared caches.

## 9. Self-Check Understanding

- Why can an attacker make the browser send a session cookie yet struggle to send the right CSRF token? Relate this to Same-Origin Policy and the token residing in a response from the valid origin.
- If two GET responses output different tokens, is that sufficient proof that HttpSession changed? **No**: check the difference between a raw token and an XOR-masked token.
- Why can a POST to a **permitAll()** endpoint still receive 403? Because CSRF is checked independently of authorization rules.
- Why can a previous token no longer be used after a session expires? Because the expected token lived in the old HttpSession and is no longer loaded by the repository for the new session.
- When can a sessionless deployment consider a different CSRF strategy? When the authentication model and how the browser auto-sends credentials have been clearly determined, not merely based on the "REST API" label.

**Remember:** HttpSessionCsrfTokenRepository is responsible for **generating, saving, and loading raw CSRF tokens per HttpSession**. CsrfFilter together with CsrfTokenRequestHandler is responsible for **extracting the client-submitted token, comparing it, and blocking invalid requests**. Understanding session cookies, deferred tokens, masking, and the login/logout lifecycle helps configure properly and diagnose 403s without disabling CSRF.
