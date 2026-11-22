# Annotations on Individual Method and Constructor Parameters in Java Reflection

When using Java Reflection to inspect **parameters of a method or constructor**, we do not only learn their count, names, and data types; we can also read **annotations attached to each parameter**. This is crucial in frameworks that use annotations to declare how to extract input data, validate values, perform dependency injection, map HTTP/JSON, or configure object creation.

Example:

```java
public void createUser(@Named("username") String name,
                       @Positive int age) {
    // Processing logic.
}
```

This is a **syntax illustration**, in which `@Named` and `@Positive` are application- or library-defined annotations, not built-in Java SE annotations. The two annotations correspond to **two different parameters**. Runtime code can read this metadata if the annotation type is defined with `@Retention(RetentionPolicy.RUNTIME)`.

This lesson focuses on how Reflection identifies annotations **of each parameter** on `java.lang.reflect.Method` and `java.lang.reflect.Constructor`, how to use `Executable.getParameterAnnotations()` and `Parameter`, the difference between annotations on **parameter declarations** and **type uses (type-use)**, as well as `RUNTIME` retention, `-parameters`, repeatable annotations, and synthetic/implicit parameters.

## 1. Related Reflection Classes

A method or constructor is an **executable**. Java has the base class `java.lang.reflect.Executable`; the two key concrete classes are:

- `Method`: metadata of a method.
- `Constructor<T>`: metadata of a constructor.
- `Parameter`: metadata of **a single parameter** in a `Method` or `Constructor`.
- `Annotation`: the base interface `java.lang.annotation.Annotation`, representing a runtime annotation.
- `AnnotatedType`: annotation metadata attached to the **type use** of a parameter, distinct from annotations attached to the parameter declaration.

Commonly used APIs:

| API | Returns | When to Use |
|---|---|---|
| `executable.getParameterCount()` | `int` | Know the parameter count in the executable's metadata |
| `executable.getParameters()` | `Parameter[]` | Need to handle each parameter along with its name, type, and annotations |
| `executable.getParameterAnnotations()` | `Annotation[][]` | Need the annotation list **by parameter index** |
| `parameter.getAnnotations()` | `Annotation[]` | Read runtime annotations attached directly to a parameter |
| `parameter.getAnnotation(MyAnnotation.class)` | `MyAnnotation` or `null` | Look up a specific annotation on the parameter |
| `parameter.isAnnotationPresent(MyAnnotation.class)` | `boolean` | Quickly check whether an annotation exists |
| `parameter.getAnnotationsByType(MyAnnotation.class)` | `MyAnnotation[]` | Retrieve **repeatable** annotations of the same type |
| `parameter.getType()` | `Class<?>` | Inspect declared type after type erasure |
| `parameter.getParameterizedType()` | `Type` | Inspect generic type information of the parameter |
| `executable.getAnnotatedParameterTypes()` | `AnnotatedType[]` | Read `TYPE_USE` annotations on each parameter's type |

`Method` and `Constructor` share many of the methods listed above because both are `Executable`. Consequently, parameter annotation reading logic can often be reused for both.

## 2. Declaring an Annotation for Parameters

An annotation is a type declared with `@interface`. The two most important meta-annotations in this scenario are:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
public @interface Named {
    String value();
}
```

This snippet can be saved as **`Named.java`** and compiled standalone with a JDK; it is a sample annotation, not a program with `main`.

- `@Target(ElementType.PARAMETER)` allows using `@Named` on **parameter declarations** of methods, constructors (and other valid parameter sites).
- `@Retention(RetentionPolicy.RUNTIME)` ensures the annotation is retained and readable by Reflection at runtime.
- `String value();` is an **annotation element**. If the annotation is written `@Named("id")`, calling `named.value()` yields the string `"id"`.
- If an annotation has no `@Retention`, the default is **`RetentionPolicy.CLASS`**; the class file may carry metadata, but core Reflection **does not provide that annotation at runtime**.

Example:

```java
public User(@Named("id") String id) {
    // Constructor of User.
}
```

Parameter annotations can guide frameworks in reading input data. However, Java **does not automatically validate or bind data** merely because a parameter has `@Named`: the framework/application must explicitly read and process the annotation.

### Three Retention Levels

| Retention | Written to Class File? | Core Reflection Reads Annotation at Runtime? |
|---|---|---|
| `SOURCE` | No; compiler typically discards after source processing | No |
| `CLASS` | Yes | No, under standard runtime Reflection annotation rules |
| `RUNTIME` | Yes | Yes, when the annotation type and metadata are accessible |

If `parameter.getAnnotation(Named.class)` returns `null`, it **does not necessarily mean** the annotation was never in source: it may have an unsuitable retention, sit on a type-use rather than the parameter declaration, be placed on another parameter, or be absent from runtime bytecode.

## 3. `getParameterAnnotations()`: Two-Dimensional Array Aligned by Parameter

Suppose we have the following method:

```java
public void submit(@Named("user") String username,
                   @Positive int count,
                   String note) {
}
```

Assume `@Named` and `@Positive` are both runtime annotations targeting `PARAMETER`. When looking up the method:

```java
Method method = Example.class.getMethod(
        "submit", String.class, int.class, String.class);

Annotation[][] annotations = method.getParameterAnnotations();
```

The snippets above are **illustrative**: `Example` and `Positive` must be defined separately, and the code imports `java.lang.reflect.Method`, `java.lang.annotation.Annotation`. The array is organized as:

```text
annotations
  [0] -> annotations of username: @Named("user")
  [1] -> annotations of count:    @Positive
  [2] -> annotations of note:     (empty array)
```

Key rules:

1. **The outer dimension** has one element per parameter in the executable's declaration/signature order. `annotations.length` corresponds to `method.getParameterCount()`.
2. **The inner dimension** holds the annotations of **the parameter at that index**. A parameter can have zero, one, or multiple annotations.
3. A parameter with no runtime annotations is represented by an **empty annotation array**, not by omitting the element from the outer dimension.
4. For an executable with no parameters, the outer array has length **`0`**.
5. Do not rely on the **order of annotations of different types** in the array on the same parameter for business logic; look up by annotation type. In particular, repeatable annotations may be stored via a **container annotation**.

Reliable iteration pattern:

```java
Annotation[][] matrix = method.getParameterAnnotations();
for (int index = 0; index < matrix.length; index++) {
    System.out.println("Parameter " + index
            + " has " + matrix[index].length + " runtime annotations");
}
```

This is an illustrative snippet placed where `method` and the `Annotation` import already exist. To read metadata beyond annotations, retrieve `Parameter[]` and pair by **the same index**.

## 4. `Parameter`: Querying Individual Parameters by Annotation Type

Instead of manually traversing a two-dimensional array, `Parameter` provides an API closer to per-parameter processing:

```java
Parameter[] parameters = method.getParameters();

for (Parameter parameter : parameters) {
    Named named = parameter.getAnnotation(Named.class);
    if (named != null) {
        System.out.println(named.value());
    }
}
```

This example uses a custom `Named` type and an existing `Method method`. Its strength is handling the name, type, and annotations of **a single parameter** in one object.

- `getAnnotation(T.class)` returns a matching annotation or `null`.
- `isAnnotationPresent(T.class)` reports whether an annotation of that type is present per the lookup API.
- `getAnnotations()` returns runtime annotations present on the parameter; for repeatable annotations, you may see the container instead of individual repeated annotations.
- `getDeclaredAnnotations()` on `Parameter` reads annotations declared directly. Parameters **do not have class-like annotation inheritance**; therefore, do not design logic assuming superclass parameter annotations automatically propagate down.
- `getAnnotationsByType(T.class)` is the appropriate way when `T` may be marked `@Repeatable`.

An annotation like `@Named("id")` is runtime metadata read via the `Named` interface. Call `named.value()` to get the annotation value; do not confuse it with **retrieving the argument value** passed when the method actually runs. Reflection metadata describes declarations, not recorded arguments from a specific invocation.

## 5. Complete Java 17+ Example: Method, Constructor, RUNTIME, TYPE_USE, Repeatable

Create a file **`ParameterAnnotationDemo.java`** with the following contents. All test annotations and classes are placed inside one public outer class, so no libraries outside Java SE are required:

```java
import java.lang.annotation.*;
import java.lang.reflect.*;

public class ParameterAnnotationDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.PARAMETER)
    public @interface Label {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.PARAMETER)
    @Repeatable(Tags.class)
    public @interface Tag {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.PARAMETER)
    public @interface Tags {
        Tag[] value();
    }

    @Retention(RetentionPolicy.CLASS)
    @Target(ElementType.PARAMETER)
    public @interface CompileOnly {}

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    public @interface NonNullType {}

    public static class Service {
        public Service(@Label("id") String id,
                       @Tag("create") @Tag("audit") int limit) {}

        public void send(@Label("to") @Tag("email") String recipient,
                         @CompileOnly String token,
                         @NonNullType String body) {}

        public void empty() {}
    }

    public static void main(String[] args) throws Exception {
        Method method = Service.class.getMethod(
                "send", String.class, String.class, String.class);
        Annotation[][] matrix = method.getParameterAnnotations();

        System.out.println("method parameters: "
                + method.getParameterCount());
        for (int i = 0; i < matrix.length; i++) {
            System.out.println("send[" + i + "] annotation count: "
                    + matrix[i].length);
        }

        Parameter[] params = method.getParameters();
        System.out.println("label: "
                + params[0].getAnnotation(Label.class).value());
        System.out.println("tag: "
                + params[0].getAnnotationsByType(Tag.class)[0].value());
        System.out.println("runtime CLASS annotation present: "
                + params[1].isAnnotationPresent(CompileOnly.class));

        System.out.println("type-use annotation on type: "
                + method.getAnnotatedParameterTypes()[2]
                        .isAnnotationPresent(NonNullType.class));
        System.out.println("type-use annotation on declaration: "
                + params[2].isAnnotationPresent(NonNullType.class));

        System.out.println("name present: "
                + params[0].isNamePresent());
        System.out.println("name: " + params[0].getName());

        Constructor<Service> constructor =
                Service.class.getConstructor(String.class, int.class);
        Parameter[] cp = constructor.getParameters();

        System.out.println("constructor label: "
                + cp[0].getAnnotation(Label.class).value());
        Tag[] tags = cp[1].getAnnotationsByType(Tag.class);
        System.out.println("constructor repeatable count: " + tags.length);
        for (Tag tag : tags) {
            System.out.println("constructor tag: " + tag.value());
        }
        System.out.println("constructor raw annotation count: "
                + constructor.getParameterAnnotations()[1].length);
        System.out.println("empty annotation slots: "
                + Service.class.getMethod("empty")
                        .getParameterAnnotations().length);
    }
}
```

Run with JDK 17+ from the directory containing the file:

```bash
javac -parameters ParameterAnnotationDemo.java
java ParameterAnnotationDemo
```

**Stdout verified upon compilation and execution:**

```text
method parameters: 3
send[0] annotation count: 2
send[1] annotation count: 0
send[2] annotation count: 0
label: to
tag: email
runtime CLASS annotation present: false
type-use annotation on type: true
type-use annotation on declaration: false
name present: true
name: recipient
constructor label: id
constructor repeatable count: 2
constructor tag: create
constructor tag: audit
constructor raw annotation count: 1
empty annotation slots: 0
```

### Analysis of Each Output Group

1. `send` has three parameters. On `send[0]`, `@Label("to")` and `@Tag("email")` both have `RUNTIME` retention and `PARAMETER` target, so `getParameterAnnotations()[0]` has **2 annotations**.
2. `send[1]` is annotated with `@CompileOnly`, but that annotation has `CLASS` retention, so it is **not visible via core Reflection**; this parameter's runtime annotation array is empty.
3. `send[2]` has `@NonNullType` with target `TYPE_USE`. It is stored on **the `String` type used at the parameter**, not returned as a parameter-declaration annotation. `getAnnotatedParameterTypes()[2]` sees it, whereas `Parameter.isAnnotationPresent(NonNullType.class)` returns `false`.
4. `Label.value()` returns `to`, and `getAnnotationsByType(Tag.class)` returns the `Tag` annotation to read `email`.
5. Running `javac -parameters` preserves **parameter names at the Reflection level**: `isNamePresent() == true`, and `getName()` returns `recipient`. If compiled **without `-parameters`** in this standard Java source case, `isNamePresent()` may be `false` and the Reflection-synthesized name may be `arg0`. Reading runtime annotations **does not require** `-parameters`.
6. Constructor `Service(String,int)` also has `Parameter[]`. The first parameter contains `@Label("id")`. The second parameter has two repeated `@Tag` annotations; `getAnnotationsByType(Tag.class)` returns **2** elements, whereas `getParameterAnnotations()[1]` normally sees **1 `@Tags` container annotation**.
7. Method `empty()` has no parameters, so `getParameterAnnotations()` returns an outer array of length `0`.

**Important:** the example only **reads metadata**. Nowhere does Java automatically trigger validation for `@Label`, `@Tag`, or `@NonNullType`. The type-use annotation here is just a custom marker; it **does not automatically prevent** passing `null` into the parameter.

## 6. Parameter Annotations vs. Type-Use Annotations

Java supports two annotation positions that can look nearly identical in source code:

```java
void process(@Label("input") String value) {
}

void processType(@NonNullType String value) {
}
```

Both lines are illustrative snippets declared inside an appropriate class, with `@Label` targeting `PARAMETER` and `@NonNullType` targeting `TYPE_USE`.

- `@Label` is a **parameter declaration annotation**. Use `Parameter.getAnnotation(Label.class)` or `Executable.getParameterAnnotations()`.
- `@NonNullType` is a **type-use annotation on `String`**. Use `Executable.getAnnotatedParameterTypes()` and then read `AnnotatedType`.
- If an annotation type is allowed to target both `PARAMETER` and `TYPE_USE`, the compiler can emit metadata for both applicable contexts; do not guess by looking at where `@` appears in source. Check `@Target` and use the appropriate API.

`getAnnotatedParameterTypes()` returns an `AnnotatedType[]` array matching parameter types in order. This is useful when describing types with deeply nested annotations:

```java
void store(java.util.List<@NonNullType String> names) {
}
```

This is an **illustrative snippet** of an annotation on a **generic type argument**, not a parameter declaration annotation. To read `@NonNullType` on `String` inside `List`, inspect `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()` after verifying that the outer `AnnotatedType` is an `AnnotatedParameterizedType`.

Contrast this with annotations targeting only `PARAMETER`: `Parameter.getAnnotations()` APIs do not automatically "drill down" into annotations on generic type arguments, array element layers, or annotated wildcards.

## 7. Repeatable Annotations: Why Counts Can Differ

Suppose an annotation is marked:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@Repeatable(Tags.class)
public @interface Tag {
    String value();
}
```

and the corresponding container is declared:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
public @interface Tags {
    Tag[] value();
}
```

Both snippets are illustrative declarations; they must be placed in appropriate files/classes and import `java.lang.annotation.*`. When used:

```java
public void authorize(@Tag("reader") @Tag("writer") String user) {
}
```

The Java compiler can store the two `@Tag` annotations via the `@Tags` container. Therefore:

- `parameter.getAnnotationsByType(Tag.class)` returns **two `Tag` instances**, suited for handling repeatable annotations.
- `parameter.getAnnotation(Tag.class)` **should not** be assumed to return one of the two `Tag` annotations when they are stored in a container; it may return `null`.
- `parameter.getAnnotations()` and `getParameterAnnotations()` may reflect the **container annotation** `Tags` rather than two individual `Tag` entries. The raw element count in the array differs from the actual number of repeated `Tag` annotations.

The complete example in section 5 confirms `getAnnotationsByType(Tag.class).length == 2` while the raw annotation count on that same constructor parameter is `1`. Do not use `getAnnotations().length` to assert "there is only one tag" without understanding repeatable annotation structure.

## 8. Parameter Names and Annotations Are Two Independent Metadata Kinds

Two APIs frequently appear side by side:

```java
Parameter parameter = method.getParameters()[0];
String name = parameter.getName();
Annotation[] annotations = parameter.getAnnotations();
```

This is an illustrative snippet in code that has a matching `Method method` and imports `Parameter`, `Annotation`. Yet there is an important distinction:

- Ordinary parameter names are retained by the compiler for Reflection via **`javac -parameters`**, so `Parameter.isNamePresent()` returns `true` and `getName()` reflects the compiled name.
- Annotations present in core Reflection require **`@Retention(RUNTIME)`** and the right target; `-parameters` does not make `CLASS`-retention annotations appear at runtime.
- A framework using annotations like `@Named("userId")` can work even if the runtime method parameter is named `arg0`, because it reads the annotation's `value()` element rather than relying on `getName()`.
- Conversely, code using parameter names for binding without checking `isNamePresent()` may misbehave if classes are built without `-parameters`.

Recommendation: when binding by name, prefer explicit annotations if the API design requires stability against compiler flag changes; if using actual parameter names, explicitly enforce and verify `-parameters` in the build pipeline.

## 9. Method, Constructor, and Compiler-Generated Parameters

Normally, `Parameter[]` and the annotation matrix align in the order of the executable's parameter types:

```java
Executable executable = /* Passed-in Method or Constructor */;
Parameter[] parameters = executable.getParameters();
Annotation[][] annotations = executable.getParameterAnnotations();

for (int i = 0; i < parameters.length; i++) {
    System.out.println(i + ": " + parameters[i].getType().getTypeName()
            + ", annotations=" + annotations[i].length);
}
```

This is an illustrative snippet, not a standalone program. When parameter name metadata is absent, indexing by **position** still works.

However, some special constructors have **extra parameters in bytecode**:

- The constructor of a **non-static inner class** may receive a reference to the enclosing class instance.
- An **enum** constructor has internal parameters used by the compiler/JVM in addition to those visible in the source declaration.
- The compiler may generate **synthetic** parameters or mark parameters **implicit/mandated**, depending on the construct and compiler.

Therefore, when writing a general-purpose framework, do not infer that parameter 0 of every constructor always corresponds to the first parameter directly written by the programmer. You can inspect `Parameter.isSynthetic()`, `Parameter.isImplicit()`, and compiler metadata as needed, while pairing `Executable.getParameterTypes()`, `getParameters()`, and annotation arrays from the **same executable**.

In special compiler-generated constructor cases, annotation/parameter metadata sometimes requires careful handling based on actual bytecode and compiler version. Do not use the name `arg0` or assumed parameter counts instead of checking reflection metadata.

### Overriding Does Not Automatically Inherit Parameter Annotations

If an interface or superclass declares a method with parameter annotations, an overriding method in a subclass **does not automatically inherit** the old parameter annotations. Java's `@Inherited` applies only to certain **class-level annotations**, and does not propagate parameter annotations through overriding.

Example:

```java
interface Handler {
    void handle(@Label("command") String command);
}

class HandlerImpl implements Handler {
    @Override
    public void handle(String command) {
    }
}
```

This is an illustrative snippet with an appropriate `Label` runtime annotation. If you inspect parameter annotations on `HandlerImpl.handle(String)`, you must not assume you will see `@Label("command")` from `Handler.handle(String)`. A framework wishing to inherit annotation conventions from an interface must **explicitly locate the corresponding method and read metadata from the interface**.

This is an important distinction between "methods with the same signature across multiple type levels" and "annotations actually attached to parameters of the specific `Method` returned by Reflection".

## 10. Looking Up the Right Method/Constructor Before Reading Annotations

Before reading annotations, select the right executable:

```java
Method m = Service.class.getMethod(
        "send", String.class, String.class, String.class);

Constructor<Service> c =
        Service.class.getConstructor(String.class, int.class);
```

These two illustrative calls match the example class in section 5. `getMethod(name, parameterTypes)` looks up a public method by name + **parameter type signature**; `getConstructor(parameterTypes)` looks up a public constructor. If you need metadata of private executables, use `getDeclaredMethod` or `getDeclaredConstructor`.

Notes:

1. Annotations **do not participate in overload resolution**. Two methods cannot be overloaded merely because annotations on their parameters differ; what matters is the method name and Java parameter type sequence.
2. `int.class` and `Integer.class` are **two different signature types**. During lookup, Java Reflection does not select overloads via boxing of runtime arguments.
3. A varargs parameter `String... names` appears in reflection parameter types as **`String[]`**.
4. A generic parameter such as `List<String>` typically has erased runtime type `List.class`; for generic metadata, use `getGenericParameterTypes()` or `Parameter.getParameterizedType()`.
5. Finding executable metadata does not mean you can **invoke** it. Access checks, module encapsulation, and passed arguments can still affect invocation. Ordinary annotation reading does not require executing the executable.

## 11. Practical Application: Annotation-Driven Validation and Binding

Suppose a framework wants to read the `@Label` annotation to learn the JSON field name or HTTP parameter name:

```java
Method endpoint = Controller.class.getMethod(
        "handle", String.class, int.class);
Parameter[] params = endpoint.getParameters();

for (int i = 0; i < params.length; i++) {
    Label label = params[i].getAnnotation(Label.class);
    if (label == null) {
        continue;
    }
    String externalName = label.value();
    Class<?> targetType = params[i].getType();

    // Map externalName -> input data -> convert to targetType,
    // then validate business conditions before Method.invoke.
}
```

This is a **design illustration snippet**, assuming a `Controller` with an appropriate public method and `Label` annotation. It is not a standalone runnable program. A real framework must add type handling, missing/null field handling, argument count checks, security, validation, and exception handling.

Reasonable workflow:

1. Look up the exact `Method` or `Constructor`.
2. Retrieve `Parameter[]` in executable order.
3. For each parameter, read annotations with `RUNTIME` retention understood by the framework, or type-use annotations where targeted.
4. Read annotation elements (`value()`, `required()`, ... if defined by that annotation) to build binding/validation rules.
5. Convert external data into the Java type matching `getType()`/`getParameterizedType()`.
6. Check errors and access permissions; only then call `Method.invoke` or `Constructor.newInstance` if needed.

**At no step does Java automatically execute annotations for you.** For example, a learner-defined `@Positive` does not automatically prevent a negative number from being passed to the method. With Bean Validation such as Jakarta Validation, dedicated libraries provide the engine and rules; core Reflection is only part of the metadata discovery mechanism.

## 12. Common Errors and Fixes

| Symptom | Possible Cause | Check or Resolution |
|---|---|---|
| `parameter.getAnnotation(MyAnno.class)` is `null` | Annotation lacks `RUNTIME` retention | Check `@Retention(RUNTIME)` declaration; rebuild classes |
| `getParameterAnnotations()[i]` is empty while source has annotation | Annotation is `TYPE_USE`, `CLASS`/`SOURCE`, or wrong parameter read | Use `getAnnotatedParameterTypes()` if `TYPE_USE`; check retention |
| `getAnnotations().length` is 1 even though source has two annotations of the same type | Repeatable annotations are stored via a container | Use `getAnnotationsByType(Tag.class)` |
| `Parameter.getName()` is `arg0` | No runtime parameter name metadata | Compile with `javac -parameters`, check `isNamePresent()` |
| `getMethod(...)` throws `NoSuchMethodException` | Lookup name, count, or parameter types are wrong; method is not public | Check exact overload and visibility; consider `getDeclaredMethod` |
| Annotation is on interface but missing on overriding class | Parameter annotations are not inherited through overriding | Framework must read annotations from the interface/supertype method |
| Iterating annotations by parameter name gets misaligned | Parameter names are unreliable without `-parameters` or with compiler-generated params | Prefer indices combined with `getParameters()` from the same executable |
| Code calling `getAnnotation(...).value()` throws `NullPointerException` | Matching runtime annotation is absent | Check for `null` or use `isAnnotationPresent` |
| Annotation is read but no validation runs | Reflection only reads metadata; it provides no validation engine | Write processing logic or integrate a dedicated framework |
| Errors when reading elements of unusual runtime annotations | Annotation type or class metadata changed, type not present, mismatched value | Check runtime classpath/modules and compatibility; some APIs can throw errors like `TypeNotPresentException`, `AnnotationTypeMismatchException`, or `IncompleteAnnotationException` |

## 13. Self-Check Questions

**Question 1.** A method has three parameters, but only the second parameter carries a runtime `@Label`. How many outer elements does `getParameterAnnotations()` have?

**Answer:** Three elements. The first and third parameters correspond to empty annotation arrays; the second element contains the annotation.

**Question 2.** An annotation declares `@Target(PARAMETER)` without `@Retention`. Is Reflection guaranteed to read this annotation?

**Answer:** No. The default retention is `CLASS`; core Reflection does not expose it as a runtime annotation. Reading via `Parameter.getAnnotation` requires `RetentionPolicy.RUNTIME`.

**Question 3.** Why doesn't `javac -parameters` make `@CompileOnly` in the example appear?

**Answer:** `-parameters` stores **parameter name** metadata. `@CompileOnly` has `CLASS` retention, so it is not returned in runtime annotation APIs; these are two separate mechanisms.

**Question 4.** `@NonNullType` with target `TYPE_USE` is placed before `String body`. Which API is appropriate to read it?

**Answer:** `method.getAnnotatedParameterTypes()[index]`, then `AnnotatedType.getAnnotation(NonNullType.class)` or `isAnnotationPresent`. Do not assume it is a parameter-declaration annotation.

**Question 5.** A parameter has `@Tag("a") @Tag("b")`. What should be used to retrieve all tags?

**Answer:** `parameter.getAnnotationsByType(Tag.class)`, because `Tag` is repeatable; do not use `getAnnotation(Tag.class)` expecting a single arbitrary tag.

**Question 6.** An interface declares parameter `@Label("id")`, while the implementing class overrides the method without repeating the annotation. Does the implementing class automatically receive that annotation when queried via Reflection?

**Answer:** No. Parameter annotations are not automatically inherited when a method is overridden. A framework must locate the interface method and read metadata there if it wants to apply interface rules.

**Question 7.** Can constructors be queried for parameter annotations just like methods?

**Answer:** Yes. `Method` and `Constructor` both inherit from `Executable`, so they have `getParameters()`, `getParameterAnnotations()`, and `getAnnotatedParameterTypes()`; keep in mind implicit/synthetic parameters on certain special constructors.

## Official Reference Sources

- Java SE API: `java.lang.reflect.Executable` — `getParameters`, `getParameterCount`, `getParameterAnnotations`, `getAnnotatedParameterTypes`.
- Java SE API: `java.lang.reflect.Parameter` — `getName`, `isNamePresent`, `getType`, `getParameterizedType`, `getAnnotationsByType`, `isSynthetic`, `isImplicit`.
- Java SE API: `java.lang.reflect.AnnotatedType`, `AnnotatedParameterizedType`.
- Java SE API: `java.lang.annotation.Retention`, `RetentionPolicy`, `Target`, `ElementType`, `Repeatable`.
- Java Language Specification: sections on annotation types, type annotations, and method/constructor parameters; Java Virtual Machine Specification: runtime-visible parameter/type annotations.
- `javac` tool: `-parameters` option to store parameter names used by Reflection.

**Remember:** Annotations on individual parameters are read via **`Executable.getParameterAnnotations()`** or **`Parameter.getAnnotation(s)`**, aligned by the exact parameter index. Only annotations with **`RUNTIME` retention** appear through core Reflection; `TYPE_USE` annotations are read via **`AnnotatedType`**; repeatable annotations should be retrieved with **`getAnnotationsByType`**. Whether parameter names require `-parameters` is separate from retaining annotations, and having an annotation **does not automatically run validation**.
