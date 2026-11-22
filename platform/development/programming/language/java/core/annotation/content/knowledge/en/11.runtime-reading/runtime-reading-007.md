# Reading Annotation Default Values with `Method.getDefaultValue()` in Java

## 1. What Is the Default Value of an Annotation Element?

In Java, annotations are declared using `@interface`. Annotation elements look like parameterless methods. Each element can **declare a default value** using the `default` keyword:

~~~java
@interface JobOptions {
    String owner() default "platform";
    int retries() default 3;
    boolean enabled();
}
~~~

There are three elements:

- `owner()`: defaults to `"platform"`.
- `retries()`: defaults to `3`.
- `enabled()`: **has no default**, so the annotation usage site must provide a value.

For example:

~~~java
@JobOptions(enabled = true)
class Worker {
}
~~~

When Java parses the annotation on `Worker`, the `owner` and `retries` elements receive their default values, while `enabled` has the supplied value `true`.

If the goal is simply to **know what values the actual annotation on a class has**, we typically call the element method on the annotation object, such as `options.owner()`. However, if we want to **inspect which defaults the annotation type itself declared**, Java Reflection provides:

~~~java
java.lang.reflect.Method.getDefaultValue()
~~~

This is the focus of this article: **`Method.getDefaultValue()` reads the `default` value declared in the annotation element definition**, rather than the value passed at a specific usage site.

## 2. Signature and Contract of `Method.getDefaultValue()`

As of Java SE 17, the method in `java.lang.reflect.Method` has the signature:

~~~java
public Object getDefaultValue()
~~~

Meaning:

1. If `Method` represents **an element in an annotation type that declares a `default`**, it returns that default value.
2. If the annotation element **does not declare a `default`**, it returns `null`.
3. If `Method` **does not represent an annotation element** (for example, a regular class method), it also returns `null`.
4. The static return type is `Object` because annotation elements can have many valid Java types. The actual object may be a primitive wrapper, `String`, `Class`, an enum value, a nested annotation, or an array of values.

Important: `null` here is a **signal that there is no default value**, not a default value of `null`. Java does not allow declaring `default null` in an annotation element.

To call `getDefaultValue()`, we first need to obtain the `Method` of the **annotation type**:

~~~java
Method method = JobOptions.class.getDeclaredMethod("retries");
Object defaultValue = method.getDefaultValue();
~~~

This snippet is **only an illustrative fragment**; it requires declaring `JobOptions` and importing `java.lang.reflect.Method`, and `getDeclaredMethod` can throw `NoSuchMethodException`.

In the example above, `defaultValue` represents the integer `3` as an `Integer`, because `Method.getDefaultValue()` returns `Object`. If `JobOptions.class.getDeclaredMethod("enabled").getDefaultValue()` is called, the result is `null` because `enabled` has no `default`.

## 3. Distinguishing Three Easily Confused Concepts

| What You Want to Know | Appropriate Way to Read | Example Result |
| --- | --- | --- |
| What `default` does the annotation type declare for `retries()`? | `JobOptions.class.getDeclaredMethod("retries").getDefaultValue()` | `3` |
| What is the actual `retries` value of the annotation applied to `Worker`? | `Worker.class.getAnnotation(JobOptions.class).retries()` | `3` or the overridden value |
| Is `@JobOptions` actually applied to `Worker`? | `Worker.class.isAnnotationPresent(JobOptions.class)` | `true` if the annotation is visible at runtime |

Suppose the usage site writes:

~~~java
@JobOptions(enabled = true, retries = 8)
class CustomWorker {
}
~~~

Then:

- `JobOptions.class.getDeclaredMethod("retries").getDefaultValue()` **is still `3`**, because the default declared on the annotation type does not change.
- `CustomWorker.class.getAnnotation(JobOptions.class).retries()` is **`8`**, because this is the effective value at the usage site.
- `owner()` of the annotation on `CustomWorker` is `"platform"` because it is not overridden.
- `enabled()` equals `true`, even though `JobOptions.class.getDeclaredMethod("enabled").getDefaultValue()` is `null`.

Thus, the two read operations answer **two different questions**. `getDefaultValue()` reads the **definition**, whereas calling an element method on an annotation object reads the **effective value** at a specific location.

## 4. Complete Java 17 Program: Printing Both Defaults and Effective Values

Create a single file **`DefaultValueDemo.java`**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Comparator;

enum Level {
    LOW, HIGH
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface JobOptions {
    String owner() default "platform";
    int retries() default 3;
    Level level() default Level.HIGH;
    Class<?> type() default String.class;
    String[] tags() default {"java", "reflection"};
    boolean enabled();
}

@JobOptions(enabled = true, retries = 8)
class Worker {
}

public class DefaultValueDemo {
    public static void main(String[] args)
            throws ReflectiveOperationException {

        Method[] elements = JobOptions.class.getDeclaredMethods();
        Arrays.sort(elements, Comparator.comparing(Method::getName));

        JobOptions options = Worker.class.getAnnotation(JobOptions.class);

        for (Method element : elements) {
            Object declaredDefault = element.getDefaultValue();
            Object effective = element.invoke(options);

            System.out.println(element.getName()
                    + " | default=" + format(declaredDefault)
                    + " | effective=" + format(effective));
        }
    }

    private static String format(Object value) {
        if (value == null) {
            return "<none>";
        }
        if (value instanceof String[] texts) {
            return Arrays.toString(texts);
        }
        if (value instanceof Class<?> type) {
            return type.getSimpleName() + ".class";
        }
        return String.valueOf(value);
    }
}
~~~

Compile and run with **JDK 17+**:

~~~bash
javac -encoding UTF-8 DefaultValueDemo.java
java DefaultValueDemo
~~~

**Exact stdout:**

~~~text
enabled | default=<none> | effective=true
level | default=HIGH | effective=HIGH
owner | default=platform | effective=platform
retries | default=3 | effective=8
tags | default=[java, reflection] | effective=[java, reflection]
type | default=String.class | effective=String.class
~~~

### Why Is the Output in This Order?

`Class.getDeclaredMethods()` **does not guarantee the order** of the returned methods. The example uses:

~~~java
Arrays.sort(elements, Comparator.comparing(Method::getName));
~~~

to sort by element name, ensuring stdout always appears in the order `enabled`, `level`, `owner`, `retries`, `tags`, `type`. If the sorting line is omitted, tests should not rely on the order of methods returned by reflection.

### Why Does `retries` Have Two Different Values?

The definition of `JobOptions` contains `int retries() default 3;`. However, `Worker` uses `@JobOptions(enabled = true, retries = 8)`.

Therefore:

- `element.getDefaultValue()` returns `Integer(3)`.
- `element.invoke(options)` invokes the `retries()` element on **`Worker`'s annotation instance**, returning `Integer(8)`.

For `owner`, the usage site does not pass a value, so both are `"platform"`.

For `enabled`, there is no `default`, so `getDefaultValue()` returns `null`, yet Java still requires specifying `enabled = true` at the usage site; thus `element.invoke(options)` returns `true`.

### Why Is `@Retention(RUNTIME)` Needed in the Example?

The program reads the annotation on the `Worker` class using:

~~~java
JobOptions options = Worker.class.getAnnotation(JobOptions.class);
~~~

This statement requires the metadata of the **annotation usage** to be retained at runtime. Therefore, the example applies `@Retention(RetentionPolicy.RUNTIME)` to `JobOptions`.

However, `JobOptions.class.getDeclaredMethod("owner").getDefaultValue()` alone reads the **default from the annotation type definition**, not from `Worker`. The `default` value is represented in the annotation type's class file (the `AnnotationDefault` attribute) and can be retrieved if the annotation type is validly loaded, even when that annotation's `@Retention` is `SOURCE` or `CLASS`. One should not infer that `getDefaultValue()` requires `RUNTIME`; **reading the annotation applied to a class** is the actual reason the example uses `RUNTIME`.

## 5. Allowed Return Types for Default Values

Annotation elements have return type restrictions defined by the Java language. Valid types include:

- Primitive types: `byte`, `short`, `int`, `long`, `char`, `float`, `double`, `boolean`.
- `String`.
- `Class` or a valid parameterized invocation of `Class`, such as `Class<?>`.
- An **enum type**.
- An **annotation type**.
- One-dimensional arrays of the allowed types above.

You cannot use `Object`, `List<String>`, `Map<...>`, multidimensional arrays, or arbitrary object types as annotation element types.

Table illustrating how `getDefaultValue()` represents data:

| Element Declaration | Return Value When Calling `getDefaultValue()` |
| --- | --- |
| `int count() default 5;` | `Integer` holding the value `5` |
| `boolean active() default true;` | `Boolean.TRUE` |
| `String label() default "main";` | The string `"main"` |
| `Class<?> type() default String.class;` | `Class` corresponding to `String.class` |
| `Level level() default Level.HIGH;` | Enum constant `Level.HIGH` |
| `String[] names() default {"a", "b"};` | A `String[]` array with two elements |
| `String required();` | `null` because there is no default |

In the table, `Level` is assumed to be the enum declared as in the runnable program.

### With Nested Annotations

An annotation can contain another annotation as an element value:

~~~java
@interface Nested {
    String code() default "ok";
}

@interface Outer {
    Nested nested() default @Nested;
}
~~~

These are two valid annotation definitions. If we call:

~~~java
Object value = Outer.class
        .getDeclaredMethod("nested")
        .getDefaultValue();
~~~

`value` is an object representing the `Nested` annotation type. You can inspect it and read its element:

~~~java
Nested nested = (Nested) value;
System.out.println(nested.code());
~~~

The illustrative snippet above must be placed inside a method that throws or handles `NoSuchMethodException`; the printed output will be:

~~~text
ok
~~~

The default of `Nested.code()` is applied because `@Nested` in the `Outer` definition does not pass `code`.

### With Arrays

If the default element value is an array, `getDefaultValue()` returns an **array object**, not a string formatted like `"[java, reflection]"`. In the `DefaultValueDemo` example, we explicitly call `Arrays.toString(texts)` to print the array cleanly and inspect individual elements.

Printing an array directly with `System.out.println(element.getDefaultValue())` invokes the array's `Object.toString()`, which typically produces a string such as `[Ljava.lang.String;@...` instead of printing the elements. Therefore, when writing tests or tools to audit annotation defaults, you need to handle arrays separately (different primitive array types require the corresponding `Arrays.toString` overloads).

## 6. How Does Reflection Read Default Definitions?

At the bytecode level, the default value of an annotation element resides in the metadata of the **annotation type**, not solely at the usage site.

For example, `JobOptions.class` contains the declaration of the `retries()` method and the default value information `3`. If you want to inspect the bytecode generated by `javac`, after running the program in Section 4, run:

~~~bash
javap -v JobOptions
~~~

In the verbose output of `javap`, you can find the **`AnnotationDefault`** attribute corresponding to elements that have a `default`. Required elements such as `enabled()` do not have such a default value attribute. `javap` is not a substitute for the Java Reflection contract, but it is very useful for understanding the data that `getDefaultValue()` retrieves.

This storage location explains why:

- A class using an annotation can omit an element that has a `default`.
- When reading the annotation at runtime, Java supplies the default value for the omitted element.
- Reflection can inspect the default definition using `Method.getDefaultValue()` **without first retrieving an annotation from a specific class**.

In particular, there is no general official way using **only the annotation object read via Reflection** to tell whether the source author explicitly wrote a value **equal to the default** or omitted the element to rely on the default. For instance:

~~~java
@JobOptions(enabled = true)
class A {
}

@JobOptions(enabled = true, retries = 3)
class B {
}
~~~

At both usage sites, `retries()` returns `3`. Relying on the effective value and the default value is not enough to conclude whether the original source wrote `retries = 3`. If exact syntactic analysis of the source is required, you need a source-code analysis or annotation-processing tool capable of preserving explicit presence information, rather than guessing from runtime reflection.

## 7. When Should You Use `getDefaultValue()`?

This is a useful API when building **tools that work with annotation types**, rather than merely reading annotation instances in a program:

1. **Generating configuration documentation:** iterating over annotation elements and listing the name, type, and default value of each option.
2. **Validating library contracts:** detecting which elements are required and which have defaults in order to produce guidance messages.
3. **Building configuration UIs or metadata explorers:** displaying the defaults defined by an API without needing a class that already uses the annotation.
4. **Comparing definitions between two library versions:** identifying which elements changed their defaults, thereby assessing client behavior changes.
5. **Debugging frameworks:** determining whether an effective value comes from the annotation type's default or may have been specified directly (noting that you cannot always distinguish the origin using reflection alone).

Example of a tool that lists the names of required elements:

~~~java
for (Method element : JobOptions.class.getDeclaredMethods()) {
    if (element.getDefaultValue() == null) {
        System.out.println("Required: " + element.getName());
    }
}
~~~

This is a **fragment** using the `JobOptions` declaration from the program in Section 4. The output in that example is:

~~~text
Required: enabled
~~~

In an annotation interface, the explicitly declared methods are the annotation elements; each element must have a valid name and return type, and no parameters. Therefore, `getDeclaredMethods()` is suitable for iterating over the elements of a directly defined annotation type.

You should avoid writing scanning libraries that do not validate the input type. Given an arbitrary `Class<?> type`, you can check:

~~~java
if (!type.isAnnotation()) {
    throw new IllegalArgumentException("Not an annotation type");
}
~~~

Only then should you iterate over the element methods. `Method.getDefaultValue()` is also a valid API call on a regular `Method`, but in that case a `null` result does not mean "the regular method is a required annotation element".

## 8. Limitations and Potential Pitfalls

### 8.1. Returning `null` When There Is No Default

In the annotation type:

~~~java
@interface Connection {
    String url();
    int timeout() default 30;
}
~~~

`url()` is a required element; `timeout()` has a default of `30`. `getDefaultValue()` returns `null` for `url()`, and `Integer(30)` for `timeout()`. Java does not allow `default null`, so the `null` case is unambiguous and cannot be confused with a valid default.

### 8.2. `getDefaultValue()` Does Not Read Overridden Values

`@JobOptions(enabled = true, retries = 8)` does not change `JobOptions.class.getDeclaredMethod("retries").getDefaultValue()` from `3` to `8`. To read `8`, you must obtain the annotation instance at the annotated location and call `retries()`, or invoke the corresponding method on the instance as shown in Section 4.

### 8.3. Do Not Confuse Annotation `default` with Interface `default` Methods

An annotation element is defined as:

~~~java
@interface Settings {
    int retries() default 3;
}
~~~

Whereas a `default` method of a regular interface is:

~~~java
interface Retrier {
    default int retries() {
        return 3;
    }
}
~~~

The two constructs have different meanings. For `Retrier.class.getDeclaredMethod("retries")`, `getDefaultValue()` returns **`null`**, because `Retrier.retries()` is not an annotation type element. To check whether a method is a default method of an interface, Reflection provides **`Method.isDefault()`**, which is a completely different API.

### 8.4. Do Not Use `getMethods()` and Treat Every Method as an Annotation Element

`getMethods()` includes public methods inherited from related interfaces/classes according to reflection rules. For an annotation type, the straightforward way to iterate over the elements declared by the annotation type itself is to call `getDeclaredMethods()` and process only those methods. Methods such as `annotationType()`, `equals()`, `hashCode()`, and `toString()` belong to the `java.lang.annotation.Annotation` or `Object` contracts, and are **not** annotation elements declared by us.

### 8.5. Pay Attention to the `Object` Return Type and Casting

The code below does not compile because `Object` cannot be assigned directly to `int`:

~~~java
// Incorrect:
// int retries = JobOptions.class.getDeclaredMethod("retries").getDefaultValue();
~~~

The correct approach when the element type is known with certainty:

~~~java
Object raw = JobOptions.class
        .getDeclaredMethod("retries")
        .getDefaultValue();

int retries = (Integer) raw;
~~~

This is a fragment that must be placed in a context that handles or declares `NoSuchMethodException`. Casting to `(Integer)` is appropriate because the `retries()` element is declared to return `int`, and the reflected representation of an integer is `Integer`. For a general-purpose tool, you must inspect `Method.getReturnType()` and handle each type properly rather than converting every default to `String`.

### 8.6. A Default Can Fail When Decoding a Type That No Longer Exists

The Java SE 17 API of `Method.getDefaultValue()` can throw:

- `TypeNotPresentException` if a default value references a type that is unavailable.
- `EnumConstantNotPresentException` if an enum value declared in the default does not exist when read.
- `AnnotationFormatError` if the default metadata encounters an invalid format.

These situations often occur when classes are compiled against inconsistent library versions, or when components are missing from the classpath or module path. When writing tools that scan bytecode across multiple artifacts, you should not assume that every value in annotation metadata will always decode successfully.

### 8.7. Changing Default Values Between Versions Can Alter Behavior

Suppose version 1 declares:

~~~java
@interface RetryPolicy {
    int attempts() default 2;
}
~~~

and a compiled client uses `@RetryPolicy` without specifying `attempts`. If in version 2 the same annotation type changes the default to `4`, code reading metadata in the version 2 environment may receive `4` without modifying the client's source code. **A default value is an observable part of the contract**, not merely an example in documentation.

This is why changing a `default` should be treated as an API **behavioral/semantic** change, even when existing annotation usages still compile and link. You should re-run tests for tools and frameworks that consume that value.

## 9. Checklist for Writing an Annotation Default Reader

A practical workflow:

1. Obtain the annotation type itself, such as `JobOptions.class`, and verify `isAnnotation()` if the input is dynamic.
2. Call `getDeclaredMethods()` to iterate over the element methods declared in that annotation type.
3. If deterministic output is needed, sort by `Method.getName()`.
4. For each method, call `getDefaultValue()`; `null` means the element has no default.
5. Check `Method.getReturnType()` and format/present the value appropriately, especially for enums, `Class`, nested annotations, and arrays.
6. If you want the **effective value at a usage site**, retrieve the annotation instance via reflection under the appropriate retention policy, then call the element method on the instance.
7. Distinguish `null` caused by having no default from metadata decoding errors, missing classes, or an annotation not being retained until runtime.
8. Do not conclude with certainty whether an element was written explicitly or fell back to its default based solely on the effective value at runtime.

## 10. Self-Check Questions and Exercises

**Question 1.** For `String owner() default "platform";`, what does `Method.getDefaultValue()` return?

**Answer:** A `String` with the value `"platform"`.

**Question 2.** `boolean enabled();` has no `default`; why is `getDefaultValue()` `null`, yet `@JobOptions(enabled = true)` can still return `true` when calling `enabled()`?

**Answer:** The element has no default, so the usage site is required to provide a value. `getDefaultValue()` reads the definition; `enabled()` on the annotation instance reads the effective value.

**Question 3.** Change `@JobOptions(enabled = true, retries = 8)` to `@JobOptions(enabled = true, retries = 3)`. Can runtime reflection determine whether the source author explicitly passed `retries = 3`?

**Answer:** It cannot be concluded in general from only the effective value and the declared default, because the explicitly passed value equals the default value.

**Question 4.** Is `@Retention(RUNTIME)` required solely to call `JobOptions.class.getDeclaredMethod("owner").getDefaultValue()`?

**Answer:** No. The default value belongs to the annotation type definition. `RUNTIME` is needed when you want to use runtime reflection to read `@JobOptions` applied to a class such as `Worker`.

**Question 5.** Why should code printing a default `String[]` use `Arrays.toString` instead of `String.valueOf`?

**Answer:** Because arrays do not override `toString()` to print their list of elements. `Arrays.toString` represents array contents in a more readable form.

**Question 6.** Do `Method.isDefault()` and `Method.getDefaultValue()` have the same meaning?

**Answer:** No. `isDefault()` refers to a default method of a regular interface; `getDefaultValue()` returns the default value declared for an annotation element.

**Hands-on Exercise:** In `DefaultValueDemo.java`, add the element `long ttl() default 60L;` to `JobOptions` and run it again. Predict the position of the new line after sorting by name, the Java type of the `getDefaultValue()` result, and the effective value when `Worker` does not specify `ttl`. Then add `ttl = 120L` at the usage site to observe that the declared default **stays the same** while the effective value **changes**.

## 11. Official Documentation

- [Java SE 17 — `java.lang.reflect.Method.getDefaultValue()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#getDefaultValue()): signature, return value, and related exceptions.
- [Java SE 17 — `java.lang.reflect.Method.isDefault()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#isDefault()): distinguishing it from interface default methods.
- [JLS Java SE 17 §9.6.2 — Defaults for Annotation Interface Elements](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.2): rules for declaring default values.
- [Java SE 17 — `AnnotatedElement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html): API for reading annotations applied to program elements.

Remember the most important distinction: **`Method.getDefaultValue()` asks what default the annotation type specifies; `element.invoke(annotationInstance)` asks what value the annotation in use actually has**. The two reads may match or differ depending on whether the usage site overrides the default.
