# Testing cookies in MockMvc or REST Assured

## Lesson Objectives

Cookies are part of the HTTP contract: the client can send cookies in the request, and the server can issue, update, or delete cookies in the response. Documentation is only reliable when tests verify the actual cookies, values, and attributes committed to by the API. Both **MockMvc** and **REST Assured** can verify cookie behavior; Spring REST Docs adds descriptors to generate cookie documentation snippets.

This lesson belongs to the **Cookies** chapter of the **SPRING_REST_DOCS** module: creating verifiable REST API documentation from HTTP tests using **MockMvc**, **WebTestClient**, or **REST Assured**; generating snippets for requests, responses, payloads, parameters, and headers; authoring Asciidoctor/Markdown documentation and integrating it into builds and CI.

After this lesson, you will be able to:

- Verify sent cookies with MockMvc and REST Assured.
- Verify response cookies for name, value, `Path`, `Domain`, `Max-Age`, `Secure`, and `HttpOnly`.
- Inspect **Cookie** and **Set-Cookie** headers when verifying wire representations.
- Combine cookie assertions with **requestCookies(...)** and **responseCookies(...)**.
- Configure REST Docs for MockMvc or REST Assured.
- Choose safe test data and keep real sessions/tokens out of snippets.
- Organize tests for missing, invalid, and expired cookies.
- Generate snippets and integrate them into Asciidoctor/CI.

## 1. Cookie testing strategy

A good cookie test should verify both **application behavior** and the **HTTP contract**. Depending on the scenario, verify:

| Component | Question to confirm | Common tools |
| --- | --- | --- |
| Request cookie | Does the client send the right name and value? | MockMvc **.cookie(...)**; REST Assured **.cookie(...)** |
| Response cookie | Does the server issue the cookie? | MockMvc **cookie()** matcher; REST Assured response cookie API |
| Value | Is the returned cookie value right? | **cookie().value(...)**; **response.getCookie(...).getValue()** |
| Attributes | Are `Path`, `Secure`, `HttpOnly`, and `Max-Age` right? | Cookie matchers or inspecting **Set-Cookie** |
| Missing cookie | Does the API use a default or return an error? | Request without cookie, assert status/body |
| Multiple cookies | Are all required cookies present? | Check each cookie and matching descriptor |
| Documentation | Do snippets reflect the actual cookies? | **requestCookies(...)**, **responseCookies(...)** |

Never assert only HTTP 200 and conclude cookies are correct. An API can return 200 while issuing a cookie missing `Secure`, with the wrong `Path`, or with an invalid value.

## 2. Preparing the API example

The example uses an endpoint that retrieves UI preferences. The client sends a **locale** cookie; the server returns a **display-mode** cookie.

~~~java
import jakarta.servlet.http.Cookie;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class PreferenceController {

    @GetMapping(
        path = "/api/preferences",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    PreferenceResponse getPreferences(
            @CookieValue(name = "locale", defaultValue = "vi") String locale,
            HttpServletResponse response) {

        Cookie displayMode = new Cookie("display-mode", "compact");
        displayMode.setPath("/");
        displayMode.setHttpOnly(true);
        displayMode.setSecure(true);
        displayMode.setMaxAge(3600);
        response.addCookie(displayMode);

        return new PreferenceResponse(locale, "loaded");
    }
}

record PreferenceResponse(String locale, String status) {}
~~~

This is a Spring MVC/Servlet example. Cookie values are dummy test data. For real authentication sessions or tokens, the application must use a secure session-management mechanism; never hardcode static strings like the example above.

## 3. Verifying request cookies with MockMvc

MockMvc lets you attach cookies to a request via **.cookie(...)**:

~~~java
import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(PreferenceController.class)
class PreferenceCookieMockMvcTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void readsLocaleCookie() throws Exception {
        mockMvc.perform(get("/api/preferences")
                .cookie(new Cookie("locale", "en"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.locale").value("en"));
    }
}
~~~

The request must send the exact **cookie name** that the controller reads via **@CookieValue**. If you send **language=en** instead of **locale=en**, Spring cannot bind the intended cookie and may fall back to `defaultValue` or return an error depending on the controller declaration.

### 3.1. Testing multiple request cookies

MockMvc accepts multiple `Cookie` objects in a single call:

~~~java
mockMvc.perform(get("/api/preferences")
        .cookie(
            new Cookie("locale", "en"),
            new Cookie("display-mode", "compact")
        ))
    .andExpect(status().isOk());
~~~

If the endpoint uses both cookies, add assertions for the corresponding behavior. If only **locale** belongs to the endpoint's contract while **display-mode** is sent by another client component, do not document it as an input the API promises to process.

## 4. Verifying response cookies with MockMvc

MockMvc provides **MockMvcResultMatchers.cookie()** to verify response cookies.

~~~java
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.cookie;

@Test
void returnsDisplayModeCookieWithExpectedAttributes() throws Exception {
    mockMvc.perform(get("/api/preferences")
            .cookie(new Cookie("locale", "vi"))
            .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(cookie().exists("display-mode"))
        .andExpect(cookie().value("display-mode", "compact"))
        .andExpect(cookie().path("display-mode", "/"))
        .andExpect(cookie().httpOnly("display-mode", true))
        .andExpect(cookie().secure("display-mode", true))
        .andExpect(cookie().maxAge("display-mode", 3600));
}
~~~

Commonly used matchers:

| Matcher | Purpose |
| --- | --- |
| **exists(name)** | Cookie is present in the response |
| **value(name, value)** | Cookie value matches |
| **path(name, path)** | `Path` matches |
| **domain(name, domain)** | `Domain` matches |
| **maxAge(name, seconds)** | Lifetime matches |
| **secure(name, true)** | `Secure` flag is set |
| **httpOnly(name, true)** | `HttpOnly` flag is set |

Matcher names and overloads may vary across Spring Test versions. Use the API of your project's dependency version and check its corresponding Javadoc.

### 4.1. Verifying SameSite via Set-Cookie

MockMvc matchers do not provide a dedicated `SameSite` matcher in every version. You can inspect the header emitted by the server:

~~~java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;

mockMvc.perform(get("/api/preferences"))
    .andExpect(header().string(
        "Set-Cookie",
        containsString("SameSite=Lax")
    ));
~~~

If a response contains multiple cookies, there may be multiple **Set-Cookie** headers. Do not assume a header matcher always inspects the right cookie; retrieve the header list and verify the header containing the matching cookie name:

~~~java
MvcResult result = mockMvc.perform(get("/api/preferences"))
    .andExpect(status().isOk())
    .andReturn();

List<String> setCookieHeaders =
    result.getResponse().getHeaders("Set-Cookie");

assertThat(setCookieHeaders)
    .anySatisfy(value -> {
        assertThat(value).contains("display-mode=compact");
        assertThat(value).contains("SameSite=Lax");
    });
~~~

The snippet above uses AssertJ. Import **MvcResult**, **List**, and the corresponding assertions when adding this to a test class. Checking the header verifies that the server emits the attribute, though it does not prove browsers enforce the cross-site policy as expected.

## 5. Generating cookie snippets using Spring REST Docs with MockMvc

Once assertions verify the request/response, add descriptors to generate snippets:

~~~java
import static org.springframework.restdocs.cookies.CookieDocumentation.cookieWithName;
import static org.springframework.restdocs.cookies.CookieDocumentation.requestCookies;
import static org.springframework.restdocs.cookies.CookieDocumentation.responseCookies;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;

mockMvc.perform(get("/api/preferences")
        .cookie(new Cookie("locale", "en"))
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.locale").value("en"))
    .andExpect(cookie().value("display-mode", "compact"))
    .andDo(document("preferences-get",
        requestCookies(
            cookieWithName("locale")
                .description("Preferred client language code; defaults to vi if absent")
        ),
        responseCookies(
            cookieWithName("display-mode")
                .description("UI mode remembered by the server for subsequent visits")
        )
    ));
~~~

With **@AutoConfigureRestDocs**, snippets are typically generated under:

~~~text
build/generated-snippets/
└── preferences-get/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── request-cookies.adoc
    └── response-cookies.adoc
~~~

**request-cookies.adoc** documents the **locale** cookie; **response-cookies.adoc** documents **display-mode**. HTTP request/response snippets record the observed operation contents, which may include cookie values and `Set-Cookie`. Inspect the data before publishing.

### 5.1. Documentation test setup

~~~java
@WebMvcTest(PreferenceController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class PreferenceCookieDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentsRequestAndResponseCookies() throws Exception {
        mockMvc.perform(get("/api/preferences")
                .cookie(new Cookie("locale", "en"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.locale").value("en"))
            .andExpect(cookie().value("display-mode", "compact"))
            .andExpect(cookie().httpOnly("display-mode", true))
            .andExpect(cookie().secure("display-mode", true))
            .andDo(document("preferences-get",
                requestCookies(
                    cookieWithName("locale")
                        .description("Preferred client language code")
                ),
                responseCookies(
                    cookieWithName("display-mode")
                        .description("UI mode remembered by the server")
                )
            ));
    }
}
~~~

This shows the test class body; include the necessary imports and annotations as in the earlier example. Descriptors do not replace assertions: **responseCookies(...)** does not by itself verify the value **compact**, `Secure`, or `HttpOnly`.

## 6. Testing missing, invalid, and expired cookies

### 6.1. Cookie not sent

If the controller uses **defaultValue**, test a request without the cookie:

~~~java
mockMvc.perform(get("/api/preferences")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.locale").value("vi"));
~~~

If the cookie is required, tests should confirm the error per the contract:

~~~java
mockMvc.perform(get("/api/secure-profile"))
    .andExpect(status().isBadRequest());
~~~

The exact HTTP status depends on your exception handler. If the API converts errors into a structured response, add payload assertions and error REST Docs snippets when needed.

### 6.2. Cookie with an invalid value

For the **locale** cookie, the API might accept only **vi** or **en**. Send an invalid value:

~~~java
mockMvc.perform(get("/api/preferences")
        .cookie(new Cookie("locale", "unknown")))
    .andExpect(status().isBadRequest());
~~~

Make sure the application validates cookies; **@CookieValue** only binds the string and does not automatically validate business value sets. Without validation, requests may be processed with responses outside the intended contract.

### 6.3. Expired or deleted cookies

A cookie is typically deleted via a **Set-Cookie** response with the same name and scope alongside **Max-Age=0** or a past `Expires` timestamp:

~~~java
mockMvc.perform(delete("/api/preferences/display-mode"))
    .andExpect(status().isNoContent())
    .andExpect(cookie().maxAge("display-mode", 0));
~~~

Tests should also verify matching `Path`/`Domain` if part of the contract; otherwise, browsers may fail to delete the old cookie.

## 7. Testing cookies with REST Assured

REST Assured lets you send cookies and read response cookies via a fluent API. To document with Spring REST Docs, configure the **RestAssuredRestDocumentation** filter.

### 7.1. Sending request cookies

~~~java
given()
    .cookie("locale", "en")
    .when()
    .get("/api/preferences")
    .then()
    .statusCode(200)
    .body("locale", equalTo("en"));
~~~

With multiple cookies:

~~~java
given()
    .cookies(Map.of(
        "locale", "en",
        "display-mode", "compact"
    ))
    .when()
    .get("/api/preferences")
    .then()
    .statusCode(200);
~~~

Common imports:

~~~java
import static io.restassured.RestAssured.given;
import static org.hamcrest.Matchers.equalTo;
import java.util.Map;
~~~

### 7.2. Verifying response cookies

REST Assured lets you read cookies from the response:

~~~java
Response response =
    given()
        .when()
        .get("/api/preferences");

assertThat(response.getCookie("display-mode"))
    .isEqualTo("compact");
~~~

This snippet uses AssertJ; import **io.restassured.response.Response** and the corresponding assertions. You can inspect additional cookie details using REST Assured's cookie API or assert the **Set-Cookie** header:

~~~java
given()
    .when()
    .get("/api/preferences")
    .then()
    .statusCode(200)
    .header("Set-Cookie", containsString("display-mode=compact"))
    .header("Set-Cookie", containsString("HttpOnly"));
~~~

When multiple `Set-Cookie` headers are present, check the full header collection or specific cookie rather than relying on header ordering. Reading the cookie value via **getCookie(...)** is convenient for simple assertions; inspecting headers is better suited when verifying attributes.

## 8. Generating snippets with REST Assured

REST Docs integrates with REST Assured via the **RestAssuredRestDocumentation** filter. Example:

~~~java
import static io.restassured.RestAssured.given;
import static org.springframework.restdocs.cookies.CookieDocumentation.cookieWithName;
import static org.springframework.restdocs.cookies.CookieDocumentation.requestCookies;
import static org.springframework.restdocs.cookies.CookieDocumentation.responseCookies;
import static org.springframework.restdocs.restassured.RestAssuredRestDocumentation.document;

given(spec)
    .filter(document("preferences-get-rest-assured",
        requestCookies(
            cookieWithName("locale")
                .description("Preferred client language code")
        ),
        responseCookies(
            cookieWithName("display-mode")
                .description("UI mode remembered by the server")
        )
    ))
    .cookie("locale", "en")
    .when()
    .get("/api/preferences")
    .then()
    .statusCode(200)
    .body("locale", equalTo("en"));
~~~

**spec** is a **RequestSpecification** configured with the REST Docs filter per your version's guide. The abridged example focuses on where **document(...)** goes; your project must configure **RestAssuredRestDocumentation.documentationConfiguration(...)** and the snippet output directory before running tests.

### 8.1. Configuring RestAssuredRestDocumentation

A common setup:

~~~java
@BeforeEach
void setUp(RestDocumentationContextProvider restDocumentation) {
    this.spec = new RequestSpecBuilder()
        .addFilter(documentationConfiguration(restDocumentation))
        .build();
}
~~~

In a real project, declare the **RequestSpecification spec** field, add the imports from REST Assured and Spring REST Docs, and apply the appropriate JUnit extension/test lifecycle. Depending on your REST Docs version, output paths and snippet defaults can be configured in `documentationConfiguration`.

## 9. When to use MockMvc vs. REST Assured?

| Criterion | MockMvc | REST Assured |
| --- | --- | --- |
| Spring MVC test integration | Direct, convenient with **@WebMvcTest** | Calls endpoints via HTTP/test server or matching configuration |
| Sending cookies | **.cookie(new Cookie(...))** | **.cookie(...)**, **.cookies(...)** |
| Response cookie assertions | **cookie()** result matchers | **getCookie(...)**, cookie API, or headers |
| Inspecting `Set-Cookie` | Header matchers and response result | **.header(...)**, response headers |
| REST Docs | **MockMvcRestDocumentation.document(...)** | **RestAssuredRestDocumentation.document(...)** filter |
| Best suited for | Controller slice tests and Spring MVC contracts | API integration tests, fluent client tests, or standalone HTTP tests |

Choose the tool according to the layer under test. MockMvc fits when testing controllers without a live server; REST Assured fits HTTP integration flows or testing APIs against a running endpoint. Neither replaces browser tests when the contract depends on cross-site browser cookie policies.

## 10. Protecting cookie values in tests and snippets

Never use real session cookies, tokens, or user data in tests. Example:

~~~java
new Cookie("SESSION", "test-session-placeholder")
~~~

Placeholder values let snippets demonstrate how clients send cookies without leaking authentication secrets. However, **http-request.adoc** and **http-response.adoc** snippets can print values even when cookie descriptors only document names. Therefore:

- Use dummy sessions and invalid/inert test tokens.
- Review all request/response snippets before publishing.
- Use operation preprocessors to replace or remove values if tests need sensitive fixtures.
- Never log cookies on test failures.
- Never commit cookie jars or user session files into the repository.

If a cookie is part of the contract, keep its name and purpose documented via **requestCookies(...)**/**responseCookies(...)**; mask only secret values. Do not assume **ignored()** on a descriptor removes a cookie from all HTTP snippets.

## 11. Integrating snippets into Asciidoctor and CI

After running tests, the output directory may look like:

~~~text
build/generated-snippets/
├── preferences-get/
│   ├── http-request.adoc
│   ├── http-response.adoc
│   ├── request-cookies.adoc
│   └── response-cookies.adoc
└── preferences-get-rest-assured/
    ├── http-request.adoc
    ├── http-response.adoc
    ├── request-cookies.adoc
    └── response-cookies.adoc
~~~

In **src/docs/asciidoc/preferences.adoc**:

~~~asciidoc
= Preferences API
:toc: left

== Get preferences

GET /api/preferences

=== Request cookies

include::{snippets}/preferences-get/request-cookies.adoc[]

=== Response cookies

include::{snippets}/preferences-get/response-cookies.adoc[]

=== HTTP response

include::{snippets}/preferences-get/http-response.adoc[]
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

In CI, run tests before building Asciidoctor. Broken cookie tests, response cookies missing flags, or mismatched descriptors must fail the pipeline. Verify snippet outputs contain no real session/token values prior to publishing.

If the final output is Markdown, use a compatible converter or include approach. **include::{snippets}/...[]** is Asciidoctor syntax, not standard Markdown.

## 12. Common errors

| Symptom | Cause | Fix |
| --- | --- | --- |
| Controller uses default even though test sent cookie | Wrong request cookie name | Cross-check **@CookieValue** and **.cookie(...)** |
| Response has cookie but wrong value | Issuance logic or test fixture bug | Assert **.value(...)**/**getCookie(...)** |
| Cookie missing `Secure`/`HttpOnly` | Code did not configure flags | Add matchers and inspect `Set-Cookie` |
| Flaky `SameSite` assertion | Multiple `Set-Cookie` headers or matcher checked another header | Filter the right header by cookie name |
| REST Docs does not generate cookie snippet | Missing **requestCookies(...)**/**responseCookies(...)** | Add descriptors to the right `document` operation |
| Descriptor mismatch | Wrong cookie name or request/response direction | Compare names in the actual operation |
| Snippet exposes session/token | Real values used in tests | Use placeholders/preprocessors and inspect output |
| MockMvc passes but browser does not send cookie | Test does not simulate cross-site browser policy | Add HTTPS browser tests |
| Asciidoctor reports missing snippet | Wrong ID or tests did not run first | Align document ID, includes, and task dependencies |

## 13. Practice exercise

API:

~~~text
POST /api/session
GET /api/profile
DELETE /api/session
~~~

Contract:

- POST creates a session and issues the **SESSION** cookie with `HttpOnly`, `Secure`, `Path`, and `Max-Age`.
- GET requires the `SESSION` cookie; if valid, returns the profile.
- DELETE ends the session and issues an expired `SESSION` cookie.
- Cookie values in tests are placeholders only.

Requirements:

1. Write a MockMvc POST test, asserting cookie existence, dummy value, and flags.
2. Document the response cookie with **responseCookies(cookieWithName("SESSION")...)**.
3. Write a GET test with `SESSION` and a test without `SESSION`; assert the expected status/body.
4. Write a DELETE test, asserting `Max-Age=0` and a `Path` matching the original cookie.
5. Write a REST Assured test sending the `SESSION` cookie and verifying the response.
6. Generate request/response cookie snippets for operations that need publication.
7. Include snippets in Asciidoctor and run `test → asciidoctor` in CI.
8. Audit generated snippets to ensure no real session IDs are present.

**Completion criteria:** request cookies are sent properly; response cookies are verified for values and attributes; missing/deleted cookie cases are tested; REST Docs generates snippets under the right operations; documentation builds in CI without leaking secrets.

## Key Takeaways

MockMvc verifies cookies conveniently via **.cookie(...)** and **cookie()** matchers; REST Assured supports **.cookie(...)**, **.cookies(...)**, **getCookie(...)**, and `Set-Cookie` header checks. When documenting, use **requestCookies(...)** and **responseCookies(...)** alongside assertions so snippets accurately reflect HTTP behavior. Test missing, invalid, and expired cookie scenarios, and assert security attributes per the contract. Simulated tests do not fully prove cross-site browser behavior; add HTTPS browser tests whenever `Secure`/`SameSite` policies matter. Use dummy values, audit snippets, and wire tests into Asciidoctor/CI to maintain trustworthy documentation.

**References:** [Spring REST Docs Reference](https://docs.spring.io/spring-restdocs/reference/), [Spring REST Docs MockMvc API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/mockmvc/MockMvcRestDocumentation.html), [Spring REST Docs REST Assured API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/restassured/RestAssuredRestDocumentation.html), [Spring MockMvcResultMatchers API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/web/servlet/result/CookieResultMatchers.html), and [REST Assured Usage Guide](https://github.com/rest-assured/rest-assured/wiki/Usage).
