# Defining an Annotation Type with `@interface` in Java

## 1. What Is an Annotation Type?

An **annotation** in Java is descriptive information (*metadata*) attached to program declarations, such as a class, method, field, or parameter; since Java 8, annotations can also be applied at certain type usage locations (*type use*). An annotation can be read and processed by the compiler, code generation tools, frameworks, or programs via reflection.

An **annotation type** is the definition for concrete annotations. Java uses the compound keyword `@interface` to declare this type:

```java
@interface Author {
    String name();
}
```

The declaration above creates an annotation type named `Author` with one required element named `name`. It can then be used as follows:

```java
@Author(name = "An")
class BookService {
}
```

In this example, `@interface Author` **defines the structure**; `@Author(name = "An")` **provides values for one usage** of that structure. The `@` sign when applying an annotation and the `@interface` syntax when defining one serve two different roles.

Annotations are commonly used for configuration and tooling, such as marking test methods, describing URL mapping rules, or providing metadata to annotation processors. **Attaching an annotation alone does not automatically create new behavior**: a compiler, annotation processor, framework, or Java code must read the annotation and execute the corresponding logic.

## 2. Basic Declaration Structure

Core syntax:

```java
@interface TenAnnotation {
    KieuTraVe tenPhanTu();
    KieuTraVe tenPhanTuKhac() default giaTriMacDinh;
}
```

Components:

- `@interface` is the syntax for declaring an *annotation interface* (commonly called an *annotation type*).
- `TenAnnotation` is the type name, following Java identifier rules; by convention, type names use PascalCase.
- `tenPhanTu()` is an **annotation element**: it looks like a no-argument method, but is used to describe an annotation value.
- The return type of the element determines the valid value type at the usage site.
- `default` provides a default value; an element without `default` must be supplied when applying the annotation.
- A `;` terminates each element declaration; there is no method body.

Example:

```java
@interface JobInfo {
    String code();
    int maxRetries() default 3;
    boolean active() default true;
}
```

Usage:

```java
@JobInfo(code = "IMPORT")
class ImportJob {}

@JobInfo(code = "EXPORT", maxRetries = 5, active = false)
class ExportJob {}
```

`code()` is required, while `maxRetries()` and `active()` can be omitted because they already have defaults. Omitting them does not cause Java to automatically infer values from field names or other variables.

### Quick Comparison with a Regular Interface

```java
interface Runner {
    void run();
}

@interface RunInfo {
    String name();
}
```

| Criterion | `interface Runner` | `@interface RunInfo` |
|---|---|---|
| Purpose | Declares a behavioral contract for classes to implement | Defines a metadata type with elements |
| Usage | `class X implements Runner` | `@RunInfo(name = "demo")` |
| Typical members | Abstract/default/static methods | Annotation elements with restricted types and defaults |
| Direct instantiation | Cannot `new Runner()`; can create an implementing class | Cannot `new RunInfo()`; typically the compiler represents the annotation and tools read it |
| Relationship with `Annotation` | Not automatically an annotation type | An annotation interface implicitly has `java.lang.annotation.Annotation` as a superinterface |

An annotation type is a specialized form of interface, but **it does not declare `extends Annotation`** and also does not declare `implements`. Writing `@interface X extends Annotation` is invalid language syntax. An annotation interface cannot have type parameters (`@interface Meta<T>` is invalid).

## 3. Allowed Element Types in Java

The valid return type of an annotation element belongs to one of the following categories:

1. Primitive types: `boolean`, `byte`, `short`, `int`, `long`, `char`, `float`, `double`.
2. `String`.
3. `Class` or an appropriate `Class<?>` / `Class<? extends SomeType>` form.
4. An `enum` type.
5. Another annotation type.
6. A **one-dimensional** array of any of the types above.

Standalone example:

```java
enum Severity {
    LOW, MEDIUM, HIGH
}

@interface Endpoint {
    String path();
    String[] roles() default {};
    int timeoutSeconds() default 30;
    Severity severity() default Severity.LOW;
    Class<?> handler() default Object.class;
}

@interface Module {
    String name();
    Endpoint[] endpoints() default {};
}
```

In `Module`, `Endpoint[]` is an array of an annotation type, which is valid because `Endpoint` is an annotation type. The curly braces `{}` in `default {}` represent an empty array.

Types that are **invalid** for elements:

```java
import java.util.List;

@interface InvalidElements {
    Object data();           // Invalid: Object
    List<String> tags();     // Invalid: List
    int[][] matrix();        // Invalid: two-dimensional array
    void perform();          // Invalid: void
}
```

The example above intentionally does not compile and is only used to identify errors. Annotation elements do not allow arbitrary object types or collections such as `List`/`Map`; in many cases, `String[]`, enums, or nested annotations can be used to represent structured configuration.

You cannot use `null` as an element value or as a `default` value. If you need to represent "unspecified", design a meaningful default such as an empty string, an `UNSPECIFIED` enum constant, an empty array, or a clearly documented sentinel value.

## 4. Declaring Required Elements and Elements with `default`

An element has the form:

```java
String name();                        // Required
int priority() default 1;             // Has default
String[] labels() default {"general"}; // Has default
```

The `default` keyword goes **inside the annotation type definition**, not at the annotation usage site:

```java
@interface Task {
    String id();
    String description() default "";
    int[] allowedCodes() default {200};
}

@Task(id = "T-01")
class TaskOne {}

@Task(id = "T-02", description = "Import", allowedCodes = {200, 201})
class TaskTwo {}
```

`@Task(id = "T-01")` is valid because the compiler uses the defaults for `description` and `allowedCodes`. Cases such as `@Task`, `@Task()`, or `@Task(description = "missing id")` are all missing `id` and cause a compilation error.

Notes:

- `default` is a **compile-time constant value** according to annotation element rules. Do not write `default null`, and do not call arbitrary methods to generate defaults.
- The default value is part of the metadata in the annotation type and is used when the element is not given an explicit value at the usage site.
- Changing a `default` value can alter the value that a program reads from previously compiled annotations that omitted that element. Therefore, changing `default` is a meaningful behavioral change and requires compatibility considerations.

## 5. Declaring an Element Named `value` and Shorthand Syntax

Java provides a convenient shorthand syntax when an annotation has an element named exactly `value`:

```java
@interface Label {
    String value();
}
```

The following two usages are equivalent:

```java
@Label("stable")
class First {}

@Label(value = "stable")
class Second {}
```

For an element with any name other than `value`, specifying the name is mandatory:

```java
@interface Path {
    String location();
}

@Path(location = "/api")
class ApiPath {}
```

`@Path("/api")` is invalid because `Path` does not declare `value()`. If the annotation has additional elements, explicitly write `value = ...` when passing multiple elements:

```java
@interface Feature {
    String value();
    boolean enabled() default true;
}

@Feature("search")
class SearchFeature {}

@Feature(value = "billing", enabled = false)
class BillingFeature {}
```

`@Feature("billing", enabled = false)` is not accepted syntax for mixing an unnamed value with `name = value` pairs.

## 6. Element Values: Constants, Enums, Classes, and Nested Annotations

Being able to declare an element's type does not mean you can pass just any Java expression. For example:

```java
enum Scope {
    LOCAL, GLOBAL
}

@interface RetryRule {
    int limit() default 2;
}

@interface ComponentInfo {
    String name();
    Scope scope() default Scope.LOCAL;
    Class<?> implementation() default Object.class;
    RetryRule retry() default @RetryRule;
    String[] aliases() default {};
}
```

A valid usage:

```java
@ComponentInfo(
    name = "order",
    scope = Scope.GLOBAL,
    implementation = String.class,
    retry = @RetryRule(limit = 4),
    aliases = {"checkout", "purchase"}
)
class OrderComponent {}
```

Key points to remember:

- `String` and numeric/primitive values must be an appropriate **constant expression**; literals or `static final` constants declared with a constant expression satisfy this requirement.
- `enum` values must be an enum constant such as `Scope.GLOBAL`, not the string `"GLOBAL"`.
- `Class` accepts a class literal such as `String.class`, not an instance like `new String()`.
- An element of an annotation type accepts an annotation literal such as `@RetryRule(limit = 4)`.
- Arrays are typically passed using `{...}`. For an array-typed element, Java also accepts a single value of the element's component type in annotation syntax, for example `aliases = "checkout"`.
- Do not pass the result of a runtime method call as an annotation value.

An **invalid** example:

```java
@interface Version {
    String number();
}

class InvalidVersion {
    static String current() { return "2.0"; }

    @Version(number = current()) // Invalid: a method call is not a constant expression
    void execute() {}
}
```

You can replace it with an appropriate constant:

```java
class ValidVersion {
    static final String CURRENT = "2.0";

    @Version(number = CURRENT)
    void execute() {}
}
```

## 7. Common Meta-Annotations Applied to `@interface` Definitions

A **meta-annotation** is an annotation placed on an annotation type to specify metadata for that annotation type itself. The most common ones are `@Retention` and `@Target` from `java.lang.annotation`.

### `@Retention`: How Long Does the Annotation Exist?

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface Traceable {
    String category() default "general";
}
```

The three policies:

| Policy | Meaning |
|---|---|
| `RetentionPolicy.SOURCE` | Present in source code; not retained by the compiler in the class file |
| `RetentionPolicy.CLASS` | Recorded in the class file; not required to be available via reflection at runtime |
| `RetentionPolicy.RUNTIME` | Present in the class file and can be read via Java reflection at runtime |

If `@Retention` is not declared, the default is **`RetentionPolicy.CLASS`**. Use `RUNTIME` when you actually need calls like `SomeClass.class.getAnnotation(...)`. Compile-time annotation processors do not require `RUNTIME` retention to inspect annotations in the source code being processed.

### `@Target`: Where Can the Annotation Be Applied?

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target({ElementType.TYPE, ElementType.METHOD})
@interface Audited {
}
```

`@Audited` can be used on type and method declarations; it cannot automatically be used on fields unless `FIELD` is included in the list. Some commonly used `ElementType` values:

| Value | Usage location |
|---|---|
| `TYPE` | Class, interface, enum, or annotation type declarations |
| `FIELD` | Field declarations, including enum constants |
| `METHOD` | Method declarations |
| `PARAMETER` | Parameter declarations |
| `CONSTRUCTOR` | Constructor declarations |
| `ANNOTATION_TYPE` | Annotation type declarations |
| `TYPE_USE` | Type uses, such as `List<@NonNull String>` |
| `TYPE_PARAMETER` | Type parameter declarations, such as `class Box<@Marker T>` |

`@Target` does not mean the annotation executes by itself at that location; it simply tells the compiler where it may be applied. If `@Target` is omitted, Java applies a broader default set of declaration locations; when you intend to create a *type annotation*, explicitly declare `TYPE_USE`.

### Other Meta-Annotations

- `@Documented` instructs the Javadoc tool to include the annotation in the generated API documentation where appropriate.
- `@Inherited` allows certain class-level annotations to be considered inherited from a superclass through Java's annotation query mechanism; it does **not** automatically propagate method or interface annotations.
- `@Repeatable` allows the same annotation to appear multiple times at a suitable location, backed by a properly declared *container annotation type*.

When first learning `@interface`, make sure you master element declarations, `default`, `@Target`, and `@Retention` first; `@Repeatable` and `@Inherited` are additional mechanisms depending on your needs.

## 8. Complete Java 17+ Example: Defining and Reading an Annotation

Create a file named **`AnnotationDefinitionDemo.java`** with the following complete code:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface TaskSpec {
    String id();
    int retries() default 2;
    String[] tags() default {};
}

@TaskSpec(id = "sync")
class SyncTask {}

@TaskSpec(id = "backup", retries = 4, tags = {"io", "critical"})
class BackupTask {}

public class AnnotationDefinitionDemo {
    public static void main(String[] args) {
        printSpec(SyncTask.class);
        printSpec(BackupTask.class);
    }

    private static void printSpec(Class<?> type) {
        TaskSpec spec = type.getAnnotation(TaskSpec.class);
        System.out.println(spec.id() + " | " + spec.retries()
                + " | " + Arrays.toString(spec.tags()));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac AnnotationDefinitionDemo.java
java AnnotationDefinitionDemo
```

Output:

```text
sync | 2 | []
backup | 4 | [io, critical]
```

Step-by-step explanation:

1. `@interface TaskSpec` defines three elements: a required `id`, `retries` defaulting to `2`, and `tags` defaulting to an empty array.
2. `@Target(ElementType.TYPE)` restricts usage to type declarations.
3. `@Retention(RetentionPolicy.RUNTIME)` retains the metadata so `getAnnotation` can read it while the program is running.
4. `@TaskSpec(id = "sync")` supplies only the required value. When read from `SyncTask`, `retries()` returns `2` and `tags()` returns an empty array by default.
5. `BackupTask` provides explicit values, so reading it returns `4` and the list `["io", "critical"]`; `Arrays.toString` formats the array as `[io, critical]`.

**Key takeaway:** `@interface` defines the data contract; `@TaskSpec(...)` attaches the data; reflection in this example is **the component that reads the data**. The annotation does not call `printSpec` or perform the "sync/backup" work on its own.

## 9. Common Mistakes When Defining Custom Annotations

The following snippets are **intentionally invalid examples** and are not meant to be placed in the runnable program from the previous section.

### Incomplete Element Syntax

```java
@interface BadSyntax {
    String name()      // Invalid: missing ;
    int priority(1);   // Invalid: annotation elements do not accept parameters
}
```

The correct syntax is `String name();` and `int priority();` (or `int priority() default 1;`). Annotation elements have no parameters, no method body, and no `throws` clause.

### Choosing a Disallowed Return Type

```java
@interface WrongType {
    java.util.List<String> names(); // Invalid: List is not a valid element type
}
```

Replace it with `String[] names();` if appropriate for the domain logic.

### Naming Elements Incorrectly or Mistyping Them at Usage Sites

```java
@interface Profile {
    String displayName();
}

@Profile(displayname = "Admin") // Invalid: letter case mismatch
class AdminProfile {}
```

The compiler performs exact name matching, so you must write `displayName = "Admin"`. Elements also cannot be named `2name`, `user-name`, or a Java keyword such as `class`.

### Omitting a Required Element

```java
@interface EventInfo {
    String event();
    boolean enabled() default true;
}

@EventInfo(enabled = false) // Invalid: missing event()
class EventHandler {}
```

Fix it with `@EventInfo(event = "login", enabled = false)`. Using `@EventInfo` or `@EventInfo()` does not make `event` optional either.

### Confusing `@interface` with a Regular Interface

```java
interface Metadata {
    String name();
}

@Metadata(name = "x") // Invalid: Metadata is not an annotation type
class Example {}
```

To use `@Metadata`, you must **define `@interface Metadata`**. Conversely, when you want to describe methods that a class must implement, you need a regular `interface` instead of `@interface`.

### Expecting Reflection to Read an Annotation with Default `CLASS` Retention

```java
@interface Stage {
    String value();
}

@Stage("demo")
class DemoStage {}
```

This declaration is valid, but `DemoStage.class.getAnnotation(Stage.class)` does not provide a runtime instance of `Stage` because the annotation type does not declare `@Retention(RUNTIME)`. If the goal is to read it at runtime, add `@Retention(RetentionPolicy.RUNTIME)` to the definition of `Stage` and recompile the related code.

### Using `@Target` Incorrectly

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@interface MethodOnly {}

@MethodOnly // Invalid: this is a class, not a method
class WrongLocation {}
```

Keep `@MethodOnly` on a method, or redesign `@Target` if it truly needs to be used on a class.

## 10. Design Principles for Easy-to-Use Annotations

A good annotation type should express **stable metadata that can be declared in source code**, with transparent element names and types.

- Choose meaningful type names (`AuditInfo`, `Endpoint`, `RetryPolicy`) rather than generic names that are unclear when placed after `@`.
- Use required elements for values that are truly indispensable; use `default` for optional settings with clear defaults.
- Use enums for finite choices that should be checked at compile time; avoid arbitrary strings if values must not fall outside a defined set.
- Use `Class<?>` when metadata needs to reference a type; use nested annotations when a group of parameters is structured.
- Avoid cramming dynamic runtime logic or complex business objects into annotations. Annotations are better suited for describing static configuration than runtime data.
- Choose a `@Target` narrow enough to catch misplaced usage; choose `@Retention` based on how the metadata is actually consumed.
- Avoid renaming, changing the type of, or especially removing published elements; such changes can break code using the annotation. Consider compatibility right when designing `default` values.

Example of a clear, meaningful design:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

enum AccessLevel { PUBLIC, INTERNAL }

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface ApiOperation {
    String value();  // Business name of the operation
    AccessLevel access() default AccessLevel.INTERNAL;
    boolean audited() default false;
}
```

At usage sites, it can be written concisely if only `value` is provided:

```java
class UserApi {
    @ApiOperation(value = "createUser", access = AccessLevel.PUBLIC, audited = true)
    void createUser() {}

    @ApiOperation("healthCheck")
    void healthCheck() {}
}
```

Here, `@ApiOperation` only carries descriptive data. To actually enforce authorization or record audit logs, the system needs a component that reads the annotation and implements those rules.

## 11. Checklist When Declaring `@interface`

Before using an annotation type in a Java project, verify:

1. Have I properly used `@interface Ten` to **define the annotation type**?
2. Does each element have the form `Kieu ten();` or `Kieu ten() default giaTri;`, with no parameters and no body?
3. Is every element type in the list allowed by Java, or a **one-dimensional** array of those types?
4. Are truly required elements distinguished from elements with `default`?
5. Do `default` and usage-site values have the correct types and satisfy annotation constant requirements?
6. If I want to use the `@Ten("x")` form, does the annotation define a `value()` element?
7. Does `@Target` allow the intended usage locations?
8. If reflection needs to read it at runtime, have I set `@Retention(RetentionPolicy.RUNTIME)`?
9. When the annotation is read, is there a component that processes the metadata, or am I expecting the annotation to create behavior on its own?
10. After modifying the definition, have I recompiled and checked all usage sites to detect compatibility errors?

When you understand `@interface` as **a metadata definition with strict elements and rules**, you will be able to design valid annotations yourself, know how to use `default`, control scope with `@Target`, and decide retention timing with `@Retention`.
