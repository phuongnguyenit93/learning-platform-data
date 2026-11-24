# Checkboxes, Field Markers, and Field Defaults of WebDataBinder in Spring MVC

## 1. Why do checkboxes need special handling?

In HTML, a **checked** checkbox typically produces a parameter pair on form submission, e.g., `subscribed=true`. An **unchecked** checkbox typically **produces no `subscribed` parameter at all**. This is standard HTML form behavior, but it creates a problem when Spring MVC uses a form to **edit an object that already holds data**.

Suppose an “Email notification settings” page displays `subscribed=true`, and the user unchecks the box. The request contains no `subscribed` parameter. If binding only updates properties whose names appear in the request, the old object still keeps `subscribed=true`: the uncheck action was not saved.

**`org.springframework.web.bind.WebDataBinder`** has two conventions to solve this:

- **Field marker**: a parameter name starting with an underscore, defaulting to `_fieldName`. It signals that the field was present on the form even if no actual value was submitted. If the original `fieldName` parameter is missing, the binder **resets the field to an empty value appropriate for its type**.
- **Field default**: a parameter name starting with an exclamation mark, defaulting to `!fieldName`. It provides **a specific fallback value** when the original parameter is not submitted; for example, `!delivery=NONE`.

This is a **Spring web data binding** mechanism for form/request parameters, not a Bean Validation annotation. It typically appears when a controller accepts `@ModelAttribute`, uses `WebDataBinder` to bind data onto a bean, and may then invoke validation via `@Valid` or `@Validated`.

This lesson uses Spring Framework 6.x behavior with Java 17; the two prefixes and their processing order are long-standing `WebDataBinder` mechanisms. Application-specific settings can change or disable the prefixes.

## 2. Data lifecycle: browser → binder → model

For a checkbox named `subscribed`:

```html
<form method="post" action="/settings">
    <input type="hidden" name="_subscribed" value="present">
    <label>
        <input type="checkbox" name="subscribed" value="true">
        Receive notifications
    </label>
    <button type="submit">Save</button>
</form>
```

Suppose the initial model has `subscribed=true`:

| User submits form | Relevant request parameters | Value after binding |
| --- | --- | --- |
| Checkbox checked | `_subscribed=present`, `subscribed=true` | `true` |
| Checkbox unchecked | Only `_subscribed=present` | `false` |
| Request has neither field nor marker | No relevant parameters | Keeps the object's existing value; here still `true` |

The hidden parameter `_subscribed` is **always submitted** when the form contains this control. The `subscribed` parameter is submitted only if the checkbox is checked. Thus, the marker lets the binder distinguish **“the field was rendered but left empty”** from **“the field was not part of this update”**.

Flow diagram:

```text
POST /settings
      |
      v
Request parameters
      |
      +-- subscribed=true? ----- yes ---> use actual value "true"
      |                              |
      |                              +--> convert to boolean true
      |
      +-- subscribed absent
              |
              +-- has !subscribed? --- yes ---> use default value
              |
              +-- no !subscribed
                      |
                      +-- has _subscribed? -- yes ---> reset to empty value
                      |
                      +-- no marker ---------------> do not modify property
      |
      v
WebDataBinder + type conversion
      |
      v
Form object receives new value
      |
      v
BindingResult / validation (if requested)
```

**Important distinction**: on a new bean where a primitive `boolean` defaults to `false`, both “nothing sent” and “reset to `false`” produce the same result. The bug becomes visible only when **the object already holds `true`**, or when the type is `Boolean`/collection/string with a non-empty initial state.

## 3. Field marker: `_` prefix and resetting to “empty”

### 3.1. Meaning of `_field`

`WebDataBinder.DEFAULT_FIELD_MARKER_PREFIX` defaults to `"_"`. For a field named `subscribed`, the marker is `_subscribed`. For a nested property path such as `preferences.notifications`, the corresponding marker is `_preferences.notifications`.

A marker is **not a value for the real field**. For example:

```text
_subscribed=visible
```

It only indicates that the `subscribed` field was present on the form. The string value `"visible"` is arbitrary; the binder cares about the **presence** of the marker parameter, not its content.

Processing during the property binding step works roughly as follows:

1. Check whether the parameter name starts with the marker prefix.
2. Strip the prefix to determine the real field name.
3. Verify the field is allowed for binding and has a **writable** property.
4. If **no real value parameter** exists for that field, add an empty value based on the field's type.
5. Remove the marker parameter from the property values before continuing normal binding.

If both `subscribed=true` and `_subscribed=visible` exist, the real `subscribed` parameter **wins**; the marker does not overwrite the real value. If `subscribed` is absent, the marker supplies an appropriate empty value.

Markers only apply to **fields that are allowed to bind and writable**. If a field is excluded by `setAllowedFields(...)`, or lacks a writable property, the marker does not force the binder to modify it.

### 3.2. What does “empty” mean?

`WebDataBinder#getEmptyValue(...)` determines the empty value by data type:

| Java property type | Default empty value when only marker is sent | Notes |
| --- | --- | --- |
| `boolean` | `false` | Common checkbox case |
| `Boolean` | `Boolean.FALSE` | **Not `null`** by default |
| `String` | `null` | Different from empty string `""` |
| Array, e.g., `String[]` | Zero-length array | Can reset multi-checkbox groups |
| `Collection` such as `List` or `Set` | Compatible empty collection if instantiable | Used for selection groups |
| `Map` | Compatible empty map if instantiable | Applies when field supports binding |
| Other types (e.g., `Integer`) | Usually `null` | Unless application/provider customizes empty value creation |

Spring provides both `getEmptyValue(Class<?>)` and the protected variant `getEmptyValue(String, Class<?>)`. Specialized applications can subclass the binder and change how empty values are chosen, but normal code should rely on the default table and write boundary tests for the types in use.

**Do not misunderstand:** the `_subscribed` marker does not map to a bean field named `_subscribed`. Spring processes the prefix and then binds onto `subscribed`. If you name real fields starting with the special prefixes, consider changing the prefix configuration to avoid collisions.

### 3.3. Arrays or multiple checkboxes with the same name

With checkboxes sharing the name `interests`, each checked box can submit a value:

```html
<input type="hidden" name="_interests" value="present">
<label><input type="checkbox" name="interests" value="JAVA"> Java</label>
<label><input type="checkbox" name="interests" value="SPRING"> Spring</label>
```

If neither is checked, the request contains only `_interests`, so an array field `String[] interests` can be reset to an **empty array**. If `interests` is `List<String>`, Spring can assign an empty collection.

Only **one logical marker** is needed per field. Template tags may emit a hidden marker next to each checkbox; what matters is that the binder detects the marker's presence. If a request repeats the same marker key multiple times, keep the form markup simple and test with your actual template engine.

## 4. Field default: `!` prefix and fallback values

`WebDataBinder.DEFAULT_FIELD_DEFAULT_PREFIX` defaults to `"!"`. Example:

```html
<input type="hidden" name="!delivery" value="NONE">
<label><input type="radio" name="delivery" value="EMAIL"> Email</label>
<label><input type="radio" name="delivery" value="SMS"> SMS</label>
```

If the user selects no radio button and no `delivery` parameter is sent, the binder can use `NONE` from `!delivery`. When the user chooses `SMS`, `delivery=SMS` takes precedence and the hidden default is ignored.

**Difference:** a field marker only signals “the control was present but no value was submitted, reset to empty”; a field default carries **a specific value** (such as `"NONE"`, `"false"`, `"0"`), which is converted to the property's type during binding.

A field can have both a marker and a default:

```text
_subscribed=visible
!subscribed=true
```

If `subscribed` is missing, the binder uses `"true"` from the field default. It does **not** reset to `false` from the marker. When processing property values, Spring runs **`checkFieldDefaults(...)` before `checkFieldMarkers(...)`**, so defaults take precedence over markers.

### 4.1. Complete precedence order

For a boolean field `subscribed` where the existing object currently has `true`:

| Request parameters | Chosen source | Result |
| --- | --- | --- |
| `subscribed=false`, `!subscribed=true`, `_subscribed=x` | Actual value `subscribed` | `false` |
| `subscribed=true`, `_subscribed=x` | Actual value `subscribed` | `true` |
| `!subscribed=true`, `_subscribed=x` | Default `!subscribed` | `true` |
| `_subscribed=x` | Marker requests empty value | `false` |
| `!subscribed=false` | Default `!subscribed` | `false` |
| None of the three parameters | No update for property | Remains `true` |

Remember the order:

**Actual `field` value → default `!field` value → reset via `_field` marker → keep existing state if completely absent.**

These rules describe the binding mechanism only; if a property is not allowed to bind, is not writable, or fails type conversion, the outcome must be handled via binding configuration and `BindingResult`.

### 4.2. Field defaults vs Java/DTO defaults

An initialized field:

```java
private boolean subscribed = true;
```

is the **object's default value** when instantiated. In contrast, `!subscribed=false` is a **client-sent request parameter**. The two mechanisms are independent:

- Field **not submitted**: when binding onto an existing object, the value stays as is.
- Marker present without real field or default: binder resets according to type.
- Field default present: binder can overwrite initial state with the value from the request.
- Real field present: the real field is used.

Never use `!role=ADMIN`, `!isAdmin=true`, or client-controlled defaults to grant permissions. Authorization and invariants must be determined on the server, never derived from hidden parameters.

## 5. Runnable Java 17 example: testing WebDataBinder behavior

This example invokes `WebDataBinder` directly, **without starting a web server**. It simulates request data with `MutablePropertyValues` and prints the result after each bind to clearly show the precedence of `field`, `!field`, and `_field`. Because each scenario creates a fresh form, the results are independent and easy to verify.

### 5.1. Project structure

```text
webdatabinder-checkbox-demo/
├── pom.xml
└── src/main/java/demo/BinderDemo.java
```

### 5.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>webdatabinder-checkbox-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-web</artifactId>
            <version>6.2.12</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.BinderDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

The `spring-web` dependency contains `WebDataBinder`, while `MutablePropertyValues` and required binding classes are pulled in transitively by Spring. The example pins Spring 6.2.x and JDK 17; `spring-boot-starter-web` is unnecessary when simply testing the binder API.

### 5.3. `src/main/java/demo/BinderDemo.java`

```java
package demo;

import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.web.bind.WebDataBinder;

public final class BinderDemo {

    // JavaBean with public setters for WebDataBinder property binding.
    public static final class SettingsForm {
        private boolean subscribed = true;
        private String delivery = "EMAIL";
        private String[] interests = {"JAVA", "SPRING"};
        private List<String> roles = new ArrayList<>(List.of("USER"));

        public boolean isSubscribed() {
            return subscribed;
        }
        public void setSubscribed(boolean subscribed) {
            this.subscribed = subscribed;
        }

        public String getDelivery() {
            return delivery;
        }
        public void setDelivery(String delivery) {
            this.delivery = delivery;
        }

        public String[] getInterests() {
            return interests;
        }
        public void setInterests(String[] interests) {
            this.interests = interests;
        }

        public List<String> getRoles() {
            return roles;
        }
        public void setRoles(List<String> roles) {
            this.roles = roles;
        }
    }

    private static void scenario(
            String name, Consumer<MutablePropertyValues> input) {
        SettingsForm form = new SettingsForm();
        WebDataBinder binder = new WebDataBinder(form, "settings");

        // Allow only the demo form's properties.
        binder.setAllowedFields(
                "subscribed", "delivery", "interests", "roles");

        MutablePropertyValues values = new MutablePropertyValues();
        input.accept(values);
        binder.bind(values);

        if (binder.getBindingResult().hasErrors()) {
            throw new IllegalStateException(
                    binder.getBindingResult().toString());
        }

        System.out.printf(
                "%s: subscribed=%s, delivery=%s, interests=%d, roles=%d%n",
                name,
                form.isSubscribed(),
                form.getDelivery(),
                form.getInterests().length,
                form.getRoles().size());
    }

    public static void main(String[] args) {
        scenario("No fields", p -> {});

        scenario("Unchecked", p ->
                p.add("_subscribed", "visible"));

        scenario("Checked", p -> {
            p.add("_subscribed", "visible");
            p.add("subscribed", "true");
        });

        scenario("Default delivery", p ->
                p.add("!delivery", "NONE"));

        scenario("Explicit beats default", p -> {
            p.add("!delivery", "NONE");
            p.add("delivery", "SMS");
        });

        scenario("Default beats marker", p -> {
            p.add("_subscribed", "visible");
            p.add("!subscribed", "true");
        });

        scenario("Reset interests", p ->
                p.add("_interests", "visible"));

        scenario("Reset roles", p ->
                p.add("_roles", "visible"));

        scenario("Reset delivery", p ->
                p.add("_delivery", "visible"));
    }
}
```

This is a **complete** program. Fields have public getters and setters; the binder uses JavaBean property binding without needing direct access to private fields. `setAllowedFields(...)` clarifies the permitted input scope, though the example does not test a real HTTP endpoint.

Run with JDK 17+ and Maven in the project directory:

```bash
mvn -q clean compile exec:java
```

**Program stdout** (excluding Maven logs, if any):

```text
No fields: subscribed=true, delivery=EMAIL, interests=2, roles=1
Unchecked: subscribed=false, delivery=EMAIL, interests=2, roles=1
Checked: subscribed=true, delivery=EMAIL, interests=2, roles=1
Default delivery: subscribed=true, delivery=NONE, interests=2, roles=1
Explicit beats default: subscribed=true, delivery=SMS, interests=2, roles=1
Default beats marker: subscribed=true, delivery=EMAIL, interests=2, roles=1
Reset interests: subscribed=true, delivery=EMAIL, interests=0, roles=1
Reset roles: subscribed=true, delivery=EMAIL, interests=2, roles=0
Reset delivery: subscribed=true, delivery=null, interests=2, roles=1
```

### 5.4. Scenario-by-scenario breakdown

- **No fields:** request contains no real field, marker, or default; the binder has no reason to overwrite initial state.
- **Unchecked:** `_subscribed` is present while `subscribed` is absent; `getEmptyValue(boolean.class)` selects `false`.
- **Checked:** both the real field and marker are present; `subscribed=true` is converted and takes precedence.
- **Default delivery:** `!delivery=NONE` is used because no `delivery` parameter exists.
- **Explicit beats default:** `delivery=SMS` takes precedence over `!delivery=NONE`.
- **Default beats marker:** `!subscribed=true` is applied before the marker; `true` is retained instead of resetting to `false`.
- **Reset interests:** `_interests` replaces the two-element array with a zero-length array.
- **Reset roles:** `_roles` replaces the single-item collection with an empty collection.
- **Reset delivery:** `_delivery` sets `String` to `null` rather than creating `""`.

The code prints **array and collection lengths** instead of collection implementation types to keep stdout stable and focus on semantics. In production requests, if a parameter has multiple values (multiple checkboxes selected), Spring must also convert request strings/arrays into the target property type; the example avoids that variability by simulating boundary cases directly.

## 6. Using in a Spring MVC controller with `@ModelAttribute`

In Spring Web MVC, `WebDataBinder` is normally created per parameter-binding pass on a command object. You can configure the binder via `@InitBinder`.

The example below is an **integration fragment inside a Spring Boot 3 app with Spring Web**, not a standalone Java class runnable with the previous demo's `pom.xml`:

```java
import org.springframework.stereotype.Controller;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;

@Controller
public class SettingsController {
    @InitBinder("settings")
    void initSettingsBinder(WebDataBinder binder) {
        binder.setAllowedFields(
                "subscribed", "delivery", "interests");
        // Default prefixes "_" and "!" already suffice for HTML forms.
    }

    @PostMapping("/settings")
    String update(
            @ModelAttribute("settings") SettingsForm form,
            BindingResult bindingResult) {

        if (bindingResult.hasErrors()) {
            return "settings-form";
        }

        // Save allowed form fields onto the domain model.
        return "redirect:/settings";
    }
}
```

`SettingsForm` is the model/form class to define in your web project; it can be modeled after the JavaBean in the demo, choosing properties suited to the endpoint. `BindingResult` must immediately follow the model parameter it describes so Spring pairs errors accurately.

To run Jakarta Bean Validation after binding, place `@Valid`/`@Validated` on the model parameter with an appropriate Jakarta Validation provider. Checkbox markers still run during the **binding** phase; Bean Validation checks values **after data binding**.

### 6.1. Hand-written HTML vs Spring form tags

If writing HTML forms directly, add the hidden marker yourself:

```html
<input type="hidden" name="_subscribed" value="1">
<input type="checkbox" name="subscribed" value="true">
```

When rendering with the **JSP Spring Form Tag Library**, `<form:checkbox path="subscribed"/>` automatically generates a hidden marker following the `_subscribed` convention. Inspect the rendered HTML because other template engines, custom JavaScript controls, and UI frameworks may handle checkboxes differently.

Example JSP fragment inside a form bound to a `modelAttribute`:

```jsp
<form:form modelAttribute="settings" method="post">
    <form:checkbox path="subscribed" label="Receive notifications"/>
    <button type="submit">Save</button>
</form:form>
```

This JSP fragment requires the Spring form taglib declared in the JSP file and a controller preparing the matching `modelAttribute`. When inspecting the actual HTML, confirm the hidden marker is submitted with the form even when the checkbox is unchecked.

### 6.2. Configuring prefixes for special forms

`WebDataBinder` provides:

```java
@InitBinder("settings")
void configure(WebDataBinder binder) {
    binder.setFieldMarkerPrefix("_");
    binder.setFieldDefaultPrefix("!");
    binder.setAllowedFields("subscribed", "delivery", "interests");
}
```

This is a controller fragment. The two prefix calls merely restate the **default values** and are normally unnecessary. If a frontend framework already uses different names, you can change them:

```java
binder.setFieldMarkerPrefix("~");
binder.setFieldDefaultPrefix("$");
```

Then the marker must be named `~subscribed` and the default `$subscribed`. Both form rendering and binding must use the **same convention**; changing only one side will break resetting/defaults.

- `setFieldMarkerPrefix(null)`: disables field marker processing completely.
- `setFieldDefaultPrefix(null)`: disables field default processing.

Disabling prefixes can suit a client protocol designed differently, provided tests prove **unchecked/unselected** states update properly.

## 7. How do field markers differ from other Spring mechanisms?

| Mechanism | Phase | What it solves |
| --- | --- | --- |
| `WebDataBinder` field marker `_field` | HTTP form/request parameter → object property | Distinguishes a field that was present without a submitted value |
| `WebDataBinder` field default `!field` | HTTP form/request parameter → object property | Supplies a fallback value when the real field is absent |
| `@ModelAttribute` | Spring MVC argument resolution | Creates/fetches model and binds request onto properties |
| `ConversionService` / property editor | Type conversion | Converts `"true"`, `"3"`, date strings into Java types |
| `@Valid` / `@Validated` | Validation | Checks constraints after binding |
| `BindingResult` | Binding/validation error reporting | Records conversion and constraint errors |
| `@RequestBody` with JSON/Jackson | HTTP message conversion | Parses JSON into object; **does not rely on form binding `_field` markers** |
| Standalone `@RequestParam` | Reading a request parameter | Reads an individual parameter, not equivalent to multi-property `@ModelAttribute` binding |

For example, JSON:

```json
{"subscribed": false}
```

is an **explicit** boolean value. If a client sends JSON `{}`, the field is absent; missing-field semantics depend on Jackson, constructors, object defaults, and update logic. Sending a JSON key `"_subscribed"` does not trigger `WebDataBinder`'s convention during JSON message conversion.

For REST APIs with PATCH or partial-update semantics, **do not automatically equate “absent” with “false”**. A PATCH may require keeping the existing value when a field is omitted from the payload; a full-edit POST form may need to reset unchecked checkboxes. Choose semantics per API contract.

## 8. Security and data integrity

Markers and defaults are **client-sent**, even when placed in hidden inputs. Any client can tamper with `_field`, `!field`, or manually add real fields. Therefore:

1. **Bind only fields permitted by the endpoint.** Use dedicated forms/DTOs and `binder.setAllowedFields(...)`, such as `"subscribed"`, `"delivery"`, `"interests"`. This is an allowlist, not a suggestion list.
2. **Never bind directly to an entire entity/domain object** containing roles, account IDs, status, price, admin flags, or internal fields without restricting writable properties.
3. **Never use `!isAdmin=true` as a security default.** Hidden values are no more trustworthy than any other form field.
4. **Validate data after binding**, such as selection limits, valid enum values, and cross-field conditions; validation does not replace authorization checks.
5. **Protect state-changing HTML forms with CSRF** per Spring Security configuration, independent of markers. A hidden marker field is not a CSRF token.
6. **Check allowed fields before resetting**: Spring processes markers/defaults for permitted, writable properties. Missing an allowlist lets attackers target properties the form UI never meant to change.
7. **Do not ignore binding errors.** If `!delivery` contains a value that cannot convert to the property type, handle the error via `BindingResult` or an appropriate error path.

For complex applications with many fields, split form objects per use case rather than using one giant model holding every entity property. That prevents one form's markers from accidentally resetting data belonging to another form.

## 9. Edge cases and common errors

### 9.1. Checkbox is unchecked, yet the object stays `true`

**Symptom:** the edit form displays a checked checkbox, the user unchecks it and saves, and refreshing still shows it checked.

**Common cause:** the request has neither `subscribed` nor `_subscribed`; the binder cannot distinguish “unchecked” from “field not sent”.

**Fix:** place the hidden marker inside the form with the same base name:

```html
<input type="hidden" name="_subscribed" value="present">
<input type="checkbox" name="subscribed" value="true">
```

Inspect the browser's Network → Form Data tab. When unchecked, the request must still include `_subscribed`.

### 9.2. Sending `_field=false` does not change the field as desired

`_field` **does not carry a reset value**. The binder checks only for presence. For `String`, the empty value is `null`; for arrays, an empty array; for `Boolean`, `false`. If you want a specific value other than “empty”, use `!field=desiredValue`.

### 9.3. Both marker and default are sent, expecting the marker to win

By the `checkFieldDefaults` → `checkFieldMarkers` order, defaults are applied before markers run. Once a default populates the real field, the marker sees the field is present and does not reset it. If you want marker reset behavior, **do not** also send a default that overrides the outcome.

### 9.4. Using `_field` for a nonexistent field

If a property is not writable or not in the allowlist, a marker will not create a valid property. Do not expect `_permissions` to magically create a `permissions` property on a DTO.

### 9.5. `Boolean` has three states, but the marker wipes out `null`

When a field is `Boolean`, a marker resets it to `Boolean.FALSE` by default, **not `null`**. If business logic distinguishes “unanswered” (`null`) from “answered no” (`false`), use an appropriate input model—such as radio buttons with explicit options or a dedicated state DTO—rather than expecting a boolean checkbox to preserve three states.

### 9.6. Multiple checkboxes leave old values behind

If a group sends values when checked but **sends no marker when nothing is selected**, old selections may persist. Add `_interests`/`_roles` to the form and test selecting all → unselecting all. Ensure the target property is a bindable array or `Collection`.

### 9.7. Frontend library checkboxes not using native HTML submission

Many UI components render a button or div instead of `<input type="checkbox">` and serialize data themselves. Inspect the actual payload. If the client explicitly sends `subscribed=false`, no marker is needed for a missing parameter. If the client omits the field when false, apply the matching convention.

### 9.8. Marker is in the form markup but never submitted

A hidden input might sit outside the `<form>` tag, be `disabled`, be stripped from the payload by JavaScript, or use a mismatched property name. HTML's `hidden` attribute itself imposes no server behavior; only the actual request parameters sent over HTTP matter.

### 9.9. Sending JSON and expecting `_field` to take effect

When an endpoint uses `@RequestBody` and Jackson, the payload is decoded by an HTTP message converter. `WebDataBinder`'s `_field` and `!field` conventions do not run during JSON deserialization. For JSON, define `false`, `null`, and missing-field semantics explicitly in your API schema/contract.

### 9.10. Missing form errors after binding

Field markers manage values, not validation exemptions. When a field is reset to `null` or an empty collection, `@NotNull`, `@NotEmpty`, or other constraints may fail. The controller must inspect `BindingResult` and display errors; do not assume “unchecked” is always valid.

## 10. Systematic testing

Spring MVC integration tests can use `MockMvc` to verify realistic form payloads. Scenarios to cover:

| Input / initial state | Expected outcome |
| --- | --- |
| Initial `subscribed=true`, only `_subscribed` | `subscribed=false` |
| Initial `subscribed=true`, no related parameters | `subscribed=true` (when binding onto existing object) |
| Initial `subscribed=false`, `subscribed=true` and marker | `subscribed=true` |
| Initial `delivery=EMAIL`, only `!delivery=NONE` | `delivery=NONE` |
| Both `delivery=SMS` and `!delivery=NONE` | `delivery=SMS` |
| Both `!subscribed=true` and `_subscribed` | Default `true` beats marker |
| Populated `String[] interests`, only `_interests` | Zero-length array |
| Populated `List<String> roles`, only `_roles` | Empty collection |
| Populated `String delivery`, only `_delivery` | `null` |
| Marker/default for field outside allowlist | Disallowed field is not updated |
| Unconvertible actual value | Binding error properly recorded |
| `setFieldMarkerPrefix(null)` configured | Marker does not auto-reset |

Some tests must clearly distinguish **pre-populated models** from **newly created models**. If you only test a new primitive boolean defaulting to `false`, the test may “pass” without proving the marker actually worked. To catch real bugs, initialize the starting value to `true`, then submit an unchecked form.

For controllers, verify both the response and the values the application actually persists, not just returned HTML. Use exact field names in `MockMvc.param(...)`, such as `.param("_subscribed", "present")`. If the endpoint updates a domain entity, verify that mapping from the form DTO to the entity actually applies the new `false` value.

## 11. Checklist for reliable checkbox forms

- [ ] Clearly identify property names, types, and before/after states.
- [ ] If unchecked sends no real value, add a hidden marker named `_field`.
- [ ] If a non-empty fallback value is needed, add `!field=value`.
- [ ] Do not send a default when you actually want the marker's reset behavior.
- [ ] Keep real field names, markers/defaults, and JavaBean property names consistent.
- [ ] For checkbox groups, test the **none selected** case.
- [ ] Use a dedicated form DTO and allowlist bindable fields.
- [ ] Verify whether your template engine emits markers by inspecting HTML and HTTP requests.
- [ ] Handle `BindingResult` and post-binding validation as needed.
- [ ] Write tests on objects with non-empty initial values.
- [ ] Do not implicitly carry form marker conventions over to JSON/PATCH APIs.
- [ ] When changing or disabling prefixes, update both request generation and tests.

**Practical rule:** in HTML forms, the **absence of a parameter** does not equal `false`. `_field` declares that the field existed on the form so it should be reset if no value arrives; `!field` supplies a specific fallback; the real `field` parameter has highest priority. Mastering that order and inspecting real payloads keeps checkboxes, radios, multi-selects, and nullable fields predictable.

## References

- [Spring Framework 6.2 WebDataBinder Javadoc — markers, defaults, empty values](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/bind/WebDataBinder.html)
- [Spring Framework 6.2 Reference — `@InitBinder` and allowed fields](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework 6.2 Reference — JSP Spring Form Tag checkbox](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc-view/mvc-jsp.html)
- [Spring Framework source — `WebDataBinder.java`](https://github.com/spring-projects/spring-framework/blob/6.2.x/spring-web/src/main/java/org/springframework/web/bind/WebDataBinder.java)
