# Building a Simple Runtime Annotation Validator Using Java Reflection

## 1. Practice Goals and Scope

This lesson builds **a minimal object data validator (runtime validator)**, using annotations to declare rules directly on fields and Reflection to enforce those rules at runtime.

Output requirements:

1. Define a `@NotBlank` annotation for `String` fields: the value must not be `null`, empty, or whitespace-only according to `String.isBlank()`.
2. Define a `@MinValue(18)` annotation for `int` or `Integer` fields: the value must not be less than the threshold; for `Integer`, `null` is treated as invalid in this example.
3. Use Reflection to read annotations and field values, producing a list of user-displayable errors.
4. Check fields declared in **superclasses** as well, not only the immediate runtime class.
5. Do not depend on the return order of `getDeclaredFields()`: sort errors before printing so test output is deterministic.
6. Distinguish metadata retained with **`RetentionPolicy.RUNTIME`** from annotations that only have `RetentionPolicy.CLASS`.
7. Create a **complete, compilable, runnable Java 17+ program** with no external libraries.

This is a **validator design practice exercise**: it only accepts an existing object, checks annotated fields, and returns a list of errors. It is **not** a classpath scanner, a general-purpose validation engine, or a replacement for Jakarta Bean Validation.

## 2. Annotations Are Metadata, Not Self-Executing Rules

Annotations declare metadata attached to program elements. For example:

```java
// Illustrative examples; complete definitions are in the program section.
@NotBlank(message = "name is required")
private final String name;

@MinValue(18)
private final Integer age;
```

These two declarations **do not make the JVM automatically validate data**. Code is required to read the annotations and apply rules to the field values. Therefore, the lesson consists of two distinct parts:

- **Metadata part:** annotations describe requirements, such as `message` or `value`.
- **Engine part:** the validator walks fields, calls `Field.getAnnotation(...)`, reads the field value with `Field.get(...)`, and appends an error message when a rule is violated.

Annotations are not restricted to fields: Java supports many `ElementType`s such as `TYPE`, `METHOD`, `PARAMETER`, `CONSTRUCTOR`, and `TYPE_USE`. Here we intentionally choose `FIELD`, because the data to validate resides in object fields.

## 3. Three Important Meta-Annotations

### `@Retention(RetentionPolicy.RUNTIME)`

This is the most critical requirement when using **runtime reflection** to read an annotation on an annotated element:

- `SOURCE`: exists in source code, not required to be written to the class file.
- `CLASS`: recorded in the class file under the corresponding retention policy, yet **not visible through standard runtime annotation reflection APIs**.
- `RUNTIME`: the class file retains the annotation in a runtime-visible form so Reflection can read it while running.

If you forget `@Retention`, the default retention policy of an annotation is **`RetentionPolicy.CLASS`**, so `field.getAnnotation(MyRule.class)` will typically return `null` even though `@MyRule` appears in the source code.

### `@Target(ElementType.FIELD)`

Restricts the annotation so it can only be placed on fields. The compiler reports an error if you try placing `@NotBlank` on a class or method when the target allows only `FIELD`. However, `@Target(FIELD)` **does not restrict the field's type**: an annotation can still be placed mistakenly on an `Integer` field. The engine itself must verify the field type to avoid applying nonsensical rules.

### Annotation elements

`@NotBlank(message = "...")` lets you configure the message; `@MinValue(18)` stores the threshold via an `int value()` element. An element named `value` supports shorthand syntax: `@MinValue(18)` is equivalent to `@MinValue(value = 18)`.

An annotation can define default values (for example `String message() default "must not be blank";`). Those values are **annotation metadata**, not per-instance state that the JVM attaches to annotated objects.

## 4. Reflection APIs Used

| API | Role in the validator | Notes |
| --- | --- | --- |
| `obj.getClass()` | Gets the runtime class of the object to validate | `obj == null` must be handled first |
| `Class.getDeclaredFields()` | Gets fields declared directly in each class | Does not include superclass fields; order is not guaranteed |
| `Class.getSuperclass()` | Walks up parent classes one by one | Stop before `Object.class` |
| `Field.getAnnotation(NotBlank.class)` | Gets the annotation instance, or `null` if absent | Requires `RUNTIME` retention to be readable |
| `Field.isAnnotationPresent(...)` | Checks whether an annotation is present | Does not replace retrieving annotation elements |
| `Field.getType()` | Determines the declared type of the field | `String.class`, `int.class`, `Integer.class` are distinct types |
| `Field.get(Object)` | Reads the value of a field on an instance | May throw `IllegalAccessException` without sufficient access |
| `Field.canAccess(Object)` | Checks current access to the field for a receiver | Distinguishes public/private; receiver must be compatible |
| `Field.trySetAccessible()` | Attempts to enable access to the field when inaccessible | May be denied by JPMS/security; not guaranteed to succeed |

The same annotation type can be read with `getAnnotation` or `getDeclaredAnnotation`. On **fields**, walking each field explicitly avoids confusion with inheritance: `@Inherited` applies according to rules for **class** annotations and does not automatically propagate field annotations from a superclass to a same-named field in a subclass. Hence, the engine walks the hierarchy via `getSuperclass()` rather than assuming `getDeclaredFields()` includes inherited fields.

**Example design choices:** `static` and synthetic fields are skipped because we are validating **an instance's own state**, not class-level data or compiler-generated members. For same-named fields shadowed between parent and child classes, prefixing the declaring class name in the error message distinguishes the two fields.

## 5. Complete Java 17+ Program

Create a file named `RuntimeAnnotationValidatorDemo.java`. All types reside in one file, using no packages outside the JDK:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface NotBlank {
    String message() default "must not be blank";
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface MinValue {
    int value();
}

@Retention(RetentionPolicy.CLASS)
@Target(ElementType.FIELD)
@interface CompileOnlyTag {}

public class RuntimeAnnotationValidatorDemo {
    static class Person {
        @NotBlank(message = "name is required")
        @CompileOnlyTag
        private final String name;

        @MinValue(18)
        private final Integer age;

        Person(String name, Integer age) {
            this.name = name;
            this.age = age;
        }
    }

    static class Employee extends Person {
        @NotBlank
        private final String department;

        Employee(String name, Integer age, String department) {
            super(name, age);
            this.department = department;
        }
    }

    static class Validator {
        static List<String> validate(Object object) {
            Objects.requireNonNull(object, "object");

            List<String> errors = new ArrayList<>();
            for (Class<?> type = object.getClass();
                    type != null && type != Object.class;
                    type = type.getSuperclass()) {
                for (Field field : type.getDeclaredFields()) {
                    if (field.isSynthetic()
                            || Modifier.isStatic(field.getModifiers())) {
                        continue;
                    }

                    NotBlank notBlank =
                            field.getAnnotation(NotBlank.class);
                    MinValue minValue =
                            field.getAnnotation(MinValue.class);
                    if (notBlank == null && minValue == null) {
                        continue;
                    }

                    if (notBlank != null && field.getType() != String.class) {
                        throw new IllegalArgumentException(
                                "@NotBlank requires String: " + field);
                    }
                    if (minValue != null
                            && field.getType() != int.class
                            && field.getType() != Integer.class) {
                        throw new IllegalArgumentException(
                                "@MinValue requires int/Integer: " + field);
                    }

                    if (!field.canAccess(object) && !field.trySetAccessible()) {
                        throw new IllegalStateException(
                                "Cannot read annotated field: " + field);
                    }

                    Object value;
                    try {
                        value = field.get(object);
                    } catch (IllegalAccessException e) {
                        throw new IllegalStateException(
                                "Cannot read annotated field: " + field, e);
                    }

                    String location =
                            type.getSimpleName() + "." + field.getName();
                    if (notBlank != null
                            && (value == null || ((String) value).isBlank())) {
                        errors.add(location + ": " + notBlank.message());
                    }
                    if (minValue != null
                            && (value == null
                                || ((Integer) value).intValue()
                                   < minValue.value())) {
                        errors.add(location + ": must be >= "
                                + minValue.value());
                    }
                }
            }
            Collections.sort(errors);
            return List.copyOf(errors);
        }
    }

    public static void main(String[] args) throws Exception {
        Field name = Person.class.getDeclaredField("name");
        System.out.println("RUNTIME visible: "
                + name.isAnnotationPresent(NotBlank.class));
        System.out.println("CLASS visible: "
                + name.isAnnotationPresent(CompileOnlyTag.class));

        Employee valid = new Employee("An", 20, "Engineering");
        Employee invalid = new Employee("  ", 16, null);

        System.out.println("Valid: "
                + Validator.validate(valid).isEmpty());

        List<String> errors = Validator.validate(invalid);
        System.out.println("Errors: " + errors.size());
        errors.forEach(System.out::println);
    }
}
```

Compile and run commands using JDK 17 or newer:

```bash
javac -encoding UTF-8 RuntimeAnnotationValidatorDemo.java
java RuntimeAnnotationValidatorDemo
```

Expected output:

```text
RUNTIME visible: true
CLASS visible: false
Valid: true
Errors: 3
Employee.department: must not be blank
Person.age: must be >= 18
Person.name: name is required
```

### Step-by-Step Explanation

1. `@NotBlank` and `@MinValue` both have `RetentionPolicy.RUNTIME`, so `Field.getAnnotation(...)` reads their configuration from `Person` and `Employee` at runtime. `@CompileOnlyTag` only has `CLASS`, so `isAnnotationPresent(CompileOnlyTag.class)` returns `false`.
2. The validator takes an existing object rather than scanning the classpath. It starts from `object.getClass()`, then uses `getSuperclass()` to inspect both `Employee` and `Person`. Using only `Employee.class.getDeclaredFields()` would miss `name` and `age`.
3. Once an annotation is found, the validator checks the field type first. This prevents `@NotBlank` on a number or `@MinValue` on a string from going unhandled; annotation misconfiguration errors are reported separately from data errors.
4. `canAccess`/`trySetAccessible` permits reading `private` fields in this example running on a standard classpath. Such access **is not guaranteed** for all classes/modules; the validator must fail explicitly when access is denied.
5. `String.isBlank()` returns `true` for an empty string or whitespace-only string per `Character.isWhitespace`; the example uses `"  "` to trigger a name error. A `null` `Integer` is also treated as failing `@MinValue` under this lesson's contract.
6. `Collections.sort(errors)` makes the output independent of the field order returned by Reflection; the `Person.`/`Employee.` prefix clearly identifies where each field is declared.
7. `List.copyOf(errors)` returns an unmodifiable list so callers cannot accidentally mutate the error list after validation finishes. The validator does not modify field values, create instances, or invoke business methods.

**The result `"Valid: true"` only means the object satisfies the two rule types implemented here.** It does not certify that the object is valid under all business constraints, sensitive-data policies, or an entire nested object graph.

## 6. Why Separate Configuration Errors from Data Errors?

Suppose someone puts `@NotBlank` on an `Integer` field. Since the annotation targets `FIELD`, the compiler **does not forbid** this, yet checking strings with `isBlank()` makes no sense. The validator needs a clear policy:

- **Configuration errors:** annotation placed on the wrong type, corrupted metadata, lack of permission to read a field, or class/module incompatibility. The example fails fast with `IllegalArgumentException` or `IllegalStateException`, rather than treating this as user-input error.
- **Data errors:** the field has the right type and was read successfully, yet fails the rule (`name` is all whitespace, `age` is below 18). These errors are collected into `List<String>` for the caller to display or return from an API.
- **`null` target object:** the example uses `Objects.requireNonNull(object, "object")` and treats this as an API misuse error rather than an object to validate.

This policy matters because lumping everything into "invalid value" can hide configuration bugs or reflection access failures. In production code, prefer a richer result type than plain strings — such as a `ValidationError(String fieldPath, String code, String message)` record — to support i18n, sorting, and UI rendering.

## 7. What Cases Should Tests Cover?

| Test case | Data/configuration | Expectation |
| --- | --- | --- |
| Runtime-visible annotation | Field with `@Retention(RUNTIME)` | `isAnnotationPresent` returns `true` |
| Class-file-only annotation | Field with `@Retention(CLASS)` | Runtime annotation API returns `false` |
| Valid object | `name="An"`, `age=20`, `department="Engineering"` | Empty error list |
| Whitespace-only string | `name="  "` | One `@NotBlank` error for `name` |
| Value below threshold | `age=16` with `@MinValue(18)` | One minimum-age error |
| Wrapper `null` value | `age=null` | One `@MinValue` error |
| `null` String | `department=null` | One `@NotBlank` error |
| Field from superclass | `name` and `age` declared in `Person` | Still validated via class hierarchy loop |
| Annotation on wrong type | `@NotBlank int count` | Configuration error raised, not treated as invalid input |
| Insufficient read access | Private field in a non-open module | Access error raised, does not pretend validation passed |
| Static or synthetic field | Not ordinary instance data | Skipped under current contract |
| Unsupported/unannotated field | Other data fields | Skipped; no extra rules inferred |

When expanding tests, you can add `check(...)` assertions or JUnit unit tests, but distinguish *annotation presence* from *the engine executing the rule properly*. Adding a new annotation to source code without a corresponding handler branch in the validator will have no effect on its own.

## 8. Limitations to Know Before Production Use

### Private access and Java modules

On a standard classpath, `trySetAccessible()` can succeed on application-owned classes, as shown above. With **named modules** in JPMS, deep reflection can be blocked unless the package is `opens` to the calling module. `getDeclaredFields()` may still list metadata while `Field.get` remains disallowed. Never assume `setAccessible(true)` will bypass every module boundary.

Libraries often prefer public accessors/getters or explicit module contracts when inspecting objects in third-party packages. If a field cannot be read, the validator must report an access error rather than silently skipping it and concluding the object is valid.

### Retention, inheritance, and shadowed fields

- `@Inherited` **only affects class-level annotation lookup under its supported mechanism**; it does not "pass" a superclass field's annotation down to a new field in a subclass.
- `getDeclaredFields()` does not include inherited fields automatically, so the `getSuperclass()` loop is intentional.
- If a subclass declares a field with the same name as a superclass field, the two fields remain distinct members. Prefixing the class name in error messages avoids ambiguity.
- Interfaces do not have ordinary instance fields (fields in interfaces are `public static final` by default); this lesson's engine only checks instance fields along the superclass chain and does not scan interfaces.

### Null, numeric types, and general data

`@MinValue` here supports **only `int`/`Integer`**: `Field.get(...)` boxes primitive `int` into `Integer`, allowing a single comparison block. `long`, `BigDecimal`, `double`, generic fields, or collections require dedicated comparison rules; never cast arbitrary `Number` values to `int` as that can lose precision or alter semantics.

`@NotBlank` uses `String.isBlank()`, which is not equivalent to checking for a valid email string, does not ensure Unicode normalization for every domain, and performs no trimming/mutation. The engine is **read-only** and does not alter the object.

### Performance, lifecycle, and thread safety

Each call currently walks the class hierarchy, reflects on fields, reads annotations, and accesses data. When validating millions of objects of the same class, a library can cache **immutable metadata** per class (such as field lists, annotations, and readers) to reduce overhead; never cache an object's field **values** as the result for another object.

In the example, `List<String> errors` is created locally per call, so there is no shared static error state. That avoids races on the error list, yet **does not make the validated object thread-safe**: if another thread mutates fields concurrently, results may reflect an inconsistent state.

### Security and API design

Enabling read access to private fields is a sensitive operation. Do not use this approach to inspect objects you do not control, never log secret values, and do not blindly trust annotations from third-party bytecode. When an application handles untrusted input, a validator is only **one validation layer**, not a substitute for authentication, authorization, business invariants, and safe deserialization.

### When to use a standard library?

For real-world applications with complex bean validation, nested objects, validation groups, localized messages, lifecycle integration, and framework support, consider **Jakarta Bean Validation** with an appropriate implementation instead of expanding a custom validator indefinitely. The custom `@NotBlank` and `@MinValue` annotations here are **custom illustrative rules**, not the exact annotations or full contract of Jakarta Validation.

## 9. Controlled Step-by-Step Extensions

1. **Add a new annotation:** e.g., `@MaxLength(int value)` for `String`. Declare `@Target(FIELD)` and `@Retention(RUNTIME)`; then add a branch in the validator to read and enforce the rule.
2. **Structure error objects:** replace `String` with a record holding field path, error code, and message. Test ordering and cases where the same field violates multiple rules.
3. **Support repeatable annotations:** only when genuinely needed, use `@Repeatable` and the appropriate `getAnnotationsByType(...)` API; do not assume `getAnnotation` returns all repeated entries.
4. **Add nested validation:** define a dedicated `@ValidNested`, walking child objects and arrays/collections with depth limits, cycle detection via an identity set, and stack overflow protection.
5. **Cache metadata:** store inspected fields/rules per `Class<?>` using a cache mindful of class loader lifecycles; avoid memory leaks when plugins can unload.
6. **Write negative unit tests:** wrong field types, private fields not opened by a module, `null`, Unicode whitespace, inheritance, static/synthetic fields, and handler errors.

Every step must answer: where does the metadata come from, when is it readable, how are configuration errors handled, and does the engine enforce the rule accurately? Annotations are **not magic**; their value comes from the reading mechanism and testing.

## 10. Self-Check Questions

**Question 1.** Why does annotating a field with `@NotBlank` without running a validator fail to block an empty `String` automatically?

**Answer:** Annotations only provide metadata. Code must retrieve the annotation and enforce the constraint for it to take effect.

**Question 2.** If `@Retention` is omitted, will `Field.getAnnotation(...)` read that annotation by default?

**Answer:** You should not expect it to. Default retention is `CLASS`, which is not visible through ordinary annotation reflection at runtime; use `RUNTIME` when reading via `Field.getAnnotation`.

**Question 3.** Does `@Target(FIELD)` stop a developer from placing `@NotBlank` on an `int` field?

**Answer:** No. `@Target` restricts the **declared program element kind** (field), not the Java data type of the field. The validator must check `Field.getType()` and report a configuration error when mismatched.

**Question 4.** Why is `Employee.class.getDeclaredFields()` insufficient to validate the `name` field declared in `Person`?

**Answer:** `getDeclaredFields()` only returns fields declared directly in `Employee`. You must walk `getSuperclass()` to inspect superclass fields if the contract covers them.

**Question 5.** Why is `Collections.sort(errors)` needed before comparing stdout in tests?

**Answer:** The Reflection API does not guarantee field return order; sorting messages makes output deterministic and keeps tests from relying on unguaranteed ordering.

**Question 6.** Is `trySetAccessible()` guaranteed to open every private field in a Java 17+ application?

**Answer:** No. JPMS, security policies, and access rules can block it. When disallowed, the validator must report an access error rather than pretending the object is valid.

**Question 7.** When `age` is an `Integer` equal to `null`, how does `@MinValue(18)` handle it in this example?

**Answer:** Invalid, because this lesson treats `null` as violating `@MinValue`; another library may treat `null` as valid for a min constraint and require a separate `@NotNull` annotation. The policy must be documented.

**Conclusion:** A runtime annotation validator follows **declare constraints (`RUNTIME`/`FIELD`) → read metadata with Reflection → access data → evaluate rules → report structured errors**. Separating configuration errors from data errors and handling inheritance and access control explicitly makes this exercise a solid foundation before adopting full validation frameworks.