# `AnnotationDefault` and How Java Stores Default Values of Annotation Elements

## 1. From the `default` Keyword to the Trace in the Class File

When defining an annotation type (`@interface`), Java allows an **element method** to have a default value using the `default` keyword:

```java
@interface RetryPolicy {
    String name();
    int attempts() default 3;
    String[] labels() default {"normal"};
}
```

In the example:

- `name()` **has no default value**: the usage site must provide `name = ...`.
- `attempts()` defaults to the integer `3`.
- `labels()` defaults to a string array containing a single element `"normal"`.

An annotation using this type can omit elements that already declare a default:

```java
@RetryPolicy(name = "SEND_MAIL")
class MailTask {}
```

When a program reads the annotation via Reflection, `attempts()` returns `3` and `labels()` returns `{"normal"}`, even though these two values **are not written at the usage site**.

So where does the compiler store the default? In the JVM class file structure, the default is represented by an **attribute named `AnnotationDefault`** attached to the `method_info` entry corresponding to each **element method** of the annotation type.

This is the focus of this lesson: distinguishing the default storage structure from how an annotation is declared and from runtime value-reading behavior.

## 2. Defaults Reside in the *Annotation Type Declaration*, Not at Each Usage Site

Consider two usage sites:

```java
@RetryPolicy(name = "SEND_MAIL")
class MailTask {}

@RetryPolicy(name = "PROCESS_ORDER", attempts = 5)
class OrderTask {}
```

Both classes use **the same annotation type** but differ in their values:

| Element | Default in `RetryPolicy` type | `MailTask` | `OrderTask` |
| --- | --- | --- | --- |
| `name()` | None | `"SEND_MAIL"` (explicit) | `"PROCESS_ORDER"` (explicit) |
| `attempts()` | `3` | `3` (taken from default) | `5` (explicit) |
| `labels()` | `{"normal"}` | `{"normal"}` (taken from default) | `{"normal"}` (taken from default) |

**Important note:** an annotation usage site typically records only the **explicitly provided name–value pairs**. It does not need to copy every default value into the annotation on each class.

When reading annotation information, the runtime combines the **explicit values at the usage site** with the **defaults taken from the annotation type definition**. If an explicit value is present, that value is used; otherwise, the default is used when the element has a `default`.

By separating the two storage locations, a single default definition can serve many annotation sites without repeating the same metadata in every class file.

## 3. Which Attribute Is `AnnotationDefault` in the JVM Specification?

A JVM class file is organized into multiple structures, in which each method has a `method_info` entry and can have attributes (`attributes`). For an **annotation type**, each element takes a form similar to a parameterless abstract method without a method body.

When an element has `default`, the compiler generates a corresponding `AnnotationDefault` attribute on the `method_info` of that element itself. According to the structure in the JVM Specification, the logical content of this attribute is a **single `element_value`**, representing the default value.

This can be visualized as follows (an explanatory diagram, not a literal bytecode dump):

```text
RetryPolicy.class
  ├── annotation type RetryPolicy
  ├── method_info: name() : String
  │     └── no AnnotationDefault
  ├── method_info: attempts() : int
  │     └── AnnotationDefault
  │           └── element_value = 3
  └── method_info: labels() : String[]
        └── AnnotationDefault
              └── element_value = {"normal"}
```

Key points to remember:

1. The name `AnnotationDefault` refers to a **class-file attribute**, not a new annotation that you write as `@AnnotationDefault` in source code.
2. The attribute resides on an **element of the annotation type**, not automatically attached separately to a business method or a class using the annotation.
3. It describes a single default value for **one element**; if an annotation type has multiple default elements, each corresponding `method_info` has its own attribute.
4. An element **without a default** will not have an `AnnotationDefault` attribute just to represent "none"; Reflection represents that absence as `null` when calling `Method.getDefaultValue()`.

`AnnotationDefault` differs from `RuntimeVisibleAnnotations` and `RuntimeInvisibleAnnotations`. The latter two describe **annotation placements** recorded in the class file according to the retention policy; whereas `AnnotationDefault` describes **an element's default within the annotation type definition**.

### How Are Values Represented?

At the class-file level, `element_value` has a type marker (*tag*) and the appropriate data. Valid value forms for an annotation element include:

- Primitive types such as `int` and `boolean`.
- `String`.
- Enum constants.
- Class literals such as `String.class`, with element type `Class<?>` or a permitted variant.
- Nested annotations.
- One-dimensional arrays of valid forms.

For example, `int attempts() default 3;` has an integer default value; `String[] labels() default {"normal"};` is an array value containing a string element. Do not interpret `AnnotationDefault` as a snippet of Java code executed to compute a value: **no business expression is executed when querying the default**.

Annotation elements cannot use arbitrary types such as `List<String>` or `Map<String, String>` as return types. These restrictions are tied to the requirement of representing metadata consistently in the class-file format.

## 4. Using `javap -v` to Inspect `AnnotationDefault`

The JDK includes the `javap` tool, which reads and displays information in class files. After compiling the file containing the `RetryPolicy` definition, you can run:

```bash
javap -v RetryPolicy
```

In the verbose output of `javap -v`, look for the **`AnnotationDefault:`** line under the information for element methods that have defaults. The exact representation may vary across JDK versions, but you will see the default values attached to elements such as `attempts` and `labels`.

If you inspect the class **using** the annotation:

```bash
javap -v MailTask
```

You will find metadata for the `@RetryPolicy` usage. In a case retained until runtime, you can see a `RuntimeVisibleAnnotations` entry on `MailTask.class`. At the `MailTask` usage site, `name = "SEND_MAIL"` is recorded explicitly, whereas `attempts = 3` and `labels = {"normal"}` are typically **not copied into** the metadata of `MailTask.class` because they are supplied by `RetryPolicy`'s defaults.

Do not confuse the two:

- **`javap -v RetryPolicy`:** inspects **the defaults declared in the annotation type**, containing the `AnnotationDefault` of the element methods.
- **`javap -v MailTask`:** inspects **the values attached at the usage site**, via the class's annotation information.

Do not rely on line positions, constant pool offsets, or the exact full `javap` output format when explaining the concept: that is simply how the tool formats data, not mandatory source syntax. What needs to be compared is **which attribute lives in which class file, and what information it serves**.

## 5. Complete Java 17+ Example: Defaults, Overrides, and Reflection

Create a single file named **`AnnotationDefaultDemo.java`**. The example uses Java SE APIs and runs on JDK 17 or later.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.util.Arrays;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface RetryPolicy {
    String name();
    int attempts() default 3;
    String[] labels() default {"normal"};
    Class<?> handler() default Object.class;
}

@RetryPolicy(name = "SEND_MAIL")
class MailTask {}

@RetryPolicy(
    name = "PROCESS_ORDER",
    attempts = 5,
    labels = {"urgent", "paid"},
    handler = String.class
)
class OrderTask {}

public class AnnotationDefaultDemo {
    private static void inspect(Class<?> type) {
        RetryPolicy info = type.getAnnotation(RetryPolicy.class);

        if (info == null) {
            System.out.println(type.getSimpleName() + ": no policy");
            return;
        }

        System.out.println(type.getSimpleName()
                + ": name=" + info.name()
                + ", attempts=" + info.attempts()
                + ", labels=" + Arrays.toString(info.labels())
                + ", handler=" + info.handler().getSimpleName());
    }

    public static void main(String[] args)
            throws NoSuchMethodException {
        inspect(MailTask.class);
        inspect(OrderTask.class);

        Method name = RetryPolicy.class.getDeclaredMethod("name");
        Method attempts = RetryPolicy.class.getDeclaredMethod("attempts");
        Method labels = RetryPolicy.class.getDeclaredMethod("labels");
        Method handler = RetryPolicy.class.getDeclaredMethod("handler");

        System.out.println("Default name: "
                + (name.getDefaultValue() == null ? "(none)" : "unexpected"));
        System.out.println("Default attempts: "
                + attempts.getDefaultValue());
        System.out.println("Default labels: "
                + Arrays.toString((String[]) labels.getDefaultValue()));
        System.out.println("Default handler: "
                + ((Class<?>) handler.getDefaultValue()).getSimpleName());
    }
}
```

Compile and run in the directory containing the file:

```bash
javac -encoding UTF-8 AnnotationDefaultDemo.java
java AnnotationDefaultDemo
```

**Expected stdout, in exact order:**

```text
MailTask: name=SEND_MAIL, attempts=3, labels=[normal], handler=Object
OrderTask: name=PROCESS_ORDER, attempts=5, labels=[urgent, paid], handler=String
Default name: (none)
Default attempts: 3
Default labels: [normal]
Default handler: Object
```

Continue inspecting the bytecode after compilation succeeds:

```bash
javap -v RetryPolicy
javap -v MailTask
javap -v OrderTask
```

The program above has one `public class AnnotationDefaultDemo` matching the file name, while the remaining types are not `public`, so they can all be placed in a single file. No auxiliary programs or external classpaths beyond the JDK are needed.

### Explanation of the Observed Output

**`MailTask`:** supplies only `name = "SEND_MAIL"`. When calling `info.attempts()`, `info.labels()`, and `info.handler()`, the runtime provides the default values from `RetryPolicy`: `3`, `{"normal"}`, and `Object.class`. `Arrays.toString` formats the array as `[normal]`, and `Object.class.getSimpleName()` returns `Object`.

**`OrderTask`:** the usage site explicitly specifies all four elements; the element calls return `5`, `{"urgent", "paid"}`, and `String.class` respectively. These values **override** the default values at the usage site, but **do not alter the default definition** of the `RetryPolicy` type.

**`name.getDefaultValue()`:** this `Method` object describes `name()` in `RetryPolicy`. Because the element has no `default`, the API returns `null`, and the program prints `(none)`. `name()` still has an actual value at each usage site, because the compiler requires the author to provide it.

**`attempts.getDefaultValue()`:** always reads the default `3` from the annotation type declaration, even when `OrderTask` specifies `attempts = 5`. `getDefaultValue()` **does not read data from a specific usage site**.

**`labels.getDefaultValue()`:** returns the array value represented as a `String[]` object, so it can be cast and passed to `Arrays.toString(...)`.

**`handler.getDefaultValue()`:** returns a `Class<?>` representing `Object.class`; it does not instantiate `Object` or a business handler.

## 6. Two Different Reflection Questions

When you have a `Class<?>` object for a business class annotated with `@RetryPolicy`, you query the **actual value at the usage site**:

```java
RetryPolicy policy = MailTask.class.getAnnotation(RetryPolicy.class);
int actualAttempts = policy.attempts(); // 3 because it uses the default
```

When you have a `Method` object describing **an element method on the annotation type**, you query the **default declared by the author**:

```java
Method element = RetryPolicy.class.getDeclaredMethod("attempts");
Object declaredDefault = element.getDefaultValue(); // Integer containing 3
```

Comparison table:

| Question | Call | Returned Data |
| --- | --- | --- |
| Does `MailTask` have `@RetryPolicy`? | `MailTask.class.getAnnotation(RetryPolicy.class)` | A `RetryPolicy` object or `null` |
| What is the actual `attempts` value on `MailTask`? | `policy.attempts()` | `int` (here, `3`) |
| What is the default value defined for `attempts`? | `element.getDefaultValue()` | An `Object` boxing the value, here `Integer(3)` |
| Does `name` have a default? | `nameMethod.getDefaultValue()` | `null` if no default is declared |
| What are the names/types of the declared elements? | `RetryPolicy.class.getDeclaredMethods()` | A `Method[]` array representing the elements |

At the framework design level, reading `getDefaultValue()` is often useful for tools analyzing annotation contracts. For regular application logic, if you already have a concrete annotation instance, call the **element method directly** such as `policy.attempts()`: the runtime has already resolved the explicit or default value for you.

**Important limitation:** an actual value equal to the default (for example, `3`) does not tell you for sure whether the author **omitted the element** or explicitly wrote `attempts = 3`. Both approaches can return the same value via Reflection. To know the exact syntax in source code, you must inspect the source/explicit metadata with an appropriate tool rather than inferring it from a returned number.

## 7. When Are Default Values Evaluated?

Annotation default values are **not dynamically computed on each read** via a Java method body. Java only permits values that are valid under compile-time rules for elements, such as literals, eligible constant expressions, enum constants, class literals, nested annotations, and one-dimensional arrays thereof.

Valid example:

```java
@interface ReportOptions {
    int retryCount() default 2;
    String title() default "daily";
    Class<?> formatter() default String.class;
    String[] sections() default {"summary", "details"};
}
```

Invalid forms are illustrated below — **only to recognize compile-time errors, do not add them to the runnable file**:

```java
// INVALID: a default value cannot invoke a method
// to compute runtime data as shown below.
@interface BadTimestamp {
    String value() default java.time.Instant.now().toString();
}

// INVALID: the return type List is not a valid annotation element type.
@interface BadList {
    java.util.List<String> names() default {};
}
```

Elements cannot have parameters, cannot declare type parameters, and cannot have a `throws` clause; `default` only records metadata values. If you want to load settings dynamically from a database or environment, let the **consumer** process data outside the annotation instead of trying to put a runtime expression into `default`.

## 8. Defaults and Binary Compatibility

Because defaults are stored in the **annotation type declaration**, changing a default value in a library can change the **value read** by previously compiled client code if the usage site **does not specify the element explicitly**.

Logical example:

```java
// Initial library version:
@interface CacheRule {
    int ttlSeconds() default 60;
}

// A usage site:
@CacheRule
class ProductCache {}
```

If the library later changes the default to `ttlSeconds() default 120` and the application is run with the **new annotation type class file**, code using `@CacheRule` can receive `120` from calling `ttlSeconds()` without needing to write `ttlSeconds = 120` at every usage site. You must ensure that the actual set of loaded classes is compatible and of the right version, avoiding mixing old and new JARs.

Conversely, a usage site explicitly specifying `@CacheRule(ttlSeconds = 30)` retains its own value of `30`, unaffected by the new default.

Another possibility is adding a new element **with a default value** to a published annotation type; this usually allows older usage sites to continue getting a value for the new element when read. If you add a **required element without a default**, usage sites that have not provided a value may run into compilation issues, and when mixing incompatible binary versions, may encounter runtime errors such as `IncompleteAnnotationException` when accessing the missing element.

**API design principle:** treat changing a default as changing the **configuration behavior** of a published annotation, not a cosmetic source-code edit. When using annotations to drive business logic, document the impact on sites that do not specify an explicit value and run versioned integration tests.

## 9. `AnnotationDefault`, `@Retention`, and Runtime Presence

All three concepts are related, yet not identical:

1. **`AnnotationDefault`:** a class-file attribute on an element of an annotation type, describing the declared default value.
2. **`@Retention`:** a meta-annotation determining whether annotation usages are retained until `SOURCE`, `CLASS`, or `RUNTIME`.
3. **`getAnnotation(...)`:** a Reflection API method used to retrieve an annotation on a given program element, which only sees matching annotations retained until runtime.

For example, the declaration:

```java
// Illustrates an annotation with SOURCE retention.
@java.lang.annotation.Retention(
    java.lang.annotation.RetentionPolicy.SOURCE
)
@interface CompileHint {
    int limit() default 10;
}
```

In a standard compilation environment, the default `10` is part of the annotation type definition and can be represented via `AnnotationDefault` in `CompileHint.class`. However, **placements of `@CompileHint` on other classes** will be omitted from runtime metadata by the compiler due to `SOURCE` retention.

Do not infer that "an annotation has a default so Reflection can always read its usage sites" or that "with `SOURCE` retention, the annotation type has no class file at all." An annotation type is a separate Java declaration that can be compiled into a class file; the retention policy governs **the existence of annotation instances at usage sites**, not whether an annotation type definition exists in the project.

If you want to read the annotation object on a class via Reflection, you need `@Retention(RUNTIME)` and metadata attached at the right target. If you want to read the default **of an element method**, select the `Method` belonging to the annotation type and call `getDefaultValue()`. These are two different operations.

## 10. Common Mistakes

1. **Confusing `AnnotationDefault` with `@AnnotationDefault` syntax.** `AnnotationDefault` is the name of a class-file attribute; Java source code declares defaults with the `default` keyword inside `@interface`.
2. **Assuming every class using an annotation stores a copy of the defaults.** Usage sites typically only need to store explicitly specified pairs; defaults belong to the annotation type definition.
3. **Calling `getDefaultValue()` on a business method's `Method`.** You must obtain the `Method` describing **an element of the annotation type**, for example `RetryPolicy.class.getDeclaredMethod("attempts")`.
4. **Thinking `getDefaultValue()` returns the actual value at a usage site.** It returns the declared default value. Read the actual value via the annotation instance by calling `policy.attempts()`.
5. **Forgetting elements without a default.** `getDefaultValue()` returns `null`; this is not a valid value to assign to an annotation element at a usage site.
6. **Misunderstanding retention.** `AnnotationDefault` can still be present in the annotation type's class file even if the annotation is marked with `SOURCE` retention; annotation usages are separate data.
7. **Confusing an annotation's `default` with an interface's `default method`.** An annotation element only declares a metadata default value; there is no method body to execute code.
8. **Assuming changing a default does not affect already compiled code.** If a usage site omits the element, the value read can depend on the active annotation type definition.
9. **Relying on `javap -v` to assume the application loaded the right class version.** The output of the inspected file and the class actually loaded by the class loader can differ if the classpath/module path contains multiple versions.
10. **Failing to handle errors when metadata/binaries are out of sync across versions.** Errors such as `IncompleteAnnotationException`, `TypeNotPresentException`, or `EnumConstantNotPresentException` can occur in their respective scenarios; proper version management and testing are necessary.

## 11. Self-Check Exercises

**Exercise 1.** `int attempts() default 3;` is compiled. Which class file and which structure does `AnnotationDefault` reside in?

**Answer:** In the **annotation type's** `RetryPolicy.class` file, attached to the `method_info` entry describing the `attempts()` element, not automatically on every class using the annotation.

**Exercise 2.** A class is annotated with `@RetryPolicy(name = "X")`. Why does `info.attempts()` return `3` even though `attempts = 3` is not present at the annotation site?

**Answer:** The runtime applies the default declared on the annotation type when the element is not explicitly provided.

**Exercise 3.** What is the difference between `info.attempts()` and `RetryPolicy.class.getDeclaredMethod("attempts").getDefaultValue()`?

**Answer:** The first call reads the value **at the usage site** (including any override if present) and returns `int`. The second call reads the **default at the element definition** and returns `Object` (here wrapping an `Integer`).

**Exercise 4.** Why does `name.getDefaultValue()` return `null` while `info.name()` can still return a string?

**Answer:** `name()` has no default, so the annotation user must provide an explicit value, such as `name = "SEND_MAIL"`.

**Exercise 5.** Which JDK tool allows inspecting the `AnnotationDefault` attribute and annotation metadata in `.class` files?

**Answer:** `javap -v RetryPolicy` to view the element definitions and `javap -v MailTask` to compare the usage.

**Exercise 6.** Does changing the default from `3` to `8` change the value of `@RetryPolicy(name = "X", attempts = 5)`?

**Answer:** No, not for the `attempts` element at that usage site, because `5` was explicitly assigned.

**Exercise 7.** Does `@Retention(SOURCE)` prevent the compiler from emitting `AnnotationDefault` for elements in the annotation type definition?

**Answer:** No. `SOURCE` governs the retention of **annotation placements**, not the removal of default definitions inside the annotation type.

**Exercise 8.** Is `int ttl() default loadConfig();` valid if `loadConfig()` is a method that reads a file?

**Answer:** No. An annotation element's default value must be of a form accepted by Java at compile time; it cannot be dynamically computed by an arbitrary method call.

**Key takeaway:** **`AnnotationDefault` is the bytecode trace of the default value belonging to the *element declaration of the annotation type*.** Explicitly written values belong to the *annotation usage site*. Reflection retrieves the actual value through the element method, whereas `Method.getDefaultValue()` reads the definition's default; the two operations are related but not interchangeable.
