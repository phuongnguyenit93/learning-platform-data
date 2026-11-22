# Reading Annotations on Parameter and Method Parameters Using Java Reflection

When a Java method accepts parameters, annotations can be placed **on each parameter** to describe metadata such as parameter names in a protocol, validation rules, required/optional status, or instructions for tooling. At runtime, Java Reflection provides `java.lang.reflect.Parameter` and methods on `Method` or `Constructor` to retrieve this data.

Conceptual example:

```java
void checkout(@Input("ticketId") String id, @Input("count") int count) {
}
```

With the `@Input` annotation declared properly and having `RUNTIME` retention, you can ask Reflection: *does the first parameter have `@Input`, and if so, what is its `value()`?* This is information **about the parameter**, not the actual value of the `id` or `count` variable when the method is called.

This lesson focuses on how to **read annotations on a parameter using Reflection**, the relationship between `Method`/`Constructor` and `Parameter`, the correctness of `@Target(PARAMETER)` and `@Retention(RUNTIME)`, how to read annotations across multiple parameters, repeatable annotation cases, and how to distinguish annotations on a **parameter declaration** from annotations on a **parameter's type**.

## 1. Distinguishing Parameter, Argument, and Annotation

Three concepts are often confused:

- **Parameter (formal parameter):** the variable declared in the method signature, for example `String id` in `void pay(String id)`.
- **Argument:** the value passed at a specific call site, for example `pay("A123")` passes the string `"A123"`.
- **Parameter annotation:** metadata attached to the **parameter declaration**, for example `@Input("ticketId") String id`.

When you use `Method.getParameters()`, you receive `Parameter` objects describing the **compiled method declaration**. You do **not** receive the arguments of a call, nor can you read the current values of local variables.

Example:

```java
void pay(@Input("ticketId") String id) {
    // id is the actual value only when a call executes here.
}
```

`@Input("ticketId")` is static metadata attached to the declaration. A program can use it to decide how to map request data to the parameter, but **the mapping must be performed by the code or framework itself**. An annotation does not pass arguments or validate data on its own.

## 2. Declaring an Annotation for a Parameter

An annotation type used to describe parameters typically has:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface Input {
    String value();
}
```

Explanation:

1. `@interface Input` defines the `Input` annotation type.
2. `@Target(ElementType.PARAMETER)` allows attaching `Input` on a **formal parameter declaration** of a method or constructor, rather than automatically allowing it anywhere with a similar-sounding name.
3. `@Retention(RetentionPolicy.RUNTIME)` preserves metadata so that standard Reflection APIs can read it while the program is running.
4. `String value()` declares an annotation element. When writing `@Input("ticketId")`, Java uses the shorthand form for `@Input(value = "ticketId")`.

If an annotation only has `@Target(PARAMETER)` but **does not declare `@Retention`**, the default retention is `CLASS`: the compiler can still write the annotation data into the class file, but the `Parameter.getAnnotation(Input.class)` API **cannot read it**.

Similarly, `@Retention(SOURCE)` does not produce runtime metadata readable via Reflection. For the goals of this lesson, prefer `RUNTIME`.

If an annotation defines `@Target(TYPE_USE)` instead of `PARAMETER`, both its meaning and the reading API differ; Section 8 covers this important boundary.

## 3. Flow for Reading Annotations from a Method

Standard steps:

1. Identify the `Class<?>` that owns the method, for example `Checkout.class`.
2. Obtain the `Method` matching the **name and parameter type list**, for example `getDeclaredMethod("confirm", String.class, int.class)`.
3. Call `Method.getParameters()` to get the `Parameter[]` array in the order of parameters in the signature.
4. On each `Parameter`, call `getAnnotation(Input.class)`, `getAnnotationsByType(...)`, or `isAnnotationPresent(...)`.
5. If the annotation exists, read its elements, such as `annotation.value()`.

Diagram:

```text
Checkout.class
     |
     +-- getDeclaredMethod("confirm", String.class, int.class)
               |
               v
             Method
               |
               +-- getParameters()
                         |
                         +-- Parameter[0] --> getAnnotation(Input.class)
                         |
                         +-- Parameter[1] --> getAnnotation(Input.class)
```

`Method` represents a method declaration, while `Parameter` represents a parameter position of that `Method`. `Parameter` also implements `AnnotatedElement`, so it provides familiar APIs such as `getAnnotation`, `getDeclaredAnnotations`, `getAnnotationsByType`, and `isAnnotationPresent`.

### 3.1. How getMethod and getDeclaredMethod Differ

- `getMethod(name, parameterTypes...)` searches for a matching **public method** on the class, including inherited public methods according to Reflection rules.
- `getDeclaredMethod(name, parameterTypes...)` searches for a method **declared directly on that class**, including private methods, but does not automatically search inherited methods.
- Both require the **exact name and parameter types**; overloads are not distinguished by variable names or annotations.
- When you only have the name without knowing the signature, you can iterate through `getDeclaredMethods()` and filter, though you must handle overloads and synthetic/bridge methods yourself if any exist.

For example, `getDeclaredMethod("confirm", String.class, int.class, String[].class)` locates the exact three-parameter method described in the complete example in Section 4.

## 4. Complete Java 17+ Example: Reading Multiple Annotations on Parameters

Create the file **`ParameterAnnotationDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface Bind {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface OptionalArg {
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface Sanitized {
}

class Checkout {
    public void confirm(
            @Bind("ticket") String ticket,
            @Bind("count") @OptionalArg int count,
            @Bind("coupon") String... coupons) {
    }

    public void prepare(@Sanitized String code) {
    }
}

public class ParameterAnnotationDemo {
    public static void main(String[] args) throws Exception {
        Method confirm = Checkout.class.getDeclaredMethod(
                "confirm", String.class, int.class, String[].class);

        for (Parameter parameter : confirm.getParameters()) {
            Bind bind = parameter.getAnnotation(Bind.class);
            System.out.println(parameter.getType().getSimpleName()
                    + " | " + bind.value()
                    + " | optional=" + parameter.isAnnotationPresent(OptionalArg.class)
                    + " | varargs=" + parameter.isVarArgs());
        }

        System.out.println("annotation rows="
                + confirm.getParameterAnnotations().length);

        Method prepare = Checkout.class.getDeclaredMethod("prepare", String.class);
        Parameter code = prepare.getParameters()[0];

        System.out.println("parameter marker="
                + code.isAnnotationPresent(Sanitized.class));
        System.out.println("type-use marker="
                + code.getAnnotatedType().isAnnotationPresent(Sanitized.class));
    }
}
```

Compile with JDK 17 or higher and enable `-parameters` so the compiler stores **declared parameter names** (not required to read annotations):

```bash
javac --release 17 -parameters ParameterAnnotationDemo.java
java ParameterAnnotationDemo
```

Exact stdout:

```text
String | ticket | optional=false | varargs=false
int | count | optional=true | varargs=false
String[] | coupon | optional=false | varargs=true
annotation rows=3
parameter marker=false
type-use marker=true
```

### 4.1. Why Is the Output Exactly Like This?

- `confirm` has three declared parameters: `String`, `int`, and `String...`, respectively. In Reflection, the varargs `String...` has the type `String[]`, so its simple type name is `String[]`.
- All three parameters are annotated with `@Bind`; calling `getAnnotation(Bind.class)` retrieves the corresponding `value()` values `"ticket"`, `"count"`, and `"coupon"`.
- Only the `count` parameter has `@OptionalArg`, so `isAnnotationPresent(OptionalArg.class)` is `true` only on the second parameter.
- `Parameter.isVarArgs()` is `true` only for the actual last varargs parameter in the `confirm` declaration.
- `Method.getParameterAnnotations()` returns a structure with one row per parameter; the outer array has length `3`.
- `@Sanitized` only has the `TYPE_USE` target, so it does not belong to annotations on the **parameter declaration**. `Parameter.isAnnotationPresent(Sanitized.class)` returns `false`.
- `Parameter.getAnnotatedType()` returns an `AnnotatedType` for the **parameter type**; `@Sanitized` is present there, so the last line returns `true`.

This snippet **does not invoke `confirm(...)` or `prepare(...)`**. All output comes from the program actively reading metadata from the method definitions, not from executing the business logic of those two methods.

**Empirical verification:** the program above was compiled with `javac --release 17 -parameters` and executed successfully, producing the exact six stdout lines listed.

## 5. Important APIs on Parameter

`java.lang.reflect.Parameter` was introduced in Java 8 and remains the standard API in Java 17+.

| API | Meaning | Notes |
| --- | --- | --- |
| `parameter.getAnnotation(Input.class)` | Retrieves a single annotation of type `Input` if present according to API rules | May return `null` |
| `parameter.isAnnotationPresent(Input.class)` | Is an annotation of type `Input` visible to Reflection? | Does not read annotation values |
| `parameter.getAnnotations()` | Array of annotations present on the parameter | Does not automatically guarantee unwrapping repeatable containers |
| `parameter.getDeclaredAnnotations()` | Annotations declared directly on the parameter | For parameters, there is no class-style annotation inheritance mechanism like `@Inherited` |
| `parameter.getAnnotationsByType(Input.class)` | Array of annotations of this type, including repeatable cases where applicable | Convenient to use if `Input` is repeatable |
| `parameter.getDeclaredAnnotationsByType(Input.class)` | Annotations of that type declared directly or indirectly via a container | Use when you want the declared scope to be explicit |
| `parameter.getType()` | Parameter type as a `Class<?>` after erasure, for example `String[].class` | Does not contain generic details |
| `parameter.getParameterizedType()` | `Type` that can carry generic information, for example `List<String>` | Different from annotation values |
| `parameter.getAnnotatedType()` | `AnnotatedType` describing the parameter's type and type-use annotations | Does not replace APIs for reading declaration annotations |
| `parameter.getName()` | Parameter name from metadata or a synthetic name when information is missing | Depends on compiler flags and bytecode source |
| `parameter.isNamePresent()` | Is the real parameter name stored in the class file? | Should be checked before relying on `getName()` |
| `parameter.isVarArgs()` | Whether the parameter is varargs | Only one valid position in the list |
| `parameter.getDeclaringExecutable()` | The `Method` or `Constructor` that owns the parameter | Returns `Executable` |

**`null` warning:** do not write `parameter.getAnnotation(Input.class).value()` unless you are certain the annotation exists. When no matching annotation is present or the retention is not `RUNTIME`, `getAnnotation` typically returns `null`.

Safe approach:

```java
Input input = parameter.getAnnotation(Input.class);
if (input != null) {
    System.out.println(input.value());
}
```

This is a **snippet** used inside a loop that has a `parameter` variable, not a standalone runnable file.

## 6. Reading via Method.getParameterAnnotations()

In addition to `Parameter[]`, Reflection also supports an older API:

```java
Annotation[][] annotations = method.getParameterAnnotations();
```

`java.lang.annotation.Annotation[][]` is a **two-dimensional array**:

- `annotations[i]` is the array of annotations placed on the `i`-th parameter.
- `annotations[i][j]` is the `j`-th annotation of parameter `i`.
- The inner array may be empty if that parameter has no runtime-visible annotations returned by the API.

Example using `confirm` from Section 4 (remember to import `java.lang.annotation.Annotation`):

```java
Annotation[][] matrix = confirm.getParameterAnnotations();
Parameter[] parameters = confirm.getParameters();

for (int i = 0; i < parameters.length; i++) {
    System.out.println(
            i + ": " + parameters[i].getType().getSimpleName()
                    + ", annotation count=" + matrix[i].length);
}
```

Expected output in this example:

```text
0: String, annotation count=1
1: int, annotation count=2
2: String[], annotation count=1
```

`@Sanitized` in the `prepare` method is an annotation on a type use, so it **does not automatically appear in the declaration annotations array** returned by `getParameterAnnotations()`.

### 6.1. Which API Should You Prefer?

If you need to work with each parameter as an object, use:

```java
for (Parameter p : method.getParameters()) {
    Bind bind = p.getAnnotation(Bind.class);
}
```

If you are working with an older library or an API that returns an annotation matrix, use `method.getParameterAnnotations()` and map by **position**.

Avoid trying to infer parameters from annotation names or unchecked indices. Although the annotation matrix is designed to correspond to parameters in the method representation, special executable cases with **implicit/synthetic parameters** or extra compiler-generated information can complicate analysis. When building a general-purpose framework that handles constructors, enums, and inner classes, inspect `Parameter` metadata, specific bytecode, and how the compiler represents them, rather than assuming every constructor looks like a regular source-level method.

## 7. Parameter Name and Annotation Are Two Independent Kinds of Metadata

Many people see `Parameter.getName()` return `arg0`, `arg1` and assume annotations cannot be read. These are **two separate issues**.

### 7.1. Without -parameters Enabled

Example:

```bash
javac --release 17 ParameterAnnotationDemo.java
```

In bytecode generated by `javac` without storing parameter name metadata enabled, `isNamePresent()` typically returns `false`, while `getName()` returns synthetic names such as `arg0`, `arg1`. This **does not lose the `@Bind` annotation with `RUNTIME` retention**.

### 7.2. With -parameters Enabled

```bash
javac --release 17 -parameters ParameterAnnotationDemo.java
```

The compiler stores parameter names in the corresponding metadata in the class file. Then, for parameters whose names are stored, `parameter.isNamePresent()` returns `true`, and `getName()` can return `ticket`, `count`, `coupons` matching the source names.

**Why does this matter?**

If you write a mini-framework that automatically maps data by Java parameter name, you must ensure the build enables `-parameters` or uses other reliable metadata. In this example, using `@Bind("ticket")` for the mapping name **does not depend** on whether the Java parameter is named `ticket` or `arg0`.

The `getDeclaredMethod(...)` signature also uses **parameter types**, not parameter names. Two overloads `confirm(String)` and `confirm(int)` must be distinguished using `String.class` and `int.class`, not by `@Bind` or the `ticket` variable.

## 8. Distinguishing ElementType.PARAMETER and ElementType.TYPE_USE

This is the most important point when reading annotations on parameters under two different meanings.

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface FromRequest {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface CleanType {}

class Api {
    void accept(@FromRequest @CleanType String name) {}
}
```

`@FromRequest` is attached to the **parameter declaration**. `@CleanType` is attached to the **type use `String`**.

They appear on the same source line, yet how they are read differs:

```java
Method m = Api.class.getDeclaredMethod("accept", String.class);
Parameter p = m.getParameters()[0];

boolean fromRequest =
        p.isAnnotationPresent(FromRequest.class);

boolean cleanType =
        p.getAnnotatedType().isAnnotationPresent(CleanType.class);
```

Both booleans evaluate to `true` in this declaration context, but they go through **two different APIs and two different kinds of metadata**.

| Annotation Location | @Target | Appropriate API |
| --- | --- | --- |
| On parameter declaration | `ElementType.PARAMETER` | `Parameter.getAnnotation`, `Parameter.getAnnotationsByType` |
| On the type used as a parameter | `ElementType.TYPE_USE` | `Parameter.getAnnotatedType()`, then call annotation APIs on `AnnotatedType` |
| On a parameter with nested generic/type arguments | `ElementType.TYPE_USE` at the type argument position | Use subtypes such as `AnnotatedParameterizedType`, `AnnotatedArrayType`, etc. to traverse the type structure |

Example with generics:

```java
void names(java.util.List<@CleanType String> values) {}
```

`@CleanType` here is attached to the `String` type argument of `List<String>`, not to `Parameter` as a declaration annotation. Reading this kind of nested annotation may require:

```java
AnnotatedType type = p.getAnnotatedType();
if (type instanceof AnnotatedParameterizedType apt) {
    AnnotatedType argumentType = apt.getAnnotatedActualTypeArguments()[0];
    boolean marked = argumentType.isAnnotationPresent(CleanType.class);
}
```

This snippet assumes `p` is the `Parameter` for `values` and that `AnnotatedType` and `AnnotatedParameterizedType` are imported; this is **contextual illustrative code**, not a standalone file.

An annotation type can also declare both targets `{PARAMETER, TYPE_USE}`. In that case, be careful about the **annotation location and applicable semantics per the JLS**, and do not use a single query as a substitute for all cases.

## 9. Reading Repeatable Annotations on a Parameter

Java allows an annotation to be repeated multiple times on the same parameter when declared with `@Repeatable` and a valid container.

Standalone example in the file **`RepeatableParameterDemo.java`**:

```java
import java.lang.annotation.*;
import java.lang.reflect.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@Repeatable(Tags.class)
@interface Tag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface Tags {
    Tag[] value();
}

class Handler {
    public void handle(@Tag("required") @Tag("visible") String input) {}
}

public class RepeatableParameterDemo {
    public static void main(String[] args) throws Exception {
        Method method = Handler.class.getDeclaredMethod("handle", String.class);
        Parameter parameter = method.getParameters()[0];

        Tag[] tags = parameter.getAnnotationsByType(Tag.class);
        System.out.println(tags.length);
        for (Tag tag : tags) {
            System.out.println(tag.value());
        }

        System.out.println(parameter.getAnnotation(Tag.class));
        System.out.println(parameter.getAnnotation(Tags.class).value().length);
    }
}
```

Run:

```bash
javac --release 17 RepeatableParameterDemo.java
java RepeatableParameterDemo
```

Stdout:

```text
2
required
visible
null
2
```

**Notable point:** `getAnnotationsByType(Tag.class)` **unwraps the valid container** and returns two `Tag` instances. Querying `getAnnotation(Tag.class)` retrieves a single direct annotation; in this repeated case it returns `null` because the bytecode represents the `Tags` container. You can read the container with `getAnnotation(Tags.class)` and obtain `value().length` as `2`.

When designing a system that processes multiple metadata entries of the same kind on a parameter, prefer `getAnnotationsByType`. There is no need to manually parse the container's annotation array if this API meets your requirements.

This example was compiled and run with `javac --release 17`; the output was verified directly.

## 10. Annotations on Constructor Parameters

`java.lang.reflect.Constructor` and `Method` both inherit from `Executable`. Therefore, both provide `getParameters()` and `getParameterAnnotations()`.

Example:

```java
class Ticket {
    Ticket(@Bind("code") String code, @Bind("quantity") int quantity) {
    }
}
```

To read them:

```java
Constructor<Ticket> ctor =
        Ticket.class.getDeclaredConstructor(String.class, int.class);

for (Parameter parameter : ctor.getParameters()) {
    Bind bind = parameter.getAnnotation(Bind.class);
    System.out.println(bind == null ? "(none)" : bind.value());
}
```

The reading snippet above requires `import java.lang.reflect.Constructor;` and `import java.lang.reflect.Parameter;`; it uses the `Bind` annotation declared in Section 4.

Expected stdout:

```text
code
quantity
```

**You do not need to instantiate `Ticket`** to read annotations on constructor parameters. Reflection is inspecting the declaration metadata on the constructor.

For non-static inner classes, enum constructors, or constructors where the compiler adds synthetic/mandated parameters, the parameter list reflects the JVM representation and can be more complex than the source you wrote. When building general-purpose logic to map parameters, use `isSynthetic()`, `isImplicit()`, and `getDeclaringExecutable()` as appropriate and check the actual compiler/version behavior rather than assuming all constructors consist only of explicit source parameters.

## 11. Are Annotations Automatically Inherited on Method Parameters?

No. Do not assume that `@Inherited` applies to parameter annotations of overridden methods.

Example:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface Key {}

class Base {
    void check(@Key String value) {}
}

class Derived extends Base {
    @Override
    void check(String value) {}
}
```

If you obtain the `Method` declared directly by `Derived` and check `getParameters()[0].isAnnotationPresent(Key.class)`, the result is `false`. Annotations on a parameter of `Base.check` are not automatically copied to the parameter of `Derived.check`.

`@Inherited` (if declared on an annotation type) has its own specific rules for certain annotations on **classes**, not for "propagating" annotations from an overridden method's parameter down to the overriding method.

A framework can **explicitly inspect parent classes/interfaces and merge metadata according to its own rules**, but that is framework logic, **not the default behavior of `Parameter.getAnnotation`**.

## 12. When Does Reflection Return null or an Empty Array?

Common practical pitfalls:

### 12.1. Retention Is Not RUNTIME

```java
@Target(ElementType.PARAMETER)
@interface SourceHint {}
```

Omitting `@Retention` defaults to `CLASS`. The annotation may be present in the class file, yet will not be returned by `Parameter.getAnnotation(SourceHint.class)`. Fix this by declaring `@Retention(RetentionPolicy.RUNTIME)` if you need to read it via Reflection.

### 12.2. Reading the Wrong Method or Overload

`getDeclaredMethod("send", String.class)` is not the same as `getDeclaredMethod("send", int.class)`. Both may be valid if overloads exist, but the annotation is attached to **a specific declaration**. You must match the exact signature and parameter types.

### 12.3. Confusing a Declaration Target with a Type-Use Target

If an annotation only has `TYPE_USE`, calling `parameter.getAnnotation(...)` will not read the type-use location. Use `getAnnotatedType` and access the appropriate type structure.

### 12.4. Using a Single-Annotation API for Repeatable Annotations

If multiple annotations of the same type are held inside a container, `getAnnotation(Repeated.class)` can be `null` even though `getAnnotationsByType(Repeated.class)` returns elements. Use the by-type API when you need the set of repeated annotations.

### 12.5. Mistakenly Believing -parameters Controls Annotations

Lacking `-parameters` means parameter names may not be available, **but it does not mean `RUNTIME` annotations are not stored**. Separate the issue of missing parameter names from the issue of annotations not appearing.

### 12.6. Metadata Exists on a Superclass Method While Code Inspects the Subclass

Method parameter annotations **are not automatically inherited** on override. You must locate the exact `Method` and, if your framework specification requires it, explicitly define how related methods are looked up.

## 13. Some Notes When Building an Annotation-Based Mapper/Validator

Application example: suppose you plan to build a binder that reads `@Bind("ticket")` to map a request to method parameters. Before implementing:

1. **Distinguish metadata from data:** `@Bind("ticket")` only declares the mapping name. The `ticket` value comes separately from the request and must be parsed and validated.
2. **Be careful with `null`:** a parameter might not have `@Bind`; your application needs an explicit policy for skipping, configuration error, or fallback.
3. **Do not trust input just because an annotation is present:** metadata does not perform validation on its own. Validation, authorization, and type conversion rules require explicit code.
4. **Determine the allowed Reflection scope:** `getDeclaredMethod` can find non-public methods as well. Finding metadata does not automatically mean you have permission to invoke that method across every module or environment.
5. **Account for overloads and generics:** retrieve the method via its exact signature; Reflection returns the post-erasure type from `getType()` and generic information via `getParameterizedType()`.
6. **Avoid relying on Java variable names if the build does not enable `-parameters`:** use annotation values or another explicit mapping contract.
7. **Handle varargs:** Java Reflection treats a `String...` parameter as having type `String[]`; binder code must explicitly convert input into the appropriate array type.

For Spring/Jakarta or other frameworks, there may be additional framework-specific annotations and metadata aggregation algorithms. The examples in this lesson use **core Java Reflection**, without relying on any framework.

## 14. Self-Check Exercises

### Exercise 1 — Identifying Locations

How many `@Field` parameter declaration annotations are in the following snippet?

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface Field {
    String value();
}

class Api {
    void save(@Field("id") String id, int version, @Field("active") boolean active) {}
}
```

**Hint:** `save` has three `Parameter` objects. Parameters 0 and 2 have `@Field`; parameter 1 does not. If iterating over `getParameters()` and calling `getAnnotation(Field.class)`, you must check for `null` at index 1.

### Exercise 2 — Reflection and Parameter Names

If compiled without `-parameters`, why can `Parameter.getName()` be `arg0` while `parameter.getAnnotation(Field.class).value()` still returns `"id"`?

**Answer:** metadata storing parameter names and annotation metadata are two separate things. `RUNTIME` retention determines whether annotations are available via Reflection; `-parameters` determines whether declared names are stored for Reflection access.

### Exercise 3 — Method or Constructor?

Choose the appropriate API to read annotations on the parameters of `new Ticket("A", 2)`. Would you call `getDeclaredMethod` or `getDeclaredConstructor`?

**Answer:** obtain the `Constructor` with `Ticket.class.getDeclaredConstructor(String.class, int.class)`, and then use `getParameters()` just like with `Method`.

### Exercise 4 — TYPE_USE Differs from PARAMETER

Given:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface Trusted {}

class Api {
    void accept(@Trusted String value) {}
}
```

Why does `parameter.isAnnotationPresent(Trusted.class)` not return `true`, whereas `parameter.getAnnotatedType().isAnnotationPresent(Trusted.class)` can return `true`?

**Answer:** this annotation applies to the `String` type used in the declaration, not as a declaration annotation on the parameter. It must be read via `AnnotatedType`.

### Exercise 5 — Repeatable Annotations

For a parameter annotated with `@Tag("required") @Tag("visible")` as declared in Section 9, should you use `getAnnotation(Tag.class)` or `getAnnotationsByType(Tag.class)` if you need **all** tags?

**Answer:** `getAnnotationsByType(Tag.class)`, because it properly handles the repeatable annotation container and returns an array of `Tag` instances.

### Exercise 6 — Method Inheritance

`Base.check(@Key String value)` is overridden as `Derived.check(String value)`. If you inspect the `Parameter` of the overriding method in `Derived`, will `@Key` appear automatically?

**Answer:** no. Parameter declaration metadata belongs to **the specific method**, and is not automatically inherited from the overridden method.

## 15. Checklist When Reading Annotations on Parameters

Before debugging `null` or an empty annotation array, check:

1. Does the annotation type have `@Target(ElementType.PARAMETER)` if it is intended for a **parameter declaration**?
2. Does it have `@Retention(RetentionPolicy.RUNTIME)` so Java Reflection can read it at runtime?
3. Did you retrieve the exact `Method` or `Constructor` using the correct signature and parameter types?
4. Are you inspecting the right element of `Parameter[]` (positions 0, 1, 2…)?
5. Did you check for `null` before calling elements such as `annotation.value()`?
6. If the annotation is repeatable, are you using `getAnnotationsByType` instead of only `getAnnotation`?
7. Is the annotation on the **parameter declaration** or on a **type-use**, and did you choose the right one between `Parameter` and `AnnotatedType`?
8. Are you confusing a parameter name issue (`-parameters`) with the ability to read annotations?
9. If the method is overridden or a constructor has implicit parameters, have you inspected the right declaration and JVM metadata?
10. Have you verified it with a small Java program producing clear stdout before integrating it into a framework?

**Conclusion:** `Method.getParameters()` and `Constructor.getParameters()` provide access to each `Parameter`; from there, runtime-visible declaration annotations can be read using `getAnnotation` or `getAnnotationsByType`. `Method.getParameterAnnotations()` is a positional matrix option. For type-use annotations, use `getAnnotatedType()`. Retention, target, method signature, and how repeatable annotations are read are the four factors that determine whether the returned metadata matches your expectations.
