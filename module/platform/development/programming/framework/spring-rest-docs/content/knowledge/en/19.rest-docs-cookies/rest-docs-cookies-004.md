# Required, optional, and default-value cookies

## Lesson Objectives

An API may require the client to send a cookie, accept a cookie if present, or fall back to a default value when the cookie is absent. These three cases must be represented consistently across the controller, tests, and **Spring REST Docs** documentation. If the controller requires a cookie while the descriptor marks it optional, the documentation will misrepresent the contract. Conversely, if a cookie is genuinely optional but tests never check the missing-cookie case, clients may encounter unexpected errors.

This lesson belongs to the **Cookies** chapter of the **SPRING_REST_DOCS** module: creating verifiable REST API documentation from HTTP tests using **MockMvc**, **WebTestClient**, or **REST Assured**; generating snippets for requests, responses, payloads, parameters, and headers; authoring Asciidoctor/Markdown documentation and integrating it into builds and CI.

After this lesson, you will be able to:

- Distinguish required cookies, optional cookies, and cookies with default values.
- Configure **@CookieValue** using **required** and **defaultValue**.
- Describe optionality using **optional()** on cookie descriptors.
- Write MockMvc tests for requests with and without cookies.
- Avoid confusing REST Docs' `optional()` with Spring MVC binding behavior.
- Document default values, error responses, and multiple cookie scenarios.
- Combine request/response cookie snippets with Asciidoctor and CI.

## 1. Three common cookie contracts

Suppose the **GET /api/profile** endpoint accepts a **locale** cookie to choose the language:

| Contract | When the client sends the cookie | When the client omits it | Spring declaration example |
| --- | --- | --- | --- |
| Required | Uses the cookie value | Request fails to bind; typically returns 400 under default handling | **@CookieValue("locale")** |
| Optional, no default | Uses the cookie value | Java receives **null** if the type/declaration allows it | **@CookieValue(name="locale", required=false)** |
| With default value | Uses the cookie value | Uses the fallback value | **@CookieValue(name="locale", defaultValue="vi")** |

These are three behaviors at the **binding/controller layer**. Spring REST Docs has its own mechanism to describe whether a cookie may be absent in the documented request. Both layers must stay consistent.

### 1.1. Processing flow

~~~mermaid
flowchart TD
    A["HTTP request"] --> B{"Has locale cookie?"}
    B -->|Yes| C["Bind cookie value"]
    B -->|No| D{"How is controller declared?"}
    D -->|required=true| E["Binding error, typically 400"]
    D -->|required=false| F["Bind null"]
    D -->|defaultValue=vi| G["Bind value vi"]
    C --> H["Controller processes"]
    F --> H
    G --> H
~~~

Do not treat every cookie as optional simply because a client could omit the header. The **API contract** determines which cookies are required, and your code and tests must enforce that contract.

## 2. Required cookies

### 2.1. Declaring with @CookieValue

When a cookie is required, you can use:

~~~java
@GetMapping("/api/profile")
ProfileResponse getProfile(
        @CookieValue("locale") String locale) {
    return new ProfileResponse("Lan", locale);
}
~~~

The **required** attribute defaults to **true**. If a request lacks the **locale** cookie, Spring MVC cannot bind the required parameter; with standard exception handling configuration, the response is typically **400 Bad Request**.

If you want to state the contract explicitly:

~~~java
@CookieValue(name = "locale", required = true) String locale
~~~

Both declarations have the same meaning. Only use **required = true** when it makes the code clearer.

### 2.2. Required descriptor in Spring REST Docs

For a required cookie, declare the descriptor without **optional()**:

~~~java
requestCookies(
    cookieWithName("locale")
        .description("Required client language code, for example vi or en")
)
~~~

Imports:

~~~java
import static org.springframework.restdocs.cookies.CookieDocumentation.cookieWithName;
import static org.springframework.restdocs.cookies.CookieDocumentation.requestCookies;
~~~

The success test must send the cookie:

~~~java
mockMvc.perform(get("/api/profile")
        .cookie(new Cookie("locale", "vi")))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.locale").value("vi"))
    .andDo(document("profile-get",
        requestCookies(
            cookieWithName("locale")
                .description("Required client language code")
        )
    ));
~~~

In the example above, **requestCookies(...)** describes the cookie actually sent in the request. REST Docs checks the descriptor against the operation; it does not magically supply a missing cookie.

### 2.3. Testing the missing-cookie case

There should be a separate test for requests without the cookie:

~~~java
@Test
void rejectsRequestWithoutRequiredLocaleCookie() throws Exception {
    mockMvc.perform(get("/api/profile"))
        .andExpect(status().isBadRequest());
}
~~~

The 400 status in the example depends on your controller and the application's exception handling. If you have a custom **@ControllerAdvice**, assert the HTTP status and payload according to your actual contract. This test verifies missing-cookie behavior; it does not necessarily need to generate the success operation's snippets.

## 3. Optional cookies without a default value

If the API accepts requests even when the cookie does not exist and the application handles that case separately, declare:

~~~java
@GetMapping("/api/profile")
ProfileResponse getProfile(
        @CookieValue(name = "locale", required = false) String locale) {
    String effectiveLocale = locale == null ? "vi" : locale;
    return new ProfileResponse("Lan", effectiveLocale);
}
~~~

Here:

- When **locale=en** is present, the controller uses **en**.
- When the cookie is absent, the Java parameter is **null**.
- The application decides the fallback value in controller/service logic.

If `null` is handled in a service, define the fallback rule in one clear place rather than repeating it across multiple endpoints.

In Spring REST Docs, the cookie descriptor is marked optional:

~~~java
requestCookies(
    cookieWithName("locale")
        .description("Preferred client language code; if missing, the API uses vi")
        .optional()
)
~~~

**optional()** tells REST Docs that the cookie may not appear in the documented request. It does **not** change **@CookieValue(required = ...)**, does not automatically assign **null** or **vi**, and does not alter controller behavior.

### 3.1. Tests with and without the cookie

~~~java
@Test
void usesProvidedLocaleCookie() throws Exception {
    mockMvc.perform(get("/api/profile")
            .cookie(new Cookie("locale", "en")))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.locale").value("en"));
}

@Test
void usesFallbackWhenOptionalLocaleCookieIsMissing() throws Exception {
    mockMvc.perform(get("/api/profile"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.locale").value("vi"));
}
~~~

When generating snippets for a request **with** the cookie, an optional descriptor can still be used to describe the overall contract. If you need snippets explicitly illustrating the missing-cookie case, record a separate operation/test and use an **optional()** descriptor so REST Docs knows the absence is valid.

## 4. Cookies with a default value

### 4.1. Using defaultValue

If the API has a fixed default value, declare it directly:

~~~java
@GetMapping("/api/profile")
ProfileResponse getProfile(
        @CookieValue(name = "locale", defaultValue = "vi") String locale) {
    return new ProfileResponse("Lan", locale);
}
~~~

When the **locale** cookie is absent, Spring uses **vi**. When the cookie has a value, that value is bound. In **@CookieValue**, setting **defaultValue** also makes the parameter non-mandatory in the **required** sense; there is no need to specify **required = false** at the same time.

An alternative approach is:

~~~java
@CookieValue(name = "locale", required = false) String locale
// then handle null explicitly in code
~~~

Both approaches can produce similar results, but they express different intents. **defaultValue** fits when there is a clear fallback value; **required=false** fits when the code needs to distinguish the absent state and handle it explicitly.

### 4.2. Documenting the default value

Descriptor:

~~~java
requestCookies(
    cookieWithName("locale")
        .description("Language code; defaults to vi if the client omits the cookie")
        .optional()
)
~~~

Descriptors do not have a separate property to set a default value for **@CookieValue**. Document the default value in **description(...)**, then prove it with a test:

~~~java
@Test
void documentsDefaultLocaleWhenCookieIsAbsent() throws Exception {
    mockMvc.perform(get("/api/profile")
            .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.locale").value("vi"))
        .andDo(document("profile-default-locale",
            requestCookies(
                cookieWithName("locale")
                    .description("Language code; defaults to vi if omitted")
                    .optional()
            )
        ));
}
~~~

This test records a request without the cookie and a response using the default language. If the REST Docs version you are using does not handle an absent optional cookie descriptor as expected, check that version's behavior and inspect the generated snippet; never declare the cookie as though it had been sent.

## 5. Distinguishing required, defaultValue, and optional()

These three mechanisms are often confused because all three relate to a cookie potentially being absent:

| Mechanism | Where declared | Effect |
| --- | --- | --- |
| **required=true** | **@CookieValue** | Spring requires the cookie to bind the parameter |
| **required=false** | **@CookieValue** | Allows missing cookie; bound value is typically `null` |
| **defaultValue="vi"** | **@CookieValue** | Uses `vi` when cookie is missing or empty per binding rules |
| **.optional()** | REST Docs cookie descriptor | Allows the cookie to be absent when verifying/generating docs |
| **.ignored()** | REST Docs cookie descriptor | Acknowledges the cookie exists without displaying it in the snippet table |

Keep the two independent layers in mind:

- **Spring MVC** decides whether a request missing the cookie can be handled and what value Java receives.
- **Spring REST Docs** validates and documents the tested operation; **optional()** does not change application binding.

Do not use **.optional()** to mask a controller that declares a required cookie. That produces documentation claiming clients may omit the cookie while the application actually returns an error.

## 6. Response cookies with defaults or conditional issuance

Required/optional semantics can also apply to **response** cookies in how the contract is expressed: does the server always return the cookie or only in certain cases?

Example where the server always issues **display-mode**:

~~~java
responseCookies(
    cookieWithName("display-mode")
        .description("UI mode always returned by the server after saving preferences")
)
~~~

If the cookie is only issued when the client chooses to remember the preference:

~~~java
responseCookies(
    cookieWithName("display-mode")
        .description("UI mode; issued only when the client chooses to save")
        .optional()
)
~~~

Tests should verify both the case with and without **Set-Cookie**. **optional()** only describes the non-mandatory presence of the cookie in the operation; the issuance condition remains application logic and must be stated in the documentation.

## 7. Complete example with MockMvc

The example uses **Java 17+**, **Spring Boot 3.x**, **JUnit 5**, and **spring-restdocs-mockmvc**.

### 7.1. Controller

~~~java
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProfileController {

    @GetMapping("/api/profile")
    ProfileResponse getProfile(
            @CookieValue(name = "locale", defaultValue = "vi") String locale) {
        return new ProfileResponse("Lan", locale);
    }
}

record ProfileResponse(String name, String locale) {}
~~~

### 7.2. Test documenting a request with the cookie and a request using the default

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
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ProfileController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class ProfileLocaleDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentProfileWithLocaleCookie() throws Exception {
        mockMvc.perform(get("/api/profile")
                .cookie(new Cookie("locale", "en"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.locale").value("en"))
            .andDo(document("profile-with-locale",
                requestCookies(
                    cookieWithName("locale")
                        .description("Language code; defaults to vi if omitted")
                        .optional()
                )
            ));
    }

    @Test
    void documentProfileWithDefaultLocale() throws Exception {
        mockMvc.perform(get("/api/profile")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.locale").value("vi"))
            .andDo(document("profile-default-locale",
                requestCookies(
                    cookieWithName("locale")
                        .description("Language code; defaults to vi if omitted")
                        .optional()
                )
            ));
    }
}
~~~

The two tests demonstrate two scenarios of the same contract:

- When **locale=en** is sent, the response uses **en**.
- When the cookie is omitted, the response uses **vi**.

**requestCookies(...)** describes an optional cookie; the default test omits **.cookie(...)**, so the request genuinely contains no cookie. When using a REST Docs version with strict cookie descriptor validation, verify **optional()** behavior by running the test and inspecting the generated snippet.

### 7.3. Required cookie case

If you change the controller to:

~~~java
@CookieValue(name = "locale") String locale
~~~

then the test with the cookie still passes, while the test without the cookie must assert a binding error. In the success documentation, remove **.optional()** from the descriptor:

~~~java
requestCookies(
    cookieWithName("locale")
        .description("Required client language code")
)
~~~

Do not use an optional descriptor for this endpoint, as it would inaccurately describe how the API can be called.

## 8. Combining cookies with headers and response body

An operation can document cookies, headers, and a JSON response together:

~~~java
document("profile-get",
    requestHeaders(
        headerWithName("Accept")
            .description("Response content type accepted by the client")
    ),
    requestCookies(
        cookieWithName("locale")
            .description("Language code; defaults to vi if omitted")
            .optional()
    ),
    responseCookies(
        cookieWithName("display-mode")
            .description("Display mode returned by the server if the user saved one")
            .optional()
    ),
    responseFields(
        fieldWithPath("name").description("User name"),
        fieldWithPath("locale").description("Language applied to the response")
    )
)
~~~

Required imports:

~~~java
import static org.springframework.restdocs.cookies.CookieDocumentation.cookieWithName;
import static org.springframework.restdocs.cookies.CookieDocumentation.requestCookies;
import static org.springframework.restdocs.cookies.CookieDocumentation.responseCookies;
import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;
import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
~~~

Only mark **.optional()** when the endpoint genuinely allows the cookie to be absent or omits issuing the cookie in some responses. If the cookie cannot be omitted, keep the descriptor required.

## 9. Integrating snippets into Asciidoctor and CI

With the two tests in section 7, the expected snippets directory is:

~~~text
build/generated-snippets/
├── profile-with-locale/
│   ├── request-cookies.adoc
│   └── http-response.adoc
└── profile-default-locale/
    ├── request-cookies.adoc
    └── http-response.adoc
~~~

In **src/docs/asciidoc/profile.adoc**:

~~~asciidoc
= Profile API
:toc: left

== Sending the locale cookie

GET /api/profile

include::{snippets}/profile-with-locale/request-cookies.adoc[]
include::{snippets}/profile-with-locale/http-response.adoc[]

== Omitting locale: using default

GET /api/profile

include::{snippets}/profile-default-locale/request-cookies.adoc[]
include::{snippets}/profile-default-locale/http-response.adoc[]
~~~

Gradle Groovy DSL example, assuming the **org.asciidoctor.jvm.convert** plugin is configured:

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

In CI, run tests before building Asciidoctor. If the controller changes from an optional cookie to a required one while the missing-cookie test still expects 200, the assertion will catch the contract change. If the descriptor remains marked optional after the code requires the cookie, reviews and tests must update them in sync.

If publishing Markdown, use a compatible converter or include approach. **include::{snippets}/...[]** is Asciidoctor syntax, not standard Markdown syntax.

## 10. Common errors

| Symptom | Cause | Fix |
| --- | --- | --- |
| Missing cookie unexpectedly returns 400 | **@CookieValue** defaults to **required=true** | Use **required=false** or **defaultValue** if the contract permits |
| Controller receives **null** | Cookie declared **required=false** without null handling | Handle explicitly in controller/service and test both cases |
| Default-value cookie still treated as required | Descriptor not marked **.optional()** | Explicitly indicate the cookie may be absent in the descriptor |
| REST Docs says optional but API returns 400 | Optional descriptor out of sync with required **@CookieValue** | Fix the code or descriptor to match the real contract |
| Docs state default `vi` but response returns another value | Missing assertion verifying the default | Test a request without the cookie and assert the response |
| Marked optional yet cookie is sent in every test | Missing-cookie scenario was never tested | Add a test for a request without the cookie |
| Response cookie does not appear | Code does not issue cookie in the response | Check **addCookie/Set-Cookie** and matchers |
| Cookie missing from table | Wrong descriptor name or placed in the wrong group | Cross-check actual cookies and use the right `requestCookies`/`responseCookies` |

## 11. Practice exercise

Design an endpoint:

~~~text
GET /api/catalog
~~~

Contract:

- The **locale** cookie is optional.
- If **locale=vi** or **locale=en** is present, the response uses that language.
- If the cookie is absent, the application defaults to **vi**.
- A cookie with an invalid value outside the allowed set returns an error according to a contract you choose and document clearly.

Requirements:

1. Write a controller using **@CookieValue(name = "locale", defaultValue = "vi")**.
2. Write a MockMvc test with cookie **en**, verifying the response uses **en**.
3. Write a test without the cookie, verifying the response uses **vi**.
4. Use **requestCookies(cookieWithName("locale").description(...).optional())** to document the optional cookie.
5. Write a test for an invalid cookie value and assert the error status/payload.
6. Generate snippets for both the cookie-present and default-value scenarios.
7. Include the snippets in Asciidoctor and run `test → asciidoctor` in CI.

Sample descriptor:

~~~java
requestCookies(
    cookieWithName("locale")
        .description("Language code; accepts vi or en, defaults to vi when absent")
        .optional()
)
~~~

**Completion criteria:** the controller handles present and absent cookies properly; tests prove the default value; the descriptor reflects optionality; invalid cookie errors are tested; snippets and documentation build successfully.

## Key Takeaways

Required cookies typically use **@CookieValue** with **required=true** (the default) and a descriptor without **.optional()**. Optional cookies can use **required=false**, while cookies with defaults use **defaultValue**; both cases can use **.optional()** in the descriptor because the cookie may be absent. **.optional() only controls Spring REST Docs validation and documentation; it does not alter Spring MVC binding.** Write tests for both cookie-present and cookie-absent cases, assert the corresponding default value or error, and include the snippets in Asciidoctor and your build/CI.

**References:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [Spring REST Docs CookieDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/cookies/CookieDocumentation.html), [Spring MVC @CookieValue](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/cookievalue.html), and [RFC 6265: HTTP State Management Mechanism](https://www.rfc-editor.org/rfc/rfc6265).
