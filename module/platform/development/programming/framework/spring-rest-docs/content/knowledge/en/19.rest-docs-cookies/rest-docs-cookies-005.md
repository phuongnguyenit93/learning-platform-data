# HttpOnly, Secure, SameSite, and their documentation meaning

## Lesson Objectives

Cookies can carry a session identifier, token, UI preference, or data that needs to be sent back across requests. The **HttpOnly**, **Secure**, and **SameSite** attributes govern how browsers access and transmit cookies. When documenting an API with **Spring REST Docs**, recording only the cookie name is insufficient if clients or operations teams need to understand these security characteristics.

This lesson belongs to the **Cookies** chapter of the **SPRING_REST_DOCS** module: creating verifiable REST API documentation from HTTP tests using **MockMvc**, **WebTestClient**, or **REST Assured**; generating snippets for requests, responses, payloads, parameters, and headers; authoring Asciidoctor/Markdown documentation and integrating it into builds and CI.

After this lesson, you will be able to:

- Explain the roles of **HttpOnly**, **Secure**, and **SameSite**.
- Choose cookie configurations suitable for sessions, authentication, or UI preferences.
- Create cookies using Servlet **Cookie** or Spring **ResponseCookie**.
- Verify cookie values and attributes in MockMvc tests.
- Use **responseCookies(...)** to describe cookies and response/header snippets to show **Set-Cookie**.
- Distinguish the cookie descriptor table from actual security attributes.
- Test HTTPS, cross-site, and CSRF scenarios matching the contract.
- Keep real session/token values out of snippets and integrate documentation into CI.

## 1. Three important security attributes

When the server sends a cookie, its attributes appear in the **Set-Cookie** header. Example:

~~~http
HTTP/1.1 200 OK
Set-Cookie: SESSION=sample-session; Path=/; HttpOnly; Secure; SameSite=Lax
Content-Type: application/json

{"status":"authenticated"}
~~~

The three attributes serve distinct roles:

| Attribute | Primary effect | Question to ask |
| --- | --- | --- |
| **HttpOnly** | Restricts JavaScript from accessing the cookie via browser APIs like `document.cookie` | Do we need to prevent client-side scripts from reading the session cookie? |
| **Secure** | Instructs the client to send the cookie only over secure connections | Must the cookie be sent exclusively over HTTPS? |
| **SameSite** | Controls cookie transmission in cross-site request contexts | Should the cookie be sent during navigations or requests originating from another site? |

These attributes are enforced by the client/browser according to cookie rules. They do not encrypt the cookie value and do not replace authentication, authorization, CSRF protection, or XSS controls.

## 2. HttpOnly: restricting cookie access from JavaScript

### 2.1. Meaning

A cookie with **HttpOnly** cannot be accessed through browser-side JavaScript APIs such as **document.cookie**. The browser can still automatically send the cookie in matching requests based on `Domain`, `Path`, `Secure`, and `SameSite`.

This property is useful for server-managed session or authentication cookies:

~~~http
Set-Cookie: SESSION=sample-session; Path=/; HttpOnly; Secure; SameSite=Lax
~~~

If a web page suffers from an XSS vulnerability, `HttpOnly` can prevent a script from directly reading the session cookie value via `document.cookie`. However, it **does not stop a malicious script from making requests using the active session** in the victim's browser. Therefore, you still need XSS prevention, input/output validation, and an appropriate Content Security Policy.

### 2.2. When should it be used?

| Cookie type | Is HttpOnly usually appropriate? | Reason |
| --- | --- | --- |
| Server-managed session cookie | Yes | JavaScript does not need to read the session identifier |
| Server-managed authentication cookie | Usually yes | Restricts direct token theft via scripts |
| Preference cookie like `locale` | Depends on architecture | If JavaScript must read it to change UI, `HttpOnly` is not appropriate |
| CSRF cookie read by JavaScript and sent back in a header | Possibly no | Client scripts need to read the token by design; evaluate the CSRF model carefully |

Do not enable `HttpOnly` simply because it sounds like a universally “safe” attribute. Consider whether the client needs to read the cookie and examine the authentication/CSRF design in use.

## 3. Secure: sending cookies only over a secure channel

### 3.1. Meaning

The **Secure** attribute requires the user agent to send the cookie only over connections considered secure under cookie rules, typically HTTPS:

~~~http
Set-Cookie: SESSION=sample-session; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

`Secure` helps prevent sending session cookies over unencrypted HTTP. It does not encrypt cookies in the database, prevent values from leaking into logs, or replace using TLS across the entire application.

In production, authentication cookies typically require **Secure** alongside HTTPS. If the application sits behind a reverse proxy or load balancer, configure external scheme detection securely so cookies are not issued with the wrong policy.

### 3.2. Secure and local environments

MockMvc tests generally do not establish a real HTTPS connection; they invoke the application in a simulated environment. Thus, a cookie with `Secure` can still be verified in the response with MockMvc, but that test **does not prove** browsers will send the cookie across a real deployed HTTPS/HTTP flow.

Do not downgrade production settings just to make local tests easier to run. Use independent test fixtures and check the `Set-Cookie` header; if you need to confirm browser cookie-sending behavior, add integration tests over HTTPS in an appropriate environment.

## 4. SameSite: controlling cookies in cross-site contexts

`SameSite` affects whether the browser sends a cookie when a request originates from a different site context. Three common values:

| Value | General description | Common use cases |
| --- | --- | --- |
| **Strict** | Tightly restricts sending cookies on cross-site requests | Sensitive sessions or areas that should not carry cookies on navigations from another site |
| **Lax** | Allows certain safe top-level navigations while restricting many other cross-site requests | Commonly chosen default for session cookies in many web applications |
| **None** | Allows the cookie to be sent in cross-site contexts subject to other conditions | Login flows or integrations that genuinely require cross-site cookies |

For **SameSite=None** cookies, modern browsers require the **Secure** attribute. Use HTTPS and verify behavior in the browsers your application supports.

### 4.1. SameSite and CSRF

Browsers automatically attaching cookies to requests is a factor in CSRF models. `SameSite` can mitigate some cross-site requests carrying cookies, but it does not replace comprehensive CSRF protection:

- For session-based applications, clearly define the CSRF token mechanism and how clients send the token back.
- Test legitimate cross-site flows such as OAuth/OIDC redirects or third-party payment callbacks.
- Do not assume `GET` is safe if an endpoint actually mutates state.
- Combine `Origin`/`Referer` checks, CSRF tokens, and defenses suited to your architecture.

Choosing `Strict`, `Lax`, or `None` must be grounded in real browser flows, not MockMvc tests alone.

## 5. Configuring cookies in Spring

### 5.1. Using Servlet Cookie

In Spring MVC running on Servlets, cookies can be created with **jakarta.servlet.http.Cookie**:

~~~java
import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletResponse;

Cookie session = new Cookie("SESSION", "sample-session");
session.setPath("/");
session.setHttpOnly(true);
session.setSecure(true);
session.setMaxAge(1800);
response.addCookie(session);
~~~

The traditional Servlet Cookie API has setters for `HttpOnly`, `Secure`, `Path`, `Domain`, and `Max-Age`; configuring `SameSite` depends on the servlet/container version or requires adding it via a header or supported mechanism. Avoid arbitrary `Set-Cookie` string concatenation when the framework provides a structured API.

### 5.2. Using Spring ResponseCookie

Spring provides **org.springframework.http.ResponseCookie** to build cookies with a fluent API:

~~~java
import org.springframework.http.ResponseCookie;

ResponseCookie session = ResponseCookie.from("SESSION", "sample-session")
    .path("/")
    .httpOnly(true)
    .secure(true)
    .sameSite("Lax")
    .maxAge(1800)
    .build();

response.addHeader("Set-Cookie", session.toString());
~~~

Check the API of your Spring Framework version to confirm supported methods and parameter types. Avoid issuing two cookies with the same name simultaneously by calling both `addCookie` and manually adding a `Set-Cookie` header.

### 5.3. Example controller issuing a session cookie

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class SessionController {

    @PostMapping("/api/session")
    ResponseEntity<SessionResponse> createSession() {
        // Illustrative value for the example only; real applications must
        // use a random session identifier managed by the security mechanism.
        ResponseCookie cookie = ResponseCookie.from(
                "SESSION", "test-session-placeholder")
            .path("/")
            .httpOnly(true)
            .secure(true)
            .sameSite("Lax")
            .maxAge(1800)
            .build();

        return ResponseEntity.ok()
            .header(HttpHeaders.SET_COOKIE, cookie.toString())
            .body(new SessionResponse("created"));
    }
}

record SessionResponse(String status) {}
~~~

Do not use the hardcoded string above as an actual session identifier. Production systems must generate, store, rotate, and revoke sessions securely; the example focuses solely on cookie configuration.

## 6. Documenting security attributes with Spring REST Docs

### 6.1. responseCookies describes cookie name and meaning

Spring REST Docs uses **responseCookies(...)** and **cookieWithName(...)** to describe response cookies:

~~~java
import static org.springframework.restdocs.cookies.CookieDocumentation.cookieWithName;
import static org.springframework.restdocs.cookies.CookieDocumentation.responseCookies;

responseCookies(
    cookieWithName("SESSION")
        .description("Server-managed session cookie; browser sends it back on matching requests")
)
~~~

Cookie descriptors document the **name and meaning**. The **response-cookies.adoc** table is not a full table of all `Set-Cookie` attributes. Flags such as **HttpOnly**, **Secure**, **SameSite**, **Path**, and **Max-Age** appear in the **Set-Cookie** header of the response snippet or can be explained further in prose.

### 6.2. Recording the Set-Cookie header

In the same operation, you can use **responseHeaders(...)** to explicitly highlight the `Set-Cookie` header:

~~~java
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;

responseHeaders(
    headerWithName("Set-Cookie")
        .description("Session cookie along with security attributes set by the server")
)
~~~

The **Set-Cookie** header may appear multiple times in a response, typically one header per cookie. When documenting multiple cookies, verify your REST Docs version's header snippet behavior and still use **responseCookies(...)** to document each cookie by name.

When attributes need emphasis, add a clear explanatory paragraph:

~~~asciidoc
The SESSION cookie is issued with HttpOnly and Secure. SameSite=Lax restricts the browser from sending the cookie in cross-site contexts; the application requires HTTPS.
~~~

This paragraph must accurately reflect the tested response configuration rather than stating an intended policy while the code emits different values.

## 7. Testing HttpOnly and Secure with MockMvc

MockMvc provides cookie matchers to verify attributes represented by the Servlet API:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.cookies.CookieDocumentation.cookieWithName;
import static org.springframework.restdocs.cookies.CookieDocumentation.responseCookies;
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.cookie;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(SessionController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class SessionCookieDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentSecureHttpOnlySessionCookie() throws Exception {
        mockMvc.perform(post("/api/session")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(cookie().exists("SESSION"))
            .andExpect(cookie().httpOnly("SESSION", true))
            .andExpect(cookie().secure("SESSION", true))
            .andExpect(cookie().path("SESSION", "/"))
            .andExpect(cookie().maxAge("SESSION", 1800))
            .andExpect(header().string("Set-Cookie",
                org.hamcrest.Matchers.allOf(
                    org.hamcrest.Matchers.containsString("HttpOnly"),
                    org.hamcrest.Matchers.containsString("Secure"),
                    org.hamcrest.Matchers.containsString("SameSite=Lax")
                )))
            .andDo(document("session-create",
                responseCookies(
                    cookieWithName("SESSION")
                        .description("Server-managed session cookie")
                ),
                responseHeaders(
                    headerWithName("Set-Cookie")
                        .description("Session cookie with HttpOnly, Secure, and SameSite attributes")
                )
            ));
    }
}
~~~

In the test:

- **cookie().httpOnly(...)** verifies the `HttpOnly` flag.
- **cookie().secure(...)** verifies the `Secure` flag.
- **cookie().path(...)** and **cookie().maxAge(...)** verify additional lifecycle/scope attributes.
- Assertions on **Set-Cookie** verify `SameSite` in the `ResponseCookie` example.
- **responseCookies(...)** generates the cookie name table; **responseHeaders(...)** documents the emitted header.

When there are multiple `Set-Cookie` headers, do not assume **header().string("Set-Cookie", ...)** always picks the right header if the response has multiple cookies. You can retrieve the list of headers and assert each value appropriately.

### 7.1. Testing SameSite

`SameSite` does not have a dedicated matcher in every MockMvc version. You can inspect the `Set-Cookie` header:

~~~java
mockMvc.perform(post("/api/session"))
    .andExpect(header().string("Set-Cookie",
        org.hamcrest.Matchers.containsString("SameSite=Lax")));
~~~

This is an assertion on the header string emitted by the server, not a test of whether a browser actually sends the cookie in a cross-site flow. For browser behavior, integration or end-to-end tests over HTTPS and real origins are required.

## 8. What snippets prove and what they do not prove

| Check/documentation | Can verify | Cannot verify by itself |
| --- | --- | --- |
| **responseCookies(...)** | Declared cookie name and description match the operation | That browsers store the cookie properly in every context |
| **http-response.adoc** | Actual test response, including the recorded `Set-Cookie` | That browsers enforce `Secure`/`HttpOnly`/`SameSite` as intended |
| MockMvc cookie matchers | Value, `HttpOnly`, `Secure`, `Path`, `Max-Age` in simulated responses | Whether browsers reject cookies over HTTP or send them cross-site |
| **SameSite=Lax** assertion on `Set-Cookie` | That the server emits that attribute | That OAuth, redirects, or CSRF flows work properly in browsers |
| Browser integration test | Cookie behavior in browsers/HTTPS per test scenarios | That all browsers/versions behave identically without testing them |

Therefore, REST Docs documentation and MockMvc tests should be paired with browser tests whenever the contract depends on browser cookie policies.

## 9. Choosing policies by cookie type

| Cookie | HttpOnly | Secure | Suggested SameSite to evaluate |
| --- | --- | --- | --- |
| Web application session | Usually enabled | Enabled on production HTTPS | `Lax` or `Strict` depending on login/navigation flows |
| Refresh token in cookie | Usually enabled | Enabled | `Lax`/`Strict` if architecture allows; evaluate cross-site flows |
| CSRF token cookie read by JavaScript | May need to be disabled | Enabled on HTTPS | Per CSRF design and client flow |
| Preference that JavaScript must read | Usually disabled | Depends on data and environment | Choose according to cross-site needs |
| Cookie embedded in iframe or cross-site flow | Usually enabled if JS need not read it | Usually required | `None` may be necessary, paired with `Secure` |

This is a starting point for evaluation, not a mandatory configuration for every application. Examine how clients work, XSS/CSRF risks, domains, HTTPS, redirects, iframes, and browser policies.

## 10. Including snippets and Asciidoctor documentation

After tests generate the **session-create** operation, the snippets directory may include:

~~~text
build/generated-snippets/session-create/
├── http-request.adoc
├── http-response.adoc
├── response-cookies.adoc
└── response-headers.adoc
~~~

In **src/docs/asciidoc/session.adoc**:

~~~asciidoc
= Session API
:toc: left

== Create session

POST /api/session

=== Response cookie

include::{snippets}/session-create/response-cookies.adoc[]

=== Response headers

include::{snippets}/session-create/response-headers.adoc[]

=== HTTP response

include::{snippets}/session-create/http-response.adoc[]

The SESSION cookie is issued with HttpOnly, Secure, and SameSite=Lax. The API uses HTTPS; clients do not need to read the session value from JavaScript.
~~~

The final paragraph is only accurate when tests and code actually produce the cookie as described. If `SameSite` or other attributes change, update both tests and documentation together.

### 10.1. Gradle/CI integration

Gradle Groovy DSL example, assuming the project already applies the **org.asciidoctor.jvm.convert** plugin:

~~~groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
    attributes 'snippets': snippetsDir
}
~~~

In CI:

1. Run the MockMvc tests that create the cookie.
2. Assert the `HttpOnly`, `Secure`, `SameSite`, and related attributes.
3. Generate `response-cookies`, `response-headers`, and `http-response` snippets.
4. Build Asciidoctor after tests succeed.
5. Verify the output contains no real session values before publishing.

If the final documentation is Markdown, an appropriate conversion or embedding mechanism is needed; **include::{snippets}/...[]** is Asciidoctor syntax.

## 11. Security and common errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Session cookie lacks `HttpOnly` | Forgot to configure or another cookie-issuing mechanism was used | Assert `HttpOnly` and inspect the actual `Set-Cookie` |
| Production cookie lacks `Secure` | Application misdetects scheme behind proxy or configuration is missing | Configure HTTPS/forwarded headers securely and test the header |
| `SameSite=None` without `Secure` | Cookie configuration incompatible with modern browser requirements | Add `Secure` and run browser tests over HTTPS |
| MockMvc test passes but browser does not send cookie | MockMvc does not simulate browser cross-site policies | Add end-to-end tests on real browsers/origins |
| JavaScript cannot read preference cookie | `HttpOnly` enabled while client needs to read the cookie | Review requirements; consider moving data to API/JSON |
| Documentation claims cookie fully protects against CSRF | Confusing `SameSite` with a complete CSRF solution | Document the actual CSRF mechanism and test the flow |
| Snippet leaks session identifier | Used real values or sensitive fixtures | Use placeholders, preprocessing, and inspect all snippets |
| `response-cookies` only lists name, lacking attributes | Only used cookie descriptors | Include `http-response`/`response-headers` and explain flags |

Never log session or token values, even on test failures or in pipeline output. If token testing is required, use dummy fixtures and publish only the cookie name and necessary attributes.

## 12. Practice exercise

Build an endpoint:

~~~text
POST /api/session
~~~

Contract:

- Server issues the **SESSION** cookie.
- The cookie has **Path=/**, **HttpOnly**, **Secure**, **SameSite=Lax**, and **Max-Age=1800**.
- The response includes a JSON body reporting session creation status.
- Documentation must not expose the session value.

Requirements:

1. Use **ResponseCookie** to create the cookie with all required attributes.
2. Write a MockMvc test verifying cookie existence, `HttpOnly`, `Secure`, `Path`, and `Max-Age`.
3. Assert that the `Set-Cookie` header contains **SameSite=Lax**.
4. Use **responseCookies(cookieWithName("SESSION")...)** to describe the cookie.
5. Use **responseHeaders(headerWithName("Set-Cookie")...)** and include **http-response.adoc** to display the response header.
6. Use a session placeholder in tests; verify snippets contain no real session value.
7. Add browser integration tests over HTTPS if the application needs to prove `Secure`/`SameSite` behavior in browsers.
8. Build Asciidoctor after tests and run the entire flow in CI.

**Completion criteria:** the server emits all three flags accurately; tests verify the attributes; cookie descriptors and response/header snippets are generated; documentation accurately explains MockMvc limitations; no session secrets appear in the output.

## Key Takeaways

**HttpOnly** restricts JavaScript from reading cookies; **Secure** restricts sending cookies over insecure connections; **SameSite** governs sending cookies in cross-site contexts. The three attributes address different concerns and do not replace TLS, XSS prevention, CSRF protection, or authorization. In Spring REST Docs, **responseCookies(...)** describes cookie names and meanings; **http-response.adoc** or **response-headers.adoc** shows the **Set-Cookie** header containing flags. MockMvc can verify response configuration, while browser behavior requires testing over HTTPS and real origins. Combine both test types and snippets in CI so documentation accurately reflects your cookie policy.

**References:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [Spring REST Docs CookieDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/cookies/CookieDocumentation.html), [Spring ResponseCookie API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ResponseCookie.html), [RFC 6265](https://www.rfc-editor.org/rfc/rfc6265), and [RFC 6265bis: Cookies](https://datatracker.ietf.org/doc/draft-ietf-httpbis-rfc6265bis/).
