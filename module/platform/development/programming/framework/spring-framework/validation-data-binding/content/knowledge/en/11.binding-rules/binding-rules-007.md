# setIgnoreInvalidFields and unreachable paths in Spring DataBinder

## 1. The problem: a field exists yet cannot reach the target object

In Spring Framework, form data can describe **nested property paths** rather than only setting top-level fields. For example:

~~~text
displayName=An
deliveryAddress.city=Ha Noi
quantity=3
~~~

Suppose `ProfileForm` has a `deliveryAddress` field of type `Address`, yet that property is currently `null`. The name `deliveryAddress.city` **is valid** in the Java model: `ProfileForm` has a `deliveryAddress` property and `Address` has a `city` property. However, the binder must traverse a `null` segment along the path to reach `city`.

Three distinct questions arise:

1. Should the binder **automatically instantiate `Address`**?
2. If it cannot instantiate it, should the binder **throw an error or silently ignore** the value for `deliveryAddress.city`?
3. If the field name **does not exist at all** (e.g., typo `deliveryAddres.city`), is it handled like case 2?

`DataBinder.setIgnoreInvalidFields(boolean)` primarily answers **question 2**. To understand it properly, compare it with `setAutoGrowNestedPaths(...)` and `setIgnoreUnknownFields(...)` instead of reading "ignore invalid" and assuming it ignores all invalid data.

## 2. Exact definition of setIgnoreInvalidFields

`org.springframework.validation.DataBinder` provides two methods:

~~~java
binder.setIgnoreInvalidFields(true);
boolean enabled = binder.isIgnoreInvalidFields();
~~~

where `binder` is an instantiated `DataBinder`/`WebDataBinder`. Per the Spring Javadoc:

- **`false` is the default.** Unreachable fields of this kind are not ignored; binding may throw an exception.
- **`true` permits ignoring binding parameters that point to a property existing in the model, when the corresponding part of the object graph does not yet exist or is unreachable**, typically because a nested path segment is `null`.
- This flag takes effect during **property binding** via `bind(PropertyValues)` (setter/field binding). It does not govern constructor binding via `construct(ValueResolver)`.
- This flag **does not apply when reading back** property values via `BindingResult` or a property accessor, so "ignored during bind" does not mean "every read of that same path is safe".

Intuitive example:

~~~java
// Illustrative snippet; ProfileForm and Address classes are defined in Section 6.
ProfileForm form = new ProfileForm(); // deliveryAddress == null
DataBinder binder = new DataBinder(form, "profileForm");
binder.setAutoGrowNestedPaths(false);
binder.setIgnoreInvalidFields(true);
binder.bind(values); // values contains "deliveryAddress.city"
~~~

Here `setAutoGrowNestedPaths(false)` tells the binder **not to auto-create** `Address` when encountering `null`. Because `setIgnoreInvalidFields(true)` is set, the input value for `deliveryAddress.city` is **ignored** in this ignorable null-nested-path case. After binding, `form.getDeliveryAddress()` remains `null`.

Crucially: **ignoring is not success in a business sense**. A client might assume the address was updated, yet the target object never received that value. Therefore, do not enable this flag broadly just to "make exceptions go away".

## 3. Three concepts that must stay separate

| Scenario | Example | Primary cause | Related setting |
| --- | --- | --- | --- |
| **Invalid/unreachable field** | `deliveryAddress.city` exists on the class, yet `deliveryAddress == null` with no auto-grow | Cannot traverse the object graph | `setIgnoreInvalidFields` |
| **Unknown field** | `deliveryAdress.city` misspelled, or `ghost` not on class | No matching target property | `setIgnoreUnknownFields` |
| **Type mismatch** | `quantity=abc` when `quantity` is `Integer` | Target property is reachable, yet string cannot convert to target type | `ConversionService`, `PropertyEditor`/`Formatter`, `BindingResult` |

These three behave **differently**:

- `setIgnoreInvalidFields(true)` does **not** turn `quantity=abc` into a valid `Integer`, nor does it suppress `typeMismatch` errors.
- `setIgnoreUnknownFields(true)` is **not** the setting for a null nested path whose name/type already exists.
- `setAllowedFields(...)` defines **which field names may be bound** as an input-protection policy. It does not replace handling null segments in the object graph.
- `setRequiredFields(...)` checks the presence of field names in input via its own mechanism; merely seeing a field sent does not guarantee that field bound successfully.

Do not treat these four options as interchangeable "error-ignoring switches".

## 4. Interaction with setAutoGrowNestedPaths

Spring's `DataBinder` defaults to `autoGrowNestedPaths = true`. When enabled and the target type permits, the binder can instantiate objects along null path segments to continue binding properties.

Imagine:

~~~java
public class ProfileForm {
    private Address deliveryAddress;

    public Address getDeliveryAddress() {
        return deliveryAddress;
    }
    public void setDeliveryAddress(Address deliveryAddress) {
        this.deliveryAddress = deliveryAddress;
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

These are two illustrative classes that must live in appropriate files or be declared as nested classes; the runnable example in Section 6 puts them in a single Java file.

When a fresh form has `deliveryAddress == null`, the table below summarizes **typical behavior for auto-instantiable JavaBeans**:

| autoGrowNestedPaths | ignoreInvalidFields | When binding `deliveryAddress.city=Ha Noi` |
| --- | --- | --- |
| `true` | `false` (default) | Spring can instantiate `Address`, then bind `city`. No unresolved null path |
| `true` | `true` | Still auto-creates and binds normally; ignore flag has no effect once the path is reachable |
| `false` | `false` | Null path does not auto-grow; typically throws `NullValueInNestedPathException` |
| `false` | `true` | Does not auto-grow; value for the null nested path can be ignored while other valid fields proceed |

Two common sources of confusion:

**First**, `setIgnoreInvalidFields(true)` does not disable auto-grow. If default `autoGrowNestedPaths=true` remains active, Spring can create `Address` and bind the field, so you will not observe the "ignore" behavior. To observe the difference, use an appropriate model and disable auto-grow **before binding**.

**Second**, `autoGrowNestedPaths=true` does not mean Spring can instantiate every object type. Unsuitable constructors, abstract types, non-instantiable collections, visibility restrictions, immutable structures, or throwing setters can still raise other exceptions. The ignore flag is designed for **ignorable null-path failures**, not to swallow arbitrary exceptions from setters, converters, or domain models.

### 4.1. Note on configuration timing

~~~java
DataBinder binder = new DataBinder(form, "profileForm");
binder.setAutoGrowNestedPaths(false);
binder.setIgnoreInvalidFields(true);
// Only now call binder.bind(...)
~~~

Configure `setAutoGrowNestedPaths` before the binder initializes `BindingResult`/the accessor or performs binding steps. Some Spring versions actively reject changing auto-grow after the binder has initialized because it would cause inconsistent behavior. In Spring MVC, place these settings in `@InitBinder` so the framework applies them before binding.

## 5. What is actually ignored inside PropertyAccessor?

Underneath `DataBinder`, `BeanWrapper`/`PropertyAccessor` processes `PropertyValues`. For null nested paths during `setPropertyValues`, the accessor layer can raise `NullValueInNestedPathException`.

In modern Spring lines, the key logic is:

~~~text
for each propertyValue to bind:
    try setPropertyValue(...)
    if NotWritablePropertyException:
        if ignoreUnknown = true then ignore
        else throw exception
    if NullValueInNestedPathException:
        if ignoreInvalid = true then ignore
        else throw exception
    if collectible PropertyAccessException:
        accumulate corresponding conversion / write error
after loop:
    if accumulated errors exist, throw PropertyBatchUpdateException
~~~

This is **descriptive pseudocode**, not literal source code. `DataBinder` catches `PropertyBatchUpdateException` and converts collectible errors into `BindingResult` errors via `BindingErrorProcessor`. Other `BeansException`s—such as an unignored null nested path—can escape `bind(...)` directly.

### 5.1. Why can BindingResult report no errors?

If you configure:

~~~java
binder.setAutoGrowNestedPaths(false);
binder.setIgnoreInvalidFields(true);
~~~

and the only issue is an allowed-to-ignore null path, `binder.getBindingResult().hasErrors()` can be **false**. No `FieldError` is created merely because a field was skipped by ignore-invalid. Nor should you inspect `getSuppressedFields()` to count fields ignored this way: suppressed fields relate to **allowed/disallowed field filtering**, a separate mechanism.

This is crucial when building REST or form APIs: a handler that checks only `BindingResult.hasErrors()` may proceed and save an object missing an update the user actually sent.

### 5.2. Ignore-invalid does not mean ignore all nested path errors

Misspelled property names can raise `NotWritablePropertyException`; valid fields whose setters intentionally throw can raise other exceptions; mistyped values can raise `TypeMismatchException` or conversion errors. Do not enable `setIgnoreInvalidFields(true)` expecting the framework to swallow **all** those exceptions.

Your behavior choice should reflect the **actual error type** and business semantics of the form.

## 6. Runnable Java 17+ example with DataBinder

The program below needs no servlet container or Spring Boot. It uses standalone `DataBinder` to demonstrate:

1. Defaults `ignoreInvalidFields = false` and `autoGrowNestedPaths = true`.
2. Auto-grow disabled, ignore-invalid enabled: null nested path is ignored **yet top-level fields still bind**.
3. Both disabled: `NullValueInNestedPathException` occurs.
4. Auto-grow enabled: nested object is created and field binds successfully.
5. Mistyped value still produces a binding error even with ignore-invalid enabled.
6. `setAllowedFields` works as a whitelist distinct from ignore-invalid.

The example pins Spring Framework `7.0.9` so the code does not depend on a shifting "latest" version. Uses JDK 17+ and Maven. Outputs are verified logically against the Spring API; depending on environment, Maven may print extra tool logs.

### 6.1. Structure

~~~text
invalid-fields-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── InvalidFieldsDemo.java
~~~

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>invalid-fields-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>7.0.9</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` brings in the Spring modules used for `DataBinder` and JavaBean binding. In a Spring Boot project with dependency management, use the Spring versions provided by the Boot BOM rather than arbitrarily mixing module versions.

### 6.3. src/main/java/InvalidFieldsDemo.java

~~~java
import org.springframework.beans.MutablePropertyValues;
import org.springframework.beans.NullValueInNestedPathException;
import org.springframework.validation.DataBinder;

public class InvalidFieldsDemo {

    public static class Address {
        private String city;

        public Address() {
        }

        public String getCity() {
            return city;
        }

        public void setCity(String city) {
            this.city = city;
        }
    }

    public static class ProfileForm {
        private Address deliveryAddress;
        private String note;
        private Integer quantity;

        public ProfileForm() {
        }

        public Address getDeliveryAddress() {
            return deliveryAddress;
        }

        public void setDeliveryAddress(Address deliveryAddress) {
            this.deliveryAddress = deliveryAddress;
        }

        public String getNote() {
            return note;
        }

        public void setNote(String note) {
            this.note = note;
        }

        public Integer getQuantity() {
            return quantity;
        }

        public void setQuantity(Integer quantity) {
            this.quantity = quantity;
        }
    }

    private static MutablePropertyValues values(String... pairs) {
        if (pairs.length % 2 != 0) {
            throw new IllegalArgumentException("Field/value pairs required");
        }
        MutablePropertyValues pvs = new MutablePropertyValues();
        for (int i = 0; i < pairs.length; i += 2) {
            pvs.add(pairs[i], pairs[i + 1]);
        }
        return pvs;
    }

    public static void main(String[] args) {
        // 1. Default values before customizing the binder.
        DataBinder defaults = new DataBinder(new ProfileForm(), "profileForm");
        System.out.println("default.ignoreInvalid="
                + defaults.isIgnoreInvalidFields());
        System.out.println("default.autoGrow="
                + defaults.isAutoGrowNestedPaths());

        // 2. No auto-grow, yet ignore null nested paths.
        ProfileForm optional = new ProfileForm();
        DataBinder lenient = new DataBinder(optional, "profileForm");
        lenient.setAutoGrowNestedPaths(false);
        lenient.setIgnoreInvalidFields(true);
        lenient.bind(values(
                "deliveryAddress.city", "Ha Noi",
                "note", "Accepted"
        ));
        System.out.println("lenient.addressNull="
                + (optional.getDeliveryAddress() == null));
        System.out.println("lenient.note=" + optional.getNote());
        System.out.println("lenient.hasErrors="
                + lenient.getBindingResult().hasErrors());
        System.out.println("lenient.suppressed="
                + lenient.getBindingResult().getSuppressedFields().length);

        // 3. No auto-grow and do not ignore null paths.
        ProfileForm strictForm = new ProfileForm();
        DataBinder strict = new DataBinder(strictForm, "profileForm");
        strict.setAutoGrowNestedPaths(false);
        strict.setIgnoreInvalidFields(false);
        try {
            strict.bind(values("deliveryAddress.city", "Ha Noi"));
            System.out.println("strict.exception=none");
        } catch (NullValueInNestedPathException ex) {
            System.out.println("strict.exception="
                    + ex.getClass().getSimpleName());
        }

        // 4. Auto-grow creates Address even when ignore-invalid = false.
        ProfileForm grown = new ProfileForm();
        DataBinder growing = new DataBinder(grown, "profileForm");
        growing.setAutoGrowNestedPaths(true);
        growing.setIgnoreInvalidFields(false);
        growing.bind(values("deliveryAddress.city", "Ha Noi"));
        System.out.println("grow.city="
                + grown.getDeliveryAddress().getCity());
        System.out.println("grow.hasErrors="
                + growing.getBindingResult().hasErrors());

        // 5. Type mismatch does not disappear with ignore-invalid.
        ProfileForm invalidNumber = new ProfileForm();
        DataBinder mismatch = new DataBinder(invalidNumber, "profileForm");
        mismatch.setIgnoreInvalidFields(true);
        mismatch.bind(values("quantity", "not-a-number"));
        System.out.println("mismatch.quantity="
                + invalidNumber.getQuantity());
        System.out.println("mismatch.fieldError="
                + mismatch.getBindingResult().hasFieldErrors("quantity"));

        // 6. Whitelist: a blocked field is not "ignored invalid".
        ProfileForm restricted = new ProfileForm();
        DataBinder allowlisted = new DataBinder(restricted, "profileForm");
        allowlisted.setAllowedFields("note");
        allowlisted.bind(values(
                "note", "Approved",
                "quantity", "99"
        ));
        System.out.println("allowlist.note=" + restricted.getNote());
        System.out.println("allowlist.quantity="
                + restricted.getQuantity());
        System.out.println("allowlist.suppressed="
                + allowlisted.getBindingResult().getSuppressedFields().length);
    }
}
~~~

### 6.4. Running and checking stdout

In the `invalid-fields-demo` directory:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=InvalidFieldsDemo
~~~

Expected output from the program's `System.out.println` (excluding Maven logs):

~~~text
default.ignoreInvalid=false
default.autoGrow=true
lenient.addressNull=true
lenient.note=Accepted
lenient.hasErrors=false
lenient.suppressed=0
strict.exception=NullValueInNestedPathException
grow.city=Ha Noi
grow.hasErrors=false
mismatch.quantity=null
mismatch.fieldError=true
allowlist.note=Approved
allowlist.quantity=null
allowlist.suppressed=1
~~~

Case-by-case breakdown:

- **Default:** `isIgnoreInvalidFields() == false`; `isAutoGrowNestedPaths() == true` on a standard `DataBinder`.
- **Lenient:** because auto-grow is off, `deliveryAddress` remains null. `deliveryAddress.city` is skipped by ignore-invalid, yet `note` is top-level and still receives `Accepted`. `hasErrors=false` and `suppressed=0` emphasize that ignore-invalid is **not** allowed-fields filtering.
- **Strict:** `deliveryAddress.city` cannot traverse `deliveryAddress == null` when auto-grow is off. `NullValueInNestedPathException` is thrown and caught in the program.
- **Grow:** `Address` has a no-arg constructor and valid getter/setter, so Spring instantiates it, traverses to `city`, and assigns `Ha Noi`; ignore-invalid is unnecessary.
- **Mismatch:** `quantity` is reachable, yet `not-a-number` cannot convert to `Integer`. The conversion failure is recorded in `BindingResult`/`FieldError`, and `quantity` remains null.
- **Allowlist:** only `note` is permitted to property-bind. `quantity` in the request is blocked by the whitelist, the target stays unchanged, and the field name is recorded in `getSuppressedFields()`.

Useful practical point: the program avoids mixing all configs into a single binder, which would make it hard to tell **which configuration caused which outcome**.

### 6.5. What the sample code does not claim

- It does not claim every nested object type auto-instantiates: constructors, generic types, collections/indexes, access modes, and custom accessors can all alter results.
- It does not claim every property binding failure throws the same exception class: the program only catches the **deliberately constructed null nested path case**.
- It does not claim ignore-invalid skips mistyped fields, non-existent fields, or domain errors inside setters.
- It does not claim stdout proves Maven ran in the current environment; run the command above to verify against your exact dependencies and JDK.

## 7. Distinguishing setIgnoreUnknownFields

`setIgnoreUnknownFields(boolean)` handles **field names with no counterpart on the target class**, not null paths of a **defined** field.

For example:

~~~text
deliveryAddress.city=Da Nang  # Valid nested path by name, yet Address may be null
deliveryAdress.city=Da Nang   # "Address" is misspelled: property does not exist
unknownFlag=on               # No unknownFlag field on ProfileForm
~~~

| Configuration | Default value | Primary case handled |
| --- | --- | --- |
| `setIgnoreInvalidFields(false)` | `false` | Does not swallow unreachable null nested path errors |
| `setIgnoreInvalidFields(true)` | Not default | Ignores eligible null nested paths during `bind` |
| `setIgnoreUnknownFields(true)` | `true` | Ignores field names absent from target |
| `setIgnoreUnknownFields(false)` | Not default | Can throw `NotWritablePropertyException` when request has non-existent fields |

If you want clients notified when they misspell a field name, consider `setIgnoreUnknownFields(false)` **in an appropriate property-binding flow**, while preparing exception handling. If an API intentionally permits extra unused fields, you may keep the default while remembering those fields are not bound.

A common mistake is seeing "ignore" in both settings and turning both on to reduce errors. The result can be **clients sending wrong inputs and the server silently dropping them**, making debugging difficult or leaving application state inconsistent.

### 7.1. getSuppressedFields is not a list of all ignored fields

`BindingResult.getSuppressedFields()` helps detect fields submitted yet stripped by the binder's allowed/disallowed configuration:

~~~java
binder.setAllowedFields("displayName", "note");
binder.bind(values);
String[] suppressed = binder.getBindingResult().getSuppressedFields();
~~~

This snippet assumes `values` is already constructed. If a field is excluded by policy, Spring can record its name in suppressed fields. **Never** use that list to conclude no fields were ignored by `setIgnoreInvalidFields(true)` or `setIgnoreUnknownFields(true)`. Neither ignore mode is required to create suppressed entries.

## 8. Usage in Spring MVC with @InitBinder

For HTML form or request parameter inputs, `@ModelAttribute` typically uses `WebDataBinder`. You can configure it in a controller:

~~~java
// Illustrative controller snippet; ProfileForm and view/service must exist.
@Controller
class ProfileController {

    @InitBinder("profileForm")
    void configureForm(WebDataBinder binder) {
        binder.setAutoGrowNestedPaths(false);
        binder.setIgnoreInvalidFields(false);
        binder.setIgnoreUnknownFields(false);
        binder.setAllowedFields(
                "displayName", "deliveryAddress.city", "note");
    }

    @PostMapping("/profiles")
    String submit(
            @Valid @ModelAttribute("profileForm") ProfileForm form,
            BindingResult result) {

        if (result.hasErrors()) {
            return "profile-form";
        }
        profileService.save(form);
        return "redirect:/profiles";
    }
}
~~~

This code **only illustrates binder configuration**; it will not compile without imports, service/view components, and the model. Note one remaining design nuance: `setAutoGrowNestedPaths(false)` and `ignoreInvalidFields=false` can cause a request containing `deliveryAddress.city` to throw an **exception** when `deliveryAddress` is null, rather than necessarily creating a `FieldError` and entering the `result.hasErrors()` branch.

Accordingly, there are at least two sensible design strategies:

**Strategy A — Pre-build the proper object graph before binding.** For instance, `ProfileForm` initializes `deliveryAddress = new Address()` while keeping `autoGrowNestedPaths=false`. The binder does not need to instantiate `Address` and can assign `city`. Suitable when the form always models a valid `Address`.

**Strategy B — Allow controlled auto-grow.** Keep `setAutoGrowNestedPaths(true)` so the framework creates nested objects, while restricting allowed fields and using clear DTO/form objects. Watch the impact of array/list indexes and `autoGrowCollectionLimit` if the form has client-controllable collections.

**Strategy C — Deliberately ignore nested fields for absent branches.** You can use `setIgnoreInvalidFields(true)`, but only when the business convention explicitly states "if the object branch does not exist yet, its fields are not updated"; the UI/handler must understand this and never return an "updated" message for a field not actually applied.

For APIs managing critical data, **prefer explicit error reporting or explicit input mapping** rather than silently dropping a requested edit.

### 8.1. Do not confuse @ModelAttribute with @RequestBody

~~~java
@PostMapping("/profiles/json")
void updateJson(@Valid @RequestBody UpdateProfileRequest request) {
    service.update(request);
}
~~~

This is a non-standalone controller method example. JSON `@RequestBody` is typically deserialized by `HttpMessageConverter`/Jackson, **not** via `DataBinder.bind(PropertyValues)` for parameters like `deliveryAddress.city`. `setIgnoreInvalidFields` is not a flag to ignore null nested JSON properties or unknown JSON properties. For JSON, configure DTOs, Jackson, Bean Validation, and domain mapping per your contract.

Also remember: `DataBinder.construct(...)` constructor binding is a separate mechanism and **does not** use `setIgnoreInvalidFields` the way property binding does.

## 9. Null paths, collection indexes, object graphs, and security boundaries

### 9.1. A nested field can be declared yet absent at runtime

Paths such as:

~~~text
customer.address.city
lines[2].product.code
preferences.theme.name
~~~

all require traversing each object/list segment. Failures can stem from:

- An intermediate object being `null`.
- An uninitialized collection, or an out-of-bounds index when auto-growth is disabled or exceeds the limit.
- An element type that cannot be instantiated, an immutable collection, or a custom collection not behaving like a standard Java `List`.
- A path valid on the class yet inaccessible under the active accessor mode.
- Setter/constructor logic or constraints preventing completion.

Only **some** of these cases produce `NullValueInNestedPathException` that ignore-invalid can skip. For out-of-bounds indexes, unknown properties, failing accessors, and conversion failures, inspect version-specific exception/API behavior. Never assume "every unreachable path is ignored when true".

### 9.2. Relationship with autoGrowCollectionLimit

`setAutoGrowCollectionLimit(int)` caps array/list auto-expansion in supported Spring modes. It is not an alternate toggle for ignore-invalid. If `lines[100].sku` exceeds the limit or cannot grow, the outcome depends on collection type, index, access mode, and settings. **Do not assume** `setIgnoreInvalidFields(true)` turns every out-of-range index into a safely ignored field.

For large requests or client-supplied paths, limit payload/body size, path depth, field counts, element counts, and modifiable fields. `@Size` validation runs **after binding**, so it does not replace resource bounds during data parsing.

### 9.3. Ignore flags are not authorization policies

`setIgnoreInvalidFields` is designed to decide **how to handle unreachable paths**, not who is permitted to change which fields. Enabling `true` does not prevent mass assignment into internal fields if those fields actually have valid, reachable paths.

For example, `role=ADMIN` on an entity with a valid `setRole(...)` can still bind if no allowlist exists. Stronger guardrails are:

1. Dedicated **input-only** DTOs/form objects with only writable fields.
2. `setAllowedFields(...)` when using property binding.
3. Caller permission checks and domain invariants in the service layer.
4. Blocking or explicitly reporting unexpectedly skipped fields.
5. Testing requests that submit unusual fields and null nested paths.

Never equate "no binding errors" with "the request executed everything intended" when parameters were ignored.

## 10. How to test systematically

When writing tests for a controller/form object, check the **object state after binding** alongside exceptions and `BindingResult`, rather than checking HTTP status alone.

| Test case | Setup | Verifiable conclusion |
| --- | --- | --- |
| Existing nested field, null branch, auto-grow off | `ignoreInvalid=false` | Path error is not silently ignored |
| Existing nested field, null branch, auto-grow off | `ignoreInvalid=true` | Nested input ignored; independent fields still bind; no `FieldError` by default |
| Existing nested field, null branch, auto-grow on | Type has suitable constructor | Object branch can instantiate and field binds |
| Invalid numeric type | `quantity=abc` | `hasFieldErrors("quantity")` reflects conversion error |
| Non-existent field | `ignoreUnknown=true/false` | Behavior differs from invalid-nested; do not confuse field names |
| Field blocked by allowlist | `setAllowedFields("note")` | Field does not bind and can appear in `getSuppressedFields()` |
| Submitted field was ignored | `ignoreInvalid=true` | UI/service does not assume the update succeeded |
| Nested JSON request | `@RequestBody` | Jackson settings and validation tested separately, not inferred from `DataBinder.bind` |

These checks can run as `DataBinder` unit tests like the program in Section 6. To test real Spring MVC, use `MockMvc` with form parameters, exception resolvers, and appropriate views/models. HTTP outcomes depend on handlers, global exception handlers, and specific configuration: there is no unconditional rule that "ignore-invalid false = HTTP 400".

In production, log malformed field structure safely and avoid logging personal data or secrets. Never print raw `rejectedValue` or full request bodies directly to logs without a masking policy.

## 11. Common mistakes and how to fix them

1. **Enabling ignore-invalid to hide all errors.** Categorize unknown paths, null nested paths, type mismatches, and domain errors before choosing a policy.
2. **Forgetting auto-grow is on by default.** For instantiable objects, null nested paths will auto-grow, hiding the effect of ignore-invalid. Test both settings.
3. **Thinking true implies @Valid.** `setIgnoreInvalidFields` handles binding, does not run `Validator`, and does not verify data validity.
4. **Thinking ignored fields always create a FieldError.** An ignored null nested field may leave no error in `BindingResult`. Check both the object and application policy.
5. **Thinking getSuppressedFields lists all ignored fields.** That list ties to allowed/disallowed field filtering, not a full log of every skipped value.
6. **Enabling ignoreUnknown instead of ignoreInvalid.** A misspelled property differs from an existing property whose path is uninitialized.
7. **Not handling exceptions in strict mode.** `NullValueInNestedPathException` can escape `bind(...)` rather than entering `BindingResult`.
8. **Reading nested fields after bind assuming ignore still applies.** This flag does not protect reads through `getBindingResult()` or property accessors.
9. **Letting clients bind directly into entities.** Ignore rules do not replace DTOs, allowlists, permission checks, or domain invariants.
10. **Using identical configuration for forms and JSON.** `@ModelAttribute`/property binding differs from `@RequestBody`/Jackson; handle each entry point appropriately.
11. **Leaving nested branches unexpectedly null.** If a nested part must always exist, initialize it in constructors/model factories or design an explicit DTO instead of silently dropping input.
12. **Treating an ignore flag as DoS protection.** It does not limit field count, path depth, collection indexes, or byte size.
13. **Disabling auto-grow after the binder has initialized.** Configure it early, when constructing the binder or inside `@InitBinder`.
14. **Skipping tests on the active framework version.** Behavior for nested collections, custom types, constructors, and exception policies can differ; write regression tests for real application paths.

## 12. Project adoption checklist

Before enabling `setIgnoreInvalidFields(true)`, answer:

- Which fields are genuinely **optional** when a nested object branch does not exist yet?
- If the client sends such a field and the server skips it, what will the API report to avoid confusion?
- Should the null branch be **initialized** before binding instead of ignored?
- Is the controller using `@ModelAttribute`/form binding or `@RequestBody` JSON?
- What is the current `autoGrowNestedPaths` setting?
- Is there a whitelist of editable fields? Should suppressed fields trigger errors?
- Which null-nested errors must be business errors, and which can be safely skipped?
- Do tests verify the bound object, `BindingResult`, and exceptions?
- Are element counts and input depth bounded?

A pragmatic design rule: **if the user sent a value meant to apply, do not silently discard it**. Enable ignore-invalid only for flows that explicitly define "if the nested branch does not exist yet, its input may be skipped". In ordinary forms, initializing valid object graphs, using clear DTOs, or returning explicit errors is easier to operate.

## Summary

`setIgnoreInvalidFields(true)` is an option to **ignore certain property-binding parameters pointing to validly named yet unreachable fields**, typically due to nulls along nested paths. It is **off by default**, does not create nested objects, does not turn type errors into valid data, and does not replace `setIgnoreUnknownFields`, `setAllowedFields`, or validation. `autoGrowNestedPaths` determines whether the binder tries to fill null branches to keep going; if it instantiates the object, ignore-invalid may never need to activate.

Distinguishing the three outcomes—**bound**, **ignored**, and **failed with error/exception**—is the key to avoiding silent input loss when using `DataBinder`.

## References

- Spring Framework 6.2 — `DataBinder` Javadoc (setIgnoreInvalidFields, ignoreUnknownFields, autoGrowNestedPaths): https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Framework 7.0 — `DataBinder` Javadoc: https://docs.spring.io/spring-framework/docs/7.0.x/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Framework — Data Binding: https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html
- Spring Framework — JavaBeans and property paths: https://docs.spring.io/spring-framework/reference/core/validation/beans-beans.html
- Spring Framework — `AbstractPropertyAccessor.setPropertyValues` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/AbstractPropertyAccessor.html
- Spring Framework — `@InitBinder` in Spring MVC: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html
