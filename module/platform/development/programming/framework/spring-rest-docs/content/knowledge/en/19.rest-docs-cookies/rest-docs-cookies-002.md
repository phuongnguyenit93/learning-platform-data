# Document response cookies with responseCookies

## Lesson Objectives

A server can send cookies to a client to store preferences, maintain a session, or support a security flow. In HTTP, the server issues cookies using the **Set-Cookie** header. When documenting responses with **Spring REST Docs**, we need to describe which cookies are created, their purpose, and how the client handles the accompanying attributes.

This lesson belongs to the **Cookies** chapter of the **SPRING_REST_DOCS** module: building verifiable REST API documentation from HTTP tests using **MockMvc**, **WebTestClient**, or **REST Assured**; generating snippets for requests, responses, payloads, parameters, and headers; authoring Asciidoctor/Markdown documentation and integrating it into builds and CI.

After this lesson, you will be able to:

- Use **responseCookies(...)** and **cookieWithName(...)** to describe cookies returned by the server.
- Distinguish the cookie snippet table from the **Set-Cookie** header in the HTTP response.
- Verify cookies, values, and attributes such as **Path**, **HttpOnly**, **Secure**, and **Max-Age**.
- Document new cookies, updated cookies, and deleted cookies.
- Use MockMvc to assert response cookies and generate the **response-cookies.adoc** snippet.
- Keep session IDs, tokens, and sensitive data out of public documentation.
- Include cookie snippets in Asciidoctor and ensure CI regenerates documentation from tests.

## 1. How are response cookies sent by the server?

When creating or updating a cookie, the server sends one or more **Set-Cookie** headers in the response. Example:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Set-Cookie: display-mode=compact; Path=/; Max-Age=3600; Secure; HttpOnly; SameSite=Lax

{"message":"Preferences saved"}
~~~

The **Set-Cookie** header contains a name/value pair and attributes that control how the client stores, sends, and expires the cookie. In the example above:

| Component | Meaning |
| --- | --- |
| **display-mode=compact** | Cookie name and value issued by the server |
| **Path=/** | Cookie applies to requests within the corresponding path scope |
| **Max-Age=3600** | Maximum lifetime of 3,600 seconds from receipt |
| **Secure** | Client sends the cookie only over secure connections according to cookie rules |
| **HttpOnly** | Browser-side JavaScript cannot read the cookie via APIs such as document.cookie |
| **SameSite=Lax** | Policy for sending cookies in certain cross-site contexts |

Response cookies differ from request cookies:

| Direction | HTTP header | Spring REST Docs |
| --- | --- | --- |
| Client → server | **Cookie** | **requestCookies(...)** |
| Server → client | **Set-Cookie** | **responseCookies(...)** |

Cookies are transmitted via headers, but when you need to describe each cookie by name, use the **CookieDocumentation** API. **responseHeaders(...)** remains useful when you want to describe other headers such as **Cache-Control**, **Location**, or **Content-Type**.

## 2. responseCookies(...) and cookieWithName(...)

Spring REST Docs provides an API to declare cookies returned by the server:

~~~java
import static org.springframework.restdocs.cookies.CookieDocumentation.cookieWithName;
import static org.springframework.restdocs.cookies.CookieDocumentation.responseCookies;
~~~

Example:

~~~java
responseCookies(
    cookieWithName("display-mode")
        .description("Display mode saved for subsequent visits")
)
~~~

Roles:

- **cookieWithName("display-mode")** creates a descriptor for the cookie named **display-mode**.
- **description(...)** explains the meaning of the cookie in the API contract.
- **responseCookies(...)** instructs REST Docs to generate a snippet describing the response cookies.

If a response has multiple cookies, pass multiple descriptors:

~~~java
responseCookies(
    cookieWithName("display-mode")
        .description("Saved display mode"),
    cookieWithName("locale")
        .description("Language used for subsequent visits")
)
~~~

The name in the descriptor must match the actual cookie name sent in the response. **responseCookies(...)** does not create a cookie on its own; the controller or filter must add the cookie to the response and the test must actually receive it.

### 2.1. The response-cookies.adoc snippet

When a test calls:

~~~java
document("profile-save",
    responseCookies(
        cookieWithName("display-mode")
            .description("Saved display mode")
    )
)
~~~

REST Docs generates the **response-cookies.adoc** snippet in:

~~~text
build/generated-snippets/
└── profile-save/
    └── response-cookies.adoc
~~~

This is a table of cookie names and descriptions based on the descriptors. **http-response.adoc** is a separate snippet showing the HTTP status, headers, and response body. The two snippets complement each other: one presents the cookie contract, while the other shows the observed HTTP response.

Cookie values and **Set-Cookie** attributes may appear in the default HTTP response snippet. Therefore, before publishing, review both **response-cookies.adoc** and **http-response.adoc**, especially for session cookies.

## 3. Creating cookies in Spring MVC

The example uses **Java 17+**, **Spring Boot 3.x**, Spring MVC, and the servlet API. The endpoint saves a display preference and sends a cookie back to the client:

~~~java
import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
class PreferenceController {

    @PostMapping(
        path = "/api/preferences",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    PreferenceResponse save(
            @RequestBody PreferenceRequest request,
            HttpServletResponse response) {

        Cookie displayMode =
            new Cookie("display-mode", request.displayMode());
        displayMode.setPath("/");
        displayMode.setHttpOnly(true);
        displayMode.setSecure(true);
        displayMode.setMaxAge(3600);
        response.addCookie(displayMode);

        return new PreferenceResponse("saved");
    }
}

record PreferenceRequest(String displayMode) {}
record PreferenceResponse(String status) {}
~~~

A successful response contains a JSON body and a **Set-Cookie** header:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Set-Cookie: display-mode=compact; Path=/; Max-Age=3600; Secure; HttpOnly

{"status":"saved"}
~~~

The example uses **jakarta.servlet.http.Cookie** to demonstrate common servlet attributes. The **SameSite** attribute does not have a standard setter in the basic Servlet Cookie API; if your application needs this attribute, use the cookie/header configuration mechanism appropriate for your Spring version and servlet container, then verify the actual `Set-Cookie` header.

In production, validate the **displayMode** value against an allowlist such as **compact** or **comfortable**. Never place arbitrary client input into a cookie without checking its size and format.

## 4. Testing response cookies with MockMvc

Add the dependency if the project does not already have it:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
~~~

Assuming Spring Boot's BOM/dependency management handles compatible versions. Place the test below in the same package as **PreferenceController**:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.cookies.CookieDocumentation.cookieWithName;
import static org.springframework.restdocs.cookies.CookieDocumentation.responseCookies;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.cookie;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(PreferenceController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class PreferenceCookieDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentDisplayModeResponseCookie() throws Exception {
        mockMvc.perform(post("/api/preferences")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                    {"displayMode":"compact"}
                    """))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("saved"))
            .andExpect(cookie().value("display-mode", "compact"))
            .andExpect(cookie().httpOnly("display-mode", true))
            .andExpect(cookie().secure("display-mode", true))
            .andExpect(cookie().path("display-mode", "/"))
            .andDo(document("preference-save",
                responseCookies(
                    cookieWithName("display-mode")
                        .description("Display mode saved for subsequent visits")
                )
            ));
    }
}
~~~

In the test:

1. **POST /api/preferences** sends JSON requesting to save the preference.
2. The controller calls **response.addCookie(...)** to add the cookie to the response.
3. The **cookie()** matchers verify the value and several key attributes.
4. **responseCookies(...)** documents the cookie in a dedicated snippet.
5. **document("preference-save", ...)** records the operation and generates the associated snippets.

MockMvc cookie matchers are useful for verifying value, path, domain, max-age, secure, httpOnly, and version when supported by the API. For attributes without a dedicated matcher or across container differences, inspect the actual **Set-Cookie** header using **header().string(...)** or extract the response and assert the appropriate attributes.

### 4.1. Snippet output

Expected output directory:

~~~text
build/generated-snippets/
└── preference-save/
    ├── http-request.adoc
    ├── http-response.adoc
    └── response-cookies.adoc
~~~

Default snippets and additional payload snippets depend on your `document` configuration. **response-cookies.adoc** contains a table describing cookie names; **http-response.adoc** shows the observed **Set-Cookie** header and body. Do not edit generated snippets directly because subsequent test runs will regenerate them.

## 5. Documenting multiple response cookies

If a response sets both **display-mode** and **locale**, declare both descriptors:

~~~java
responseCookies(
    cookieWithName("display-mode")
        .description("Saved display mode"),
    cookieWithName("locale")
        .description("Language used for subsequent requests")
)
~~~

The test must produce both cookies. Example:

~~~java
Cookie displayMode = new Cookie("display-mode", "compact");
displayMode.setPath("/");
response.addCookie(displayMode);

Cookie locale = new Cookie("locale", "vi");
locale.setPath("/");
response.addCookie(locale);
~~~

Each cookie can have different attributes. Test the attributes that belong to the contract rather than assuming that text in **description(...)** automatically verifies **Path**, **Secure**, or **HttpOnly**.

### 5.1. Cookies can be optional in a response

An endpoint may issue a cookie only when the user chooses to remember a preference. In that case, responses in some scenarios will not include the cookie. The descriptor can use **optional()** if the cookie does not appear in every documented request/response:

~~~java
responseCookies(
    cookieWithName("display-mode")
        .description("Display mode; created only when the user saves preferences")
        .optional()
)
~~~

**optional()** only states that the cookie may be absent in the operation inspected by REST Docs. It does not make the controller create the cookie or decide when it is issued. Write separate tests for cases with and without the cookie, and clearly document the issuance condition.

## 6. Updating and deleting cookies

### 6.1. Updating a cookie

To update a cookie, the server sends a new **Set-Cookie** header with the same name and scope, but with a new value or updated attributes. Example changing the display mode:

~~~java
Cookie preference = new Cookie("display-mode", "comfortable");
preference.setPath("/");
preference.setHttpOnly(true);
preference.setSecure(true);
preference.setMaxAge(3600);
response.addCookie(preference);
~~~

You can document the new response with the same descriptor:

~~~java
responseCookies(
    cookieWithName("display-mode")
        .description("Current display mode saved by the server")
)
~~~

If the same endpoint can return different cookie values depending on the request, write a test for each behavior you want to publish. The descriptor table documents the cookie; the tests and response snippets show the specific values and attributes in each scenario.

### 6.2. Deleting a cookie

A server typically instructs the client to delete a cookie by resending the corresponding name and scope with an empty value and **Max-Age=0** or a past **Expires** timestamp:

~~~java
Cookie expired = new Cookie("display-mode", "");
expired.setPath("/");
expired.setMaxAge(0);
response.addCookie(expired);
~~~

Cookies are identified by scope, so **Path** and **Domain** must match the original cookie. If the original cookie was set for **Path=/** but the deletion response sends a different scope, the client may keep the old cookie.

A test can verify that the response issues an expired cookie:

~~~java
mockMvc.perform(delete("/api/preferences/display-mode"))
    .andExpect(status().isNoContent())
    .andExpect(cookie().maxAge("display-mode", 0))
    .andDo(document("preference-delete-cookie",
        responseCookies(
            cookieWithName("display-mode")
                .description("Display mode cookie cleared with Max-Age=0")
        )
    ));
~~~

This is an excerpt for a hypothetical DELETE endpoint. You need to import **MockMvcRequestBuilders.delete** and implement the corresponding controller. Even when the cookie-deletion response has no body, you can still document the response cookie and HTTP status.

## 7. Cookie attributes and how to document them

Cookie snippets primarily describe the name and meaning of each cookie. Attributes are usually shown via the **Set-Cookie** header in **http-response.adoc**. When detailed guidance is needed, add prose documentation and tests verifying the actual attribute values.

| Attribute | Meaning | What to verify |
| --- | --- | --- |
| **Path** | Applicable path scope | Does the client send the cookie on the intended endpoints? |
| **Domain** | Applicable host scope | Are the host/subdomains configured properly? |
| **Max-Age** | Lifetime in seconds | Does the cookie expire at the expected time? |
| **Expires** | Expiration timestamp | Does it align with the cookie lifecycle policy? |
| **Secure** | Send only over secure connections | Is production running over HTTPS? |
| **HttpOnly** | Disallows JavaScript access via ordinary APIs | Should script access be restricted? |
| **SameSite** | Sending policy in cross-site contexts | Do login/redirect flows behave as designed? |

**SameSite** commonly takes **Strict**, **Lax**, or **None**. If using **SameSite=None**, the cookie must satisfy the **Secure** requirement enforced by modern browsers. Browser behavior can depend on versions and context; do not rely solely on MockMvc to conclude that cross-site flows work in real browsers.

### 7.1. Servlet Cookie and ResponseCookie

**jakarta.servlet.http.Cookie** is convenient for Spring MVC applications running on Servlets. This API does not provide standard setters for all modern cookie attributes such as `SameSite`.

Spring also provides **org.springframework.http.ResponseCookie** to build cookies as headers:

~~~java
import org.springframework.http.ResponseCookie;

ResponseCookie cookie = ResponseCookie.from("display-mode", "compact")
    .path("/")
    .httpOnly(true)
    .secure(true)
    .sameSite("Lax")
    .maxAge(3600)
    .build();

response.addHeader("Set-Cookie", cookie.toString());
~~~

This snippet illustrates declaring attributes with **ResponseCookie**; check the actual methods and Spring Framework version in your project. Do not simultaneously add a servlet `Cookie` with the same name unless you intend for the response to emit two distinct `Set-Cookie` headers.

## 8. Securing cookie values in documentation

Response cookies may contain a **session ID**, refresh token, or authentication value. Those values must not be included in documentation or committed as real fixtures.

Guidelines:

1. Use dummy cookies in tests, such as **test-session-placeholder**, never production sessions.
2. Inspect both **response-cookies.adoc** and **http-response.adoc** because cookie values can appear in both the table and raw headers.
3. If values must be masked, use appropriate preprocessing or design fixtures without secrets.
4. Do not omit the entire authentication cookie description if clients need to know the cookie-sending mechanism; instead, describe the name, purpose, and attributes without exposing real values.
5. Never write tokens, session IDs, or personal data to test logs or CI output.

Example describing only the session cookie:

~~~java
responseCookies(
    cookieWithName("SESSION")
        .description("Server-managed session cookie; automatically sent back by the client")
)
~~~

Real server-generated values may need to be replaced in the recorded operation before snippet generation. Even after preprocessing, inspect the final snippets to ensure no sensitive data remains.

## 9. Combining responseCookies with headers and response fields

An operation can document cookies, headers, and a JSON body at the same time:

~~~java
document("preference-save",
    responseCookies(
        cookieWithName("display-mode")
            .description("Saved display mode")
    ),
    responseHeaders(
        headerWithName("Cache-Control")
            .description("Response caching policy")
    ),
    responseFields(
        fieldWithPath("status")
            .description("Result of saving preferences")
    )
)
~~~

Static imports:

~~~java
import static org.springframework.restdocs.cookies.CookieDocumentation.cookieWithName;
import static org.springframework.restdocs.cookies.CookieDocumentation.responseCookies;
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
~~~

Do not document **Set-Cookie** with both **responseCookies(...)** and **responseHeaders(...)** as if they were two different cookies. Cookie descriptors document cookie names; the response headers snippet is where observed HTTP headers are shown.

## 10. Including response cookie snippets in Asciidoctor and CI

Once the test generates the **preference-save** snippets, they can be included in **src/docs/asciidoc/index.adoc**:

~~~asciidoc
= Preference API
:toc: left

== Save display mode

POST /api/preferences

=== Response cookies

include::{snippets}/preference-save/response-cookies.adoc[]

=== HTTP response

include::{snippets}/preference-save/http-response.adoc[]
~~~

With Gradle and the **org.asciidoctor.jvm.convert** plugin configured:

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

The `asciidoctor` task depends on `test` so snippets are created before inclusion. In CI, publish documentation only after both REST Docs tests and the documentation build succeed. If a cookie is removed from the response, a descriptor declares the wrong name, or an include points to the wrong snippet ID, the pipeline should catch the failure rather than publishing incomplete documentation.

If the final documentation is Markdown, use a conversion tool or an appropriate snippet-embedding mechanism. **include::{snippets}/...[]** is Asciidoctor syntax, not standard Markdown.

## 11. Common errors

| Symptom | Cause | Fix |
| --- | --- | --- |
| **response-cookies.adoc** is missing | **responseCookies(...)** was not declared or the operation did not generate the descriptor | Add the descriptor to the right **document(...)** call and re-run the test |
| Descriptor reports non-existent cookie | Wrong cookie name or response did not send the cookie | Cross-check the actual **Set-Cookie** header and the name in **cookieWithName(...)** |
| Cookie snippet exists but HTTP response is not as expected | Only the descriptor was declared without creating the cookie in the controller | Call **response.addCookie(...)** or add `Set-Cookie` |
| Cookie value is right but attributes are missing | Path, Secure, HttpOnly, or Max-Age not configured | Set the attributes and assert them in tests |
| Cookie deleted but browser keeps storing it | Path/Domain does not match the old cookie | Send the expired cookie with the exact same scope |
| Session ID appears in documentation | Real response value was recorded in HTTP snippets | Use dummy fixtures or preprocessing and check all outputs |
| Cross-site request does not send cookie | Unsuitable SameSite/Secure or browser policy | Test in a browser and over HTTPS per the contract |
| Two cookies with the same name appear unexpectedly | Added both a Servlet Cookie and a ResponseCookie with the same name | Pick one `Set-Cookie` creation mechanism per cookie |
| Asciidoctor cannot find response cookie snippet | Test has not run or snippet ID is wrong | Check document identifier, output dir, and task dependencies |

## 12. Practice exercise

Build an endpoint that remembers a UI preference:

~~~text
POST /api/preferences
DELETE /api/preferences/display-mode
~~~

Contract:

- POST receives JSON **{"displayMode":"compact"}**.
- POST response returns HTTP 200 and sets the **display-mode** cookie.
- The cookie has **Path=/**, **HttpOnly**, **Secure**, and **Max-Age=3600**.
- DELETE returns HTTP 204 and re-issues the **display-mode** cookie with **Max-Age=0**.

Requirements:

1. Write a controller using **HttpServletResponse.addCookie(...)** or **ResponseCookie**.
2. Write a MockMvc test for POST; assert the status, response body, cookie value, and attributes.
3. Use **responseCookies(cookieWithName("display-mode")...)** to generate the **preference-save/response-cookies.adoc** snippet.
4. Write a DELETE test; assert HTTP 204 and Max-Age=0; generate the **preference-delete-cookie/response-cookies.adoc** snippet.
5. Create an Asciidoctor document with two sections describing the created cookie and the deleted cookie.
6. Verify that **http-response.adoc** contains no real token or session ID.
7. Wire test and Asciidoctor in Gradle/CI, confirming that changing cookie attributes causes tests to fail when the contract is broken.

Sample descriptor:

~~~java
responseCookies(
    cookieWithName("display-mode")
        .description("Display mode saved on the client; expires after one hour")
)
~~~

**Completion criteria:** response cookies are created properly; tests verify name, value, and attributes; expired cookies are tested; snippets are generated and included under the right operations; documentation leaks no secret values.

## Key Takeaways

**responseCookies(...)** is used to document cookies returned by the server, while **cookieWithName(...)** identifies each cookie name and **description(...)** explains its purpose. Create the cookie in the response, verify its value and attributes with MockMvc, and use descriptors to generate **response-cookies.adoc**. For updated or deleted cookies, check both scope and expiration. Session/token values must be mocked or masked before publishing. Finally, include the cookie snippet and HTTP response in Asciidoctor so your build/CI always produces documentation from tested responses.

**References:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [Spring REST Docs CookieDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/cookies/CookieDocumentation.html), [Spring MVC @CookieValue](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/cookievalue.html), [Spring ResponseCookie API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ResponseCookie.html), and [RFC 6265](https://www.rfc-editor.org/rfc/rfc6265).
