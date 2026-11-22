# Enum Values and Nested Annotations in Java

## 1. Context: Annotations with Elements and Values

In Java, an annotation does not only exist in marker form such as `@Override`. It can also **contain multiple elements (annotation elements)** to store structured metadata. Each element is declared like a parameterless method inside `@interface`, and the element's value is supplied when using the annotation:

```java
@interface Example {
    String name();
    int version() default 1;
}

@Example(name = "sample", version = 2)
class Demo {}
```

`name()` is a required element because it has no default value. `version()` has `default 1`, so it can be omitted when using the annotation. This is the syntax for declaring annotation elements; when using reflection, Java returns the values through the corresponding methods such as `annotation.name()` and `annotation.version()`.

This lesson focuses on two expressive value types:

- **Enum values:** restrict a choice to constants defined in an enum, for example `Priority.HIGH`.
- **Nested annotation values:** use an annotation as the value of an element belonging to another annotation, for example `@Schedule(window = @Window(start = 8, end = 17))`. An **annotation array** can be used to declare multiple sub-configurations.

This is **statically typed metadata checked by Java**, not an arbitrary object or a command that automatically triggers business logic.

## 2. Valid Data Types for Annotation Elements

Java only allows annotation elements to have the following types:

| Category | Declaration example inside `@interface` | Valid value when used |
| --- | --- | --- |
| Primitive types | `int retries();`, `boolean enabled();` | `retries = 3`, `enabled = true` |
| `String` | `String label();` | `label = "report"` |
| `Class` or `Class<?>` with an appropriate type | `Class<?> handler();` | `handler = String.class` |
| `enum` type | `Priority priority();` | `priority = Priority.HIGH` |
| Annotation type | `Window window();` | `window = @Window(start = 8, end = 17)` |
| One-dimensional array of a valid type | `Priority[] priorities();`, `Rule[] rules();` | `priorities = {Priority.HIGH, Priority.LOW}` |

The types `Integer`, `List<String>`, `Map`, arbitrary business classes, two-dimensional arrays, and the `void` return type are **invalid** as annotation element types. Elements cannot be declared with parameters or a `throws` clause. Annotation values also **cannot be `null`**.

These rules explain why enums and nested annotations are very useful: they help describe fixed choices or multi-field structures right within Java's data type constraints.

## 3. Enum Values in Annotations

### 3.1. Declaring an Enum Type and an Element Using an Enum

```java
enum Priority {
    LOW, NORMAL, HIGH
}

@interface Task {
    Priority priority() default Priority.NORMAL;
}

@Task(priority = Priority.HIGH)
class UrgentTask {}

@Task
class OrdinaryTask {}
```

In the example:

- `Priority` is an enum defining three fixed choices. The compiler knows the exact allowed values.
- `priority()` is an annotation element **with return type `Priority`**; `default Priority.NORMAL` is used if no value is provided when writing `@Task`.
- `@Task(priority = Priority.HIGH)` specifies the value directly from an enum constant; `@Task` uses the default value.
- `@Task(priority = Priority.CRITICAL)` will cause a compile error because the enum does not yet have a `CRITICAL` constant.

When assigning a value to an annotation element of an enum type, Java requires an **enum constant name** permitted in the context of an annotation expression. A `Priority` variable holding the value `Priority.HIGH` does not become a valid expression to substitute for an enum constant in an annotation.

Invalid example:

```java
// Code illustrating an error; does not compile standalone.
class InvalidTask {
    static final Priority SELECTED = Priority.HIGH;

    @Task(priority = SELECTED) // ERROR: requires a valid enum constant.
    void run() {}
}
```

Even though `SELECTED` is `static final`, it is still a **variable** holding an enum value, not the way to write an enum constant in an annotation. Write `Priority.HIGH` directly.

### 3.2. Why Are Enums Better Than Free-Form Strings?

Comparison:

```java
@interface TextTask {
    String priority();
}

@TextTask(priority = "HGIH") // The compiler accepts this string.
class TypoTask {}
```

`"HGIH"` is a valid string even though the intent may have been `"HIGH"`. With `Priority.HIGH`, the IDE can suggest values, the compiler rejects incorrect constant names, and refactoring tools can update enum references more consistently.

Use an enum when the set of choices is controlled by the source code and type safety is needed. If the configuration must change arbitrarily outside build/deploy time, choosing an enum requires careful consideration because adding a new constant is still a change to the enum's source code and typically requires rebuilding.

### 3.3. Enum Arrays

An element can also accept an enum array:

```java
@interface AllowPriorities {
    Priority[] value();
}

@AllowPriorities({Priority.LOW, Priority.HIGH})
class SupportedTasks {}
```

`value()` is a special element name that enables the **shorthand syntax** `@AllowPriorities({...})`; the full syntax is `@AllowPriorities(value = {...})`. The array still holds constants of that exact enum type, not strings.

## 4. Annotations as Values of Other Annotations

### 4.1. Defining a Sub-Configuration

Suppose an overall annotation needs to describe a value range. We create an annotation that solely represents the range, and then use it as an element:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target({})
@interface Range {
    int min() default 0;
    int max() default 100;
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface CheckRange {
    Range range() default @Range;
}

class RangeService {
    @CheckRange(range = @Range(min = 1, max = 20))
    void check() {}
}
```

`range()` has **the annotation `Range` as its return type**, so an annotation expression `@Range(...)` must be used when assigning it. `new Range(...)` is invalid; an annotation type cannot be instantiated with `new`.

`@Target({})` declares that `Range` does not directly target a regular program element; one valid use of it is as a nested annotation inside another annotation's value. This is a technique to prevent accidentally placing `@Range` directly on a class or method when it is only a sub-configuration. `@CheckRange` is the annotation applied to METHOD.

The expression `default @Range` creates a **default value** with `min = 0`, `max = 100`; it is valid because every element of `Range` has a default. You can explicitly write `default @Range(min = 0, max = 100)` if desired.

### 4.2. Distinguishing Two Common Meanings of “Nested Annotation”

The phrase *nested annotation* can refer to two different structures:

**Case A — annotation-valued element**, the focus of this lesson:

```java
@CheckRange(range = @Range(min = 1, max = 20))
void process() {}
```

`@Range(...)` resides **inside the value of the `range` element** of `@CheckRange`. Reflection can return an object implementing the `Range` annotation interface through the `checkRange.range()` method when the annotation has the appropriate retention.

**Case B — declaring an annotation type inside another type:**

```java
class Catalog {
    @interface Entry {
        String value();
    }
}

@Catalog.Entry("item")
class Item {}
```

Here `Entry` is **an annotation type declared nested inside the `Catalog` class**, referenced as `Catalog.Entry`. It is not automatically the value of an element of another annotation. The two concepts can be combined, but they are not synonymous.

### 4.3. Arrays of Nested Annotations

An element of type `Rule[]` can accept **multiple annotations of the same type** to create a sub-configuration:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target({})
@interface Rule {
    String name();
    boolean required() default true;
}

@interface RuleCollection {
    Rule[] rules();
}

@RuleCollection(rules = {
    @Rule(name = "email"),
    @Rule(name = "phone", required = false)
})
class ProfileDefinition {}
```

Each item in `rules` has type `Rule`. The `{...}` syntax creates an array of annotation values; it is **not the same** as placing two `@Rule` annotations directly next to each other on the same class.

When no rules are needed, you can define `Rule[] rules() default {};`, and then use `@RuleCollection` without listing the array.

## 5. Standalone Runnable Java 17+ Example: Enums, Nested Annotations, Arrays, and Defaults

Create the file **NestedAnnotationValuesDemo.java** with the following full content. The program only uses the Java SE API and requires no external libraries.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;

enum Level {
    LOW, NORMAL, HIGH
}

@Retention(RetentionPolicy.RUNTIME)
@Target({})
@interface RangeConfig {
    int min() default 0;
    int max() default 100;
}

@Retention(RetentionPolicy.RUNTIME)
@Target({})
@interface CheckConfig {
    String name();
    Level level() default Level.NORMAL;
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Monitor {
    Level level() default Level.NORMAL;
    RangeConfig range() default @RangeConfig;
    CheckConfig[] checks() default {};
}

public class NestedAnnotationValuesDemo {
    @Monitor(
        level = Level.HIGH,
        range = @RangeConfig(min = 2, max = 8),
        checks = {
            @CheckConfig(name = "format"),
            @CheckConfig(name = "access", level = Level.HIGH)
        }
    )
    void validate() {}

    @Monitor
    void fallback() {}

    static void printMetadata(String methodName)
            throws NoSuchMethodException {
        Method method = NestedAnnotationValuesDemo.class
                .getDeclaredMethod(methodName);
        Monitor monitor = method.getAnnotation(Monitor.class);

        System.out.println(methodName + ": level=" + monitor.level());
        System.out.println("range=" + monitor.range().min()
                + ".." + monitor.range().max());

        for (CheckConfig check : monitor.checks()) {
            System.out.println("check=" + check.name()
                    + "/" + check.level());
        }

        System.out.println("checks=" + monitor.checks().length);
    }

    public static void main(String[] args)
            throws NoSuchMethodException {
        printMetadata("validate");
        printMetadata("fallback");
    }
}
```

Compile and run from the directory containing the file with JDK 17 or later:

```bash
javac NestedAnnotationValuesDemo.java
java NestedAnnotationValuesDemo
```

Stdout:

```text
validate: level=HIGH
range=2..8
check=format/NORMAL
check=access/HIGH
checks=2
fallback: level=NORMAL
range=0..100
checks=0
```

**Step-by-step explanation:**

1. `Level` is an enum, so `Monitor.level()` only returns constants belonging to `Level`.
2. `RangeConfig` is an annotation used as a **nested configuration value** for `Monitor.range()`. The `monitor.range()` method returns a `RangeConfig`, and then `min()` and `max()` return the integers.
3. `CheckConfig[]` is an **annotation array**. `validate()` declares two entries; the `format` entry does not specify `level`, so it uses the default `NORMAL`.
4. `fallback()` only has `@Monitor`, yet still receives the default values: `Level.NORMAL`, the default `@RangeConfig` 0..100, and an empty `checks` array.
5. All three custom annotations have `@Retention(RUNTIME)` to demonstrate reading metadata at runtime; the `Monitor` annotation is placed on METHOD, while the two child annotations are only used as values.
6. `getDeclaredMethod` looks up a method by name; `getAnnotation(Monitor.class)` reads the annotation on that exact Method. The calls `monitor.level()`, `monitor.range()`, and `monitor.checks()` retrieve statically typed metadata.

The code **does not automatically check the 2..8 bounds, does not run the “format” check, and does not enforce the “access” check**. It is only metadata. To create validation or permission checks, you must write a component that reads the values and applies the corresponding logic.

## 6. Default Values, Shorthand Syntax, and How Java Checks Them

### 6.1. Elements With and Without Defaults

An annotation can contain both required elements and optional elements:

```java
@interface EndpointInfo {
    String path();                         // Required
    Level level() default Level.NORMAL;   // Optional
    RangeConfig range() default @RangeConfig;
}
```

When using `@EndpointInfo(path = "/orders")`, the other two elements take their defaults; if you write `@EndpointInfo` without providing `path`, the compiler reports an error due to the missing required element.

Default values are defined **inside the annotation type**, and should not be understood as values copied into each usage site in the source code. When reading an annotation through the API, values are returned as if they had been fully supplied, even when the usage declaration omitted elements with defaults. Changing a default in the annotation type can affect the observed result of an annotation that does not specify an explicit value after the components are compatibly built/deployed.

### 6.2. `value()` and Shorthand Syntax

If an annotation has an element named `value`, the element name can be omitted when passing only `value`:

```java
@interface SelectLevel {
    Level value();
}

@SelectLevel(Level.HIGH)
class HighLevelType {}
```

The syntax above is equivalent to `@SelectLevel(value = Level.HIGH)`. When there are other elements and multiple named values need to be specified, use the appropriate `name = value` pair form. This shorthand also applies when `value()` has an annotation type or an annotation array type.

### 6.3. Values Must Be Valid at Compile Time

The compiler checks the exact type and syntax of annotation expressions. The following example **does not compile standalone**; each line illustrates a separate error:

```java
// Illustrative errors — do not include simultaneously in a runnable program.
@Monitor(level = "HIGH")              // Wrong: String instead of Level.
@Monitor(level = null)                // Wrong: annotation value cannot be null.
@Monitor(range = new RangeConfig())   // Wrong: cannot instantiate an annotation with new.
@Monitor(checks = {"format"})         // Wrong: String[] instead of CheckConfig[].
```

For `int`, `String`, or other primitive elements, the value must satisfy the **constant expression** rules applicable to annotation values. For `enum`, the expression must satisfy the **enum constant** requirement; for an annotation element, the value must be in **annotation** form, for example `@RangeConfig(min = 1)`. A runtime method call cannot be used as an annotation value.

**Business logic note:** `@RangeConfig(min = 10, max = 2)` can still pass Java's syntax/type checks because both are valid `int` values. Java does not inherently know the rule “min must be less than or equal to max”. If this constraint is needed, an annotation processor or metadata-processing code must check it itself.

## 7. Reading and Processing Enum/Nested Annotation Values with Reflection

In the runnable example in section 5, `Monitor monitor = method.getAnnotation(Monitor.class)` provides an object representing the annotation. From there:

- `monitor.level()`: returns `Level`, which can be used in a `switch` over the enum constants to choose a processing branch.
- `monitor.range()`: returns `RangeConfig`, and then `min()` and `max()` can be called.
- `monitor.checks()`: returns `CheckConfig[]`, allowing iteration over each element to read `name()` and `level()`.

Annotation elements themselves **are not reassignable fields** in the metadata object. There is no `monitor.setLevel(...)`; an annotation type's methods are read-only accessors for the declared information.

When reflection does not find `@Monitor` on a method, `getAnnotation(Monitor.class)` can return `null`; real-world code must check before accessing it. In the example in section 5, both methods are annotated with `@Monitor`, so the access is valid.

`@Retention(RUNTIME)` is a condition typically required to read annotations via reflection. Annotations with `SOURCE` or `CLASS` retention cannot be read with `getAnnotation` in that way, although the compiler or other build tools can still use them.

When an annotation has a deep structure (for example, `Monitor` containing `RangeConfig` and a list of `CheckConfig`), business processing typically consists of two phases:

1. **Reading the configuration**: retrieving the root annotation, enums, sub-configurations, and arrays of sub-configurations.
2. **Applying the rules**: validating the configuration yourself, then using it in a validator, mapper, engine, or framework.

Keeping the two phases distinct helps avoid confusing **describing with metadata** and **executing a feature**.

## 8. How Do Nested Annotations Differ from @Repeatable?

Both involve multiple annotations appearing, but the syntax and data model differ:

**Annotation array as an element value:**

```java
@Monitor(checks = {
    @CheckConfig(name = "first"),
    @CheckConfig(name = "second")
})
void work() {}
```

Here **only one `@Monitor`** is attached to `work()`; the two `@CheckConfig` instances are **the value of the `checks` element**. Therefore, `CheckConfig` does not need `@Repeatable`.

**A single annotation type applied directly multiple times to the same declaration:**

```java
// Syntax example when an annotation type has been declared with @Repeatable
@Tag("first")
@Tag("second")
void work() {}
```

In this case, `@Tag` is an annotation placed **directly twice** on `work()`. For this syntax to be valid, `Tag` must be designed with `@Repeatable` and have a compatible container.

When designing:

- Need a parent configuration containing multiple sub-configurations with a clear relationship → consider an element of **annotation array** type such as `CheckConfig[] checks()`.
- Need to allow users to place the same annotation multiple times directly on the same target → consider **@Repeatable**.

Both mechanisms can be used in the same library, but they cannot be treated as the same thing.

## 9. Common Mistakes and Fixes

**Mistake 1 — Passing a string instead of an enum constant.** Writing `level = "HIGH"` for an element of type `Level` causes a compile error. Fix it to `level = Level.HIGH` (or a valid enum constant expression in Java).

**Mistake 2 — Passing an enum variable instead of an enum constant name.** A `static final Level` variable still does not satisfy the enum constant syntax required in an annotation. Use the constant name directly.

**Mistake 3 — Using `new` for a nested annotation.** An annotation-valued element accepts values in the form `@RangeConfig(...)`, not `new RangeConfig(...)`.

**Mistake 4 — Forgetting to provide a required element.** An element such as `String name();` without a default must be present when the annotation is used. If you want it to be optional, define a valid default.

**Mistake 5 — Trying to omit an element using `null`.** Annotation elements do not accept null. Design the absent state using an explicit default value, an `UNSPECIFIED` enum, an empty string, or an empty array depending on the API contract.

**Mistake 6 — Using multidimensional arrays, collections, or arbitrary objects.** `Rule[][]`, `List<Rule>`, and arbitrary class types are not allowed as annotation element types. Valid annotation arrays must be one-dimensional.

**Mistake 7 — Confusing annotation arrays with `@Repeatable`.** `checks = {@CheckConfig(...), ...}` declares an array value of `@Monitor`; it does not require repeating `@CheckConfig` directly on the method.

**Mistake 8 — Assuming metadata automatically validates business logic.** Java checks types, but it does not check “min does not exceed max” or “rules must have unique names”. Separate validation code is required.

**Mistake 9 — Failing to distinguish TARGET and RETENTION.** `@Target({})` designates the annotation to be used only as a sub-value in the example; `@Retention(RUNTIME)` enables demonstrating reading metadata via reflection. They govern two independent aspects.

**Mistake 10 — Calling `getAnnotation` without a null check.** If the method does not have the corresponding annotation, the result can be null, and `.level()` or `.range()` must not be called immediately.

## 10. Practice Exercises

1. Add `CRITICAL` to the `Level` enum, change `validate()` to `level = Level.CRITICAL`, and then predict the first line of stdout. Try intentionally writing `level = "CRITICAL"` to observe the type error.
2. Add `boolean inclusive() default true;` to `RangeConfig`. Write `@RangeConfig(min = 1, max = 10, inclusive = false)` in `validate()`, and then add a line printing `inclusive`.
3. Add `@CheckConfig(name = "timeout", level = Level.LOW)` to the `checks` array and predict all of the `check=` and `checks=` lines.
4. Create a third method `void unspecified() {}` without `@Monitor`. Modify `printMetadata` so that when `getAnnotation` returns `null`, it prints an appropriate message instead of throwing a `NullPointerException`.
5. Try writing `@Monitor(range = @RangeConfig(min = 20, max = 2))`. Explain why this snippet is still type-valid and suggest where the business validation should be performed.

**Conclusion:** Annotation elements can accept an **enum constant**, **another annotation**, or a **one-dimensional annotation array** to represent strongly typed configurations. Enums create a fixed set of choices; nested annotations group related values; defaults allow omitting unnecessary configuration. Java validates syntax, types, and valid expressions at compile time, while business logic must be handled by the code or tools that read the metadata.
