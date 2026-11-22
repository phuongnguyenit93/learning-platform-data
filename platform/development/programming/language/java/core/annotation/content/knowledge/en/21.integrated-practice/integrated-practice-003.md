# Integrated Practice: Using @Repeatable to Describe Multiple Validation Rules in Java

A field may simultaneously require multiple validation conditions: not blank, reaching a minimum length, matching a regular expression, belonging to a set of values, and so on. Java supports describing **multiple occurrences of the same annotation type** on a single declaration through `@Repeatable`. As a result, instead of creating a new annotation for every combination of conditions, we can define a **unified rule model** and attach multiple configuration records to the same element.

Example of the idea:

```java
@Check(rule = Rule.NOT_BLANK, message = "must not be blank")
@Check(rule = Rule.MIN_LENGTH, min = 4, message = "at least 4 UTF-16 units")
public String username;
```

This is an **illustrative declaration snippet**; it requires defining `Check`, `Rule`, and an appropriate container. Both annotations belong to the same type `Check`, yet **each application carries its own parameters**.

This practice exercise builds the complete workflow:

1. Design the rule annotation `@Check` and the container annotation `@Checks`.
2. Declare metadata using `@Repeatable(Checks.class)`, `@Target(FIELD)`, and `@Retention(RUNTIME)`.
3. Apply multiple `@Check` annotations to each field of a registration form.
4. Read all rules completely using `Field.getAnnotationsByType(Check.class)`.
5. Execute a simple validator, collect all errors, and print results verified with Java 17.
6. Analyze limitations, misconfigurations, rule ordering, retention, extensibility, and what needs to be tested before production use.

**Core principle distinction:** `@Repeatable` only permits and represents multiple annotations of the same type. **It does not run validation automatically**. It is the code that reads the annotations and implements the rules that determines whether a value is valid or not.

## 1. Why Are Repeated Annotations Needed for Multiple Rules?

Suppose user information needs to satisfy:

- `username` must not be empty or contain only whitespace.
- `username` must have at least four UTF-16 code units according to `String.length()`.
- `pin` must not be blank.
- `pin` must consist of exactly three ASCII digits from `0` to `9`.

There are multiple API options. One approach is to attach separate annotations:

```java
@NotBlank
@MinLength(4)
String username;
```

This is only a **conceptual illustration**; `NotBlank` and `MinLength` are not two standard built-in annotations that work automatically in core Java.

Another approach is to describe conditions using a single common annotation:

```java
@Check(rule = Rule.NOT_BLANK, message = "required")
@Check(rule = Rule.MIN_LENGTH, min = 4, message = "too short")
String username;
```

The latter approach has advantages when all rules genuinely belong to **a unified processing mechanism**: the same error-reporting policy, the same processor/validator, and the same metadata lifecycle. Each `@Check` is an independent configuration.

However, repeatable annotations are not always the best choice. If rules have very different semantics and arguments, specialized annotations such as `@NotBlank`, `@Pattern`, and `@Size` may be clearer and more type-safe. This exercise chooses a single general annotation to focus on **the repeatable mechanism and its consumer**.

## 2. Designing the Repeated Annotation and Container

An annotation is allowed to appear multiple times when it has `@Repeatable(Container.class)`. The specified container must have a `value()` element returning **an array of the repeated annotation**.

We will use:

```java
enum Rule {
    NOT_BLANK,
    MIN_LENGTH,
    MATCHES
}

@Repeatable(Checks.class)
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface Check {
    Rule rule();
    int min() default 0;
    String regex() default "";
    String message();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface Checks {
    Check[] value();
}
```

This is a **condensed illustrative declaration**; it requires importing `Repeatable`, `Retention`, `RetentionPolicy`, `Target`, and `ElementType`. The complete program with imports will be provided in Section 5.

The elements of `Check`:

| Element | Meaning | Required or has default? |
| --- | --- | --- |
| `rule()` | Selects the check type `NOT_BLANK`, `MIN_LENGTH`, or `MATCHES` | Required |
| `min()` | Minimum length when using `MIN_LENGTH` | `default 0` |
| `regex()` | Regular expression when using `MATCHES` | `default ""` |
| `message()` | Message when violated | Required |

`@Checks` is a **container annotation**, not a rule set with its own algorithm. The compiler uses it when it needs to represent multiple `@Check` annotations on the same element.

### Specifying Target and Retention

Because the example processes annotations directly on **fields** using runtime reflection:

```java
@Repeatable(Checks.class)
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface Check { /* the elements listed above */ }

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface Checks { /* Check[] value(); */ }
```

This is **illustrative syntax**, not intended as a standalone runnable file. The container and repeated annotation share the same target `FIELD` and retention `RUNTIME`. In this exercise, `@Inherited` is not needed, because the `@Inherited` mechanism is designed for querying annotations **on a class via its superclass**, and does not automatically propagate field annotations.

We can add `@Documented` to both definitions if we want the configuration annotations to appear in the API documentation. If the repeated type has `@Documented`, the container **must also** have `@Documented` according to Java rules.

### Important Requirements for the Container

According to the Java Language Specification (JLS) §9.6.3, the container for an annotation `T` must satisfy:

1. Declare exactly `T[] value();`.
2. Any element other than `value()`, if present, must have a default value.
3. The retention of the container is no shorter than that of the repeated annotation: `SOURCE ≤ CLASS ≤ RUNTIME`.
4. The target of the container must be compatible with the target of the repeated annotation according to JLS rules. It does not have to be identical in every case, but using the same `FIELD` is the clear choice here.
5. If the repeated annotation has `@Documented`, the container also has `@Documented`.
6. If the repeated annotation has `@Inherited`, the container also has `@Inherited`.

An **intentionally incorrect** example that does not compile:

```java
@Repeatable(BadChecks.class)
@interface BadCheck {}

@interface BadChecks {
    String[] value(); // Wrong: must be BadCheck[].
}
```

Merely adding `@Repeatable` is not enough if the container is invalid. The compiler will reject such a repeatable definition.

## 3. When Writing Two @Check Annotations Consecutively, What Does the Compiler Store?

Suppose:

```java
@Check(rule = Rule.NOT_BLANK, message = "required")
@Check(rule = Rule.MIN_LENGTH, min = 4, message = "too short")
String username;
```

This is an **illustrative declaration** using the `Check` definition above. According to JLS §9.7.5, when multiple annotations of the same repeated type appear in a valid context, the compiler may represent them as an **implicitly declared container annotation**:

```java
@Checks({
    @Check(rule = Rule.NOT_BLANK, message = "required"),
    @Check(rule = Rule.MIN_LENGTH, min = 4, message = "too short")
})
String username;
```

The two representations above illustrate equivalent metadata for those rules. When there are multiple consecutive repeated annotations, the left-to-right order is preserved in the container's `value()` array.

A surprising consequence for reflection:

- `field.getDeclaredAnnotation(Check.class)` **does not necessarily return a rule** when there are two `@Check` annotations, because the rules may exist **indirectly inside `@Checks`**.
- `field.getDeclaredAnnotation(Checks.class)` can return the container.
- `field.getDeclaredAnnotationsByType(Check.class)` and `field.getAnnotationsByType(Check.class)` are designed to retrieve **each `Check` annotation inside the container**, in the exact order.
- With **a single** `@Check` attached directly, `getDeclaredAnnotation(Check.class)` can return that annotation immediately.

In a validator that needs to process **all rules**, do not use a call that returns **a single** annotation such as `getAnnotation(Check.class)` to try to collect the full configuration. Prefer the `getAnnotationsByType` or `getDeclaredAnnotationsByType` API.

### Do Not Arbitrarily Mix the Repeated Type with the Manual Container

When using both `@Check` and `@Checks` at the same location, valid and invalid cases depend on counts and JLS §9.7.5 rules. To keep the API easy to understand, choose **one consistent style**, usually multiple consecutive `@Check` annotations, rather than forcing users to write the container manually.

## 4. Designing the Validator: From Annotations to Behavior

Metadata does not execute on its own. For `@Check` annotations to produce real value, we must have a consumer:

```text
Registration object
        |
        v
Reflection: retrieve declared Field objects
        |
        v
Sort fields so output is easy to test
        |
        v
getAnnotationsByType(Check.class)
        |
        v
For each @Check:
  NOT_BLANK  -> String.isBlank()
  MIN_LENGTH -> String.length() >= min
  MATCHES    -> Pattern.matches(regex, text)
        |
        v
Collect each violation into List<String>
        |
        v
Return the list; caller decides how to display/handle it
```

Several design choices are fixed for the example:

- Apply only to **fields of type `String`** and demonstrate on **a single specific form class**. This is the contract of the demo, not an inherent limitation of `@Repeatable`.
- `NOT_BLANK` treats `null` or a string consisting entirely of whitespace according to `String.isBlank()` as invalid.
- `MIN_LENGTH` uses `String.length()`, meaning the number of **UTF-16 code units**, which does not necessarily equal the number of user-perceived characters (*grapheme clusters*). Complex Unicode may require a different rule.
- `MATCHES` uses `Pattern.matches()`, requiring a **full-string match** against the regular expression.
- If the value is `null`, all three check types in the demo report a violation. A framework might want a different rule, such as skipping null for `MIN_LENGTH` so that `NOT_BLANK` handles it separately.
- The validator **collects all errors**, rather than stopping at the first error. A single field can produce multiple messages.
- To keep stdout deterministic, the demo **sorts field names** before checking; in practice, one should not rely on the order returned by `Class.getDeclaredFields()`.

These decisions must be clearly documented in the annotation's Javadoc and tested together with the consumer. Java does not enforce any specific interpretation of `NOT_BLANK` or `MATCHES`.

## 5. Complete Java 17 Example: Multiple Rules on the Same Field

Create a single file **`RepeatableRulesDemo.java`** with the complete contents below. All necessary classes, enums, and annotation types are in one file, and there is only one `public` class matching the filename.

```java
import java.lang.annotation.*;
import java.lang.reflect.Field;
import java.util.*;
import java.util.regex.Pattern;

enum Rule { NOT_BLANK, MIN_LENGTH, MATCHES }

@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@Repeatable(Checks.class)
@interface Check {
    Rule rule();
    int min() default 0;
    String regex() default "";
    String message();
}

@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface Checks {
    Check[] value();
}

class Registration {
    @Check(rule = Rule.NOT_BLANK, message = "must not be blank")
    @Check(rule = Rule.MIN_LENGTH, min = 4,
           message = "at least 4 UTF-16 units")
    public final String username;

    @Check(rule = Rule.NOT_BLANK, message = "must not be blank")
    @Check(rule = Rule.MATCHES, regex = "\\d{3}",
           message = "exactly 3 digits")
    public final String pin;

    Registration(String username, String pin) {
        this.username = username;
        this.pin = pin;
    }
}

public class RepeatableRulesDemo {
    static List<String> validate(Registration form)
            throws IllegalAccessException {
        List<String> problems = new ArrayList<>();
        Field[] fields = Registration.class.getDeclaredFields();
        Arrays.sort(fields, Comparator.comparing(Field::getName));

        for (Field field : fields) {
            String value = (String) field.get(form);

            for (Check check : field.getAnnotationsByType(Check.class)) {
                boolean invalid = switch (check.rule()) {
                    case NOT_BLANK -> value == null || value.isBlank();
                    case MIN_LENGTH -> value == null || value.length() < check.min();
                    case MATCHES -> value == null ||
                            !Pattern.matches(check.regex(), value);
                };

                if (invalid) {
                    problems.add(field.getName() + ": " + check.message());
                }
            }
        }
        return problems;
    }

    public static void main(String[] args) throws Exception {
        Field field = Registration.class.getDeclaredField("username");

        System.out.println("rules-on-username=" +
                field.getAnnotationsByType(Check.class).length);
        System.out.println("direct-check=" +
                (field.getDeclaredAnnotation(Check.class) != null));
        System.out.println("container=" +
                (field.getDeclaredAnnotation(Checks.class) != null));

        System.out.println("invalid:");
        for (String message : validate(new Registration("ab", "9x"))) {
            System.out.println(message);
        }

        System.out.println("valid-errors=" +
                validate(new Registration("alice", "123")).size());
    }
}
```

Compile and run with **JDK 17 or higher**:

```bash
javac --release 17 -encoding UTF-8 RepeatableRulesDemo.java
java RepeatableRulesDemo
```

**Exact** stdout, verified with `javac` and `java`:

```text
rules-on-username=2
direct-check=false
container=true
invalid:
pin: exactly 3 digits
username: at least 4 UTF-16 units
valid-errors=0
```

### Output Explanation

1. `rules-on-username=2`: the `username` field has two `@Check` rules; `getAnnotationsByType(Check.class)` retrieves both.
2. `direct-check=false`: when two `@Check` annotations are at the same location, the compiler represents them using the `@Checks` container, so an individual `Check` is not **directly present** on the field according to the rules of `getDeclaredAnnotation()`.
3. `container=true`: `@Checks` is the implicitly declared annotation containing the two rules.
4. `invalid:`: preparing to print all violations for the form with `username="ab"` and `pin="9x"`.
5. `pin: exactly 3 digits`: `"9x"` does not match the full regex `\\d{3}`; it is still not rejected by `NOT_BLANK` because it is not blank.
6. `username: at least 4 UTF-16 units`: `"ab"` only has `String.length()==2`, which is less than `min=4`; `NOT_BLANK` for this field still passes.
7. `valid-errors=0`: the data `("alice", "123")` satisfies all rules, so the error list is empty.

Because the fields are sorted by name, `pin` is checked before `username`. Within each field, the repeated rules are processed in the declaration order returned by reflection from the container.

**Note:** the fields in the demo are `public final String` to simplify reading via `Field.get(form)`. In real projects, fields are usually `private`; a framework must have a valid access strategy that accounts for Java module access and security constraints, or switch to reading properties/getters with target `METHOD` if the contract specifies that.

### Checking the Empty String Case Further

If we run the same validator with:

```java
validate(new Registration("", ""));
```

This is an **illustrative expression** placed in the context of the demo and does not print results by itself. The error list will include both the `NOT_BLANK` condition and the length/regex conditions, because the current validator does not skip other rules after encountering an empty string.

This shows that the checks are **independent**. If a product only wants to display one error per field, a separate orchestration policy such as **fail-fast per field** or rule prioritization is needed; do not assume `@Repeatable` will pick the first error for you.

## 6. Comparing Ways to Retrieve Annotations from a Field

Suppose `Registration.username` has two `@Check` annotations as in the demo.

| Reflection API | Result and Meaning |
| --- | --- |
| `field.getAnnotation(Check.class)` | `null` in the case where two rules are wrapped in a container |
| `field.getDeclaredAnnotation(Check.class)` | `null` because there is no `Check` directly present |
| `field.getAnnotation(Checks.class)` | The container holding the two rules |
| `field.getAnnotationsByType(Check.class)` | An array of two `Check` annotations after unpacking the container |
| `field.getDeclaredAnnotationsByType(Check.class)` | Also retrieves the two rules directly on the field in the demo |
| `field.getDeclaredAnnotations()` | An array of directly present annotations, which includes `Checks` |

For **fields**, `getAnnotationsByType()` and `getDeclaredAnnotationsByType()` typically produce the same result regarding inheritance mechanisms, because `@Inherited` does not copy field annotations from a parent class to a shadowed field in a subclass. However, a validator must still decide **the set of fields to traverse**: `getDeclaredFields()` only returns fields declared directly on the class being inspected, and does not automatically return fields from all superclasses.

Another question is "can we retrieve annotations from a getter with the same name?". Not automatically. Annotations on a **field** are distinct from annotations on a **method**. If attaching annotations to getters is needed, support `@Target(METHOD)` and traverse `Method` objects according to a clear contract.

### Distinguishing Repeated Annotations from Manual Container Declaration

```java
@Checks({
    @Check(rule = Rule.NOT_BLANK, message = "must not be blank"),
    @Check(rule = Rule.MIN_LENGTH, min = 4, message = "too short")
})
String username;
```

This is an **illustrative alternative snippet** for two consecutive `@Check` annotations, with the container written explicitly. Annotation users usually prefer the repeated syntax because it is shorter; consumers should use APIs that also support the indirect container form.

In a system that requires compatibility with older library versions, changing the reading API from `getAnnotation(Check.class)` to `getAnnotationsByType(Check.class)` can be a mandatory step after an annotation becomes repeatable.

## 7. Controlling the Semantics and Validity of Rule Configurations

Having `@Repeatable` does not mean the compiler validates all relationships among the elements of `@Check`.

For example, the compiler accepts the following values in terms of data types:

```java
@Check(rule = Rule.MIN_LENGTH, min = -5,
       message = "invalid length")
@Check(rule = Rule.MATCHES, regex = "[",
       message = "invalid regex")
String value;
```

This is an **illustrative declaration with business-logic misconfigurations**, though all elements have valid Java types. It is not recommended for use.

The issues:

- `MIN_LENGTH` with `min=-5` has nonsensical semantics for a length.
- `MATCHES` with `regex="["` is an invalid regular expression; `Pattern.matches()` can throw `PatternSyntaxException` at runtime.
- `NOT_BLANK` with `min` or `regex` supplied creates a redundant configuration that easily causes confusion.
- `message=""` may fail to inform the user of the cause of the error.

In a real project, there are two layers of validation that should be performed:

1. **Validate annotation definitions at compile time:** an annotation processor can read `@Check`, verify `min >= 0`, ensure the regex compiles, and check the combination between `rule` and its corresponding elements, then emit a compiler diagnostic right at the invalid declaration.
2. **Validate configuration before processing runtime data:** the framework builds a validated rule set and precompiles `Pattern` instances, and only afterward accepts user data. Avoid letting metadata errors mix with data errors.

Annotation syntax only constrains the element types allowed by Java; default values are not a built-in validation policy of the compiler.

### Document the Length Rule

In the demo, `String.length()` measures **UTF-16 code units**. For many emojis or combining-mark characters, the number of code units can differ from the number of characters the user visually sees.

If the product contract states "at least four displayed characters", you must choose the corresponding counting method (for example, by Unicode grapheme clusters with an appropriate tool), rather than taking `String.length()` and assuming it is always the number of displayed characters. This is a rule implementation decision and is not directly related to `@Repeatable`.

### Do Not Use Annotations as an Arbitrary Data Store

Java annotation elements only accept primitives, `String`, `Class`, enums, annotations, or one-dimensional arrays of the allowed types. They do not accept arbitrary types such as `List<Rule>`, lambdas, mutable objects, or `null`.

Therefore, to express a complex rule, consider elements of the valid types or have the annotation reference **a registered policy** via an enum, class token, or identifier. Avoid stuffing an entire dynamic validator program into annotations.

## 8. Extensibility Design: Should You Add to the Rule Enum or Create New Annotation Types?

The `@Check(rule=Rule.X,...)` pattern has a limitation: the `min()`, `regex()`, and `message()` elements always exist even when not every rule uses them. An increasing number of rules can turn the annotation into a hard-to-maintain "catch-all configuration".

Two directions for extension:

**Approach A — keep a single repeated annotation with an enum.** Reasonable when all conditions belong to the same category and the parameter set is small. The consumer uses a `switch` for each `Rule`, and a processor can block meaningless configuration combinations.

**Approach B — use multiple specialized annotation types.** For example, `@NotBlank`, `@MinLength(4)`, `@Matches("\\d{3}")`. Suitable when each rule has very different elements and needs separate validation. Each annotation type can also be marked `@Repeatable` if a field needs multiple instances of **the same kind** of rule, such as multiple different patterns.

There is no need to make every validation repeatable. If a field only has **one** `@NotBlank` rule and **one** `@MinLength` rule, those are two different annotation types; Java already allows using both side by side **without `@Repeatable`**. `@Repeatable` specifically solves **repeating the same annotation type** on a single declaration or type-use.

### Repeatable or an Annotation Containing an Array?

Replacing with a single annotation:

```java
// Illustrative declaration for an alternative design:
@interface RuleSet {
    Rule[] value();
}
```

A `@RuleSet({Rule.NOT_BLANK, Rule.MIN_LENGTH})` only carries an enum list and cannot directly carry `min=4` or a separate message for each rule. If each rule requires independent parameters, repeatable `@Check` or an array of **nested annotations** is usually more natural.

If you only store a simple set of flags with no additional parameters, an enum array can be simpler and easier to maintain than a repeatable container.

## 9. Rules on Ordering, Duplication, and Conflicts

When an element has multiple annotations, relying on order can carry business meaning. However, how rules are applied should be **explicitly specified**.

- **Annotation order:** The JLS defines left-to-right ordering for annotations contained in the implicitly generated container. With `getAnnotationsByType()` on a field as in the demo, the rule order is preserved accordingly. Nevertheless, iterating over `getDeclaredFields()` does not guarantee field order; the demo must sort them to obtain deterministic output.
- **AND condition:** the current example requires every rule to pass; any failing rule produces a violation. If business requirements call for OR, priorities, or conditional rules, the validator must model them explicitly.
- **Duplicate rules:** two `@Check(rule=NOT_BLANK)` annotations on the same field may be syntactically valid yet meaningless, and could even generate two messages. The decision on whether to forbid duplicates belongs to the consumer or processor.
- **Conflicting rules:** `MIN_LENGTH(min=10)` combined with `MAX_LENGTH(max=5)` (if added to the enum) is contradictory metadata. Java does not detect this automatically without a consumer.
- **Error severity:** some rules might be warnings while others are errors. The annotation can add a `Severity` enum, but clear display guidelines and priority logic are required.
- **Reading from superclasses:** the demo processes a single concrete class and its declared fields. If you want to apply rules from a superclass, you must traverse the classes in the hierarchy and decide how to handle shadowed fields and merging order. `@Inherited` does not propagate field annotations in this way.

A reliable validator system should have **tests for rule combinations**, not just tests for each rule in isolation.

## 10. Common Mistakes

| Misconception or Anti-pattern | Correct Practice |
| --- | --- |
| Attaching two annotations of the same type while forgetting `@Repeatable` | Define a valid repeated annotation and container |
| Declaring container `String[] value()` for `@Check` | The container must have `Check[] value()` |
| Using only `getAnnotation(Check.class)` | Use `getAnnotationsByType(Check.class)` to read multiple rules |
| Using `@Target(TYPE)` for an annotation placed on a field | Need `@Target(FIELD)` or another target matching the placement |
| Forgetting `@Retention(RUNTIME)` when reflection is needed | Both the repeated type and container must have the appropriate retention |
| Expecting Java to validate data automatically upon seeing `@Check` | There must be an actual consumer reading and executing the rules |
| Ignoring null/blank | Define behavior for null and whitespace-only strings |
| Assuming `String.length()` is always the number of displayed characters | Accurately document the counting unit; consider Unicode |
| Using unchecked regexes | Validate configuration and catch `PatternSyntaxException` at the appropriate time |
| Assuming `getDeclaredFields()` order is fixed | Sort fields or do not rely on ordering |
| Putting `@Inherited` on a repeatable FIELD annotation and expecting inheritance across same-named fields | The standard inheritance mechanism does not work that way |
| Swallowing configuration errors as user input errors | Separate metadata validation at startup from data validation |
| Not defining a policy for duplicate/conflicting rules | Provide a mechanism to emit diagnostics or reject the configuration |

## 11. Suggested Code Organization in a Real Application

The demo resides in a single file for ease of learning. A real library should be separated into components with clear responsibilities:

```text
annotation/
    Check.java
    Checks.java
    Rule.java

validator/
    Validator.java
    RuleEvaluator.java
    Violation.java

model/
    Registration.java

test/
    ValidatorTest.java
    AnnotationContractTest.java
```

This is a **recommended organization diagram**, not files that must be created to run the demo.

**The annotation declaration layer** contains only the metadata contract. **The evaluator layer** contains the concrete rules and is unit-tested separately. **The validator** reads metadata, coordinates rule application, and collects `Violation` objects instead of concatenating messages directly inside the loop. **The test layer** verifies that metadata is actually present at the expected targets with the right retention.

If performance matters, field reflection and regex compilation can be **cached per class/field**. Pay attention to classloaders and cache lifecycles to avoid retaining unused class metadata in applications that support hot reload.

For rules involving sensitive data, error messages should describe the violated condition **without printing secret values** such as PINs, passwords, or tokens. The demo prints only the field name and message, not the user input.

## 12. Testing Checklist

Before considering the implementation complete, verify the following cases:

1. **Compiler:** two `@Check` annotations on a single field compile; the `@Checks` container has the correct signature.
2. **Reflection:** `getAnnotationsByType(Check.class)` retrieves the exact number of rules, types, and parameters.
3. **Retention:** if changed to `CLASS` or `SOURCE`, reflection behavior changes by design; do not mistake this for a bug in `@Repeatable`.
4. **Blank:** `null`, `""`, and whitespace-only strings are handled according to the contract.
5. **Length:** strings shorter than, equal to, and longer than the threshold; especially Unicode data if the contract uses `String.length()`.
6. **Regex:** matching strings, non-matching strings, invalid regexes, and appropriate error messages.
7. **Multiple rules:** at least two rules on the same field; one rule failing and all rules failing.
8. **Ordering:** do not depend on the field order returned by reflection; if rule order is meaningful, it must be tested.
9. **Invalid configuration:** `min < 0`, invalid regex, non-`String` field, meaningless duplicate rules.
10. **Inheritance:** if the validator extends to superclasses, clearly define the policy for field hiding and hierarchy traversal.
11. **Access:** whether `private` fields or module boundaries are validly supported.
12. **No data leaks:** report only the necessary violation details; do not dump secret data.

## 13. Self-Check Questions

**Question 1.** Why do two `@Check` annotations on the same field require `@Repeatable`, whereas `@NotBlank` next to `@Pattern` does not?

**Answer:** `@Repeatable` allows **repeating a single annotation type**. Two annotations of different types can naturally appear together at an allowed target location.

**Question 2.** Which element is required on the container for `@Check`?

**Answer:** `Check[] value();`, along with satisfying the related retention, target, and meta-annotation requirements.

**Question 3.** Why does `getDeclaredAnnotation(Check.class)` return `null` on a field with two `@Check` annotations in the demo?

**Answer:** Multiple annotations of the same type are represented using the `@Checks` container; the `Check` annotations are indirectly present rather than having a `Check` directly present on the field in this case.

**Question 4.** If a field has three rules, what does `Field.getAnnotationsByType(Check.class)` return?

**Answer:** An array containing the three `Check` annotations when the metadata has the appropriate RUNTIME retention; the consumer can iterate over each rule.

**Question 5.** Is the configuration `@Check(rule=Rule.MATCHES, regex="[", message="invalid regex")` rejected by the Java compiler solely because the regex is invalid?

**Answer:** No. This configuration is valid with respect to syntax and annotation value types; `javac` does not automatically check regular expression syntax. An annotation processor or runtime processing code must detect the invalid regex (for example, `PatternSyntaxException`). The enum name and required elements must still be declared properly in order to compile.

**Question 6.** In the demo, how many errors do `username="ab"` and `pin="9x"` produce?

**Answer:** Two: username fails to meet `min=4`, and pin does not match the three-digit regex. Neither is blank.

**Question 7.** When needing to retrieve metadata of multiple fields from a parent class, is simply adding `@Inherited` to `@Check` sufficient?

**Answer:** No. `@Inherited` does not propagate field annotations like that; the validator must traverse the class hierarchy itself if designed to support it.

**Question 8.** If you want validator messages to be consistent across JVMs, what do you need to pay attention to?

**Answer:** Do not rely on the order of `getDeclaredFields()`; sort the fields and explicitly publish the rule-ordering policy, as in the demo.

## Official Documentation

- [Java Language Specification 17, §9.6.3 — Repeatable Annotation Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.3).
- [JLS 17, §9.7.5 — Multiple Annotations of the Same Interface](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.5).
- [Java SE 17 API — Repeatable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Repeatable.html).
- [Java SE 17 API — AnnotatedElement](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html).
- [Java SE 17 API — Field](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html).
- [Java SE 17 API — Pattern](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html).

**Conclusion:** `@Repeatable` enables a field to naturally carry multiple validation configurations of the same type. For the system to actually validate data, there must be a consumer that reads **all rules using `getAnnotationsByType()`**, understands each element, and reports violations according to the contract. Combining standard container design, the right retention/target, configuration validation, and runtime tests makes repeatable annotations a reliable metadata API.
