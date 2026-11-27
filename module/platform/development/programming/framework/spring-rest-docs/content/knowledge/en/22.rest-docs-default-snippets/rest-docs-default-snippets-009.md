# request-cookies and response-cookies

## Learning Objectives

In the **SPRING_REST_DOCS** module, cookies are commonly used to maintain login sessions, store state, or pass an identifier between client and server. An API can read cookies from requests or create/update cookies in responses. API documentation needs to explain which cookies the client must send, which cookies the server returns, and what each cookie means.

Spring REST Docs provides two default snippets:

- **request-cookies**: documents cookies appearing in the HTTP request.
- **response-cookies**: documents cookies appearing in the HTTP response.

These snippets are generated from cookie descriptors in tests. REST Docs compares descriptors against observed cookies, helping detect new cookies, omitted cookies, or changed cookie names.

After this lesson, you will be able to:

- Distinguish request-side cookies from response-side cookies.
- Use requestCookies, responseCookies, and cookieWithName.
- Generate and include request-cookies.adoc and response-cookies.adoc.
- Use optional, ignored, and relaxedRequestCookies/relaxedResponseCookies.
- Test cookies with MockMvc and WebTestClient.
- Understand the relationship between the Cookie header, Set-Cookie, and security attributes.
- Avoid confusing documenting cookies with testing the entire cookie security policy.

## 1. Cookies in HTTP Requests and Responses

Cookies are exchanged in two directions:

**Request:** the client sends cookies to the server via the Cookie header. Example:

```http
GET /profile HTTP/1.1
Host: api.example.test
Cookie: JSESSIONID=abc123; theme=dark
```

**Response:** the server sends cookies back to the client via the Set-Cookie header. Example:

```http
HTTP/1.1 200 OK
Set-Cookie: JSESSIONID=xyz789; Path=/; HttpOnly; Secure; SameSite=Lax
Set-Cookie: logged_in=true; Path=/; Secure; SameSite=Lax
```

| Side | HTTP Header | Meaning |
| --- | --- | --- |
| Request | Cookie | Cookie name/value pairs sent by the client |
| Response | Set-Cookie | Server directive to create, update, or delete a cookie on the client |

A cookie created by the server in a response typically only appears in the next request when the client stores and sends it back according to domain, path, expiry, Secure, SameSite, and the client's cookie policy. Therefore, request and response cookies must be documented per HTTP exchange.

## 2. Spring REST Docs Cookie Documentation API

The APIs reside in the package:

```java
org.springframework.restdocs.cookies.CookieDocumentation
```

Main methods:

| API | Function |
| --- | --- |
| cookieWithName("...") | Creates a descriptor for the cookie with the specified name |
| requestCookies(...) | Generates a snippet documenting request cookies |
| responseCookies(...) | Generates a snippet documenting response cookies |
| relaxedRequestCookies(...) | Documents a subset of request cookies, ignoring other undeclared cookies |
| relaxedResponseCookies(...) | Documents a subset of response cookies, ignoring other undeclared cookies |

Two default snippets:

```text
build/generated-snippets/
└── profile/
    ├── request-cookies.adoc
    └── response-cookies.adoc
```

Filenames do not contain the cookie name. Each snippet contains a summary table of documented cookies for that operation.

## 3. requestCookies — Documenting Client-Sent Cookies

### 3.1. MockMvc Example

Suppose the GET /profile endpoint requires a session cookie:

```java
import jakarta.servlet.http.Cookie;

import static org.springframework.restdocs.cookies.CookieDocumentation.cookieWithName;
import static org.springframework.restdocs.cookies.CookieDocumentation.requestCookies;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;

this.mockMvc.perform(get("/profile")
        .cookie(new Cookie("JSESSIONID", "abc123")))
    .andExpect(status().isOk())
    .andDo(document("profile",
        requestCookies(
            cookieWithName("JSESSIONID")
                .description("Session identification cookie.")
        )));
```

requestCookies generates the request-cookies.adoc snippet. The cookieWithName descriptor specifies the cookie name and description explains its role.

In Spring Boot 3/4 examples, the servlet API uses the jakarta.servlet namespace. For older Spring projects using javax.servlet, import Cookie from the namespace used by the application.

### 3.2. Multiple Cookies in a Request

```java
this.mockMvc.perform(get("/profile")
        .cookie(
            new Cookie("JSESSIONID", "abc123"),
            new Cookie("locale", "vi-VN")
        ))
    .andExpect(status().isOk())
    .andDo(document("profile",
        requestCookies(
            cookieWithName("JSESSIONID")
                .description("Session identification cookie."),
            cookieWithName("locale")
                .description("User's preferred language.")
        )));
```

The name in cookieWithName must match the actual name in the request. REST Docs does not infer that sessionId, JSESSIONID, and SESSION are the same cookie.

### 3.3. Using relaxedRequestCookies

If the request contains some cookies outside the operation's documentation scope:

```java
relaxedRequestCookies(
    cookieWithName("JSESSIONID")
        .description("Session identification cookie.")
)
```

Relaxed mode allows other undeclared cookies to appear in the request without failing the test. Declared cookies must still be present, unless marked optional.

## 4. responseCookies — Documenting Server-Returned Cookies

### 4.1. MockMvc Example

Suppose an authentication endpoint creates session cookies:

```java
import static org.springframework.restdocs.cookies.CookieDocumentation.responseCookies;

this.mockMvc.perform(post("/login")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
                {
                  "username": "an",
                  "password": "test-password"
                }
                """))
    .andExpect(status().isOk())
    .andDo(document("login",
        responseCookies(
            cookieWithName("JSESSIONID")
                .description("Server-issued session identification cookie."),
            cookieWithName("logged_in")
                .description("Indicates whether the client is logged in.")
        )));
```

The response-cookies.adoc snippet documents cookies in the response. The JSESSIONID cookie may be updated by the server when a session is created or changed.

### 4.2. Creating Cookies in Test Responses

With MockMvc, response cookies can be created from the controller:

```java
ResponseCookie sessionCookie = ResponseCookie.from("SESSION", "session-value")
        .httpOnly(true)
        .secure(true)
        .sameSite("Lax")
        .path("/")
        .build();

return ResponseEntity.ok()
        .header(HttpHeaders.SET_COOKIE, sessionCookie.toString())
        .body(profile);
```

REST Docs reads cookies sent in the exchange's response. In tests, also assert the Set-Cookie header or corresponding cookie to verify the endpoint actually creates cookies per contract.

### 4.3. Deleting Cookies

Servers typically delete cookies by sending Set-Cookie with the same name, an empty value, and an expiration in the past or Max-Age=0:

```http
Set-Cookie: SESSION=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax
```

At the protocol level, this is still a Set-Cookie in the response. Documentation should explain the cookie deletion behavior rather than merely calling it a newly created cookie.

## 5. Strict, Optional, and Ignored Behavior

### 5.1. Default Strict Mode

requestCookies and responseCookies check correspondence between actual cookies and descriptors:

- A cookie appearing in the exchange without a descriptor can fail the test.
- A documented cookie absent from the exchange also fails the test unless marked optional.

This allows documentation tests to detect when an API starts sending a new cookie or stops sending a published cookie.

### 5.2. Optional Cookies

A cookie may appear in some responses but not others:

```java
responseCookies(
    cookieWithName("SESSION")
        .description("Login session cookie."),
    cookieWithName("remember_me")
        .optional()
        .description("Persistent login cookie; only present when the user chooses remember me.")
)
```

optional allows a documented cookie to be absent from the current exchange. It is useful for cookies depending on login state, user preferences, or processing branches.

### 5.3. Ignored Cookies

If a cookie is present in the exchange but does not need to appear in the snippet table:

```java
requestCookies(
    cookieWithName("SESSION")
        .description("Session cookie."),
    cookieWithName("tracking_id")
        .ignored()
)
```

ignored handles the cookie so validation does not fail for an undocumented cookie, while excluding it from the snippet table. Do not use ignored to hide important security cookies that clients need to understand.

### 5.4. relaxedResponseCookies

If you only want to document part of the response cookies:

```java
relaxedResponseCookies(
    cookieWithName("SESSION")
        .description("Login session cookie.")
)
```

Other undeclared cookies are ignored. Declared cookies that do not appear still require optional if they may be absent.

| Declaration | Undocumented Cookie | Documented Cookie Absent |
| --- | --- | --- |
| requestCookies/responseCookies | Fails the test | Fails the test, unless optional |
| relaxedRequestCookies/relaxedResponseCookies | Ignored | Fails the test, unless optional |
| ignored() | Handles specified cookie without displaying | Does not make cookie optional |
| optional() | Does not affect other cookies | Allows documented cookie to be absent |

## 6. WebTestClient Example

WebTestClient can send cookies in a request using the cookie method:

```java
import static org.springframework.restdocs.cookies.CookieDocumentation.cookieWithName;
import static org.springframework.restdocs.cookies.CookieDocumentation.requestCookies;
import static org.springframework.restdocs.cookies.CookieDocumentation.responseCookies;
import static org.springframework.restdocs.webtestclient.WebTestClientRestDocumentation.document;

this.webTestClient.get()
    .uri("/people")
    .cookie("JSESSIONID", "abc123")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .consumeWith(document("people",
        requestCookies(
            cookieWithName("JSESSIONID")
                .description("Session identification cookie.")
        ),
        responseCookies(
            cookieWithName("logged_in")
                .description("Indicates whether the user is logged in.")
        )));
```

In the response, the application can return Set-Cookie via response headers. REST Docs records response cookies to generate response-cookies.adoc. Verify the test's request/response has the right cookies before relying on the snippet.

## 7. Cookie Name, Value, and Security Attributes

REST Docs cookie snippets focus on **cookie names and descriptions**. They do not replace cookie policy documentation and do not guarantee that security flags are enabled.

Important attributes:

| Attribute | Meaning | What to Explain in Documentation |
| --- | --- | --- |
| Secure | Browser sends cookie only over a secure channel per cookie rules | Cookie is only used over HTTPS in appropriate production environments |
| HttpOnly | Client-side JavaScript cannot read the cookie via standard cookie APIs | Reduces script access to cookies; does not replace XSS mitigations |
| SameSite | Controls sending cookies in cross-site contexts | Choosing Strict, Lax, or None based on navigation and auth flows |
| Domain | Host scope allowed to receive the cookie | Which hosts/domains the cookie applies to |
| Path | Request path scope to which the cookie is sent | Which paths the cookie applies to |
| Max-Age/Expires | Cookie storage lifetime | Session cookie or persistent cookie; when it expires |

Set-Cookie example:

```http
Set-Cookie: SESSION=opaque-value; Path=/; Max-Age=1800; Secure; HttpOnly; SameSite=Lax
```

REST Docs response-cookies lists SESSION and describes its purpose. If readers need to know Secure, HttpOnly, SameSite, Path, or Max-Age, describe those policies in prose or document the Set-Cookie header separately. Do not assume the default cookie table includes columns for all these attributes.

### 7.1. Do Not Record Secret Values in Documentation

Session cookies, refresh tokens, or authentication codes are typically sensitive data. Tests should use dummy values rather than taking real cookies from accounts or production environments. In descriptions, state the purpose and how clients use the cookie rather than publishing values.

## 8. Cookies and Login Session Security

Cookies may carry session IDs or tokens; therefore, documentation content must be accurate:

- Session cookies are typically issued by the server and automatically sent by the client on subsequent requests.
- Do not describe a session cookie as an access token in an Authorization header if the auth mechanism does not use bearer tokens.
- Secure, HttpOnly, and SameSite serve different roles; do not collapse all of them into a single "secure cookie" claim.
- Cookies can be deleted or rotated after logout, session expiration, or login state changes.
- Cookie scope is affected by domain/path and browser policies.

REST Docs tests can prove an exchange sent/returned a cookie with a specific name. To prove security attributes, separate assertions on Set-Cookie or corresponding application configuration and tests are needed.

Header check example:

```java
MvcResult result = this.mockMvc.perform(post("/login")
        .contentType(MediaType.APPLICATION_JSON)
        .content(loginJson))
    .andExpect(status().isOk())
    .andReturn();

String setCookie = result.getResponse().getHeader(HttpHeaders.SET_COOKIE);

assertThat(setCookie)
        .contains("HttpOnly")
        .contains("Secure")
        .contains("SameSite=Lax");
```

This is an illustrative assertion. In a real project, inspecting cookies via the servlet API or an appropriate parser can also be more robust than matching raw header strings verbatim.

## 9. Including Cookie Snippets in AsciiDoc

After running tests, both snippets can be included:

```asciidoc
== Request cookies
include::{snippets}/profile/request-cookies.adoc[]

== Response cookies
include::{snippets}/profile/response-cookies.adoc[]
```

If an operation only has request cookies or only has response cookies, include only the corresponding snippet. Do not include files not generated by tests.

An example directory structure:

```text
build/generated-snippets/
└── profile/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── request-cookies.adoc
    └── response-cookies.adoc
```

request-cookies and response-cookies are supplementary snippets to general HTTP request/response; they do not replace http-request or http-response.

## 10. Common Errors

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Test reports undocumented request cookie | Request has a new cookie without a descriptor | Add cookieWithName or use relaxedRequestCookies intentionally |
| Test reports descriptor did not find cookie | Wrong name or request did not send cookie | Check Cookie header, test setup, and descriptor name |
| response-cookies.adoc not generated | responseCookies not declared or response lacks corresponding cookie | Add snippet and verify Set-Cookie |
| Documented cookie missing in one branch | Cookie only present in certain states | Mark optional if contract allows absence |
| Internal cookie fails test | Strict mode detected undeclared cookie | Document, ignore, or relax with a clear rationale |
| Cookie table does not show Secure/HttpOnly | Default cookie snippet focuses on name/description | Assert Set-Cookie and explain attributes separately |
| Test using javax.servlet.Cookie fails to compile | Project uses Jakarta Servlet | Switch to jakarta.servlet.http.Cookie per Spring generation |
| Cookie returned yet browser does not send it back | Domain, Path, Secure, SameSite, expiry, or client policy | Inspect Set-Cookie and client cookie-sending conditions |
| Docs contain real session values | Test data taken from real environment | Use dummy values, replace tokens, and inspect artifacts |

## 11. Hands-on Exercise

1. Create a GET /profile endpoint accepting the JSESSIONID cookie.
2. Write a MockMvc test sending the cookie and use requestCookies to document the session cookie.
3. Create a POST /login endpoint returning a SESSION or JSESSIONID cookie.
4. Use responseCookies to document the server-issued cookie.
5. Verify Secure, HttpOnly, SameSite, Path, and Max-Age with separate assertions on Set-Cookie.
6. Mark remember_me as optional when the cookie is only created if the client selects remember me.
7. Add an extra undocumented cookie; observe strict mode failing and try relaxedRequestCookies.
8. Include request-cookies.adoc and response-cookies.adoc in AsciiDoc documentation.

**Self-assessment questions**

1. Which two sides of an HTTP exchange do requestCookies and responseCookies describe?
2. How does the Cookie header differ from Set-Cookie?
3. What is cookieWithName used for?
4. How does default requestCookies handle undocumented cookies?
5. How does optional differ from ignored?
6. Which validation rule does relaxedResponseCookies change?
7. Why does a cookie snippet table not replace Secure/HttpOnly/SameSite documentation?
8. How can you test cookie security attributes without putting secret values into documentation?

## Official References

- [Spring REST Docs — HTTP Cookies](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/http-cookies.html): requestCookies, responseCookies, cookieWithName, and relaxed mode.
- [CookieDocumentation API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/cookies/CookieDocumentation.html): methods for generating cookie snippets.
- [CookieDescriptor API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/cookies/CookieDescriptor.html): description, optional, and ignored for cookie descriptors.
- [MDN — Set-Cookie HTTP Header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie): cookie attributes and browser handling.
- [RFC 6265 — HTTP State Management Mechanism](https://www.rfc-editor.org/rfc/rfc6265): HTTP cookie mechanism.

**Practical conclusion:** Use requestCookies to document cookies sent by the client and responseCookies to document cookies issued or updated by the server. Use cookieWithName for each cookie, optional for cookies that may be absent, and ignored or relaxed when clearly justified. Document Secure, HttpOnly, SameSite, and expiration with separate explanations or Set-Cookie assertions, and only use dummy cookie values in tests and artifacts.
