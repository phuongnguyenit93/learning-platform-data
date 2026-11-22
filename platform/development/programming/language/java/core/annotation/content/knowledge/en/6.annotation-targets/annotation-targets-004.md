# Annotations on PARAMETER and LOCAL_VARIABLE in Java

## 1. Two Different Applicable Targets

Java allows restricting where an annotation can be used through the `@Target` meta-annotation. When declaring `@Target(ElementType.PARAMETER)` or `@Target(ElementType.LOCAL_VARIABLE)`, we are describing **two different kinds of declarations**:

- **`ElementType.PARAMETER`**: the annotation is applied to the **formal parameter declaration** of a method or constructor. For example: the `name` parameter in `void greet(@Input String name)`.
- **`ElementType.LOCAL_VARIABLE`**: the annotation is applied to a **local variable declaration** inside a code block, for example: the `message` variable in a method body `@LocalInfo String message = "...";`.

Both are metadata attached to a declaration in Java code. They **do not automatically alter parameter or variable data, perform validation, grant permissions, or generate checking logic**. To produce behavior, you need a tool, an annotation processor, or application code that processes the corresponding information.

These two targets are particularly easy to confuse because both method parameters and local variables have a name and a data type, and often appear together within the same method. However, they differ in their **declaration location, scope, and observability through reflection**.

## 2. Declaring Annotations with @Target

To define an annotation type that attaches only to parameters:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.PARAMETER)
@interface Input {
    String value();
}
```

To define a type that attaches only to local variables:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.LOCAL_VARIABLE)
@interface LocalInfo {
    String value();
}
```

The two examples above are **two independent declaration snippets to explain `@Target`**. When combining them into an actual file, import the classes only once.

You can allow **both positions** using an `ElementType` array:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target({ElementType.PARAMETER, ElementType.LOCAL_VARIABLE})
@interface Track {
    String value();
}
```

At this point, `@Track` is allowed on formal parameters and local variables, but **is not automatically allowed on classes, fields, or methods**. The compiler checks `@Target` at the point of use.

### Quick Comparison

| Criterion | `PARAMETER` | `LOCAL_VARIABLE` |
| --- | --- | --- |
| Attachment site | Formal parameter declaration of a method/constructor | Local variable declaration inside a code block |
| Example | `void pay(@Input String account)` | `@LocalInfo String receipt = "...";` |
| Element described by the annotation | Parameter `account` | Local variable `receipt` |
| Target checked at compile time | Yes | Yes |
| Readable via Java Core reflection? | Possible, for annotations with `RUNTIME` retention, via `Parameter` | No equivalent Java Core reflection API for local variable declaration annotations |
| Automatically generates behavior? | No | No |

`PARAMETER` is also used in the context of a **constructor parameter**, not only a method parameter. A `String account` variable declared inside a method body is a local variable, even if its value comes from a parameter.

## 3. Annotations on Parameters: PARAMETER

Consider the method:

```java
void register(
        @Input("username") String username,
        @Input("age") int age) {
    // ...
}
```

The two `@Input` annotations here are of the same type, but they are placed on **two different parameter declarations**. This is not a case of repeating an annotation on the same declaration, so **`@Repeatable` is not needed**.

Their effect depends on a component that knows how to read `@Input`: for example, a custom parameter mapper could read the strings `"username"` and `"age"` to bind data from an incoming request. Java Core does not automatically generate that mapping mechanism.

### 3.1. Reading Parameter Annotations via Reflection

When an annotation has `@Retention(RetentionPolicy.RUNTIME)`, a program can retrieve annotations on parameters through `java.lang.reflect.Parameter`.

Common flow:

1. Obtain the `Method` or `Constructor` via reflection.
2. Call `getParameters()` to get the `Parameter` objects.
3. Use `parameter.getAnnotation(Input.class)` or `parameter.isAnnotationPresent(Input.class)`.
4. Read the element inside the annotation if found.

`Method.getParameterAnnotations()` also returns an array of annotations per parameter. `Parameter.getAnnotations()` provides an API to operate directly on a single parameter.

**Note:** Java may not preserve source parameter names (`username`, `age`) in the way `Parameter.getName()` exposes them during normal compilation. Depending on the compiler and the `-parameters` flag, the observed names may be `arg0`, `arg1`. This is **independent of whether the `@Input("username")` annotation is retained at runtime**. The annotation's `value()` element holds the string specified by the developer.

### 3.2. Constructor Parameters

```java
class Account {
    private final String id;

    Account(@Input("accountId") String id) {
        this.id = id;
    }
}
```

`@Input` is attached to the constructor's `id` parameter declaration and is valid with `ElementType.PARAMETER`. If it has `RUNTIME` retention, reflection via `Constructor.getParameters()` can read it similarly to a method parameter.

Do not confuse the constructor parameter with the `id` field: the two positions are two different program elements. Attaching an annotation directly to the field requires an appropriate target such as `ElementType.FIELD`.

## 4. Annotations on Local Variables: LOCAL_VARIABLE

Consider the code snippet inside a method:

```java
void process(String input) {
    @LocalInfo("normalized value")
    String normalized = input.trim();

    @LocalInfo("result counter")
    int count = normalized.length();

    System.out.println(count);
}
```

`normalized` and `count` are **local variables**; `@LocalInfo` uses `ElementType.LOCAL_VARIABLE`, so it is valid on these declarations.

Do not interpret an annotation as a function call: `@LocalInfo` does not cause `trim()` to run again, does not insert logging, does not control assignment, and does not automatically change the variable's lifetime.

### 4.1. Timing and Scope of Local Variables

A local variable is declared inside a block; it is not a member of the class and not a parameter of the method. The scope in which the variable name can be used depends on block structure, definite assignment rules, and Java semantics.

For example:

```java
void calculate(int amount) {
    @LocalInfo("local copy")
    int doubled = amount * 2;
    System.out.println(doubled);
}
```

`amount` is a **PARAMETER**, whereas `doubled` is a **LOCAL_VARIABLE**. The fact that both have type `int` does not make them the same kind of declaration.

### 4.2. Can LOCAL_VARIABLE Be Read via Reflection?

This is the most important difference in practical applications.

`Method`, `Constructor`, and `Parameter` are objects in the Java Reflection API, but **Java Core has no `LocalVariable` object in reflection to look up individual local variables and call `getAnnotation` on that variable declaration**.

Even if an annotation type for `LOCAL_VARIABLE` has `@Retention(RetentionPolicy.RUNTIME)`, that **does not mean** an application can use standard reflection to retrieve `@LocalInfo` from the `doubled` variable. For local variable declaration annotations, Java does not guarantee that the corresponding metadata is included in the class file in the way the reflection API for parameters works.

If the problem involves analyzing, validating, or transforming information at the local variable level, you need to consider compile-time tools (for example, annotation processors with limited observability capabilities, compiler plugins, or source code analysis tools) rather than assuming you can use `Method.getParameters()` to see local variables. Certain annotations attached to the **used type** of a variable follow different metadata storage rules; that is `TYPE_USE`, which is distinguished in section 7.

### 4.3. The `var` Case

In Java 17+, `var` uses type inference for local variables in valid contexts. When an annotation targets a local variable declaration, you can write:

```java
void run() {
    @LocalInfo("inferred local")
    var message = "ready";

    System.out.println(message);
}
```

Here, `var` is Java's type inference syntax and does not create a separate annotation target. `message` is still a local variable. Use `@Target(LOCAL_VARIABLE)` when the target is a variable declaration.

## 5. Standalone Java 17+ Example: Observing the Two Applicable Targets

This example defines annotations for **parameters only**, **local variables only**, and **both**. The program uses only the JDK, with no third-party libraries required.

Create the file **ParameterLocalTargetDemo.java**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface InputName {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.LOCAL_VARIABLE)
@interface LocalHint {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.PARAMETER, ElementType.LOCAL_VARIABLE})
@interface Track {
    String value();
}

public class ParameterLocalTargetDemo {
    static void greet(
            @InputName("person")
            @Track("received")
            String name) {
        @LocalHint("computed message")
        @Track("temporary")
        String greeting = "Hello, " + name;

        System.out.println(greeting);
    }

    public static void main(String[] args) throws NoSuchMethodException {
        Method method = ParameterLocalTargetDemo.class
                .getDeclaredMethod("greet", String.class);

        Parameter parameter = method.getParameters()[0];
        InputName input = parameter.getAnnotation(InputName.class);

        System.out.println(input.value());
        System.out.println(parameter.isAnnotationPresent(Track.class));

        greet("Lan");
    }
}
```

Compile and run with JDK 17 or later, from the directory containing the file:

```bash
javac ParameterLocalTargetDemo.java
java ParameterLocalTargetDemo
```

Exact stdout:

```text
person
true
Hello, Lan
```

**Result explanation:**

1. `@InputName("person")` has target `PARAMETER`; because its retention is `RUNTIME`, `parameter.getAnnotation(InputName.class)` returns the annotation attached to the `name` parameter. Therefore, `person` is printed.
2. `@Track("received")` is also attached to the `name` parameter, because `@Track` allows `PARAMETER`; `isAnnotationPresent(Track.class)` returns `true`.
3. Inside `greet`, `@LocalHint("computed message")` and `@Track("temporary")` are both attached to the `greeting` local variable declaration. They **do not appear in `parameter.getAnnotations()`**, because a parameter and a local variable are two separate declarations.
4. `greet("Lan")` performs normal string concatenation to produce `Hello, Lan`. The annotations do not automatically interfere with the method's logic.

Setting `@Retention(RUNTIME)` on `LocalHint` in the example **does not unlock a new reflection API to read `@LocalHint` on `greeting`**. It helps clearly illustrate that *retention policy* and *accessibility by element kind through the reflection API* are two different concerns.

## 6. Valid and Invalid Positions

### 6.1. For PARAMETER Only

```java
@Target(ElementType.PARAMETER)
@interface ParamOnly {}

class Example {
    void f(@ParamOnly String name) {} // Valid.

    void g() {
        // @ParamOnly String local = "x"; // ERROR if uncommented.
    }
}
```

When `@ParamOnly` only has target `PARAMETER`, placing it before a local variable declaration is invalid.

### 6.2. For LOCAL_VARIABLE Only

```java
@Target(ElementType.LOCAL_VARIABLE)
@interface LocalOnly {}

class Example {
    // void f(@LocalOnly String name) {} // ERROR if uncommented.

    void g() {
        @LocalOnly
        String local = "x"; // Valid.
    }
}
```

When `@LocalOnly` only has target `LOCAL_VARIABLE`, placing it on the `name` parameter is invalid.

The two snippets in section 6 are **independent illustrative snippets** and require importing `java.lang.annotation.ElementType` and `java.lang.annotation.Target` before compiling into a complete file. Do not combine them as-is into a single file because both use the class name `Example`.

### 6.3. Multiple Annotations on the Same Declaration

An annotation allowed to target `PARAMETER` can appear alongside another annotation that also allows `PARAMETER`:

```java
void send(@InputName("email") @Track("request") String email) {
    // ...
}
```

No special ordering is required for annotations of different types. The presence of multiple annotations only specifies **which metadata is attached to the parameter**; the behavior and business execution order depend on the processing component.

## 7. Do Not Confuse PARAMETER and LOCAL_VARIABLE with TYPE_USE

A common practical issue is an annotation placed immediately before the **type** of a parameter or variable:

```java
@Marker String name
```

Looking at the textual position alone is not enough to tell whether the annotation targets the **parameter/variable declaration** or **the use of the `String` type**. Java has another target:

- `ElementType.TYPE_USE`: targets **the use of a type** (type use), for example a type in a variable or parameter declaration, a generic type argument, a cast, or other valid type-use contexts.
- `ElementType.PARAMETER`: targets a formal parameter declaration.
- `ElementType.LOCAL_VARIABLE`: targets a local variable declaration.

Example illustrating a TYPE_USE annotation:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.TYPE_USE)
@interface ReadOnlyType {}

class Example {
    void print(@ReadOnlyType String text) {
        @ReadOnlyType String local = text;
        System.out.println(local);
    }
}
```

`@ReadOnlyType` in the example is attached to the **used type**. It is not an annotation declared with `@Target(PARAMETER)` or `@Target(LOCAL_VARIABLE)`, even though it can also be written immediately before `String` in those two positions.

**Important point about reflection:** For a method parameter, the `Parameter.getAnnotations()` API is used to read annotations *on the parameter declaration*. Meanwhile, annotation information of the **parameter's type** is represented through `Parameter.getAnnotatedType()` and `AnnotatedType` when the metadata is retained at runtime and supported. Do not expect both APIs to always return the same set of annotations.

For local variables, standard Java reflection still does not allow traversing local variable declarations the way it traverses `Method` or `Parameter`. Tools that read bytecode or compiler APIs serve different problems than traditional reflection.

### TYPE_USE Does Not Automatically Mean Validation

An annotation like `@ReadOnlyType` only becomes an actual checked constraint if there is a compiler plugin, type checker, or other tool that understands it. Java does not automatically turn every `TYPE_USE` annotation into an immutability, non-null, or extended type-checking mechanism.

## 8. Retention and Metadata Observability

`@Target` and `@Retention` answer two independent questions:

- **`@Target`:** where is the annotation placed in source?
- **`@Retention`:** until which stage is the annotation's metadata retained?

Common retention policies:

| Retention | Meaning | `PARAMETER` via reflection | `LOCAL_VARIABLE` via reflection |
| --- | --- | --- | --- |
| `SOURCE` | Used only at source/compile time | No | No |
| `CLASS` | Kept in the class file according to retention rules | No, not via the runtime annotation API | No corresponding API |
| `RUNTIME` | Allows runtime access to metadata at supported locations | Yes, via `Parameter` when the annotation is present | **No corresponding Java Core API for local variable declaration annotations** |

An annotation type that does not declare `@Retention` defaults to **`CLASS`** retention. Therefore, examples that require reflection on parameters must explicitly specify `@Retention(RetentionPolicy.RUNTIME)`.

For annotations on local variable declarations, do not infer that setting `RUNTIME` guarantees retrieval via `Method` or `Parameter`: there is no reflection object describing individual local variables.

In addition, debug information about local variable names (if present) in the class file and annotation information are **two different kinds of data**. Enabling compiler debug options cannot be treated as a way to automatically read all local variable annotations via reflection.

## 9. Practical Applications and How to Choose a Target

### When to Use PARAMETER

Parameter annotations are suitable for metadata attached to **method/constructor inputs**. For instance, a library might read the field name to map, validation conditions, conversion rules, or required values to process inputs.

In a framework, the effect also requires integrating the right component that consumes the annotation. Just because an annotation has target `PARAMETER` does not mean Java automatically checks constraints. For example, framework annotations marking request parameters are typically read by the framework at runtime; they are not a standard Java SE mechanism.

### When to Use LOCAL_VARIABLE

Local variable annotations are more useful for **source code analysis tools or compile-time checks**, because Java Core reflection does not expose a direct API for local variables. Tools can use the metadata to enforce coding rules, issue warnings, or analyze local properties, depending on whether the tool supports seeing and processing annotations there.

If you need to place configuration for the application to read at runtime per method, consider the actual goal: metadata at the parameter or method level may be more appropriate than placing it on a local variable and expecting reflection to read it.

### When to Use Both

If a piece of metadata has the same valid meaning both at an input and on a temporary variable, define:

```java
@Target({ElementType.PARAMETER, ElementType.LOCAL_VARIABLE})
@interface Note {
    String value();
}
```

Only broaden `@Target` when there is a clear purpose. Allowing multiple targets does not mean tools process the annotation in the same way in both places.

## 10. Common Mistakes

**1. Using `PARAMETER` to annotate a variable in a method body.** Local variables require `LOCAL_VARIABLE`; the compiler will reject an annotation intended only for `PARAMETER`.

**2. Using `LOCAL_VARIABLE` to annotate a parameter.** Method/constructor parameters are a different declaration from local variables, even though the syntax of both has a type and a name.

**3. Thinking `@Retention(RUNTIME)` for a local variable means reflection can read the variable.** Java Core reflection has an API for `Parameter`, and no equivalent API for a local variable declaration.

**4. Assuming a `PARAMETER` annotation can be retrieved via `Method.getAnnotation(...)`.** Annotations on a **parameter** require accessing `Method.getParameters()[i]` and then reading the annotation from the `Parameter`. `Method.getAnnotation` queries annotations directly on the **method**, not the parameters.

**5. Confusing declaration annotations with `TYPE_USE` type annotations.** Check the annotation type's `@Target` and use `getAnnotatedType()` when you actually want to read supported runtime type-use annotations.

**6. Believing the value inside an annotation validates itself.** `@InputName("email")` only provides a metadata string. There is no validation unless a processor interprets that string.

**7. Expecting `Parameter.getName()` to always return the original name.** Parameter names may be replaced with synthetic names like `arg0`; if you need source names, use the appropriate compiler flag and mechanism, or specify a dedicated name in the annotation value.

**8. Assuming an annotation on a parameter automatically applies to every variable assigned from that parameter.** Metadata does not automatically propagate along with passed or assigned data; a local variable is an independent declaration.

**9. Omitting `@Target` in an annotation definition.** This can lead to the annotation being used in unintended places. Declaring the necessary `ElementType` values helps the compiler enforce proper usage.

**10. Forgetting to check `@Retention` before writing reflection logic.** Annotations without `RUNTIME` retention will not be provided by `Parameter.getAnnotation(...)` under standard runtime reflection.

## 11. Practice Exercises

1. In the `ParameterLocalTargetDemo` example, add a `@InputName("prefix") String prefix` parameter to `greet`. Update `getDeclaredMethod` and the reflection code to print both metadata names. Do not forget to update the method call.
2. Try attaching `@LocalHint("wrong")` to the `name` parameter. Note the compilation error and explain it using `@Target(LOCAL_VARIABLE)`.
3. Try attaching `@InputName("wrong")` to the `greeting` variable. Explain why the error occurs even though the variable has the same `String` type.
4. Change `@Retention(RetentionPolicy.RUNTIME)` of `InputName` to `CLASS`. Predict the result of `parameter.getAnnotation(InputName.class)` and update the program to handle the case where it is not found.
5. Add a `@Track("other local") int count = name.length();` variable inside `greet`. Explain why reading only `Method.getParameters()` cannot find the annotation on `count`.
6. Define an annotation `@TypedLabel` with only `TYPE_USE`, then try annotating the `String` type of both a parameter and a local variable. Compare the concept of a *declaration* annotation with a *type-use* annotation.

**Key takeaway:** `PARAMETER` describes a **parameter declaration**; `LOCAL_VARIABLE` describes a **local variable declaration**. The Java compiler checks `@Target` for both, but their readability via reflection is not the same. Choose the target based on the element you need to describe and the component that actually consumes the metadata.
