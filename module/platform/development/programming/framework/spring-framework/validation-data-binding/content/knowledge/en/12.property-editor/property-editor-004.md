# StringTrimmerEditor and Converting Empty Strings to Null in Spring Framework

In web applications, users frequently submit values like `"  Lan  "`, `""`, or `"   "`. Even though an input field looks blank, the received data can still be a non-null `String` object containing only whitespace. Spring's **`StringTrimmerEditor`** normalizes such string values during **property binding**: it trims leading and trailing whitespace and, if configured, converts an empty result into **`null`**.

The core concept consists of two distinct behaviors:

1. **Trim**: `"  Lan  "` becomes `"Lan"`.
2. **Empty-as-null**: when the processed string becomes `""`, convert it to `null` if `emptyAsNull=true` is selected; if `false`, keep `""`.

`StringTrimmerEditor` belongs to the **PropertyEditor** family; it is not a validation annotation, does not trigger automatically for every HTTP request, and **is not registered by Spring by default for all strings**. This article explains the API, how to register it on `DataBinder`/`WebDataBinder`, the difference between empty strings and `null`, effects on Bean Validation, a runnable Java 17 example, and common real-world pitfalls.

## 1. Why Distinguish Empty, Whitespace, and Null?

Java has three values that are very easy to conflate:

| Value | `value == null` | `value.isEmpty()` | `value.isBlank()` in Java 17 |
| --- | --- | --- | --- |
| `null` | `true` | Cannot call; throws `NullPointerException` | Cannot call |
| `""` | `false` | `true` | `true` |
| `"   "` | `false` | `false` | `true` |
| `"  Lan  "` | `false` | `false` | `false` |

For an optional `middleName` property, many applications treat both `""` and `"   "` as **no data provided**, represented by `null` in the DTO. Downstream logic can then check `middleName == null` instead of manually handling multiple whitespace variants.

Conversely, for input data that must preserve exact bytes/characters, such as passwords, signatures, document bodies, or multiline text, automatic trimming can **alter the meaning of the data**. Therefore, it cannot be applied blindly to every `String` across the entire application.

**Foundational rule:** `null` means **no object reference**; `""` means **a String object with length 0**; `"   "` is a string with characters consisting only of whitespace in common terms. Whether these three cases should collapse into one is an **input contract decision**.

## 2. What Is StringTrimmerEditor?

Full class name:

```java
org.springframework.beans.propertyeditors.StringTrimmerEditor
```

It extends `java.beans.PropertyEditorSupport`, implementing the JavaBeans `PropertyEditor` mechanism. Spring can register this editor on a binder to convert **string input data into a `String` property value** before calling the corresponding setter.

Main constructors:

```java
new StringTrimmerEditor(true);
new StringTrimmerEditor(false);
new StringTrimmerEditor("\r\n\f", true);
```

| Constructor | Meaning |
| --- | --- |
| `StringTrimmerEditor(true)` | Trims leading/trailing whitespace; sets value to `null` if the result is empty |
| `StringTrimmerEditor(false)` | Trims leading/trailing whitespace, keeping an empty result as `""` |
| `StringTrimmerEditor(charsToDelete, emptyAsNull)` | Trims, then deletes any characters listed in `charsToDelete`, then checks emptiness to convert to `null` if the flag is enabled |

The boolean argument does not mean "enable or disable trimming": **this boolean only controls converting an empty string to `null`**. Both `true` and `false` perform trimming.

### How `setAsText` processes input

The editor's processing rule can be understood through a simplified algorithm:

```java
void conceptualSetAsText(String text) {
    if (text == null) {
        setValue(null);
        return;
    }

    String value = text.trim();

    if (charsToDelete != null) {
        value = StringUtils.deleteAny(value, charsToDelete);
    }

    setValue(emptyAsNull && value.isEmpty() ? null : value);
}
```

This is **illustrative pseudo-code**, not a method to copy into a standalone class: `charsToDelete`, `emptyAsNull`, and `setValue` are parts of the editor implementation; `StringUtils` is Spring's utility class. The important part is the **order: trim -> delete optional characters -> convert empty to null**.

An input that is initially `null` remains `null` even when `emptyAsNull=false`. The `false` flag **does not convert null into an empty string**.

### PropertyEditor getter/setter

- `setAsText(String)`: receives text and converts it into the value stored by the editor.
- `getValue()`: retrieves the converted value; may be a `String` or `null`.
- `getAsText()`: represents the current value as text; with `StringTrimmerEditor`, when the internal value is `null`, the text result is `""`.

Because `getAsText()` represents `null` as `""`, to verify conversion to `null`, inspect **`getValue()` or the actual property on the target**, not just the rendered text.

## 3. Behavior Table: emptyAsNull true vs. false

Assume no extra `charsToDelete` is passed and the editor's trimming mechanism is used.

| Input | `new StringTrimmerEditor(true)` | `new StringTrimmerEditor(false)` |
| --- | --- | --- |
| `null` | `null` | `null` |
| `""` | `null` | `""` |
| `"   "` | `null` | `""` |
| `" \t "` | `null` | `""` |
| `"  Lan  "` | `"Lan"` | `"Lan"` |
| `" A  B "` | `"A  B"` | `"A  B"` |
| `"null"` (four letters) | `"null"` | `"null"` |
| `"  42  "` | `"42"` | `"42"` |

Three points to remember:

1. **Does not remove internal spaces**: `" A  B "` becomes `"A  B"`. This is a trim operation, not a whitespace-collapsing function.
2. A string with content `"null"` remains **four characters**, not Java `null`. The editor does not interpret literal text specially.
3. The editor relies on Java's `String.trim()`: do not assume it removes **all** Unicode whitespace, such as non-breaking space (`U+00A0`). Java's `String.isBlank()` and `String.strip()` follow different rules; do not equate them with `String.trim()`.

The table above describes operations on strings passed **through the editor**. If you invoke a DTO setter directly:

```java
form.setName("   ");
```

no `StringTrimmerEditor` magically appears just because the project uses Spring. Normalization is a behavior of a **configured conversion/binding path**, not a property of every setter.

## 4. Character Deletion Option: charsToDelete

Two-argument constructor:

```java
StringTrimmerEditor editor =
        new StringTrimmerEditor("\r\n\f", true);
```

Characters in `charsToDelete` are **a set of characters to delete at any position after trimming**, not a regex and not limited to leading/trailing positions.

Example:

```java
editor.setAsText("  AB\nCD  ");
System.out.println(editor.getValue()); // "ABCD"
```

Because the editor deletes the newline character in the middle, the two lines join into `ABCD`. When the input contains only characters in the deletion set and/or trimmed characters, the final result becomes `""` and is converted to `null` if `emptyAsNull=true`.

**Caution:** adding a regular space (`" "`) to `charsToDelete` can remove **internal spaces too**, turning `"Ho Chi Minh"` into `"HoChiMinh"`. This differs from standard trimming and easily corrupts names, addresses, and free-form text. Deleting newlines may also be inappropriate for textareas and multiline comments; set policies per field appropriately.

## 5. How to Register with DataBinder

`DataBinder` belongs to `org.springframework.validation`. It does not apply `StringTrimmerEditor` automatically; developers must register the editor via `registerCustomEditor(...)`.

### Applying to all String properties

```java
DataBinder binder = new DataBinder(form, "form");
binder.registerCustomEditor(
        String.class, new StringTrimmerEditor(true));
```

Here:

- `String.class` is the property type to convert.
- `new StringTrimmerEditor(true)` is the normalizing editor.
- This configuration applies to `String` properties that the binder **actually binds** through the appropriate mechanism.
- Registration does not retroactively mutate existing values on `form`. Without a corresponding bind/convert pass, setters are not invoked merely because an editor is registered.

Afterward, `binder.bind(MutablePropertyValues)` can convert incoming text to `null` or a trimmed string before writing to the bean.

### Applying to a single specific property

`DataBinder` also has an overload accepting a field name:

```java
binder.registerCustomEditor(
        String.class,
        "displayName",
        new StringTrimmerEditor(true));
```

This is useful when only `displayName` should be trimmed, while `rawMessage` or `secretValue` must be preserved verbatim.

If the property lives on a nested object, you can pass a path like `"contact.displayName"` when the binder's target is the parent object owning that property. Do not guess paths: the binder's target determines where paths start.

**A single property path should not have conflicting editors registered.** Especially when dealing with collection-level and element-level editors on the same path, check the specific rules of `PropertyEditorRegistry`. For ordinary string trimming, one clear type-wide String editor or one field-specific String editor suffices.

### What to watch out for when registering for String.class?

This is a broad configuration: names, descriptions, notes, and user content may all be trimmed if bound through the same binder and matching the type. If the application needs to preserve line breaks, whitespace, or user secrets, consider field-level registration rather than applying to all Strings.

`StringTrimmerEditor` is a **stateful PropertyEditor** (its value is stored in the instance). Best practice is creating an editor per binder/request, as in `@InitBinder`, rather than sharing a global mutable instance across requests and threads.

## 6. Runnable Java 17 Example: Trim, Empty-to-Null, and Binding

This example uses `DataBinder` directly, **without Spring Boot or an HTTP server**. We will inspect the editor's direct behavior, applying it to all `String`s, the difference when targeting only one field, and how a field **absent from input** stays untouched.

### 6.1. Project structure

```text
string-trimmer-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/StringTrimmerDemo.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'string-trimmer-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.18'
}

application {
    mainClass = 'example.StringTrimmerDemo'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
```

Use JDK 17+ and a Gradle version capable of running on that JDK, with Maven Central access for the initial dependency download. `spring-context` brings in the Spring modules needed for `DataBinder` and `StringTrimmerEditor`; the example does not depend on Jakarta Validation.

### 6.2. Complete Java code

**`src/main/java/example/StringTrimmerDemo.java`**

```java
package example;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.beans.propertyeditors.StringTrimmerEditor;
import org.springframework.validation.DataBinder;

public class StringTrimmerDemo {

    public static class ContactForm {
        private String name;
        private String nickname;
        private String note;
        private String missing = "original";

        public ContactForm() {
        }

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public String getNickname() {
            return nickname;
        }

        public void setNickname(String nickname) {
            this.nickname = nickname;
        }

        public String getNote() {
            return note;
        }

        public void setNote(String note) {
            this.note = note;
        }

        public String getMissing() {
            return missing;
        }

        public void setMissing(String missing) {
            this.missing = missing;
        }
    }

    private static String show(String value) {
        return value == null ? "<null>" : "[" + value + "]";
    }

    public static void main(String[] args) {
        StringTrimmerEditor direct = new StringTrimmerEditor(true);
        direct.setAsText("  Lan  ");
        System.out.println("direct=" + show((String) direct.getValue()));

        direct.setAsText(" \t ");
        System.out.println(
                "emptyAsNull=" + show((String) direct.getValue()));

        StringTrimmerEditor keepEmpty = new StringTrimmerEditor(false);
        keepEmpty.setAsText(" \t ");
        System.out.println(
                "keepEmpty=" + show((String) keepEmpty.getValue()));

        StringTrimmerEditor deleteLineBreaks =
                new StringTrimmerEditor("\r\n", true);
        deleteLineBreaks.setAsText(" A\nB ");
        System.out.println(
                "deleteLineBreaks="
                        + show((String) deleteLineBreaks.getValue()));

        direct.setAsText(null);
        System.out.println(
                "nullInput=" + show((String) direct.getValue()));
        System.out.println("nullAsText=[" + direct.getAsText() + "]");

        ContactForm form = new ContactForm();
        DataBinder binder = new DataBinder(form, "contactForm");
        binder.registerCustomEditor(
                String.class, new StringTrimmerEditor(true));

        MutablePropertyValues values = new MutablePropertyValues();
        values.add("name", "  Lan Anh  ");
        values.add("nickname", "  \t  ");
        values.add("note", "  Two  spaces  ");

        binder.bind(values);

        System.out.println("bindName=" + show(form.getName()));
        System.out.println("bindNickname=" + show(form.getNickname()));
        System.out.println("bindNote=" + show(form.getNote()));
        System.out.println("bindMissing=" + show(form.getMissing()));
        System.out.println(
                "errors=" + binder.getBindingResult().getErrorCount());

        ContactForm pathOnly = new ContactForm();
        DataBinder pathBinder = new DataBinder(pathOnly, "contactForm");
        pathBinder.registerCustomEditor(
                String.class, "name", new StringTrimmerEditor(true));

        MutablePropertyValues pathValues = new MutablePropertyValues();
        pathValues.add("name", "  Mai  ");
        pathValues.add("nickname", "   ");

        pathBinder.bind(pathValues);

        System.out.println("onlyName=" + show(pathOnly.getName()));
        System.out.println(
                "onlyNickname=" + show(pathOnly.getNickname()));
    }
}
```

### 6.3. Run and stdout

In the `string-trimmer-demo` directory:

```bash
gradle -q run
```

If a Gradle wrapper is present, use `./gradlew -q run` on Linux/macOS or `gradlew.bat -q run` on Windows.

**Expected stdout:**

```text
direct=[Lan]
emptyAsNull=<null>
keepEmpty=[]
deleteLineBreaks=[AB]
nullInput=<null>
nullAsText=[]
bindName=[Lan Anh]
bindNickname=<null>
bindNote=[Two  spaces]
bindMissing=[original]
errors=0
onlyName=[Mai]
onlyNickname=[   ]
```

Explanation:

1. `direct` shows trimming a non-empty string: `"  Lan  "` becomes `"Lan"`.
2. `emptyAsNull`: after trimming `" \t "` to empty, the editor produces **`null`**.
3. `keepEmpty`: same input but boolean `false`, so the value is `""`; `show` displays `[]`, distinct from `<null>`.
4. `deleteLineBreaks` removes the newline between `A` and `B` thanks to `charsToDelete="\r\n"`, yielding `"AB"`.
5. `nullInput` preserves `null`. However, `getAsText()` returns an empty string for `null`, so `nullAsText=[]`; do not confuse display text with the stored value.
6. When registered for all `String.class`, `name` is trimmed; `nickname` containing only whitespace becomes `null`; `note` preserves **the two spaces in the middle**.
7. `missing` is not in `MutablePropertyValues`, so it is not modified and retains its initial value `"original"`.
8. `errors=0`: the example has no conversion errors and no constraint validator registered. The editor **does not automatically generate validation errors** merely because it converts an empty string to `null`.
9. With the property-specific overload `"name"`, only `name` passes through the trimmer; `nickname` has no editor registered and remains a three-space string. The result `onlyNickname=[   ]` differs from `null`.

Each binder in the example is used in a single binding pass with its own editor. Even though an editor can be called sequentially in tests via `setAsText`, the same instance should never be shared across concurrent threads.

## 7. Registering in Spring MVC with @InitBinder

In Spring MVC (Servlet stack), `WebDataBinder` extends `DataBinder`. An `@InitBinder` method registers editors for the binder serving a model attribute.

Example **integration snippet** inside a controller:

```java
import org.springframework.beans.propertyeditors.StringTrimmerEditor;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;

@InitBinder("contactForm")
void initContactBinder(WebDataBinder binder) {
    binder.registerCustomEditor(
            String.class, new StringTrimmerEditor(true));
}
```

This snippet must sit **inside a Spring MVC controller class or appropriate controller advice**; it is not a standalone Java SE program. The name `"contactForm"` must match the actual model attribute:

```java
@PostMapping("/contacts")
public String submit(
        @Valid @ModelAttribute("contactForm") ContactForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return "contacts/form";
    }
    return "contacts/result";
}
```

The `@PostMapping` snippet is also **integration code**, requiring Spring MVC/Jakarta Validation imports, the `ContactForm` class, view templates, and matching application setup. Those snippets only illustrate **exactly where** the editor participates; the complete standalone runnable example is in section 6.

Typical processing flow of a URL-encoded form:

```text
POST /contacts
Content-Type: application/x-www-form-urlencoded

name=++Lan++&nickname=+++
            |
            v
Spring MVC prepares WebDataBinder for "contactForm"
            |
            v
@InitBinder registers StringTrimmerEditor(true)
            |
            v
Read request parameters -> conversion and property binding
            |
            +-- name: "  Lan  " -> "Lan"
            +-- nickname: "   " -> null
            |
            v
Run validation if triggered (@Valid / @Validated)
            |
            v
Controller reads ContactForm and BindingResult
```

Note that `+` in `application/x-www-form-urlencoded` is normally decoded as a space. The flow above assumes the binder actually receives the fields and they are not excluded from allowed fields. `@InitBinder` **configures** the editor; it does not call `binder.bind(...)` or `binder.validate()` merely by virtue of the annotation existing.

### Controller-local, model-attribute-specific, or global?

- `@InitBinder("contactForm")` inside a controller restricts configuration to the matching model attribute name.
- `@InitBinder` without a name inside a controller applies more broadly to binders within that controller.
- `@InitBinder` inside `@ControllerAdvice` can apply across a set of controllers governed by the advice. If normalizing all strings broadly, audit fields like passwords, rich text, and textareas.

This is why you should pick the **narrowest registration scope** that fits your data requirements.

## 8. Difference Between an Absent Field and an Empty-String Field

A form has three distinct scenarios:

| Scenario | Request data | Likely outcome with StringTrimmerEditor(true) |
| --- | --- | --- |
| Field present with nothing typed | `name=` | Property binds to `null` |
| Field contains only whitespace | `name=+++` (URL-encoded) | After decoding + trimming, becomes `null` |
| Field absent from request | No `name` key | Editor typically does not run for this field; existing value on target is preserved |

This is especially important when updating an object **that already holds data**. `StringTrimmerEditor` does not set every missing property to `null`. If a PATCH operation should mean "clear value", define a clear contract between an **omitted field** and a **field sent as an empty string**. With reused model attributes, pre-bind values and setter policies both affect the result.

`"null"` (four letters) is not `null`; the editor only converts **a post-normalization string of length 0**. Likewise, `"0"` or `"false"` still has content — it is not turned into null just because it represents a commonly falsy value.

## 9. Impact on Jakarta Bean Validation

`StringTrimmerEditor` performs **normalization/conversion**. Annotations such as `@NotNull`, `@NotEmpty`, and `@NotBlank` perform **validation**. The typical order for `@ModelAttribute` is binding first and validation second, so the editor can alter the input value seen by constraints.

Suppose the input is `"   "` and the property type is `String`:

| Constraint | Without trimming | With StringTrimmerEditor(true) applied |
| --- | --- | --- |
| `@NotNull` | Usually passes, since value is a non-null String | Fails, since value becomes `null` |
| `@NotEmpty` | Usually passes, since it has three characters | Fails, since value becomes `null` |
| `@NotBlank` | Fails, since it contains only whitespace | Fails, since value becomes `null` |
| `@Size(min=1)` | Usually passes since length is 3 | `null` is normally considered valid by `@Size`; add `@NotNull` if required |
| `@Pattern(...)` | Depends on the specific regex | `null` is normally not rejected by `@Pattern`; combine with `@NotNull` if needed |

This table assumes a Jakarta Bean Validation provider is configured and constraints actually run. Do not infer that every field has `@Valid` or that validation turns on automatically simply by registering an editor.

### Choosing constraints by intent

- Use `@NotBlank` for required text that must not be whitespace-only.
- Use `@NotNull` when the presence of a value is mandatory.
- Use `@NotEmpty` when the value must not be null or empty; for whitespace-only Strings, understand whether an editor normalizes them beforehand.
- Use `@Size` for length bounds; by itself it does not guarantee a non-null property.

Integration DTO example:

```java
public class ContactForm {
    @NotBlank
    private String name;

    private String nickname;

    // Getters, setters, and constructors per the chosen binding mechanism.
}
```

This is an **illustrative snippet**, requiring `jakarta.validation.constraints.NotBlank` and actual accessors. If `nickname` contains only whitespace and the true editor is applied, it becomes `null`, while `name` is rejected by `@NotBlank` when empty. The editor itself does not decide whether to return HTTP 400 or the error message text; the controller and validation/error handling decide that.

**Avoid implicit reliance on normalization.** A validation rule shared across Spring MVC, batch imports, and asynchronous consumers may receive data that never passed through `StringTrimmerEditor`. If the system requires storing canonical data, design a consistent normalization policy at trusted entry points, not just in one controller.

## 10. What Is Not Handled by StringTrimmerEditor?

This editor has a very specific scope:

1. **Not a security filter**: does not sanitize HTML, prevent SQL injection, escape output, or verify authorization. Query parameterization, output encoding, and access control remain separate concerns.
2. **Does not validate emails, phone numbers, or URLs**: `"bad-email"` remains a non-empty string after trimming.
3. **Does not collapse internal spaces by default**: `"An  Binh"` still keeps two spaces between words.
4. **Does not normalize all Unicode whitespace by default**: its trimming is based on `String.trim()`, not Unicode normalization.
5. **Does not process data outside the binder**: manually constructed objects, directly called setters, or batch jobs bypassing the editor are unaffected.
6. **Not guaranteed to apply to `@RequestBody` JSON**: Spring MVC normally uses `HttpMessageConverter`/Jackson to deserialize JSON. `WebDataBinder` editors for property binding are not Jackson's default mechanism.
7. **Not a cure for other type conversion failures**: input `age=abc` for `Integer age` is not fixed by an editor registered for `String.class`.
8. **Not equivalent to `StringUtils.hasText` or `String.isBlank`**: those methods inspect text, whereas the editor **transforms** the value during conversion.
9. **Does not decide database storage behavior**: JPA, JDBC, and serialization work with whatever data they receive; the editor does not rewrite existing records.

For `@RequestParam`, `@PathVariable`, and other resolvers, conversion paths may use binder/conversion infrastructure depending on context; do not claim that a single `@InitBinder` trims every parameter kind identically to `@ModelAttribute`. Test the real behavior of each endpoint.

## 11. Common StringTrimmerEditor Mistakes

| Symptom | Possible cause | Remediation |
| --- | --- | --- |
| Created `new StringTrimmerEditor(true)` yet field keeps spaces | Forgot `registerCustomEditor` on the binder binding the field | Register on the right binder and model attribute |
| Blank string remains `""` instead of `null` | Used `StringTrimmerEditor(false)` | Use `true` if the input contract treats blank as null |
| Field omitted from request does not become null | Editor does not iterate over unbound properties | Distinguish missing vs. blank in update logic |
| Words in string lost internal spaces | `charsToDelete` included space character | Remove space from `charsToDelete` when content spaces matter |
| Multiline text lost newlines | `charsToDelete` included `\r\n` | Only delete newlines when truly appropriate |
| Password got trimmed and no longer matches original | Registered for all Strings without checking field nature | Scope by field or separate forms with different rules |
| Name or email after trim differs from raw input | Normalization is a lossy transformation | Store raw value separately if business/audit needs it |
| `@NotNull` suddenly switched from passing to failing | The true editor converted blank String to null before validation | Adjust contract and constraint tests accordingly |
| `@Size(min=1)` missed blank input after editor ran | Null values may be accepted by `@Size` | Combine with `@NotNull` or use `@NotBlank` |
| JSON `@RequestBody` still keeps whitespace | Data deserialized via Jackson, not form property editors | Use a dedicated JSON/DTO normalization strategy |
| One test passes, concurrent requests fail weirdly | Shared stateful `PropertyEditor` instance across threads | Instantiate editors within the proper binder scope |
| NBSP or some Unicode spaces do not disappear | `trim()` does not strip all whitespace code points | Define Unicode policy and use different normalization if needed |

### Beware of "delete all spaces"

Avoid turning:

```java
new StringTrimmerEditor(" ", true)
```

into a default habit. It removes **every ordinary space character** after trimming, even inside meaningful values. On `"Ho Chi Minh"`, the result becomes `"HoChiMinh"`, not `"Ho Chi Minh"`. To trim ends and turn blanks into null, simply use:

```java
new StringTrimmerEditor(true)
```

### Beware of editor lifecycle

`PropertyEditorSupport` stores value state. Reusing one instance sequentially in a demo is fine for observing `setAsText/getValue`. But registering a mutable singleton editor across concurrent binders risks cross-request interference. In web systems, instantiate editors inside `@InitBinder` and never share mutable editor objects across threads.

## 12. Step-by-Step Testing and Debugging

When the editor does not yield expected results, follow this checklist:

1. **Inspect actual input**: is the key present? Is the value `""`, `"   "`, `null`, or completely absent?
2. **Identify data source**: URL-encoded form / query parameter / JSON body / manually constructed object?
3. **Identify binder**: is it the binder for the right model attribute, and was `@InitBinder` invoked?
4. **Inspect editor registration**: `registerCustomEditor(String.class, ...)` or field-path overload? Is another formatter/converter/editor competing?
5. **Check ordering**: was `bind(...)` called before reading values? Was validation triggered if needed?
6. **Observe target**: use getters to check `== null` and String length, not just rendered text.
7. **Compare true and false**: on a blank input, `true` gives `null`, `false` gives `""`.
8. **Check special whitespace**: if data has Unicode whitespace or line breaks, identify character types; `trim()` does not handle all cases.
9. **Verify validation**: `@NotNull`, `@NotEmpty`, `@NotBlank`, and `@Size` yield different outcomes; test both blank and missing.
10. **Verify data safety**: test multiline text, passwords, and fields requiring exact characters before registering type-wide.

You can write unit tests following this test case table:

| Test case | Input | Expected value with true editor |
| --- | --- | --- |
| Normal string | `"  Mai  "` | `"Mai"` |
| Empty string | `""` | `null` |
| Whitespace-only string | `"   "` | `null` |
| String with internal spaces | `" A  B "` | `"A  B"` |
| Literal string "null" | `"null"` | `"null"` |
| `null` input passed to `setAsText` | `null` | `null` |
| Missing key in `MutablePropertyValues` | No key | Preserves previous value on bean |
| Value of field without registered editor | `"   "` | Original string may be preserved |

Distinguish **direct editor unit tests** (testing `setAsText/getValue`), **binder unit tests** (testing `registerCustomEditor + bind`), and **MVC integration tests** (verifying `@InitBinder` is actually invoked and checking post-bind/post-validation values). Discrepancies across these three layers usually pinpoint missing registration, wrong scope, or requests using JSON instead of forms.

## 13. Practice Exercises

Given `UpdateContactForm` with three String properties: `displayName`, `bio`, `rawText`. The form submits:

```text
displayName = "   Linh   "
bio         = "     "
rawText     = "  Keep  these  spaces  "
```

**Tasks:**

1. Predict the result if `new StringTrimmerEditor(true)` is registered for all `String.class`.
2. Predict the result if `false` is used instead of `true`.
3. Propose how to trim only `displayName` and `bio` while **leaving `rawText` unchanged**.
4. If `bio` has `@NotNull`, how do the three configurations differ when `bio` contains only spaces?
5. Why does an omitted `rawText` input key in the request not cause the editor to set that field to null?

**Guided answers:**

- With the true editor for all Strings: `displayName="Linh"`, `bio=null`, `rawText="Keep  these  spaces"`; ends are trimmed while the two internal spaces remain.
- With the false editor for all Strings: `displayName="Linh"`, `bio=""`, `rawText="Keep  these  spaces"`.
- To preserve `rawText`, register the editor **by field**, e.g., `registerCustomEditor(String.class, "displayName", new StringTrimmerEditor(true))` and add a similar registration for `"bio"`.
- `@NotNull` normally treats `bio=null` as invalid, but treats `bio=""` or `"     "` as non-null; to forbid whitespace-only strings regardless of editors, use `@NotBlank`.
- Editors run when a field passes through the appropriate property-binding process; they do not automatically convert properties that have no incoming input.

## 14. Key Takeaways and Official Documentation

Summary:

- `StringTrimmerEditor(true)` = **trim** + **convert empty result to null**.
- `StringTrimmerEditor(false)` = **trim**, while keeping an empty result as `""`.
- `new StringTrimmerEditor(charsToDelete, emptyAsNull)` allows deleting **optional characters anywhere** after trimming; use cautiously.
- **You must register the editor** via `DataBinder.registerCustomEditor(...)` or corresponding binder configuration; Spring does not enable a trimmer for all `String`s by default.
- `@InitBinder` is the common place in Spring MVC to register editors for a specific model attribute.
- An editor is neither validation nor a sanitizer. It transforms data **before form constraints are normally evaluated**.
- Distinguish **null**, **empty string**, **whitespace-only string**, and **omitted field**.

References:

- [Spring Framework — StringTrimmerEditor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/beans/propertyeditors/StringTrimmerEditor.html): constructors, `emptyAsNull`, `setAsText`, and `getAsText`.
- [Spring Framework — Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html): `PropertyEditor` types, binding mechanism, and the fact that StringTrimmerEditor is not registered by default.
- [Spring Framework — DataBinder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/validation/DataBinder.html): `registerCustomEditor`, `bind`, and `BindingResult`.
- [Spring Framework — MVC @InitBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html): registration scope of converters/formatters/property editors for request binders.
- [Jakarta Validation — Built-in Constraints](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html): semantics of constraints such as `@NotNull`, `@NotEmpty`, `@NotBlank`, `@Size`.
