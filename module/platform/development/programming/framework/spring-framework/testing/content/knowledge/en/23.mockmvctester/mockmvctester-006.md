# Verifying Model, View, and Server-Side Details

`MockMvcTester` is an AssertJ-style Spring MVC testing API available since Spring Framework 6.2. Beyond status, headers, and response body, this API lets you verify results that exist only on the server side, such as model attributes, logical view names, flash attributes, and the handler that processed the request. These checks are useful for view-returning controllers, redirect flows, forms with validation, or endpoints that attach data to the request or session.

An HTTP `200 OK` response does not prove the controller chose the right view or populated the right data in the model. For example, an account detail page might return status 200 while missing the `account` model attribute; when the template renders, it will lack the required data. Checking the model and view helps tests verify the contract between the controller and the presentation layer.

## MockMvcTester in the MVC Processing Flow

`MockMvcTester` uses the `MockMvc` infrastructure. Requests are routed through `DispatcherServlet` along with the Spring MVC components configured in the test environment. Thus, tests can observe the selected handler, the model and view returned by the controller, redirect flash attributes, request/session attributes, and the final response produced by the mock servlet.

`MockMvcTester` does not start a real web server. Tests run in a mock servlet environment without opening sockets or testing browser rendering. This is server-side testing for the Spring MVC flow; if you need to test the network stack, container, TLS, or HTML in a real browser, you need additional tests running the application on a server.

`MockMvcTester` was introduced in Spring Framework 6.2. Projects need the `spring-test` module and AssertJ on the test classpath. The examples below use Java, JUnit Jupiter, and Spring Test 6.2 or later.

## Creating MockMvcTester

There are three common setup approaches, depending on the scope you want to test.

### Using WebApplicationContext

When you want to use the application's Spring MVC configuration, create the tester from `WebApplicationContext`:

```java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.web.SpringJUnitWebConfig;
import org.springframework.test.web.servlet.assertj.MockMvcTester;
import org.springframework.web.context.WebApplicationContext;

@SpringJUnitWebConfig(ApplicationWebConfiguration.class)
class AccountControllerMvcTest {

    private final MockMvcTester mvc;

    AccountControllerMvcTest(@Autowired WebApplicationContext context) {
        this.mvc = MockMvcTester.from(context);
    }
}
```

`ApplicationWebConfiguration` must load the controllers, MVC infrastructure, and dependencies used by the controllers. This approach suits tests that need to verify mappings, interceptors, converters, validators, advice, and view resolver configurations registered in the context.

With Spring Boot, you can use `@SpringBootTest` to load the application context and inject `WebApplicationContext` similarly. If the project already has `MockMvc`, you can create the tester from that instance using `MockMvcTester.create(mockMvc)`.

### Using a Specific Controller

If you only need to set up one controller and minimal MVC configuration, use `MockMvcTester.of(...)`:

```java
MockMvcTester mvc = MockMvcTester.of(new AccountController(accountService));
```

In this mode, the test focuses on the passed-in controller. Components such as controller advice, validators, converters, or custom view resolvers must be configured explicitly if the behavior under test depends on them. When the goal is to test the real application configuration, use a tester built from `WebApplicationContext`.

## How to Send Requests and Run Assertions

`MockMvcTester`'s request builder has methods such as `get()`, `post()`, `put()`, `delete()`, and `uri(...)`. It reuses MockMvc's request configuration style, such as `param`, `header`, `content`, `contentType`, `accept`, `cookie`, `sessionAttr`, and `with`.

```java
import static org.assertj.core.api.Assertions.assertThat;

assertThat(mvc.get().uri("/accounts/{id}", 42L))
        .hasStatusOk();
```

Calling `assertThat(...)` accepts the AssertJ-capable builder, executes the request, and returns a dedicated assertion for `MvcTestResult`. You can call `.exchange()` if you want to retain the result and run multiple assertion statements:

```java
MvcTestResult result = mvc.get()
        .uri("/accounts/{id}", 42L)
        .exchange();

assertThat(result).hasStatusOk();
assertThat(result).hasViewName("accounts/detail");
```

Do not execute the same builder twice if the test intends to verify a single request. Retain the `MvcTestResult` after `.exchange()` and use it for all subsequent assertions. `MvcTestResult` also exposes the request, response, and underlying `MvcResult` for detailed inspection when high-level assertions are not enough.

## Verifying Model Attributes

The model holds data the controller prepares for the view. A controller can add data via a `Model`, `ModelMap`, or `ModelAndView` parameter, or via the `@ModelAttribute` annotation.

Example controller returning a detail view:

```java
@Controller
class AccountController {

    private final AccountService accountService;

    AccountController(AccountService accountService) {
        this.accountService = accountService;
    }

    @GetMapping("/accounts/{id}")
    String detail(@PathVariable long id, Model model) {
        Account account = accountService.findById(id);
        model.addAttribute("account", account);
        model.addAttribute("canEdit", accountService.canEdit(id));
        return "accounts/detail";
    }
}
```

The test can check both the view and model in a single chain:

```java
assertThat(mvc.get().uri("/accounts/{id}", 42L))
        .hasStatusOk()
        .hasViewName("accounts/detail")
        .model()
        .containsKey("account")
        .containsEntry("canEdit", true);
```

`model()` returns `ModelAssert`, an AssertJ map assertion over the model entries. Consequently, you can use familiar map checks:

```java
assertThat(mvc.get().uri("/accounts/{id}", 42L))
        .model()
        .containsKeys("account", "canEdit")
        .containsEntry("canEdit", true)
        .doesNotContainKey("internalToken");
```

If you need to inspect an object's values, assert directly on the entry or inspect the object's properties:

```java
assertThat(mvc.get().uri("/accounts/{id}", 42L))
        .model()
        .hasEntrySatisfying("account", value -> {
            assertThat(value).isInstanceOf(Account.class);
            Account account = (Account) value;
            assertThat(account.getId()).isEqualTo(42L);
            assertThat(account.getDisplayName()).isEqualTo("Mai Nguyen");
        });
```

If the test only cares that the controller puts the right object in the model, there is no need to render a real template. If you want to verify the HTML response, configure the view technology so the view renders in MockMvc and assert on the response content. Those two goals differ: model assertions verify server-side data, whereas body assertions verify content rendered into the response.

## Verifying That the Model Has No Validation Errors

`ModelAssert` supports checking validation errors attached to model attributes. When a controller returns a confirmation view after successful binding and validation, you can assert that the attribute has no errors:

```java
assertThat(mvc.post().uri("/accounts")
                .param("displayName", "Mai Nguyen")
                .param("email", "mai@example.test"))
        .hasStatusOk()
        .hasViewName("accounts/confirm")
        .model()
        .doesNotHaveErrors()
        .doesNotHaveAttributeErrors("accountForm");
```

`doesNotHaveErrors()` checks that the model has no binding/validation errors. `doesNotHaveAttributeErrors("accountForm")` focuses only on the specified attribute. Use the narrower assertion when the model may legitimately contain another attribute with errors in the same response.

## Verifying BindingResult and Field Errors

When a controller receives a form via `@ModelAttribute` with a `BindingResult` immediately following the object, Spring places the binding result into the model under a key prefixed with `BindingResult.MODEL_KEY_PREFIX` plus the attribute name. `MockMvcTester` provides `extractingBindingResult(...)` to inspect those errors in AssertJ style.

Controller example:

```java
@PostMapping("/accounts")
String create(
        @Valid @ModelAttribute("accountForm") AccountForm form,
        BindingResult bindingResult) {

    if (bindingResult.hasErrors()) {
        return "accounts/new";
    }

    accountService.create(form);
    return "redirect:/accounts";
}
```

Test confirming the error is bound to the right field:

```java
assertThat(mvc.post().uri("/accounts")
                .param("displayName", "Mai")
                .param("email", "not-an-email"))
        .hasStatusOk()
        .hasViewName("accounts/new")
        .model()
        .hasAttributeErrors("accountForm")
        .extractingBindingResult("accountForm")
        .hasFieldErrors("email");
```

Dedicated assertions for `BindingResult` include:

| Assertion | Meaning |
|---|---|
| `model().hasErrors()` | Model has at least one binding result containing errors |
| `model().doesNotHaveErrors()` | Model has no errors |
| `model().hasAttributeErrors("accountForm")` | The specified attribute has errors |
| `model().doesNotHaveAttributeErrors("accountForm")` | The specified attribute has no errors |
| `model().extractingBindingResult("accountForm").hasErrorsCount(2)` | Binding result has the exact number of errors |
| `.hasFieldErrors("email", "displayName")` | The listed fields have errors |
| `.hasOnlyFieldErrors("email")` | Only the email field has errors, with no other errors |
| `.hasFieldErrorCode("email", "Email")` | Field has an error with the specified error code |

`hasFieldErrors(...)` verifies that the listed fields have errors, whereas `hasOnlyFieldErrors(...)` verifies the exact set of errored fields and no others. Use `hasOnlyFieldErrors` when the exact count and set of errored fields are part of the behavior the test must protect.

Binding errors from type conversion and Bean Validation errors can both appear as field errors. If you need to distinguish `age=abc` from `age=-1`, you can access the underlying `BindingResult` via `MvcTestResult` and check `FieldError#isBindingFailure()`, or use the `MvcResult` API as shown below.

## Verifying View Names

For controllers returning a view name, `hasViewName(...)` checks the logical view name in `ModelAndView`:

```java
assertThat(mvc.get().uri("/accounts/new"))
        .hasStatusOk()
        .hasViewName("accounts/new");
```

You can use `viewName()` when you want to chain AssertJ string assertions:

```java
assertThat(mvc.get().uri("/accounts/new"))
        .viewName()
        .startsWith("accounts/");
```

The view name is the logical name returned by the controller. For instance, `accounts/detail` may be mapped by `ViewResolver` to a corresponding template or JSP. This assertion does not prove that the template file exists or that a browser renders the page pixel-perfectly. To verify rendered content, assert on the response body; to test real browser experience, an end-to-end test is required.

If the controller returns `@ResponseBody`, `ResponseEntity`, or a DTO from `@RestController`, there is typically no `ModelAndView`. In that case, do not call `hasViewName()` or `model()`; assert on status, headers, and response body instead.

## Verifying Redirects, Forwards, and Flash Attributes

After processing a form successfully, controllers typically redirect to prevent resubmitting data when the user refreshes the page:

```java
@PostMapping("/accounts")
String create(
        @Valid @ModelAttribute("accountForm") AccountForm form,
        BindingResult errors,
        RedirectAttributes redirectAttributes) {

    if (errors.hasErrors()) {
        return "accounts/new";
    }

    Account created = accountService.create(form);
    redirectAttributes.addFlashAttribute(
            "notice", "Account created successfully");
    return "redirect:/accounts/" + created.getId();
}
```

MockMvcTester can verify the redirect status, target URL, and flash attributes:

```java
assertThat(mvc.post().uri("/accounts")
                .param("displayName", "Mai Nguyen")
                .param("email", "mai@example.test"))
        .hasStatus3xxRedirection()
        .hasRedirectedUrl("/accounts/42")
        .flash()
        .containsEntry("notice", "Account created successfully");
```

`flash()` returns a map assertion over the output flash attributes stored during request processing. It is suited for checking one-time messages passed across a redirect. Flash attributes differ from query parameters and from regular model attributes of the current request.

If a controller uses a forward instead of a redirect, you can verify the forwarded URL:

```java
assertThat(mvc.get().uri("/legacy/accounts"))
        .hasStatusOk()
        .hasForwardedUrl("/accounts/list");
```

Redirect and forward have different semantics. A redirect instructs the client to send a new request to the target URL; a forward transfers the request internally on the server. Do not use redirect assertions for a controller returning `forward:` or vice versa.

## Verifying the Handler That Processed the Request

A URL may be handled by multiple mappings with different conditions. `handler()` allows confirming which controller or handler method was actually invoked:

```java
assertThat(mvc.get().uri("/accounts/{id}", 42L))
        .handler()
        .hasType(AccountController.class);
```

You can also verify the specific handler method:

```java
assertThat(mvc.get().uri("/accounts/{id}", 42L))
        .handler()
        .method()
        .hasName("detail");
```

Checking the handler is helpful when an application has overlapping routes, inherited controllers, or multiple mappings by HTTP method, `params`, `headers`, `consumes`, and `produces`. If you only assert the response body, two different handlers might coincidentally return identical content and the test would miss that the request was dispatched to the wrong handler.

## Verifying Request and Session Attributes

The model belongs to `ModelAndView`, whereas request and session attributes belong to the Servlet API. When you need to verify data placed in the request or session, retain `MvcTestResult` and read from the mock request:

```java
MvcTestResult result = mvc.get()
        .uri("/wizard/step")
        .sessionAttr("wizardId", "W-42")
        .exchange();

assertThat(result).hasStatusOk();
assertThat(result.getRequest().getAttribute("currentStep"))
        .isEqualTo("review");
assertThat(result.getRequest().getSession(false))
        .isNotNull();
assertThat(result.getRequest().getSession(false)
        .getAttribute("wizardId"))
        .isEqualTo("W-42");
```

Here `sessionAttr(...)` sets an input session attribute for the test request. If the controller modifies the session, inspect the session after the request completes. Use `getSession(false)` when you want to verify the request already has a session without accidentally creating a new session during the assertion.

For request attributes, distinguish attributes supplied by the test from attributes set by an interceptor, filter, or controller during processing. If testing a value produced by the server, do not set that same key with `.requestAttr(...)` before executing the request, because the test would no longer prove the server created the value.

## Using MvcTestResult for Detailed Inspection

`MvcTestResult` is the result of a single request execution. It provides access to the underlying `MvcResult`, request, and response. When dedicated assertions do not meet a requirement, you can access `ModelAndView` directly:

```java
MvcTestResult result = mvc.get()
        .uri("/accounts/{id}", 42L)
        .exchange();

MvcResult mvcResult = result.getMvcResult();
ModelAndView modelAndView = mvcResult.getModelAndView();

assertThat(modelAndView).isNotNull();
assertThat(modelAndView.getViewName()).isEqualTo("accounts/detail");
assertThat(modelAndView.getModel()).containsKey("account");
```

To read the binding result from the model:

```java
BindingResult bindingResult = (BindingResult) modelAndView.getModel().get(
        BindingResult.MODEL_KEY_PREFIX + "accountForm");

assertThat(bindingResult).isNotNull();
assertThat(bindingResult.getFieldErrors("email")).isNotEmpty();
```

If the controller returns a response body rather than a view, `getModelAndView()` may be `null`. Check before reading the model. For response bodies, use `result.getResponse().getContentAsString()` or MockMvcTester's `bodyText()`/`bodyJson()` assertions.

If a handler throws an exception handled by a `HandlerExceptionResolver`, the request may still produce a complete response to assert on. If the exception is unhandled and the request fails unexpectedly, `MvcTestResult` has `getUnresolvedException()`; in that case, you cannot read a complete MVC result as if the request finished normally.

## Combining Legacy MockMvc Assertions

`MockMvcTester` does not discard the entire `MockMvc` API. If a project already has custom `RequestBuilder`, `ResultMatcher`, or `ResultHandler` components, they can be integrated:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

assertThat(mockMvc.perform(get("/accounts/{id}", 42L)))
        .matches(status().isOk())
        .hasViewName("accounts/detail");
```

Or use `.matches(...)` to apply a legacy `ResultMatcher` to the result produced by `MockMvcTester`'s request builder:

```java
assertThat(mvc.get().uri("/accounts/{id}", 42L))
        .matches(status().isOk())
        .hasViewName("accounts/detail");
```

For a custom `ResultHandler`, use `.apply(...)`. This integration is useful when migrating gradually from `mockMvc.perform(...).andExpect(...)` to AssertJ without immediately rewriting every shared matcher.

## Asynchronous Requests

If a controller processes asynchronously, `exchange()` waits for the request to complete before returning the result so assertions read a settled response. The default wait time is 10 seconds; you can specify a timeout for the request:

```java
assertThat(mvc.get().uri("/reports/42")
                .exchange(Duration.ofSeconds(5)))
        .hasStatusOk()
        .hasViewName("reports/detail");
```

If you need to manage the lifecycle of a running async request yourself, use `asyncExchange()` and handle the async state according to the test's goal. Do not use `exchange()` with an overly short timeout if the handler needs reasonable time to finish; nor should you raise the timeout to mask a hung process.

## Common Mistakes

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `MockMvcTester` not found | Spring Framework older than 6.2 or missing `spring-test` | Use Spring Framework 6.2 or later and add the appropriate test dependency |
| `assertThat(...)` lacks MVC assertions | Missing AssertJ or builder did not come from `MockMvcTester` | Check AssertJ on the test classpath and the request builder type |
| No `ModelAndView` | Controller returns `@ResponseBody`, `ResponseEntity`, or `@RestController` | Assert on the response body; do not check view/model for body responses |
| Model missing attribute | Controller did not add the attribute, wrong model attribute name, or a different handler branch ran | Inspect `Model`, `@ModelAttribute`, and the actual handler |
| Binding result not found | Wrong attribute name or controller did not declare `BindingResult` in the right position | Use the exact `@ModelAttribute` name and place `BindingResult` immediately after the object |
| View name is right but HTML is wrong | Test only checks the logical view name | Assert on the rendered response body or add browser tests |
| Flash attribute does not appear | Controller uses a regular model attribute instead of `addFlashAttribute`, or request does not redirect | Check the redirect branch and use `RedirectAttributes` |
| Handler assertion fails | Another mapping was selected due to method, path, params, or headers | Check `@RequestMapping` conditions and the sent request |
| Session assertion creates a false result | Test calls `getSession()` which creates a new session | Use `getSession(false)` to only read an existing session |

## Choosing Assertions by Goal

| What Needs to Be Proven | Recommended Assertion |
|---|---|
| Request returns the expected status | `hasStatusOk()`, `hasStatus(...)` |
| Controller picks the right logical view | `hasViewName(...)` or `viewName()` |
| Model has data needed by the view | `model().containsKey(...)`, `containsEntry(...)` |
| Model has no validation errors | `model().doesNotHaveErrors()` |
| Form has errors on the right fields | `model().extractingBindingResult(...).hasFieldErrors(...)` |
| Redirect targets the right URL | `hasRedirectedUrl(...)` |
| Flash message is present after redirect | `flash().containsEntry(...)` |
| Request is handled by the expected controller | `handler().hasType(...)` or `handler().method().hasName(...)` |
| Server sets the right request/session attribute | `MvcTestResult#getRequest()` and Servlet API |
| Need to read ModelAndView details | `MvcTestResult#getMvcResult()` |

When testing a view-returning controller, verify the status, logical view name, and important model attributes. For forms, add assertions for `BindingResult`; for PRG flows, verify the redirect URL and flash attributes. These assertions show that the controller prepared the right server-side data and chose the right navigation outcome before the user sees the page.
