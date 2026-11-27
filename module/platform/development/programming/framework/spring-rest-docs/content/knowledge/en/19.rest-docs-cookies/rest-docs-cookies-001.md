# Document request and response cookies

## Lesson Objectives

An HTTP cookie is a small piece of data that a server sends to a client via the **Set-Cookie** header; on subsequent requests, the client can send the cookie back via the **Cookie** header. An API may use cookies to maintain a login session, remember UI preferences, or determine the language. When documenting an API with **Spring REST Docs**, you need to clearly describe which cookies the client must send and which cookies the server may return.

This lesson belongs to the **SPRING_REST_DOCS** module: creating verifiable REST API documentation from HTTP tests using **MockMvc**, **WebTestClient**, or **REST Assured**; generating snippets for requests, responses, payloads, parameters, and headers; authoring Asciidoctor/Markdown documentation and integrating it into builds and CI.

After this lesson, you will be able to:

- Distinguish request cookies from response cookies.
- Use Spring REST Docs' **requestCookies(...)**, **responseCookies(...)**, and **cookieWithName(...)**.
- Send cookies with MockMvc and verify cookies created by the server.
- Generate **request-cookies.adoc** and **response-cookies.adoc** snippets.
- Distinguish cookie descriptors from **Cookie/Set-Cookie** header descriptors.
- Document optional cookies and handle missing cookie cases.
- Protect session IDs, tokens, and sensitive data in test fixtures and documentation.
- Include cookie snippets in Asciidoctor and run the documentation generation workflow in CI.

## 1. How do cookies travel over HTTP?

Cookies have two directions of exchange:

1. The server sends a cookie to the client using the **Set-Cookie** header in the response.
2. The client stores the cookie according to browser or HTTP client rules. On a subsequent matching request, the client sends the cookie name and value in the **Cookie** header.

Example response:

~~~http
HTTP/1.1 200 OK
Set-Cookie: display-mode=compact; Path=/; HttpOnly; Secure; SameSite=Lax
Content-Type: application/json

{"message":"Preferences saved"}
~~~

Subsequent request:

~~~http
GET /api/profile
Cookie: display-mode=compact; locale=vi
Accept: application/json
~~~

| Component | Direction | Role |
| --- | --- | --- |
| **Set-Cookie** | Server → client | Instructs the client to store or update a cookie |
| **Cookie** | Client → server | Sends cookie name/value pairs matching the request |
| **Path** | Set-Cookie attribute | Limits the URL path scope for which the client sends the cookie |
| **Domain** | Set-Cookie attribute | Specifies the host scope according to cookie rules |
| **Max-Age/Expires** | Set-Cookie attribute | Expiration lifetime of the cookie |
| **Secure** | Set-Cookie attribute | Restricts sending the cookie over insecure connections |
| **HttpOnly** | Set-Cookie attribute | Prevents browser-side JavaScript from accessing the cookie via APIs such as document.cookie |
| **SameSite** | Set-Cookie attribute | Controls cookie transmission in cross-site contexts |

**A cookie is neither a path parameter nor a query parameter.** It is transmitted in HTTP headers. Therefore, in Spring REST Docs we use the dedicated cookie descriptor group rather than placing cookies in **pathParameters(...)**, **queryParameters(...)**, or **requestFields(...)**.

## 2. Which API does Spring REST Docs use to describe cookies?

Spring REST Docs provides descriptors for cookies:

~~~java
import static org.springframework.restdocs.cookies.CookieDocumentation.cookieWithName;
import static org.springframework.restdocs.cookies.CookieDocumentation.requestCookies;
import static org.springframework.restdocs.cookies.CookieDocumentation.responseCookies;
~~~

- **cookieWithName("locale")** creates a descriptor for a cookie named `locale`.
- **requestCookies(...)** describes cookies sent by the client in the request.
- **responseCookies(...)** describes cookies sent by the server in the response.
- **description(...)** explains the cookie's purpose so API consumers understand when to send or expect it.

Example:

~~~java
requestCookies(
    cookieWithName("locale")
        .description("Preferred user language, for example vi")
);

responseCookies(
    cookieWithName("display-mode")
        .description("Display mode remembered by the server")
);
~~~

A request or response can have multiple cookies. Each cookie needs its own descriptor whose name matches the actual cookie in the tested operation.

### 2.1. Cookie descriptors and header descriptors are different

Cookies are transmitted via headers, but Spring REST Docs provides separate snippets to present cookies by name:

| Documentation API | Purpose |
| --- | --- |
| **requestHeaders(...)** | Describes headers such as Accept, Authorization, or X-Request-Id |
| **responseHeaders(...)** | Describes headers such as Content-Type, Location, or Cache-Control |
| **requestCookies(...)** | Describes each cookie sent by the client |
| **responseCookies(...)** | Describes each cookie set by the server |

If the goal is to document the **locale** cookie, use **requestCookies(cookieWithName("locale")...)**. If you want to explain the overall **Cookie** header, you can describe that header in a separate headers section when appropriate, but you should not use it as a replacement for the cookies table.

## 3. Creating an example controller

The example uses **Java 17+**, **Spring Boot 3.x**, Spring MVC, and **JUnit 5**. The endpoint reads the **locale** cookie, falls back to a default when the cookie is absent, and sends the **display-mode** cookie back to the client.

~~~java
import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProfileController {

    @GetMapping("/api/profile")
    ProfileResponse getProfile(
            @CookieValue(name = "locale", defaultValue = "vi")
            String locale,
            HttpServletResponse response) {

        Cookie displayMode = new Cookie("display-mode", "compact");
        displayMode.setPath("/");
        displayMode.setHttpOnly(true);
        displayMode.setSecure(true);
        displayMode.setMaxAge(3600);
        response.addCookie(displayMode);

        return new ProfileResponse("Lan", locale);
    }
}

record ProfileResponse(String name, String locale) {}
~~~

Explanation:

- **@CookieValue("locale")** binds the request cookie to the Java method parameter.
- **defaultValue = "vi"** allows the endpoint to use a default language if the `locale` cookie is not sent.
- **response.addCookie(...)** instructs the servlet response to send the `display-mode` cookie.
- **HttpOnly**, **Secure**, **Path**, and **Max-Age** are cookie attributes configured on the response.

This is an illustrative example. In production systems, authentication/session cookies must be managed by your application's security mechanism or Spring Security; you should never generate a session token using a hardcoded string like the UI preference cookie example.

## 4. MockMvc test and generating snippets for request/response cookies

Add the dependency if the project does not already have it:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
~~~

This example assumes Spring Boot's BOM/dependency management handles compatible versions. Create a test in the same package as the controller:

~~~java
import jakarta.servlet.http.Cookie;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.cookies.CookieDocumentation.cookieWithName;
import static org.springframework.restdocs.cookies.CookieDocumentation.requestCookies;
import static org.springframework.restdocs.cookies.CookieDocumentation.responseCookies;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.cookie;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ProfileController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class ProfileCookieDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentProfileRequestAndResponseCookies() throws Exception {
        mockMvc.perform(get("/api/profile")
                .cookie(new Cookie("locale", "vi"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.locale").value("vi"))
            .andExpect(cookie().value("display-mode", "compact"))
            .andDo(document("profile-get",
                requestCookies(
                    cookieWithName("locale")
                        .description("Preferred user language")
                ),
                responseCookies(
                    cookieWithName("display-mode")
                        .description("Display mode remembered by the server")
                )
            ));
    }
}
~~~

In this test:

1. **.cookie(new Cookie("locale", "vi"))** sends the cookie from the client into MockMvc.
2. **requestCookies(...)** describes the `locale` cookie in the request snippet.
3. The controller calls **response.addCookie(...)** to create the `display-mode` cookie.
4. **cookie().value(...)** verifies the cookie value returned by the response.
5. **responseCookies(...)** describes the response cookie in a separate snippet.

The assertions verify both HTTP behavior and cookie contents. A descriptor only documents the contract; it does not create cookies on its own or cause them to appear in the response.

### 4.1. Snippet output

With the **profile-get** identifier, the snippet directory is expected to contain:

~~~text
build/generated-snippets/
└── profile-get/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── request-cookies.adoc
    └── response-cookies.adoc
~~~

REST Docs generates cookie snippets when an operation includes **requestCookies(...)** and **responseCookies(...)** descriptors. Other default request/response snippets are generated according to your integration configuration.

The documentation table displays the declared cookie names and descriptions. Actual cookie values sent or received may still appear in the default request/response snippets; carefully review the output before publishing if the values are confidential.

## 5. Optional cookies and missing cookie cases

A cookie can be optional under the contract. For example, if **locale** is not sent, the application defaults to **vi**. A test for that case:

~~~java
@Test
void profileUsesDefaultLocaleWhenCookieIsMissing() throws Exception {
    mockMvc.perform(get("/api/profile")
            .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.locale").value("vi"));
}
~~~

If you want to document a non-mandatory cookie, you can mark the descriptor as optional:

~~~java
requestCookies(
    cookieWithName("locale")
        .description("User language; defaults to vi if omitted")
        .optional()
)
~~~

Calling **optional()** on a cookie descriptor indicates that the cookie may be absent in the documented request. It does not configure a default value for the controller; the default value comes from **@CookieValue(defaultValue = "vi")** or application logic. You should have a test verifying the behavior when the cookie is missing.

For a required cookie, do not mark it optional:

~~~java
@CookieValue(name = "session-id") String sessionId
~~~

If a request omits a required cookie, Spring MVC may return a binding error depending on the application's exception handling mechanism. Verify the status code and error structure in tests rather than assuming all missing-cookie cases produce the same response.

## 6. Response cookies: expiration, deletion, and security attributes

The server can send a new cookie, update an existing cookie, or delete a cookie. The client receives a new **Set-Cookie** header and processes it according to its attributes.

### 6.1. Setting a cookie

~~~java
Cookie preference = new Cookie("display-mode", "compact");
preference.setPath("/");
preference.setHttpOnly(true);
preference.setSecure(true);
preference.setMaxAge(3600);
response.addCookie(preference);
~~~

Attributes commonly worth considering:

| Attribute | Meaning |
| --- | --- |
| **HttpOnly** | The cookie cannot be accessed by ordinary JavaScript in the browser |
| **Secure** | The cookie is only sent over secure channels according to client rules |
| **SameSite** | Controls cookie sending in cross-site contexts |
| **Path** | Path scope to which the cookie applies |
| **Domain** | Host scope to which the cookie applies |
| **Max-Age** | Lifetime duration in seconds |
| **Expires** | Timestamp when the cookie expires |

Servlet APIs and Spring versions may differ in how they support newer attributes such as **SameSite**. Inspect the actual generated **Set-Cookie** header and use the configuration approach appropriate for your framework/container version.

### 6.2. Deleting a cookie

To instruct the client to delete a cookie, the server typically resends the same cookie name and scope with an empty value and an expiration time in the past or **Max-Age=0**. Servlet example:

~~~java
Cookie expired = new Cookie("display-mode", "");
expired.setPath("/");
expired.setMaxAge(0);
response.addCookie(expired);
~~~

The **Path** and **Domain** scope must match the previously created cookie so the client deletes the right cookie. If you delete with the same name but a different scope, the client may retain the old cookie.

You can document a deleted response cookie using **responseCookies(...)** if the contract requires clients to observe the deletion. At the same time, inspect **Set-Cookie** in the response to verify the expiration attributes. Do not rely solely on the cookie name in the snippet while overlooking actual behavior.

### 6.3. Session cookies and preference cookies

| Type | Examples | Notes |
| --- | --- | --- |
| Session/authentication | **JSESSIONID**, application session cookies | Secret values; never put real values into documentation |
| CSRF | CSRF token cookie | Describe its relationship with the returned header/token if required by the application |
| Preference | **locale**, **display-mode** | Usually non-sensitive, though dummy test data should still be used |
| Tracking/analytics | Behavioral analytics cookies | Document only when part of the API contract and compliant with privacy requirements |

For a session cookie, you can write a descriptor like:

~~~java
responseCookies(
    cookieWithName("JSESSIONID")
        .description("Server-managed session cookie; automatically sent back by the client")
)
~~~

However, **do not include real session values** in examples or snippets. Use dummy test sessions, a replacement preprocessor, or omit the values from recordings if unnecessary.

## 7. Combining cookie snippets with header and body snippets

An operation may need to describe cookies, headers, and payloads together. Example:

~~~java
document("profile-get",
    requestHeaders(
        headerWithName("Accept")
            .description("Response content type accepted by the client")
    ),
    requestCookies(
        cookieWithName("locale")
            .description("Preferred user language")
    ),
    responseCookies(
        cookieWithName("display-mode")
            .description("Display mode remembered by the server")
    ),
    responseFields(
        fieldWithPath("name").description("User name"),
        fieldWithPath("locale").description("Applied language")
    )
)
~~~

Descriptor APIs to import:

~~~java
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.restdocs.cookies.CookieDocumentation.cookieWithName;
import static org.springframework.restdocs.cookies.CookieDocumentation.requestCookies;
import static org.springframework.restdocs.cookies.CookieDocumentation.responseCookies;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
~~~

Place each descriptor in its proper group:

- **requestHeaders(...)** for the `Accept` header.
- **requestCookies(...)** for the `locale` cookie.
- **responseCookies(...)** for the `display-mode` cookie.
- **responseFields(...)** for the JSON response data.

Avoid repeating the same information across multiple snippets if it makes the documentation harder to follow. When you need to explain the overall session mechanism, you can have a dedicated authentication/session section instead of turning every cookie into per-operation details.

## 8. Protecting cookies and sensitive data in documentation

Cookies often contain session identifiers or tokens. Therefore, cookie documentation requires controlling test data:

1. Use dummy values; never use real session IDs, tokens, or account cookies.
2. Never commit cookie jar files or credentials to the repository.
3. Review **http-request.adoc**, **http-response.adoc**, **request-cookies.adoc**, and **response-cookies.adoc** before publishing.
4. If sensitive values appear in default snippets, consider using a preprocessor to replace or remove them.
5. Keep the contract description covering cookie names, roles, attributes, and client usage; masking values does not mean removing all cookie documentation.

Example using a preprocessor to remove the `Cookie` or `Set-Cookie` header from default snippets:

~~~java
document("session-check",
    preprocessRequest(removeHeaders("Cookie")),
    preprocessResponse(removeHeaders("Set-Cookie")),
    requestCookies(
        cookieWithName("JSESSIONID")
            .description("Server-managed session cookie")
    )
)
~~~

This controls raw header snippets; verify how preprocessors interact with cookie snippets in the Spring REST Docs version you are using. If a cookie snippet also contains values that should be hidden, inspect the output and choose an appropriate replacement strategy. Do not assume that removing a header automatically guarantees no other snippet contains the same data.

## 9. Documenting cookies in Asciidoctor

Once the test generates the **profile-get** snippets, the documentation can include them:

~~~asciidoc
= Profile API
:toc: left

== Get user profile

GET /api/profile

=== Request cookies

include::{snippets}/profile-get/request-cookies.adoc[]

=== Response cookies

include::{snippets}/profile-get/response-cookies.adoc[]

=== HTTP request

include::{snippets}/profile-get/http-request.adoc[]

=== HTTP response

include::{snippets}/profile-get/http-response.adoc[]
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

The `asciidoctor` task depends on `test` so snippets are generated before being included. In CI, publish documentation only when both REST Docs tests and the documentation build step succeed. If a descriptor declares a cookie that is absent from the operation or omits a cookie that must be documented, REST Docs validation can fail the test depending on your descriptor configuration.

If the final documentation is published in Markdown, you will need a conversion tool or a corresponding mechanism to embed snippets. The **include::{snippets}/...[]** directive is Asciidoctor syntax, not standard Markdown.

## 10. Common errors

| Symptom | Cause | Fix |
| --- | --- | --- |
| **request-cookies.adoc** is not generated | **requestCookies(...)** was not declared or the request lacks the corresponding cookie | Send the cookie in MockMvc and add a descriptor with the exact name |
| **response-cookies.adoc** is not generated | Controller/response did not set the cookie or **responseCookies(...)** is missing | Call **response.addCookie(...)**, assert Set-Cookie, and declare the descriptor |
| Descriptor reports non-existent cookie | Misspelled name, wrong casing, or the cookie is absent from the operation | Cross-check the actual name in the request/response |
| Optional cookie fails when absent | Descriptor is not marked optional or controller lacks a default value | Align the contract, `optional()`, and handling logic |
| Documentation exposes session ID/token | Request/response snippets recorded real values | Use dummy fixtures, mask, or remove values from snippets |
| Cookie deleted but client still sends it | Wrong Path/Domain or missing appropriate Max-Age=0/Expires | Send Set-Cookie with the same scope and inspect response headers |
| Cookie not sent by browser | Unsuitable Secure, SameSite, Domain, Path, or cross-site policy | Test in the corresponding client/browser environment |
| Only Set-Cookie header appears without a cookie table | Only `responseHeaders` was documented | Use **responseCookies(...)** for cookies |
| Asciidoctor reports missing cookie snippet | Test has not generated the snippet or wrong identifier in include | Check document ID, output directory, and test → asciidoctor ordering |

## 11. Practice exercise

UI preference management API:

~~~text
GET /api/settings
POST /api/settings
~~~

Contract:

- The GET request may send the **locale** cookie; if absent, the server uses **vi**.
- The GET response sets the **display-mode** cookie with the dummy value **compact**.
- POST receives a JSON body containing **displayMode**, then updates the **display-mode** cookie.
- Preference cookies contain no authentication information.

Requirements:

1. Write a controller with **@CookieValue** to read **locale** and **HttpServletResponse.addCookie(...)** to return **display-mode**.
2. Write a MockMvc test with the `locale` cookie; assert the JSON response and response cookie.
3. Use **requestCookies(cookieWithName("locale")...)** and **responseCookies(cookieWithName("display-mode")...)** to generate both snippets.
4. Write a test without sending `locale` and verify the default **vi**; mark the descriptor optional in the appropriate documentation test.
5. Write a POST test with a JSON body and response cookie, combining **requestFields(...)** if payload documentation is needed.
6. Include cookie snippets and HTTP snippets in Asciidoctor; verify that CI generates all required files.
7. Try replacing the preference cookie with a dummy session cookie; ensure secret values do not appear in the documentation.

Sample descriptors:

~~~java
requestCookies(
    cookieWithName("locale")
        .description("User language; defaults to vi if omitted")
        .optional()
),
responseCookies(
    cookieWithName("display-mode")
        .description("Display mode saved for subsequent visits")
)
~~~

**Completion criteria:** tests verify both request cookies and response cookies; snippets record the exact names and descriptions; missing-cookie cases are handled according to the contract; documentation does not leak sensitive data and builds successfully from snippets.

## Key Takeaways

**requestCookies(...)** describes cookies sent by the client, while **responseCookies(...)** describes cookies set by the server. Use **cookieWithName(...)** to create descriptors and **description(...)** to explain their purpose; pair them with MockMvc assertions to confirm that cookies are actually sent and received. Optional cookies should be documented with **optional()** when appropriate and accompanied by tests for missing-cookie cases. For session IDs or tokens, always use dummy data and inspect all snippets before publishing. Finally, include **request-cookies.adoc** and **response-cookies.adoc** in Asciidoctor and wire the test task into your build/CI so the documentation accurately reflects the API's cookie contract.

**References:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [Spring REST Docs CookieDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/cookies/CookieDocumentation.html), [Spring MVC @CookieValue](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/cookievalue.html), and [RFC 6265: HTTP State Management Mechanism](https://www.rfc-editor.org/rfc/rfc6265).
