# Testing Views, Forms, Redirects, Flash Attributes, and Sessions in Spring MVC

An HTML web flow may return the form page again on invalid input, or accept a successful POST and redirect to another GET endpoint. Testing this flow properly must inspect **which view was selected, which model was passed to the view, whether form data was bound and validated, where the response redirected, which request received the flash message, and whether session state persists across its intended lifecycle**.

This covers Servlet-based Spring MVC, applying to `@Controller` classes that return HTML/views (unlike `@RestController` endpoints that mainly return JSON). Examples use Java 17+, Spring Boot 3.3, and JUnit 5 for easy runnable setup; views, models, `RedirectAttributes`, and sessions belong to Spring MVC.

## 1. Looking at the whole flow, not just one status code

Suppose there is a registration page at `GET /signup` and the form submits to `POST /signup`:

```text
GET /signup
  → controller initializes form object into Model
  → view "signup/form"
  → browser receives HTML page with <form>

POST /signup, name="  " (invalid)
  → data binding + Bean Validation
  → BindingResult contains errors
  → returns view "signup/form" with errors, NO redirect

POST /signup, name="An" (valid)
  → processes form
  → stores attribute lasting longer than one request in HttpSession
  → addFlashAttribute("notice", ...)
  → 3xx response + Location: /signup/done

GET /signup/done (same session)
  → flash message becomes an attribute in Model
  → view "signup/done" displays result
  → flash has been removed from temporary storage

GET /signup/done again (same session)
  → flash "notice" is gone
  → session attribute still remains if not removed
```

The successful flow is the **Post/Redirect/Get (PRG)** pattern. The browser receives the POST result via a redirect, then switches to GET; refreshing the result page normally does not re-submit the POST. PRG reduces the risk of form resubmission on refresh, though it does not guarantee protection against all duplicate POSTs: critical data-mutating operations still need business-layer controls, such as an idempotency key or unique constraint where appropriate.

| Component | Where / how long data lives | What to assert |
| --- | --- | --- |
| View name | Handler's view selection result | `view().name("signup/form")` |
| Model | Attributes passed to the view for the request | `model().attributeExists(...)`, `model().attribute(...)` |
| Form binding / validation | Request parameters → form object; errors in `BindingResult` | `model().attributeHasFieldErrors(...)` or `attributeHasNoErrors(...)` |
| Redirect | 3xx HTTP response with `Location` header | `status().is3xxRedirection()`, `redirectedUrl(...)` |
| Flash attribute | Temporary data carried to the target request, usually stored via session | `flash().attribute(...)` on POST, `model().attribute(...)` on GET after redirect |
| Session attribute | Session-bound state that can span multiple requests | `session().attribute(...)` with the same `MockHttpSession` |

**Note:** `MockMvc` uses simulated Servlet requests/responses and can execute MVC, view resolution, and configured template rendering, but does not open an HTTP socket. `andExpect(redirectedUrl(...))` checks redirect metadata; it **does not automatically perform the follow-up GET**. To test the full PRG flow, the test must issue a separate GET carrying the same session.

## 2. Preparing a runnable example

Example structure:

```text
src/main/java/com/example/webtest/
  WebTestApplication.java
  SignupForm.java
  SignupController.java
src/main/resources/templates/signup/
  form.html
  done.html
src/test/java/com/example/webtest/
  SignupControllerWebTest.java
```

Use a Spring Boot 3.3 project (Java 17+) with the following Gradle dependencies; Spring Boot plugin/version configuration remains managed by the main build:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-validation` supplies the Bean Validation implementation for `@NotBlank`/`@Valid`. `spring-boot-starter-thymeleaf` renders real views using templates, allowing HTML output assertions in addition to view name and model. If the real application uses JSP or another view resolver, configure the corresponding engine and environment; never assume a correct view name means the template file exists.

File `WebTestApplication.java`:

```java
package com.example.webtest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebTestApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebTestApplication.class, args);
    }
}
```

File `SignupForm.java`:

```java
package com.example.webtest;

import jakarta.validation.constraints.NotBlank;

public class SignupForm {
    @NotBlank(message = "Name must not be blank")
    private String name;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
```

File `SignupController.java`:

```java
package com.example.webtest;

import jakarta.servlet.http.HttpSession;
import jakarta.validation.Valid;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

@Controller
@RequestMapping("/signup")
public class SignupController {

    @GetMapping
    public String showForm(Model model) {
        model.addAttribute("signupForm", new SignupForm());
        return "signup/form";
    }

    @PostMapping
    public String submit(
            @Valid @ModelAttribute("signupForm") SignupForm form,
            BindingResult errors,
            RedirectAttributes redirect,
            HttpSession session) {

        if (errors.hasErrors()) {
            return "signup/form";
        }

        session.setAttribute("lastName", form.getName());
        redirect.addFlashAttribute("notice", "Registration successful");
        return "redirect:/signup/done";
    }

    @GetMapping("/done")
    public String done(Model model, HttpSession session) {
        model.addAttribute("lastName", session.getAttribute("lastName"));
        return "signup/done";
    }

    @GetMapping("/reset")
    public String reset(HttpSession session) {
        session.removeAttribute("lastName");
        return "redirect:/signup";
    }
}
```

Place `BindingResult` **immediately after** the `@Valid @ModelAttribute` parameter it validates. When data is invalid, the controller returns the form along with binding/validation errors in the model; placing `BindingResult` in the wrong position or failing to handle errors can turn the behavior into an exception instead of displaying form errors.

The code above intentionally stores only a name in the session for illustration; real applications must handle business rules, authorization, and sensitive data per system requirements. Never use `HttpSession` as a shared data store across users.

File `templates/signup/form.html`:

```html
<!doctype html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head><meta charset="UTF-8"><title>Sign up</title></head>
<body>
<h1>Enter name</h1>
<form th:action="@{/signup}" th:object="${signupForm}" method="post">
    <label for="name">Name</label>
    <input id="name" type="text" th:field="*{name}">
    <p th:if="${#fields.hasErrors('name')}"
       th:errors="*{name}">Name input error</p>
    <button type="submit">Submit</button>
</form>
</body>
</html>
```

File `templates/signup/done.html`:

```html
<!doctype html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head><meta charset="UTF-8"><title>Result</title></head>
<body>
<h1>Sign up</h1>
<p id="notice" th:text="${notice}">Notice</p>
<p id="name" th:text="${lastName}">Entered name</p>
</body>
</html>
```

Thymeleaf automatically uses `BindingResult` to render `th:errors`. Model attributes are data the server passes to the view; browsers cannot directly access Java objects. The corresponding template is what turns that content into HTML.

## 3. Testing GET: view name, model, and rendered HTML

Use `@WebMvcTest(SignupController.class)` to load the web slice with `MockMvc`. This test verifies routing, binding, validation, view resolvers/templates available in the slice, and the simulated session; it does not start a real server or prove external services.

File `src/test/java/com/example/webtest/SignupControllerWebTest.java`:

```java
package com.example.webtest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.flash;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.model;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.session;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.view;

@WebMvcTest(SignupController.class)
class SignupControllerWebTest {

    @Autowired
    MockMvc mvc;

    @Test
    void getFormReturnsViewModelAndRenderedHtml() throws Exception {
        mvc.perform(get("/signup"))
                .andExpect(status().isOk())
                .andExpect(view().name("signup/form"))
                .andExpect(model().attributeExists("signupForm"))
                .andExpect(content().string(containsString("Enter name")))
                .andExpect(content().string(containsString("name=\"name\"")));
    }

    @Test
    void invalidFormShowsFieldErrorWithoutRedirect() throws Exception {
        mvc.perform(post("/signup").param("name", "   "))
                .andExpect(status().isOk())
                .andExpect(view().name("signup/form"))
                .andExpect(model().attributeHasFieldErrors(
                        "signupForm", "name"))
                .andExpect(content().string(
                        containsString("Name must not be blank")));
    }

    @Test
    void successRedirectsAndCarriesFlashAcrossOneGet() throws Exception {
        MockHttpSession browserSession = new MockHttpSession();

        mvc.perform(post("/signup")
                        .session(browserSession)
                        .param("name", "An"))
                .andExpect(status().is3xxRedirection())
                .andExpect(view().name("redirect:/signup/done"))
                .andExpect(redirectedUrl("/signup/done"))
                .andExpect(flash().attribute(
                        "notice", "Registration successful"))
                .andExpect(session().attribute("lastName", "An"));

        mvc.perform(get("/signup/done").session(browserSession))
                .andExpect(status().isOk())
                .andExpect(view().name("signup/done"))
                .andExpect(model().attribute(
                        "notice", "Registration successful"))
                .andExpect(model().attribute("lastName", "An"))
                .andExpect(content().string(
                        containsString("Registration successful")));

        mvc.perform(get("/signup/done").session(browserSession))
                .andExpect(status().isOk())
                .andExpect(model().attributeDoesNotExist("notice"))
                .andExpect(model().attribute("lastName", "An"));
    }

    @Test
    void resetRemovesPersistentSessionAttribute() throws Exception {
        MockHttpSession browserSession = new MockHttpSession();
        browserSession.setAttribute("lastName", "An");

        mvc.perform(get("/signup/reset").session(browserSession))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/signup"))
                .andExpect(session().attributeDoesNotExist("lastName"));
    }
}
```

Run tests with the Gradle wrapper from the project directory:

```bash
./gradlew test --tests com.example.webtest.SignupControllerWebTest
```

On Windows PowerShell, you can use `.\gradlew.bat test --tests com.example.webtest.SignupControllerWebTest`. The assertions above describe the **expected results** of the example, not published test execution logs. The project needs the exact dependencies, classes, and templates shown; if a template is missing, an error may occur during view resolution/rendering even if the controller selects the right logical view name.

### Why assert both view and HTML?

`view().name("signup/form")` proves the handler picked the right logical view. It does not yet prove the view engine found the template and rendered the right content. When Thymeleaf is loaded with `form.html` and `done.html`, checking `content().string(...)` adds evidence that the returned HTML contains the important parts.

Do not compare the entire HTML string if the goal is merely confirming a label, validation error, or input field; whitespace formatting, HTML attribute ordering, or layout can change while functionality remains right. If you need to verify DOM structure and JavaScript behavior, use an appropriate HTML/DOM testing tool or browser; `MockMvc` does not execute browser JavaScript.

## 4. Testing form binding and validation

In the example, `post("/signup").param("name", "   ")` creates a decoded Servlet request parameter; the MVC binder assigns the value to `SignupForm.name` before `@Valid` checks `@NotBlank`. Important cases should be separated clearly:

- **Valid form:** attribute `signupForm` binds cleanly, `BindingResult` has no errors, and the controller redirects.
- **Validation-error form:** MVC binds the value, yet constraints fail; the controller re-renders the form with field errors and does not execute business success logic.
- **Type-conversion-error form:** a numeric field receiving invalid characters can produce a binding/conversion error; assert the appropriate field/object error rather than assuming it is the same as `@NotBlank`.
- **Missing parameter:** depending on data type and constraints, the field may be `null` or a default value; tests must reflect the actual contract rather than guessing.
- **Test-simulated form data:** `.param("name", "An")` adds a simulated request parameter; it does not test a real browser submitting a form or network-level multipart/form encoding.

An assertion focused on a valid form can use `model().attributeHasNoErrors("signupForm")` when the response actually has the form attribute in the model. In the success pattern, the controller returns a **redirect**, so asserting the redirect and flash/session is more appropriate than expecting the form model to remain on the redirect response.

`@InitBinder` and custom validators can be used if business rules require them. In that case test with the same binder/validator configuration as the app; instantiating the controller directly in a unit test will not run through the MVC data binder.

## 5. Redirects: checking Location and PRG

In the controller, `return "redirect:/signup/done"` instructs Spring MVC to produce a redirect response. Tests should verify both that the response is 3xx and the target URL:

```java
mvc.perform(post("/signup").param("name", "An"))
        .andExpect(status().is3xxRedirection())
        .andExpect(redirectedUrl("/signup/done"));
```

This standalone check only illustrates the matchers; the complete test earlier reuses `MockHttpSession` to track state. To confirm a specific HTTP code required by a contract, assert `status().isFound()` for 302, or 303 when the app explicitly returns “See Other”. Do not assume Spring MVC always defaults to 303 just because the code follows PRG.

`redirectedUrl(...)` checks the URL in the redirect; `header().string("Location", "...")` can also be used to inspect the header directly. `view().name("redirect:/signup/done")` is the MVC-side logical view name; a real HTTP client never sees that logical view name—it sees the response status and header.

`RedirectAttributes` has two distinct delivery channels:

```java
// Illustrated inside a redirect-handling method:
redirect.addAttribute("page", 2);          // May go into the URL path/query
redirect.addFlashAttribute("notice", "OK"); // Via FlashMap, not in the URL
```

`addAttribute` uses values to expand URI templates or append query parameters depending on the redirect target and configuration. `addFlashAttribute` stores temporary data for the post-redirect request (usually backed by the HTTP session). Never put passwords, tokens, or sensitive data in the query string just to pass them from POST to GET; URLs can appear in logs, history, and referrers.

## 6. Flash attributes: two sides and one-time use

Flash attributes are data kept **across requests** to show a message after a redirect. Spring MVC manages them via `FlashMap` and `FlashMapManager`. Controllers use `RedirectAttributes.addFlashAttribute`, so they normally do not interact with `FlashMap` directly.

There are two distinct checks:

1. **POST output flash map:** `flash().attribute("notice", "...")` shows the handler prepared the message to pass forward.
2. **Target GET input/model:** `model().attribute("notice", "...")` on `GET /signup/done` proves the destination request received the message.

The third check in the example—calling `GET /signup/done` a second time with the same session and asserting `model().attributeDoesNotExist("notice")`—tests the one-time consumption behavior. Session attribute `lastName` remains, clearly distinguishing flash attributes from longer-lived session data.

**Do not equate:** writing `.flashAttr("notice", "OK")` directly on a GET request in a test is a way to **inject an input flash attribute** to test the target view; it is useful for isolating the view, but does not prove the POST created the flash or that `FlashMapManager` saved and consumed it. To test the full PRG flow as shown here, run real POST and GET calls with two `MockMvc.perform` invocations sharing one `MockHttpSession`.

Spring MVC attaches redirect target metadata to the flash map to reduce the chance of another request picking up the message by mistake. Even so, concurrent requests (polling, assets, or AJAX in some scenarios) can create race conditions; do not use flash as a business queue requiring guaranteed delivery or as long-term result storage.

## 7. Session: sharing one session across multiple requests

An HTTP session can preserve state across multiple requests from the same client. In `MockMvc` tests, two independent `perform` calls do not represent the same browser unless you reuse the session. Therefore we create a `MockHttpSession` and pass it to requests with `.session(browserSession)`:

```java
MockHttpSession browserSession = new MockHttpSession();
browserSession.setAttribute("theme", "dark");

mvc.perform(get("/signup/done").session(browserSession))
        .andExpect(session().attribute("theme", "dark"));
```

In a running application, clients typically send a session ID cookie such as `JSESSIONID` while the server manages that session's data; cookie names, session stores, and protection policies depend on Servlet container/Spring Session configuration. `MockHttpSession` only tests state at the simulated Servlet layer—it does not prove browser cookies are protected by `Secure`, `HttpOnly`, `SameSite`, or that a distributed session store works properly.

To verify the session is cleaned up at the right time, `/signup/reset` calls `session.removeAttribute("lastName")`; the test uses `session().attributeDoesNotExist("lastName")`. When the application needs to terminate the **entire** session, `session.invalidate()` is a separate operation affecting all session attributes; test according to your app's logout and security policies.

### HttpSession vs. @SessionAttributes

`HttpSession` is the Servlet API for session-scoped data. `@SessionAttributes` on a `@Controller` class is a Spring MVC mechanism that promotes selected **controller-managed model attributes** into the session to support multi-step forms/wizards:

```java
// Conceptual example; not a complete standalone runnable controller.
@Controller
@SessionAttributes("draft")
class DraftController {
    // A model with attribute "draft" will be stored in the session.
    // When the conversation ends, the handler accepts SessionStatus:
    // status.setComplete();
}
```

`SessionStatus.setComplete()` ends retention of model attributes declared by the controller with `@SessionAttributes`; it **does not mean** invalidating the entire `HttpSession` and does not replace logout logic. For multi-step forms, tests should verify the draft survives across the required requests and is cleared after `setComplete()`; for the single-step form in this example, using `HttpSession` directly suffices to demonstrate state.

Session data can introduce coupling between test cases. Create a fresh `MockHttpSession` per test or clean fixtures explicitly; never share one static session so test execution order affects outcomes.

## 8. Key considerations when writing real-world tests

**Web slice configuration:** `@WebMvcTest` is a Spring Boot annotation; it loads the relevant MVC slice, not all application services/repositories. Controllers with dependencies outside the slice need explicit mocks (in Boot 3.3, typically `@MockBean`). To verify real bean wiring, consider `@SpringBootTest` with `@AutoConfigureMockMvc`; there is still no HTTP socket unless you use a real server and network HTTP client. View, model, flash, and session matchers remain useful in MockMvc with a broader context.

**Security/CSRF:** if `spring-boot-starter-security` is added, form POSTs may be blocked with 403 before reaching the controller if a CSRF token or permission is missing. When testing secured flows, add `spring-security-test` and supply authentication/CSRF matching the test case, e.g., `post("/signup").with(csrf())` with static import `org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf`. Never disable security filters just to turn a form test green and treat it as security verification.

**View names vs. real HTTP:** with `MockMvc`, `view().name(...)` and `model()` are Spring MVC-layer assertions; with an HTTP client hitting a real port, only observable status/headers/body/cookies and public behavior exist. If an endpoint serves an SPA or JSON responses, asserting logical view names is no longer the relevant contract.

**Redirect chains:** `MockMvc` does not follow redirects automatically. Tests may need multiple sequential `perform` calls; a test checking only 302 will miss a flash attribute failing to arrive, a lost session, or a broken GET view.

**Form data and encoding:** `.param(...)` supplies already-decoded parameters. If specifications require UTF-8 handling, payload limits, multipart file uploads, or real proxy/client behavior, add tests at the layer where those issues can arise.

**Validation errors:** never assert only `status().isOk()` on a failed POST and conclude the user saw an error. Check `BindingResult` and/or the rendered HTML message. Testing type conversion errors and business errors (such as duplicate names) are distinct scenarios; each needs its own expected outcome.

**Session reliability:** flash usually uses the session as temporary storage, yet has a different lifecycle from session attributes. Avoid using flash to hold large objects or critical state that must persist across multiple requests; avoid storing non-serializable resources if the system plans to use a distributed session store.

## 9. Checklist before concluding a form flow is tested

| Step | Question to prove | Typical assertion |
| --- | --- | --- |
| GET form | Did it pick the right view and provide the form object? | `view().name`, `model().attributeExists` |
| Render form | Does the HTML contain the required fields and labels? | `content().string(containsString(...))` |
| Invalid POST | Did it bind/validate, return the form, and show field errors? | `attributeHasFieldErrors`, `view().name` |
| Valid POST | Did it redirect instead of rendering the result page directly? | `is3xxRedirection`, `redirectedUrl` |
| Flash after POST | Was the message placed in the output flash? | `flash().attribute` |
| GET after redirect | Did the target request receive and display the message? | `model().attribute` and HTML content |
| Subsequent GET | Does the temporary message no longer appear? | `attributeDoesNotExist` |
| Same session | Are attributes preserved across multiple requests? | Reuse `MockHttpSession`, `session().attribute` |
| Cleanup state | Are attributes removed when the workflow finishes? | `session().attributeDoesNotExist` |

Separating these questions helps distinguish controller/model bugs, template rendering bugs, validation bugs, redirect bugs, and state lifecycle bugs. A strong test is one that provides the exact **evidence for the user contract needed**, with an appropriately configured MVC context.

### References

- Spring Framework — MockMvc expectations: https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/expectations.html
- Spring Framework — MockMvc requests: https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/requests.html
- Spring Framework — Redirect attributes: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/redirecting-passing-data.html
- Spring Framework — Flash attributes: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/flash-attributes.html
- Spring Framework — @SessionAttributes: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/sessionattributes.html
- Spring Boot 3.3 — Testing Spring Boot applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
