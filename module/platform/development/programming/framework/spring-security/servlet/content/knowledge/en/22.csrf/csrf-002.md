# CsrfFilter and HTTP Methods Requiring a CSRF Token

## 1. Problem to Solve

In a Spring Security application running on the **Servlet stack**, users can log in with a session; the browser automatically attaches the session cookie to matching requests. An attacker can lure a logged-in user into visiting another page and from there send a data-modifying request to the application. If the server relies solely on the session cookie, the forged request may be processed with the victim's privileges. This is **Cross-Site Request Forgery (CSRF)**.

For example: a user is logged into an account management site. A malicious page submits a POST form to the shipping address change feature. The browser may attach the login cookie depending on cookie/SameSite policies; the server sees a valid session yet lacks proof that the request originated from a trusted UI. A **CSRF token** adds proof that an attacker's page normally cannot read from the same session due to same-origin restrictions.

Three central questions of this lesson:

1. Where does **CsrfFilter** perform its check in the Servlet request flow?
2. Which **HTTP methods** require a token by default, and why does GET differ from POST, PUT, PATCH, and DELETE?
3. How to obtain, send, and test tokens without disabling CSRF protection just to make an API work?

CSRF is a mechanism for protecting state-changing requests when the browser **automatically sends authentication credentials** such as session cookies. It does not replace login, authorization, input validation, or XSS defenses.

## 2. How Does CsrfFilter Work?

**CsrfFilter** resides in the filter chain configured by Spring Security for a Servlet application. It processes requests **before reaching the controller**, using the following key components:

- **CsrfTokenRepository**: stores, loads, or generates tokens; the common default configuration is **HttpSessionCsrfTokenRepository**, storing the token server-side in the HTTP session.
- **CsrfTokenRequestHandler**: exposes the token to the request so the UI can use it and resolves the token submitted by the client; Spring Security 6 versions use a default mechanism with token masking (XOR) to mitigate token leakage via response compression/BREACH.
- **RequestMatcher** for CSRF protection: decides whether a request must have its token **verified**. By default this selection is based on HTTP method.
- **AccessDeniedHandler**: rejects a protected request if the token is missing or incorrect; typically resulting in **HTTP 403 Forbidden**.

Abbreviated flow:

~~~text
HTTP request
    |
    v
SecurityFilterChain (Servlet)
    |
    v
CsrfFilter: load token source, configure request handler
    |
    +-- Exempt method (GET/HEAD/OPTIONS/TRACE by default)
    |       |
    |       +--> Pass through CSRF verification --> subsequent filters/controllers
    |
    +-- Checked method (e.g., POST/PUT/PATCH/DELETE)
            |
            +--> Obtain expected token from repository
            +--> Read client-submitted token (header or parameter)
            |
            +-- Match? -- Yes --> Continue filter chain
                         |
                         +-- No --> 403; controller does not execute the operation
~~~

**Common point of confusion:** CsrfFilter may still be invoked for GET; what is exempted is **requiring a token for the request to proceed**. GET can still be used to **issue/expose the token to the client**. The final HTTP status also depends on other filters, routing, and authorization; "exempt from CSRF" does not mean "always returns 200".

The token from the repository is bound to the user/session context, whereas the token presented by the client is the proof that must match. In session-based setups, sending back the same session cookie when using the token is essential: a token from session A is invalid for session B.

## 3. Which Methods Require a Token by Default?

Spring Security Servlet uses CsrfFilter's default matcher: **CSRF verification is not required for GET, HEAD, TRACE, and OPTIONS; all other methods are subject to verification** if the request passes through a security chain with CSRF enabled and no exception configured.

| HTTP method | Checked for CSRF by default? | Meaning |
| --- | --- | --- |
| **GET** | No | Retrieves a data representation; must not cause business-meaningful state changes. |
| **HEAD** | No | Similar to GET but without a response body. |
| **OPTIONS** | No | Queries server options; commonly used in CORS preflight. |
| **TRACE** | No | Included in the methods excluded by the default matcher; many servers disable TRACE for other security reasons. |
| **POST** | **Yes** | Commonly creates data, submits forms, or executes actions. |
| **PUT** | **Yes** | Writes or replaces a resource; although idempotent in HTTP, it is still not a safe method. |
| **PATCH** | **Yes** | Partially updates a resource. |
| **DELETE** | **Yes** | Deletes a resource; idempotent does not mean exempt from CSRF. |
| **Other methods**, e.g., CONNECT or extension methods | **Yes** | Because they are not among the four methods exempted by default. |

Distinguish two HTTP properties:

- **Safe**: by HTTP contract, the request is not intended to alter state as requested by the user. GET/HEAD/OPTIONS/TRACE are considered safe; systems must design GET to read data and never use GET for deletion, payment, or password changes.
- **Idempotent**: repeating the same request has the same intended effect as a single one. PUT and DELETE can be idempotent **yet are still unsafe** and still require a CSRF token under the default configuration.

Do not conclude "DELETE is safe because it is idempotent" or "POST does not need a token because the endpoint allows anonymous access". **CSRF and authorization are two independent mechanisms**: a `permitAll()` endpoint can still receive a 403 from CsrfFilter when a token is missing.

The matcher can be customized via `csrf().requireCsrfProtectionMatcher(...)` or exceptions added via `ignoringRequestMatchers(...)`; in that case the table above describes the **default**, not an immutable rule for every application.

## 4. Where Does the Token Come From and How Is It Sent?

With the common default configuration **HttpSessionCsrfTokenRepository**:

1. The server issues/reads the CSRF token for the HTTP session. Spring Security 6 supports **deferred tokens**: only actually loading/generating when needed.
2. On a read request or form page, the application embeds the valid token into HTML or returns it from a same-origin endpoint.
3. When sending a protected request, the client sends the **session cookie** together with the **token** obtained from that session.
4. CsrfFilter compares the client-submitted token against the repository token; if missing, wrong, expired, or from a different session, it is rejected.

Default names in the session repository:

- **Form parameter**: `_csrf` (suitable for HTML forms).
- **Header**: `X-CSRF-TOKEN` (suitable for fetch/AJAX).
- **Request attribute** provided by the handler: usually accessed via `CsrfToken.class.getName()` or `_csrf`; Spring Security 6's default handler may return a **masked token value** for rendering to pages.

**Do not manually unwrap or transform the token value obtained from the request attribute before sending it back.** In the example below, the client directly uses the value returned by the `/csrf` endpoint and Spring Security handles it server-side.

Another configuration is **CookieCsrfTokenRepository**, typically using a cookie named `XSRF-TOKEN` and header `X-XSRF-TOKEN`. For SPAs, allowing JavaScript to read the cookie (e.g., `withHttpOnlyFalse()`) must be carefully evaluated. In Spring Security 6, the token sent SPA-style from a cookie does not necessarily match the XOR-masked token rendered into a response; depending on configuration, a **SPA-aware request handler** is needed to properly decode/accept it and load the token when needed. Do not switch repositories and assume an old frontend will automatically work.

Session cookies, CSRF tokens, access tokens, and JWTs are distinct concepts. If an API authenticates **solely** via an Authorization header actively attached by the client and uses no cookies or browser auto-sent credentials, CSRF risk can differ significantly. If a JWT is instead stored in an auto-sent cookie, the CSRF issue still exists.

## 5. Runnable Example: GET Needs No Token, POST Requires a Token

This sample uses **Java 17**, **Spring Boot 3.3.5**, and Spring Security Servlet. It intentionally sets all URLs to `permitAll()` to observe CSRF behavior in isolation, not as a production authorization configuration. Structure:

~~~text
csrf-method-demo/
  pom.xml
  src/main/java/example/csrf/CsrfDemoApplication.java
  src/test/java/example/csrf/CsrfDemoApplicationTests.java
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
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>csrf-method-demo</artifactId>
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

**src/main/java/example/csrf/CsrfDemoApplication.java**:

~~~java
package example.csrf;

import jakarta.servlet.http.HttpServletRequest;
import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class CsrfDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CsrfDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth.anyRequest().permitAll())
                .csrf(Customizer.withDefaults())
                .build();
    }

    @RestController
    static class DemoController {

        @GetMapping("/csrf")
        Map<String, String> csrf(HttpServletRequest request) {
            CsrfToken token = (CsrfToken) request.getAttribute(CsrfToken.class.getName());
            return Map.of("token", token.getToken());
        }

        @GetMapping("/api/messages")
        Map<String, String> read() {
            return Map.of("message", "read permitted");
        }

        @PostMapping("/api/messages")
        Map<String, String> write(@RequestBody Map<String, String> body) {
            return Map.of("saved", body.getOrDefault("message", ""));
        }
    }
}
~~~

The line `.csrf(Customizer.withDefaults())` explicitly shows that the lesson keeps default CSRF protection enabled. The GET `/csrf` endpoint reads the token from the request attribute and calls `getToken()` to generate/load the token when needed; with the session repository, this gives the client a token linked to the session cookie. On Spring Security 6, the returned value may be a masked token and **may differ across GET requests**; that is not necessarily an error.

Run in the project directory with Maven and JDK 17+:

~~~bash
mvn spring-boot:run
~~~

Open a second terminal (the following commands use Bash/Git Bash; requires `curl` and Python 3 to read JSON):

~~~bash
# 1) GET: does not require a CSRF token.
curl -i http://localhost:8080/api/messages

# 2) POST: no token sent -> 403.
curl -i -H 'Content-Type: application/json' \
  -d '{"message":"hello"}' \
  http://localhost:8080/api/messages

# 3) GET token; save the session cookie issued by the server.
TOKEN=$(curl -fsS -c csrf-cookies.txt http://localhost:8080/csrf \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')

# 4) POST with the same cookie and token -> 200.
curl -i -b csrf-cookies.txt \
  -H "X-CSRF-TOKEN: $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"message":"hello"}' \
  http://localhost:8080/api/messages
~~~

Expected results, with the sample app running properly and no other filters/configurations: step 1 is **200 OK** with JSON `{"message":"read permitted"}`; step 2 is **403 Forbidden** (error body depends on configuration); step 4 is **200 OK** with `{"saved":"hello"}`. The token in step 3 is read from actual JSON, not hardcoded. Changing the cookie, using an invalid token, or omitting the header in step 4 will cause verification to fail.

A same-origin frontend can do the same:

~~~javascript
const tokenResponse = await fetch("/csrf", { credentials: "same-origin" });
if (!tokenResponse.ok) throw new Error("Cannot obtain CSRF token");
const { token } = await tokenResponse.json();

const result = await fetch("/api/messages", {
  method: "POST",
  credentials: "same-origin",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": token
  },
  body: JSON.stringify({ message: "hello" })
});
if (!result.ok) throw new Error("Request failed: " + result.status);
console.log(await result.json());
~~~

Inside the browser, the code must run from the application's valid origin; JavaScript from a malicious page cannot normally read the token response from another origin freely. Avoid configuring CORS to allow reading tokens from untrusted sources with credentials.

## 6. Testing CsrfFilter Behavior with MockMvc

File **src/test/java/example/csrf/CsrfDemoApplicationTests.java**:

~~~java
package example.csrf;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfDemoApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void getWithoutTokenIsAllowed() throws Exception {
        mvc.perform(get("/api/messages"))
                .andExpect(status().isOk());
    }

    @Test
    void postWithoutTokenIsRejected() throws Exception {
        mvc.perform(post("/api/messages")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"message\":\"hello\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void postWithValidTokenIsAllowed() throws Exception {
        mvc.perform(post("/api/messages").with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"message\":\"hello\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.saved").value("hello"));
    }
}
~~~

Run `mvn test`. `csrf()` is a **test request post-processor** provided by `spring-security-test`: it attaches a valid token to test functionality passing through the filter, not how a production client generates tokens. You can use `with(csrf().useInvalidToken())` to verify the 403 path with an invalid token.

The **POST** tests demonstrate both branches of CsrfFilter; the method table in section 3 explains the default matcher. If you write real endpoints for PUT/PATCH/DELETE, you should have corresponding missing/valid token tests. Do not conclude CSRF exemption merely from a 404/405 response on a method without a handler.

## 7. When to Adjust the Protection Scope?

Some systems have multiple kinds of endpoints in the same application:

| Scenario | How to evaluate |
| --- | --- |
| Web using session/form login, session cookies sent automatically | **Keep CSRF** for data-modifying methods. |
| Same-origin SPA using session cookies | Keep CSRF; issue the token and transmit it in the header matching the active request handler. |
| True REST API using no cookies/auto-sent credentials, only Bearer tokens via Authorization header attached by the app | Evaluate the threat model to decide protection, based on how clients actually store and send credentials. |
| Machine-to-machine webhook from a provider, not relying on browser sessions | May exclude **the exact webhook path**, while verifying signature/HMAC/secret per provider protocol. |
| POST endpoint for unauthenticated guests | Can still be checked by CSRF; anonymous/`permitAll()` does not automatically exempt from CSRF. |

Example **configuration snippet inside a SecurityFilterChain being built**, not a standalone Java program:

~~~java
http.csrf(csrf -> csrf
    .ignoringRequestMatchers("/webhooks/provider/**")
);
~~~

The snippet above only illustrates a scoped exception. It does not authenticate the webhook and should not be copied without a caller verification mechanism. Avoid configuring `csrf.disable()` for the entire application just because a POST from Postman/curl gets a 403. When there are multiple `SecurityFilterChain` beans, check **which chain actually matches the URL**, because the CsrfFilter and matcher in each chain may differ.

**Note on login and logout:** if CSRF is enabled, login and logout POSTs may also have to send a token. In a Spring Security configuration with CSRF enabled, logout typically defaults to POST. Upon successful authentication/logout, the old token may be cleared or need to be freshly loaded; an SPA holding a token for too long may receive a 403 after a session change. With a template engine such as Thymeleaf combined with Spring MVC/Spring Security, forms can have the CSRF field automatically inserted; with manual fetch calls, developers must send the corresponding header/parameter.

## 8. Diagnosing 403 Errors and Common Design Mistakes

1. **POST/PUT/PATCH/DELETE returns 403, GET returns 200:** first check whether there is a CSRF filter and a missing/wrong token; then check authorization. A 403 status alone does not prove only CSRF caused the error.
2. **Token was sent yet still returns 403:** check whether the client kept the **same session cookie** when fetching and sending the token; check the exact header/parameter name, whether the token was HTML-escaped, whether the session changed, or whether it came from a different repository/request handler.
3. **Sending `X-XSRF-TOKEN` while the server expects `X-CSRF-TOKEN`:** determine the repository, request handler, and frontend convention. The common name of CookieCsrfTokenRepository does not automatically apply to HttpSessionCsrfTokenRepository.
4. **GET mutating data:** this is a serious design flaw. Change the write operation to an appropriate method and require a token; do not "fix" it by requiring a CSRF token on every GET.
5. **Relying on CORS or SameSite as the sole defense:** CORS primarily controls response reading and certain JavaScript requests; HTML forms still have cross-site submission paths. SameSite helps reduce risk, but you must account for cross-site/same-site, subdomains, browsers, and login flows; it is an additional layer, not proof that CsrfFilter is unnecessary.
6. **Disabling CSRF immediately because the API uses JWT:** ask whether the JWT lives in an Authorization header actively attached by the client or in a cookie automatically sent by the browser. The storage location and transport mechanism determine the threat model.
7. **Solving 403 with `permitAll()`:** authorization rules do not bypass CSRF. If an endpoint genuinely needs exemption, evaluate its authentication mechanism and use a narrow exclusion matcher.
8. **Not seeing a token after GET:** with deferred tokens, the token is only loaded/generated when accessed. Render the token via a form or an appropriate `/csrf` endpoint; do not assume every GET always creates a session.
9. **Header token present but no cookie:** if the token is stored in the session, missing the matching session cookie causes a token mismatch. When testing with curl/Postman, remember to carry the cookie jar.
10. **Enabling TRACE because TRACE is listed as CSRF-exempt:** wrong. CSRF protection and HTTP method allowance policies are independent decisions; TRACE is usually blocked at the server/proxy.

For debugging, enable appropriate Spring Security logging in the development environment, tracking **method, URL, selected chain, status, header/parameter names, and cookie/session presence**. Never log raw tokens, session cookies, or credentials in production logs.

## 9. Core Takeaways

- **CsrfFilter** blocks before the controller when a request needs a token but has a missing/incorrect one; safe requests still pass through the filter and can obtain tokens.
- Under the default matcher, **GET, HEAD, TRACE, and OPTIONS do not require CSRF verification**; **POST, PUT, PATCH, DELETE, and remaining methods require verification** if CSRF applies to that request.
- **Safe differs from idempotent**: PUT/DELETE are not exempted just because they can be idempotent.
- **Token and cookie must share the same session context**; the session repository typically accepts `_csrf` or `X-CSRF-TOKEN`. For SPAs using a cookie repository, handle tokens according to Spring Security 6's mechanism.
- When a request returns 403, identify the actual chain, matcher, repository, handler, token, and cookie before deciding to adjust configuration.
