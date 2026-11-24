# Form Page Practice: Views, Localization, Session, and Redirects in Spring MVC

## 1. Practice problem and target outcome

A traditional web form page has more responsibilities than receiving a few strings and calling a service. Spring MVC must render an HTML view, bind form fields into a Java object, validate data, preserve user-entered inputs, select the UI language, maintain state across requests, and navigate after a successful save.

In this lesson, we build a **registration page with draft saving**:

1. The user opens `GET /form` and sees a Thymeleaf page in English.
2. Clicking the `?lang=vi` link switches labels and messages to Vietnamese and remembers the choice in the HTTP session.
3. Entering name, email, and notes and clicking **Save draft**; the server keeps the draft in the session and redirects back to `GET /form`.
4. Clicking **Submit registration**; if name/email is invalid, the server re-renders the form with errors without redirecting.
5. If data is valid, the server marks completion, removes the controller-managed draft from the session, sets a flash message, and redirects to `GET /done`. Refreshing the result page does not resubmit the POST.

This lesson demonstrates **Spring MVC Servlet + Thymeleaf + Jakarta Bean Validation**, using Java 17 and Spring Boot 3.3.x (Spring Framework 6.1). The demo does not write to a database: "completed" only verifies that the HTTP/view flow works. Production applications need dedicated service, transaction, security, and idempotency layers.

Learning goals: understand `Model`, logical view names, `th:object`/`th:field`, `MessageSource` and locales, `@SessionAttributes`/`SessionStatus`, `RedirectAttributes.addFlashAttribute`, Post/Redirect/Get (PRG), and how to test each form stage with MockMvc.

## 2. Request flow of an MVC form

~~~mermaid
flowchart TD
    A[GET /form] --> B[DispatcherServlet]
    B --> C[Controller returns logical view 'form']
    C --> D[Thymeleaf renders HTML from model + messages]
    D --> E[Browser displays form]
    E --> F{POST /form with action}
    F -->|save| G[Bind draft and keep in session]
    G --> H[Flash saved=true]
    H --> I[302 Location: /form]
    I --> A
    F -->|finish| J[Bind + Jakarta Validation]
    J -->|Invalid| K[BindingResult has field errors]
    K --> C
    J -->|Valid| L[SessionStatus.setComplete]
    L --> M[Flash completedName]
    M --> N[302 Location: /done]
    N --> O[GET /done renders view 'done']
~~~

This is a multi-request HTTP flow. The **view** is rendered into HTML by the template engine; the **model** holds data exposed to the template. When a controller returns `"form"`, Spring uses a view resolver to locate the template (e.g., `templates/form.html`). When it returns `"redirect:/form"`, Spring emits an HTTP redirect so the browser **issues a new GET request**; it does not render the `form` view directly inside the POST.

| Controller return value | What Spring does | Browser URL |
| --- | --- | --- |
| `"form"` | Renders template `form.html` in the current request | Keeps request URL |
| `"done"` | Renders template `done.html` | Keeps request URL |
| `"redirect:/form"` | Sends redirect with Location `/form` | Browser navigates to `/form` |
| `"forward:/form"` | Forwards server-side to another handler | Browser usually keeps the URL |

Redirect after a **successful POST**, and do not blindly redirect when `BindingResult` has errors. If you redirect on validation failure without explicitly preserving `BindingResult` and form values, errors and user input vanish. Returning the `form` view directly on error is both simpler and preserves the request's binding result.

## 3. Thymeleaf views, binding, and data validation

### 3.1. Model and template

In Spring Boot with the Thymeleaf starter, `src/main/resources/templates/form.html` is the HTML view; the controller returns the logical view name `"form"`. The template reads model attributes supplied by the controller. Example Thymeleaf snippet:

~~~html
<form th:action="@{/form}" th:object="${draft}" method="post">
  <input type="text" th:field="*{name}">
  <span th:if="${#fields.hasErrors('name')}"
        th:errors="*{name}">Name error</span>
  <button name="action" value="finish" type="submit">Submit</button>
</form>
~~~

This is a fragment to illustrate syntax, not a complete page. `th:object` points to the **model attribute** `draft`. `th:field` generates the name/id/value matching the object's property; if Spring hits binding errors, the template re-displays the user's entered value along with the matching `BindingResult`.

Distinguish clearly:
- HTML `name="action"` is a **submit-button control parameter** (`save` or `finish`) sent by the browser.
- `name`, `email`, and `note` are fields on `draft`, bound via JavaBean setters.
- `@Valid` triggers Bean Validation on the object in the final submit handler; `BindingResult` must sit **immediately after** the validated argument.
- `th:errors` retrieves error messages from Bean Validation/binding, whereas `#{form.title}` reads UI text from the message bundle.

### 3.2. Client vs. server boundaries

HTML attributes like `required` and `maxlength` improve UX, yet can be bypassed via cURL, bots, or custom clients. Constraints must be re-enforced on the server with `@NotBlank`, `@Email`, `@Size`, and business checks.

Fields such as `id`, `role`, `price`, and `owner` must not appear on a freely bound form object if clients are not allowed to modify them. Use a dedicated input DTO; never bind an entire entity containing sensitive fields directly.

## 4. Localization: MessageSource, LocaleResolver, interceptor

Spring MVC selects a `Locale` for the request and passes it to Spring's message resolver and the template engine. For instance, with `messages.properties` (default English) and `messages_vi.properties` (Vietnamese):

~~~properties
form.title=Registration form
form.name=Name
form.submit=Submit registration
~~~

~~~properties
form.title=Biểu mẫu đăng ký
form.name=Họ tên
form.submit=Gửi đăng ký
~~~

In the Thymeleaf view, `<h1 th:text="#{form.title}">` displays the string for the active locale. **MessageSource** manages UI strings; it does not translate database contents automatically or localize business errors that were not designed for i18n.

Two common strategies:
- `AcceptHeaderLocaleResolver`: infers locale from the `Accept-Language` header; fits cases where users change language via browser/header. This resolver **does not support changing locale via an interceptor calling setLocale** in the usual way.
- `SessionLocaleResolver`: reads/writes the chosen locale in `HttpSession`; fits session-based examples. `LocaleChangeInterceptor` watches `?lang=vi` or `?lang=en` and invokes the resolver to change the language, persisting across subsequent requests in the same session.

The demo uses `SessionLocaleResolver`. When the session expires or the browser drops the cookie, the language falls back to default (English here). Provide clear language choices, restrict supported locales in production, and test all required message keys.

**Validation messages** live in separate resource bundles in the example (`ValidationMessages.properties`, `ValidationMessages_vi.properties`) keyed by the constraint annotations. This lets tests verify both UI labels and validation messages per locale instead of hardcoding English in Java.

## 5. Session, flash attributes, and redirects: three lifecycles

### 5.1. @SessionAttributes and SessionStatus

`@SessionAttributes("draft")` on the **controller class** tells Spring to store the model attribute named `draft` in the HTTP session across requests of that workflow. When `@ModelAttribute("draft")` first runs, the object is created and saved; subsequent GET/POST requests retrieve it from the session.

`SessionStatus.setComplete()` marks the workflow complete so Spring **removes model attributes managed by @SessionAttributes** after the handler runs. It **does not call `HttpSession.invalidate()`**, because invalidating would wipe login state, locale, and other user workflows. Drafts are temporary state; the app must still handle session timeouts or concurrent tabs sharing a session overwriting each other.

Do not confuse:
- `@SessionAttributes` (plural, class-level): selects model attributes Spring automatically manages for a controller workflow.
- `@SessionAttribute` (singular, method parameter): reads an existing session attribute, typically managed elsewhere.
- `HttpSession`: Servlet API to read/write/remove session data manually, suited when state ownership is explicit.
- `SessionLocaleResolver`: also uses the HTTP session, yet stores the **locale** separately rather than the `draft`.

Sessions are usually identified via the `JSESSIONID` cookie, though session data does not necessarily live inside the cookie itself; in typical Servlet apps, data lives on the server. When running multiple instances, configure session stickiness or shared session storage (such as Spring Session with Redis) and plan for serialization and TTLs.

### 5.2. RedirectAttributes and flash

After saving a draft, we add `saved=true` via `RedirectAttributes.addFlashAttribute`. Spring stores flash attributes **temporarily** for the post-redirect request (typically via session/FlashMap), moves them into the next GET's model, and then removes them. This is a mechanism for short-lived UI status like "saved," not long-term workflow storage.

In the demo, `completedName` appears on the result page only right after a valid POST. It is **not in the query string** because it is passed as flash data. If a user opens `GET /done` directly without flash data, the controller redirects back to `/form`.

Distinguish:
- `redirectAttributes.addAttribute("id", id)`: fits path/query parameters (visible in URLs, bookmarks, logs).
- `redirectAttributes.addFlashAttribute("saved", true)`: temporary data carried across one redirect without appearing in the query string.
- `@SessionAttributes("draft")`: retains data across multiple requests until `setComplete()` is called.
- Normal Model: by default exists only for a single request to render a view.

### 5.3. Post/Redirect/Get and its limits

If POST returns HTML directly, pressing F5 can prompt the browser to resubmit the POST. With **PRG**, a successful POST returns a redirect so the browser issues a GET, meaning F5 on the GET page will not resend the POST. However, PRG **does not guarantee exactly-once processing**: double-clicking two POSTs, client retries, or parallel requests can still produce duplicate side effects. When persisting to a DB or processing payments, add transactions, unique/idempotency keys, race controls, and business validation.

For POSTs failing validation, return the view directly to keep `BindingResult`; redirecting on errors requires storing errors/values separately, which is usually unnecessary complexity.

## 6. Runnable Java 17/Spring Boot 3.3 project

We create a small Servlet MVC application with one controller for the session form workflow and another for the result page. Separating **DoneController** ensures `GET /done` does not re-create `draft` through FormController's `@ModelAttribute` method after the session workflow is cleared.

### 6.1. Directory structure

~~~text
mvc-form-i18n-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── FormDemoApplication.java
    │   │   ├── WebConfig.java
    │   │   ├── RegistrationDraft.java
    │   │   ├── FormController.java
    │   │   └── DoneController.java
    │   └── resources/
    │       ├── messages.properties
    │       ├── messages_vi.properties
    │       ├── ValidationMessages.properties
    │       ├── ValidationMessages_vi.properties
    │       └── templates/
    │           ├── form.html
    │           └── done.html
    └── test/java/demo/
        └── FormFlowTest.java
~~~

All classes share package `demo` so Spring Boot component scanning detects controllers and configuration. The demo needs no repository or database.

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>mvc-form-i18n-demo</artifactId>
    <version>1.0.0</version>
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

Maven dependencies include MVC/Tomcat, Thymeleaf view resolver, Jakarta Bean Validation, and JUnit/MockMvc. Version `3.3.13` is pinned to illustrate Spring 6.1 APIs; for production projects, choose a supported branch per your organization's update policy.

### 6.3. FormDemoApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FormDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(FormDemoApplication.class, args);
    }
}
~~~

This class boots the application context and embedded web server. `@EnableWebMvc` is not needed with Spring Boot's defaults: adding it can accidentally disable MVC auto-configuration and default views/converters.

### 6.4. WebConfig.java: choosing locale via session

~~~java
package demo;

import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.LocaleResolver;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
import org.springframework.web.servlet.i18n.LocaleChangeInterceptor;
import org.springframework.web.servlet.i18n.SessionLocaleResolver;

@Configuration
public class WebConfig implements WebMvcConfigurer {

    @Bean
    public LocaleResolver localeResolver() {
        SessionLocaleResolver resolver = new SessionLocaleResolver();
        resolver.setDefaultLocale(Locale.ENGLISH);
        return resolver;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        LocaleChangeInterceptor interceptor = new LocaleChangeInterceptor();
        interceptor.setParamName("lang");
        registry.addInterceptor(interceptor);
    }
}
~~~

By default or with `lang=en`, English is selected. Requesting `GET /form?lang=vi` makes the interceptor update the locale stored in the HTTP session. Later requests in the same session do not need the parameter repeated. Here, only `en` and `vi` have complete bundles; production apps should whitelist supported locales rather than accepting arbitrary locale strings.

### 6.5. RegistrationDraft.java: form input DTO

~~~java
package demo;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public class RegistrationDraft {

    @NotBlank(message = "{form.name.required}")
    @Size(max = 80, message = "{form.name.length}")
    private String name = "";

    @NotBlank(message = "{form.email.required}")
    @Email(message = "{form.email.invalid}")
    private String email = "";

    @Size(max = 200, message = "{form.note.length}")
    private String note = "";

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public String getNote() {
        return note;
    }

    public void setNote(String note) {
        this.note = note;
    }
}
~~~

Fields are bound by Spring via setters. `@NotBlank` rejects null, empty strings, or whitespace; `@Email` checks basic email formatting rules without **verifying that the mailbox exists**. `@Size` enforces length on validation. The **Save draft** button below skips full validation so incomplete drafts can be saved; production apps must cap HTTP request size and guard session size against oversized payload abuse.

### 6.6. FormController.java: create, keep, and complete the draft

~~~java
package demo;

import jakarta.validation.Valid;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.SessionAttributes;
import org.springframework.web.bind.support.SessionStatus;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

@Controller
@RequestMapping("/form")
@SessionAttributes("draft")
public class FormController {

    @ModelAttribute("draft")
    public RegistrationDraft draft() {
        return new RegistrationDraft();
    }

    @GetMapping
    public String showForm() {
        return "form";
    }

    @PostMapping(params = "action=save")
    public String saveDraft(
            @ModelAttribute("draft") RegistrationDraft draft,
            RedirectAttributes redirect) {

        // @SessionAttributes automatically keeps draft across requests in the same session.
        // Do not enforce validation to allow saving an incomplete draft.
        redirect.addFlashAttribute("saved", true);
        return "redirect:/form";
    }

    @PostMapping(params = "action=finish")
    public String finish(
            @Valid @ModelAttribute("draft") RegistrationDraft draft,
            BindingResult errors,
            RedirectAttributes redirect,
            SessionStatus sessionStatus) {

        if (errors.hasErrors()) {
            // Same request, keeps BindingResult and field values for Thymeleaf.
            return "form";
        }

        // Demo only confirms the form, does not save to a database.
        redirect.addFlashAttribute(
            "completedName", draft.getName().trim());
        sessionStatus.setComplete();
        return "redirect:/done";
    }
}
~~~

There is no need to call `model.addAttribute("draft", ...)` in GET because the `@ModelAttribute("draft")` method initializes the model object when absent. When `draft` already exists in the session, Spring reuses it. **Multiple tabs in the same browser/session can share the same draft**, so complex production workflows may need a distinct workflow ID instead of a single fixed session attribute name.

`BindingResult` sits immediately after `@Valid @ModelAttribute`; misplacing it prevents Spring from routing field errors into that argument as expected. `SessionStatus.setComplete()` is called only after the form is valid, avoiding clearing the draft while the user still needs to fix errors.

### 6.7. DoneController.java: avoid empty result on direct URL visit

~~~java
package demo;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class DoneController {

    @GetMapping("/done")
    public String done(Model model) {
        if (!model.containsAttribute("completedName")) {
            return "redirect:/form";
        }
        return "done";
    }
}
~~~

The `completedName` flash attribute moves into the GET model right after redirect. If a user refreshes once flash data is gone, the controller redirects back to the form since the completion marker is missing. In a database-backed app, use the **saved record's ID and an idempotent GET page**, rather than relying solely on flash data to revisit results minutes later.

### 6.8. Resource bundles for UI and validation

**src/main/resources/messages.properties**:

~~~properties
form.title=Registration form
form.language=Language
form.name=Full name
form.email=Email address
form.note=Notes
form.save=Save draft
form.finish=Submit registration
form.saved=Draft saved in this session.
form.done.title=Registration completed
form.done.message=Registration received for:
form.new=Start another registration
~~~

**src/main/resources/messages_vi.properties**:

~~~properties
form.title=Biểu mẫu đăng ký
form.language=Ngôn ngữ
form.name=Họ và tên
form.email=Địa chỉ email
form.note=Ghi chú
form.save=Lưu bản nháp
form.finish=Gửi đăng ký
form.saved=Đã lưu bản nháp trong phiên hiện tại.
form.done.title=Đăng ký hoàn tất
form.done.message=Đã nhận đăng ký của:
form.new=Tạo đăng ký khác
~~~

**src/main/resources/ValidationMessages.properties**:

~~~properties
form.name.required=Please enter your name.
form.name.length=Name must not exceed {max} characters.
form.email.required=Please enter your email.
form.email.invalid=Email format is invalid.
form.note.length=Notes must not exceed {max} characters.
~~~

**src/main/resources/ValidationMessages_vi.properties**:

~~~properties
form.name.required=Vui lòng nhập tên.
form.name.length=Tên không được vượt quá {max} ký tự.
form.email.required=Vui lòng nhập email.
form.email.invalid=Định dạng email không hợp lệ.
form.note.length=Ghi chú không được vượt quá {max} ký tự.
~~~

Spring Boot automatically discovers `messages*.properties` for UI text when auto-configuring `MessageSource`; Jakarta Bean Validation resolves `{form....}` keys from the corresponding validation resource bundles. `{max}` is interpolated by the validator from `@Size(max=...)`. When testing i18n, verify **both labels and errors** in the target locale. Never put secrets, user input, or unescaped HTML into message bundles.

### 6.9. form.html: input view, locale switch, error display

**src/main/resources/templates/form.html**:

~~~html
<!doctype html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title th:text="#{form.title}">Registration form</title>
</head>
<body>
  <nav>
    <span th:text="#{form.language}">Language</span>:
    <a th:href="@{/form(lang='en')}">English</a>
    <a th:href="@{/form(lang='vi')}">Tiếng Việt</a>
  </nav>

  <h1 th:text="#{form.title}">Registration form</h1>

  <p th:if="${saved}" th:text="#{form.saved}">
    Draft saved.
  </p>

  <form th:action="@{/form}" th:object="${draft}" method="post">
    <div>
      <label for="name" th:text="#{form.name}">Name</label>
      <input id="name" type="text" th:field="*{name}" maxlength="80">
      <span th:if="${#fields.hasErrors('name')}"
            th:errors="*{name}">Name error</span>
    </div>

    <div>
      <label for="email" th:text="#{form.email}">Email</label>
      <input id="email" type="email" th:field="*{email}">
      <span th:if="${#fields.hasErrors('email')}"
            th:errors="*{email}">Email error</span>
    </div>

    <div>
      <label for="note" th:text="#{form.note}">Notes</label>
      <textarea id="note" th:field="*{note}" maxlength="200"></textarea>
      <span th:if="${#fields.hasErrors('note')}"
            th:errors="*{note}">Notes error</span>
    </div>

    <button type="submit" name="action" value="save"
            th:text="#{form.save}">Save draft</button>
    <button type="submit" name="action" value="finish"
            th:text="#{form.finish}">Submit</button>
  </form>
</body>
</html>
~~~

`th:field` generates/populates input values from `RegistrationDraft`; after errors, it re-renders alongside `BindingResult`. In a real browser, `type="email"` applies default client-side validation; to **test server-side validation specifically**, MockMvc/cURL can submit invalid form data directly. In production, add `aria-describedby`, error-to-input associations, CSS error states, keyboard focus, and screen-reader support.

Never use `th:utext` on user-provided data. `th:text` escapes HTML; the result page uses the same rule to prevent XSS.

### 6.10. done.html: GET view after redirect

**src/main/resources/templates/done.html**:

~~~html
<!doctype html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title th:text="#{form.done.title}">Completed</title>
</head>
<body>
  <h1 th:text="#{form.done.title}">Completed</h1>
  <p>
    <span th:text="#{form.done.message}">Received for:</span>
    <strong th:text="${completedName}">Visitor</strong>
  </p>
  <a th:href="@{/form}" th:text="#{form.new}">New registration</a>
</body>
</html>
~~~

In the demo, `completedName` is a flash attribute present for the target GET after redirect. Rendering with `th:text` escapes characters like `<` and `>` in input. When displaying real results long-term, persist the record to a database and build an authorized `GET /registrations/{id}` endpoint.

## 7. Testing the workflow with Spring Boot + MockMvc

MockMvc runs simulated HTTP requests through the MVC stack, exercising the real controllers, view resolver, binder, validator, interceptors, and session. You can assert view name, status, Location, flash attributes, field errors, and rendered HTML. This test **does not open a TCP socket** and does not prove reverse proxy/TLS behavior; for real browser testing, use Selenium/Playwright or an HTTP client against RANDOM_PORT.

**src/test/java/demo/FormFlowTest.java**:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.flash;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.model;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.view;

@SpringBootTest
@AutoConfigureMockMvc
class FormFlowTest {

    @Autowired
    MockMvc mvc;

    @Test
    void getFormRendersThymeleafView() throws Exception {
        mvc.perform(get("/form"))
            .andExpect(status().isOk())
            .andExpect(view().name("form"))
            .andExpect(model().attributeExists("draft"))
            .andExpect(content().string(containsString("Registration form")));
    }

    @Test
    void languageChoicePersistsWithinOneHttpSession() throws Exception {
        MockHttpSession session = new MockHttpSession();

        mvc.perform(get("/form").session(session).param("lang", "vi"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                containsString("Biểu mẫu đăng ký")));

        mvc.perform(get("/form").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string(
                containsString("Biểu mẫu đăng ký")));
    }

    @Test
    void saveDraftRedirectsAndKeepsFormDataInSession() throws Exception {
        MockHttpSession session = new MockHttpSession();
        mvc.perform(get("/form").session(session))
            .andExpect(status().isOk());

        mvc.perform(post("/form").session(session)
                .param("action", "save")
                .param("name", "Lan")
                .param("email", "lan@example.org")
                .param("note", "Call in the morning"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/form"))
            .andExpect(flash().attribute("saved", true));

        RegistrationDraft draft =
            (RegistrationDraft) session.getAttribute("draft");
        assertEquals("Lan", draft.getName());
        assertEquals("lan@example.org", draft.getEmail());

        mvc.perform(get("/form").session(session))
            .andExpect(status().isOk())
            .andExpect(model().attributeExists("draft"))
            .andExpect(content().string(containsString("Lan")));
    }

    @Test
    void invalidFinalSubmitReturnsSameViewWithFieldErrors()
            throws Exception {
        MockHttpSession session = new MockHttpSession();

        mvc.perform(post("/form").session(session)
                .param("action", "finish")
                .param("name", " ")
                .param("email", "not-an-email")
                .param("note", ""))
            .andExpect(status().isOk())
            .andExpect(view().name("form"))
            .andExpect(model().attributeHasFieldErrors(
                "draft", "name", "email"));

        // Invalid form has not called SessionStatus.setComplete().
        RegistrationDraft draft =
            (RegistrationDraft) session.getAttribute("draft");
        assertEquals("not-an-email", draft.getEmail());
    }

    @Test
    void validFinalSubmitUsesPrgAndClearsDraft() throws Exception {
        MockHttpSession session = new MockHttpSession();

        mvc.perform(get("/form").session(session))
            .andExpect(status().isOk());

        MvcResult result = mvc.perform(post("/form").session(session)
                .param("action", "finish")
                .param("name", "Lan")
                .param("email", "lan@example.org")
                .param("note", ""))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/done"))
            .andExpect(flash().attribute("completedName", "Lan"))
            .andReturn();

        assertNull(session.getAttribute("draft"));

        mvc.perform(get("/done").session(session)
                .flashAttrs(result.getFlashMap()))
            .andExpect(status().isOk())
            .andExpect(view().name("done"))
            .andExpect(content().string(containsString("Lan")));
    }

    @Test
    void directDoneUrlWithoutFlashRedirectsToForm() throws Exception {
        mvc.perform(get("/done"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/form"));
    }
}
~~~

There are **6 `@Test` methods**: view rendering; switching locale and persisting across the session; saving draft and redirecting; validation failure; successful PRG and clearing draft; and direct visit to done redirecting. These assertions check rendered HTML and lifecycle behavior, not just direct controller method calls.

Two easily misunderstood testing details:

- Reuse the same `MockHttpSession` across `mvc.perform(...)` calls to simulate a browser carrying the same session cookie. Each new `MockHttpSession` represents a separate session; using a different session on the GET after POST causes draft/locale to be **absent**, as expected.
- `MvcResult.getFlashMap()` captures flash data from the POST, and `.flashAttrs(...)` attaches it to the simulated GET after redirect. MockMvc does not follow redirects like a browser; the test must perform the follow-up GET explicitly. In a real browser, Spring's `RedirectAttributes`/FlashMap stores and consumes flash data across the redirect.

To run the tests:

~~~bash
mvn -q test
~~~

If all tests pass, Maven returns exit code **0**, with reports in `target/surefire-reports/`. `-q` mode may suppress summary lines; do not mistake "no output" for verified success without checking the exit code. This is a complete practice example; runtime execution **is not claimed to have been run while authoring this lesson**.

## 8. Running the web app and observing requests

Start the project from the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

If port 8080 is free and no other config is active, visit:

~~~text
http://localhost:8080/form
http://localhost:8080/form?lang=vi
http://localhost:8080/form?lang=en
~~~

Walkthrough:
1. Open `/form?lang=vi` and check the labels **Biểu mẫu đăng ký** and **Lưu bản nháp**.
2. Enter name `Lan`, email `lan@example.org`, optional notes, and click **Lưu bản nháp**. Watch DevTools Network: **POST /form → HTTP redirect → GET /form**; the values remain on the form.
3. Change the email to an invalid format and click **Gửi đăng ký**. The browser may block submission client-side due to input type=email; to test the server directly, use cURL/MockMvc or change the `type` attribute to text in DevTools. The server returns the view with errors.
4. Fix the email to a valid one and submit. The browser receives a redirect to `/done`, displaying the entered name. Refreshing the result URL does not resend the POST.
5. Go back to `/form`: the old draft was cleared by `SessionStatus.setComplete()`, so a fresh empty object starts; the `lang=vi` choice remains in the same HTTP session.

When using cURL across multiple requests, preserve cookies:

~~~bash
curl -c cookies.txt -b cookies.txt -i \
  "http://localhost:8080/form?lang=vi"

curl -c cookies.txt -b cookies.txt -i \
  -X POST "http://localhost:8080/form" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "action=save" \
  --data-urlencode "name=Lan" \
  --data-urlencode "email=lan@example.org" \
  --data-urlencode "note=Note"

curl -c cookies.txt -b cookies.txt -i \
  "http://localhost:8080/form"
~~~

`cookies.txt` here is a **file created by cURL on the learner's machine**, not a Spring config file. Never commit cookies/tokens to Git or post them in bug reports. If Spring Security is enabled on the app, POSTs will require a valid CSRF token and possibly authentication; cURL commands must then follow the appropriate security flow.

## 9. Things to understand before taking the demo to production

### 9.1. Session lifetime and multiple tabs

In the demo, one browser session holds exactly one `draft` under that attribute name. Two tabs in the same browser share JSESSIONID, edit the same draft, and can cause tab A to overwrite tab B. To support parallel forms, add a unique workflow ID, scope state by ID, and control concurrency.

Sessions are not permanent databases: server restarts, timeouts, failovers, or users clearing cookies can lose drafts. If users expect multi-day or multi-device drafts, persist to a DB with account identity, authorization, and version history; keep only lightweight references in the session.

In a cluster, sessions can be stored in a shared backing store like Redis via Spring Session or routed with session affinity. Objects placed into distributed sessions require attention to serialization, schema evolution, size, TTL, and sensitive data. Never store passwords, card numbers, or unnecessary sensitive data in sessions.

### 9.2. CSRF, XSS, and authorization

`POST /form` is a state-changing action. In apps with authentication/cookies, enable Spring Security CSRF protection as configured; Thymeleaf forms automatically include a hidden CSRF field when Spring Security/RequestDataValueProcessor is properly configured, though real responses and submissions must be tested. Never disable CSRF just to make an example run if production needs it.

`th:text` and `th:field` handle HTML escaping, yet user input must still be validated/sanitized for its display context. Never use `th:utext` for untrusted content. Session cookies should carry `HttpOnly`, `Secure` over HTTPS, appropriate `SameSite`, session timeouts, and session-fixation protection per security policy.

PRG solves browser-refresh UX, not duplicate POSTs or CSRF. An actual registration action needs server-side uniqueness/idempotency and proper authorization.

### 9.3. Form binding and mass assignment

`RegistrationDraft` contains only fields the browser is allowed to submit. Using a JPA entity directly with `id`, `role`, `isAdmin`, or `verified` lets an attacker submit extra form parameters to alter fields absent from the UI. Always use a DTO, map to entities in the service, and enforce allowed fields/constructor binding as needed.

Even for **save draft** without full validation, cap request size, field lengths, session counts, and request rates to prevent abuse. In critical business apps, saving a draft may still enforce minimal invariants distinct from final submission validation.

### 9.4. Redirect URLs and sensitive data

`redirect:/done` is a server-controlled relative URL. Never take a user-supplied `next` parameter and pass it straight into `redirect:`: that creates an **open redirect**. If "return to previous page" is required, enforce an audited host/path allowlist.

`RedirectAttributes.addFlashAttribute` keeps data out of the URL by default, yet it is not a long-term secret vault: flash data typically lives in the session and can be consumed prematurely by concurrent requests. Avoid passing financial data or credentials in flash attributes, and never treat the completion GET page as the business source of truth.

### 9.5. Production localization

In production, decide:
- Which languages are supported and how missing message keys fall back.
- Whether language selection lives in the session, a cookie, the user account, or the URL.
- Whether validation messages, dates/times, numbers, currencies, and plural forms follow the locale.
- Accessibility of the language switcher; whether the `<html>` `lang` attribute should track the active locale.
- Check not only form labels, but also error messages, emails, and completion pages in both vi/en.

The example keeps `<html lang="en">` static to keep HTML simple; real bilingual pages should bind `lang` dynamically (such as `th:lang="${#locale.language}"`) so screen readers pronounce content properly. Test the locale selector and `Accept-Language` in real environments, especially when proxies/CDNs cache HTML.

## 10. Required test matrix

| Scenario | Expectation | Test layer |
| --- | --- | --- |
| GET fresh form | 200, form view, fresh draft model | MockMvc |
| Switch `?lang=vi` | Vietnamese labels and locale saved in session | Multi-request MockMvc with same session |
| Subsequent GET without lang | Remains in Vietnamese | MockMvc |
| POST save draft missing fields | Redirect to /form; draft retained | MockMvc |
| GET after save | Name/email/note still present on form | MockMvc with MockHttpSession |
| POST finish with blank name | Form view, name field error, draft not cleared | MockMvc |
| POST finish with bad email | Form view, email error | MockMvc |
| POST finish valid | Redirect to /done, flash completedName, draft cleared | MockMvc |
| GET /done after redirect | Done view and escaped name | MockMvc/browser |
| Direct GET /done | Redirect to /form when no flash present | MockMvc |
| Fresh session | Locale/draft do not leak from prior session | MockMvc with two sessions |
| Session timeout | Draft lost per contract, no 500 | Integration |
| Two tabs in one session | Evaluate overwrite risk, decide workflow ID | Browser/integration |
| Security enabled | POST with valid CSRF passes; bad token rejected | spring-security-test/integration |
| Reverse proxy | Cookies/redirect Location/scheme correct over HTTPS | E2E behind proxy |
| Double POST | Side effects not duplicated per idempotency contract | Service/integration |

To test HTML escaping, submit a name containing `<`/`>` through the valid flow and verify the output contains escaped text rather than executable HTML/script. With mock HTML, avoid comparing whole documents verbatim since whitespace/layout changes; assert key text, view name, status, and model attributes.

## 11. Common pitfalls and fixes

1. **Placing form.html in `static` instead of `templates`:** Spring cannot resolve logical view `form` via Thymeleaf. Place it in `src/main/resources/templates/`.
2. **Using `@RestController` for HTML pages:** writes the string `"form"` as the response body instead of a view name. Use `@Controller`.
3. **Missing `th:object` while using `th:field="*{...}"`:** template binding fails. Ensure the model contains the named object.
4. **Forgetting `@Valid`/`spring-boot-starter-validation`:** DTO annotations do not run as expected. Test invalid input to ensure field errors appear.
5. **Not placing `BindingResult` immediately after the form object:** binding/validation errors are not captured properly. Fix the handler signature.
6. **Redirecting after validation errors:** loses field errors or form values unless stored separately. Return the logical view `form` on the failed request.
7. **Using `AcceptHeaderLocaleResolver` with `LocaleChangeInterceptor`:** that resolver does not support changing locale via setLocale. Use SessionLocaleResolver/CookieLocaleResolver or another design.
8. **Creating only `messages_vi.properties` without the default bundle:** breaks fallback and other languages' keys; always maintain the default base bundle.
9. **Hardcoding UI text in HTML/Java:** switching languages only works partially. Use `#{key}` and resource bundles consistently.
10. **Confusing flash with session state:** flash survives one redirect; drafts need session/workflow state across multiple requests.
11. **Calling `HttpSession.invalidate()` on form completion:** can wipe login/locale. Call `SessionStatus.setComplete()` to clear controller-managed workflow attributes.
12. **Forgetting to clear the draft after submit:** the next registration sees old data; call setComplete once the business action truly finishes.
13. **Assuming PRG prevents duplicate submits:** two POSTs can still execute; use idempotency/unique operation keys when side effects exist.
14. **Storing huge or sensitive data in the session:** wastes memory, creates security exposure, and complicates replication.
15. **Not reusing the same session cookie in tests:** GET after POST loses draft and locale, misleadingly pointing to bad config. Reuse MockHttpSession/cookies.
16. **Asserting full raw HTML pages:** tests break on formatting tweaks; assert the contract (status, view, key text/elements/redirect/flash).
17. **Redirecting to unvalidated user input:** risks open redirects. Allow only internal/allowlisted URLs.
18. **Relying on flash to view registrations permanently:** refreshes/direct links lack data; production result pages must query persisted data with authorization.
19. **Ignoring multi-tab behavior:** one draft per session can be overwritten; add workflow IDs or optimistic locking when needed.
20. **Testing only in a browser with client-side validation:** does not prove server-side Bean Validation works. Send invalid payloads via MockMvc/cURL.

## 12. Implementation checklist

For a complete Spring MVC form page, verify in order:
1. GET/POST routes and logical view names are right; Thymeleaf templates read declared model objects.
2. Data binds into a dedicated DTO, `@Valid` and `BindingResult` run on the server, and field errors render accurately.
3. Labels, buttons, validation messages, and the done page have resource bundles; locale selection and persistence match the lifecycle.
4. Session state stores only what is needed, has timeouts, and is cleared via `SessionStatus.setComplete()` on success.
5. Successful POSTs redirect and consume flash cleanly; failed POSTs re-render the form with entered data and messages.
6. CSRF/XSS/authorization, request sizes, session cookies, and sensitive data have explicit policies.
7. MockMvc and integration tests cover happy paths, invalid inputs, same/new sessions, redirects, flash, localization, timeouts, and double submits per risk.
8. For multi-instance production, verify session storage/affinity, reverse-proxy forwarded headers, and HTTPS redirects.

## 13. Conclusion

**Views** display the form and user feedback; **binding/validation** safely maps requests into DTOs; **localization** selects messages by locale; **sessions** retain draft state across requests; and **redirects + flash** complete POSTs via PRG without losing transient notifications.

These pieces truly hold together only when tested within one cohesive HTTP workflow. In Spring MVC, splitting `FormController` and `DoneController`, using `@SessionAttributes`, `SessionLocaleResolver`, `RedirectAttributes`, and MockMvc tests lets you verify each responsibility clearly. When moving to a real application, add persistence, security, concurrency, and idempotency rather than turning the HTTP session into a database.

## References

- Spring Framework — MVC view technologies and Thymeleaf: https://docs.spring.io/spring-framework/reference/web/webmvc-view.html
- Spring Framework — ModelAttribute / Data Binding: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework — Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework — @SessionAttributes: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/sessionattributes.html
- Spring Framework — Locale and SessionLocaleResolver: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/localeresolver.html
- Spring Framework — RedirectAttributes and Flash Attributes: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/redirecting-passing-data.html
- Spring Framework — MockMvc: https://docs.spring.io/spring-framework/reference/testing/mockmvc.html
- Thymeleaf — Spring form binding and validation: https://www.thymeleaf.org/doc/tutorials/3.1/thymeleafspring.html
- Spring Boot 3.3 — Testing: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
