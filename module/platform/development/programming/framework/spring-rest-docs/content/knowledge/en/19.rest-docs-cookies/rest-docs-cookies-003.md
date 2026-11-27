# cookieWithName and cookie descriptions

## Lesson Objectives

When documenting cookies with **Spring REST Docs**, the cookie name helps clients identify the data to send or receive, while the description explains its purpose and usage. The **cookieWithName(...)** descriptor is the starting point for declaring each cookie; it is placed inside **requestCookies(...)** or **responseCookies(...)** depending on the direction of travel.

This lesson belongs to the **Cookies** chapter of the **SPRING_REST_DOCS** module: creating verifiable REST API documentation from HTTP tests using **MockMvc**, **WebTestClient**, or **REST Assured**; generating snippets for requests, responses, payloads, parameters, and headers; authoring Asciidoctor/Markdown documentation and integrating it into builds and CI.

After this lesson, you will be able to:

- Declare descriptors using **cookieWithName("...")**.
- Write **description(...)** entries that clearly explain a cookie's meaning, timing, and intended use.
- Place descriptors in the appropriate **requestCookies(...)** or **responseCookies(...)** group.
- Document multiple cookies, optional cookies, and cookies intentionally excluded from tables.
- Distinguish descriptors from cookie values, **Set-Cookie** attributes, and the **Cookie** header.
- Combine cookie descriptors with header/payload descriptors in a single operation.
- Inspect snippets, avoid exposing sensitive values, and include documentation in Asciidoctor/CI.

## 1. What is cookieWithName(...)?

**cookieWithName(name)** creates a descriptor for a cookie named **name**. This descriptor is passed to a grouping function:

- **requestCookies(...)**: describes cookies sent by the client in an HTTP request.
- **responseCookies(...)**: describes cookies set by the server in an HTTP response.

Example:

~~~java
import static org.springframework.restdocs.cookies.CookieDocumentation.cookieWithName;
import static org.springframework.restdocs.cookies.CookieDocumentation.requestCookies;
import static org.springframework.restdocs.cookies.CookieDocumentation.responseCookies;

requestCookies(
    cookieWithName("locale")
        .description("Preferred user language")
);

responseCookies(
    cookieWithName("display-mode")
        .description("Display mode saved for subsequent visits")
);
~~~

In this example:

| Component | Role |
| --- | --- |
| **cookieWithName("locale")** | Selects the cookie named **locale** |
| **description(...)** | Explains the cookie's purpose to documentation readers |
| **requestCookies(...)** | Declares request cookies |
| **cookieWithName("display-mode")** | Selects the cookie named **display-mode** |
| **responseCookies(...)** | Declares response cookies |

Descriptors do not create cookies and do not modify the application. A cookie must actually appear in the test's request or response for REST Docs to match it and generate the corresponding snippet.

## 2. Distinguishing cookie names, values, and attributes

Consider a response:

~~~http
HTTP/1.1 200 OK
Set-Cookie: display-mode=compact; Path=/; Max-Age=3600; HttpOnly; Secure; SameSite=Lax
Content-Type: application/json

{"status":"saved"}
~~~

Here:

- **display-mode** is the cookie name.
- **compact** is the cookie value.
- **Path**, **Max-Age**, **HttpOnly**, **Secure**, and **SameSite** are cookie attributes in **Set-Cookie**.
- **status** is a JSON response field, not a cookie.

Therefore, the descriptor is normally:

~~~java
responseCookies(
    cookieWithName("display-mode")
        .description("Display mode saved by the server")
)
~~~

Do not pass a value into **cookieWithName(...)**:

| Usage | Right/wrong | Reason |
| --- | --- | --- |
| **cookieWithName("display-mode")** | Right | This is the cookie name |
| **cookieWithName("compact")** | Wrong in this example | This is the value, not the name |
| **cookieWithName("Path")** | Wrong in this example | This is a Set-Cookie attribute |
| **cookieWithName("status")** | Wrong in this example | This is a JSON field |

Request cookies look like **Cookie: locale=vi**; response cookies look like **Set-Cookie: display-mode=compact; ...**. A descriptor selects only the cookie name, not the entire raw header.

## 3. Writing helpful descriptions for API callers

A good description answers the questions API integrators typically have:

1. What is the cookie used for?
2. On which request does the client send the cookie, or in what situation does the server create it?
3. Does the value have a specific format or set of allowed values?
4. Is the cookie optional or can it be absent?
5. Are there important attributes or security notes to keep in mind?

Examples:

| Generic description | More helpful description |
| --- | --- |
| “Language” | “Preferred user language code, for example vi or en” |
| “Theme” | “Saved UI theme; accepts light or dark” |
| “Session” | “Server-managed session cookie; sent back by the client on requests within the cookie scope” |
| “Preference cookie” | “UI display mode compact or comfortable chosen by the user” |

Keep descriptions concise yet clear. If there are many rules such as expiration, `SameSite` policy, or authentication flows, present them in a separate prose section or a header/cookie attributes table; avoid turning `description` into a hard-to-read paragraph.

### 3.1. Writing from the client's perspective

For request cookies:

~~~java
requestCookies(
    cookieWithName("locale")
        .description("Language code the client wants for returned content; for example vi or en")
)
~~~

The description tells the client what to send and why.

For response cookies:

~~~java
responseCookies(
    cookieWithName("display-mode")
        .description("UI display mode saved by the server after the client updates preferences")
)
~~~

The description tells the client when the server returns the cookie and how the client can use it.

Avoid writing descriptions from an internal implementation viewpoint such as “set in the updatePreference() method”. API documentation should prioritize observable behavior and the contract that clients need to understand.

## 4. Declaring multiple cookies in a single operation

A request can send multiple cookies:

~~~http
GET /api/profile
Cookie: locale=vi; display-mode=compact
Accept: application/json
~~~

Describe them using multiple descriptors inside the same **requestCookies(...)**:

~~~java
requestCookies(
    cookieWithName("locale")
        .description("Preferred client language code, for example vi"),
    cookieWithName("display-mode")
        .description("UI mode saved by the client, for example compact")
)
~~~

A response can also issue multiple cookies:

~~~java
responseCookies(
    cookieWithName("display-mode")
        .description("Saved display mode"),
    cookieWithName("locale")
        .description("Remembered preferred language")
)
~~~

Each descriptor must use the exact cookie name that the operation actually sends or receives. Cookie names are case-sensitive depending on implementation and cookie rules; keep the casing consistent across controllers, tests, and documentation.

Do not create multiple descriptors with the same name to represent multiple values of one cookie. If a cookie's value changes across scenarios, define one descriptor for that name and write separate tests for each meaningful case.

## 5. Request cookies and response cookies are two independent groups

An operation can both receive cookies and return cookies. For example, the server reads **locale** and issues **display-mode**:

~~~java
document("profile-get",
    requestCookies(
        cookieWithName("locale")
            .description("Preferred client language code")
    ),
    responseCookies(
        cookieWithName("display-mode")
            .description("UI mode remembered by the server")
    )
)
~~~

This produces two snippets:

~~~text
build/generated-snippets/profile-get/
├── request-cookies.adoc
└── response-cookies.adoc
~~~

The two tables represent two separate directions of travel. Do not use **responseCookies(...)** for cookies sent by the client, or **requestCookies(...)** for cookies just set by the server.

### 5.1. Combining with HTTP headers and payloads

An operation can document cookies, headers, and a JSON response at the same time:

~~~java
document("profile-get",
    requestHeaders(
        headerWithName("Accept")
            .description("Content type accepted by the client")
    ),
    requestCookies(
        cookieWithName("locale")
            .description("Preferred client language code")
    ),
    responseCookies(
        cookieWithName("display-mode")
            .description("UI mode remembered by the server")
    ),
    responseFields(
        fieldWithPath("name").description("User name"),
        fieldWithPath("locale").description("Applied language")
    )
)
~~~

Imports:

~~~java
import static org.springframework.restdocs.cookies.CookieDocumentation.cookieWithName;
import static org.springframework.restdocs.cookies.CookieDocumentation.requestCookies;
import static org.springframework.restdocs.cookies.CookieDocumentation.responseCookies;
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
~~~

Place each piece of data into the right descriptor category:

| Data | Descriptor |
| --- | --- |
| **Accept** header | **requestHeaders(...)** |
| Sent **locale** cookie | **requestCookies(...)** |
| Returned **display-mode** cookie | **responseCookies(...)** |
| JSON fields **name**, **locale** | **responseFields(...)** |

## 6. Optional cookies: optional()

If a cookie can be absent under the API contract, the descriptor can be marked **optional()**:

~~~java
requestCookies(
    cookieWithName("locale")
        .description("Preferred client language code; defaults to vi if omitted")
        .optional()
)
~~~

Or for a response cookie that only appears in certain cases:

~~~java
responseCookies(
    cookieWithName("promotion")
        .description("Promotional campaign code cookie; issued only when eligible")
        .optional()
)
~~~

**optional()** describes that the cookie may not appear in the tested operation. It does not automatically:

- Create a default value for **@CookieValue**.
- Modify the controller or filter.
- Make the cookie appear in the response.
- Verify the business condition for issuing the cookie.

For example, the controller needs its own handling behavior:

~~~java
@GetMapping("/api/profile")
ProfileResponse profile(
        @CookieValue(name = "locale", defaultValue = "vi") String locale) {
    return new ProfileResponse(locale);
}
~~~

Tests should cover both sending **locale=vi** and omitting the cookie to confirm the application actually uses the default value.

## 7. Excluding cookies from the table with ignored()

Sometimes a technical cookie exists in an operation but does not need to be repeated in a specific documentation table. You can mark its descriptor **ignored()**:

~~~java
requestCookies(
    cookieWithName("tracking-id").ignored(),
    cookieWithName("locale")
        .description("Preferred client language code")
)
~~~

The **tracking-id** cookie is still present in the request, but it is not rendered as a row in the snippet. Only use this when the cookie is already explained in a common section or is not something callers need to focus on for that operation.

**ignored()** differs from omitting a descriptor:

- **ignored()** explicitly indicates that the cookie is acknowledged but intentionally excluded from the table.
- Omitting a descriptor can cause strict verification mode to report an undocumented cookie.
- **optional()** means the cookie may be absent; **ignored()** means the cookie does not need to be displayed in the table.

Do not use **ignored()** to hide a cookie containing secrets and assume the data disappears from all snippets. Its value may still appear in **http-request.adoc** or **http-response.adoc**. Inspect the output and use preprocessing if values need to be hidden.

## 8. Describing session cookies and security cookies

Session cookies are typically sensitive. Documentation should explain their role and client usage without placing real values in snippets.

~~~java
responseCookies(
    cookieWithName("SESSION")
        .description("Server-managed session cookie; stored by the client and sent back on requests within the cookie scope")
)
~~~

For a CSRF cookie:

~~~java
responseCookies(
    cookieWithName("XSRF-TOKEN")
        .description("Server-issued CSRF token; used by the client according to the API's CSRF protection mechanism")
)
~~~

These descriptions are examples and do not imply every application uses the same mechanism. If the client must read the CSRF cookie and send its value back in an **X-XSRF-TOKEN** header, document both the response cookie and the request header in the corresponding authentication/CSRF section.

Attributes such as **Secure**, **HttpOnly**, **SameSite**, **Path**, **Domain**, **Max-Age**, and **Expires** typically appear in the **Set-Cookie** header of the response snippet. Cookie descriptors describe the name and meaning; if an attribute is a critical part of the contract, write dedicated assertions and explain it in prose.

Never write real session IDs, refresh tokens, or production authentication cookies into test sources. Use dummy values safe for publication; inspect both cookie snippets and HTTP responses before publishing.

## 9. Complete example with MockMvc

The example uses **Java 17+**, **Spring Boot 3.x**, **JUnit 5**, and **spring-restdocs-mockmvc**.

### 9.1. Controller

~~~java
import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProfileController {

    @GetMapping("/api/profile")
    ProfileView getProfile(
            @CookieValue(name = "locale", defaultValue = "vi")
            String locale,
            HttpServletResponse response) {

        Cookie displayMode = new Cookie("display-mode", "compact");
        displayMode.setPath("/");
        displayMode.setHttpOnly(true);
        displayMode.setSecure(true);
        displayMode.setMaxAge(3600);
        response.addCookie(displayMode);

        return new ProfileView("Lan", locale);
    }
}

record ProfileView(String name, String locale) {}
~~~

### 9.2. Test and descriptors

~~~java
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
class ProfileCookieTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentCookieNamesAndDescriptions() throws Exception {
        mockMvc.perform(get("/api/profile")
                .cookie(new jakarta.servlet.http.Cookie("locale", "vi"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.locale").value("vi"))
            .andExpect(cookie().value("display-mode", "compact"))
            .andExpect(cookie().httpOnly("display-mode", true))
            .andDo(document("profile-get",
                requestCookies(
                    cookieWithName("locale")
                        .description("Preferred client language code")
                ),
                responseCookies(
                    cookieWithName("display-mode")
                        .description("UI mode saved by the server")
                )
            ));
    }
}
~~~

In the test:

- The **locale** cookie is sent in the request via **.cookie(...)**.
- The request descriptor uses **cookieWithName("locale")**.
- The controller issues **display-mode** in the response.
- The response descriptor uses **cookieWithName("display-mode")**.
- Assertions verify the value and attributes of the actually returned cookie.

### 9.3. Documentation output

Snippet directory:

~~~text
build/generated-snippets/
└── profile-get/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── request-cookies.adoc
    └── response-cookies.adoc
~~~

**request-cookies.adoc** and **response-cookies.adoc** present names and descriptions from the descriptors. **http-request.adoc** and **http-response.adoc** show the observed request and response; cookie values may appear here. Do not edit files in **generated-snippets** manually; update the test or descriptors and re-run to regenerate content.

## 10. Integrating into Asciidoctor and CI

In **src/docs/asciidoc/profile.adoc**:

~~~asciidoc
= Profile API
:toc: left

== Get profile

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

Gradle Groovy DSL example when the **org.asciidoctor.jvm.convert** plugin is configured:

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

The `asciidoctor` task depends on `test` so snippets are generated before being included. In CI, verify that the **profile-get** directory and the **request-cookies.adoc** and **response-cookies.adoc** files were generated. If a cookie is renamed in code without updating the descriptor, documentation tests should catch the mismatch.

If the final output is Markdown, use a converter or an appropriate snippet-embedding mechanism. **include::{snippets}/...[]** is Asciidoctor syntax, not standard Markdown syntax.

## 11. Common errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Descriptor cannot find cookie | Name in **cookieWithName(...)** is wrong or cookie is absent from the operation | Cross-check actual request/response cookie names |
| Value chosen instead of cookie name | Used **cookieWithName("compact")** instead of **cookieWithName("display-mode")** | Use the name to the left of the **=** sign |
| Request cookie documented in response snippet | Descriptor placed in the wrong group | Use **requestCookies(...)** or **responseCookies(...)** for the right direction |
| Cookie table is missing a row | Forgot descriptor for the remaining cookie | Declare each cookie separately |
| Cookie does not appear but test still needs documentation | Cookie may be optional without the descriptor reflecting it | Use **optional()** when appropriate and test the missing case |
| Technical cookie appears in the table | No documentation decision made yet | Use **ignored()** when explained elsewhere |
| Session ID still exposed in HTTP response snippet | Only excluded cookie from the descriptor table | Use dummy fixtures or preprocessing and inspect all snippets |
| Cookie description does not tell clients what to do | Description is too generic | Write around purpose and observable behavior |
| Asciidoctor missing cookie snippet | Test has not run or include uses the wrong identifier | Check document ID, output directory, and task dependencies |

## 12. Practice exercise

An API saves user preferences:

~~~text
POST /api/preferences
~~~

The response issues two cookies:

- **display-mode**: values `compact` or `comfortable`.
- **locale**: language codes `vi` or `en`.

Requirements:

1. Write a controller or filter that issues both cookies via **Set-Cookie**.
2. Write a MockMvc test confirming both cookies are present in the response with the expected values.
3. Use **responseCookies(...)** with two **cookieWithName(...)** descriptors.
4. Write descriptions stating the purpose and accepted values of each cookie.
5. Add assertions for **Path**, **Secure**, **HttpOnly**, and **Max-Age** per the contract.
6. Include **response-cookies.adoc** and **http-response.adoc** in Asciidoctor.
7. Try renaming a cookie in the controller without updating the descriptor; confirm the documentation test catches the mismatch.

Sample descriptors:

~~~java
responseCookies(
    cookieWithName("display-mode")
        .description("Saved UI mode; compact or comfortable"),
    cookieWithName("locale")
        .description("Language code saved for subsequent visits; vi or en")
)
~~~

**Completion criteria:** both cookie names match the response; descriptions are meaningful to clients; tests verify values and attributes; snippets accurately reflect the response; Asciidoctor documentation builds successfully in build/CI.

## Key Takeaways

**cookieWithName("name")** declares a descriptor by cookie name; **description(...)** explains its purpose and client usage. Place descriptors in **requestCookies(...)** when the client sends cookies and **responseCookies(...)** when the server issues them. You can use **optional()** for cookies that may be absent or **ignored()** when intentionally hiding an acknowledged cookie from the table, though neither removes values from all snippets. Inspect actual requests/responses, protect sessions/tokens, and include cookie snippets in Asciidoctor so the cookie contract is verified by tests and CI.

**References:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [Spring REST Docs CookieDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/cookies/CookieDocumentation.html), [Spring MVC @CookieValue](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/cookievalue.html), and [RFC 6265](https://www.rfc-editor.org/rfc/rfc6265).
