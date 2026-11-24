# Distinguishing Absent Fields, Null, Empty Strings, and Blank Strings in Spring Validation & Data Binding

## 1. Why Must These Four States Be Distinguished?

When receiving input data, the same `displayName` property can fall into four different situations:

1. **Absent/missing field**: the input payload **does not declare the key** `displayName` at all. For example, JSON `{}`.
2. **Present field with null value (explicit null)**: the key exists, but its value is JSON `null` or Java `null`. For example, `{"displayName": null}`.
3. **Present field with empty string**: the actual value is a zero-length string, `""`.
4. **Present field with blank/whitespace-only string**: the string has at least one character, all of which are considered whitespace under the applicable rule, such as `"   "` or a string containing tabs.

All four cases may be unacceptable for a required field, yet **they do not have the same meaning for binding, data updates, defaulting, error reporting, and API contracts**. Merging them too early can prevent the system from knowing whether the user skipped the field, explicitly requested clearing the value, or entered an invalid value.

For example, in a partial profile-update API, `{}` might mean "keep the name unchanged"; `{"displayName": null}` might mean "clear the name"; `{"displayName": ""}` might be a request to set the name to an empty string (usually rejected); and `{"displayName": "   "}` is whitespace-only input (also usually rejected). These are **API-defined rules**, not how Spring automatically interprets every PATCH.

### Source Identification Table

| Input Data | Key Present? | Java/JSON Value at Source | Classification |
| --- | --- | --- | --- |
| `{}` | No | No value to read | `ABSENT` |
| `{"displayName": null}` | Yes | `null` | `NULL` |
| `{"displayName": ""}` | Yes | `""` (length = 0) | `EMPTY` |
| `{"displayName": "   "}` | Yes | String of 3 spaces | `BLANK` |
| `{"displayName": "\t"}` | Yes | String containing a tab character after JSON parsing | `BLANK` |
| `{"displayName": " Linh "}` | Yes | String containing letters and spaces | `VALUE` |
| `{"displayName": 123}` | Yes | Numeric value | **Wrong expected type**, must not arbitrarily be called empty string |

The `EMPTY` and `BLANK` states in the table are made **mutually exclusive**: `EMPTY` means `length == 0`; `BLANK` here means **non-empty and whitespace-only**. In Java, `"".isBlank()` also returns `true`, so check `isEmpty()` first if you want to separate all four states.

## 2. In Java: Null, Empty, and Blank Are Different Checks

For `String value`:

- `value == null`: the reference variable does not point to a `String` object; never call `value.isEmpty()` or `value.isBlank()` before checking for null.
- `value.isEmpty()`: true when `value.length() == 0`, reflecting length only.
- `value.isBlank()` (Java 11+): true when the string is empty **or** all code points in the string are considered whitespace by `Character.isWhitespace`.
- `value.trim().isEmpty()`: depends on `String.trim()` rules (stripping leading/trailing characters with code ≤ U+0020), which does not match `String.isBlank()` for all Unicode characters.
- `value.strip().isEmpty()`: uses whitespace rules based on `Character.isWhitespace` like `isBlank()`; do not assume every character that looks like "whitespace" in every language is classified identically by Java.

**Special case:** The non-breaking space character `U+00A0` looks like a regular space, yet Java's `Character.isWhitespace` does not treat it as ordinary whitespace. When handling multilingual data, define your product's Unicode rules and test specific characters. Do not replace business rules with an arbitrary `trim` call.

### Complete Java 17+ Example: Preserving Key Presence

Create `PresenceDemo.java`:

~~~java
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class PresenceDemo {

    static String classify(Map<String, String> input, String key) {
        if (!input.containsKey(key)) {
            return "ABSENT";
        }

        String value = input.get(key);

        if (value == null) {
            return "NULL";
        }
        if (value.isEmpty()) {
            return "EMPTY";
        }
        if (value.isBlank()) {
            return "BLANK";
        }
        return "VALUE";
    }

    public static void main(String[] args) {
        Map<String, String> input = new HashMap<>();
        input.put("explicitNull", null);
        input.put("empty", "");
        input.put("whitespace", " \t ");
        input.put("withText", " Linh ");

        for (String key : List.of(
                "missing", "explicitNull", "empty", "whitespace", "withText")) {
            System.out.println(key + " => " + classify(input, key));
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 PresenceDemo.java
java PresenceDemo
~~~

Exact stdout:

~~~text
missing => ABSENT
explicitNull => NULL
empty => EMPTY
whitespace => BLANK
withText => VALUE
~~~

The key point is that **both `Map.get("missing") == null` and `Map.get("explicitNull") == null` evaluate to true**. Only `containsKey(...)` distinguishes "key absent" from "key present with null". Using `Map.of(...)` to build a map with null values also does not work because `Map.of` factories disallow null; the example intentionally uses `HashMap`.

The `classify` function represents the state of **source data** while the source still retains presence information. A single `String` property on a JavaBean can only hold `null` or a string; by itself it cannot express "whether the field appeared in the request".

## 3. HTTP Form/Query and JSON Differ at Representation Level

### 3.1. Query Strings and HTML Forms

For a `nickname` parameter in a web application:

| Request | Observed in Parameter Data | Directly Represents JSON Null? |
| --- | --- | --- |
| `GET /profile` | No `nickname` parameter | No |
| `GET /profile?nickname=` | `nickname` present, empty string value | No |
| `GET /profile?nickname` | Normally represented as empty value by HTTP parsers; do not rely on omitting `=` to represent null | No |
| `GET /profile?nickname=%20%20` | Parameter present, value of two spaces after URL decoding | No |
| `GET /profile?nickname=null` | Parameter present, value is the four-character string `"null"` | No |

In `application/x-www-form-urlencoded`, the sender operates with strings and key-value pairs. `null` as understood by Java is not a standard wire-format value for form fields. If the frontend omits the field from the form, it is **missing**; if it sends `nickname=`, it is **empty**. For unchecked checkboxes, browsers may omit the field name; a form control's default submission behavior depends on HTML and frontend code.

Spring MVC can bind form/query parameters with `@RequestParam` or `@ModelAttribute`. Do not confuse `@RequestParam`'s `required = true` with `@NotBlank`: `required` primarily checks parameter presence, while `@NotBlank` checks string content during validation. Type conversion can also turn empty values into null for certain target types, affecting how Spring evaluates "missing after conversion".

Example:

~~~java
@GetMapping("/search")
String search(
        @RequestParam(name = "term", required = false) String term) {
    return term == null ? "NO_VALUE" : "TEXT[" + term + "]";
}
~~~

This is a **snippet placed inside a Spring MVC controller**, requiring imports from `org.springframework.web.bind.annotation` and a Spring Web application. It illustrates an optional String parameter; it does **not** guarantee preserving all source presence details after configured converters/editors run. If exact distinction is needed, inspect the full parameter map at the boundary—such as `@RequestParam MultiValueMap<String, String> params` and `params.containsKey("term")`—before collapsing to a single String.

`@RequestParam(defaultValue = "guest")` applies the default when the parameter **is omitted or has an empty value**, so it intentionally merges missing and empty. `required = false`/`Optional<String>` makes a parameter optional, but does not replace recording "whether the field appeared" for all data types. If an API needs to distinguish them, do not rely on `defaultValue` or `Optional` to preserve all four states.

### 3.2. JSON Has Distinct Null

JSON distinguishes an absent member from a member present with literal `null`. HTTP body:

~~~json
{}
~~~

and:

~~~json
{"nickname": null}
~~~

are two different documents. Likewise:

~~~json
{"nickname": ""}
~~~

differs from:

~~~json
{"nickname": " \t "}
~~~

In the last example, `\t` is validly escaped in JSON; after parsing, the string contains a space and a tab.

In Spring MVC, `@RequestBody` is read by `HttpMessageConverter` (usually via Jackson) and converted into a Java object. If the target is the DTO:

~~~java
public class ProfileRequest {
    private String nickname;

    public String getNickname() {
        return nickname;
    }

    public void setNickname(String nickname) {
        this.nickname = nickname;
    }
}
~~~

then under standard Jackson configuration, if `nickname` starts as null, both `{}` and `{"nickname": null}` can result in `request.getNickname() == null`. At that point, information about **whether the member was present** is lost. If the property has a non-null initial value or Jackson is configured differently (constructors, null-handling, setters), results may vary; do not reduce every DTO to a single fixed rule.

**Also distinguish "no body" from "JSON body `{}`"**: `@RequestBody(required = true)` checks for the presence of the body, which does not mean every member inside the JSON object is required.

### 3.3. Preserving All Four States with JsonNode at the Boundary

When PATCH or API semantics require separating missing from explicit null, JSON can be read as a tree. Example **Spring MVC controller snippet**, requiring Spring Web with Jackson and corresponding imports:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
class InputStateController {

    @PostMapping("/input-state")
    String inputState(@RequestBody JsonNode body) {
        if (body == null || !body.isObject()) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Expected JSON object");
        }

        if (!body.has("nickname")) {
            return "ABSENT";
        }

        JsonNode node = body.get("nickname");
        if (node.isNull()) {
            return "NULL";
        }
        if (!node.isTextual()) {
            return "WRONG_TYPE";
        }

        String text = node.textValue();
        if (text.isEmpty()) {
            return "EMPTY";
        }
        return text.isBlank() ? "BLANK" : "VALUE";
    }
}
~~~

Return value of the method for each JSON object:

| Body | Returned String |
| --- | --- |
| `{}` | `ABSENT` |
| `{"nickname": null}` | `NULL` |
| `{"nickname": ""}` | `EMPTY` |
| `{"nickname": " \t "}` | `BLANK` |
| `{"nickname": "Linh"}` | `VALUE` |
| `{"nickname": 7}` | `WRONG_TYPE` |

Use `body.has("nickname")` to check presence, `node.isNull()` to detect JSON null, and `node.isTextual()` to avoid silently turning numbers/booleans/objects into strings. With Jackson trees, `body.path("nickname")` returns a missing node when the member is absent, whereas `get("nickname")` returns Java null when absent; `NullNode` represents explicit JSON null. Do not use `node.asText()` to classify before checking the type, because conversion can erase the original meaning.

The example consistently uses the property name `nickname` across controller, tests, and API contract so states are not confused by renaming aliases.

## 4. State Can Change When Data Passes Through DataBinder

Spring `DataBinder` supports constructor binding and property binding. In the case of property binding on a mutable JavaBean:

- **Field absent in source**: the binder receives no assignment operation for that property; the object's existing value is typically preserved.
- **Field present with empty string**: if the property type is `String` and no custom editor/converter overrides it, `""` is normally assigned as an empty String.
- **Field containing only whitespace**: remains a String with content unless a sanitization/conversion rule exists.
- **Field with Java null**: sources like `MutablePropertyValues` can contain null; the target object receives null depending on property type and binding settings. This differs from HTML form submissions.
- **Type-conversion error**: for example `age=abc` when the target is an integer; the binder may record a `FieldError` with a code like `typeMismatch`; this is not one of the four valid String states.

Be careful with DTOs that have defaults:

~~~java
class DisplayForm {
    private String nickname = "Anonymous";

    public String getNickname() {
        return nickname;
    }

    public void setNickname(String nickname) {
        this.nickname = nickname;
    }
}
~~~

If the binder only binds properties present in the source data, an omitted `nickname` property keeps `"Anonymous"`. If the source contains `nickname=""`, the setter can receive `""` and overwrite the default. If an empty value is turned into null by a custom editor, the setter can receive null. **Inspect the binder configuration and pre/post-binding values** rather than guessing solely from the `String` type.

### How Does StringTrimmerEditor Change Semantics?

Spring provides `StringTrimmerEditor`, though it is **not automatically registered for every String field**. Example per-controller registration:

~~~java
@InitBinder
void registerTrimming(WebDataBinder binder) {
    binder.registerCustomEditor(
        String.class, new StringTrimmerEditor(true));
}
~~~

This is a snippet inside a Spring MVC controller, requiring `@InitBinder`, `WebDataBinder`, and `org.springframework.beans.propertyeditors.StringTrimmerEditor`. The `true` argument converts strings that are empty **after trimming** into null.

With this editor, depending on the input data:

| Value Before Custom Editor | String Value After Editor |
| --- | --- |
| `""` | `null` |
| `"   "` | `null` |
| `"  Linh  "` | `"Linh"` |
| `"Linh"` | `"Linh"` |

Because of this transformation, a validator receiving **post-binding** data can no longer tell whether the original error was `EMPTY` or `BLANK`. The editor also **does not mark an absent field as explicit null**, and it is not the default mechanism of `@RequestBody` JSON deserialization. `StringTrimmerEditor` has its own trimming rules; do not assume it aligns with every Unicode whitespace definition in validation.

Do not register trimming globally if the system must preserve significant whitespace (such as encrypted/signed payloads, formatted text, or user secrets). Decide per field group or use case, and if exact error reporting for raw input is required, check/record presence before normalization.

## 5. Jakarta Bean Validation Checks Values, Not Presence Automatically

This is the most common source of confusion when using Spring Validation. Constraints run on **the Java value the validator sees**, unaware of whether a JSON property was sent or omitted unless that information was preserved.

For a `String` property, behavior of basic standard annotations:

| Constraint | `null` | `""` | `"   "` | `"Linh"` | Purpose |
| --- | --- | --- | --- | --- | --- |
| `@NotNull` | Invalid | Valid | Valid | Valid | Requires a **non-null value** |
| `@NotEmpty` | Invalid | Invalid | Valid | Valid | Non-null and length greater than 0 |
| `@NotBlank` | Invalid | Invalid | Invalid | Valid | String has at least one non-whitespace character |
| `@Size(min = 1)` | Valid | Invalid | Valid | Valid | Checks length when value is non-null |
| `@Pattern(regexp = "...")` | Typically valid for null per standard constraint | Depends on regex | Depends on regex | Depends on regex | Checks pattern when a string is present |

In the table, "Valid" considers only **the single stated constraint** under matching value conditions; other constraints may still fail. With `@NotBlank`, the exact definition of "blank" in Bean Validation/providers and specific Unicode rules must be tested against your actual provider/version; do not assume `String.trim()` reproduces every case.

Example DTO for a creation request (partial Java class):

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateProfileRequest(
    @NotBlank
    @Size(max = 80)
    String displayName
) {}
~~~

When a Spring application integrates a Bean Validation provider, such as Hibernate Validator:

~~~java
@PostMapping("/profiles")
void create(@Valid @RequestBody CreateProfileRequest request) {
    // Continue only after the request passes input constraints.
}
~~~

The controller snippet is a code fragment needing Web MVC imports and `jakarta.validation.Valid`. If Jackson maps both `{}` and `{"displayName":null}` to `displayName == null`, `@NotBlank` rejects both, yet **cannot indicate whether the cause was missing or explicit null**. `@NotBlank` also rejects `""` and whitespace-only strings. If the API only needs to report "name must not be blank", merging these failures may be acceptable. If the API needs distinct messages for missing/null or PATCH semantics, preserve presence information from the source.

**Important note on triggering validation:** annotations like `@NotBlank` are declarative; Bean Validation requires a provider and an activation point such as `@Valid @RequestBody` / `@Validated` in an appropriate Spring flow, or calling `jakarta.validation.Validator.validate(...)`. Simply calling `new CreateProfileRequest(null)` **does not automatically throw an error**. `@Nullable` is a nullability hint, not a content-validation directive; `Optional<String>` does not by itself solve distinguishing missing from explicit null.

### States and Messages That May Need to Differ

For a creation request, a contract might define:

| Source State | Example Policy | Example Message |
| --- | --- | --- |
| `ABSENT` | Reject | `displayName is required` |
| `NULL` | Reject | `displayName must not be null` |
| `EMPTY` | Reject | `displayName must not be empty` |
| `BLANK` | Reject | `displayName must contain text` |
| `VALUE` | Further validate length limits, allowed characters, domain rules | Accept or return corresponding error |

These are **example API policies**, not mandatory default messages from Jakarta Validator or Spring. A system may choose a single error code for invalid fields as long as the contract is clear and consistent.

## 6. Create, Full Replace, and Partial Update

The four states are especially important when endpoints mutate data.

### 6.1. POST Create

Usually, a required field must have an actual value. You can use `@NotBlank`/`@NotNull` on the DTO; for optional fields, product-defined defaults may apply. If you need to distinguish a client "omitting" from "explicitly sending null" for analytics, auditing, or error messages, read raw JSON/tree/presence before DTO binding erases the difference.

### 6.2. PUT Replace

PUT usually implies replacing the representation state of a resource per the contract. Explicitly specify whether an omitted field in a full representation is treated as an error, defaulted, or ignored. Do not assume `null` and `absent` are equivalent merely because the post-Jackson DTO receives null for both. IDs and server-managed fields should never be modifiable by the client through binding.

### 6.3. PATCH Partial Update

For an application-defined PATCH contract, you might choose:

| Input State | Illustrative Action |
| --- | --- |
| `ABSENT` | Keep existing value unchanged |
| `NULL` | Clear value, if the field permits clearing |
| `EMPTY` | Reject or accept setting an empty string per contract |
| `BLANK` | Reject or normalize per field rules |
| `VALUE` | Validate and update the new value |

Using `Map.containsKey` to preserve the first two states:

~~~java
// Illustrative logic in a service/adapter after parsing JSON into a Map.
if (patch.containsKey("displayName")) {
    Object raw = patch.get("displayName");

    if (raw == null) {
        profile.clearDisplayName(); // Only when the contract permits clearing.
    } else if (raw instanceof String text && !text.isBlank()) {
        profile.setDisplayName(text);
    } else {
        throw new IllegalArgumentException("Invalid displayName");
    }
}
~~~

This snippet depends on the contracts of `profile` and the `patch` variable, and is not a standalone program. Thanks to `containsKey`, the absent-key branch leaves the old value untouched. Do not use `patch.getOrDefault("displayName", null)` if you need to distinguish missing from explicit null, since both paths return null.

If an API uses **JSON Merge Patch (RFC 7396)**, an absent member means no change, whereas `null` means deleting the member per the merge patch standard. If an API uses JSON Patch (RFC 6902), requests are expressed as a list of operations such as `add`, `replace`, and `remove`, so semantics differ. Do not automatically call every HTTP PATCH endpoint a JSON Merge Patch; declare the Content-Type and update rules explicitly.

**Do not use an entity directly as a PATCH DTO**: an entity with nullable properties can no longer separate "not sent" from "sent null", causing accidental data deletion or updates to attributes the client is not authorized to write. Separate the payload, validate present fields, and map to the domain with an allowed-field list.

## 7. Checking in the Right Order

For a field coming from JSON or a map-like source, the sequence can be:

~~~text
Read source data
    |
    +-- key does not exist ---------> ABSENT (keep unchanged / missing error)
    |
    +-- key exists
           |
           +-- null ----------------> NULL (clear / null error)
           |
           +-- wrong type ----------> TYPE ERROR
           |
           +-- String
                 |
                 +-- length == 0 ---> EMPTY
                 |
                 +-- whitespace only -> BLANK
                 |
                 +-- contains non-whitespace characters -> VALUE
                       |
                       +-- check length, pattern, domain rules
~~~

A sound handling policy typically proceeds step by step:

1. **Preserve presence at the intake boundary:** use `JsonNode.has(...)`, `Map.containsKey(...)`, or a three-state wrapper class (missing / explicit null / value). Do not discard presence before establishing semantics.
2. **Check data types:** distinguish JSON numbers/booleans/objects from Strings; do not automatically coerce every type into text unless the API calls for it.
3. **Decide whether to normalize:** trimming, Unicode normalization, and case folding must be intentional per field, not a blanket cure-all.
4. **Apply appropriate constraints:** `@NotBlank` for fields requiring text; `@NotEmpty` when whitespace is accepted but zero length is not; `@NotNull` when an empty string is a valid value.
5. **Apply business rules in service/domain:** such as unique display names, profile edit permissions, and updatable states. Controller constraints do not replace these invariants.
6. **Return errors per contract:** HTTP handling (Spring MVC, WebFlux) translates errors into responses; consumers/CLIs may return their own formats. In audit logs, take care not to store raw secrets or sensitive data.

When using `@Valid @RequestBody`, object-level constraint violations can become `MethodArgumentNotValidException`. When method validation applies due to constraints directly on method parameters, it can be `HandlerMethodValidationException` (modern Spring MVC). For forms/model attributes, `BindingResult` can hold both binding and validation errors. Malformed JSON or deserialization type mismatches can occur **before** Bean Validation is invoked. Therefore, do not label every input error as an "@NotBlank error".

## 8. Testing the Four States at the API Boundary

Testing a field should go beyond "valid" and "invalid". Use at least the following inputs according to the API definition:

| Test Case | JSON Body | Expected When Preserving Raw Presence |
| --- | --- | --- |
| T1 | `{}` | `ABSENT` |
| T2 | `{"displayName": null}` | `NULL` |
| T3 | `{"displayName": ""}` | `EMPTY` |
| T4 | `{"displayName": "   "}` | `BLANK` |
| T5 | `{"displayName": "\t"}` | `BLANK` |
| T6 | `{"displayName": "  An  "}` | `VALUE`, decide trimming per contract |
| T7 | `{"displayName": 5}` | `TYPE ERROR` if contract only accepts String |
| T8 | `{"displayName": false}` | `TYPE ERROR` |
| T9 | `{"displayName": []}` | `TYPE ERROR` |
| T10 | `{"displayName": "\u00a0"}` | Test Unicode per chosen whitespace policy |

T10 contains a non-breaking space via JSON escape. A test should prove your application's Unicode policy rather than assuming it behaves like a regular space.

For forms, also test `?displayName=`, `?displayName=%20%20`, and omitting the parameter completely; if using `@RequestParam(defaultValue=...)`, verify both missing and empty trigger the default as designed. With `StringTrimmerEditor(true)`, test empty and whitespace strings to verify when they turn into null. For PATCH, test two consecutive requests: omitting the field must preserve the existing value, while sending null follows the published clearing policy.

Check **raw unnormalized input**, **post-binding/deserialization values**, and **validation outcomes**. Inspecting only the final DTO is insufficient to confirm that the API preserves the difference between absent and explicit null.

## 9. Common Implementation Mistakes

1. **Using `value == null` to conclude a key is absent.** For maps/trees, check `containsKey`/`has` first. A present key holding null is not equivalent to a nonexistent key.
2. **Calling `isEmpty()` when `value` may be null.** Avoid `NullPointerException` by handling null first before checking length/whitespace.
3. **Using `isBlank()` and labeling empty strings as "blank" in every message.** In Java, `"".isBlank() == true`, so to separate the four cases cleanly, check `isEmpty()` before `isBlank()`.
4. **Confusing `@NotNull` with `@NotBlank`.** `@NotNull` allows `""` and `"   "`. `@NotEmpty` allows `"   "`. For required text fields, typically choose `@NotBlank`.
5. **Using `@Size(min=1)` instead of required.** This constraint allows null through; to reject null, combine it with the appropriate constraint.
6. **Assuming JSON null and missing are always preserved in a DTO.** On nullable String beans, both states usually become Java null. To preserve the distinction, model presence explicitly at parse time.
7. **Enabling `StringTrimmerEditor(true)` and then expecting to report exact empty vs whitespace errors from the bound DTO.** The data has already been transformed; inspect before normalization if the exact error kind matters.
8. **Treating the strings `"null"`, `"undefined"`, or `"N/A"` as Java null.** These are ordinary character strings and carry special meaning only if the contract defines it.
9. **Using `@RequestParam(defaultValue=...)` when presence must be preserved.** The default value applies to missing or empty, merging those two states.
10. **Mixing PATCH varieties.** JSON Merge Patch has specific explicit-null semantics; JSON Patch uses explicit operations; a custom PATCH endpoint does not automatically inherit the same rules.
11. **Normalizing globally without considering business context.** Leading/trailing spaces can be meaningful data; names, passwords, codes, and free text do not all share one rule.
12. **Failing to check wrong types.** JSON numbers, booleans, arrays, and objects are not "empty strings". Return proper type errors instead of coercing to String and masking client bugs.

## 10. Takeaways When Designing an Input Object

- **Presence belongs to the source structure**: use a presence flag, JSON tree, map, or wrapper to represent it when the application must tell states apart.
- **Null is a value**: Java null and JSON null have distinct meanings, yet after DTO binding you may no longer know whether null was explicit or defaulted from an omitted field.
- **Empty is about length**: the string `""` has length 0; it is not automatically null.
- **Blank is about content**: a string can have length > 0 while containing only whitespace; how whitespace is defined depends on the API/Unicode rules chosen.
- **Validation checks post-conversion values**: `@NotNull`, `@NotEmpty`, and `@NotBlank` address different requirements and do not solve field presence by themselves.
- **Binding and normalization can discard information**: define semantics before applying default values, trimming, or mapping into DTOs or entities.
- **The update contract drives behavior**: especially when PATCH must distinguish omitting a field from explicitly sending null.

## Standard References

- [Spring Framework — Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html)
- [Spring Framework — Validation, Data Binding and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html)
- [Spring MVC — @RequestParam](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html)
- [Spring MVC — @RequestBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring MVC — Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework — StringTrimmerEditor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/beans/propertyeditors/StringTrimmerEditor.html)
- [Jakarta Bean Validation specification](https://jakarta.ee/specifications/bean-validation/)
- [RFC 7396 — JSON Merge Patch](https://www.rfc-editor.org/rfc/rfc7396)
- [RFC 6902 — JSON Patch](https://www.rfc-editor.org/rfc/rfc6902)
