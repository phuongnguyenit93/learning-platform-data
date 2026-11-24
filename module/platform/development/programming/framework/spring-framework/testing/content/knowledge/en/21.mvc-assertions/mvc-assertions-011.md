# ResultHandler, print, and Diagnostic Information on Failure

**Context:** Spring Framework Testing → MVC Result Assertions.

A MockMvc test typically ends with assertions on HTTP status, headers, response body, or model. When an assertion fails, merely knowing that the actual result differed from the expected one is often not enough to find the root cause. You need to observe the request that was sent, the selected handler, any resolved exception, the actual response, and secondary state such as redirects, flash attributes, or async processing.

Spring Test provides three complementary mechanisms:

- **ResultMatcher:** asserts a condition on the request processing outcome.
- **ResultHandler:** observes or processes the outcome after the request has executed, such as printing diagnostic output.
- **MvcResult:** gives direct access to the request, response, handler, exception, model, and related data.

Understanding when each mechanism runs helps you place print statements in the right spot, capture the data needed for investigation, and avoid losing diagnostics when the first assertion throws an error.

## 1. What Does a MockMvc Request Outcome Include?

MockMvc simulates a request flowing through Spring MVC in a test environment. Calling **perform** executes the request and returns a **ResultActions** object so the test can continue asserting or handling the outcome.

Basic flow:

~~~text
MockMvc.perform(request)
        |
        v
Spring MVC processes the request
        |
        v
MvcResult is created
        |
        +---- ResultMatcher: checks conditions
        |
        +---- ResultHandler: observes / prints / saves result
        |
        +---- andReturn(): retrieves MvcResult for deeper inspection
~~~

Each component has a distinct role:

| Component | Role | Example |
|---|---|---|
| ResultActions | Chain of operations on the request outcome | andExpect, andDo, andReturn |
| ResultMatcher | Verifies whether the outcome matches expectations | status().isOk(), jsonPath(...) |
| ResultHandler | Performs an action with the outcome | print(), logging, collecting data |
| MvcResult | Post-processing request and response data | getRequest(), getResponse(), getResolvedException() |

Do not confuse ResultHandler with ResultMatcher. A matcher answers "is the outcome correct?", whereas a handler answers "what should be done with this outcome?". A handler can print data, save it, or forward it to diagnostic tools. Assertions should always be expressed explicitly with matchers so failure messages clearly pinpoint which condition failed.

## 2. ResultActions and Execution Order

### 2.1. Three Key Methods

After calling perform, ResultActions exposes three primary methods:

~~~java
ResultActions actions = mockMvc.perform(get("/orders/42"));

actions.andExpect(status().isOk());
actions.andDo(print());

MvcResult result = actions.andReturn();
~~~

- **andExpect(matcher):** executes a ResultMatcher on MvcResult. If the condition is not met, the matcher typically throws AssertionError and the test fails.
- **andDo(handler):** executes a ResultHandler on MvcResult. Handlers are commonly used for printing or collecting information.
- **andReturn():** returns the MvcResult so the test can read request, response, handler, or exception details.

Operations can be chained:

~~~java
mockMvc.perform(get("/orders/42"))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.id").value(42))
        .andDo(print());
~~~

This chain reads cleanly: send the request, verify status, verify content type, verify JSON data, then print the outcome.

### 2.2. Why Placing print After Assertions May Not Run

These methods execute as the chain is invoked. If an **andExpect** fails, it throws AssertionError right at that step. Subsequent operations in the chain are not executed.

Example:

~~~java
mockMvc.perform(get("/orders/404"))
        .andExpect(status().isOk())
        .andDo(print());
~~~

If the actual response is 404, the test stops at **status().isOk()**. The trailing **andDo(print())** never gets a chance to run. This is a common reason tests fail without producing the diagnostic output the author expected.

If you want to print before assertions run, place the handler right after perform:

~~~java
mockMvc.perform(get("/orders/404"))
        .andDo(print())
        .andExpect(status().isOk());
~~~

Once the request has executed and ResultActions is returned, print runs before the following matchers. If a subsequent assertion fails, the output has already been generated.

When you want to print every request executed through a MockMvc instance, configure **alwaysDo** on the builder. This is helpful when investigating a suite of tests with many requests.

## 3. Printing Results with MockMvcResultHandlers.print()

### 3.1. Basic Usage

Spring Test provides **MockMvcResultHandlers.print()**, typically imported statically:

~~~java
import static org.springframework.test.web.servlet.result.MockMvcResultHandlers.print;
~~~

Usage with MockMvc:

~~~java
mockMvc.perform(get("/orders/42"))
        .andDo(print())
        .andExpect(status().isOk());
~~~

The output of print can display information such as:

- HTTP method and URI.
- Request parameters, headers, and body.
- Handler selected to process the request.
- Exception resolved by Spring, if any.
- Model and flash attributes, if present.
- HTTP status, response headers, and response body.
- Async-related details when the request uses asynchronous processing.

The exact details shown depend on the request type and what data actually exists in MvcResult. For example, a request with no body has empty request content; a REST endpoint that does not use model/view has no meaningful model/view details.

### 3.2. Printing Every Request with alwaysDo

If you want every request through MockMvc to be printed, register the handler on the builder:

~~~java
MockMvc mockMvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .alwaysDo(print())
        .build();
~~~

With standalone setup:

~~~java
MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new OrderController())
        .alwaysDo(print())
        .build();
~~~

**alwaysDo** applies the ResultHandler to every request executed through the MockMvc created from that builder. The handler is invoked while constructing the result, before the test continues calling matchers on ResultActions. Thus, the output is still printed even if a later assertion fails.

This is a good option while investigating issues when you want consistent output. In large test suites, printing every request can produce excessive logs and make CI output hard to read. Once you identify the cause, you can remove alwaysDo or keep print only on tests needing diagnostics.

### 3.3. Printing per Test or per Request

You do not have to enable print across all of MockMvc. You can attach the handler only to the suspect request:

~~~java
@Test
void showsDiagnosticOutputForMissingOrder() throws Exception {
    mockMvc.perform(get("/orders/404"))
            .andDo(print())
            .andExpect(status().isNotFound());
}
~~~

This keeps output focused on the scenario under investigation. If an assertion checks that status itself, place print before the assertion as shown above.

If a test performs multiple requests, each request can attach its own handler so you know which output belongs to which step.

## 4. Writing a Custom ResultHandler

**ResultHandler** is a functional interface accepting **MvcResult**. You can use a lambda to record specific details instead of printing the entire result.

Example:

~~~java
ResultHandler diagnosticHandler = result -> {
    MockHttpServletRequest request = result.getRequest();
    MockHttpServletResponse response = result.getResponse();

    System.out.println("Request: "
            + request.getMethod() + " " + request.getRequestURI());

    System.out.println("Handler: " + result.getHandler());
    System.out.println("Status: " + response.getStatus());
    System.out.println("Content-Type: " + response.getContentType());
    System.out.println("Response body: " + response.getContentAsString());

    Exception resolvedException = result.getResolvedException();
    if (resolvedException != null) {
        System.out.println("Resolved exception: "
                + resolvedException.getClass().getName()
                + ": " + resolvedException.getMessage());
    }
};
~~~

Attach the handler to a request:

~~~java
mockMvc.perform(get("/orders/404"))
        .andDo(diagnosticHandler)
        .andExpect(status().isNotFound());
~~~

This example uses the mock request and mock response APIs. In a real handler, you can use a logger instead of System.out to control log levels and formatting. Methods reading the body can throw encoding exceptions; the ResultHandler interface allows exceptions to be thrown while reading data.

### 4.1. Printing Only Needed Fields

You do not always need to print the full request and response. You can create a small handler:

~~~java
ResultHandler statusAndException = result -> {
    int status = result.getResponse().getStatus();
    Exception exception = result.getResolvedException();

    System.out.println("HTTP status = " + status);

    if (exception != null) {
        exception.printStackTrace();
    }
};
~~~

A small handler is handy when tests run frequently and you only need a few fields to spot failures. A shared handler can take a scenario name or correlation ID from the test and log it alongside the status and URI.

### 4.2. Observation Handler vs. Assertion Matcher

You can write a lambda directly as a ResultHandler:

~~~java
mockMvc.perform(get("/orders/42"))
        .andDo(result -> {
            System.out.println(
                    result.getResponse().getStatus()
            );
        })
        .andExpect(status().isOk());
~~~

If you want to assert the status, use a ResultMatcher:

~~~java
mockMvc.perform(get("/orders/42"))
        .andExpect(result ->
                assertThat(result.getResponse().getStatus())
                        .isEqualTo(200));
~~~

The two lambdas look similar, but their purposes differ. A handler performs an observation action; a matcher asserts a condition and must fail the test when the condition is not satisfied.

Avoid hiding important assertions inside a handler just to reuse a lambda. Keeping them as matchers makes the contract explicit and ensures failures report the exact unmet condition.

## 5. Inspecting MvcResult for Deeper Diagnostics

### 5.1. Obtaining MvcResult

Use **andReturn()** to retrieve the result after the request has executed:

~~~java
MvcResult result = mockMvc.perform(get("/orders/42"))
        .andDo(print())
        .andReturn();
~~~

From there you can inspect the request and response directly:

~~~java
MockHttpServletRequest request = result.getRequest();
MockHttpServletResponse response = result.getResponse();

assertThat(request.getMethod()).isEqualTo("GET");
assertThat(request.getRequestURI()).isEqualTo("/orders/42");
assertThat(response.getStatus()).isEqualTo(200);
~~~

You can combine andReturn with earlier matchers:

~~~java
MvcResult result = mockMvc.perform(get("/orders/42"))
        .andExpect(status().isOk())
        .andReturn();

String body = result.getResponse().getContentAsString();
assertThat(body).contains("\"id\":42");
~~~

Note that if a matcher fails before andReturn, the line retrieving the result will not execute. When you need to capture output even when an assertion may fail, use a handler before the assertions or configure alwaysDo.

### 5.2. Important Information in MvcResult

| Method | Information |
|---|---|
| getRequest() | The MockHttpServletRequest that was sent |
| getResponse() | The MockHttpServletResponse that was received |
| getHandler() | The selected handler, typically a HandlerMethod in Spring MVC |
| getInterceptors() | Interceptors associated with the handler |
| getResolvedException() | Exception handled by a HandlerExceptionResolver |
| getModelAndView() | ModelAndView if the request produced a view outcome |
| getFlashMap() | Flash attributes saved during a redirect |
| getAsyncResult() | Result of an async request once ready |
| getAsyncResult(timeout) | Waits for the async result within the specified timeout |

Not every method has data on every request. For instance, REST endpoints typically do not produce a ModelAndView; non-redirect requests typically have no flash attributes.

### 5.3. Identifying the Selected Controller Method

You can inspect the handler:

~~~java
MvcResult result = mockMvc.perform(get("/orders/42"))
        .andDo(print())
        .andReturn();

Object handler = result.getHandler();
System.out.println("Selected handler: " + handler);
~~~

If the handler is a **HandlerMethod**, you can inspect its bean and method:

~~~java
if (result.getHandler() instanceof HandlerMethod handlerMethod) {
    System.out.println("Controller bean: "
            + handlerMethod.getBeanType().getName());
    System.out.println("Controller method: "
            + handlerMethod.getMethod().toGenericString());
}
~~~

This is helpful when multiple mappings look similar, multiple controllers handle a group of URLs, or a test hits the wrong endpoint. If the handler is null, the request may never have mapped to a controller, such as failing during handler mapping or an earlier component.

### 5.4. Inspecting the Resolved Exception

If an exception was handled by a **HandlerExceptionResolver**, MvcResult can expose it via getResolvedException():

~~~java
MvcResult result = mockMvc.perform(get("/orders/404"))
        .andDo(print())
        .andReturn();

Exception exception = result.getResolvedException();

assertThat(exception)
        .isInstanceOf(OrderNotFoundException.class);
~~~

This confirms that the controller actually threw the expected exception type while also checking that advice or a resolver converted it into a response.

Distinguish resolved exceptions from unhandled exceptions. If no MVC resolver handles an exception, perform may throw ServletException or a related exception directly during execution. In that case the test does not receive a normal MvcResult to call getResolvedException(); inspect the thrown exception and its stack trace instead.

### 5.5. Checking Model and Flash Attributes

For view-returning controllers:

~~~java
MvcResult result = mockMvc.perform(get("/orders"))
        .andExpect(status().isOk())
        .andReturn();

ModelAndView modelAndView = result.getModelAndView();

assertThat(modelAndView).isNotNull();
assertThat(modelAndView.getViewName()).isEqualTo("orders/list");
assertThat(modelAndView.getModel()).containsKey("orders");
~~~

For redirects with flash attributes:

~~~java
MvcResult result = mockMvc.perform(post("/orders")
                .param("customerName", "An"))
        .andExpect(status().is3xxRedirection())
        .andExpect(redirectedUrl("/orders"))
        .andReturn();

assertThat(result.getFlashMap())
        .containsEntry("message", "Order created");
~~~

Flash attributes carry data across a redirect. Reading them from MvcResult verifies that notification messages or temporary state were set.

## 6. Diagnosing Step by Step Across Request and Response

When a test fails, read diagnostics in order from the start of the request to the response. This identifies whether the fault is in mapping, binding, controller logic, exception handling, or serialization.

### 6.1. Request

Check:

- Is the HTTP method right?
- Are the URI and path variables right?
- Are query parameters complete and named properly?
- Does Content-Type match the request body?
- Does Accept match the expected response type?
- Were authentication, locale, or business headers sent?
- Does the request body have valid JSON/XML and the expected DTO structure?

For example, a JSON endpoint can fail if the test forgets contentType:

~~~java
mockMvc.perform(post("/orders")
                .content("""
                        {
                          "customerName": "An"
                        }
                        """))
        .andExpect(status().isCreated());
~~~

If the endpoint requires application/json, a request without Content-Type may prevent Spring from finding a matching converter. Fix the test:

~~~java
mockMvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {
                          "customerName": "An"
                        }
                        """))
        .andExpect(status().isCreated());
~~~

### 6.2. Handler Mapping

If the response is 404 or handler is null, check:

- Does the URL match @RequestMapping, @GetMapping, or @PostMapping?
- Does the HTTP method match?
- Do path variables match the pattern?
- Is the controller registered in the application context?
- Does component scanning cover the controller package?
- Does standalone setup pass the right controller to the builder?
- Is a context path or servlet path altering the URL?

A request can return 404 because no handler was found, or because the controller/advice intentionally returned 404 for a missing resource. Checking the handler and exception distinguishes these two cases.

### 6.3. Binding and Message Conversion

If the status is 400 or 415, inspect the request content type, body, parameters, and related exception.

Common indicators:

| Symptom | Area to Inspect |
|---|---|
| 415 Unsupported Media Type | Content-Type and whether an HttpMessageConverter supports that media type |
| 406 Not Acceptable | Accept header and converter capability to write the response |
| 400 Bad Request | Deserialization, type conversion, data binding, or validation |
| MethodArgumentTypeMismatchException | Query/path parameter conversion |
| HttpMessageNotReadableException | Reading request body, invalid JSON, or mismatched data types |
| MethodArgumentNotValidException | Bean Validation on the request object |

Do not assume every HTTP 400 is a validation error. Malformed JSON can be rejected before the DTO is constructed; a query parameter that fails to convert to an enum can also produce a 400 error.

### 6.4. Controller and Exception Handling

If the handler is right but the response is unexpected, check:

- Was the controller actually invoked?
- What did the controller's dependencies return?
- Was any exception thrown?
- Did a resolver handle the exception?
- Which ControllerAdvice was chosen?
- Did multiple advice beans or handlers match?
- Were the response status and body constructed according to the contract?

You can use getResolvedException to see which exception was resolved. If there is no resolved exception yet the response is an error, the controller may have explicitly returned a ResponseEntity or another component may have produced it.

### 6.5. Response

Inspect the following properties:

~~~java
MockHttpServletResponse response = result.getResponse();

int status = response.getStatus();
String contentType = response.getContentType();
String location = response.getHeader(HttpHeaders.LOCATION);
String body = response.getContentAsString();
~~~

Check status, content type, headers, body, and encoding. For redirects, check Location. For JSON responses, verify key fields and values with jsonPath. For file or binary responses, do not coerce the content into a string to print as JSON.

## 7. Writing ResultMatchers with Clear Failure Messages

Spring provides many built-in matchers:

~~~java
mockMvc.perform(get("/orders/42"))
        .andExpect(status().isOk())
        .andExpect(header().exists(HttpHeaders.ETAG))
        .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.id").value(42))
        .andExpect(jsonPath("$.status").value("PAID"));
~~~

These matchers typically produce clearer failure messages than grabbing the response body and comparing strings with a generic assertion.

You can write a custom matcher when a business condition is checked repeatedly:

~~~java
ResultMatcher hasOrderId(long expectedId) {
    return result -> {
        String body = result.getResponse().getContentAsString();
        JsonNode json = new ObjectMapper().readTree(body);

        assertThat(json.path("id").asLong())
                .as("order id in response body")
                .isEqualTo(expectedId);
    };
}
~~~

Usage:

~~~java
mockMvc.perform(get("/orders/42"))
        .andExpect(status().isOk())
        .andExpect(hasOrderId(42));
~~~

A custom matcher should verify a single meaningful rule and be named after the condition being asserted. If a matcher lumps unrelated assertions into one big function, failures make it hard to tell which condition broke.

In the example above, ObjectMapper is instantiated inside the matcher for illustration. In larger test suites, reuse an application-configured mapper and handle parse errors appropriately. For simple JSON checks, jsonPath is usually more concise.

## 8. Diagnosing Asynchronous Requests

Spring MVC supports handlers returning asynchronous types such as Callable, DeferredResult, or WebAsyncTask. When a request starts async processing, the initial perform call may return before the final result is ready.

Checking async state:

~~~java
MvcResult asyncResult = mockMvc.perform(get("/reports/42"))
        .andExpect(request().asyncStarted())
        .andDo(print())
        .andReturn();
~~~

Then dispatch the async result to assert the final response:

~~~java
mockMvc.perform(asyncDispatch(asyncResult))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON));
~~~

Do not check only the status of the initial request and assume the async endpoint returned its final response. You must dispatch the async result and assert the status/body on the subsequent dispatch.

If you need to read the async result directly, MvcResult provides getAsyncResult() and getAsyncResult(timeout). Read it only after the request has started async processing and the result is ready; otherwise, the test may wait or fail with a timeout.

When diagnosing async issues, check step by step:

- Did the request actually transition to async?
- Did the Callable/DeferredResult complete?
- Was an exception thrown on the async thread?
- Was asyncDispatch invoked?
- Did the final response have the expected status and body?

## 9. Combining print and Assertions in a Helper

If multiple tests need printing before assertions run, you can extract a helper:

~~~java
ResultActions performWithDiagnostics(
        MockHttpServletRequestBuilder request) throws Exception {

    return mockMvc.perform(request)
            .andDo(print());
}
~~~

Usage:

~~~java
performWithDiagnostics(get("/orders/42"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.id").value(42));
~~~

This helper standardizes printing across a group of tests. Use it only when it improves readability; if a helper hides the request builder or important configuration, calling MockMvc directly is clearer.

If you always want printing within a test class, configure MockMvc with alwaysDo:

~~~java
@BeforeEach
void setUp() {
    mockMvc = MockMvcBuilders
            .webAppContextSetup(webApplicationContext)
            .alwaysDo(print())
            .build();
}
~~~

You can use a dedicated helper for tests under investigation while keeping other tests quiet to reduce noise.

## 10. Organizing Diagnostic Output in CI

When running tests locally, output may appear straight on the console. In CI, output is usually captured in test task logs or test reports. Make sure ResultHandler output goes to logs accessible by the development team.

Useful guidelines:

- Print the request and response of the test under investigation.
- Place print before matchers likely to fail, or use alwaysDo within an appropriate MockMvc scope.
- Preserve stack traces and root exceptions.
- Log the handler method to separate mapping issues from business errors.
- Avoid printing excessive unrelated requests in large test suites.
- Use a logger with appropriate levels if output needs to be controlled by environment.
- Never write tokens, auth cookies, passwords, or personal data to shared logs.

Diagnostic output should be sufficient to reproduce the root cause without exposing sensitive data. If requests carry Authorization headers or cookies, consider not dumping all headers to shared CI logs. A custom ResultHandler can log just URI, status, and handler instead of dumping the full request.

### 10.1. Distinguishing Assertion Failures from Request Execution Failures

These two failure types have different symptoms:

**Assertion failure:** the request ran and produced an MvcResult, but a matcher failed. For example, expecting 200 and getting 404. Print or a handler placed before matchers reveals the actual response.

**Request execution failure:** an unhandled exception caused perform to throw before returning ResultActions. For example, a controller threw an exception with no matching resolver. In this case, an andDo(print()) chained after perform will not run because perform never returned; examine the exception stack trace and exception resolver configuration.

Understanding this distinction prevents wasting time searching for an MvcResult when the request never completed normally.

## 11. Full Example: Investigating an Unexpected 404 Response

Suppose a test expects an endpoint to return HTTP 200:

~~~java
@Test
void returnsOrderDetails() throws Exception {
    MvcResult result = mockMvc.perform(get("/orders/42")
                    .accept(MediaType.APPLICATION_JSON))
            .andDo(print())
            .andReturn();

    assertThat(result.getResponse().getStatus()).isEqualTo(200);
}
~~~

If the test fails with status 404, you can inspect the data in MvcResult to locate the cause:

~~~java
@Test
void diagnosesUnexpectedNotFound() throws Exception {
    MvcResult result = mockMvc.perform(get("/orders/42")
                    .accept(MediaType.APPLICATION_JSON))
            .andDo(print())
            .andReturn();

    System.out.println("Handler: " + result.getHandler());
    System.out.println("Status: "
            + result.getResponse().getStatus());
    System.out.println("Body: "
            + result.getResponse().getContentAsString());

    Exception exception = result.getResolvedException();
    if (exception != null) {
        System.out.println("Resolved exception: "
                + exception.getClass().getName());
    }

    assertThat(result.getResponse().getStatus()).isEqualTo(200);
}
~~~

The findings can point to several lines of investigation:

1. **Null handler:** the request was not mapped to any controller. Check the URL, HTTP method, component scanning, and servlet configuration.
2. **Right handler with a resolved exception:** the controller was invoked and an exception was handled by a resolver. Inspect the exception type, advice, and input data.
3. **Right handler, no exception, 404 response:** the controller may have explicitly returned 404 or another component produced it. Inspect ResponseEntity return logic and relevant interceptors/filters.
4. **Response body indicates resource not found:** confirm that test data or mocked services return the record expected by the endpoint.

During investigation, never change an expected 200 assertion to 404 just to make the test pass if the endpoint contract still requires 200. Identify why the result differed and fix the configuration, data, or behavior appropriately.

## 12. Common Mistakes When Using ResultHandler and print

### Print Output Does Not Appear When a Test Fails

Check where andDo(print()) is placed. If it comes after a failing matcher, the handler does not execute. Move print before matchers or use alwaysDo on the builder.

### Output Exists but Does Not Reveal the Cause

Print provides a request/response snapshot; it does not analyze the cause by itself. Inspect the handler, resolved exception, status, headers, and body via MvcResult. When needed, write a custom ResultHandler logging only meaningful fields.

### Test Fails Before andDo Is Called

If perform throws an unhandled exception, ResultActions is not returned and handlers attached after perform do not run. Inspect the stack trace and check HandlerExceptionResolver or the exception thrown during processing.

### Excessive Logs Make Debugging Harder

If alwaysDo(print()) is enabled across all of MockMvc, every request generates output. Scope it only where needed, or write a concise handler logging brief fields. Remove temporary diagnostic settings once investigation finishes.

### Cannot Read Response Body

Some responses are binary, streaming, or use special encodings. Do not always call getContentAsString() for every response. For file downloads, verify content type, headers, length, or bytes according to the endpoint contract.

### Confusing Resolved Exceptions with Unhandled Root Exceptions

getResolvedException() reflects only exceptions handled by a resolver in MvcResult. Unhandled exceptions can cause perform to throw directly. Inspect the stack trace instead of assuming every error appears in getResolvedException().

### Diagnostics Exposing Sensitive Data

print() can display headers, cookies, and bodies. Do not emit full output in environments with real data or shared logs without controlling what is written. For tests with sensitive data, use selective handlers and dummy values.

## 13. Practical Guidelines

1. Use ResultMatcher to assert the HTTP contract; use ResultHandler to observe outcomes.
2. Place andDo(print()) before matchers that might fail if you want output on assertion failure.
3. Use alwaysDo(print()) when you need to print every request on a MockMvc instance during investigation.
4. Use andReturn() to inspect MvcResult and examine the request, response, handler, exception, model, or flash attributes in depth.
5. Use getResolvedException() when an exception was handled by a Spring MVC resolver.
6. When perform throws before returning ResultActions, inspect the stack trace and resolver configuration.
7. For async requests, assert asyncStarted and verify the final response via asyncDispatch.
8. Prefer matchers with clear failure messages and name custom matchers after the condition they check.
9. Keep logs focused, readable, and free of credentials or sensitive data.
10. Once you find the root cause, keep valuable assertions and remove unnecessary temporary print configuration.

ResultHandler and print show what Spring MVC processed; MvcResult supplies the data for deeper investigation; ResultMatcher turns expectations into explicit test assertions. Combining these three mechanisms ensures a MockMvc failure does not just report a failed test, but gives a clear trail showing how far the request got, which component handled it, and how the actual response was built.

