# ServletRequestDataBinder and HTTP Parameter Sources in Spring MVC

## 1. Overview: from an HTTP request to a JavaBean

When receiving form data or a query string, a Spring MVC application usually wants to work with a **typed Java object** rather than manually reading each string value and converting types. For example, HTTP sends `name=Lan&age=26&newsletter=true` and Java needs a `ProfileForm` with `String name`, `int age`, and `boolean newsletter`.

`org.springframework.web.bind.ServletRequestDataBinder` is a component in **Spring Web (Servlet stack)** dedicated to **data binding from `jakarta.servlet.ServletRequest` parameters into a JavaBean**. It extends `WebDataBinder` → `DataBinder` and adds support for multipart files. `bind(ServletRequest)` converts request data into property values, applies allowed/required field rules, converts types, updates the target, and records binding errors in `BindingResult`.

Distinguish three tasks:

- **Collecting data:** `ServletRequest#getParameterMap()` represents the request parameters parsed by the Servlet container from the query string/form body. Multipart requires additional processing.
- **Binding and type conversion:** `ServletRequestDataBinder#bind(request)` assigns values to target properties through property access, type conversion, and binder configuration.
- **Business validation:** annotations such as `@NotBlank`, `@Min`, or Spring `Validator` can validate *after* the binding step. Calling `bind(request)` alone **does not automatically run full Bean Validation**.

In Spring MVC controllers, this work is usually performed automatically for `@ModelAttribute` parameters. Understanding `ServletRequestDataBinder` helps explain parameter sources, `typeMismatch` errors, unchecked checkboxes, multipart handling, and **mass assignment** risks when users send unexpected properties.

## 2. Position in the Spring architecture

Simple diagram:

~~~text
HTTP request (query string / HTML form / multipart)
         |
         v
jakarta.servlet.ServletRequest
         |
         +-- getParameterMap(): String/String[] parameters
         +-- MultipartRequest / Servlet Part (if present)
         |
         v
ServletRequestDataBinder
  ├─ ServletRequestParameterPropertyValues
  ├─ adds MultipartFile/Part when applicable
  ├─ WebDataBinder: field defaults/markers
  ├─ DataBinder: allowed/required fields, conversion
  └─ BindingResult: errors and suppressed fields
         |
         v
JavaBean / form object
         |
         v
Validator (when triggered by MVC or application)
         |
         v
Controller / error result / business logic
~~~

Related components:

| Component | Role |
| --- | --- |
| `DataBinder` — `org.springframework.validation.DataBinder` | Binds onto a target, supporting allowed fields, required fields, converters, `BindingResult`, and registering validators. HTTP-agnostic. |
| `WebDataBinder` — `org.springframework.web.bind.WebDataBinder` | Adds HTML form support: field markers, defaults, multipart. |
| **`ServletRequestDataBinder`** | Accepts `ServletRequest` directly along with request parameters/parts and performs binding. |
| `ServletRequestParameterPropertyValues` | Converts request parameters into `MutablePropertyValues`; has overloads for prefix filtering. |
| `ExtendedServletRequestDataBinder` | Variant used in Spring MVC to add **URI template variables and request headers** to binding values when applicable. |
| `BindingResult` | Holds conversion results, `required`/`typeMismatch` errors, validation errors, and suppressed properties. |
| `@ModelAttribute` | Common controller declaration; Spring selects and configures the appropriate binder for the request. |
| `@InitBinder` | Controller or `@ControllerAdvice` hook to set allowed fields, converters, validators, and customize the binder. |

**Version note:** this article uses the `jakarta.servlet.*` namespace, corresponding to Spring Framework **6+/7+** and Spring Boot **3+**. `ServletRequestDataBinder#construct(ServletRequest)` (constructor binding) was introduced in **Spring Framework 6.1**. In older versions, constructor binding, integrations, and import packages may differ.

## 3. HTTP parameter sources the binder actually reads

### 3.1. Query parameters and form parameters

In the Servlet API, the standard request parameter map provides:

- Name/value pairs in the URL, e.g., `GET /profiles?name=Lan&age=26`.
- HTML form data decoded by the Servlet container, e.g., `POST` with `application/x-www-form-urlencoded`.
- Repeated values with the same name, e.g., `tags=java&tags=spring`, represented as `String[]` in `getParameterValues("tags")`.

`ServletRequestDataBinder#bind(request)` by default creates `ServletRequestParameterPropertyValues(request)` **without a prefix**, converts them into property values, and binds them onto the target. Parameter names must correspond to writable JavaBean property names:

~~~text
HTTP request parameter       JavaBean target
------------------------     ------------------------------
name=Lan                     setName("Lan")
age=26                       setAge(26)              [String → int]
newsletter=true              setNewsletter(true)     [String → boolean]
address.city=Da Nang         getAddress().setCity("Da Nang")
tags=java&tags=spring        setTags(String[])       [if target has array]
~~~

Nested names such as `address.city` and indexed names such as `items[0].name` are BeanWrapper **property paths**, not JSON field names. The binder requires a valid path, a writable target, and a binder configuration that permits it. For nested collections, control `autoGrowCollectionLimit` to prevent clients from supplying excessively large indices.

**Do not assume ordering/precedence** when the query string and form body share the same parameter name. The Servlet container builds the parameter map; if ordering matters, design the API to avoid duplicate keys or use an input mechanism with a clear contract.

### 3.2. Multipart files

`bind(request)` supports `multipart/form-data` once the request has been resolved into a `MultipartRequest`/`MultipartHttpServletRequest`, or has compatible Servlet `Part`s where supported by the framework. Files use the **multipart part name** to match bean properties, e.g., `avatar` ↔ `setAvatar(MultipartFile avatar)`. Supported file property types include `MultipartFile`, `byte[]`, or `String` depending on the source and conversion.

Enable and configure multipart support in the Spring MVC stack before expecting uploaded files to appear automatically in the binder. `WebDataBinder#setBindEmptyMultipartFiles(false)` can prevent an empty file upload from overwriting an existing file; by default this setting is `true`. Storing files, size limits, MIME/type checks, and content scanning must be handled separately; binding is not a file-safety mechanism.

### 3.3. URI template variables and HTTP headers

A common point of confusion: **`ServletRequestDataBinder` used directly** primarily reads **request parameters and multipart**, and does not automatically scan all headers, cookies, path variables, or JSON bodies.

In **Spring MVC `@ModelAttribute`**, the `ExtendedServletRequestDataBinder` variant can add **URI template variables and request headers** when constructing binding values. According to MVC documentation, they are added only if they do not override a request parameter of the same name; hyphens in header names are stripped when mapping to properties. For example:

~~~java
@PostMapping("/accounts/{accountId}/profile")
String update(@ModelAttribute AccountForm form,
              BindingResult result) {
    // Spring MVC prepares and binds the form for the handler.
    return result.hasErrors() ? "profile-form" : "profile-ok";
}
~~~

This is a **controller snippet** (assuming `AccountForm`, imports, and view names exist), not a standalone program. If the URL is `/accounts/42/profile`, `accountId=42` can participate in binding `AccountForm` within MVC integration, provided it is not overridden by a same-named request parameter and the property is allowed. **Do not extrapolate this MVC behavior to a manual call `new ServletRequestDataBinder(form).bind(request)`.**

**Cookies and arbitrary headers are not request parameters by default.** `@CookieValue` and `@RequestHeader` use separate argument resolvers when that data is needed explicitly. Headers participating in MVC binding must also be subject to allowlisting and trust controls like any client-supplied input.

### 3.4. JSON body follows a different path

For JSON:

~~~http
POST /profiles
Content-Type: application/json

{"name":"Lan","age":26}
~~~

A controller typically uses:

~~~java
@PostMapping("/profiles")
ResponseEntity<Void> create(@Valid @RequestBody ProfileRequest body) {
    // ...
    return ResponseEntity.ok().build();
}
~~~

Here `@RequestBody` uses an `HttpMessageConverter` (usually Jackson) to read JSON, followed by validation if enabled. A JSON object **does not automatically become Servlet request parameters** for `ServletRequestDataBinder#bind`. Distinguishing these two paths explains why `@ModelAttribute` does not consume JSON bodies the way `@RequestBody` does.

## 4. `ServletRequestDataBinder` API and lifecycle

Important APIs:

| API | Purpose |
| --- | --- |
| `new ServletRequestDataBinder(target, "profileForm")` | Creates a binder for the target and object name used in `BindingResult`. |
| `bind(ServletRequest request)` | Binds request parameters/multipart onto an existing target; may record field errors. |
| `construct(ServletRequest request)` (6.1+) | Creates the target via a data constructor from the request, distinct from setter/property binding. |
| `getBindingResult()` | Retrieves errors, field errors, and suppressed fields; does not produce an HTTP response by itself. |
| `setAllowedFields("name", "age", ...)` | Allows only the specified property paths during **setter/property binding**. |
| `setRequiredFields("name")` | Requires a field to be present in binding input; missing fields produce a `required` error code. |
| `setDeclarativeBinding(true)` (6.1+) | Enables constructor binding and allows setter binding only when allowed fields are configured. |
| `setConversionService(...)` / `registerCustomEditor(...)` | Customizes type conversion and formatting. |
| `setFieldMarkerPrefix(...)` / `setFieldDefaultPrefix(...)` | Customizes `_field` and `!field` from HTML forms. |
| `setBindEmptyMultipartFiles(...)` | Controls whether empty `MultipartFile` uploads are bound. |
| `closeNoCatch()` | Treats binding errors as fatal; throws `ServletRequestBindingException` if errors exist. |

Typical manual programming flow:

~~~java
ProfileForm form = new ProfileForm();
ServletRequestDataBinder binder =
        new ServletRequestDataBinder(form, "profileForm");
binder.setAllowedFields("name", "age", "newsletter");
binder.bind(servletRequest);
BindingResult result = binder.getBindingResult();

if (result.hasErrors()) {
    // Handle typeMismatch / required / binding errors.
}
~~~

This is an **illustrative snippet** in an environment with `ProfileForm`, `ServletRequest`, and imports; a complete test program is in section 6. The binder is normally created/used by Spring MVC in the request pipeline; you do not usually instantiate it manually in a controller just to use `@ModelAttribute`.

### `BindingResult` and error codes

- `result.getFieldError("age")`: returns a `FieldError` when `age=not-a-number` cannot be converted to `int`. The error code usually starts with `typeMismatch` (which can be expanded into more specific codes by object/property/type via `MessageCodesResolver`).
- `result.getFieldError("name")`: can carry the code `required` when `setRequiredFields("name")` is set and the parameter is missing.
- `result.hasErrors()` checks whether errors exist (binding errors, or validation errors if validation was triggered).
- `result.getSuppressedFields()` lists properties **blocked by allowed/disallowed field filters**. Not every unknown request parameter appears here; do not treat this list as a complete log of all HTTP keys.
- `setIgnoreUnknownFields(true)` by default ignores nonexistent properties; do not rely on it to prevent mass assignment on **existing** properties.
- `binder.validate()` runs only validators registered with the binder. Calling `bind(request)` alone **does not invoke** `binder.validate()` by default.

## 5. HTML form specials: checkbox markers and defaults

An unchecked HTML checkbox normally **does not submit** a parameter with the field name. If the target initially had `newsletter=true`, submitting a form with the checkbox unchecked could leave the old value intact unless the binder knows the checkbox was present on the form.

`WebDataBinder` supports two mechanisms:

**Field marker (default prefix `_`):**

~~~text
_newsletter=present
~~~

If `_newsletter` is present **without `newsletter`**, the binder understands the field was present on the form with no submitted value and resets the property to an appropriate empty value (for `boolean`, `false`). The marker value such as `present` does not matter; only the marker's presence serves as the signal.

**Field default (default prefix `!`):**

~~~text
!age=18
~~~

When `age` is not submitted, the binder can use `18` as the default and convert it to `int`. A default parameter takes precedence over a field marker for the same field if both are submitted.

HTML marker example:

~~~html
<input type="hidden" name="_newsletter" value="present">
<input type="checkbox" name="newsletter" value="true">
~~~

This is an HTML form example. If the checkbox is checked, the browser submits both `newsletter=true` and the marker; the actual value is bound. If unchecked, the browser submits only the marker so the property is reset to `false`. **Do not use markers for security authorization**: clients can freely submit or tamper with both the marker and the field.

Note that `ServletRequestParameterPropertyValues(request, "profile")` with a prefix like `profile_name` is a **prefix-filtering feature of the PropertyValues class**, completely distinct from `WebDataBinder`'s `_newsletter` marker and `!age` default. `ServletRequestDataBinder#bind(request)` does not use a `profile_` prefix by default.

## 6. Runnable example: testing the binder with HTTP parameters

Using **Java 17+** and a **Spring Boot 3+** Maven project, add these two dependencies if not already present:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Create **`src/test/java/com/example/binding/ServletRequestDataBinderTest.java`** with the full Java code. `MockHttpServletRequest` and `MockMultipartHttpServletRequest` come from `spring-test` (via the test starter) and can simulate a **parameter map parsed by the Servlet API** without starting a web server:

~~~java
package com.example.binding;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.mock.web.MockMultipartHttpServletRequest;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.ServletRequestDataBinder;
import org.springframework.web.multipart.MultipartFile;

import java.nio.charset.StandardCharsets;
import java.util.Arrays;

import static org.junit.jupiter.api.Assertions.*;

class ServletRequestDataBinderTest {

    @Test
    void bindsParametersAndSuppressesUnsafeProperty() {
        ProfileForm form = new ProfileForm();
        MockHttpServletRequest request =
                new MockHttpServletRequest("POST", "/profiles");
        request.addParameter("name", "Lan");
        request.addParameter("age", "26");
        request.addParameter("newsletter", "true");
        request.addParameter("address.city", "Da Nang");
        request.addParameter("admin", "true"); // Client sends an extra field.

        ServletRequestDataBinder binder =
                new ServletRequestDataBinder(form, "profileForm");
        binder.setAllowedFields(
                "name", "age", "newsletter", "address.city");
        binder.bind(request);

        BindingResult result = binder.getBindingResult();
        assertFalse(result.hasErrors());
        assertEquals("Lan", form.getName());
        assertEquals(26, form.getAge());
        assertTrue(form.isNewsletter());
        assertEquals("Da Nang", form.getAddress().getCity());
        assertFalse(form.isAdmin()); // Not bound.
        assertArrayEquals(
                new String[] {"admin"}, result.getSuppressedFields());

        System.out.println(
                form.getName() + " | " + form.getAge()
                + " | " + form.getAddress().getCity()
                + " | admin=" + form.isAdmin());
        System.out.println(
                "errors=" + result.getErrorCount()
                + ", suppressed=" + Arrays.toString(
                        result.getSuppressedFields()));
    }

    @Test
    void recordsTypeMismatchInsteadOfSilentlyAcceptingIt() {
        ProfileForm form = new ProfileForm();
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addParameter("age", "not-a-number");

        ServletRequestDataBinder binder =
                new ServletRequestDataBinder(form, "profileForm");
        binder.setAllowedFields("age");
        binder.bind(request);

        BindingResult result = binder.getBindingResult();
        assertTrue(result.hasFieldErrors("age"));
        assertEquals("typeMismatch",
                result.getFieldError("age").getCode());
        assertEquals(0, form.getAge());
    }

    @Test
    void resetsCheckboxWithFieldMarker() {
        ProfileForm form = new ProfileForm();
        form.setNewsletter(true); // Value before submit.
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addParameter("_newsletter", "present");
        // No "newsletter" parameter: checkbox is unchecked.

        ServletRequestDataBinder binder =
                new ServletRequestDataBinder(form, "profileForm");
        binder.setAllowedFields("newsletter");
        binder.bind(request);

        assertFalse(form.isNewsletter());
        assertFalse(binder.getBindingResult().hasErrors());
    }

    @Test
    void usesFieldDefaultWhenRealFieldIsMissing() {
        ProfileForm form = new ProfileForm();
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addParameter("!age", "18");

        ServletRequestDataBinder binder =
                new ServletRequestDataBinder(form, "profileForm");
        binder.setAllowedFields("age");
        binder.bind(request);

        assertEquals(18, form.getAge());
        assertFalse(binder.getBindingResult().hasErrors());
    }

    @Test
    void recordsRequiredFieldWhenMissing() {
        ProfileForm form = new ProfileForm();
        ServletRequestDataBinder binder =
                new ServletRequestDataBinder(form, "profileForm");
        binder.setRequiredFields("name");
        binder.bind(new MockHttpServletRequest());

        assertTrue(binder.getBindingResult().hasFieldErrors("name"));
        assertEquals("required",
                binder.getBindingResult()
                        .getFieldError("name").getCode());
    }

    @Test
    void bindsMultipartFileByPartName() {
        ProfileForm form = new ProfileForm();
        MockMultipartHttpServletRequest request =
                new MockMultipartHttpServletRequest();
        request.addFile(new MockMultipartFile(
                "avatar", "avatar.txt", "text/plain",
                "demo".getBytes(StandardCharsets.UTF_8)));

        ServletRequestDataBinder binder =
                new ServletRequestDataBinder(form, "profileForm");
        binder.setAllowedFields("avatar");
        binder.bind(request);

        assertNotNull(form.getAvatar());
        assertEquals("avatar.txt",
                form.getAvatar().getOriginalFilename());
        assertFalse(binder.getBindingResult().hasErrors());
    }

    public static class ProfileForm {
        private String name;
        private int age;
        private boolean newsletter;
        private boolean admin;
        private Address address = new Address();
        private MultipartFile avatar;

        public String getName() { return name; }
        public void setName(String name) { this.name = name; }

        public int getAge() { return age; }
        public void setAge(int age) { this.age = age; }

        public boolean isNewsletter() { return newsletter; }
        public void setNewsletter(boolean newsletter) {
            this.newsletter = newsletter;
        }

        public boolean isAdmin() { return admin; }
        public void setAdmin(boolean admin) { this.admin = admin; }

        public Address getAddress() { return address; }
        public void setAddress(Address address) {
            this.address = address;
        }

        public MultipartFile getAvatar() { return avatar; }
        public void setAvatar(MultipartFile avatar) {
            this.avatar = avatar;
        }
    }

    public static class Address {
        private String city;

        public String getCity() { return city; }
        public void setCity(String city) { this.city = city; }
    }
}
~~~

From the Spring Boot project root, run:

~~~bash
./mvnw test -Dtest=ServletRequestDataBinderTest
~~~

On Windows run `mvnw.cmd test -Dtest=ServletRequestDataBinderTest`; if Maven is installed globally, use `mvn test -Dtest=ServletRequestDataBinderTest`. When the tests pass, standard output (alongside Maven/JUnit logs) will include **two lines explicitly printed by the program** with this configuration:

~~~text
Lan | 26 | Da Nang | admin=false
errors=0, suppressed=[admin]
~~~

Key points to observe:

1. `name=Lan` is assigned to a `String`; `age=26` is converted by Spring from `String` to `int`; `address.city=Da Nang` goes into the nested JavaBean.
2. The client also sent `admin=true`, but `setAllowedFields(...)` blocks this property. The target keeps `admin=false` and `BindingResult#getSuppressedFields()` records `admin`.
3. `age=not-a-number` is not silently turned into a valid age; `BindingResult` contains a `FieldError` with code `typeMismatch`.
4. The `_newsletter` marker resets an existing boolean from `true` back to `false` when the real field is omitted.
5. The `!age=18` default provides a value when the request lacks `age`.
6. `setRequiredFields("name")` detects a missing `name` parameter; it **does not replace** Bean Validation `@NotBlank` when a user sends `name=""`.
7. `MockMultipartHttpServletRequest` simulates a parsed multipart request; the binder assigns `avatar` to the `MultipartFile` property matching the part name.

**Exact scope limitation of the demo:** `MockHttpServletRequest#addParameter` populates the parameter map directly to test the binder. It **does not** demonstrate how an actual Servlet container parses raw HTTP bodies, does not invoke controller/proxy layers, and does not automatically run Bean Validation. To test the full HTTP stack, use `MockMvc` or an integration test with Spring MVC.

## 7. In controllers: `@ModelAttribute` and `@InitBinder`

On Servlet MVC, the most common approach is declaring a `@ModelAttribute` parameter; the framework creates/configures the binder per request and populates `BindingResult`.

The following is a **controller snippet**, assuming `ProfileForm` is a public DTO with getters/setters similar to the example above and appropriate Spring imports exist:

~~~java
@Controller
@RequestMapping("/profiles")
class ProfileController {

    @InitBinder("profileForm")
    void configureProfileBinder(WebDataBinder binder) {
        binder.setAllowedFields(
                "name", "age", "newsletter", "address.city", "avatar");
    }

    @PostMapping
    String save(@ModelAttribute("profileForm") ProfileForm form,
                BindingResult result) {

        if (result.hasErrors()
                || result.getSuppressedFields().length > 0) {
            return "profile-form";
        }

        // Process only allowed and validated fields.
        return "profile-saved";
    }
}
~~~

`BindingResult` must be placed **immediately after** the corresponding `@ModelAttribute` parameter. `@InitBinder("profileForm")` customizes the binder only for the model attribute of that name; if `@InitBinder` omits a name, it can apply to multiple model attributes within the controller scope. In a larger application, `@ControllerAdvice` supports global policy, though you still need to know specifically which form may bind which properties.

To run Bean Validation on the form, add `@Valid` to `@ModelAttribute` when a validation provider and `spring-boot-starter-validation` (or equivalent setup) are present:

~~~java
String save(@Valid @ModelAttribute("profileForm") ProfileForm form,
            BindingResult result) {
    if (result.hasErrors()) {
        return "profile-form";
    }
    return "profile-saved";
}
~~~

This is also a **method snippet**, not a complete controller. `@Valid` triggers constraint checks on the DTO; `bind` is the data-assignment step. For `@RequestBody` JSON endpoints, the conversion path is `HttpMessageConverter`, as distinguished earlier.

### Constructor binding for immutable objects

Spring Framework **6.1+** supports `ServletRequestDataBinder#construct(ServletRequest)` to instantiate objects using a constructor and request parameters. In the MVC flow, a model attribute can be constructed via a constructor (including records), followed by property binding depending on configuration. This differs from `bind` onto an existing bean.

Example of an immutable form:

~~~java
public record CreateProfileForm(String name, Integer age) {
}
~~~

In an MVC controller:

~~~java
@PostMapping("/new-profiles")
String create(@ModelAttribute CreateProfileForm form) {
    // Spring can bind arguments through the data constructor.
    return "created";
}
~~~

These are **two separate illustrative snippets**. When using constructor binding, parameter name metadata and appropriate Spring configuration are needed to map request parameters. `@BindParam("http-name")` can be used if the wire name differs from the constructor parameter name. Do not bypass constructor binding rules on immutable DTOs by enabling unrestricted setter binding on business entities.

`DataBinder#setDeclarativeBinding(true)` is a Spring 6.1+ option to prefer only values **declared** in the constructor; setter/property binding proceeds only when allowed fields are configured. Choose this approach or dedicated form DTOs to restrict the surface clients can modify.

## 8. Security: mass assignment, nested fields, and allowed fields

**Mass assignment** occurs when the system binds a property that users were never intended to modify. For example, an entity has `role`, `admin`, `accountBalance`, `ownerId`, and an attacker sends:

~~~http
POST /profiles
Content-Type: application/x-www-form-urlencoded

name=Lan&admin=true&accountBalance=1000000
~~~

If these setters are invoked by the binder without restriction, the client can alter sensitive state. **HTTP input is untrusted**, including path variables, headers, form fields, and multipart metadata.

Mitigation steps:

1. **Use dedicated form DTOs** containing only fields the client is actually allowed to edit; do not bind directly to JPA entities with many internal properties.
2. **Prefer immutable constructor-bound DTOs** with explicitly declared fields. When using property binding, configure `setAllowedFields(...)`/`@InitBinder` for the required fields.
3. **Restrict nested property paths too.** Allowed fields can specify names such as `address.city`, `items[0].quantity`, or wildcard patterns when truly necessary, though overly broad wildcards can expose unintended fields.
4. **Inspect suppressed fields** in processing/monitoring flows where appropriate; blocking a field does not prove the rest of the request is valid.
5. **Do not confuse validation with authorization:** `@NotNull` and `@Valid` do not decide who is permitted to change `role`. Enforce permission checks at the service/API boundary.
6. **Limit auto-grow and nested structures** when accepting dynamic property paths; prevent clients from creating huge graphs via `items[999999]`.
7. **Do not rely solely on `setDisallowedFields(...)`.** Denylists easily miss newly added sensitive properties as DTOs/entities evolve; an explicit allowlist is much more resilient.

Example input:

~~~text
name=Lan
address.city=Da Nang
address.isVerified=true
admin=true
~~~

With `setAllowedFields("name", "address.city")`, the binder may only update `name` and `address.city` via property binding. `admin` and `address.isVerified` must not change even if the beans have corresponding setters. With constructor-bound DTOs, you must still carefully define which constructor arguments accept input and avoid declaring server-only fields as arbitrary inputs.

## 9. Extensions, configuration, and error handling

### 9.1. Extension point `addBindValues`

`ServletRequestDataBinder` provides:

~~~java
@Override
protected void addBindValues(
        MutablePropertyValues mpvs, ServletRequest request) {
    // Add or adjust values before doBind(...).
}
~~~

This is a **subclass snippet**, requiring `MutablePropertyValues`/`ServletRequest` imports and a class extending `ServletRequestDataBinder`. The default implementation of `addBindValues` is empty; when customizing a binder, you can add controlled extra values before `WebDataBinder#doBind`. **Do not automatically add untrusted request headers or server secrets into property values** if doing so could allow clients to overwrite sensitive properties.

### 9.2. Type conversion and formatters

`bind(request)` applies Spring's conversion mechanism. For example, `age=26` → `int` works with default type conversion; `date=2026-11-12` → `LocalDate` may require an appropriate formatter/conversion service. In Spring MVC, `@DateTimeFormat`, converters/formatters, and `@InitBinder` are common customization options. A parse failure is not automatically a business error; it can become a `FieldError` with code `typeMismatch`.

Do not manually call `Integer.parseInt(request.getParameter("age"))` in a controller if you are already using form binding: doing so creates two separate error-handling paths. Use `BindingResult` to re-render the form and preserve per-field error information.

### 9.3. When to use `closeNoCatch()`?

`ServletRequestDataBinder#closeNoCatch()` throws `ServletRequestBindingException` if `BindingResult` contains errors. It should only be used when binding errors must be treated as a fatal condition; in typical MVC forms, accepting `BindingResult` next to the model attribute and returning the form with error messages is more convenient. `closeNoCatch()` does not replace checking suppressed fields or business validation.

## 10. Practical checklist and common mistakes

| Symptom | Common cause | How to check/fix |
| --- | --- | --- |
| `@ModelAttribute` does not receive values from JSON | JSON body goes through `@RequestBody` message converters. | Use `@RequestBody` for JSON or send properly formatted form/query parameters. |
| `age` becomes `0` with a `typeMismatch` error | HTTP string cannot be converted to `int`. | Check `BindingResult.getFieldError("age")` and conversion service. |
| Unchecking a checkbox leaves the old value as `true` | Neither the field nor a marker was sent. | Add `_newsletter` or a form rendering mechanism that emits markers. |
| Multipart form does not bind the file | Request was not parsed as multipart or part name differs from property. | Check multipart resolver/config, part name, and property type. |
| URI variable does not appear when calling binder manually | Direct `ServletRequestDataBinder` does not automatically add path vars. | Use `@ModelAttribute`/MVC integration or map explicitly. |
| Sensitive data gets modified via another property | Broad entity binding or missing allowlist. | Dedicated DTO + allowed fields + authorization. |
| `@NotBlank` does not run after manual `binder.bind` | Binding is separate from validation. | Register/trigger validator and call `validate`, or use `@Valid` in MVC. |
| Unknown field is ignored without error | Unknown-field policy or not a writable property. | Use allowlist and observe suppressed fields; test real requests. |
| A nested field fails to bind | Missing getter/setter, wrong path, null target, or auto-grow config. | Verify JavaBean property paths and nested objects. |

Before going to production:

- [ ] Clarify whether input comes from query/form/multipart or JSON body; choose `@ModelAttribute` or `@RequestBody` accordingly.
- [ ] Use an appropriate form DTO, restricting setter binding via allowed fields or declarative/constructor binding.
- [ ] Use `BindingResult` to handle `typeMismatch`/`required` errors and monitor suppressed fields if needed.
- [ ] Test nested properties, repeated parameters, checkbox markers/defaults, multipart uploads, and type conversion errors.
- [ ] Ensure validation and authorization run at the proper layers; do not treat binding as validation or permission checking.
- [ ] Verify how additional URI/header sources behave in Spring MVC compared to using `ServletRequestDataBinder` directly.
- [ ] Do not alter binder configuration or rely on version-dependent behavior without integration tests.

## References

- Spring Framework API — `ServletRequestDataBinder` (`bind`, `construct`, `addBindValues`, multipart, `closeNoCatch` methods): https://docs.spring.io/spring-framework/docs/6.2.2/javadoc-api/org/springframework/web/bind/ServletRequestDataBinder.html
- Spring Framework API — `WebDataBinder` (field markers/defaults, multipart options): https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/bind/WebDataBinder.html
- Spring Framework API — `ServletRequestParameterPropertyValues` (request parameter values and prefixes): https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/bind/ServletRequestParameterPropertyValues.html
- Spring Framework Reference — MVC data binding, model security, `@InitBinder`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html
- Spring Framework Reference — `@ModelAttribute` and request parameter/URI variable/header sources: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
