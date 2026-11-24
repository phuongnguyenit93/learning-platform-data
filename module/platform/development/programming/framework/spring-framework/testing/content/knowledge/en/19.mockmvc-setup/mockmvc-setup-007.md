# defaultRequest, alwaysExpect, and Shared Customizations

When a test suite uses `MockMvc`, many requests often share the same characteristics: the same `Accept` header, locale, context path, user information, or headers used for testing. Many tests also need to assert common conditions on every response, such as a successful status or a security header that must always be present. Repeating those settings in every `perform(...)` call makes tests verbose and prone to inconsistency.

Spring MVC Test lets you configure shared rules directly on `MockMvcBuilder`. Three key methods are:

- `defaultRequest(...)`: defines a default request inherited by every request sent through `MockMvc`.
- `alwaysExpect(...)`: registers a `ResultMatcher` that must be applied after every request.
- `alwaysDo(...)`: registers a `ResultHandler` executed after every request, commonly used to print request/response details or record diagnostic information.

In addition, the builder can register filters, `MockMvcConfigurer`s, and customizations for `DispatcherServlet`. These settings give every request using the same `MockMvc` a consistent test environment.

## 1. Configuring MockMvcBuilder Once

`MockMvc` is created from a builder. You can combine multiple configuration methods before calling `build()`:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultHandlers.print;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.Locale;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

class ApiControllerTests {

    @Autowired
    private WebApplicationContext webApplicationContext;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders
            .webAppContextSetup(webApplicationContext)
            .defaultRequest(get("/")
                .accept(MediaType.APPLICATION_JSON)
                .header("X-Test-Client", "mock-mvc")
                .locale(Locale.US))
            .alwaysExpect(status().isOk())
            .alwaysDo(print())
            .build();
    }
}
```

In the example, every request dispatched via `mockMvc` receives the declared default values. After the request completes, Spring applies the status matcher and invokes the handler to print result details. Tests do not have to repeat these shared settings in each test method.

The snippet illustrates how to compose the builder; in a complete test class, add the corresponding JUnit imports such as `@BeforeEach`, `@Test`, and the static assertions used.

## 2. Setting Default Requests with defaultRequest

`defaultRequest(RequestBuilder)` accepts a request builder as a template. Properties of the default request are applied to every request executed by that `MockMvc`. Individual requests still supply the URI and can declare values specific to the case under test.

Commonly configured settings include:

- `accept(...)` to set the media type accepted by the client.
- `contentType(...)` to set the content type of requests that have a body.
- `header(...)` to add common headers.
- `locale(...)` to set the request locale.
- `contextPath(...)`, `servletPath(...)`, or session/principal info when the test needs to simulate that environment.

For example, an internal API always expects JSON and test requests carry a header identifying the caller:

```java
mockMvc = MockMvcBuilders.webAppContextSetup(webApplicationContext)
    .defaultRequest(get("/")
        .accept(MediaType.APPLICATION_JSON)
        .header("X-Test-Client", "mock-mvc"))
    .build();
```

After that, tests only need to describe what is specific to each request:

```java
mockMvc.perform(get("/api/profile"))
    .andExpect(status().isOk());

mockMvc.perform(get("/api/orders"))
    .andExpect(status().isOk());
```

Both requests inherit `Accept: application/json` and `X-Test-Client: mock-mvc`. Each request's URI still comes from `get("/api/profile")` or `get("/api/orders")`.

### Specific Requests Can Override Default Values

When a test needs something different from the default, declare that value on the specific request. The following example uses the header and locale as controller inputs:

```java
import java.util.Locale;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

record RequestContext(String client, String language) {
}

@RestController
class RequestContextController {

    @GetMapping("/api/request-context")
    RequestContext requestContext(
            @RequestHeader("X-Test-Client") String client,
            Locale locale) {
        return new RequestContext(client, locale.toLanguageTag());
    }
}
```

With the default configuration from the previous section, a test can verify the default values are used:

```java
mockMvc.perform(get("/api/request-context"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.client").value("mock-mvc"))
    .andExpect(jsonPath("$.language").value("en-US"));
```

An individual request can override the header and locale:

```java
mockMvc.perform(get("/api/request-context")
        .header("X-Test-Client", "mobile-test")
        .locale(Locale.CANADA))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.client").value("mobile-test"))
    .andExpect(jsonPath("$.language").value("en-CA"));
```

The result shows that a specific request builder can supply its own settings when needed. Therefore, `defaultRequest` suits values that are genuinely shared; scenario-specific data should be placed directly in `perform(...)` so the test's intent stays clear.

### Notes on Choosing Default Values

Avoid putting every attribute into the default request. Only put values that nearly every request within that `MockMvc`'s scope truly needs. A few points to consider:

- Do not set a default `contentType` if the same `MockMvc` tests JSON requests, form requests, and bodyless requests.
- Do not set a shared session or principal if tests require different users or authentication states.
- Avoid defaults that make a test look as though it verified a condition that the test did not actually set intentionally.
- If endpoint groups have different default rules, create separate builders or `MockMvc` setups per group rather than one overly broad shared configuration.

## 3. Applying Matchers to Every Request with alwaysExpect

`alwaysExpect(ResultMatcher)` registers a matcher executed for every request. This is the right place to verify invariant conditions within the scope of a `MockMvc`.

For example, if every test in a group only calls successful endpoints, you can apply `200 OK` status once:

```java
mockMvc = MockMvcBuilders.webAppContextSetup(webApplicationContext)
    .alwaysExpect(status().isOk())
    .build();
```

Individual tests can still add their own assertions:

```java
mockMvc.perform(get("/api/profile"))
    .andExpect(jsonPath("$.active").value(true));

mockMvc.perform(get("/api/settings"))
    .andExpect(jsonPath("$.theme").value("dark"));
```

Every request must satisfy `status().isOk()` before its specific assertions finish. If a response returns another status, the shared matcher fails the test even if the test did not call `andExpect(status()...)` directly.

Other shared conditions might include a header always added by a filter, the content type of a JSON API, or a security condition applying to every endpoint in the test group. For example:

```java
mockMvc = MockMvcBuilders.webAppContextSetup(webApplicationContext)
    .alwaysExpect(header().exists("X-Content-Type-Options"))
    .build();
```

The matcher above only makes sense if the application genuinely guarantees that header appears on every response in the test scope. Choose conditions with clear business or configuration meaning, avoiding turning a test assumption into a blanket rule that does not hold for all endpoints.

### Do Not Use a Shared Matcher for Intentionally Different Responses

A test suite may verify `200`, `400`, `401`, `404`, or `500`. If you attach `alwaysExpect(status().isOk())` to a `MockMvc` used for all cases, error-checking tests will fail due to the shared matcher.

There are three ways to handle this:

1. Register the shared matcher only for a group of requests where the condition always holds.
2. Create separate `MockMvc` setups for different endpoint groups or scenario groups.
3. Keep the status assertion in each test if status varies by scenario.

`alwaysExpect` should describe a genuinely shared contract, not the expected outcome of a single test.

## 4. Running a Shared ResultHandler with alwaysDo

`alwaysDo(ResultHandler)` registers an action invoked after every request. A common usage is `print()` to print the request, handler, model, exception, and response while debugging:

```java
import static org.springframework.test.web.servlet.result.MockMvcResultHandlers.print;

mockMvc = MockMvcBuilders.webAppContextSetup(webApplicationContext)
    .alwaysDo(print())
    .build();
```

Unlike `alwaysExpect`, `alwaysDo` performs an action on the result. It does not replace assertions, and printing the response by itself does not fail a test when data is wrong.

The two methods can be combined:

```java
mockMvc = MockMvcBuilders.webAppContextSetup(webApplicationContext)
    .alwaysExpect(status().isOk())
    .alwaysDo(print())
    .build();
```

With that, every request has its status checked and its details printed. In large test suites, printing every request can produce a huge amount of logs. Enable `alwaysDo(print())` only when investigating or when log volume remains readable; otherwise, use `andDo(print())` on the specific test you need to inspect.

## 5. Registering Filters and Shared Configuration

`MockMvcBuilder` also lets you register filters so they are applied during request processing. This is useful when testing filters handling encoding, correlation IDs, CORS, or authentication.

```java
mockMvc = MockMvcBuilders.webAppContextSetup(webApplicationContext)
    .addFilters(requestIdFilter, characterEncodingFilter)
    .defaultRequest(get("/").accept(MediaType.APPLICATION_JSON))
    .build();
```

Filters registered on the builder belong to that `MockMvc`'s pipeline. Pay attention to filter order if behavior depends on execution sequence. If the application uses Spring Security, you can apply Spring Security Test's integration setup:

```java
import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;

mockMvc = MockMvcBuilders.webAppContextSetup(webApplicationContext)
    .apply(springSecurity())
    .build();
```

This example requires the project to have Spring Security and its test dependency. `springSecurity()` registers the security filter chain integration and Spring Security's testing support. Add this setup only when the application actually uses Spring Security.

The builder also provides `addDispatcherServletCustomizer(...)` when you need to adjust the configuration of the `DispatcherServlet` created for `MockMvc`. This is a lower-level customization; use it only when a servlet setting is part of the behavior under test. Normal MVC configuration should reside in the application context so tests reflect the application configuration.

## 6. Combining Customizations into an Intentional Setup

A shared configuration typically combines default requests, shared matchers, and filters:

```java
mockMvc = MockMvcBuilders.webAppContextSetup(webApplicationContext)
    .addFilters(requestIdFilter)
    .defaultRequest(get("/")
        .accept(MediaType.APPLICATION_JSON)
        .header("X-Test-Client", "mock-mvc"))
    .alwaysExpect(status().isOk())
    .build();
```

When reading this setup, three scopes stand out clearly:

| Configuration | Effect | Question It Answers |
|---|---|---|
| `addFilters(...)` | Requests pass through registered filters | Do the filters participate in request processing? |
| `defaultRequest(...)` | Requests inherit default attributes | Which headers, locale, or attributes does every request start with? |
| `alwaysExpect(...)` | Every response is checked by a shared matcher | Which condition must hold for all requests in the group? |
| `alwaysDo(...)` | Every result is handled by a result handler | Which information should be recorded or displayed after every request? |
| `apply(...)` | Applies a `MockMvcConfigurer` | Which testing integration needs to be attached to the builder? |

Keep this configuration close to the test class or a shared factory so readers clearly see which rules `MockMvc` applies. If the configuration is shared across multiple test classes, place it in a test configuration class or a `MockMvc` factory method whose name describes its scope of use.

## 7. Common Configuration Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| A request receives an unexpected header or locale | `defaultRequest` sets a shared value | Check the builder and overriding settings in `perform(...)` |
| Tests checking `400` or `404` keep failing | `alwaysExpect(status().isOk())` applies to error requests too | Use a separate builder or remove the shared status matcher |
| Test logs are too verbose | `alwaysDo(print())` prints every request | Switch to `andDo(print())` on the test being debugged |
| Filter does not run in MockMvc | Filter was not registered on the builder or not configured in the test context | Use `addFilters(...)` or the matching integration setup |
| Default values couple tests together | One builder holds too many settings for disparate scenarios | Split configurations by test group sharing the same contract |
| Test assumes response was verified because logs were printed | `alwaysDo` only processes the result; it does not assert correctness | Add `alwaysExpect` or `andExpect` |

When a test fails, identify whether a shared matcher or an individual assertion caused the failure. Separating shared setup from per-scenario assertions helps errors pinpoint the exact violated condition.

## 8. Workflow for Choosing Configuration

1. Identify request attributes that are truly identical across every test in a group. Put those attributes in `defaultRequest`.
2. Identify response conditions that must hold across every request in the group. Register them with `alwaysExpect`.
3. Register `alwaysDo` only when an action is needed after every request, such as printing details for debugging.
4. Add filters or `MockMvcConfigurer` when the test pipeline requires them; pay attention to ordering and corresponding dependencies.
5. Separate builders when test groups differ in status expectations, authentication, content type, or request environment.

`defaultRequest` standardizes inputs, `alwaysExpect` verifies the shared output contract, and `alwaysDo` performs an action after each request. Filter and configurer customizations add behavior to the MockMvc pipeline. Using each mechanism within its proper scope keeps tests concise while making clear which rules apply to the entire request group.
