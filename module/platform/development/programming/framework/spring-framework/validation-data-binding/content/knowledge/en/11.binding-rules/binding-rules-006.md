# setIgnoreUnknownFields and handling non-existent fields in Spring

## 1. The problem: a request contains a property the target object does not have

In Spring Framework, **data binding** is the process of taking input values (typically from request parameters, form fields, or a `PropertyValues` source) and assigning them to properties of a Java object. Developers define which properties the object can accept; a request sender, however, can submit any extra parameter names.

Suppose a DTO has one writable property named `name`:

~~~java
public class ProfileForm {
    private String name;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
~~~

A request submits name/value pairs:

~~~text
name=Lan
nickname=Lana
~~~

`name` has a matching setter. `nickname` has no writable property on `ProfileForm`. When Spring attempts **property binding**, it must decide whether to **ignore** or **error on** the name `nickname`.

The configuration method governing this decision is:

~~~java
dataBinder.setIgnoreUnknownFields(true);  // Ignore non-existent fields
dataBinder.setIgnoreUnknownFields(false); // Reject non-existent fields
~~~

`setIgnoreUnknownFields` belongs to `org.springframework.validation.DataBinder`. In Spring MVC, `org.springframework.web.bind.WebDataBinder` inherits this mechanism and can be configured via `@InitBinder`. **The default value is `true`**: the binder ignores parameters that do not correspond to writable target properties, rather than requiring every input name to exist.

This rule is easily mistaken for a validation mode, when in fact it determines **how the property accessor handles unknown property names during writes**. It does not dictate HTTP status codes, is not a security allowlist, and does not replace required-field checks.

### Learning outcomes

After this lesson, you will be able to:

1. Accurately explain `setIgnoreUnknownFields(boolean)` and its default state.
2. Predict outcomes when a request contains a non-existent field, a field without a setter, an invalid type, or a field blocked by allowed fields.
3. Distinguish **unknown**, **invalid nested path**, **missing required**, **type mismatch**, and **suppressed field**.
4. Build a runnable `DataBinder` example, catch the right exception in strict mode, and inspect `BindingResult`.
5. Configure `@InitBinder` for a model attribute in Spring MVC with proper scoping.
6. Choose whether to ignore or reject unexpected inputs based on API contracts and binding safety.

## 2. API and default behavior

API signatures:

~~~java
public void setIgnoreUnknownFields(boolean ignoreUnknownFields);
public boolean isIgnoreUnknownFields();
~~~

Across widely used Spring Framework versions such as 5.3, 6.0, 6.1, 6.2, and 7.0, the Javadoc specifies the default `ignoreUnknownFields = true`. Always cross-check against the **actual library version** when maintaining an application.

| Configuration | When encountering a property name with no writable target | Meaning |
| --- | --- | --- |
| Setter not called | Typically ignored | Default `true` |
| `setIgnoreUnknownFields(true)` | Ignored | Favors tolerating extra parameters |
| `setIgnoreUnknownFields(false)` | Not ignored; may throw `NotWritablePropertyException` | Requires input names to match writable properties |
| `setAllowedFields("name")` | Out-of-whitelist fields are filtered out before assignment | Policy for selecting bindable fields, independent of the unknown flag |
| Constructor binding via `construct(...)` | Uses only values needed for the constructor | This flag **does not apply** to the constructor binding path |

Boundary noted in the Javadoc: this setting applies when the binder invokes **`bind(PropertyValues)`**; it does not alter reading values through `getBindingResult()` and does not automatically alter constructor binding. For JSON `@RequestBody`, reading the payload through an HTTP message converter/JSON deserializer is a separate mechanism.

### 2.1. "Non-existent" in terms of writability

Under the default JavaBeans property binding strategy, Spring looks for a writable property through a property accessor. Thus:

- **No `nickname` property**: this is an unknown field.
- **Getter exists without a setter** for `nickname`: the property is readable but not writable; this case can also lead to `NotWritablePropertyException` when the binder tries to assign it.
- **Has setter `setAge(Integer)` but input is `"abc"`**: the `age` field exists, yet the value has the wrong type; this is a **type mismatch**, not unknown.
- **Path `address.city` exists, yet `address` is null and cannot auto-instantiate**: this can be an **invalid nested path**, distinct from unknown.
- **Omitting `name`**: this is a *missing* field, distinct from sending a field name the object does not recognize.

Access strategy also matters: `DataBinder.initDirectFieldAccess()` allows binding directly onto fields instead of via getters/setters. A field without a setter can still be a valid target under direct field access if access conditions are met. Therefore, when evaluating "unknown", identify whether the binder uses **BeanProperty access** or **DirectFieldAccess**.

Do not equate "the class has a member of this name" with "the binder can successfully write to this path".

### 2.2. A before-and-after example

Given `ProfileForm` with only `name` and input `name=Lan&nickname=Lana`:

~~~text
Default: ignoreUnknownFields = true
    name      -> setter invoked -> target.name = "Lan"
    nickname  -> no writable property found -> ignored
    bind(...) -> completes, assuming no other errors

Strict: ignoreUnknownFields = false
    name      -> writable property
    nickname  -> no writable property found
    bind(...) -> may throw NotWritablePropertyException
~~~

Code should not assume strict mode will always record a `FieldError` for the controller to read from `BindingResult`. Exceptions caused by **invalid field names** are handled differently from ordinary conversion errors.

## 3. Where does Spring check unknown fields in the pipeline?

For property binding, the approximate execution model is:

~~~text
PropertyValues from request or data source
             |
             v
DataBinder / WebDataBinder
             |
             +--> filter fields by allowedFields / disallowedFields
             |
             +--> check requiredFields (if configured)
             |
             v
PropertyAccessor.setPropertyValues(
    values, ignoreUnknown, ignoreInvalid
)
             |
             +--> Writable name + conversion OK -> assign target
             |
             +--> Non-writable name:
             |       ignoreUnknown=true  -> ignore
             |       ignoreUnknown=false -> NotWritablePropertyException
             |
             +--> Unreachable nested path:
             |       handled per ignoreInvalid and nested path settings
             |
             +--> PropertyAccessExceptions may be batched:
                     BindingResult receives conversion/write errors
~~~

In `AbstractPropertyAccessor`'s implementation, a `NotWritablePropertyException` is ignored if `ignoreUnknown` is enabled; if disabled, the exception is thrown. Batch-collectible `PropertyAccessException`s are accumulated, and `DataBinder` translates eligible ones into binding error entries. Exact error handling depends on the binding path and Spring version.

Key consequences to remember:

- **Ignoring unknown fields** does not cause Spring to record an error for that field. `result.hasErrors()` can still be `false`.
- **Rejecting unknown fields** can make `bind(...)` throw an exception, so code immediately following `bind` might **not execute**.
- **Filtering via `setAllowedFields`** occurs before applying property values. An unknown field outside the whitelist can be stripped before the strict accessor ever sees it.
- **Binding is not transactional**: if several properties are assigned before hitting a fatal error, do not assume Spring rolls back partial changes on the object. For atomic APIs, separate validation and business execution into distinct steps.

## 4. Standalone Java 17+ example: three policies

This demo uses Spring Context 6.2.12, Java 17+, and Gradle. No Spring Boot or servlet container is required. It keeps the same DTO and input across three policies for direct comparison.

Create a test project directory, then add the following files:

**`settings.gradle`**

~~~groovy
rootProject.name = 'unknown-field-binding-demo'
~~~

**`build.gradle`**

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.12'
}

application {
    mainClass = 'UnknownFieldBindingDemo'
}
~~~

**`src/main/java/UnknownFieldBindingDemo.java`**

~~~java
import java.util.Arrays;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.beans.NotWritablePropertyException;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

public final class UnknownFieldBindingDemo {

    public static final class ProfileForm {
        private String name;

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }
    }

    public static void main(String[] args) {
        runCase("default", true, false);
        runCase("strict", false, false);
        runCase("strict+allow-list", false, true);
    }

    private static void runCase(
            String label, boolean ignoreUnknown, boolean allowOnlyName) {

        ProfileForm target = new ProfileForm();
        DataBinder binder = new DataBinder(target, "profileForm");
        binder.setIgnoreUnknownFields(ignoreUnknown);

        if (allowOnlyName) {
            binder.setAllowedFields("name");
        }

        MutablePropertyValues input = new MutablePropertyValues();
        input.add("name", "Lan");
        input.add("nickname", "Lana");

        try {
            binder.bind(input);
            BindingResult result = binder.getBindingResult();

            System.out.println(label
                    + ": ignore=" + binder.isIgnoreUnknownFields()
                    + ", name=" + target.getName()
                    + ", errors=" + result.getErrorCount()
                    + ", suppressed="
                    + Arrays.toString(result.getSuppressedFields()));
        } catch (NotWritablePropertyException ex) {
            System.out.println(label
                    + ": exception=" + ex.getClass().getSimpleName()
                    + ", property=" + ex.getPropertyName());
        }
    }
}
~~~

Run from the directory containing `build.gradle`:

~~~bash
gradle -q run
~~~

If using the Gradle Wrapper, run `./gradlew -q run` on Linux/macOS or `gradlew.bat -q run` on Windows. Gradle needs Maven Central access if dependencies are not cached.

**Expected stdout**:

~~~text
default: ignore=true, name=Lan, errors=0, suppressed=[]
strict: exception=NotWritablePropertyException, property=nickname
strict+allow-list: ignore=false, name=Lan, errors=0, suppressed=[nickname]
~~~

### 4.1. Explaining each output line

**`default` case:** `ignoreUnknownFields=true`. `name` binds successfully, while `nickname` has no writable property and is ignored. There are no conversion or validation errors, so `errors=0`. The `suppressed` array is empty: ignoring unknown fields is not the same as recording **suppressed fields** from a whitelist.

**`strict` case:** `ignoreUnknownFields=false` with no allowed fields configured. `nickname` reaches the property accessor, yet `ProfileForm` has no setter for it. `NotWritablePropertyException` is thrown, and the catch block prints the property name. Never build business logic assuming `name` was or was not already assigned after catching an exception; processing order and partial mutations can affect state.

**`strict+allow-list` case:** strict mode is still enabled, yet `setAllowedFields("name")` strips `nickname` from the property values before assignment. Binding never encounters an unknown property, completes cleanly, and records `suppressed=[nickname]`. This proves **strict + whitelist does not always mean "every unknown field throws an exception"**.

While experimenting, try renaming `nickname` to `name` and adding another writable field to observe the effect. Then try removing `input.add("name", "Lan")`; omitting `name` is not flagged as a missing field by `setIgnoreUnknownFields(false)`. To require a field's presence, see `setRequiredFields` next.

## 5. Distinguishing five easily confused scenarios

| Scenario | Example | Relevant mechanism | Typical outcome |
| --- | --- | --- | --- |
| **Unknown** | Input `nickname`, DTO has no writable property | `setIgnoreUnknownFields` | Ignored by default; strict mode can throw `NotWritablePropertyException` |
| **Missing required** | `name` omitted even though form requires it | `setRequiredFields` or validation like `@NotBlank`/`@NotNull` | `"required"` / constraint error depending on setup |
| **Invalid nested path** | `address.city` when `address` cannot be traversed | `setIgnoreInvalidFields`, `setAutoGrowNestedPaths` | May throw `NullValueInNestedPathException` or be ignored |
| **Type mismatch** | `age=abc` when `age` is `Integer` | `ConversionService`, `BindingErrorProcessor` | Typically a `FieldError` with code `typeMismatch` in `BindingResult` |
| **Disallowed / suppressed** | `role=ADMIN` when `allowedFields={"name"}` | `setAllowedFields`, `getSuppressedFields` | Input filtered before binding; inspect suppressed fields |

Each category must be identified at the **exact stage where it occurs**:

- Unknown means a **non-writable property name**, even when the value string looks valid.
- Type mismatch means a **valid property name whose value cannot convert to the target type**.
- Missing required means **absent input**, distinct from sending extra input.
- Invalid nested field may exist in the class declaration, yet the runtime object graph cannot reach it.
- Suppressed means a **policy decision forbidding binding** via whitelist/blacklist; it does not automatically generate a `FieldError`.

### 5.1. Example: setRequiredFields does not replace unknown checks

~~~java
DataBinder binder = new DataBinder(new ProfileForm(), "profileForm");
binder.setRequiredFields("name");
binder.setIgnoreUnknownFields(false);
~~~

When `name` is missing from `PropertyValues`, the binder can record a `"required"` error via the default `BindingErrorProcessor`. This differs from receiving `nickname` with no matching property.

`setRequiredFields` checks input value presence according to the binder's rules, which is not identical to every Bean Validation constraint. For example, a field submitted as an empty string may demand extra business validation. The word "required" in HTML, Jakarta Validation, and `DataBinder` can entail different conditions; do not assume they share a single switch.

### 5.2. Example: invalid type does not become unknown

A DTO with `Integer age` and standard getter/setter:

~~~java
public class AgeForm {
    private Integer age;

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }
}
~~~

With `age=abc`, `age` is a writable property. `setIgnoreUnknownFields(true)` **does not make `"abc"` valid**, nor is its job to ignore type conversion failures. Under normal binder configuration, `BindingResult.hasFieldErrors("age")` becomes `true`, and `FieldError` holds the rejected value and an error code like `typeMismatch`.

To reject invalid values, handle conversion and validation errors; do not try to use strict unknown mode as a substitute for type checking.

## 6. Unknown, read-only, and nested paths: subtle decisions

### 6.1. Property with getter but no setter

Example:

~~~java
public class ReadOnlyForm {
    private final String id = "fixed";

    public String getId() {
        return id;
    }
}
~~~

`id` **is readable** via its getter, yet default JavaBeans property binding has no setter to mutate it. Input `id=other` is typically treated as a non-writable property: ignored by default, errored in strict mode. Having a field `id` in the class does not automatically make it writable.

If an application wants an immutable value, omitting the setter is part of the design, though using a **dedicated input DTO** rather than binding straight onto a domain entity with internal fields is even better.

### 6.2. Null in a nested path is not necessarily unknown

Consider:

~~~java
public class ContactForm {
    private Address address;

    public Address getAddress() {
        return address;
    }

    public void setAddress(Address address) {
        this.address = address;
    }
}

public class Address {
    private String city;

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }
}
~~~

If `address` is `null` while the input contains `address.city=Hanoi`, the outcome depends on **auto-grow nested paths** and binder configuration. If auto-grow is enabled and the nested class can be instantiated, `address` can be created and `city` assigned. If the path cannot be traversed, you may get `NullValueInNestedPathException`.

Two distinct APIs:

~~~java
binder.setIgnoreUnknownFields(false); // Handles non-writable property names
binder.setIgnoreInvalidFields(true);  // Ignores existing nested paths that cannot be accessed
~~~

`ignoreInvalidFields` defaults to `false`; when enabled, it skips certain unreachable nested paths. **Do not turn this flag on merely to "silence" input errors** if dropping an important value could cause wrong business decisions. Conversely, enabling `ignoreUnknownFields` does not guarantee all null nested paths are ignored.

The code above illustrates two structurally separate Java classes; when running it yourself, place them in separate files or adjust modifiers per Java rules, then test with your application's actual auto-grow settings.

### 6.3. Property names and casing

For a JavaBeans property `displayName`, input `displayName=An` normally matches, whereas `displayname=An` should not be assumed to map to the same property by default. On the binding path, property names follow property accessor rules; avoid arbitrarily rewriting parameter names without an explicit contract.

In web applications, a typo in `<input name="...">` is easily missed silently when `ignoreUnknownFields=true`. If a form fails to update data even though the HTTP request carries the parameter, inspect the **exact property name** and setter before looking at validation.

## 7. Configuring in Spring MVC with @InitBinder

In Spring MVC, `WebDataBinder` shares behavior with `DataBinder`. For example, a controller handling `profileForm` can enable strict mode for that model attribute alone:

~~~java
package com.example.profile;

import org.springframework.stereotype.Controller;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;

@Controller
public class ProfileController {

    @InitBinder("profileForm")
    public void configure(WebDataBinder binder) {
        binder.setIgnoreUnknownFields(false);
    }

    @PostMapping("/profiles")
    public String submit(
            @ModelAttribute("profileForm") ProfileForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return "profile/form";
        }

        return "redirect:/profiles";
    }
}
~~~

This is an **integration example** (placed inside a Spring MVC app with a `ProfileForm` class, view engine, and redirect route), not a standalone Java program. `@InitBinder("profileForm")` scopes customization to the attribute of that name within this controller. `WebDataBinder` is created per request/binding as appropriate and should never be stored as singleton controller state.

With `name=Lan`, binding proceeds normally. However, if a user submits `nickname=Lana` and the DTO has no writable property:

- Strict mode can make binding throw `NotWritablePropertyException` while resolving `@ModelAttribute`.
- The controller method might **not even be invoked**, even with a `BindingResult errors` parameter immediately following `@ModelAttribute`.
- `BindingResult.hasErrors()` is not guaranteed to capture every unknown-property exception.
- HTTP status and response body depend on MVC exception handling, `@ControllerAdvice`, error response configuration, and application setup; **never promise HTTP 400 unconditionally** without testing on the actual stack.

If a public API contract requires rejecting all extra parameters with HTTP 400, design and test the appropriate exception/validation handler; do not flip one flag and assume it constitutes a complete HTTP contract.

### 7.1. Global customization can affect other endpoints

Putting `@InitBinder` inside an unscoped `@ControllerAdvice` affects many controllers at once. HTML/form requests with extra parameters, framework-specific markers, or legacy clients may behave differently.

Before enabling strict mode application-wide:

1. List affected model attributes and the actual field names submitted by forms.
2. Verify whether endpoints use `@ModelAttribute` query/form property binding.
3. Test valid forms, forms with extra fields, and forms with missing fields.
4. Check exception handlers and response contracts.
5. Consider scoping configuration only to DTOs/endpoints needing strict enforcement.
6. Test auxiliary framework parameters or form markup rather than assuming every request parameter binds verbatim.

`@InitBinder` can configure conversion, formatters, allowed fields, validators, and other binder options. Scoping prevents unintended behavioral changes in unrelated controllers.

## 8. Why is setAllowedFields more important than strict unknown for sensitive data?

This is the decisive point in secure binding design.

Suppose a target class has two writable properties:

~~~java
public class AccountForm {
    private String displayName;
    private boolean administrator;

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public boolean isAdministrator() {
        return administrator;
    }

    public void setAdministrator(boolean administrator) {
        this.administrator = administrator;
    }
}
~~~

Input `administrator=true` is **not an unknown field**: the DTO has a matching setter. Neither `setIgnoreUnknownFields(true)` nor `setIgnoreUnknownFields(false)` blocks assigning this property.

Thus, if clients may only edit the display name:

~~~java
@InitBinder("accountForm")
public void configureAccount(WebDataBinder binder) {
    binder.setAllowedFields("displayName");
}
~~~

Whitelisting `displayName` decides **which properties** may be modified; strict unknown only decides how to treat **non-writable properties**. Design DTOs containing only accepted fields, and apply an allow-list for property binding where needed. For permissions, account status, balance, or roles, enforce authorization in the business layer; never treat the binder as the sole security boundary.

A combination that can surprise developers:

~~~java
binder.setAllowedFields("displayName");
binder.setIgnoreUnknownFields(false);
~~~

If a client sends `displayName=A&administrator=true&strange=x`:

- `displayName` is in the allow-list.
- `administrator`, though an existing property, is excluded from property binding.
- `strange` does not exist and is also excluded from binding because it is outside the allow-list.
- `getSuppressedFields()` can record the blocked fields.
- Strict mode will not necessarily throw an unknown-property exception, because the field was filtered from the inputs before the property accessor ran.

If the requirement is "detect and reject **any** key the client is not allowed to send", validate input keys against the schema/contract at the request boundary or handle suppressed fields per policy. `setAllowedFields` **filters** by default rather than always throwing an exception per forbidden field.

### 8.1. Should you explicitly reject suppressed fields?

Yes, if the business contract requires requests with forbidden fields to be explicitly rejected. With plain `DataBinder`, after `bind(...)` finishes:

~~~java
String[] suppressed = binder.getBindingResult().getSuppressedFields();
if (suppressed.length > 0) {
    throw new IllegalArgumentException("Unsupported input properties");
}
~~~

This **snippet** illustrates the policy and does not itself map to an HTTP status. In web controllers, place this logic where binding/validation results are inspected and ensure partially mutated objects are never used before rejecting. Do not return internal sensitive field lists to users unnecessarily.

When logging, cap length/frequency and avoid printing raw input values. An attacker could intentionally send thousands of parameter names to generate log noise.

## 9. Constructor binding is outside this flag's scope

Spring can construct targets via constructor binding, which is especially useful for immutable objects, records, or DTOs describing only valid input data. The `setIgnoreUnknownFields` Javadoc explicitly states: this flag applies to **property binding via `bind(PropertyValues)`**, not to `construct(...)`, because constructor binding fetches the values needed to instantiate the object.

DTO example:

~~~java
public record CreateProfileRequest(String name, int age) {
}
~~~

This record has only two components, `name` and `age`. How constructor binding handles ignoring extra keys, missing-parameter errors, or type conversions depends on the resolver and version/configuration. Do not infer that `setIgnoreUnknownFields(false)` turns constructor binding into a "strict schema validator" across all keys.

Likewise, `DataBinder.setDeclarativeBinding(true)` (since Spring Framework 6.1) restricts binding declaratively: constructor binding and property binding only when `allowedFields` is configured. It is not a synonym for `setIgnoreUnknownFields(false)`.

Different goals:

| Goal | Appropriate approach |
| --- | --- |
| Immutable input objects | Constructor binding / suitable record DTO |
| Restricting which writable properties can update | Dedicated DTO + `setAllowedFields` for property binding |
| Detecting non-writable property names | `setIgnoreUnknownFields(false)` in property binding |
| Detecting all keys outside the API contract | Explicit request/schema validation, including suppressed fields if needed |
| Validating value correctness | Conversion + Bean Validation / business validators |
| Enforcing permission to edit data | Authorization in the business layer |

## 10. JSON @RequestBody and other binders

A common mistake is setting `setIgnoreUnknownFields(false)` expecting a JSON body with unknown keys to be rejected. In Spring MVC:

~~~java
@PostMapping("/profiles/json")
public String submitJson(@RequestBody CreateProfileRequest request) {
    return request.name();
}
~~~

This is a **snippet inside a REST controller**, not a standalone app. JSON data is converted into objects via `HttpMessageConverter` (typically Jackson). Unknown JSON property handling is governed by the JSON mapper's rules, annotations/configuration, and version—such as Jackson's unknown-property policy. It is **not automatically controlled by `DataBinder.setIgnoreUnknownFields`** on a separate `@ModelAttribute`.

Separate three paths:

~~~text
?name=Lan&nickname=Lana or form-urlencoded
    -> @ModelAttribute / WebDataBinder property binding
    -> setIgnoreUnknownFields may participate

{"name":"Lan","nickname":"Lana"} in @RequestBody JSON
    -> HttpMessageConverter / JSON mapper
    -> JSON mapper's unknown-property rules

new CreateProfileRequest(name, age) via constructor binding
    -> Resolver picks constructor parameters
    -> setIgnoreUnknownFields does not check all keys
~~~

In Spring Boot, the configuration annotation property `@ConfigurationProperties(ignoreUnknownFields = ...)` belongs to **Spring Boot's configuration binding mechanism**. Despite the similar name, it is not a method on an MVC `WebDataBinder` and should not be cited as evidence for form request behavior.

Test JSON and form/query endpoints separately, especially when supporting multiple client versions or migrating systems.

## 11. Choosing an ignore or reject policy per requirement

There is no single right choice for every endpoint. Weigh the **input contract**, compatibility, and how users recover from errors.

| Context | Typical sensible option | Reason |
| --- | --- | --- |
| Evolving HTML form, legacy clients send harmless extra fields | Keep default `true` | Avoid breaking submissions over minor extra parameters |
| Strict form-urlencoded API needing typo detection | Consider `false` + tested error handler | Unknown fields do not disappear silently |
| Account profile update form | Dedicated DTO + `setAllowedFields` | Prevents assigning forbidden properties even if they exist |
| Need to reject all keys outside allow-list | Pre-validate request keys or inspect suppressed fields | Strict flag is **insufficient** once allow-list filters keys |
| Form with many optional nested objects | Test nested auto-grow and `ignoreInvalidFields` | Avoid dropping important data or hitting null path failures |
| JSON API | Configure and test the JSON deserializer | Do not rely on MVC property-binding flags |
| Constructor-bound immutable DTO | Define constructor/resolver contract and validation | Strict unknown does not apply directly |

For public APIs, if a key is rejected, return a clear contract-level message ("unknown input field", "unsupported parameter") without leaking stack traces or internal property details. If keys are ignored, consider metrics or contract tests so field-name typos do not slip through silently during development.

**Practical decision:** use a whitelist to define *what may be bound*; use strict unknown when you want errors on *non-writable property names* in property binding with a proper exception-handling strategy; use validation to verify *whether values are valid*.

## 12. Do unknown-field errors automatically become HTTP 400?

Do not treat `setIgnoreUnknownFields(false)` as an HTTP response builder. This API lives in the binding layer; thrown exceptions pass through argument resolvers, MVC exception handling, custom application handlers, and framework error mechanisms.

Therefore, clarify:

1. Does the endpoint go through `WebDataBinder.bind(...)`?
2. Is the request using `@ModelAttribute` or `@RequestBody`?
3. Was the unknown field already stripped by allowed fields?
4. When strict mode is enabled, which exact exception is thrown on your running Spring version?
5. Is the controller invoked? Is there a custom `@ControllerAdvice`?
6. What status and error body does the product's public API contract specify?

`NotWritablePropertyException` thrown by the property accessor is an exception from the property processing layer; do not assume it always becomes a `FieldError`. `BindingResult` typically captures binding/validation errors the binder can collect; a non-writable property error in strict mode can abort before the controller reads the result.

If you want to actively return 400, use a scoped `@ExceptionHandler` with exception types verified via integration tests, or validate input schemas before binding. Never catch every `BeansException` broadly and return 400, as some failures may indicate server bugs rather than bad requests.

## 13. Regression tests you should have

Create datasets and assertions for the same DTO on the exact Framework/Boot version you run. Minimum test cases:

| Case | Input / configuration | Verifiable expectation |
| --- | --- | --- |
| 1. Happy path | `name=Lan` | `target.name` is assigned |
| 2. Default unknown | `name=Lan&nickname=Lana`, `true` | Binding completes; unknown ignored; no `typeMismatch` generated |
| 3. Strict unknown | Same input, `false` | Non-writable property exception is observed |
| 4. Known invalid value | `age=abc` with `Integer age` | Conversion error; **not** treated as unknown |
| 5. Read-only | `id=other`, only `getId()` exists | Verify non-writable property behavior |
| 6. Missing required | `name` absent, `setRequiredFields("name")` configured | Binder missing-field error |
| 7. Suppressed field | `setAllowedFields("name")`, send `role` | `getSuppressedFields()` records blocked field |
| 8. Strict + allow-list | `false` and whitelist, send unknown outside whitelist | Field may be suppressed before strict check |
| 9. Nested null path | `address.city` when `address` is null | Outcome depends on auto-grow / ignoreInvalid |
| 10. MVC form | `@ModelAttribute` + `@InitBinder` | Verify controller invocation, exception/status/body |
| 11. JSON body | JSON with extra property | Outcome comes from JSON mapper, not property-binding flag |
| 12. Security | Field has setter, yet client is not allowed to edit it | DTO/allowed fields block update; service still checks permissions |

When testing strict mode, besides asserting the exception type, assert the **business invariant**: the database-writing service must not execute if the request is rejected. Do not check only `BindingResult.hasErrors()`, because an unknown-property exception can occur before that path.

Unit assertion example (illustrated in JUnit Jupiter with full Spring dependencies):

~~~java
assertThrows(NotWritablePropertyException.class,
        () -> binder.bind(values));
~~~

This assumes `binder` has `setIgnoreUnknownFields(false)` configured, `values` contains a non-writable field, and `org.junit.jupiter.api.Assertions.assertThrows` is imported. If `setAllowedFields` filters that field out first, the assertion must change: do not assert an exception that no longer occurs.

### Testing at the DataBinder level before MockMvc

Prefer two layers of tests:

- **`DataBinder` unit tests:** fast, isolating `ignoreUnknown`/`allowedFields`/`suppressed`/`invalid`/`typeMismatch` rules. You can inspect exception classes and target state directly.
- **MockMvc or MVC integration tests:** verify `@InitBinder` applies to the right model name, real request parameters convert into `PropertyValues` as expected, and error handlers return the contracted status/body.

If unit tests pass yet MockMvc does not throw on JSON input, check the input path: JSON deserialization does not go through the property binder's flag.

## 14. Common troubleshooting checklist

### "Renamed an input yet the server still returns success"

- Check `<input name="...">` or the actual query parameter name.
- Check getters/setters, JavaBeans naming, and field access mode.
- Check `isIgnoreUnknownFields()`; default `true` can silently ignore typos.
- Check that the binder uses the expected DTO class/version.
- If strictness is required, add a test with an unknown name and observe exception/HTTP behavior.

### "Set false yet no FieldError appears in BindingResult"

- `NotWritablePropertyException` can be thrown right inside `bind`.
- Inspect the stack trace and property accessor entry point.
- Do not expect `BindingResult` to capture every fatal failure.
- If the API needs form errors displayed instead of an exception, design an appropriate error translation layer rather than swallowing exceptions globally.

### "Set false yet extra fields are still ignored"

- Did `setAllowedFields` or `setDisallowedFields` strip the field before writing?
- Is the controller using constructor binding or JSON instead of property binding?
- Does `@InitBinder` target the exact model attribute name and controller scope?
- Is the binder using the same configuration/instance you inspected?
- Is the property name truly unknown, or does a matching writable setter/field exist?

### "A nested field fails to bind"

- Verify the exact `address.city` path and object graph.
- Check for null intermediate objects, nested type instantiability, and `setAutoGrowNestedPaths`.
- Distinguish `ignoreInvalidFields` from `ignoreUnknownFields`.
- Inspect the specific exception type instead of enabling both flags to mask errors.

### "Is enabling strict mode a protection against mass assignment?"

- Not sufficient: a dangerous property that has a setter is still a **known** property.
- Use dedicated input DTOs, `allowedFields` whitelists, authorization, and invariant checks in the service.
- If the contract forbids extra keys, inspect all received keys at the request boundary or track suppressed fields.
- Test with a known-but-forbidden field, not only an unknown field.

### "Controller returns 500 instead of 400"

- Identify the exact exception and where it was thrown.
- Do not infer HTTP status mapping from the `setIgnoreUnknownFields` API.
- Design a consistent error contract using narrow exception handlers or request validation.
- Avoid accidentally turning internal programming bugs into "bad request" responses.
- Test status/body again with Spring MVC/Boot and your real configuration.

## 15. Self-check questions

1. **What is the default of `setIgnoreUnknownFields`?** — `true`; unknown properties in property binding are normally ignored.
2. **What error does `false` typically cause if a property name is not writable?** — It can throw `NotWritablePropertyException`.
3. **Do unknown fields always create a `FieldError`?** — No; by default they may be ignored, and strict mode may throw an exception directly.
4. **Does `setAllowedFields` with `setIgnoreUnknownFields(false)` automatically reject every out-of-whitelist field with an exception?** — No. Blocked fields are typically suppressed before the property accessor runs.
5. **What does `getSuppressedFields()` record?** — Fields excluded from property binding by allow/disallow rules; it does not automatically list ignored unknown fields.
6. **Is `age=abc` into `Integer age` an unknown field?** — No, that is a type conversion error.
7. **Does `setIgnoreUnknownFields(false)` treat missing `age` in a request as an error?** — Not merely for being absent; use required/validation rules if needed.
8. **What does `setIgnoreInvalidFields` check?** — Fields/paths that may exist yet are unreachable, such as a nested path through a null value that cannot auto-instantiate.
9. **Does this flag automatically govern unknown JSON keys in `@RequestBody`?** — No; the JSON mapper has its own mechanism.
10. **If a DTO has a writable `role` property, does strict unknown block `role=ADMIN`?** — Not by strictness alone; use DTOs, allowed fields, and authorization.
11. **Why run MockMvc tests after binder unit tests?** — Because request routing, model attribute names, handlers, and HTTP status depend on MVC configuration.
12. **Should database writes continue after a strict binder throws an exception?** — No; invalid requests must be handled at the boundary before executing business logic.

## 16. Official references

- [Spring Framework – DataBinder Javadoc (6.1.0)](https://docs.spring.io/spring-framework/docs/6.1.0/javadoc-api/org/springframework/validation/DataBinder.html), covering `setIgnoreUnknownFields`, `setIgnoreInvalidFields`, `setAllowedFields`, and `bind`.
- [Spring Framework – DataBinder Javadoc (6.2.x)](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/DataBinder.html), for checking APIs on the application branch.
- [Spring Framework – PropertyAccessor Javadoc (6.2.6)](https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/beans/PropertyAccessor.html), `setPropertyValues` contract and exceptions.
- [Spring Framework – NotWritablePropertyException Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/NotWritablePropertyException.html).
- [Spring Framework – BindingResult Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/BindingResult.html).
- [Spring Framework – MVC Data Binding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html), guidance on DTOs and allowed fields.
- [Spring Framework – @InitBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html), binder configuration scope.
- [Spring Framework – Core Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html), binder mechanisms, property paths, and validation.
- [Spring Framework 5.3.36 – DataBinder](https://docs.spring.io/spring-framework/docs/5.3.36/javadoc-api/org/springframework/validation/DataBinder.html), reference for pre-Spring 6 behavior.

**Key takeaway:** `setIgnoreUnknownFields(true)` lets property binding ignore non-writable property names; `false` surfaces name errors on that binding path. This rule is **different** from choosing allowed fields (`setAllowedFields`), type conversion errors, and value validation. Choose a policy matching your input contract, handle exceptions explicitly, and test real requests before relying on strict mode.
