# Spring MVC — RedirectAttributes, Flash Attributes, and Redirect Data Lifecycle

## 1. Objectives

After a user submits a POST form and the server saves the data successfully, the result page is typically opened via a GET URL. Spring MVC supports this workflow with **Post/Redirect/Get (PRG)**, `RedirectAttributes`, and **flash attributes**.

You will learn how to:

- Distinguish `addAttribute(...)` (values in the URL) from `addFlashAttribute(...)` (temporary data for the target request).
- Understand the HTTP POST → 302/303 redirect → GET flow and the limitations of PRG.
- Trace the outbound `FlashMap`, temporary storage (by default via the HTTP session), target URL matching, inbound `FlashMap`, and single-consumption behavior.
- Handle form validation, success notices, and redirects to a detail page with Thymeleaf.
- Evaluate scenarios such as premature flash loss, session expiration, concurrent browser tabs, API/AJAX calls, and sensitive data.
- Run a Spring Boot 3.5, Java 17 project and test redirects/flash attributes with MockMvc.

This lesson focuses on **Spring MVC on the Servlet stack**. Do not apply MVC's session-based `FlashMap` mechanism directly to Spring WebFlux.

## 2. What Problem Does Post/Redirect/Get Solve?

If the server returns HTML directly to a POST:

~~~text
Browser                         Server
 POST /messages --------------->
                 save data
 <---------------- HTTP 200 HTML
 Refresh: browser may prompt "confirm form resubmission" and POST again
~~~

A single refresh can create a duplicate record. The PRG design:

~~~text
Browser                         Spring MVC
 POST /messages --------------> Validate, save: id=42
 <-------------- HTTP 302 Location: /messages/42
 GET /messages/42 ------------> Fetch data by id
 <-------------- HTTP 200 HTML
 Refresh result page ----------> GET /messages/42
~~~

Illustrative handler:

~~~java
@PostMapping("/messages")
public String create(RedirectAttributes redirectAttributes) {
    long id = 42; // Real ID obtained from the service after saving successfully.
    redirectAttributes.addAttribute("id", id);
    redirectAttributes.addFlashAttribute("notice", "Created successfully");
    return "redirect:/messages/{id}";
}
~~~

`redirect:` is a **view name** prefix for redirection. Spring MVC produces an HTTP redirect with a `Location` header. After the browser issues the target GET, refreshing repeats the GET rather than repeating the old POST.

**Limitation:** PRG reduces duplicate POSTs from page refreshes, yet **does not guarantee idempotency** against double-clicks, client retries, network timeouts after server commit, or two concurrent POSTs. For orders, payments, or critical write operations, add idempotency keys, unique constraints, and appropriate transactions.

### 2.1. Choosing 302, 303, 307, or 308?

| Status | Notable semantics | Role in PRG |
| --- | --- | --- |
| `302 Found` | Temporary redirect; clients historically switch POST to GET | Standard `redirect:` returns 302 |
| `303 See Other` | Client should retrieve target resource, typically via GET | Expresses "POST succeeded, open result page" most clearly |
| `307 Temporary Redirect` | Preserves method and body during redirect | Unsuitable if you want POST switched to GET |
| `308 Permanent Redirect` | Preserves method and body; permanent redirect | Not used for ordinary PRG |

To emit 303 explicitly, you can return a configured `RedirectView`:

~~~java
RedirectView view = new RedirectView("/messages/42");
view.setStatusCode(HttpStatus.SEE_OTHER);
return view;
~~~

This snippet illustrates a handler returning `RedirectView` and requires the corresponding Spring MVC/HTTP imports. If using `return "redirect:..."` as in the project below, do not assume 303 by default; tests should assert appropriate 3xx/Location behavior.

## 3. `RedirectAttributes`: Data for Redirects

Interface to import:

~~~java
import org.springframework.web.servlet.mvc.support.RedirectAttributes;
~~~

Two core operations:

~~~java
attrs.addAttribute("id", 42);
attrs.addAttribute("tab", "history");
attrs.addFlashAttribute("notice", "Saved successfully");
~~~

| Operation | Where value appears | Lifecycle | Use case |
| --- | --- | --- | --- |
| `addAttribute("id", 42)` | URI path or query parameter | Persists in URL; bookmarkable/shareable | Resource ID, page, filter |
| `addFlashAttribute("notice", "...")` | Temporary `FlashMap`, not appended to URL | Targets matching next request, then consumed | One-time success notice |
| `model.addAttribute(...)` in normal view handler | Current request's Model | Serves current rendering | Form/view data |
| `HttpSession.setAttribute(...)` | HTTP session | Until removed/expired | Multi-request state |
| `@SessionAttributes` | Model attributes persisted by Spring in session | Until flow finishes or session expires | Multi-step wizard |

### 3.1. `addAttribute` Goes into Path or Query

~~~java
@PostMapping("/orders")
public String create(RedirectAttributes attrs) {
    attrs.addAttribute("id", 42);
    attrs.addAttribute("tab", "history");
    return "redirect:/orders/{id}";
}
~~~

In this scenario `Location` looks like:

~~~text
/orders/42?tab=history
~~~

`id` expands the `{id}` placeholder, while `tab` has no matching placeholder and is therefore appended as a query parameter. Redirect attributes are formatted/encoded properly for URI usage; avoid manually concatenating query strings from untrusted input.

Because URLs appear in browser history, bookmarks, analytics, `Referer` headers, and access logs, **never** pass access tokens, passwords, private emails, or sensitive data via `addAttribute`. Even a publicly exposed ID still requires authorization checks in the GET handler.

### 3.2. `addFlashAttribute` Delivers Data to the Target GET Request

~~~java
@PostMapping("/orders")
public String create(RedirectAttributes attrs) {
    attrs.addAttribute("id", 42);
    attrs.addFlashAttribute("notice", "Order created successfully");
    return "redirect:/orders/{id}";
}

@GetMapping("/orders/{id}")
public String detail(@PathVariable long id, Model model) {
    model.addAttribute("orderId", id);
    return "order-detail";
}
~~~

These are fragments of a controller with mappings and views declared. Spring MVC automatically promotes the flash attribute `notice` into the target GET's `Model` if the flash entry is still valid and the request matches.

In the Thymeleaf template:

~~~html
<p th:if="${notice != null}" th:text="${notice}"></p>
~~~

No `@RequestParam("notice")` is needed, because `notice` **is not a query parameter**. And the GET handler does not need to call `session.getAttribute` manually, since Spring manages the inbound `FlashMap` automatically.

### 3.3. `RedirectAttributes` Does Not Behave Like a Regular Model

Handler:

~~~java
@PostMapping("/preview")
public String preview(Model model, RedirectAttributes attrs) {
    model.addAttribute("preview", "Hello");
    attrs.addFlashAttribute("notice", "Saved");
    return "preview";
}
~~~

Because the handler returns the view `preview` with **no redirect**, do not expect `notice` to be forwarded to a later request. The regular `Model` serves rendering of the current request.

Spring MVC has a legacy compatibility rule regarding the default Model on redirect: simple model attributes can appear in the redirect URL if `RedirectAttributes` is not explicitly declared. `RequestMappingHandlerAdapter` provides `ignoreDefaultModelOnRedirect` to control this behavior. Declaring `RedirectAttributes` explicitly helps prevent unintended model attributes from leaking.

## 4. `FlashMap` and `FlashMapManager`

Spring MVC has two key abstractions:

- **`FlashMap`:** a map holding flash attributes plus metadata identifying the target request and expiration.
- **`FlashMapManager`:** manages saving/retrieving/removing `FlashMap` instances; the default MVC implementation is typically `SessionFlashMapManager`, storing them temporarily in the HTTP session.

Spring MVC exposes the concept of inbound/outbound maps per request:

- **Output `FlashMap`:** data placed in the source request to carry over to a future request.
- **Input `FlashMap`:** data received by the target request from a prior output.

**Detailed flow:**

~~~text
A. POST /orders
   Controller:
      attrs.addAttribute("id",42)
      attrs.addFlashAttribute("notice","OK")
      return "redirect:/orders/{id}"
   MVC/RedirectView:
      Expand URL to /orders/42
      Stamp output FlashMap with target path and query
      FlashMapManager saves output, typically in HTTP session
   Server -> Client:
      HTTP 302, Location: /orders/42
      Set-Cookie: JSESSIONID=... (if new session created)

B. GET /orders/42, keeping session cookie
   FlashMapManager finds map matching target
   Retrieves as input FlashMap, removes consumed map from storage
   MVC adds notice="OK" to Model
   GET controller loads order 42
   Template renders notice and order detail

C. Browser refreshes GET /orders/42
   Flash already consumed; model lacks notice from A
   Page still loads order 42 using URL and persistent data
~~~

A flash attribute is **not guaranteed** to appear exactly once under all circumstances. It can be lost due to timeouts/sessions or competing requests; therefore, treat it as a **best-effort temporary handoff to a matching request**, not a message queue with delivery guarantees.

### 4.1. Request Matching and URL Stamping

A hazard with flash attributes is that the "next request" could be a polling/AJAX call or asset fetch arriving before the browser's target GET. Spring MVC mitigates this by having `RedirectView` **stamp the target URL** (path and query parameters) onto the `FlashMap`, and the manager checks it upon retrieval:

~~~text
POST /orders -> Location: /orders/42?tab=summary
GET /api/notifications       -> normally does not match target
GET /orders/42?tab=summary   -> matches target, retrieves flash
~~~

Spring recommends flash primarily for redirect scenarios. Stamping reduces accidental pickup yet **does not eliminate all race conditions**, especially when multiple tabs sharing a session redirect to the same target path/query concurrently. If the target request fails after popping the flash map, the notice will also be gone on refresh.

### 4.2. Does Flash Create a Session?

Flash support is **always available** in Spring MVC, yet simply having it enabled does not force session creation when flash is unused. When output flash data actually needs saving, the default implementation uses the HTTP session.

Consequences:

- The client must retain the **session cookie** between POST and GET.
- If the session expires/invalidates or cookies are blocked, the notice may be lost.
- Multi-node applications must configure session sharing or sticky sessions if flash data must cross nodes.
- Objects stored in a distributed session may require proper serialization; prefer small, simple flash values.
- Flash does not replace a database and is not the sole receipt for a transaction.

### 4.3. Expiration and When Data Disappears

A `FlashMap` has a time-to-live. It can expire before the browser opens the target URL if the TTL elapses; the exact duration depends on the manager/configuration. Once the target GET retrieves the flash, the manager normally **removes the entry on retrieval** without waiting for user acknowledgment.

Never design business logic like "only succeed if the page reads the flash": the POST may have succeeded even if the flash message was lost. The source of truth for result data must be the database/GET resource.

### 4.4. When You Need to Access `FlashMap` Directly

You can access them via:

~~~java
Map<String, ?> input = RequestContextUtils.getInputFlashMap(request);
FlashMap output = RequestContextUtils.getOutputFlashMap(request);
~~~

Requires `org.springframework.web.servlet.support.RequestContextUtils`, `org.springframework.web.servlet.FlashMap`, and Servlet `request`. This fragment illustrates advanced usage. In normal controllers, **prefer `RedirectAttributes`** so Spring handles URL/flash extraction and storage.

When building low-level redirects manually (for example setting the `Location` header directly), the output `FlashMap` is not automatically stamped/saved through the view redirect mechanism. `RequestContextUtils.saveOutputFlashMap(location,request,response)` exists for such cases, though use it only when you intentionally manage the redirect flow.

## 5. Lifecycle of Valid and Invalid Forms

A typical MVC form handler:

~~~java
@PostMapping("/messages")
public String submit(
        @Valid @ModelAttribute("form") MessageForm form,
        BindingResult errors,
        RedirectAttributes attrs) {

    if (errors.hasErrors()) {
        return "message-form";
    }

    long id = saveMessage(form); // Illustrative service call.
    attrs.addAttribute("id", id);
    attrs.addFlashAttribute("notice", "Saved successfully");
    return "redirect:/messages/{id}";
}
~~~

**Success branch:** save data → new GET URL with ID → flash success message → redirect.

**Validation error branch:** keep the form and `BindingResult` in the **same request** → re-render the form; user sees field errors and entered values. `BindingResult` must come **immediately after** the corresponding `@ModelAttribute` parameter.

Why avoid redirecting when the form has errors?

- Error details and rejected values live in the current request's binding/model.
- A redirect starts a new request: unless you explicitly persist form/errors in flash, that state disappears.
- Flashing an entire form containing passwords, file uploads, large payloads, or sensitive data can be unsafe.
- No extra session flow complexity is needed for a straightforward form.

### 5.1. Can Flash Carry Validation Errors Across a Redirect?

Yes, if your architecture mandates strict PRG even on errors. Advanced fragment:

~~~java
attrs.addFlashAttribute("form", form);
attrs.addFlashAttribute(
        BindingResult.MODEL_KEY_PREFIX + "form", errors);
return "redirect:/messages/new";
~~~

Note the key `BindingResult.MODEL_KEY_PREFIX + "form"` must match the model attribute name. The GET form handler must also avoid overwriting the form/errors received from flash. However, flash carries session, TTL, concurrency, data-protection, and `BindingResult` complexity: **re-rendering the form in the same request on error** is usually much easier to maintain.

## 6. Comparing `RedirectAttributes`, Session, and URL

| Need | Suitable Approach | Consequence |
| --- | --- | --- |
| Path to a newly created resource | `addAttribute("id", id)` and `redirect:/resources/{id}` | Easy to bookmark, reload, and share |
| Active filter/tab/page | `addAttribute` | Stored in the URL |
| One-time notice after POST | `addFlashAttribute` | Temporary data; may be lost on timeout |
| Multi-step wizard data | `@SessionAttributes` or controlled backend session/state | Requires lifecycle management and cleanup |
| Durable business results | Database/repository | Re-fetchable on reload and after session expiry |
| REST API returning newly created result | `201 Created` + Location/JSON | Does not necessarily use HTML redirect |
| SPA/AJAX self-navigation | JSON response and client-side navigation | Do not rely on `fetch` auto-following redirects to switch screens |

`@SessionAttributes` is not flash: it is an MVC feature keeping selected model attributes across multiple requests in a controller flow, typically ending with `SessionStatus.setComplete()`. `@RequestAttribute` also differs: it reads an attribute from the **current request**, without automatically surviving a redirect.

## 7. Be Careful with HTTP Statuses and URLs

### 7.1. `RedirectView` and `303 See Other`

If you want 303 instead of 302:

~~~java
@PostMapping("/submit")
public RedirectView submit(RedirectAttributes attrs) {
    long id = save(); // Illustrative.
    attrs.addAttribute("id", id);
    RedirectView view = new RedirectView("/messages/{id}");
    view.setStatusCode(HttpStatus.SEE_OTHER);
    return view;
}
~~~

This fragment needs imports for `RedirectView`, `HttpStatus`, and the service. Verify URL expansion/encoding/contextPath for your setup. Concise `return "redirect:..."` is usually enough for MVC forms, while 303 communicates HTTP semantics more clearly if an API contract wants to enforce GET.

### 7.2. Do Not Leave Open Redirects

Wrong:

~~~java
return "redirect:" + request.getParameter("next");
~~~

If `next=https://evil.example`, the application can redirect users to an attacker-controlled domain for phishing. Use fixed internal routes, an allowlist of destinations, canonicalization, and scheme/host validation if return URLs are genuinely required.

### 7.3. Never Put Secrets in URLs or Arbitrarily in Flash

`addAttribute("token", secret)` leaks the token via browser history, `Referer`, and logs. Flash is absent from the URL yet may sit in the session, be rendered onto the target page, and face session fixation/hijacking risks if session management is weak. Never store credentials, access tokens, or domain objects with sensitive data in flash just because it is "hidden from the URL".

## 8. Complete Spring Boot 3.5 Project

Java 17 + Maven project: open a form to enter a message, submit POST, save in memory, and redirect to the detail page with a flash notice. Refreshing GET drops the notice while the message data remains in application memory.

### 8.1. Structure

~~~text
redirect-flash-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/RedirectFlashApplication.java
    │   └── resources/templates/
    │       ├── message-form.html
    │       └── message-detail.html
    └── test/java/demo/MessageControllerTest.java
~~~

### 8.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>redirect-flash-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 8.3. RedirectFlashApplication.java

All Java code below belongs in **a single file** `src/main/java/demo/RedirectFlashApplication.java`. One public top-level class matches the filename; the other classes are package-private.

~~~java
package demo;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

@SpringBootApplication
public class RedirectFlashApplication {
    public static void main(String[] args) {
        SpringApplication.run(RedirectFlashApplication.class, args);
    }
}

class MessageForm {
    @NotBlank
    @Size(max = 100)
    private String text;

    public MessageForm() {}

    public String getText() { return text; }
    public void setText(String text) { this.text = text; }
}

record Message(long id, String text) {}

@Controller
@RequestMapping("/messages")
class MessageController {
    private final Map<Long, Message> store = new ConcurrentHashMap<>();
    private final AtomicLong nextId = new AtomicLong();

    @GetMapping("/new")
    String newForm(Model model) {
        if (!model.containsAttribute("form")) {
            model.addAttribute("form", new MessageForm());
        }
        return "message-form";
    }

    @PostMapping
    String create(
            @Valid @ModelAttribute("form") MessageForm form,
            BindingResult errors,
            RedirectAttributes attrs) {

        if (errors.hasErrors()) {
            return "message-form";
        }

        long id = nextId.incrementAndGet();
        store.put(id, new Message(id, form.getText().trim()));

        attrs.addAttribute("id", id);
        attrs.addFlashAttribute(
                "notice", "Message created successfully");

        return "redirect:/messages/{id}";
    }

    @GetMapping("/{id}")
    String detail(@PathVariable long id, Model model) {
        Message message = store.get(id);
        if (message == null) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Message not found");
        }

        model.addAttribute("message", message);
        // notice is already placed in the model if an input FlashMap exists.
        return "message-detail";
    }
}
~~~

**Explanation:** A successful POST adds two kinds of attributes: `id` substitutes into the URL, and `notice` travels via flash. A failing POST re-renders the form so `BindingResult` remains available. The detail GET loads data by ID on its own without needing `notice` to work; refreshing GET still displays the message.

`ConcurrentHashMap`/`AtomicLong` allow the in-memory demo to serve multiple requests, yet this is not durable storage; restarting the app loses messages. Real applications require repositories/services, transactions, and authorization.

### 8.4. message-form.html

Place in `src/main/resources/templates/message-form.html`:

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Create Message</title>
</head>
<body>
  <h1>Create Message</h1>
  <form th:action="@{/messages}" th:object="${form}" method="post">
    <label for="text">Content</label>
    <input id="text" type="text" th:field="*{text}" maxlength="100">
    <div th:if="${#fields.hasErrors('text')}"
         th:errors="*{text}">Input error</div>
    <button type="submit">Create</button>
  </form>
</body>
</html>
~~~

`th:object` selects the form bean, and `th:field` binds the input to the `text` property. When `@NotBlank` or `@Size` fails, Thymeleaf reads field errors from `BindingResult` prepared by Spring in the model.

### 8.5. message-detail.html

Place in `src/main/resources/templates/message-detail.html`:

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Message Details</title>
</head>
<body>
  <p th:if="${notice != null}" th:text="${notice}">Created</p>
  <h1 th:text="${message.text}">Content</h1>
  <p>ID: <span th:text="${message.id}">0</span></p>
  <a th:href="@{/messages/new}">Create another message</a>
</body>
</html>
~~~

Use `th:text` to HTML-escape content automatically when rendering to the view. Never use `th:utext` with unsanitized user data as it can cause XSS. After refresh, `notice` is normally absent so the notice paragraph is hidden; `message` is reloaded from the store.

### 8.6. Starting and Observing in the Browser

Inside the `redirect-flash-demo` directory:

~~~bash
mvn spring-boot:run
~~~

Open `http://localhost:8080/messages/new`. Enter valid text and submit. The browser is redirected to `/messages/1` if it is the first creation; the flash notice appears only on the first target GET. Refresh the page: the message content stays while the notice disappears. Return to the form and submit an empty or whitespace-only string to test validation: the controller renders the form directly without redirecting.

### 8.7. Testing with curl and Session Cookies

~~~bash
curl -i -c cookies.txt -b cookies.txt \
  -X POST 'http://localhost:8080/messages' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'text=Hello Spring'
~~~

When it is the first record, the redirect response has Location `/messages/1` (and possibly `Set-Cookie` for the HTTP session). Then:

~~~bash
curl -i -c cookies.txt -b cookies.txt \
  'http://localhost:8080/messages/1'
~~~

Next GET in the same session:

~~~bash
curl -i -c cookies.txt -b cookies.txt \
  'http://localhost:8080/messages/1'
~~~

The first GET contains the notice HTML; the second GET no longer has the notice. Without preserving cookies, the flash attribute can be lost. On Windows PowerShell, use `curl.exe` on a single line or with PowerShell line continuation; `\` in the examples is for Bash.

Do not use `curl -L -X POST` to infer PRG behavior: depending on options, cURL may continue issuing POST when following redirects. Separate POST and GET commands clearly show the redirect URL, HTTP status, and session cookie.

### 8.8. MockMvc Testing

Create `src/test/java/demo/MessageControllerTest.java`:

~~~java
package demo;

import jakarta.servlet.http.HttpSession;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.flash;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.model;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrlPattern;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.view;

@SpringBootTest
@AutoConfigureMockMvc
class MessageControllerTest {
    @Autowired MockMvc mvc;

    @Test
    void validPostRedirectsAndStoresFlash() throws Exception {
        mvc.perform(post("/messages").param("text", "Hello"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("/messages/*"))
            .andExpect(flash().attribute(
                    "notice", "Message created successfully"));
    }

    @Test
    void invalidPostRendersTheForm() throws Exception {
        mvc.perform(post("/messages").param("text", "  "))
            .andExpect(status().isOk())
            .andExpect(view().name("message-form"))
            .andExpect(model().attributeHasFieldErrors("form", "text"));
    }

    @Test
    void noticeExistsOnFirstMatchingGetOnly() throws Exception {
        MvcResult postResult = mvc.perform(
                post("/messages").param("text", "Once"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        String location = postResult.getResponse().getRedirectedUrl();
        assertNotNull(location);
        HttpSession session = postResult.getRequest().getSession(false);
        assertNotNull(session);
        MockHttpSession mockSession = (MockHttpSession) session;

        mvc.perform(get(location).session(mockSession))
            .andExpect(status().isOk())
            .andExpect(view().name("message-detail"))
            .andExpect(model().attribute(
                    "notice", "Message created successfully"));

        mvc.perform(get(location).session(mockSession))
            .andExpect(status().isOk())
            .andExpect(model().attributeDoesNotExist("notice"));
    }
}
~~~

Run:

~~~bash
mvn test
~~~

The tests verify the redirect `Location`, flash in the outbound `FlashMap`, loading of flash on the first GET, and its absence on the second GET. Reading the actual redirect URL avoids assuming fixed IDs across tests. This is an MVC **MockMvc test**; testing real browser session cookies, multi-node setups, proxies, timeouts, or concurrent tabs requires additional integration/E2E tests.

## 9. Common Mistakes

1. **Using `addAttribute` for private notices:** the message can appear in the query string and leak via history/logs. Use flash for small notices; never use flash for secrets.
2. **Forgetting to redirect:** calling `addFlashAttribute` when the handler returns a regular view. Flash is not automatically carried over to the target request.
3. **Dropping the session cookie:** POST and GET run in two different sessions, so GET never sees the flash attribute.
4. **Setting the `Location` header manually without saving `FlashMap`:** low-level redirects can bypass `RedirectView`'s lifecycle.
5. **Making the detail GET depend on flash:** refreshing or losing the session breaks the page. GET must fetch the resource by URL ID.
6. **Redirecting on validation failure without carrying form/`BindingResult`:** users see no errors; for standard form errors, re-render the same view.
7. **Using flash as a queue or durable storage:** data has a TTL, is consumed once, and can be lost under concurrency.
8. **Redirecting to the same target from multiple tabs:** URL stamping cannot fully disambiguate flash maps sharing the same target URL.
9. **Assuming PRG prevents all duplicate writes:** server-side idempotency protection is still needed for critical write operations.
10. **Using `@SessionAttributes` instead of flash:** session attributes live across multiple requests and require explicit completion, so notices may display repeatedly.
11. **Concatenating redirect URLs from untrusted values:** open redirect risk and broken encoding.
12. **Using browser `fetch` to auto-follow redirects while expecting full page navigation:** AJAX/SPA apps usually need client-side navigation and dedicated state handling.
13. **Forgetting CSRF protection on form POSTs when Spring Security is present:** PRG does not stop CSRF; enable CSRF per policy instead of disabling it for demos.
14. **Ignoring URL/query stamping behind a reverse proxy:** URL rewrites or altered query params can stop flash from matching the target request.
15. **Putting entities or large payloads in flash:** creates session serialization, memory, and privacy risks.

## 10. Practice Exercises

**Exercise 1.** A POST creates order ID 123, and GET displays `/orders/123`. Write a snippet using `addAttribute("id", 123)` and `addFlashAttribute("notice", "Order created")`. State which field appears in the URL and which is rendered only once.

**Exercise 2.** Diagram the POST → 302 → GET → refresh GET sequence. Identify when the output `FlashMap` is saved, when the input `FlashMap` is popped, and when the data is discarded.

**Exercise 3.** Why must `BindingResult` immediately follow `@ModelAttribute` in form validation? On error, should you return the form or redirect, and if redirecting, what needs to be preserved?

**Exercise 4.** Compare `addFlashAttribute` with `@SessionAttributes` for a wizard retaining data across four steps. Why could flash data disappear before reaching step 4?

**Exercise 5.** Two tabs in the same session POST and redirect to `/profile` with two different notices. Explain why URL stamping does not guarantee the right notice in each tab and suggest how to adjust the flow.

**Exercise 6.** A client sends `next=https://attacker.example`. Why can `return "redirect:" + next` be dangerous? Design an allowlist of internal destinations.

**Exercise 7.** In MockMvc, how do you assert outbound flash, capture the actual redirect URL, pass the same `MockHttpSession` to the first GET, and verify the flash attribute is gone on the second GET?

**Exercise 8.** If a POST creates an order successfully but the cookie is not sent on GET, how do the domain outcome and flash notice differ? How should the GET page behave?

## 11. Takeaways

- **PRG** prevents refreshing a result page from accidentally resending a POST, yet does not guarantee strict idempotency.
- **`RedirectAttributes.addAttribute`** creates URL/path/query state; use it only for data safe to expose publicly.
- **`RedirectAttributes.addFlashAttribute`** creates temporary data for a **matching target request**; backed by the HTTP session by default and subject to expiration.
- **`FlashMap` + `FlashMapManager`** handle saving, target matching, adding to the model, and consuming; URL stamping reduces but does not eliminate race conditions.
- **Validation errors usually re-render the form in the same request** to preserve `BindingResult`. **Success usually redirects** with a flash notice.
- Flash is a UX convenience, not a database, session wizard, secret store, or guaranteed delivery queue.

## 12. References

- [Spring Framework 6.2 — Redirect Attributes](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/redirecting-passing-data.html).
- [Spring Framework 6.2 — Flash Attributes](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/flash-attributes.html).
- [Spring MVC — RedirectAttributes API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/support/RedirectAttributes.html).
- [Spring MVC — FlashMap API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/FlashMap.html).
- [Spring MVC — RedirectView API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/view/RedirectView.html).
- [Spring MVC — Thymeleaf Views](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc-view/mvc-thymeleaf.html).
