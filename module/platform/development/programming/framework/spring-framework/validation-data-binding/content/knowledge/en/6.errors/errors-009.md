# BindingResult Data Model and Object Name in Spring

## 1. What Problem Does BindingResult Solve?

When Spring receives data from a form, query parameters, or other request values to populate a Java object, two outcomes must be retained:

1. **The target object** with the properties that were assigned successfully.
2. **Error information from the binding/validation pass**: object-wide errors, per-property errors, error codes, rejected values, and data needed to re-render the form.

`org.springframework.validation.BindingResult` is the interface that gathers those outcomes. It extends `Errors` while adding target access, model-attribute generation, and specific binding metadata. Thus `BindingResult` is not a simple `Map<String, String>` of error messages; it is a **structured result attached to an object identified by an object name**.

For example, a user submits a registration form with:

~~~text
name=
age=abc
role=ADMIN
~~~

Suppose the target object allows binding only `name` and `age`, and `age` has type `Integer`:

- `name` can be assigned as an empty string. If the application checks "name is required", a `FieldError` is added afterward.
- `age` cannot convert from `"abc"` to `Integer`, which produces a `typeMismatch` binding error. The invalid input still needs to be retained in the error details so the user can fix it.
- `role` is outside the list of bindable fields, so it is **suppressed**. This does not automatically become a `FieldError`.
- If a form-wide rule fails, such as two incompatible values, the application can add a **global error** (`ObjectError`).

Conceptual model:

~~~text
DataBinder / WebDataBinder
├── target: RegistrationForm
├── objectName: "registrationForm"
└── BindingResult
    ├── objectName: "registrationForm"
    ├── target: same RegistrationForm instance (once instantiated)
    ├── globalErrors: List<ObjectError>
    ├── fieldErrors: List<FieldError>
    │   ├── field: "age", rejectedValue: "abc", bindingFailure: true
    │   └── field: "name", rejectedValue: "", bindingFailure: false
    ├── suppressedFields: ["role"]
    └── getModel()
        ├── "registrationForm" → form object
        └── "org.springframework.validation.BindingResult.registrationForm"
            → the BindingResult itself
~~~

The name `registrationForm` is not decorative: it connects the object, errors, and form view. Understanding object names is essential for reading `BindingResult` data accurately and diagnosing Spring MVC errors.

## 2. Classes and Interfaces in the Error Model

### 2.1. Errors and BindingResult

`Errors` is the contract for querying and recording errors:

| Component | Representative API | Meaning |
| --- | --- | --- |
| Identity | `getObjectName()` | Logical name of the object being validated |
| Any errors | `hasErrors()`, `getErrorCount()` | Overview of error status |
| Object-level errors | `reject(...)`, `getGlobalErrors()` | Errors not attached to a single field |
| Field-level errors | `rejectValue(...)`, `getFieldErrors()` | Errors attached to a property path |
| Querying one field | `getFieldError("age")`, `hasFieldErrors("age")` | Look up errors for a specific field |
| Value/type | `getFieldValue("age")`, `getFieldType("age")` | Value possibly holding rejected input; type of the field |
| Nested paths | `getNestedPath()`, `pushNestedPath(...)`, `popNestedPath()` | Helps validators work across object graphs |

`BindingResult extends Errors`, adding:

| API | Role |
| --- | --- |
| `getTarget()` | Retrieves the bound target object; may be `null` in certain constructor-binding paths before instantiation |
| `getModel()` | Generates a two-entry map for the object and binding result to put into the view model |
| `MODEL_KEY_PREFIX` | Standard model key prefix used for `BindingResult` |
| `getSuppressedFields()` | List of field names blocked from binding |
| `getRawFieldValue("field")` | Retrieves raw value from the target under the active binding strategy |
| `resolveMessageCodes(...)` | Generates candidate error codes for message lookup |
| `getPropertyEditorRegistry()`, `findEditor(...)` | Accesses editor metadata if supported by the implementation |
| `addError(ObjectError)` | Appends an error created by collaborating strategies |

Most applications use APIs at the `Errors`/`BindingResult` level without depending directly on implementation classes.

Common implementations are `BeanPropertyBindingResult` for JavaBeans properties (getters/setters), `DirectFieldBindingResult` for direct field access, and `MapBindingResult` for map targets. `DataBinder.getBindingResult()` returns the result matching how the binder was configured. Do not create a fresh `BindingResult` unrelated to the binder and expect it to automatically hold the request's binding errors.

### 2.2. ObjectError and FieldError

`ObjectError` represents an error across the **entire object**; for example, start time cannot exceed end time, or password and confirmation password do not match. It provides:

- `getObjectName()`: the object holding the error.
- `getCode()` and `getCodes()`: base/prioritized codes for message lookup (check exact Javadoc for your version).
- `getArguments()` and `getDefaultMessage()`: arguments and fallback message.
- The `MessageSourceResolvable` contract so `MessageSource` can select a localized message.

`FieldError extends ObjectError`, so it retains object name, message codes, and default message while adding:

- `getField()`: field path such as `age`, `address.city`, or `items[0].price`.
- `getRejectedValue()`: the rejected value, often needed to re-render the input.
- `isBindingFailure()`: `true` when the error is considered a **binding failure**, such as a type-conversion failure; `false` for validation errors recorded via `rejectValue`.

Example with object name `registrationForm`:

~~~text
ObjectError
  objectName = registrationForm
  code       = registration.invalid
  field      = (no field)

FieldError
  objectName     = registrationForm
  field          = age
  rejectedValue  = abc
  bindingFailure = true
  code           = typeMismatch
~~~

`getAllErrors()` includes both global and field errors; `getGlobalErrors()` includes only global errors; `getFieldErrors()` includes only field errors. A field can have multiple errors, so `getFieldError("age")` returns only the **first error**; use `getFieldErrors("age")` when you need to handle all of them.

**Distinguish the three names:** `objectName` tells *which object*, `field` tells *which property*, and `errorCode` tells *which kind of error*. Never use them interchangeably.

## 3. How Is Object Name Determined?

### 3.1. With standalone DataBinder

You can specify the name explicitly in the constructor:

~~~java
RegistrationForm form = new RegistrationForm();
DataBinder binder = new DataBinder(form, "registrationForm");
BindingResult result = binder.getBindingResult();

System.out.println(result.getObjectName()); // registrationForm
~~~

This snippet illustrates code in a program with `DataBinder`, `BindingResult`, and `RegistrationForm` imported. The target object is `form`, while the logical binding name is `"registrationForm"`. This name does not have to match the class name (`RegistrationForm`) or the Java variable name (`form`).

If you call `new DataBinder(form)` without a name, `DataBinder.DEFAULT_OBJECT_NAME` defaults to `"target"`. Therefore, never assume every `DataBinder` automatically infers `registrationForm` from the Java class.

### 3.2. With @ModelAttribute in Spring MVC

Example controller signature:

~~~java
@PostMapping("/register")
public String register(
        @Valid @ModelAttribute("registrationForm") RegistrationForm form,
        BindingResult bindingResult) {
    if (bindingResult.hasErrors()) {
        return "registration/form";
    }
    return "redirect:/registered";
}
~~~

This is an integration snippet inside a Spring MVC `@Controller`, not a standalone Java file. `@ModelAttribute("registrationForm")` sets the model attribute name to **registrationForm**, and `bindingResult.getObjectName()` for the corresponding object uses that same name.

If no name is specified:

~~~java
public String register(@ModelAttribute RegistrationForm form,
                       BindingResult bindingResult) {
    // ...
}
~~~

Spring MVC applies conventions to derive the model attribute name from the parameter type/metadata; for a normal class like `RegistrationForm`, the name is typically `registrationForm`. It is best to **specify the name explicitly** when form views or contract code depend on a fixed name, rather than relying on default name inference in every case.

Key verification points:

- `@ModelAttribute("registrationForm")` is the **object's name**; `@ModelAttribute("name")` would refer to a different attribute name, not the `name` field inside `registrationForm`.
- The string in `getObjectName()` corresponds to the model attribute name used by the view.
- Declare `BindingResult` **immediately after** the `@ModelAttribute` parameter being handled. A `BindingResult` placed after another parameter may no longer be associated by MVC with the intended object.
- If two form DTOs exist in the same controller/model, use **two distinct model attribute names** so errors and input fields do not collide.
- Renaming `"registrationForm"` requires updating templates, error lookup keys, and any handlers accessing the model by that name.

### 3.3. Does the object name change when validating nested fields?

No. For `registrationForm.address.city`:

- `getObjectName()` remains `"registrationForm"`.
- `FieldError.getField()` is `"address.city"` when the error is on this field.
- `getNestedPath()` may be `"address."` while a validator is inside a nested-path context, yet it does not change the object name.
- Message codes can combine both the object name and the full field path.

Thanks to this separation, a single `BindingResult` can collect errors across multiple levels of an object graph while keeping a stable object identifier.

## 4. Two Model Keys Provided by BindingResult.getModel()

### 4.1. Exact naming formula

`BindingResult.MODEL_KEY_PREFIX` has the value:

~~~text
org.springframework.validation.BindingResult.
~~~

For `objectName = "registrationForm"`, `bindingResult.getModel()` returns a `Map<String, Object>` with two main entries:

| Model key | Value |
| --- | --- |
| `registrationForm` | Target `RegistrationForm` |
| `org.springframework.validation.BindingResult.registrationForm` | The `BindingResult` instance itself |

Formula:

~~~java
String objectName = result.getObjectName();
String bindingKey = BindingResult.MODEL_KEY_PREFIX + objectName;
Map<String, Object> attrs = result.getModel();

Object target = attrs.get(objectName);
BindingResult errors = (BindingResult) attrs.get(bindingKey);
~~~

This example applies to an already-created `BindingResult`; replace `result` with the actual variable in your method.

Do not use `"BindingResult.registrationForm"`, `"bindingResult"`, or the target's class name arbitrarily for lookup. Only the standard prefix combined with the **actual object name** is the binding result's model key.

For two distinct objects:

~~~text
profileForm
org.springframework.validation.BindingResult.profileForm

shippingForm
org.springframework.validation.BindingResult.shippingForm
~~~

Each key pair refers to a separate target/binding-result. Accidentally reusing the same object name can overwrite map entries and cause templates/handlers to display the wrong errors.

### 4.2. getModel() creates a new map on every call

The Javadoc specifies that `getModel()` creates a new map **on each invocation**. Therefore:

~~~java
Map<String, Object> first = result.getModel();
first.put("additionalAttribute", "value");

Map<String, Object> second = result.getModel();
System.out.println(second.containsKey("additionalAttribute")); // false
~~~

Adding entries to the returned map mutates only **that map**; it does not alter `BindingResult` state and will not appear in the map returned by subsequent calls.

When assembling a `ModelAndView` manually, if both target and errors must reach the view, add these entries to the active model. Conceptual logic:

~~~java
modelAndView.addAllObjects(bindingResult.getModel());
~~~

Here `modelAndView` is an already-instantiated `ModelAndView`. In typical annotation-based controllers, Spring MVC manages linking model attributes and `BindingResult`; there is no need to call `getModel()` manually on every view return. Manually adding an error under the wrong key name can prevent the view from finding the needed details.

### 4.3. Do not confuse Model with BindingResult

- `Model` or `ModelMap` belongs to Spring MVC: the collection of attributes for the view.
- `BindingResult`: error and binding details for **one target**.
- `bindingResult.getModel()`: a way to **package two related entries** so they can be added to a model.
- Each `BindingResult` has its own object name; one MVC `Model` can hold multiple objects and multiple `BindingResult` instances.

In other words, `BindingResult` can produce part of a model, but it does not replace the request's `Model`.

## 5. Standalone Runnable Example: Observing the Data Model

This example uses **Java 17+** and Spring Framework **6.2.12** via Gradle. It needs no Spring Boot, HTTP server, or Jakarta Bean Validation provider. Validation is performed explicitly via `rejectValue`/`reject` so you can clearly see the differences among type-mismatch errors, business errors, and suppressed fields. The commands below suit a machine with JDK 17+ and Gradle installed.

Create `settings.gradle`:

~~~groovy
rootProject.name = 'binding-result-model-demo'
~~~

Create `build.gradle`:

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
    mainClass = 'BindingResultModelDemo'
}
~~~

Create `src/main/java/BindingResultModelDemo.java`:

~~~java
import java.util.Arrays;
import java.util.Map;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.FieldError;

public class BindingResultModelDemo {

    public static class RegistrationForm {
        private String name;
        private Integer age;
        private String role;

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public Integer getAge() {
            return age;
        }

        public void setAge(Integer age) {
            this.age = age;
        }

        public String getRole() {
            return role;
        }

        public void setRole(String role) {
            this.role = role;
        }
    }

    public static void main(String[] args) {
        RegistrationForm form = new RegistrationForm();

        DataBinder binder = new DataBinder(form, "registrationForm");
        binder.setAllowedFields("name", "age");

        MutablePropertyValues input = new MutablePropertyValues();
        input.add("name", "");
        input.add("age", "abc");
        input.add("role", "ADMIN");

        binder.bind(input);
        BindingResult result = binder.getBindingResult();

        result.rejectValue("name", "required", null,
                "Name must not be blank");
        result.reject("registration.invalid", null,
                "Form is invalid");

        String key = BindingResult.MODEL_KEY_PREFIX
                + result.getObjectName();
        Map<String, Object> model = result.getModel();

        FieldError ageError = result.getFieldError("age");
        FieldError nameError = result.getFieldError("name");

        System.out.println("objectName=" + result.getObjectName());
        System.out.println("targetSame=" + (result.getTarget() == form));
        System.out.println("bindingKey=" + key);
        System.out.println("modelTarget=" + (model.get("registrationForm") == form));
        System.out.println("modelErrors=" + (model.get(key) == result));
        System.out.println("freshMap=" + (result.getModel() != model));

        System.out.println("fieldErrors=" + result.getFieldErrorCount());
        System.out.println("globalErrors=" + result.getGlobalErrorCount());
        System.out.println("allErrors=" + result.getErrorCount());
        System.out.println("ageField=" + ageError.getField());
        System.out.println("ageRejected=" + ageError.getRejectedValue());
        System.out.println("ageFieldValue=" + result.getFieldValue("age"));
        System.out.println("ageBindingFailure=" + ageError.isBindingFailure());
        System.out.println("nameBindingFailure=" + nameError.isBindingFailure());
        System.out.println("suppressed=" +
                Arrays.toString(result.getSuppressedFields()));
        System.out.println("ageOnTarget=" + form.getAge());
        System.out.println("roleOnTarget=" + form.getRole());
    }
}
~~~

Run with:

~~~bash
gradle -q run
~~~

If the project has a Gradle Wrapper, use `./gradlew -q run` on Linux/macOS or `gradlew.bat -q run` on Windows. The command downloads Spring Context and required dependencies from Maven Central when network access is available.

**Expected stdout** with the exact dependencies and inputs above:

~~~text
objectName=registrationForm
targetSame=true
bindingKey=org.springframework.validation.BindingResult.registrationForm
modelTarget=true
modelErrors=true
freshMap=true
fieldErrors=2
globalErrors=1
allErrors=3
ageField=age
ageRejected=abc
ageFieldValue=abc
ageBindingFailure=true
nameBindingFailure=false
suppressed=[role]
ageOnTarget=null
roleOnTarget=null
~~~

How to read each group of results:

1. `objectName=registrationForm` because the `DataBinder` constructor received that name; `targetSame=true` confirms the binder is attached to the same `form` object.
2. `bindingKey` equals `BindingResult.MODEL_KEY_PREFIX + objectName`. Both `modelTarget=true` and `modelErrors=true` confirm the map references the existing object and result.
3. `freshMap=true` does not mean the target or errors were copied. Only the **Map object itself** is a new instance on each `getModel()` call.
4. `fieldErrors=2` comprises the type mismatch on `age` and the `required` error added for `name`; `globalErrors=1` is the object-wide error added via `reject`. `allErrors=3` is the sum.
5. `ageRejected=abc`, `ageFieldValue=abc` show that the rejected input remains accessible for re-display. Meanwhile, `ageOnTarget=null` because conversion to `Integer` failed.
6. `ageBindingFailure=true` distinguishes the type-conversion error from `nameBindingFailure=false`: the `name` error was added by the application via validation-style `rejectValue`.
7. `role` is not in the `setAllowedFields` allowlist, so it appears in `suppressed=[role]`; the target keeps `role=null`. **A suppressed field does not automatically become a FieldError**.

The example does not use `@Valid` or constraint annotations; the goal is to explore `BindingResult` itself. In real applications, validators or a Jakarta Bean Validation provider can add other errors following the same model. If you change the inputs or configuration in the example, stdout can change; do not treat this as a fixed law for every binder.

## 6. Object Values vs. Invalid User Input

A common mistake is reading only fields on the target and ignoring values stored inside errors.

Suppose property `age` is `Integer`, yet the request submits `age=abc`. After binding fails:

~~~text
form.getAge()                    → null
result.getFieldError("age")      → FieldError exists
error.getRejectedValue()        → "abc"
result.getFieldValue("age")      → "abc" (per the example BindingResult)
error.isBindingFailure()        → true
~~~

If the controller returns the form view after an error, rendering only `form.age` will not accurately reflect what the user just entered. The view's binding mechanism can use the rejected value in `BindingResult` to preserve the entered input and let the user correct it.

Different ways to read:

| Need | API | What to know |
| --- | --- | --- |
| Value already on the object | `getTarget()` then access field | May remain unassigned if conversion failed |
| Field value for binding/forms | `getFieldValue("age")` | May return rejected value, not necessarily target Java type |
| Specific error's value | `getFieldError("age").getRejectedValue()` | Requires null-check if field has no error |
| Declared type | `getFieldType("age")` | Can infer type even when target value is null |
| Raw value from target | `getRawFieldValue("age")` | Implementation-dependent; do not substitute for rejected input |
| Error list on a field | `getFieldErrors("age")` | Can hold multiple errors for one field |

Never assign the rejected value back into the target just to "preserve the form"; doing so breaks type constraints. Pass errors and appropriate values to the view through Spring's APIs. When writing logs or API error responses, mask sensitive data such as passwords, tokens, and personal details instead of printing `getRejectedValue()` verbatim.

## 7. Object Name, Field Path, and Message Codes

### 7.1. One error code is not one message line

`rejectValue("age", "typeMismatch", ...)` (or an automatically generated conversion error) supplies a **logical error code**. Spring can expand it into more specific codes via `MessageCodesResolver`.

For example, with:

~~~text
objectName = registrationForm
field      = age
fieldType  = java.lang.Integer
errorCode  = typeMismatch
~~~

`DefaultMessageCodesResolver` usually builds candidate codes ordered from specific to general:

~~~text
typeMismatch.registrationForm.age
typeMismatch.age
typeMismatch.java.lang.Integer
typeMismatch
~~~

In practice, the list depends on the configured `MessageCodesResolver`, the field type Spring determines, and whether the property is a list/map/nested property. For primitive `int`, the type segment can be `int`. Do not assume every system always produces the exact four strings in this example.

An `ObjectError` with code `registration.invalid` and object name `registrationForm` can have candidate codes:

~~~text
registration.invalid.registrationForm
registration.invalid
~~~

This structure lets you pick messages at each level:

- Specific to one field on one form: `typeMismatch.registrationForm.age`.
- General to a field regardless of form: `typeMismatch.age`.
- General to a data type: `typeMismatch.java.lang.Integer`.
- General fallback across all forms: `typeMismatch`.

### 7.2. MessageSource picks the message

Example `messages_vi.properties` file in an application with a matching `MessageSource` configuration:

~~~properties
typeMismatch.registrationForm.age=Tuổi phải là một số nguyên.
typeMismatch.age=Giá trị tuổi không hợp lệ.
required.registrationForm.name=Vui lòng nhập tên.
registration.invalid.registrationForm=Thông tin đăng ký chưa phù hợp.
~~~

`MessageSource` tries the codes to fetch a message for the `Locale`, applying arguments and fallbacks as needed. `getDefaultMessage()` is a fallback value, not proof that Spring located and applied the proper display language. To resolve an error manually in the backend:

~~~java
String message = messageSource.getMessage(error, locale);
~~~

This snippet assumes `MessageSource messageSource`, `ObjectError error`, and `Locale locale` are available. `ObjectError` implements `MessageSourceResolvable`. The final message also depends on message-bundle configuration.

When renaming `objectName` from `registrationForm` to `signupForm`, the most specific code also changes to `typeMismatch.signupForm.age`; i18n files or test assertions relying on the old name may stop matching. That is a major reason to treat the object name as part of the contract between controller and view.

### 7.3. Nested fields and collection indices

For DTOs with nested properties:

~~~text
registrationForm.address.city
registrationForm.contacts[0].email
registrationForm.items[2].quantity
~~~

Field errors usually store names relative to the root object, such as `address.city` or `items[2].quantity`, while the object name remains `registrationForm`. `Errors` provides nested-path APIs for validators operating on child fields. When generating error codes, `DefaultMessageCodesResolver` can produce both index-specific codes and more general codes for the collection.

Example:

~~~text
typeMismatch.registrationForm.items[2].quantity
typeMismatch.registrationForm.items.quantity
typeMismatch.items[2].quantity
typeMismatch.items.quantity
typeMismatch.quantity
...
typeMismatch
~~~

The `...` represents intermediate codes depending on field type and resolver configuration, not an actual error code. To know for sure, inspect `fieldError.getCodes()` on your active framework version/configuration.

Another concern is uninitialized nested properties. The binder can be configured to auto-grow nested paths in supported cases, or it can raise property-access errors. Do not assume every nested path submitted by a user is valid or binds successfully. DTOs and allowlists must restrict which fields are accepted from outside.

## 8. BindingResult in the Spring MVC Lifecycle

### 8.1. Processing chain when receiving a form

For a controller with `@ModelAttribute("registrationForm")`:

~~~text
HTTP form/query parameters
       |
       v
Spring MVC argument resolver
       |
       v
Find or create model attribute "registrationForm"
       |
       v
WebDataBinder converts types and assigns properties
       |
       +--> binding error: FieldError (e.g., typeMismatch)
       |
       v
Validator / Jakarta Bean Validation when triggered
       |
       +--> field error: FieldError
       +--> object-wide error: ObjectError
       |
       v
BindingResult attached to registrationForm
       |
       +--> Controller reads via adjacent BindingResult parameter
       |
       +--> View model has registrationForm and BindingResult.registrationForm
       |
       v
Re-render form on error, or proceed with business logic
~~~

Each normal request/binding pass has its own binder and result. `BindingResult` must never be stored as a mutable field on a singleton controller, because error data belongs to a **specific request and target**.

### 8.2. A controller returning an HTML form

Integration example in Spring MVC 6.x/7.x with a Jakarta Validation provider; these files belong to the same package `com.example.registration`. They are components of a **web application that already has Spring MVC and a view engine**, not a standalone program with `main`.

File `RegistrationForm.java`:

~~~java
package com.example.registration;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class RegistrationForm {

    @NotBlank
    private String name;

    @NotNull
    @Min(18)
    private Integer age;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }
}
~~~

File `RegistrationController.java`:

~~~java
package com.example.registration;

import jakarta.validation.Valid;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;

@Controller
public class RegistrationController {

    @GetMapping("/registrations/new")
    public String newForm(Model model) {
        model.addAttribute("registrationForm", new RegistrationForm());
        return "registration/form";
    }

    @PostMapping("/registrations")
    public String submit(
            @Valid @ModelAttribute("registrationForm") RegistrationForm form,
            BindingResult result) {

        if (result.hasErrors()) {
            return "registration/form";
        }

        return "redirect:/registrations/success";
    }
}
~~~

For the form to work, configure a suitable view engine (e.g., Thymeleaf) and provide a `/registrations/success` route if you want the redirect to succeed. `@Valid` requires the Jakarta Bean Validation API plus a configured provider; adding the annotation alone without a provider may not enforce constraints as expected.

A matching Thymeleaf template snippet (e.g., `templates/registration/form.html`) illustrates object naming and error rendering:

~~~html
<form method="post" th:action="@{/registrations}"
      th:object="${registrationForm}">
    <label>Name
        <input type="text" th:field="*{name}">
    </label>
    <p th:if="${#fields.hasErrors('name')}" th:errors="*{name}"></p>

    <label>Age
        <input type="text" th:field="*{age}">
    </label>
    <p th:if="${#fields.hasErrors('age')}" th:errors="*{age}"></p>
    <button type="submit">Submit</button>
</form>
~~~

The template is **an integrated HTML fragment**, not a full HTML document. In Spring Security setups with CSRF enabled, ensure the form includes a CSRF token via the enabled integration. In this template, `th:object="${registrationForm}"` points to the model attribute name; `*{age}` points to the target's field. The `BindingResult` for that exact model attribute allows field expressions to locate matching values and errors.

When submitting `name=` and `age=abc`:

- `name` is an empty string: `@NotBlank` can produce an error on `name`.
- `age=abc`: conversion to `Integer` fails and produces a `typeMismatch` error on `age`.
- Without special configuration, MVC returns the view after the controller checks `result.hasErrors()`.
- Both form and error state stay tied to `registrationForm` so the view displays errors and entered values.

This example **declares no extra constraints directly on method parameters** beyond `@Valid` on the DTO, keeping the focus on `BindingResult` next to `@ModelAttribute`. In signatures using method validation, exception generation can follow another branch; see the common mistakes section below.

### 8.3. BindingResult must immediately follow the related parameter

Correct:

~~~java
public String submit(
        @Valid @ModelAttribute("registrationForm") RegistrationForm form,
        BindingResult result,
        Model model) {
    // result corresponds to registrationForm
    return "registration/form";
}
~~~

Incorrect adjacency:

~~~java
public String submit(
        @Valid @ModelAttribute("registrationForm") RegistrationForm form,
        Model model,
        BindingResult result) {
    // MVC cannot automatically associate result with form at this position
    return "registration/form";
}
~~~

Both snippets above are **illustrative signatures**, placed in a controller with full imports and handler annotations. The `Errors`/`BindingResult` parameter must sit immediately after **the corresponding model attribute or supported argument**. Never place a single `BindingResult` at the end of a method hoping to gather errors from all parameters.

To validate two objects together, understand how method argument resolution and per-argument validation work; never attempt to merge errors from two distinct DTOs into one `BindingResult`.

## 9. Binding Errors, Validation Errors, and Suppressed Fields

All three involve unwanted input, yet **they differ in data representation and handling**.

| Scenario | Typical representation | How to inspect |
| --- | --- | --- |
| `age=abc` when target is `Integer` | `FieldError`, code `typeMismatch`, `bindingFailure=true` | `getFieldError("age")` and `isBindingFailure()` |
| `age=15` with `@Min(18)` constraint | Validation `FieldError`, usually `bindingFailure=false` | `getFieldErrors("age")`, constraint code |
| `name=` with `@NotBlank` | Validation `FieldError` | `getFieldErrors("name")` |
| Two conflicting properties | `ObjectError` / global error | `getGlobalErrors()` |
| `role=ADMIN` with `setAllowedFields("name","age")` | Suppressed field, normally creates no `FieldError` | `getSuppressedFields()` |
| Form failed to instantiate via constructor binding | May lack instantiated target; errors/field values still recorded | `getTarget()` may be null, inspect errors |

**Conversion and validation are distinct phases.** A value that cannot even convert to `Integer` is not ready for `@Min(18)` checking; do not treat `typeMismatch` as the same error kind as `Min`.

Regarding suppressed fields, this is a property-binding restriction mechanism. If your application treats a request carrying forbidden fields as a business/security violation, handle or audit it under a dedicated policy. `BindingResult.getSuppressedFields()` is a useful signal, though by itself it neither returns HTTP 400 nor generates a validation message.

## 10. Reading Errors Properly in Application Code

### 10.1. Query APIs have distinct meanings

~~~java
boolean anyError = result.hasErrors();
boolean anyFieldError = result.hasFieldErrors();
boolean ageHasError = result.hasFieldErrors("age");

int allCount = result.getErrorCount();
int globalCount = result.getGlobalErrorCount();
int fieldCount = result.getFieldErrorCount();

List<ObjectError> global = result.getGlobalErrors();
List<FieldError> ageErrors = result.getFieldErrors("age");
~~~

This is an illustrative snippet with `BindingResult result` and imports for `java.util.List`, `ObjectError`, and `FieldError`. Use the method matching your exact need. `hasErrors()` can be `true` solely because of a global error, even when `getFieldError("age")` returns `null`.

When building UI messages, check for null:

~~~java
FieldError ageError = result.getFieldError("age");
if (ageError != null) {
    String field = ageError.getField();
    Object rejectedValue = ageError.getRejectedValue();
    // Pass safe field/code/message to the view.
}
~~~

`getRejectedValue()` is an `Object` and can be `null`; it may also contain personal data or unsafe input. Never cast it directly to `Integer` when parsing failed. Leave HTML escaping to the template engine; never inject raw strings into HTML or logs.

### 10.2. Handling multiple errors on the same field

For example, a `password` field that is both too short and missing a digit may receive errors from multiple validators depending on setup. In that case:

- `result.getFieldError("password")` returns only the **first** error.
- `result.getFieldErrors("password")` returns all errors for that field.
- `result.getFieldErrorCount("password")` is the count of field errors for it.
- `getDefaultMessage()` may be absent, or serve only as a fallback.
- `getCodes()` lets the resolver find localized messages in priority order.

Do not read only the first error and declare the rest of the request valid. For JSON APIs, construct a stable error structure with `field`, public code, and resolved message; avoid dumping internal error-object details mechanically.

### 10.3. Creating field errors and object errors

When validating with a standalone Spring `Validator`:

~~~java
@Override
public void validate(Object target, Errors errors) {
    RegistrationForm form = (RegistrationForm) target;

    if (form.getName() == null || form.getName().isBlank()) {
        errors.rejectValue("name", "required", null,
                "Name must not be blank");
    }

    if (form.getAge() != null && form.getAge() < 18) {
        errors.rejectValue("age", "tooYoung", null,
                "Age must be at least 18");
    }

    // If an object-wide error is needed:
    // errors.reject("registration.invalid", null, "Form is invalid");
}
~~~

This is **a method inside a class implementing `org.springframework.validation.Validator`**; the code assumes `RegistrationForm` from the earlier example and an implemented `supports(Class<?>)` method. The two `rejectValue` calls record field errors, whereas `reject` records a global error. Do not equate Spring's `Validator` with `jakarta.validation.Validator`: they are two separate APIs in different packages.

For an object containing nested fields, avoid accidentally prepending the object name inside `rejectValue`. Normally pass a relative path like `"address.city"`, and let `Errors`/resolvers combine it with the object name.

## 11. When Can an Object Have No Target?

With property-setter binding, the target is usually already instantiated. However, with **constructor binding**, the binder may have to construct the target from input values. If the constructor cannot instantiate the object due to argument errors, `BindingResult.getTarget()` may be `null`, while error details and recorded field values are still retained for diagnostics.

This has two consequences:

1. Never write error-handling code assuming `result.getTarget()` always returns a non-null instance in every scenario.
2. When you only need to return error messages, prefer `BindingResult`, `FieldError`, and recorded field values rather than calling getters on a target that may not exist.

`BindingResult.recordFieldValue(...)` supports constructor-binding strategies in recording values when the target could not be constructed; this is typically an internal binder API, not a method controllers call in normal flows.

Across Spring versions, constructor binding and target creation have subtle differences; check Javadoc and test on your application's Spring version, especially during major/minor upgrades. What remains invariant is that **object name and error state do not depend on the controller always having a complete target**.

## 12. Error Handling in Spring MVC Is Not Only BindingResult

`BindingResult` is the binding/validation error model for an argument, yet Spring MVC has multiple input paths:

- `@ModelAttribute` receives form/query parameters through the binder. Placing `BindingResult` right after the parameter lets the controller read supported errors in this flow.
- `@RequestBody` is typically read by an HTTP message converter (such as Jackson JSON). Unparseable JSON can throw an error **before** any object or `BindingResult` exists in the form style.
- `@Valid @RequestBody` can raise `MethodArgumentNotValidException` when argument-level validation fails without a matching `Errors`/`BindingResult`.
- For constraints directly on controller method parameters (such as `@RequestParam @Min(1) int page`), Spring MVC 6.1+ provides **built-in method validation** and can throw `HandlerMethodValidationException`.
- `@Validated` on a controller class can route method validation through AOP instead of the integrated MVC path. Do not assume a single exception class covers all errors.
- `BindingResult` is not an automatic HTTP response. Status/body on error also depend on argument resolvers, exception handlers, and how the controller builds responses.

If your goal is re-rendering an HTML form, `BindingResult` adjacent to `@ModelAttribute` fits well. If your goal is a JSON REST API, identify whether failures occur during **JSON parsing**, **data binding**, **Bean Validation**, or **method validation**, and handle each properly in `@ControllerAdvice` or an equivalent mechanism.

## 13. Two Forms with the Same Name and Template Issues

Suppose a checkout page has two objects:

~~~text
billingForm
shippingForm
~~~

Conceptually, the correct model is:

~~~text
billingForm                                  → BillingForm
org.springframework.validation.BindingResult.billingForm
                                             → BindingResult for BillingForm

shippingForm                                 → ShippingForm
org.springframework.validation.BindingResult.shippingForm
                                             → BindingResult for ShippingForm
~~~

If the controller renames both to `@ModelAttribute("form")`, keys with the same name collide in the model. When a form displays the wrong errors, check in order:

1. Under what name did the controller add the object to the model?
2. What is `result.getObjectName()` in the corresponding handler?
3. Which object does the template's `th:object`/JSP `modelAttribute` point to?
4. Is the key `BindingResult.MODEL_KEY_PREFIX + objectName` preserved in the model?
5. Does any code construct a `ModelAndView` or overwrite the model attribute with a new object after binding?
6. Are you reading the result adjacent to the right argument?

A common bug is creating `new RegistrationForm()` and calling `model.addAttribute("registrationForm", ...)` **again** inside the error branch, replacing the target containing what the user just submitted. That causes the view to lose submitted inputs. In normal error branches, return the form view with the existing target/binding result; replace the object only for an explicit, deliberate reason.

## 14. Testing the Data Model Instead of Just the UI

Tests should cover both raw data and model keys.

| Case | Input/action | Expected verification |
| --- | --- | --- |
| Object identity | `new DataBinder(form, "registrationForm")` | `getObjectName()` is `registrationForm` |
| Unnamed default | `new DataBinder(form)` | `getObjectName()` is `target` |
| Model key pair | `getModel()` | Target at `objectName` key and `BindingResult` at prefix + `objectName` |
| Repeated map reads | Call `getModel()` twice | Distinct Map instances; same target/result |
| Successful binding | `age=21` | Target `age=21`, no type mismatch |
| Failed binding | `age=abc` | Field error, rejected value, `bindingFailure=true` |
| Validation | `name=` then `rejectValue`/`@NotBlank` | `FieldError` with `bindingFailure=false` in the right flow |
| Global error | `reject(...)` | `hasGlobalErrors()` is true |
| Suppressed field | `setAllowedFields("name","age")` and input `role` | `getSuppressedFields()` has `role`, target unassigned |
| Nested field | `address.city` | `getObjectName()` unchanged; field path describes child property |
| MVC form | `@ModelAttribute("registrationForm")` + adjacent `BindingResult` | Controller reads right target's errors; view shows errors on right form |
| Renamed form | `registrationForm` → `signupForm` | Views and i18n keys use the new name |
| Sensitive input | Rejected password/token | Raw value omitted from public logs/responses |

In the standalone demo above, you can replace `input.add("age","abc")` with `input.add("age","21")` and **re-run** to observe how `ageOnTarget`, `ageRejected`, and `getFieldError("age")` change. Before doing that experiment, update the code referencing `ageError`, because it will be `null` once no error exists; this also verifies `getFieldError` semantics in real apps.

In MVC integration tests, use MockMvc or real requests to verify model keys, `BindingResult`, and rendered views. Tests should note the Spring/Jakarta Validation provider version. Do not rely solely on a Vietnamese error string: i18n messages can change while the underlying error data remains valid.

## 15. Common Mistakes and Fixes

**Mistake 1: "Errors are missing in the view even though controller reports `hasErrors()=true`."** Check `BindingResult`'s object name, the controller's model attribute name, and `th:object` in the template. The model key must be `BindingResult.MODEL_KEY_PREFIX + objectName`.

**Mistake 2: "The model has the form object but no BindingResult."** If building `ModelAndView`/model outside MVC's automatic flow, put both entries from `getModel()` into the model. If MVC already handles `@ModelAttribute`, check whether code accidentally overwrites those entries.

**Mistake 3: "I added a field to `result.getModel()` and it vanished."** Every `getModel()` call returns a fresh map. Update the view's active map via `Model.addAttribute(...)` or retain and merge the created map properly.

**Mistake 4: "`getFieldError("age")` is present yet `form.getAge()` is null."** With `age=abc`, this is expected: conversion failed, and the rejected input is preserved in `FieldError`. Use the field error/value to render messages.

**Mistake 5: "There are blocked fields yet `hasErrors()` is false."** `getSuppressedFields()` is independent of `FieldError`; allowlist suppression does not automatically create validation errors.

**Mistake 6: "Reading `getFieldError()` missed other errors."** This method returns only the first field error; use `getFieldErrors()` or `getAllErrors()` for the full list. Also check `getGlobalErrors()` for form-wide errors.

**Mistake 7: "`getRejectedValue()` is always a String."** Incorrect. Its return type is `Object`, and it can be another type or `null`. Never cast blindly; handle by input type and protect sensitive data.

**Mistake 8: "Placing `BindingResult` at the end of the controller signature works fine."** Incorrect in standard `@ModelAttribute` binding flows; this parameter must immediately follow the related argument.

**Mistake 9: "Seeing `@Valid` guarantees errors appear in BindingResult."** A suitable validator/provider and controller handling path are required. If constraints sit directly on method parameters or JSON parsing fails, a different path applies.

**Mistake 10: "The Java class name dictates every error key."** With MVC `@ModelAttribute("customName")` or `DataBinder(target,"customName")`, the object name is **explicitly assigned**. Never concatenate class names to guess error keys.

**Mistake 11: "Global errors and field errors are the same thing."** An object-level rule usually uses `reject` and becomes an `ObjectError`; a field-level rule uses `rejectValue` and becomes a `FieldError`. The UI must render both appropriately.

**Mistake 12: "Printing the raw rejected value for debugging is always safe."** No. Rejected values come from untrusted input and may contain sensitive data, HTML, or control characters. Never emit them raw into logs, error JSON, or unescaped HTML.

## 16. Knowledge Self-Check

1. With `new DataBinder(form, "customerForm")`, what does `getObjectName()` return? **customerForm**; it does not have to be the class name.
2. What key does `BindingResult.MODEL_KEY_PREFIX + "customerForm"` produce? **`org.springframework.validation.BindingResult.customerForm`**.
3. What does `getModel()` contain? **The target under `objectName` and the `BindingResult` under prefix + `objectName`**, returned in a fresh map on each call.
4. Does `getAllErrors()` include `FieldError` instances? **Yes**, because it combines global and field errors.
5. Does `getFieldErrors()` contain a purely global `ObjectError`? **No**.
6. If `age=abc` fails to convert to `Integer`, does `getTarget()` always hold age `"abc"`? **No**; age may remain unassigned while the rejected value is stored in the error.
7. Does a field suppressed by `allowedFields` automatically make `hasErrors()` true? **No**.
8. How do `FieldError.getObjectName()` and `FieldError.getField()` differ? **Root object name** vs. **property path**.
9. Why must `BindingResult` be placed immediately after `@ModelAttribute`? So MVC attaches errors to the right bound argument.
10. If a template changes `th:object` from `customerForm` to `orderForm`, what must be checked? Model attribute, binding-result key, object name, i18n messages, and the corresponding controller.

## 17. Primary Reference Documentation

- [Spring Framework – BindingResult Javadoc (6.2.x)](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring Framework – Errors Javadoc (6.2.x)](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/Errors.html)
- [Spring Framework – ObjectError Javadoc (6.2.x)](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/ObjectError.html)
- [Spring Framework – FieldError Javadoc (6.2.x)](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/FieldError.html)
- [Spring Framework – DataBinder Javadoc (6.2.x)](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework – DefaultMessageCodesResolver Javadoc (6.2.x)](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/DefaultMessageCodesResolver.html)
- [Spring Framework – Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html)
- [Spring Framework – Resolving Error Codes to Error Messages](https://docs.spring.io/spring-framework/reference/core/validation/error-code-resolution.html)
- [Spring MVC – ModelAttribute](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring MVC – Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)

**Guiding principle:** always know **which object name** a `BindingResult` represents, distinguish **global** vs. **field** errors, read **rejected values / error codes** properly, and preserve the **model key pair** when rendering forms. This is the foundation for debugging binding/validation without losing user input or attaching errors to the wrong object.
