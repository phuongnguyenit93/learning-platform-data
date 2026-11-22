# RUNTIME: storing annotations in the class file and making them readable at runtime

When an annotation type is declared with `@Retention(RetentionPolicy.RUNTIME)`, annotations applied at positions where metadata can be stored are retained in the `.class` file and can be queried at runtime via Java's Reflection APIs. This is the foundational mechanism that enables programs or libraries to discover metadata on classes, methods, fields, constructors, parameters, and appropriate reflective objects.

An important point to understand accurately: **`RUNTIME` retention makes metadata readable; it does not generate behavior by itself**. To invoke a method, validate a field, or configure a component based on an annotation, there must still be code that performs that work.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain the exact meaning of `RetentionPolicy.RUNTIME` across the source → bytecode → runtime lifecycle.
- Distinguish `RUNTIME` from `SOURCE` and `CLASS`, including the default when `@Retention` is omitted.
- Create annotations using `@Retention(RUNTIME)` and query them on classes, methods, fields, and parameters using Reflection.
- Understand the differences between `getAnnotation`, `getDeclaredAnnotation`, `getAnnotations`, and the APIs for repeatable annotations.
- Recognize the limitations of `@Inherited`, `@Target`, annotations on local variable declarations, and type-use annotations.
- Know how to inspect metadata in a class file using `javap -v` and explain why annotations do not trigger logic on their own.

## 2. What does `@Retention(RUNTIME)` mean?

`@Retention` is a **meta-annotation** in the `java.lang.annotation` package: you place it on the definition of an annotation type to choose how long annotations of that type are retained.

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface AuditMarker {
    String value();
}
~~~

This snippet is an illustrative type declaration, not a complete program yet. When code uses `@AuditMarker("login")` on a suitable element, the compiler retains the metadata in bytecode, and the program can query the annotation while the JVM is running.

The three values of `RetentionPolicy`:

| Policy | Present in source | Typically has metadata in `.class` | Visible to standard runtime Reflection? | Common purpose |
| --- | --- | --- | --- | --- |
| `SOURCE` | Yes | No | No | Checking/processing information at compile time |
| `CLASS` | Yes | Yes | No | Tools that inspect or transform bytecode |
| `RUNTIME` | Yes | Yes | Yes | Runtime code reads annotations and determines behavior |

**If an annotation type does not have `@Retention`, Java defaults to `CLASS`**. Therefore, when you want to inspect it with `Class.getAnnotation(...)`, do not forget `@Retention(RetentionPolicy.RUNTIME)`.

For common declaration positions such as classes, fields, methods, or parameters, the model above helps predict the outcome. The Java Language Specification has an exception you should know: annotations on **local variable declarations** and on **lambda formal parameter declarations** are not retained as declaration annotations in the binary, even when the annotation type specifies `RUNTIME`. Those annotations must be distinguished from **type-use annotations** on data types: type annotations have their own retention rules and can be written to bytecode when retention is appropriate. Therefore, `RUNTIME` does not mean "every @ symbol everywhere can be queried through the same API".

## 3. Lifecycle: source → class file → Reflection

~~~text
.java source code
    |
    |  @Retention(RUNTIME) on annotation type
    |  @MyAnnotation(...) at a valid position
    v
javac compiles
    |
    +--> .class with runtime-visible metadata
    |       (e.g., RuntimeVisibleAnnotations attribute)
    v
JVM loads the class when needed
    |
    +--> runtime code uses Reflection on the right element
             |
             +--> Class / Method / Field / Parameter / ...
             +--> getAnnotation(MyAnnotation.class)
                       |
                       +--> annotation object to read elements
                       +--> application itself decides the next behavior
~~~

In the class file, annotations using `RUNTIME` are typically represented by attributes such as `RuntimeVisibleAnnotations`; annotations on parameters have `RuntimeVisibleParameterAnnotations`; annotations at type-use positions have `RuntimeVisibleTypeAnnotations`. `CLASS` annotations can reside in the `RuntimeInvisibleAnnotations` attribute or its corresponding variants, but the name "Invisible" here refers to **runtime Reflection**, and does not mean bytecode tools cannot read them.

The JVM or Reflection **does not automatically scan the entire classpath and process every annotation**. The application must already have a way to locate the class/member to inspect and actively invoke the API or use a library/framework that does so.

`RUNTIME` also does not automatically modify the bytecode of an annotated method, insert logging calls, instantiate objects, or create dependency injection or transactions. Those behaviors, if present, come from other code.

## 4. Declaring a RUNTIME annotation properly

An annotation that can be read on classes and methods can be defined as follows:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface EndpointInfo {
    String value();
    int version() default 1;
}
~~~

Meaning of each part:

- `@Retention(RetentionPolicy.RUNTIME)`: the annotation is retained so it can be queried at runtime.
- `@Target({TYPE, METHOD})`: allows use on type declarations and methods. `@Target` restricts placement, whereas `@Retention` restricts lifetime; they answer two different questions.
- `String value()`: a required element, for example `@EndpointInfo("orders")`.
- `int version() default 1`: an element with a default value. If the usage site does not provide `version`, reading it returns `1`.

There is no requirement to use `@Target` in order to have `RUNTIME` retention, but declaring explicit targets helps the compiler report errors early if the annotation is placed in the wrong location. `@Target(TYPE)` is also not identical to `@Target(TYPE_USE)`; an annotation at a type-use site may have to be queried via `AnnotatedType` instead of `Class.getAnnotation`.

## 5. Standalone Java 17+ example: comparing RUNTIME, CLASS, and SOURCE

Create the file **`RuntimeRetentionDemo.java`** with the entire content below (no `package` declaration). All annotation types and helper classes are non-`public`; there is only one public class matching the file name.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;

@Retention(RetentionPolicy.RUNTIME)
@Target({
    ElementType.TYPE,
    ElementType.METHOD,
    ElementType.FIELD,
    ElementType.PARAMETER
})
@interface RuntimeTag {
    String value();
    int level() default 1;
}

@Retention(RetentionPolicy.CLASS)
@Target(ElementType.TYPE)
@interface ClassTag {}

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
@interface SourceTag {}

@RuntimeTag(value = "service", level = 2)
@ClassTag
@SourceTag
class ExampleService {
    @RuntimeTag("action")
    public String process(@RuntimeTag("input") String value) {
        return value;
    }

    @RuntimeTag("id")
    private int id;
}

public class RuntimeRetentionDemo {
    public static void main(String[] args)
            throws ReflectiveOperationException {

        Class<ExampleService> type = ExampleService.class;
        RuntimeTag onType =
                type.getDeclaredAnnotation(RuntimeTag.class);
        Method method =
                type.getDeclaredMethod("process", String.class);

        System.out.println("type=" +
                onType.value() + ":" + onType.level());
        System.out.println("method=" +
                method.getAnnotation(RuntimeTag.class).value() + ":" +
                method.getAnnotation(RuntimeTag.class).level());
        System.out.println("field=" +
                type.getDeclaredField("id")
                    .getAnnotation(RuntimeTag.class).value());
        System.out.println("parameter=" +
                method.getParameters()[0]
                      .getAnnotation(RuntimeTag.class).value());

        System.out.println("runtime-visible=" +
                type.isAnnotationPresent(RuntimeTag.class));
        System.out.println("class-visible=" +
                type.isAnnotationPresent(ClassTag.class));
        System.out.println("source-visible=" +
                type.isAnnotationPresent(SourceTag.class));
    }
}
~~~

Run from the directory containing the file using JDK 17 or later:

~~~bash
javac -encoding UTF-8 RuntimeRetentionDemo.java
java RuntimeRetentionDemo
~~~

**Exact stdout:**

~~~text
type=service:2
method=action:1
field=id
parameter=input
runtime-visible=true
class-visible=false
source-visible=false
~~~

### Explaining the results

1. Class `ExampleService` has `@RuntimeTag(value = "service", level = 2)`. `getDeclaredAnnotation(RuntimeTag.class)` finds metadata declared **directly** on the class, so the first line is `type=service:2`.
2. Method `process(String)` has `@RuntimeTag("action")`. Because `level` is omitted, this element takes the default value `1`; hence the result is `method=action:1`.
3. Field `id` is declared `private`. `getDeclaredField("id")` can still retrieve metadata on the field declaration without needing to read or modify the **value** of the private field; the result is `field=id`. Accessing the contents of a private field is a separate matter and may be restricted.
4. The method parameter has `@RuntimeTag("input")`. `method.getParameters()[0].getAnnotation(...)` returns the annotation on the first parameter, producing `parameter=input`. The `-parameters` option is not needed just to read parameter annotations; `-parameters` mainly preserves source parameter names for Reflection.
5. `isAnnotationPresent(RuntimeTag.class)` is `true` on the class because runtime-visible metadata is available.
6. `ClassTag` has `CLASS` retention: the annotation can appear in bytecode, but runtime Reflection cannot see it, so `class-visible=false`.
7. `SourceTag` has `SOURCE` retention: the annotation is not retained in the class file under this policy, so `source-visible=false`.

The example **does not call** `new ExampleService().process(...)`. Reading metadata on a method does not cause the method to be executed.

## 6. Inspecting the class file yourself with `javap -v`

After compiling the example above, run:

~~~bash
javap -v ExampleService
~~~

When browsing the class metadata section, you will encounter groups like:

~~~text
RuntimeVisibleAnnotations:
  ...
    RuntimeTag(...)
RuntimeInvisibleAnnotations:
  ...
    ClassTag
~~~

The snippet above **illustrates the structure of the relevant sections**, not a complete transcript of `javap -v` output (constant pool indices, layout, line numbers, and notation depend on the compiler).

To verify thoroughly:

- Look for `RuntimeVisibleAnnotations` on the class, field, and method annotated with `@RuntimeTag`.
- Look for `RuntimeVisibleParameterAnnotations` on the `process` method to see the annotation attached to the `String value` parameter.
- Look for `RuntimeInvisibleAnnotations` for `ClassTag` on the class.
- Confirm there is no `SourceTag` annotation usage in the stored metadata of `ExampleService.class`.

Do not confuse `ClassTag` appearing in the constant pool or tool output text with being readable via `Class.getAnnotation`. Whether Reflection can see metadata depends on the retention policy and how the metadata is stored, not merely on whether the type name appears somewhere in disassembled output.

To observe `TYPE_USE` annotations, you need to declare an annotation with `@Target(TYPE_USE)` and look it up through an appropriate Reflection API such as `Field.getAnnotatedType()` or `Method.getAnnotatedReturnType()`. That is a separate storage location and reading mechanism, and is not automatically the same as annotations declared on a field/method.

## 7. Choosing the right Reflection API

With `RUNTIME`, a necessary condition is that the annotation is **actually attached at the position the API is inspecting**. An annotation on a class does not implicitly appear when querying a method of that class.

| API | Purpose | Notes |
| --- | --- | --- |
| `element.getAnnotation(Tag.class)` | Retrieves an annotation of type `Tag` if considered present; may return `null` | When reading a class, `@Inherited` may take effect according to its own rules |
| `element.getDeclaredAnnotation(Tag.class)` | Retrieves only an annotation declared directly on the element | Does not search superclasses |
| `element.isAnnotationPresent(Tag.class)` | Checks whether an annotation of type `Tag` is present according to `getAnnotation` rules | Returns a boolean |
| `element.getAnnotations()` | Returns annotations present according to the API rules | On a class, may include certain inherited annotations |
| `element.getDeclaredAnnotations()` | Returns only direct annotations | Returns an empty array if none are present |
| `element.getAnnotationsByType(Tag.class)` | Retrieves multiple annotations, supporting `@Repeatable` and applicable inheritance rules | Returns an array, possibly of length 0 |
| `element.getDeclaredAnnotationsByType(Tag.class)` | Retrieves repeatable annotations declared directly or indirectly via a container | Does not inspect superclasses |

Here, `element` is an object implementing `AnnotatedElement`, such as `Class`, `Method`, `Field`, or `Parameter`. Use `getDeclaredMethod(...)`/`getDeclaredField(...)` when you need members declared on the class itself, including `private` members. If you need element values after finding the annotation, call methods on the annotation instance, such as `tag.value()`, `tag.level()`.

An important note about `@Repeatable`: when an annotation type is repeatable, the compiler can place multiple annotations inside a **container annotation**. `getAnnotationsByType(...)`/`getDeclaredAnnotationsByType(...)` are designed to read through the container. You should not assume `getAnnotation(Tag.class)` always returns an element when multiple annotations of the same type appear at the same position.

### Handling potentially absent annotations

`getAnnotation(...)` does not throw an error simply because an annotation is absent: it returns `null`. Correct example:

~~~java
RuntimeTag tag = ExampleService.class.getAnnotation(RuntimeTag.class);
if (tag != null) {
    System.out.println(tag.value());
}
~~~

This is an illustrative snippet using the types from the program above. In code that uses libraries, always handle the possibility of a missing annotation, an unexpected actual target, inheritance not being applied, or a class compiled with a different retention than expected. Calling `tag.value()` on `null` is what causes the program to fail with a `NullPointerException`.

## 8. `RUNTIME` does not mean annotations are inherited

For example, suppose there are two classes:

~~~java
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@interface Category {
    String value();
}

@Category("base")
class Parent {}

class Child extends Parent {}
~~~

`Child.class.getAnnotation(Category.class)` can return the annotation from `Parent` because **`Category` has `@Inherited` and is placed on a class declaration**. However, `Child.class.getDeclaredAnnotation(Category.class)` returns `null`, because `Child` does not declare the annotation directly.

All classes that use `@Inherited` also need an appropriate retention policy if you want runtime Reflection to see the annotation. **`RUNTIME` alone does not establish an inheritance relationship**.

Limitations of `@Inherited`:

- Only takes effect when querying annotations on a **class**, along the superclass chain, and when the annotation type has `@Inherited`.
- Does not automatically apply in the same way to interfaces that a class implements.
- Does not automatically transfer annotations on a superclass's methods/fields onto the subclass's methods/fields.
- The `getDeclared...` APIs intentionally ignore inherited annotations.

This is an illustrative snippet and should not be appended to `RuntimeRetentionDemo.java` to form a single program without adjusting imports/file names accordingly.

## 9. How is RUNTIME used in applications?

A practical scenario is needing to select methods allowed to run by command name. You can define `@Command("run")` with `RUNTIME` retention, use Reflection to find annotated methods, read the `"run"` value, and register them in a lookup table. The lookup table then dispatches calls when the user actually issues a command.

Those steps are carried out by a **processor** written by the application/framework; `@Command` merely carries the command name. Without scanning and registration code, the annotation does not create a command on its own.

Similarly, the Java ecosystem uses runtime annotations as part of validation, dependency injection, mapping, or test discovery mechanisms. However, a framework may combine compile-time techniques, bytecode scanning, and intermediate mechanisms; you should not assume every framework annotation is read solely via `getAnnotation(...)`.

**Annotation processors in `javac` can also observe annotations at compile time**, so `RUNTIME` retention is not a prerequisite for a processor to run. When the goal is strictly compile-time processing, `SOURCE` is sometimes the more appropriate choice.

### Choosing a policy based on your needs

- Only need the compiler or an annotation processor to inspect metadata in source code? Consider `SOURCE`.
- Want metadata present in `.class` for bytecode post-processing tools without needing runtime Reflection? Consider `CLASS`.
- Need a program/library to read metadata on elements while the JVM is running? Choose `RUNTIME` and set an appropriate `@Target`.

Choose retention based on **who will read the data and when it will be read**, not based on the annotation's name or a desire for automation. Longer retention also does not turn an annotation into a security mechanism: you cannot rely solely on the presence of a custom `@Secured` annotation to protect a call without a processor that actually checks permissions.

## 10. Common cases and pitfalls

### 10.1. Forgetting to declare `@Retention`

~~~java
@interface Marker {
    String value();
}
~~~

`@Marker` will default to `CLASS`. Even if it is placed on a class and `javac` compiles successfully, standard runtime Reflection will not see an instance of that annotation. To read it at runtime, add `@Retention(RetentionPolicy.RUNTIME)` **on the annotation type**, then recompile the necessary components.

### 10.2. Using the wrong Reflection element

If you attach `@RuntimeTag` to `process(...)` but call `ExampleService.class.getAnnotation(RuntimeTag.class)`, the result refers to **the annotation on the class**, not the method. In the main example, the class also has `@RuntimeTag`, so you get `"service"` instead of `"action"`. Obtain the right `Method` first and then query it.

### 10.3. Confusing `getDeclaredAnnotation` with `getAnnotation`

With an `@Inherited` annotation on a superclass, `getAnnotation` on a subclass can retrieve the inherited value; `getDeclaredAnnotation` only retrieves direct declarations, so it may return `null`. Use the API that matches your intent, especially when a framework exhibits metadata inheritance behavior.

### 10.4. Assuming `RUNTIME` automatically causes annotations to be processed

Simply creating `@Audit` and placing it on a method will not generate any logs. You must write or integrate audit-handling code, and verify whether it actually looks up that method/annotation.

### 10.5. Assuming an annotation in one position appears in every API

Declaration annotations, parameter annotations, and type-use annotations have different lookup APIs. Placing `@Target(FIELD)` and reading via `Field.getAnnotatedType()` is different from placing `@Target(TYPE_USE)` on the field's **type**. Determine whether the annotation describes a declaration or a type use.

### 10.6. Treating local variables as an exception like fields

A declaration annotation placed on a local variable declaration is not stored in the binary like an annotation on a field, even with `RUNTIME`. There is no `LocalVariable` Reflection API to retrieve declaration annotations similar to `Field`. If the goal is type-use metadata, that is a different topic and requires using the corresponding API/bytecode.

### 10.7. Confusing it with preserving parameter names

`-parameters` enables Reflection to see Java parameter names such as `value` instead of synthetic names. `RUNTIME` parameter annotations can be retrieved with `Method.getParameters()[i].getAnnotation(...)` even when `-parameters` is not enabled. These two kinds of metadata are independent.

### 10.8. Inferring runtime behavior solely from `javap`

Seeing `RuntimeVisibleAnnotations` in bytecode only proves that the metadata is stored and can be read properly by Reflection. It does not prove that a library scanned the class, registered the component, or applied any logic. You need to inspect the actual dispatching code.

## 11. Self-verification practice exercises

1. **Retention:** Run `RuntimeRetentionDemo.java`, then change `RuntimeTag`'s `@Retention(RetentionPolicy.RUNTIME)` to `CLASS`. Predict the output before running; adjust the program to check for `null` safely and avoid calling `value()` on an absent annotation.
2. **Bytecode:** Run `javap -v ExampleService`. Compare `RuntimeVisibleAnnotations` and `RuntimeInvisibleAnnotations`, locate `RuntimeVisibleParameterAnnotations`; explain why `SourceTag` is absent from the annotation usage section of the class file.
3. **API:** Obtain the `Method` corresponding to `process(String)` and inspect `getAnnotation(RuntimeTag.class)`. Compare it with the result when reading the annotation on `Class`.
4. **Target:** Narrow `RuntimeTag`'s `@Target` down to `METHOD` while keeping the other placement sites. Observe the compiler error: retention does not replace target checking.
5. **Inheritance:** Create `Parent`/`Child` and `@Category` with `@Inherited` as illustrated. Compare `Child.class.getAnnotation(...)` and `getDeclaredAnnotation(...)`, then remove `@Inherited` to contrast.
6. **Missing annotation:** Write a class without `@RuntimeTag`. Use `getAnnotation(...)` together with a `null` check, and confirm the program has no errors.
7. **Design:** Design `@Action(name = "...")` with `RUNTIME` retention for methods. Specify what a handler class must do to find the annotation and execute the right method, along with the points that need to be controlled regarding access permissions and errors.

Assess yourself with four questions: **where the annotation is**, **what retention it has**, **which API can read it**, and **who performs the behavior after reading it**. If you can answer all four, you understand the role of `RUNTIME` in Java Core.

## 12. Key Takeaways

- `@Retention(RetentionPolicy.RUNTIME)` retains annotations in the class file and allows runtime Reflection to query applicable metadata.
- Omitting `@Retention` defaults to `CLASS`, meaning the annotation typically cannot be read by runtime Reflection.
- `@Target` and `@Retention` are independent: one controls where an annotation can be placed, and the other controls how long it persists.
- `getAnnotation` can return `null`; `getDeclaredAnnotation` only checks direct declarations. `@Inherited` affects certain queries on classes, not every member.
- Declaration annotations on local variables and lambda formal parameters are exceptions that are not stored in the binary; type-use annotations must be considered separately.
- The presence of a `RUNTIME` annotation does not execute logic on its own. Handler code is what turns metadata into application behavior.

### References

- [Java Language Specification 17, `9.6.4.2: @Retention](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.2).
- [Java SE 17: Retention](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Retention.html).
- [Java SE 17: RetentionPolicy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/RetentionPolicy.html).
- [Java SE 17: AnnotatedElement](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html).
- [Java SE 17: Class Reflection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html).
