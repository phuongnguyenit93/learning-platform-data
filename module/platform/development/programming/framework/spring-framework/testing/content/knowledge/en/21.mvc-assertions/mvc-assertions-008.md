# Redirects, Forwards, and Flash Attributes

In Spring MVC, a controller can return a view name instructing the framework to route the request to another resource. Two common mechanisms are **redirect** and **forward**. A redirect asks the client to make a new HTTP request to a target URL; a forward transfers the current request internally on the server side. When you need to carry a notification or temporary data across a redirect, Spring provides **flash attributes**.

Spring MVC Test lets you assert these outcomes with `MockMvc`. You can verify the redirect status and URL, the forwarded URL, generated flash attributes, and flash data appearing in the subsequent request. Key matchers include `redirectedUrl(...)`, `redirectedUrlPattern(...)`, `forwardedUrl(...)`, `forwardedUrlPattern(...)`, `flash()`, and `model()`.

## 1. Controllers Returning View Names

Redirects and forwards using view-name syntax are typically used with controllers annotated with `@Controller`:

```java
@Controller
class OrderController {

    @PostMapping("/orders")
    String createOrder() {
        return "redirect:/orders/42";
    }
}
```

Spring interprets the returned string as a view name. The `redirect:` prefix tells the framework to create a redirect view; the `forward:` prefix tells it to create a forward view.

Do not confuse this view-name return style with `@RestController`. `@RestController` includes `@ResponseBody`, so the string `"redirect:/orders/42"` would be written directly into the response body instead of being interpreted as a redirect view. If an endpoint returns REST data, use an appropriate HTTP response mechanism such as `ResponseEntity` and a `Location` header; if you want to return a view name, use `@Controller` or intentionally annotate methods with `@ResponseBody` as needed.

## 2. Redirect: Client Sends a New Request

A redirect is a navigation outcome at the HTTP layer. The controller returns a view name starting with `redirect:`:

```java
@Controller
@RequestMapping("/orders")
class OrderController {

    @PostMapping
    String create(@RequestParam String customer) {
        // Create order and obtain the new order ID.
        return "redirect:/orders/42";
    }
}
```

Spring produces a redirect response, typically with status 302 under the default `RedirectView` configuration, and a `Location` header pointing to the target URL. The client receives this response and issues a new request to that address. In a Post/Redirect/Get (PRG) flow, the client sends a POST to create data, receives a redirect, and then GETs the result page. This prevents refreshing the result page from repeating the original POST.

With `MockMvc`, you can assert a redirect as follows:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(post("/orders").param("customer", "Lan"))
        .andExpect(status().is3xxRedirection())
        .andExpect(redirectedUrl("/orders/42"));
```

`status().is3xxRedirection()` checks that the response belongs to the redirect status group. `redirectedUrl(...)` checks the target URL set in the response. If the contract specifically requires status 302, use `status().isFound()`; if the application intentionally returns 303 See Other, assert `status().isSeeOther()`. Use an exact matcher whenever the specific status is part of the HTTP contract.

### Redirects with Path Variables and Query Parameters

`RedirectAttributes.addAttribute(...)` puts data into the redirect URL. Values can expand URI template variables or be appended as query parameters.

```java
@PostMapping
String create(
        @RequestParam String customer,
        RedirectAttributes redirectAttributes
) {
    long orderId = 42L;
    redirectAttributes.addAttribute("id", orderId);
    redirectAttributes.addAttribute("source", "checkout");
    return "redirect:/orders/{id}";
}
```

In this example, `id` substitutes `{id}` in the path, and `source` becomes a query parameter. The test can verify the resulting URL:

```java
mockMvc.perform(post("/orders").param("customer", "Lan"))
        .andExpect(status().is3xxRedirection())
        .andExpect(redirectedUrl("/orders/42?source=checkout"));
```

If dynamic values make exact URL matching difficult, use `redirectedUrlPattern(...)` to match by pattern. `redirectedUrl(...)` and `redirectedUrlPattern(...)` verify the navigation target, while status matchers verify the response category.

## 3. Forward: Server-Side Request Transfer

A forward is an internal server operation via `RequestDispatcher`. The client does not receive a redirect response to make a new request. The URL in the browser stays the original URL; the current request is transferred to the target resource or servlet within the same application.

A controller can return a view name starting with `forward:`:

```java
@Controller
class ReportController {

    @GetMapping("/reports/{id}/preview")
    String preview(@PathVariable long id, Model model) {
        model.addAttribute("reportId", id);
        return "forward:/internal/reports/preview";
    }
}
```

The `forward:` prefix instructs Spring to forward to the specified path. Because this is an internal dispatch, there is no 3xx response and no `Location` header asking the client to navigate.

The test can verify the forwarded URL:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.forwardedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(get("/reports/42/preview"))
        .andExpect(status().isOk())
        .andExpect(forwardedUrl("/internal/reports/preview"));
```

`forwardedUrl(...)` asserts the internal dispatch destination recorded by the mock request. `forwardedUrlPattern(...)` can be used when matching by pattern.

Forwarding preserves the current request. Because no new client request is made, the HTTP method and request attributes continue in the same processing flow. This differs from a redirect, where the client processes a 3xx response and creates a new request according to status code semantics and client behavior.

### Forwarding to a View Resource

Forwarding can also route to an internal resource, such as a JSP under `WEB-INF`:

```java
@GetMapping("/reports/{id}")
String view(@PathVariable long id, Model model) {
    model.addAttribute("reportId", id);
    return "forward:/WEB-INF/views/reports/detail.jsp";
}
```

In a running application, the servlet container and view technology handle the target resource. `MockMvc` can verify the forward URL and model in the MVC result; it does not render JSPs like a full servlet container. If you need to verify real template or JSP rendering, add integration tests suited to your view technology.

## 4. Comparing Redirect and Forward

| Aspect | Redirect | Forward |
| --- | --- | --- |
| Where it happens | Client receives a redirect response and sends a new request. | Server forwards the current request internally. |
| Initial HTTP response | 3xx status and usually `Location`. | Does not produce a 3xx response merely for forwarding. |
| Client-side URL | Updated to target URL after client follows redirect. | Remains the original URL. |
| Request | A new request is created after redirect. | Continues the current request. |
| Passing data onward | Can use URL attributes or flash attributes. | Can use request attributes and model within the same request. |
| Primary matchers | `redirectedUrl(...)`, `redirectedUrlPattern(...)`. | `forwardedUrl(...)`, `forwardedUrlPattern(...)`. |

Choose redirect when you want to finish the current request and navigate the client, especially in PRG after a POST operation. Choose forward when the server needs to internally dispatch the request to another resource or servlet without asking the client for a new request.

## 5. What Are Flash Attributes Used For?

During a redirect, regular model attributes do not automatically survive into the next request because a redirect creates a new request. If you need to display a message such as "Order created successfully" on the destination page, use a flash attribute.

A flash attribute is temporary data stored in a `FlashMap` to pass from the current request to the next request. Spring uses `FlashMapManager` to save and restore the flash map; once consumed by the matching target request, flash data is used once and removed. Flash attributes are not appended to the URL query string.

In the controller, inject `RedirectAttributes` and call `addFlashAttribute(...)`:

```java
@PostMapping
String create(
        @RequestParam String customer,
        RedirectAttributes redirectAttributes
) {
    long orderId = 42L;

    redirectAttributes.addAttribute("id", orderId);
    redirectAttributes.addFlashAttribute("notice", "Order created successfully");

    return "redirect:/orders/{id}";
}
```

Here:

- `addAttribute("id", orderId)` supplies data for the redirect URL.
- `addFlashAttribute("notice", ...)` saves the message in the output flash map for the target request to receive.
- `return "redirect:/orders/{id}"` generates the redirect response to the detail page.

Flash attributes suit temporary notifications, operation outcomes, or small pieces of data needed right after a redirect. Avoid using the flash map for large payloads or long-lived state.

## 6. Verifying Flash Attributes on the Redirect Response

Spring MVC Test provides the `flash()` result matcher to verify the output flash map produced by the current request.

```java
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.flash;

mockMvc.perform(post("/orders").param("customer", "Lan"))
        .andExpect(status().is3xxRedirection())
        .andExpect(redirectedUrl("/orders/42"))
        .andExpect(flash().attribute(
                "notice", "Order created successfully"));
```

Useful matchers include:

| Matcher | What Is Verified |
| --- | --- |
| `flash().attribute(name, value)` | Flash map contains an attribute with the expected name and value. |
| `flash().attributeExists(name)` | The flash attribute exists. |
| `flash().attributeDoesNotExist(name)` | The flash attribute does not exist. |
| `flash().attributeCount(count)` | Number of attributes in the flash map. |

You can combine matchers to verify both count and contents:

```java
mockMvc.perform(post("/orders").param("customer", "Lan"))
        .andExpect(flash().attributeCount(1))
        .andExpect(flash().attributeExists("notice"))
        .andExpect(flash().attributeDoesNotExist("debugInfo"));
```

`flash()` checks flash data created by the request under test. It differs from `model()`, which checks the model of the current request handler. The flash map carries data across a redirect boundary; the model holds data used during rendering or processing of the current request.

## 7. Verifying the Target Request Receives Flash Attributes

After confirming the redirect response builds the right flash map, you can simulate the follow-up request and supply those flash attributes to the request builder via `.flashAttrs(...)`.

The target controller can receive flash attributes through `Model`:

```java
@GetMapping("/{id}")
String detail(@PathVariable long id, Model model) {
    model.addAttribute("orderId", id);
    return "orders/detail";
}
```

The test performs the POST request, grabs the flash map from the result, and sends a GET to the target URL:

```java
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.model;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

MvcResult redirectResult = mockMvc.perform(post("/orders")
                .param("customer", "Lan"))
        .andExpect(status().is3xxRedirection())
        .andReturn();

mockMvc.perform(get("/orders/42")
                .flashAttrs(redirectResult.getFlashMap()))
        .andExpect(status().isOk())
        .andExpect(model().attribute("notice", "Order created successfully"))
        .andExpect(model().attribute("orderId", 42L));
```

`MvcResult.getFlashMap()` returns the output flash map created by the first request. `flashAttrs(...)` sets those entries as input flash attributes on the simulated GET request. When Spring MVC handles the target request, flash values are merged into the model, allowing `model().attribute(...)` to verify the message the view will receive.

This simulation focuses on two parts: the request creating flash data and the target controller consuming it. It explicitly passes the map from the prior result to the next request. If your goal is to test the full save/restore lifecycle of flash maps across a session and `FlashMapManager`, design an integration test using the shared session and real flash map management.

## 8. Distinguishing URL Attributes, Flash Attributes, and Model Attributes

These three data mechanisms have different lifecycles and scopes:

| Attribute Type | How Created | Where It Appears | Lifecycle |
| --- | --- | --- | --- |
| Redirect URL attribute | `RedirectAttributes.addAttribute(...)` | Path variable or query string of the redirect URL. | Present in the URL and the request sent to the destination. |
| Flash attribute | `RedirectAttributes.addFlashAttribute(...)` | Input flash map of the next request, then available in the model. | Temporary, typically consumed once. |
| Model attribute | `Model.addAttribute(...)` or `ModelMap.addAttribute(...)` | Model of the current request for the view. | Tied to the current request/render. |

Example:

```java
redirectAttributes.addAttribute("id", 42L);
redirectAttributes.addFlashAttribute("notice", "Created");
```

`id` can appear in the path `/orders/42`; `notice` is stored in the flash map. If instead you used `model.addAttribute("notice", "Created")` and returned `redirect:/orders/42`, the regular model would not automatically carry over to the new GET request.

Never put passwords, tokens, or sensitive data into URL attributes because URLs can show up in browser history, logs, and referrers. Flash attributes avoid putting values into query strings, yet should still hold only temporary data compatible with the application's session mechanism.

## 9. Verifying Redirects and Forwards with Patterns

When the target URL has dynamic segments, you can use pattern matchers instead of exact full-URL matching.

Example redirecting to a path containing a runtime-generated ID:

```java
mockMvc.perform(post("/reports").param("title", "Annual report"))
        .andExpect(status().is3xxRedirection())
        .andExpect(redirectedUrlPattern("/reports/*"));
```

Similarly for forward:

```java
mockMvc.perform(get("/reports/42/export"))
        .andExpect(forwardedUrlPattern("/internal/reports/*"));
```

Pattern matchers are helpful when part of the URL depends on dynamic data while the path structure still needs verification. When the exact URL is part of the contract, prefer exact URL matchers so tests catch unintended changes.

## 10. Verifying `RedirectView` and Status Codes

Beyond the `redirect:` string prefix, a controller can return a `RedirectView` to configure redirect behavior more explicitly:

```java
@PostMapping("/orders")
RedirectView create() {
    RedirectView view = new RedirectView("/orders/42");
    view.setStatusCode(HttpStatus.SEE_OTHER);
    return view;
}
```

`HttpStatus.SEE_OTHER` corresponds to 303. This status is often used in PRG so the client accesses the target page using GET after a POST. When using `RedirectView` with a custom status, tests should assert the exact status and URL:

```java
mockMvc.perform(post("/orders"))
        .andExpect(status().isSeeOther())
        .andExpect(redirectedUrl("/orders/42"));
```

Redirects can use other statuses depending on HTTP semantics and client needs. 302 and 303 commonly cause browsers to follow up with GET; 307 and 308 are defined to preserve the HTTP method and body during redirection. Choose the status deliberately and assert what clients must obey.

## 11. Common Mistakes When Testing Redirects, Forwards, and Flash

**Using `@RestController` and expecting `redirect:` strings to be processed.**

`@RestController` writes the returned string into the response body. Use `@Controller` for view names, or return `ResponseEntity` with a status and `Location` if the endpoint is a REST API.

**Checking only 3xx status without checking the URL.**

A redirect response could point to the wrong target while still having the right status. Combine `status().is3xxRedirection()` with `redirectedUrl(...)` or `redirectedUrlPattern(...)`.

**Using `forwardedUrl` to check a redirect.**

Redirect and forward are different mechanisms. Use `redirectedUrl(...)` for redirect responses and `forwardedUrl(...)` for internal dispatches.

**Expecting regular model attributes to survive a redirect.**

A redirect initiates a new request. Use `addFlashAttribute(...)` for temporary data needed by the next request, or `addAttribute(...)` if the data belongs in the URL.

**Checking flash attributes with `model()` on the POST request.**

Flash attributes are written to the redirect request's output flash map. Use `flash()` to check that map. Only check with `model()` on the target request after supplying input flash attributes.

**Forgetting to pass the flash map when simulating the follow-up request.**

In manually simulated multi-step tests, pass `.flashAttrs(redirectResult.getFlashMap())` on the target request. If you want to test automatic persistence/retrieval via session, test with `FlashMapManager` and a shared session.

**Assuming forward creates a new client request.**

Forwarding is an internal dispatch, with no redirect response sent to the browser. If you need to change the client URL or implement PRG, use a redirect.

**Assuming a forward matcher verifies that a JSP resource rendered.**

`forwardedUrl(...)` verifies the forward target in the MockMvc result. It does not prove that a servlet container rendered the JSP or a template engine produced the final HTML.

## 12. Workflow for Testing Navigation Results

When writing tests for controllers that navigate, first clarify which mechanism the controller is supposed to perform:

1. If the client should visit a new URL, check the redirect status and `Location` using `redirectedUrl(...)` or `redirectedUrlPattern(...)`.
2. If the server should transfer the current request internally, check the target using `forwardedUrl(...)` or `forwardedUrlPattern(...)`.
3. If a redirect carries temporary data, use `addFlashAttribute(...)` and check the output map with `flash()`.
4. If you need to confirm the target page receives flash data, take `MvcResult.getFlashMap()` and pass it via `.flashAttrs(...)` to the next request.
5. If data belongs in the URL, use `addAttribute(...)` and check the exact path or query string.
6. If a specific redirect status such as 302 or 303 matters, assert that exact status instead of only the broad 3xx group.
7. If you need to confirm views rendered by a servlet container or template engine, add appropriate integration tests.

## Conclusion

A redirect generates a 3xx response so the client sends a new request; a forward transfers the current request internally on the server. Spring MVC Test provides `redirectedUrl(...)` and `forwardedUrl(...)` to assert these two outcomes. Flash attributes use `FlashMap` to carry temporary data across a redirect and can be asserted with `flash()` or fed into the next test request via `.flashAttrs(...)`.

Properly distinguishing URL attributes, flash attributes, and model attributes helps tests confirm data appears in the right place at the right time. When testing only the controller, MockMvc can verify navigation URLs and model/flash maps; full view rendering and servlet lifecycle behavior should be verified at the appropriate integration level.
