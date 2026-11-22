# Method.getDefaultValue: Reading Default Values of Annotation Elements via Java Reflection

## 1. Concept and purpose

An annotation is declared with `@interface`. Each element (*annotation element*) is written as a **zero-parameter** method declaration, such as `int retries()` or `String name()`. An element can declare a **default value** using the `default` keyword:

```java
@interface Config {
    String name();                  // Required when using the annotation.
    int retries() default 3;       // Default value is 3.
    boolean enabled() default true;
}
```

In Reflection, each element is represented by a `java.lang.reflect.Method` object. The method:

```java
Object defaultValue = method.getDefaultValue();
```

reads **the default value declared on that annotation element itself** represented by `Method`, without needing to instantiate an object of the annotated class.

**Most important rules:**

- If `Method` represents an annotation element **that declares `default`**, `getDefaultValue()` returns the corresponding default value as an `Object`.
- If the element **has no default value**, the result is **`null`**.
- If `Method` **does not represent an element declared directly in an annotation type**, the result is also **`null`**.
- If the element type is primitive, the returned value is **boxed** into the corresponding wrapper. For example, `int retries() default 3` → `Integer.valueOf(3)`.
- `getDefaultValue()` **does not retrieve the overridden value at an annotation usage site**. To read the effective value of an annotation attached to a class/method, read the annotation object.

This API is useful when building metadata readers, configuration checkers, annotation documentation generators, validation tools, scanners, or Reflection-based frameworks.

## 2. Distinguishing default value from effective value

Consider:

```java
@Retention(RetentionPolicy.RUNTIME)
@interface Task {
    String name();
    int retries() default 3;
}

@Task(name = "backup", retries = 7)
class BackupTask {}

@Task(name = "cleanup")
class CleanupTask {}
```

For element `Task.retries()`:

- **Declared default value:** `3`. Read via `Task.class.getDeclaredMethod("retries").getDefaultValue()`.
- **Effective value on `BackupTask`:** `7`, because the usage site overrode it.
- **Effective value on `CleanupTask`:** `3`, because the usage site omitted `retries` so Java applied the default.

```java
Method retries = Task.class.getDeclaredMethod("retries");
Object declaredDefault = retries.getDefaultValue(); // Integer(3)

Task backup = BackupTask.class.getAnnotation(Task.class);
int usedByBackup = backup.retries(); // 7

Task cleanup = CleanupTask.class.getAnnotation(Task.class);
int usedByCleanup = cleanup.retries(); // 3
```

The snippets above are **illustrative code** and require `import java.lang.annotation.*` and `java.lang.reflect.*`. A complete standalone program appears in section 4.

`@Retention(RetentionPolicy.RUNTIME)` is required to retrieve the **attached annotation** via `getAnnotation(...)` while the program runs. Meanwhile, `getDefaultValue()` reads metadata on the `Method` of the annotation type itself; it is not an operation retrieving an annotation attached to a usage element.

**You cannot rely on `getDefaultValue()` to determine whether an effective value at a usage site was written explicitly or inherited from the default.** If the author explicitly writes `retries = 3`, the effective value is still `3`.

## 3. API, return values, and data types

Java SE 17 signature:

```java
public Object getDefaultValue()
```

| Element declaration | `getDefaultValue()` value | Runtime type of result |
| --- | --- | --- |
| `int retries() default 3;` | `3` | `Integer` |
| `boolean enabled() default true;` | `true` | `Boolean` |
| `String label() default "java";` | `"java"` | `String` |
| `String[] tags() default {"a","b"};` | Array containing `"a"`, `"b"` | `String[]` |
| `Class<?> handler() default String.class;` | `String.class` | `Class<?>` |
| `Priority priority() default Priority.HIGH;` | `Priority.HIGH` | Enum `Priority` |
| `Meta meta() default @Meta;` | Default annotation object | Annotation type `Meta` |
| `String name();` | `null` | No default value |

Because the return type is `Object`, you must **check/pair with `method.getReturnType()`** before casting. Example:

```java
Method method = Config.class.getDeclaredMethod("retries");
Object value = method.getDefaultValue();

if (value instanceof Integer retries) {
    System.out.println(retries);
}
```

The element method returns `int`, yet `getDefaultValue()` returns an `Integer`. For a primitive array return type, such as `int[] levels() default {1,2}`, the returned value is **`int[]`**, not `Integer[]`: boxing applies only to **a single primitive value**, not transforming an entire array.

Valid annotation element types per Java language rules include primitives (excluding `void`), `String`, `Class` or permitted parameterized forms, enums, annotation types, and one-dimensional arrays of those types. Do not use arbitrary element types like `List<String>` or `Map`, and `null` cannot be used as a valid default value.

## 4. Runnable Java 17+ example and exact stdout

Save the following program as **`AnnotationDefaultDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.util.Arrays;

public class AnnotationDefaultDemo {
    enum Priority { LOW, HIGH }

    @Retention(RetentionPolicy.RUNTIME)
    @interface Meta {
        String author() default "team";
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface Config {
        String name();                              // No default.
        int retries() default 3;
        boolean enabled() default true;
        String[] tags() default {"core", "reflection"};
        Class<?> handler() default String.class;
        Priority priority() default Priority.HIGH;
        Meta meta() default @Meta;
    }

    @Config(name = "service", retries = 7, tags = {"prod"})
    static class Service {}

    @Config(name = "backup")
    static class Backup {}

    interface Greeter {
        default String greet() {
            return "hi";
        }
    }

    public static void main(String[] args) throws Exception {
        Method name = Config.class.getDeclaredMethod("name");
        Method retries = Config.class.getDeclaredMethod("retries");

        System.out.println("name default: " + name.getDefaultValue());

        Object retryDefault = retries.getDefaultValue();
        System.out.println("retries default: " + retryDefault
                + " (" + retryDefault.getClass().getSimpleName() + ")");

        System.out.println("enabled default: "
                + Config.class.getDeclaredMethod("enabled").getDefaultValue());

        System.out.println("tags default: " + Arrays.toString(
                (String[]) Config.class.getDeclaredMethod("tags")
                        .getDefaultValue()));

        System.out.println("handler default: "
                + ((Class<?>) Config.class.getDeclaredMethod("handler")
                        .getDefaultValue()).getSimpleName());

        System.out.println("priority default: "
                + Config.class.getDeclaredMethod("priority").getDefaultValue());

        Meta nested = (Meta) Config.class.getDeclaredMethod("meta")
                .getDefaultValue();
        System.out.println("meta.author default: " + nested.author());

        Config service = Service.class.getAnnotation(Config.class);
        Config backup = Backup.class.getAnnotation(Config.class);

        System.out.println("service retries: " + service.retries());
        System.out.println("backup retries: " + backup.retries());
        System.out.println("service tags: "
                + Arrays.toString(service.tags()));
        System.out.println("backup tags: "
                + Arrays.toString(backup.tags()));

        System.out.println("retries via invoke: " + retries.invoke(service));

        Method defaultMethod = Greeter.class.getMethod("greet");
        System.out.println("interface default method isDefault: "
                + defaultMethod.isDefault());
        System.out.println("interface default method getDefaultValue: "
                + defaultMethod.getDefaultValue());

        System.out.println("ordinary method getDefaultValue: "
                + String.class.getMethod("length").getDefaultValue());
    }
}
```

Compile and run with Java 17 or later:

```bash
javac AnnotationDefaultDemo.java
java AnnotationDefaultDemo
```

Stdout:

```text
name default: null
retries default: 3 (Integer)
enabled default: true
tags default: [core, reflection]
handler default: String
priority default: HIGH
meta.author default: team
service retries: 7
backup retries: 3
service tags: [prod]
backup tags: [core, reflection]
retries via invoke: 7
interface default method isDefault: true
interface default method getDefaultValue: null
ordinary method getDefaultValue: null
```

### Explaining notable lines

1. `Config.name()` does **not** declare `default`, so `name.getDefaultValue()` returns `null`. The `name` element is still required when using `@Config`.
2. `Config.retries()` declares `default 3`, so the result is an `Integer` wrapper object with value `3`.
3. The default array `tags` is `String[]`. Use `Arrays.toString` to display contents; calling `toString()` directly on an array will not yield the desired element-listing format.
4. The default of `Class<?> handler()` is a `Class`, of `Priority priority()` is an enum value, and of `Meta meta()` is the corresponding annotation object.
5. On `Service`, the effective `retries` value is `7` (overridden). On `Backup`, the effective value is `3` (default).
6. `retries.invoke(service)` invokes the element on the **annotation instance object** and returns the effective value `7`; it **differs from** `retries.getDefaultValue()`, which always describes the element's default.
7. `Greeter.greet()` is an **interface default method** with a method body; `isDefault()` returns `true`, yet `getDefaultValue()` still returns `null`. The two meanings of *default* are unrelated.
8. `String.length()` is an ordinary method, not an annotation element; `getDefaultValue()` returns `null`.

## 5. You must obtain the Method of the annotation type

Suppose `@Config` is attached to `Service`; three mistakes must be avoided:

```java
// Correct: get the element declared in the annotation type.
Method element = Config.class.getDeclaredMethod("retries");
Object defaultValue = element.getDefaultValue();

// Correct: get the annotation instance on the usage site.
Config annotation = Service.class.getAnnotation(Config.class);
int actual = annotation.retries();

// Wrong purpose: looking up "retries" on class Service.
// Service.class.getDeclaredMethod("retries") normally does not exist.
```

An annotation instance may be implemented at runtime via proxies or internal techniques, but to read defaults you should use **`Config.class`** or `annotation.annotationType()` and `getDeclaredMethod(elementName)`, rather than inferring the implementation structure of the annotation object.

To inspect all defaults of an annotation type, use:

```java
// Illustrative utility method; place inside a Java class with necessary imports.
static void printDefaults(Class<? extends java.lang.annotation.Annotation> type) {
    for (java.lang.reflect.Method element : type.getDeclaredMethods()) {
        Object value = element.getDefaultValue();

        System.out.println(element.getName()
                + " : " + element.getReturnType().getTypeName()
                + " => " + (value == null ? "<required>" : value));
    }
}
```

This is **illustrative code**, not a program with `main`. Production metadata processors should add formatters for **arrays** using `Arrays.toString` or `Arrays.deepToString` based on data type, and **sort** element names for stable output (because `getDeclaredMethods()` guarantees no order).

To avoid cast errors, classify `value` with `instanceof`, combine with `element.getReturnType()`, and handle `null` before unpacking.

## 6. Null means “no default declared”, not a default value of null

An annotation element **cannot validly have** `default null` in Java source code. Therefore:

```java
@interface Notice {
    String message();                // No default.
    String optional() default "";    // Default is empty string.
    String[] tags() default {};      // Default is empty array.
}
```

Distinction table:

| Declaration | `getDefaultValue()` | Has default? |
| --- | --- | --- |
| `String message();` | `null` | No |
| `String optional() default "";` | `""` | Yes |
| `String[] tags() default {};` | `String[]` array of length `0` | Yes |
| `int count() default 0;` | `Integer(0)` | Yes |
| `boolean active() default false;` | `Boolean.FALSE` | Yes |

Therefore, **do not** use checks such as `if (!Boolean.TRUE.equals(defaultValue))` to conclude a default is missing, because `false` is a completely valid default. Simple rule: `value == null` means no default exists under `getDefaultValue()`'s contract.

Note that `getDefaultValue()` called on an ordinary `Method` also returns `null`; if you need to distinguish “required element” from “not an annotation element”, check `method.getDeclaringClass().isAnnotation()`.

## 7. Do not confuse with other “default” concepts

| Phrase/API | Meaning | Related to `Method.getDefaultValue()`? |
| --- | --- | --- |
| `@interface X { int n() default 3; }` | Default value of an annotation element | **Yes**, returns boxed `3` |
| `interface X { default void run() {} }` | Interface default method with body | **No**, `getDefaultValue()` is normally `null` |
| `Method.isDefault()` | Whether a method is an interface default method | Completely **different** API |
| `@Retention(RUNTIME)` | Annotation retained for runtime access at usage sites | Does not create a default; useful for `getAnnotation` |
| `@Target(TYPE)` | Restricts where the annotation can be used | Does not determine default values |
| `Class.getAnnotation(X.class)` | Returns the annotation instance attached to the element | Reads **effective** value via `annotation.element()` |
| `Method.invoke(annotationInstance)` | Invokes element method on an annotation instance | Returns **effective** value; not merely default |

**Note on `@Retention`:** When a tool wants to read an **attached** annotation at runtime, declare the annotation with `@Retention(RetentionPolicy.RUNTIME)`. If only the metadata of an annotation type is loaded, Reflection can read information about the type's own element methods and defaults without obtaining an annotation instance at a usage site.

## 8. Default rules in annotations and compatibility

Annotations have several specific constraints compared to ordinary Java methods:

- Annotation elements accept no parameters and declare no `throws`.
- Default values must be expressions matching the element type and Java's annotation constant/value rules. Arbitrary runtime values like `default new java.util.Date()` cannot be used.
- Default arrays describe only **one-dimensional arrays of valid element types**; to represent complex structures, consider nested annotations or another schema design.
- Elements without `default` must be provided when using the annotation in source code, unless corresponding providing syntax exists.
- Defaults belong to the **annotation type declaration**, rather than being stored repeatedly as an explicit value at every annotation usage site.

An important consequence during library evolution: if `default 3` is changed to `default 5` in a new version of an annotation, usage sites that **do not explicitly declare `retries`** can receive the new effective value when running against the new annotation version. Conversely, sites that wrote `retries = 7` continue using `7` per their usage declaration. Hence changing a default can be a **behavioral change**, even without editing every annotation usage site.

When writing frameworks or scanners: treat default values as part of the configuration contract; clearly document versions/policies if defaults affect business behavior. Do not modify `Method` or treat the result of `getDefaultValue()` as a runtime setting that can be overridden via Reflection.

## 9. Common mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| `getDefaultValue()` returns `null` for `name()` | Required element, no default declared | Recognize missing default; read from annotation instance if attached |
| Returns `3` even though annotation usage sets `retries = 7` | Reading declaration default, not effective value | Use `annotation.retries()` or `Method.invoke(annotation)` |
| `getDefaultValue()` returns `null` for an interface default method | Interface method `default` differs from annotation default | Use `Method.isDefault()` to identify default methods |
| `ClassCastException` when casting default of `int` to `String` | Primitive is boxed into `Integer` | Check `getReturnType()` and `instanceof` before casting |
| Printing `tags` array outputs `[Ljava.lang.String;@...` | Calling `Object.toString()` on array | Use `Arrays.toString((String[]) value)` |
| Thinking `default ""` or `default {}` means no default | Empty values are still valid defaults | Only check `getDefaultValue() == null` |
| `NoSuchMethodException` when looking up element via target class | Element belongs to the **annotation type**, not the annotated class | Look up via `Config.class.getDeclaredMethod(...)` |
| `getAnnotation(Config.class)` returns `null` | Annotation absent / not runtime-retained / wrong location | Check `@Retention(RUNTIME)` and declaration location |
| Default containing `Class` is unavailable when reading | Missing type dependency or class-loading failure | Per API docs, `getDefaultValue()` can throw `TypeNotPresentException` |
| Element iteration results change order | `getDeclaredMethods()` does not guarantee order | Sort by name when outputting reports or serializing |

### Errors when classpath or binary metadata become incompatible

The Java SE 17 documentation for `Method.getDefaultValue()` notes `TypeNotPresentException` if a `Class`-typed default value references a type that can no longer be loaded. In addition, when analyzing annotations from version-mismatched libraries, linkage/metadata-format errors or errors accessing annotation instance values can occur. Do not assume every annotation in a plugin environment has valid binary metadata.

In ordinary applications, **there is no need to catch** rare errors to read an annotation controlled by the project itself; in general bytecode/library scanning tools, decide an intentional error-handling policy and provide details about the problematic annotation type/element.

## 10. Knowledge self-check

1. **What does `int timeout() default 0;` return via `getDefaultValue()`?** An `Integer` object with value `0`, not `null`.
2. **What does `String id();` return?** `null`, because there is no default; usage sites must declare `id` when required.
3. **Does `@Config(retries = 9)` change `retries`'s `getDefaultValue()` to 9?** No; the default on the annotation type does not change. The effective value at the usage site is `9`.
4. **Does `String[] tags() default {};` have a default?** Yes; it returns an empty array, distinct from `null`.
5. **Does an interface default method with `Method.isDefault() == true` mean `getDefaultValue()` is non-`null`?** No, the two APIs serve two different concepts.
6. **To see all defaults on an `@interface`, what do you do?** Iterate `annotationType.getDeclaredMethods()`, call `getDefaultValue()` on each `Method`, check `null`, and format appropriately by type.
7. **To get the final effective value applied on an annotated class, what do you do?** Obtain the annotation via `getAnnotation(...)`, then invoke the element on the instance; do not read only `Method.getDefaultValue()`.

**Key takeaway:** `Method.getDefaultValue()` retrieves the **declared default value of an annotation element**, returning `null` if there is no default or it is not an annotation element. It does not read values overridden on an annotated target, and is unrelated to interface `Method.isDefault()`.

References: [Java SE 17 — Method.getDefaultValue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#getDefaultValue()), [JLS §9.6.2 — Defaults for Annotation Type Elements](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.2), [Java SE 17 — Annotation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Annotation.html).