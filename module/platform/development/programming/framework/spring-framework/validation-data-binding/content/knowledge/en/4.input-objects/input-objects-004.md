# Distinguishing Primitive Types from Wrapper Types When Data Is Missing

When Spring Framework receives data from a form, query parameter, or JSON, what matters is not only **which Java type the data is converted into**, but also **whether the application can tell if that field was omitted**. Two declarations that look very similar—`int quantity` and `Integer quantity`, `boolean enabled` and `Boolean enabled`—can lead to different business decisions when an input omits a field.

The scope of this lesson is **input objects (input DTOs/forms)** in Spring Data Binding and validation. Three scenarios must be distinguished: *not providing the field*, *providing a real value (including 0 or false)*, and *providing null or an empty string*. Exact behavior also depends on the intake channel, binder/converter configuration, and JSON deserializer.

## 1. Fundamental Differences in Java

A primitive type is a Java data type that directly stores a value from its domain; a wrapper type is a reference type that, in addition to holding a value, can also hold `null`.

| Primitive Type | Wrapper Type | Default Value of an Uninitialized **Instance Field** | Meaning When Used as Input |
| --- | --- | --- | --- |
| `int` | `Integer` | `0` / `null` | `int` cannot represent "not provided"; `Integer` can be `null`. |
| `long` | `Long` | `0L` / `null` | Same issue for quantities, IDs, limits, and numeric durations. |
| `double` | `Double` | `0.0d` / `null` | `0` may be a meaningful value; a wrapper separates it from an absent field. |
| `boolean` | `Boolean` | `false` / `null` | `false` can be an explicit user choice, distinct from "not selected". |
| `char` | `Character` | `'\u0000'` / `null` | The default NUL character is not a reliable indicator of missing data. |

Example on a newly instantiated JavaBean with no initializers and before binding:

~~~java
class Input {
    int count;          // 0
    Integer countBox;   // null
    boolean confirmed;  // false
    Boolean confirmBox; // null
}
~~~

**The default values in the table apply to instance fields and array elements.** A local primitive variable is not automatically assigned a default value for immediate use by Java; it must be assigned before being read. Furthermore, a field already initialized by a constructor, field initializer, or other logic retains that value if the binder does not overwrite it. Therefore, "missing data" does **not always mean** "a primitive field equals 0"; 0 is simply the default value of a primitive field on a newly instantiated object without explicit initialization.

### Why Can't `0` and `false` Stand In for `null`?

Consider two requests sent to an order-creation API:

- Request A **does not send** the `quantity` property.
- Request B explicitly sends `quantity=0`.

If both bind onto an `int quantity` field of a new JavaBean, both can end up holding `0`. Looking only at `quantity`, you can no longer tell whether the user sent 0 or sent nothing at all. With `Integer quantity`, under standard property binding, A leaves `null` while B holds `0`, making required-input checks straightforward.

Similarly, if a checkbox or JSON sends `false`, that can be a valid choice. A `boolean` field holds `false` even before receiving any data; in a form requiring a yes/no answer, only `Boolean` can represent the unanswered state (`null`).

## 2. How Does Spring Bind When a Field Is Absent from Source Data?

During **setter/property binding** onto an existing JavaBean, `DataBinder` only updates properties that have corresponding input values. A property **absent** from the binding value set normally **keeps its current state**:

~~~text
Input data without "quantity"
                     |
                     v
            DataBinder / WebDataBinder
                     |
            Does not assign that property
                     |
           +---------+---------+
           |                   |
    int quantity        Integer quantity
   (newly created)       (newly created)
           |                   |
           0                  null
~~~

This differs from a request that **includes the field** with an empty string or invalid type. In that case Spring may invoke a converter, assign `null` to a wrapper, or raise a `typeMismatch` error for a primitive, depending on the field type and conversion mechanism. Do not conclude that "every empty string becomes 0" or "every empty string becomes null".

If the JavaBean already held `quantity = 5` before binding, a request omitting `quantity` can leave it as 5, even if the type is `Integer`. **The post-bind value alone is not proof of whether a field was present in the request.**

## 3. Java 17+ Program Demonstrating Spring `DataBinder`

The standalone example below uses two DTOs with the same property names but different types. Sample inputs are placed into `MutablePropertyValues`, similar to the name/value pairs a binder receives from a form. There is no web server in this example.

Directory structure:

~~~text
primitive-wrapper-input/
├── pom.xml
└── src/main/java/example/PrimitiveWrapperInputDemo.java
~~~

Create `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>primitive-wrapper-input</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>example.PrimitiveWrapperInputDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Create `src/main/java/example/PrimitiveWrapperInputDemo.java`:

~~~java
package example;

import java.util.Map;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

public class PrimitiveWrapperInputDemo {

    public static class PrimitiveInput {
        private int quantity;
        private boolean enabled;

        public int getQuantity() {
            return quantity;
        }

        public void setQuantity(int quantity) {
            this.quantity = quantity;
        }

        public boolean isEnabled() {
            return enabled;
        }

        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }
    }

    public static class WrapperInput {
        private Integer quantity;
        private Boolean enabled;

        public Integer getQuantity() {
            return quantity;
        }

        public void setQuantity(Integer quantity) {
            this.quantity = quantity;
        }

        public Boolean getEnabled() {
            return enabled;
        }

        public void setEnabled(Boolean enabled) {
            this.enabled = enabled;
        }
    }

    private static <T> T bind(T target, Map<String, String> values) {
        DataBinder binder = new DataBinder(target);
        binder.bind(new MutablePropertyValues(values));
        BindingResult result = binder.getBindingResult();

        if (result.hasErrors()) {
            throw new IllegalStateException("Bind failed: " + result);
        }
        return target;
    }

    public static void main(String[] args) {
        var absentPrimitive = bind(new PrimitiveInput(), Map.of());
        var absentWrapper = bind(new WrapperInput(), Map.of());

        var explicitPrimitive = bind(
                new PrimitiveInput(),
                Map.of("quantity", "0", "enabled", "false"));
        var explicitWrapper = bind(
                new WrapperInput(),
                Map.of("quantity", "0", "enabled", "false"));

        var positiveWrapper = bind(
                new WrapperInput(),
                Map.of("quantity", "3", "enabled", "true"));

        System.out.println("primitive/absent: "
                + absentPrimitive.getQuantity() + ", "
                + absentPrimitive.isEnabled());
        System.out.println("wrapper/absent: "
                + absentWrapper.getQuantity() + ", "
                + absentWrapper.getEnabled());
        System.out.println("primitive/explicit: "
                + explicitPrimitive.getQuantity() + ", "
                + explicitPrimitive.isEnabled());
        System.out.println("wrapper/explicit: "
                + explicitWrapper.getQuantity() + ", "
                + explicitWrapper.getEnabled());
        System.out.println("wrapper/positive: "
                + positiveWrapper.getQuantity() + ", "
                + positiveWrapper.getEnabled());
    }
}
~~~

With **JDK 17+**, Maven, and dependency download access if not yet cached, run from `primitive-wrapper-input`:

~~~bash
mvn -q compile exec:java
~~~

Output printed by the program:

~~~text
primitive/absent: 0, false
wrapper/absent: null, null
primitive/explicit: 0, false
wrapper/explicit: 0, false
wrapper/positive: 3, true
~~~

The first two lines illustrate **omitted fields**. The next two lines illustrate **the user explicitly sending 0 and false**. The primitive type yields the exact same post-bind state in both scenarios; the wrapper type separates them when the initial field is `null`. The final line shows that wrappers hold values normally when data is provided.

This example uses Spring `DataBinder` with **property binding on new JavaBeans**; it does not represent all behaviors of JSON deserialization, constructor binding, field initializers, custom editors, or form checkbox markers.

## 4. Distinguishing "Absent", "Empty", `null`, and Wrong Type

This is the most bug-prone area when connecting forms/REST endpoints to Java DTOs:

| Actual Input | Meaning | Notable Outcome |
| --- | --- | --- |
| No `quantity` key in bound value set | Absent field | Property binder usually does not assign: primitive keeps existing value (default `0` on a new bean), wrapper keeps existing value (default `null`). |
| `quantity=0` present | User supplied zero | Both `int` and `Integer` can hold `0` after successful conversion. |
| `enabled=false` present | User selected false | Both `boolean` and `Boolean` can hold `false`; wrapper distinguishes it from prior `null`. |
| `quantity=` present (empty string from form) | Field present without numeric value | Numeric wrapper may convert to `null`; primitive may raise a bind/conversion error. Always check `BindingResult`. |
| `quantity=abc` present | Value cannot be converted to a number | Typically a type-conversion error; do not treat the remaining default value as valid input. |
| JSON sends `"quantity": null` | Explicit `null` sent | Wrapper receives `null` under standard config; primitive handling depends on Jackson and null-coercion settings. |
| JSON omits `quantity` | Property does not appear | With normal POJO setter binding, keeps the field's default; constructors/records and custom deserializers may behave differently. |

### JSON with `@RequestBody`: Be Careful with Primitives

`@RequestBody` normally reads JSON via Jackson in Spring MVC. Under common Jackson settings, JSON `null` into a primitive property of a JavaBean can become the primitive default (`0`, `false`). Depending on configuration, Jackson can reject this; for example, enabling `DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES` rejects **explicit JSON null** for primitives.

Do not assume that enabling that option also rejects JSON **missing the key entirely**. Checking property presence, constructor rules, and deserializer behavior follow separate mechanisms. With beans using standard setters, a property missing from JSON is normally not assigned.

When a JSON request has malformed syntax or an unreadable type, Spring may throw `HttpMessageNotReadableException` before the controller runs. That **does not mean** validation ran and `BindingResult` reported an error.

### Forms with `@ModelAttribute`: Mind Checkboxes

HTML normally **does not submit a checkbox field when it is unchecked**. If you bind onto a newly created `boolean enabled`, you may receive `false` without knowing whether the user actively sent false. Some Spring form binding mechanisms add a field marker (default prefix `_`) to indicate the checkbox was present on the form and support resetting the value when unchecked. Field markers can cause the binder to actively assign a value rather than simply leaving an absent field untouched.

Therefore, to distinguish "unanswered" from "answered no", design the data transport and required-answer rules explicitly; **merely switching `boolean` to `Boolean` is not enough** if the HTML/client layer collapses both states before submitting.

### Query Parameters Differ from DTO Properties

For a single controller parameter:

~~~java
// Spring MVC snippet, not a standalone program.
@GetMapping("/search")
public String search(
        @RequestParam(required = false) Integer page) {
    return page == null ? "not-specified" : "page-" + page;
}
~~~

`@RequestParam(required = false) Integer page` can receive `null` when the parameter is omitted. Conversely, `@RequestParam int page` is required by default: Spring can report a missing-parameter error **before** the method body executes. If you always want a default, declare `@RequestParam(defaultValue = "1") int page` explicitly; the default value is applied when the parameter is absent or empty according to the annotation's semantics.

This does not contradict the `0` default of an `int` field in a DTO: **direct parameter resolution** and **JavaBean property binding** are two different processing paths.

## 5. Bean Validation: How to Catch "Not Sent" Errors?

Do not expect `@NotNull` to catch an omitted primitive field. A primitive always holds a value once the object is constructed, so `@NotNull` on `int` or `boolean` **does not help detect an absent field**. If the user must supply a positive quantity, a clear declaration is typically:

~~~java
// Illustrative DTO; requires Jakarta Bean Validation + provider.
public class CreateOrderForm {
    @jakarta.validation.constraints.NotNull
    @jakarta.validation.constraints.Positive
    private Integer quantity;

    @jakarta.validation.constraints.NotNull
    private Boolean newsletterEnabled;

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }

    public Boolean getNewsletterEnabled() {
        return newsletterEnabled;
    }

    public void setNewsletterEnabled(Boolean newsletterEnabled) {
        this.newsletterEnabled = newsletterEnabled;
    }
}
~~~

The rules have distinct effects:

- `@NotNull Integer quantity`: rejects `null`, such as when the property remains `null` because it was not bound.
- `@Positive Integer quantity`: rejects `0` and negative numbers; per Bean Validation, `null` is considered valid by `@Positive` alone, so combine it with `@NotNull` if the field is required.
- `@NotNull Boolean newsletterEnabled`: forces the user to supply true **or false** when the binding mechanism preserves the distinction between an absent field and a submitted field.
- If business logic requires the value **to be true**, use `@AssertTrue`; however, this annotation does not reject `null` on its own either, so add `@NotNull` when you need both presence and acceptance.

Putting `@NotNull` on `boolean` does not enforce selection. Putting `@Min(1)` or `@Positive` on primitive `int` can catch the default `0` as an error, yet still **cannot distinguish** a user omitting the number from a user intentionally sending `0`. That may suffice when both are invalid inputs; it does not work when different errors or business rules apply to the two cases.

### The Controller Must Block the Invalid Branch

~~~java
// Snippet inside a Spring MVC @Controller that already has orderService and view.
@PostMapping("/orders")
public String create(
        @Valid @ModelAttribute("order") CreateOrderForm form,
        BindingResult result) {

    if (result.hasErrors()) {
        return "orders/new";
    }

    // Validation has verified quantity and newsletterEnabled are non-null.
    orderService.create(
            form.getQuantity(),
            form.getNewsletterEnabled());
    return "redirect:/orders";
}
~~~

In Spring Boot 3.x, Bean Validation annotations reside in `jakarta.validation.*` and require a Bean Validation provider, typically provided by `spring-boot-starter-validation`. `@Valid` must be triggered at the appropriate entry point; merely instantiating a Java DTO without running validation means annotations **do not automatically produce errors**.

`BindingResult` must stand **immediately after** the corresponding `@Valid @ModelAttribute` parameter. When errors exist, the `return` branch runs before `orderService.create(...)`. When using `@Valid @RequestBody`, validation and error reporting have their own details; without an adjacent `BindingResult` parameter, Spring MVC typically reports errors via `MethodArgumentNotValidException` and exception handling.

## 6. Which Type Should You Choose for Each Purpose?

There is no rule stating "every DTO must use wrappers". The right type depends on whether the **unprovided state** carries meaning in the contract.

| Field Purpose | Usually Appropriate Type | Reason |
| --- | --- | --- |
| Required quantity that must be positive | `@NotNull @Positive Integer quantity` | Separates missing/`null` from `0`, validating both presence and value. |
| Optional quantity where service chooses default | `Integer quantity` | `null` expresses "unspecified"; `0` is an explicitly submitted value. |
| Required "Yes/No" flag where both are valid | `@NotNull Boolean enabled` | Three states prior to validation: unselected, true, false. |
| Flag that must be agreed to as true | `@NotNull @AssertTrue Boolean consent` | Forces an answer and requires the answer to be true. |
| Internal state already defaulting to false without needing presence | `boolean active` | `false` is a valid model value in its own right. |
| Internal counter that always has a number and is never absent | `int attempts` | No need for a wrapper just to allow a useless `null`. |
| JSON PATCH: missing = keep, `null` = clear, value = change | Type representing **both presence and value** | `Integer`/`Boolean` alone cannot represent all three states. |

### Partial Update (PATCH) Case

This is a scenario where wrappers **are still not enough**. Consider two JSON payloads:

~~~json
{}
~~~

and:

~~~json
{"nickname": null}
~~~

If both deserialize into the same DTO with a `String nickname` field defaulting to `null`, reading `nickname == null` cannot tell whether the caller wants to **keep nickname unchanged** or **clear nickname**. The same applies to `Integer age` or `Boolean enabled`.

To support a PATCH contract properly, track **whether the field appeared** separately. Approaches include reading a `JsonNode` and calling `has("nickname")` (distinct from `hasNonNull(...)`), using a patch-specific state type, or using a deserializer mechanism that marks presence. Business logic must then branch explicitly:

~~~text
Field absent     -> Keep existing data unchanged
Field = null     -> Clear/reset if the contract allows
Field = value    -> Validate and update value
~~~

Do not use a wrapper's `null` to arbitrarily infer either of the first two actions. For PUT/create, a missing field may be rejected; for PATCH, a missing field usually means keep unchanged per contract, so validation must follow the operation as well.

## 7. Common Mistakes

**Mistake 1 — Treating `0` as a sign of missing data.**

~~~java
int quantity = form.getQuantity();
if (quantity == 0) {
    // Cannot tell whether the user omitted it or explicitly sent 0.
}
~~~

If `0` is a valid value, inferring "not entered" wrongly rejects valid data. If `0` is invalid, `@Positive` can block both, yet the exact root cause still cannot be distinguished with a primitive.

**Mistake 2 — Using `@NotNull` on a primitive to require input.**

~~~java
@NotNull
private int quantity; // this annotation does not detect an absent field
~~~

The usual fix is `@NotNull Integer quantity` combined with an appropriate value constraint. Do not change the type and forget to update getters/setters, mappers, and unboxing sites.

**Mistake 3 — Unboxing a wrapper before validation runs.**

~~~java
Integer quantity = form.getQuantity();
int units = quantity; // NullPointerException if quantity == null
~~~

Only convert to a primitive after verifying the value is non-null, such as after validation succeeds or after applying an explicit default:

~~~java
int units = quantity == null ? 1 : quantity;
~~~

The last line is only valid if **the contract allows a default of 1**; never silently substitute a default for a required input.

**Mistake 4 — Defining a field default and still expecting to detect absence.**

~~~java
private Integer quantity = 0; // A missing field still leaves quantity == 0.
~~~

A wrapper does not preserve an absence signal if the application pre-initializes it. If you must require the user to send a value, do not initialize a value that causes `@NotNull` to always pass.

**Mistake 5 — Ignoring conversion errors and continuing business logic.**

The string `"abc"` cannot convert to `Integer`, and an empty string may fail conversion to a primitive depending on the converter. Even if the target property retains its default, the binder may have recorded a `FieldError`. Always check `BindingResult.hasErrors()` before calling the service.

**Mistake 6 — Assuming JSON null, an absent field, and an empty string are always identical.**

Different input forms travel through different conversion paths. Test `{}`, `{"quantity":null}`, `{"quantity":0}`, and form input `quantity=` separately. Re-test whenever you add custom converters, field markers, constructor binding, or change Jackson settings.

**Mistake 7 — Reusing a creation DTO for partial updates.**

A `null` wrapper might mean "not entered" in create, yet mean "clear" or "unchanged" in patch. Use per-use-case DTOs/contracts and preserve field presence state.

## 8. Test Input Behavior, Not Just Java Types

At a minimum, test the cases below at the exact entry point in use (`DataBinder`, `@ModelAttribute`, `@RequestParam`, or `@RequestBody`), because they do not share the same binding path:

| Test Case | With Required `Integer quantity` | With Required `Boolean enabled` |
| --- | --- | --- |
| Omit field completely | Reports required error if using `@NotNull` without initializer/default | Reports required error if using `@NotNull` and absence state is preserved |
| Send actual `null` (JSON) | Reports required error or request-reading error depending on config | Reports required error or request-reading error depending on config |
| Send `0` / `false` | `0` rejected if using `@Positive`, not rejected by `@NotNull` alone | `false` valid if user only needs to choose Yes/No |
| Send `1` / `true` | Valid for `@NotNull @Positive` | Valid for `@NotNull` |
| Send empty string / wrong type | Check conversion error and actual message | Check conversion/field marker behavior for the intake channel |

At the controller level, verify both **HTTP status/field error response** and that **the service is not invoked when input is invalid**. For a create endpoint requiring `quantity`, include a test proving a request without `quantity` does not create an order—do not test only `quantity = -1`. For PATCH, verify distinguishing absent from null by asserting the persisted data state.

## 9. Practical Rules to Remember

1. When you need to represent **not provided**, prefer wrappers such as `Integer`, `Long`, and `Boolean` in input DTOs, and do not pre-initialize defaults if `null` is meant to signal absence.
2. When data is required, use real validation: `@NotNull` to verify value-level presence, combined with `@Positive`/`@Min` or `@AssertTrue` when content checks are needed. Always run validation and inspect results before business logic.
3. Do not use `0` or `false` as a missing-data sentinel when either can be a valid choice.
4. Distinguish **absent property**, **empty value**, **JSON null**, and **conversion error** for the exact request-intake path implemented. Do not generalize from one binding style to all others.
5. For **three-state PATCH**, track field presence separately; a wrapper alone is not enough.
6. Use primitives at the input boundary only when the contract genuinely permits a natural default, or when the resolution/validation mechanism ensures distinguishing absent input is unnecessary.

Spring and Jakarta reference documentation for implementation verification:

- [Spring Framework — Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html)
- [Spring Framework — Validation, Data Binding and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html)
- [Spring MVC — `@ModelAttribute` Method Arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring MVC — `@RequestParam` Method Arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html)
- [Spring MVC — `@RequestBody` Method Arguments](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Jakarta Validation — Built-in Constraint Definitions](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html#builtinconstraints)
