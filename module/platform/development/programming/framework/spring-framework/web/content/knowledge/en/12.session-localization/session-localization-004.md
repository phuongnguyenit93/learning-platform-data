# @SessionAttributes, SessionStatus, and Differences from @SessionAttribute in Spring MVC

> **Context:** Spring Web MVC on the **Servlet stack**, Java 17+, and Spring Boot 3.x / Spring Framework 6.x. This lesson distinguishes three components easily confused because of similar names: **`@SessionAttributes`** temporarily stores **model attributes** across multiple HTTP requests of a workflow; **`SessionStatus`** marks the end of that workflow and requests cleanup of the managed attributes; **`@SessionAttribute`** reads a **pre-existing session attribute** as a handler parameter. All three relate to the HTTP session, yet **they are not synonymous**, nor do they replace security, validation, or durable storage.

## 1. Why Is State Needed Across Requests?

HTTP does not inherently carry a Java object from one request to the next. A multi-step form may require:

1. The user enters a **name** in step 1.
2. The user enters a **city** in step 2.
3. The user confirms both and completes the flow.
4. The server clears the temporary draft so old data does not appear when starting a new flow.

If each request carries only the current step's fields, somewhere must hold the **temporary draft**. One option in Spring MVC is a model attribute placed in the **HTTP session** via `@SessionAttributes`.

```text
Client (JSESSIONID cookie)
     |
GET /wizard/start
     | Controller creates model["draft"]
     v
HTTP Session: draft(name="", city="")
     |
POST /wizard/name -> draft.name="Lan"
     |
POST /wizard/city -> draft.city="Da Nang"
     |
POST /wizard/finish
     | complete business logic
     | SessionStatus.setComplete()
     v
HTTP Session: no draft left in controller workflow
     |
GET /wizard/start -> create new draft
```

The session cookie (normally `JSESSIONID` under default Servlet configuration) lets the server recognize multiple requests coming from the same HTTP session. Without sending the cookie back, the server may treat the request as a new session. Session attributes are not global variables shared across all users.

**Core concepts:**
- **Request scope:** data exists only while processing a single request.
- **Model:** the map of data a controller passes to the view; normally **not persisted** across requests.
- **HTTP session:** storage holding attributes bound to a server-side session (depending on deployment infrastructure).
- **Controller conversation:** a sequence of requests serving a temporary task, such as a wizard; `@SessionAttributes` is designed for this kind of data.

## 2. Comparing the Three APIs Up Front

| API | Where is it declared? | What does it do? | Auto-saves or auto-cleans? |
| --- | --- | --- | --- |
| `@SessionAttributes("draft")` | **On the class** `@Controller` / `@RestController` | Declares that a model attribute named `draft` should be stored in the session across requests of the controller workflow | Spring MVC syncs matching model attributes into the session; cleans up when the conversation is marked complete |
| `SessionStatus status` | **Handler method parameter** | Provides `setComplete()` and `isComplete()` for the workflow lifecycle | `setComplete()` triggers Spring MVC to clean up **attributes managed by `@SessionAttributes`** |
| `@SessionAttribute(name="tenantCode")` | **On a handler method parameter** | Reads an attribute already stored in the HTTP session | **Does not create, save, or clean** attributes; only resolves the value for the parameter |
| `HttpSession` | Handler method parameter / Servlet API | Reads, writes, and deletes attributes directly; can invalidate the entire session | Managed explicitly by your code or container/session infrastructure |

**Do not confuse plural and singular:**

- **`@SessionAttributes` (plural):** **model → session** mechanism scoped to a controller and task lifecycle.
- **`@SessionAttribute` (singular):** **session → method parameter** mechanism for an existing value.
- **`SessionStatus`:** the **completion** signal telling the controller to stop retaining temporary model attributes in the session.

They are not ways to declare "bean scope=session." For example, `@SessionScope` is a Spring container mechanism for managing beans per session; this lesson focuses on **Spring MVC handler model attributes**.

## 3. `@SessionAttributes`: Declaring on a Controller and Storing Model Attributes

Minimal syntax:

```java
@Controller
@SessionAttributes("draft")
public class WizardController {

    @GetMapping("/wizard")
    public String start(Model model) {
        model.addAttribute("draft", new DraftForm());
        return "wizard-form";
    }
}
```

This is an **illustrative method**, requiring you to define `DraftForm` and the `wizard-form` view. Role of each part:

- `@SessionAttributes("draft")` declares that the controller uses a **model attribute named `draft`** across multiple requests.
- `model.addAttribute("draft", new DraftForm())` puts the object into the Model.
- After the method finishes in the Spring MVC pipeline, Spring detects the declared attribute and keeps it in the HTTP session.
- On subsequent requests, Spring restores the model attribute from the session so handlers in the same workflow can continue using it.

`@SessionAttributes` does not mean "put every local variable of the controller into the session." Only **model attributes matching by name or type** participate.

### 3.1. Declaring by Name and/or Type

```java
@SessionAttributes(names = {"draft", "addressForm"})
class WizardController {
    // ...
}
```

Or:

```java
@SessionAttributes(types = DraftForm.class)
class WizardController {
    // ...
}
```

The snippets above are **two separate options**, not placed on the same class. The annotation supports `names`/`value` and `types`:

- Use **names** when you want only specific named model attributes to participate in the conversation.
- Use **types** when you intentionally want model attributes of that type stored. Be careful if the controller has multiple attributes of the same type that do not need persistence: overly broad declarations may store more data than intended.
- You can combine name/type per Spring's contract; avoid overly broad matching because it can create unnecessary sessions, inflate size, or retain sensitive data longer than needed.

**Scope:** the annotation lives on the **handler controller** class. Spring activates the conversation mechanism only when handling that controller; it is not an instruction for "every controller to automatically save `draft`." However, the HTTP session is a shared store within the same session, so if two controllers accidentally use the **same session attribute name**, they can collide. Choose workflow-specific names.

### 3.2. Retrieving the Attribute with `@ModelAttribute`

```java
@PostMapping("/wizard/name")
public String saveName(
        @ModelAttribute("draft") DraftForm draft,
        BindingResult bindingResult) {
    // Spring finds the "draft" model attribute, including values restored from session.
    // Binding and validation can run according to MVC rules.
    return "wizard-next";
}
```

This is an **illustrative method** requiring an appropriate template. Spring does not build a new object on every request if the corresponding session attribute already exists. `@ModelAttribute("draft")` is how you access the workflow object and participate in binding.

**Security warning:** client property binding can populate fields of a mutable bean if the method does not restrict inputs. Do not store entities containing `isAdmin`, `ownerId`, `price`, or broad JPA relationships just because `@SessionAttributes` is convenient. Use a form DTO containing only contract inputs, enforce authorization checks, and/or configure `@InitBinder#setAllowedFields`.

### 3.3. Creating a Model Attribute When Not Yet in the Session

To avoid manual initialization across multiple handlers:

```java
@ModelAttribute("draft")
public DraftForm initializeDraft() {
    return new DraftForm();
}
```

A `@ModelAttribute` method like this is invoked to contribute a value when the model does not yet contain that attribute; on requests where `draft` was already restored from the session, it should not overwrite the existing draft. This is a common pattern for form wizards; see the complete example in Section 8.

**Distinguish missing initialization:** if a handler declares `@ModelAttribute("draft")` and Spring expects the attribute in the session when it is absent, behavior can depend on how the attribute was declared, whether an initializer exists, constructor binding, and method flow. Do not rely on an empty session always generating the right state implicitly; design an explicit initialization step and test shortcut/completion requests.

## 4. `SessionStatus`: Marking Completion and Cleaning Workflow Attributes

Spring MVC lets you inject `SessionStatus` directly into a handler method:

```java
@PostMapping("/wizard/finish")
public String finish(
        @ModelAttribute("draft") DraftForm draft,
        SessionStatus sessionStatus) {

    // Validated and persisted business data successfully.
    sessionStatus.setComplete();
    return "redirect:/wizard/done";
}
```

This is an **illustrative snippet**, not standalone runnable code. `setComplete()` means **the current conversation is finished**; after handling, Spring cleans up attributes managed by that controller's `@SessionAttributes`. Do not mistake this method for:

- `HttpSession.invalidate()`: destroys the entire HTTP session, along with other session attributes and the session identity.
- `session.removeAttribute("anyKey")`: deletes an arbitrary key from the servlet session.
- `model.clear()`: clears all temporary attributes in the Model at the time of the method.
- `userService.save(...)`: persists data permanently to a database.

`SessionStatus` is the interface `org.springframework.web.bind.support.SessionStatus`, with:

| Method | Meaning |
| --- | --- |
| `void setComplete()` | Marks the conversation finished so MVC performs cleanup |
| `boolean isComplete()` | Checks whether the current handler has marked it complete |

**Ordering matters:** call `setComplete()` **after** validation, authorization, and business commit/save succeed. If validation fails and you still call complete, the user can lose draft data and cannot continue properly. If a database write fails, do not mark complete before checking the result.

### 4.1. What Does `setComplete()` Clean Up?

With `@SessionAttributes("draft")`, Spring MVC removes the `draft` data tracked by the conversation manager in the session. It **does not automatically remove** session keys like `tenantCode`, a cart added directly via `HttpSession.setAttribute("cart", ...)`, or login state managed by the security framework.

If the controller also uses `@SessionAttributes("shippingForm")`, the same controller can clean up attributes matching that annotation when session status is marked complete. Do not lump multiple independent workflows needing different lifecycles under one overly broad `@SessionAttributes` configuration if a single `setComplete()` call could wipe out another flow's data.

### 4.2. `SessionStatus` Is Not Login State

The statement:

```java
status.setComplete();
```

**is not equivalent to logout**. Login/logout is controlled by security and session management mechanisms. With Spring Security, logout normally clears `SecurityContext` and may invalidate the session as configured; never use `SessionStatus` to replace logout.

### 4.3. What Happens If the Workflow Is Called Again After Complete?

When a controller handler needs `draft` again, Spring can **create a new draft** if a `@ModelAttribute("draft")` initializer is declared. Thus after `POST finish` and a new `GET start`, fields can reset to empty strings. This is the normal way to avoid showing stale drafts by mistake. Write tests to confirm fresh creation, especially if something else writes the same session key.

## 5. `@SessionAttribute`: Reading an Existing Value from the Session

The **singular** annotation is placed on a **method parameter**, not on a class:

```java
@GetMapping("/current-tenant")
@ResponseBody
public String currentTenant(
        @SessionAttribute(name = "tenantCode", required = false)
        String tenantCode) {

    return tenantCode == null ? "missing" : tenantCode;
}
```

Suppose a filter, authentication flow, or application code ran:

```java
session.setAttribute("tenantCode", "tenant-a");
```

When a request carries the same HTTP session, Spring resolves that attribute as the `tenantCode` argument. This is just reading a value from the session, **without needing** class-level `@SessionAttributes("tenantCode")`.

Options:

- `name` or `value`: session key name.
- `required = true` (default): a missing attribute can raise an exception during method argument resolution.
- `required = false`: allows absence; for reference types like `String`, the method can receive `null`, so check before using.
- `Optional<T>` can be used to express presence/absence in a strongly typed way.

Example:

```java
@GetMapping("/locale-preference")
@ResponseBody
public String preferred(
        @SessionAttribute(name = "preferredLanguage", required = false)
        String language) {

    return language == null ? "default" : language;
}
```

**When should you use `@SessionAttribute`?** When an attribute is managed **outside a controller conversation** and the controller merely needs to read it: data set by a filter, a per-session setting, or metadata saved by another part of the application. If you need to add/remove attributes, accept `HttpSession` or `WebRequest` per contract rather than forcing `@SessionAttributes` into that role.

### 5.1. Missing Required Session Attribute

```java
@GetMapping("/must-have-tenant")
@ResponseBody
public String mustHave(
        @SessionAttribute("tenantCode") String tenantCode) {
    return tenantCode;
}
```

If there is no session or no `tenantCode` key, Spring MVC may throw an exception for the missing required session attribute before invoking the method. The exact HTTP status and body depend on resolver/error configuration; **do not assert that every version returns an identical body**. For truly optional data, write `required=false` or `Optional` and handle the absent branch explicitly.

### 5.2. Does `@SessionAttribute` Modify the Session?

Not automatically. The parameter merely passes an existing value to the method. With a reference to a mutable object, Java code can **mutate that object itself**; however, that is a side effect on the object/session, **not an automatic model-conversation mechanism of the annotation**. For persistent data needing control, prefer immutable values or a service with explicit write logic.

## 6. Direct Comparison Using One Scenario

Suppose the same session contains:

```text
draft       = DraftForm("Lan", "Da Nang")
tenantCode  = "demo-tenant"
cart        = [Book-1, Book-2]
```

| Operation | Result |
| --- | --- |
| Handler in `@SessionAttributes("draft")` receives `@ModelAttribute("draft") DraftForm` | Participates in the model/session lifecycle; can read and update draft |
| Handler receives `@SessionAttribute("tenantCode") String` | Only reads value `demo-tenant` into the method argument |
| `SessionStatus.setComplete()` in the wizard controller | Removes managed `draft`; does not actively remove `tenantCode` or `cart` |
| `session.removeAttribute("tenantCode")` | Removes key `tenantCode` without ending `draft` |
| `session.invalidate()` | Destroys the entire HTTP session; all attributes in that session can no longer be used |

**In short:** the plural form manages **conversation model state**; the singular form reads **existing session state**; `SessionStatus` ends the managed conversation. Do not substitute one for another just because all three involve `HttpSession`.

## 7. Differences from Similar Mechanisms

### 7.1. `@ModelAttribute` Without `@SessionAttributes`

```java
@PostMapping("/one-step")
public String submit(@ModelAttribute SimpleForm form) {
    return "done";
}
```

Normally the form lives only for the current request processing lifecycle; Spring **does not by default** keep it in the HTTP session for subsequent requests. If a wizard needs temporary retention, add an appropriate mechanism (session conversation or other storage).

### 7.2. `RedirectAttributes.addFlashAttribute(...)`

```java
@PostMapping("/done")
public String done(RedirectAttributes redirects) {
    redirects.addFlashAttribute("notice", "Saved");
    return "redirect:/summary";
}
```

Flash attributes serve to **pass data across a single redirect to the next request**, typically for success messages, not for a long multi-step wizard. The platform may use the session to carry flash data, but a flash attribute's lifecycle is not `@SessionAttributes`.

### 7.3. Direct `HttpSession`

```java
@GetMapping("/manual-session")
@ResponseBody
public String manual(HttpSession session) {
    session.setAttribute("pref", "compact");
    return (String) session.getAttribute("pref");
}
```

This code actively manipulates session keys. Use `HttpSession` when you need explicit control over keys/TTL/invalidation/session metadata, while keeping size and permissions in check. `SessionStatus` does not remove `pref` by default in this example because it is not a managed session attribute of a controller workflow.

### 7.4. `@SessionScope`

```java
@Component
@SessionScope
class ShoppingCart {
    // Session-scoped bean, not a wizard model attribute.
}
```

`@SessionScope` is a Spring IoC bean-scope mechanism with a per-session proxy; it is not an annotation for binding a Model to the session. If the application needs shared state across controllers/services within one session, a session-scoped bean can be a separate option, though it still brings concurrency/serialization/session-expiry concerns.

## 8. Complete, Runnable Example: Wizard and Independent Session Attribute

Spring Boot 3.x, Java 17+ example with only the **Spring Web** dependency to minimize complexity. No template engine or database is needed: handlers return JSON while still being Spring MVC controllers, letting us observe the model/session lifecycle directly. The example intentionally omits Spring Security and uses simulated data. Real applications require proper auth/CSRF.

### 8.1. Project Setup

Create a Maven Spring Boot 3.x project with the **Spring Web** dependency at [Spring Initializr](https://start.spring.io/). `pom.xml` includes the starter:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
```

This is a dependency fragment; parent/plugins/metadata are prepared by Initializr. Place the following Java source at `src/main/java/com/example/demo/DemoApplication.java`. The file has only one `public class`; the other classes are package-private, which is valid in Java 17.

### 8.2. Complete Java Code

```java
package com.example.demo;

import java.util.LinkedHashMap;
import java.util.Map;

import jakarta.servlet.http.HttpSession;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.SessionAttribute;
import org.springframework.web.bind.annotation.SessionAttributes;
import org.springframework.web.bind.support.SessionStatus;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

class DraftForm {
    private String name = "";
    private String city = "";

    public DraftForm() {
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }
}

@Controller
@RequestMapping("/wizard")
@SessionAttributes("draft")
class WizardController {

    // Create a new draft only when no attribute has been restored from session.
    @ModelAttribute("draft")
    public DraftForm initializeDraft() {
        return new DraftForm();
    }

    @GetMapping("/start")
    @ResponseBody
    public Map<String, String> start(
            @ModelAttribute(value = "draft", binding = false)
            DraftForm draft) {

        return snapshot("started", draft);
    }

    @GetMapping("/state")
    @ResponseBody
    public Map<String, String> state(
            @ModelAttribute(value = "draft", binding = false)
            DraftForm draft) {

        return snapshot("in-progress", draft);
    }

    @PostMapping(path = "/name",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    @ResponseBody
    public Map<String, String> name(
            @ModelAttribute(value = "draft", binding = false)
            DraftForm draft,
            @RequestParam("name") String name) {

        draft.setName(name);
        return snapshot("name-set", draft);
    }

    @PostMapping(path = "/city",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    @ResponseBody
    public Map<String, String> city(
            @ModelAttribute(value = "draft", binding = false)
            DraftForm draft,
            @RequestParam("city") String city) {

        draft.setCity(city);
        return snapshot("city-set", draft);
    }

    @PostMapping("/finish")
    @ResponseBody
    public Map<String, String> finish(
            @ModelAttribute(value = "draft", binding = false)
            DraftForm draft,
            SessionStatus status) {

        // Demo does not write to a database. Before completing in a real system,
        // validate input/permissions and commit business changes successfully.
        Map<String, String> result = snapshot("complete", draft);
        status.setComplete();
        return result;
    }

    @PostMapping("/cancel")
    @ResponseBody
    public ResponseEntity<Map<String, String>> cancel(
            SessionStatus status) {

        status.setComplete();
        return ResponseEntity.ok(Map.of("stage", "cancelled"));
    }

    private static Map<String, String> snapshot(
            String stage, DraftForm draft) {
        Map<String, String> result = new LinkedHashMap<>();
        result.put("stage", stage);
        result.put("name", draft.getName());
        result.put("city", draft.getCity());
        return result;
    }
}

@RestController
@RequestMapping("/session/tenant")
class TenantController {

    @PostMapping("/set-demo")
    public Map<String, String> setDemo(HttpSession session) {
        // Demonstrates server-side assignment only; do not take tenant from the client.
        session.setAttribute("tenantCode", "demo-tenant");
        return Map.of("tenant", "demo-tenant");
    }

    @GetMapping
    public Map<String, String> get(
            @SessionAttribute(name = "tenantCode", required = false)
            String tenantCode) {
        return Map.of("tenant",
                tenantCode == null ? "<missing>" : tenantCode);
    }

    @PostMapping("/clear")
    public Map<String, String> clear(HttpSession session) {
        session.removeAttribute("tenantCode");
        return Map.of("tenant", "<missing>");
    }
}
```

**Design explanation:**

- `@Controller @SessionAttributes("draft")` registers the `draft` model attribute for the workflow. Thanks to the `@ModelAttribute("draft")` initializer, the first request gets a fresh `DraftForm`; subsequent requests carrying the session attribute retain the same data.
- `@ModelAttribute(value = "draft", binding = false)` in handlers retrieves `draft` from the model/session **without automatically binding arbitrary request parameters to its properties**. The two endpoints use `@RequestParam` and intentionally set one property per step to demonstrate avoiding over-posting. Production also requires validation and authorization rather than copying raw strings.
- The methods return JSON via `@ResponseBody`; even without rendering a view template, MVC still manages model/session attributes through its normal pipeline.
- `finish` and `cancel` accept `SessionStatus` and call `setComplete()`; Spring cleans up the wizard's `draft` attribute. The `DraftForm` object inside the handler can still be used to build the response body, but after the request it is no longer retained in the managed session.
- `TenantController` does not declare `@SessionAttributes`. It writes the `tenantCode` session key via `HttpSession.setAttribute(...)` and reads it using **singular `@SessionAttribute`**. Calling `SessionStatus.setComplete()` in the wizard does not touch this key.
- `Map.of(...)` does not guarantee JSON object field order, so compare fields/values rather than key order. `snapshot` uses `LinkedHashMap` for readable output.
- Spring MVC controllers are singletons by default; **do not** place `private DraftForm currentDraft` on the controller to hold user state, because multiple users could read/overwrite each other's state. The draft must come from the request's session/model.

### 8.3. Running the Application

In the Maven project root:

```bash
# macOS or Linux
./mvnw spring-boot:run

# Windows PowerShell / Command Prompt
mvnw.cmd spring-boot:run
```

The server listens on `http://localhost:8080` by default unless `server.port` or context path is changed.

### 8.4. Sending Multiple Requests with the **Same Session Cookie**

Use `-c cookies.txt -b cookies.txt` on **every request** to save and load the cookie jar; omitting either can cause subsequent requests to lose the session. The commands below are for Bash; PowerShell can use `curl.exe` with each command collapsed onto one line.

**Step 1 — Initialize the draft:**

```bash
curl -sS -c cookies.txt -b cookies.txt \
  http://localhost:8080/wizard/start
```

JSON body:

```json
{"stage":"started","name":"","city":""}
```

**Step 2 — Set only the name:**

```bash
curl -sS -c cookies.txt -b cookies.txt \
  -X POST http://localhost:8080/wizard/name \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'name=Lan'
```

JSON:

```json
{"stage":"name-set","name":"Lan","city":""}
```

**Step 3 — Set only the city:**

```bash
curl -sS -c cookies.txt -b cookies.txt \
  -X POST http://localhost:8080/wizard/city \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'city=Da Nang'
```

JSON:

```json
{"stage":"city-set","name":"Lan","city":"Da Nang"}
```

**Step 4 — Read the draft across requests:**

```bash
curl -sS -c cookies.txt -b cookies.txt \
  http://localhost:8080/wizard/state
```

JSON:

```json
{"stage":"in-progress","name":"Lan","city":"Da Nang"}
```

All data comes from the **HTTP session**; `GET /wizard/state` does not need query parameters or a body resending name/city.

**Step 5 — Create a session attribute outside the workflow:**

```bash
curl -sS -c cookies.txt -b cookies.txt \
  -X POST http://localhost:8080/session/tenant/set-demo

curl -sS -c cookies.txt -b cookies.txt \
  http://localhost:8080/session/tenant
```

The first step writes `tenantCode=demo-tenant` into `HttpSession`; the second uses `@SessionAttribute` to read it back. Body:

```json
{"tenant":"demo-tenant"}
```

**Step 6 — Finish the wizard:**

```bash
curl -sS -c cookies.txt -b cookies.txt \
  -X POST http://localhost:8080/wizard/finish
```

The JSON reflects the values right before cleanup:

```json
{"stage":"complete","name":"Lan","city":"Da Nang"}
```

After this response, `SessionStatus.setComplete()` instructed MVC to clean up `draft`. Call again:

```bash
curl -sS -c cookies.txt -b cookies.txt \
  http://localhost:8080/wizard/state
```

The JSON will show a **newly initialized** state from the initializer:

```json
{"stage":"in-progress","name":"","city":""}
```

However, reading `tenantCode` still returns the stored value:

```bash
curl -sS -c cookies.txt -b cookies.txt \
  http://localhost:8080/session/tenant
```

```json
{"tenant":"demo-tenant"}
```

This illustrates a key distinction: **completing the wizard does not delete the entire HTTP session**.

If `POST /wizard/cancel` is called, the body is `{"stage":"cancelled"}` and `draft` is also cleaned up. Afterward, calling `POST /session/tenant/clear` removes `tenantCode` specifically; `GET /session/tenant` returns `{"tenant":"<missing>"}`.

**Note:** the JSON strings above show field values under default Spring Boot/Jackson settings; HTTP headers or field order may vary by configuration. If a request drops the session cookie, data may reset early because the session changed. If Spring Security is added with CSRF enabled, POST requests may return 403 without a token; this example does not enable security.

## 9. Lifecycle Testing with MockMvc

You can verify that **the same session preserves `draft` across requests** and **cleans up on completion** rather than just eyeballing JSON output. Add `spring-boot-starter-test` to your build and create `src/test/java/com/example/demo/WizardSessionTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class WizardSessionTest {

    @Autowired
    MockMvc mvc;

    @Test
    void draftSurvivesAcrossRequestsAndIsClearedOnComplete()
            throws Exception {

        var start = mvc.perform(get("/wizard/start"))
                .andExpect(status().isOk())
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) start.getRequest().getSession(false);
        assertNotNull(session);
        assertNotNull(session.getAttribute("draft"));

        mvc.perform(post("/wizard/name")
                        .session(session)
                        .param("name", "Lan"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("Lan"));

        mvc.perform(post("/wizard/city")
                        .session(session)
                        .param("city", "Da Nang"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.city").value("Da Nang"));

        mvc.perform(get("/wizard/state").session(session))
                .andExpect(jsonPath("$.name").value("Lan"))
                .andExpect(jsonPath("$.city").value("Da Nang"));

        mvc.perform(post("/wizard/finish").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.stage").value("complete"));

        assertNull(session.getAttribute("draft"));

        mvc.perform(get("/wizard/state").session(session))
                .andExpect(jsonPath("$.name").value(""))
                .andExpect(jsonPath("$.city").value(""));
    }
}
```

This is a **separate** test file using JUnit 5 and Spring Boot 3.x MockMvc. If the test framework has custom filters/security, configure them appropriately. Run:

```bash
# macOS / Linux
./mvnw test

# Windows
mvnw.cmd test
```

Key assertions:
- After `GET start`, the session contains `draft`.
- Step 1 / Step 2 `POST` calls using **the same `MockHttpSession`** retain the data.
- After `POST finish`, the session **no longer contains** `draft`.
- The next `GET state` creates a fresh empty draft.

Another useful test: set `tenantCode` in the same session before finishing, then verify `getAttribute("tenantCode")` still exists after cleanup. This checks that `SessionStatus` affects only managed session attributes.

## 10. Limitations and Risks in Production Applications

### 10.1. An HTTP Session Is Not a Database

Sessions have their own lifecycle and can time out, be invalidated on logout, be lost on container restart without proper persistence, or be replicated/serialized across distributed infrastructure. If a workflow must survive long periods, resume from another device, or meet audit requirements, consider **server-side persistence** (a database/cache with secure keys) instead of treating `@SessionAttributes` as durable storage.

When running multiple server instances, load balancer sticky sessions or a shared session solution like Spring Session may be necessary. Never assume a session attribute in one JVM's memory automatically appears in another JVM.

### 10.2. Do Not Put Mutable User State in a Singleton Controller

**Wrong:**

```java
@Controller
class UnsafeController {
    private DraftForm draft = new DraftForm(); // Shared across requests/users!
}
```

Controllers are normally singleton beans. Mutable fields like this risk cross-user data leakage or race conditions. Instead, use request/model/session-bound data with clear scopes and lifecycles.

### 10.3. Multiple Tabs and Concurrent Requests

One session can be shared across multiple browser tabs. Two tabs opening the same wizard with the same `draft` key can overwrite each other's data. Moreover, concurrent requests updating a mutable object in the session can cause lost updates; HTTP sessions **do not** automatically provide transaction locks or optimistic locking for every operation.

Solutions depending on requirements:
- Allow one active workflow per session at a time if UX permits.
- Use a unique **workflow ID** with separate per-workflow storage (with TTL and access checks).
- Enforce concurrency control/transactions in the service or persistence layer.
- Avoid sharing a single mutable `DraftForm` in the session if the product supports parallel editing flows.

### 10.4. Session Fixation, Cookies, CSRF, and Authorization

Never treat a session ID or the presence of an attribute as sole proof of authorization. For web apps using session cookies, configure TLS, `HttpOnly`, `Secure`, and `SameSite` appropriately; login/logout/session fixation protection should be managed by security configuration. `@SessionAttribute("tenantCode")` only fetches an existing value and does not guarantee that the tenant is authenticated or that the user can access every resource in that tenant.

In the `TenantController` example, `tenantCode` is assigned a fixed demo value on the server. **Never** create a production endpoint allowing the client to switch tenants or principals arbitrarily and then authorize based on that value; always verify from a trusted identity/authorization service.

State-changing POST/PUT/DELETE forms require CSRF protection when using cookie-based authentication. `SessionStatus.setComplete()` does not perform CSRF checks or authorization.

### 10.5. Minimizing Sensitive Data and Size Limits

Avoid storing raw passwords, arbitrary access tokens, large uploads, massive JPA entity graphs, or non-serializable objects when session replication is required. Session state should remain small, have an appropriate TTL, and hold only data needed for the workflow. When storing Java objects in a clustered session, types/structures may need serialization support per session store configuration.

### 10.6. Validation and Over-Posting

In handlers using `@ModelAttribute` with data binding, clients can submit extra parameters outside the UI, such as `isAdmin=true`. Therefore:
- Prefer a **dedicated DTO** for the wizard instead of an entity.
- Allow only fields belonging to each step's contract.
- If mutable form property binding is needed, consider `@InitBinder("draft")` + `setAllowedFields(...)`, or `@ModelAttribute(binding=false)` with explicit field assignment as in the demo.
- Verify Bean Validation and business constraints before calling `setComplete()`.
- Service-layer authorization and ownership checks remain mandatory; a session object does not enforce permissions.

**Do not confuse:** validation checks whether values are valid; binding restrictions control which fields can be bound; authorization decides who may act on a resource.

## 11. Common Mistakes

| Symptom | Possible cause | How to fix |
| --- | --- | --- |
| Draft disappears after each request | Client does not send the same session cookie, session timeout, unshared session store | Send the same `JSESSIONID`/cookie jar, inspect session config |
| Old draft still appears after finish | Forgot `SessionStatus.setComplete()`, or finish handler belongs to a different workflow | Call `setComplete()` after completion; test attribute cleanup |
| `setComplete()` does not delete `tenantCode` | That key is not managed by `@SessionAttributes` | Use `HttpSession.removeAttribute` or the appropriate owner mechanism |
| Entire session wiped after wizard | Code called `HttpSession.invalidate()` | Distinguish `invalidate` from `SessionStatus.setComplete()` |
| `@SessionAttribute` receives `null` | `required=false` and key missing/different session | Check for null/`Optional` or verify where the value is populated |
| Missing attribute errors before controller method | `@SessionAttribute` defaults to `required=true` | Use `required=false` if optional, ensure key is set when required |
| Two tabs overwrite each other's draft | Both tabs share `HttpSession` and the same attribute key | Use per-workflow IDs and transaction/concurrency policies |
| Unexpected request body field alters draft | Mutable model attribute exposed to unrestricted property binding | Small DTOs, allowlist, or `binding=false` |
| POST page returns 403 | CSRF protection enabled without token | Check Spring Security and form/cURL CSRF token |
| Draft stored in controller field | Singleton shared across users | Never store mutable per-user state on a controller |
| Logout does not happen on finish | `SessionStatus` does not control authentication | Use logout/security session management |
| New browser does not see draft | Different sessions per cookie/client | This is an HTTP session boundary, not a converter bug |
| Same session key used by another controller | Attribute name collision | Use workflow-specific attribute names and integration tests |

### 11.1. Systematic Debugging

1. Verify every request carries the same session cookie (avoid logging raw session IDs in production logs).
2. Verify the controller has `@SessionAttributes("draft")` matching the model attribute name.
3. Verify `draft` was added to the Model or has a `@ModelAttribute("draft")` initializer.
4. Verify the handler receives `@ModelAttribute("draft")` without unintended/blocked data binding.
5. Check whether `SessionStatus#setComplete()` was called **earlier than expected** or forgotten.
6. If reading an existing key, check where `HttpSession.setAttribute(...)` is called and verify the key name matches `@SessionAttribute`.
7. In multi-instance apps, verify session persistence/replication, load balancing, and serialization.
8. Write MockMvc tests spanning multiple requests in the same session, finishing the workflow, and re-creating a draft; add multi-tab/concurrent update tests if needed.

## 12. Self-Check Questions

**Q1.** To keep a `draft` object in the Model between step 1 and step 2 of the same controller, what do you use?

**Answer:** Class-level `@SessionAttributes("draft")` along with building/restoring the corresponding Model attribute.

**Q2.** How do you end a form wizard and clean up only the model attributes managed by the controller workflow?

**Answer:** Accept `SessionStatus` in the handler and call `setComplete()` after successful completion.

**Q3.** Does `@SessionAttribute("preferredLanguage") String language` create the key automatically if missing?

**Answer:** No. It reads an existing session attribute; by default `required=true` and a missing key can fail argument resolution. If optional, use `required=false` or `Optional` and handle absence.

**Q4.** Does `SessionStatus.setComplete()` log the user out and clear all session keys?

**Answer:** No. It ends the conversation managed by `@SessionAttributes` and does not invalidate the whole HTTP session or log out.

**Q5.** Why is `private DraftForm draft` an unsafe field in `@Controller`?

**Answer:** Controllers are normally singletons and the field is shared across users/requests, causing race conditions and data leakage risks.

**Q6.** If the same user opens the wizard in two tabs, do they get two independent drafts?

**Answer:** Not by default. Both tabs normally share the same session cookie and key, modifying the same object. Parallel workflows require separate keys/storage design.

**Q7.** Once `@SessionAttributes` keeps `DraftForm` server-side, can validation and authorization be skipped?

**Answer:** No. Clients can still submit parameters for binding and users must still be authorized per resource/action; session persistence is merely state storage.

## 13. Official Documentation

- [Spring Framework — `@SessionAttributes`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/sessionattributes.html): keeping temporary model attributes in the HTTP session and ending with `SessionStatus`.
- [Spring Framework — `@SessionAttribute`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/sessionattribute.html): reading pre-existing HTTP session attributes via handler method parameters.
- [Spring Framework — `@ModelAttribute` methods](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-modelattrib-methods.html): providing model attributes and coordinating controller methods.
- [Spring Framework — `@ModelAttribute` method arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): binding, validation, and model/session attribute resolution.
- [Spring Framework — MVC Method Arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html): `SessionStatus`, `@SessionAttribute`, `HttpSession`, and supported argument types.
- [Spring Framework — `SessionStatus` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/bind/support/SessionStatus.html): `setComplete()` and `isComplete()` contract.
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): protecting state-changing requests that use sessions/cookies.

**Conclusion:** use **`@SessionAttributes`** for a set of model attributes living temporarily across requests in the same controller workflow; use **`SessionStatus.setComplete()`** to clean them up on completion or cancellation; use **`@SessionAttribute`** when you only need to **read** an existing key from the HTTP session, especially one managed outside the controller. None of the three replace session security, binding restrictions, business validation, concurrency control, or durable persistence.
