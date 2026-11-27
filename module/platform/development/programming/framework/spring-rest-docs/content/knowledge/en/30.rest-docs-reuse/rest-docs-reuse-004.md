# Reusing header and cookie descriptors

## 1. Why reuse header and cookie descriptors?

Spring REST Docs generates verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. Tests send requests, verify responses, and use descriptors to document headers, cookies, payloads, parameters, and hypermedia links. The generated snippets are then compiled into Asciidoctor/Markdown and integrated into the build and CI.

Many endpoints share several common headers and cookies. For example:

- Requests often send Accept to declare the expected media type.
- Requests with a JSON body send Content-Type.
- APIs protected by a bearer token include an Authorization header.
- Multilingual APIs may use Accept-Language.
- Session-based applications may receive a JSESSIONID cookie.
- Responses may return Cache-Control, ETag, Set-Cookie, or a correlation header.

If the same descriptors are redeclared across dozens of tests, descriptions easily drift apart. Centralizing shared descriptors in helpers keeps documentation consistent and reduces duplication.

## 2. HeaderDescriptor and CookieDescriptor

Spring REST Docs provides specialized descriptors for each type of HTTP metadata:

| Descriptor | Purpose | Creation API |
| --- | --- | --- |
| HeaderDescriptor | Describes an HTTP header | headerWithName("...") |
| CookieDescriptor | Describes a cookie | cookieWithName("...") |

Descriptors can declare a description, optional/ignored status, and additional attributes. They are passed to the corresponding snippet methods:

| Snippet API | Scope |
| --- | --- |
| requestHeaders(...) | Headers sent by the client |
| responseHeaders(...) | Headers returned by the server |
| requestCookies(...) | Cookies sent by the client |
| responseCookies(...) | Cookies returned by the server |

Headers and cookies are distinct structures. Cookies are sent in a request via the Cookie header, while the server sends cookies via Set-Cookie. Spring REST Docs provides cookie descriptors to document cookies by name and attributes; using a header descriptor for the entire Cookie header does not replace cookie descriptors when the goal is to document individual cookies.

## 3. Declaring shared descriptors for request headers

Suppose an API commonly receives these headers:

- Accept: media type the client wants to receive.
- Content-Type: media type of the request body.
- Authorization: bearer token used for authentication.
- X-Correlation-ID: correlation ID for tracing the request.

Create a helper returning the standard descriptors:

~~~java
import org.springframework.restdocs.headers.HeaderDescriptor;

import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;

final class ApiHeaderDescriptors {

    private ApiHeaderDescriptors() {
    }

    static HeaderDescriptor[] commonRequestHeaders() {
        return new HeaderDescriptor[] {
                headerWithName("Accept")
                        .description("Media type accepted by the client"),
                headerWithName("Content-Type")
                        .optional()
                        .description("Media type of the request body"),
                headerWithName("Authorization")
                        .description("Bearer token used for authentication"),
                headerWithName("X-Correlation-ID")
                        .description("Request correlation ID")
        };
    }
}
~~~

Each call to commonRequestHeaders() creates a new descriptor array. You can use the helper across multiple operations:

~~~java
document("orders-create",
        requestHeaders(ApiHeaderDescriptors.commonRequestHeaders()),
        requestFields(orderRequestFields()));

document("customers-update",
        requestHeaders(ApiHeaderDescriptors.commonRequestHeaders()),
        requestFields(customerRequestFields()));
~~~

Both operations share consistent phrasing for the headers required by the API. When terminology or header policies change, update the helper and rerun the documentation tests to regenerate uniform snippets.

Only include in snippets the headers that are actually present in the request. If an endpoint does not send Content-Type because it has no body, do not include a required descriptor for that header in the operation.

## 4. Reusing response header descriptors

Request headers and response headers have different semantics, so separate helpers should be defined. For example, a response has Content-Type, Cache-Control, ETag, and X-Correlation-ID:

~~~java
import org.springframework.restdocs.headers.HeaderDescriptor;

import static org.springframework.restdocs.headers.HeaderDocumentation.headerWithName;

final class ApiResponseHeaderDescriptors {

    private ApiResponseHeaderDescriptors() {
    }

    static HeaderDescriptor[] commonResponseHeaders() {
        return new HeaderDescriptor[] {
                headerWithName("Content-Type")
                        .description("Media type of the response"),
                headerWithName("Cache-Control")
                        .description("Caching policy of the response"),
                headerWithName("ETag")
                        .description("Validator representing the representation version"),
                headerWithName("X-Correlation-ID")
                        .description("Correlation ID for tracing the request")
        };
    }
}
~~~

Use in an operation:

~~~java
document("orders-get",
        responseHeaders(
                ApiResponseHeaderDescriptors.commonResponseHeaders()));
~~~

Do not reuse a response descriptor array for requests just because the header names match. Content-Type on a request describes the body format sent by the client; on a response, it describes the body format returned by the server.

## 5. Shared cookie descriptors

In a session-based application, many requests may send a JSESSIONID cookie. Some applications also use a locale, remember-me, or CSRF cookie. Create a helper for request cookies:

~~~java
import org.springframework.restdocs.cookies.CookieDescriptor;

import static org.springframework.restdocs.cookies.CookieDocumentation.cookieWithName;

final class ApiCookieDescriptors {

    private ApiCookieDescriptors() {
    }

    static CookieDescriptor[] commonRequestCookies() {
        return new CookieDescriptor[] {
                cookieWithName("JSESSIONID")
                        .description("Client login session identifier"),
                cookieWithName("locale")
                        .optional()
                        .description("Display language selected by the client")
        };
    }
}
~~~

When documenting a request:

~~~java
document("account-get",
        requestCookies(ApiCookieDescriptors.commonRequestCookies()));
~~~

The JSESSIONID cookie is documented as required in this operation; locale is optional. The required/optional state must match the endpoint's contract and is not necessarily identical across all APIs.

### Response cookies

If the server creates a session or updates a cookie, you can define a separate response cookie set:

~~~java
static CookieDescriptor[] commonResponseCookies() {
    return new CookieDescriptor[] {
            cookieWithName("JSESSIONID")
                    .description("Session cookie issued by the server"),
            cookieWithName("locale")
                    .optional()
                    .description("Cookie storing the language preference")
    };
}
~~~

And use it:

~~~java
document("login",
        responseCookies(ApiCookieDescriptors.commonResponseCookies()));
~~~

Only document a response cookie if the actual response includes the corresponding cookie, typically sent via Set-Cookie. Do not assume every response reissues a session cookie.

## 6. Combining shared descriptors with operation-specific descriptors

An endpoint may use the shared header set and add a specific header, such as If-Match when updating a resource with optimistic locking.

You can create a helper to combine descriptors:

~~~java
import java.util.Arrays;
import java.util.stream.Stream;

static HeaderDescriptor[] withAdditionalHeaders(
        HeaderDescriptor[] common,
        HeaderDescriptor... specific) {
    return Stream.concat(Arrays.stream(common), Arrays.stream(specific))
            .toArray(HeaderDescriptor[]::new);
}
~~~

Usage:

~~~java
requestHeaders(withAdditionalHeaders(
        ApiHeaderDescriptors.commonRequestHeaders(),
        headerWithName("If-Match")
                .description("ETag of the version read by the client")));
~~~

If you need to combine shared cookies with specific cookies, the same approach can be applied with CookieDescriptor[]. Only create an array-merging abstraction if the project has enough operations that genuinely need it; for one or two endpoints, declaring them directly is often easier to read.

## 7. Complete MockMvc example

The following example illustrates a request sending headers/cookies and a response returning headers/cookies. Assume the application has a session-based /api/account endpoint and the headers/cookies listed in the descriptors are actually sent/returned.

~~~java
import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.headers.HeaderDocumentation.requestHeaders;
import static org.springframework.restdocs.headers.HeaderDocumentation.responseHeaders;
import static org.springframework.restdocs.cookies.CookieDocumentation.requestCookies;
import static org.springframework.restdocs.cookies.CookieDocumentation.responseCookies;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs
class AccountDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void getAccountDocumentsReusableHeadersAndCookies() throws Exception {
        mockMvc.perform(get("/api/account")
                        .accept(MediaType.APPLICATION_JSON)
                        .header("Authorization", "Bearer test-token")
                        .header("X-Correlation-ID", "test-correlation-001")
                        .cookie(new Cookie("JSESSIONID", "session-fixture"),
                                new Cookie("locale", "vi")))
                .andExpect(status().isOk())
                .andDo(document("account-get",
                        requestHeaders(ApiHeaderDescriptors.commonRequestHeaders()),
                        requestCookies(ApiCookieDescriptors.commonRequestCookies()),
                        responseHeaders(ApiResponseHeaderDescriptors.commonResponseHeaders()),
                        responseCookies(ApiCookieDescriptors.commonResponseCookies())));
    }
}
~~~

The example must be adapted to your application's actual response and session configuration. If the application does not use session cookies or does not return ETag, Cache-Control, or response cookies in this operation, adjust the helpers/descriptors accordingly or omit those snippets from the operation.

Cookie/header values in documentation should be dummy fixtures. Never record valid session IDs or bearer tokens from a real runtime environment.

## 8. Required, optional, and ignored when reusing

Descriptors can carry optional() or ignored() state. Consider these states when reusing:

- Use a required descriptor when the header/cookie must be present according to the operation contract.
- Use optional() when it is valid for the header/cookie to be absent.
- Use ignored() when intentionally excluding the header/cookie from the snippet and descriptor checks.

Do not create a shared descriptor with optional() called just because one endpoint allows absence, and then reuse that exact descriptor for another endpoint that requires the header.

A safe approach is using factories that create fresh descriptors:

~~~java
static HeaderDescriptor correlationIdHeader() {
    return headerWithName("X-Correlation-ID")
            .description("Request correlation ID");
}

static HeaderDescriptor optionalTraceHeader() {
    return headerWithName("X-Trace-Parent")
            .optional()
            .description("Trace information if sent by the client");
}
~~~

Required operations use correlationIdHeader(); operations that allow missing trace info use optionalTraceHeader(). That way, descriptor state is tied to explicit intent.

## 9. Sharing descriptors via helpers or utility classes

| Organization | When suitable | Notes |
| --- | --- | --- |
| Static factory methods | Multiple tests in the same module | Simple, readable |
| Utility class per API group | Multiple endpoint groups sharing headers/cookies | Clearly separate request and response |
| Test fixture module | Multiple modules needing the same descriptions | Must place fixture on the test runtime classpath |
| Profile-based descriptor builder | APIs with public, internal, admin groups | Avoid merging overly broad descriptor sets |

Example source layout:

~~~text
src/test/java/
└── com/example/docs/
    ├── descriptors/
    │   ├── ApiHeaderDescriptors.java
    │   ├── ApiResponseHeaderDescriptors.java
    │   └── ApiCookieDescriptors.java
    └── tests/
        ├── AccountDocumentationTest.java
        └── OrderDocumentationTest.java
~~~

Do not place test-only helpers into production packages if the application does not need them at runtime. If multiple modules need to share them, package helpers into proper test fixtures instead of creating cross-module dependencies on another module's test sources.

## 10. Cookies and headers are not places to store secrets in documentation

Headers such as Authorization, Cookie, and Set-Cookie can contain tokens or session identifiers. When documenting requests/responses, check the data written to snippets:

- Use dummy tokens or sanitized values.
- Remove or replace sensitive headers using operation preprocessors if necessary.
- Do not use real session cookies copied from a browser or staging/production environment.
- Inspect http-request, http-response, request-headers, and cookie snippets before committing.

The purpose of descriptors is to document header/cookie names and meanings. Secret values do not need to be exposed to explain the API contract.

## 11. Common errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Header descriptor does not match request | Header was not actually sent or name is misspelled | Check request fixture and header name |
| Response header not found | Endpoint does not return that header in the operation | Verify actual response before using a required descriptor |
| Cookie descriptor does not find cookie | Cookie is missing in request/response or test setup is wrong | Check Cookie/Set-Cookie and use the right requestCookies/responseCookies |
| An endpoint unintentionally treats header as optional | Reused a descriptor that already called optional() | Create separate factories for required and optional states |
| Request/response header descriptions mixed up | Shared description text in the wrong direction | Separate request header and response header helpers |
| Tests duplicate varied descriptions | Descriptors redeclared in every operation | Move truly shared parts into a helper |
| Snippet contains real session/token | Fixture uses live environment data | Use dummy fixtures or preprocess before generating documentation |
| Build cannot find helper in another module | Test fixture is not on the test runtime classpath | Add the test-fixtures dependency or declare the helper locally |

When a test fails, inspect the actual HTTP operation first. Descriptors must reflect the headers/cookies being sent or returned by the request; a reuse helper does not cause a header to appear in the HTTP message automatically.

## 12. Practice exercise

1. Create an ApiHeaderDescriptors helper with shared API request headers.
2. Create a separate helper for response headers and verify which headers each endpoint actually returns.
3. Create ApiCookieDescriptors for request cookies and response cookies.
4. Reuse the helpers across two different documentation tests; verify descriptions remain consistent.
5. Add a specific If-Match header for an update endpoint and combine it with the shared descriptor set.
6. Create required and optional descriptor variants; confirm endpoints with different contracts do not mix up states.
7. Check generated snippets to ensure they contain no real bearer tokens or session IDs.

**Completion criteria:** distinguish HeaderDescriptor and CookieDescriptor; reuse via helpers/factories; separate request and response descriptors; combine shared and specific descriptors; handle required/optional per contract; protect sensitive values in snippets.

## 13. Pre-commit checklist

- [ ] Header/cookie descriptors are properly classified as request or response.
- [ ] Shared descriptions are placed in clearly named helpers.
- [ ] Descriptor factories return the state matching the operation.
- [ ] An optional descriptor is never reused for an operation requiring it.
- [ ] Cookies are documented with cookie descriptors when individual cookies need documentation.
- [ ] Descriptors are only included in an operation if the header/cookie is actually present in the message.
- [ ] Authorization/Cookie/Set-Cookie values use dummy fixtures or have been sanitized.
- [ ] Tests are executed to regenerate request/response header and cookie snippets.
- [ ] Asciidoctor/Markdown build succeeds with the new snippets.

**Remember:** HeaderDescriptor and CookieDescriptor help document headers and cookies consistently. Creating helpers or factories for shared metadata groups, separating requests from responses, and creating fresh descriptors per each operation's required/optional state keeps Spring REST Docs documentation maintainable while accurately reflecting real HTTP messages.
