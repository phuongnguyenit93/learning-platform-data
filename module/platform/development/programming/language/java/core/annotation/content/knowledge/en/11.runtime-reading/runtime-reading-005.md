# Reading Element Values via Annotation Type Methods in Java

## 1. Why Does an Annotation Have Methods?

When defining a custom annotation with `@interface`, the declarations inside it that look like parameterless methods are called **annotation elements**. Each element defines a **name** and a **metadata value type**:

```java
@interface OperationInfo {
    String value();
    int retries() default 0;
    String[] labels() default {};
    Class<?> handler() default Object.class;
}
```

Here, `value()`, `retries()`, `labels()`, and `handler()` are element methods. They have no programmer-written method body and accept no arguments. At the usage site, the code author supplies a value for each element:

```java
// Illustrates usage syntax; not a complete program yet.
@OperationInfo(
    value = "ISSUE_TICKET",
    retries = 2,
    labels = {"ticket", "critical"},
    handler = String.class
)
public void issueTicket() {}
```

This annotation describes metadata for **the `issueTicket` method**. The text `retries = 2` in the annotation is not a command to "automatically retry twice". To actually perform a retry, there must be a processor that reads the value and applies the rule.

**Lesson focus:** at runtime, after obtaining the annotation object via Reflection, we **call the parameterless element methods on the annotation object itself** to retrieve the metadata values:

```java
OperationInfo info = method.getAnnotation(OperationInfo.class);
if (info != null) {
    String action = info.value();
    int attempts = info.retries();
    String[] tags = info.labels();
    Class<?> type = info.handler();
}
```

This is a **statically typed** API: `info` has type `OperationInfo`, so the compiler knows the exact methods `value()`, `retries()`, `labels()`, and `handler()` along with their return types.

## 2. Three Steps to Read Element Values at Runtime

### Step 1: Define an Annotation with Appropriate Retention

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface OperationInfo {
    String value();
    int retries() default 0;
}
```

There are two important conditions:

- `@Retention(RetentionPolicy.RUNTIME)`: the metadata is retained so the standard Reflection API can retrieve it while the program is running.
- `@Target(ElementType.METHOD)`: the annotation type can be applied to **method declarations**. Therefore, when reading it, you must query the `Method` object describing that exact method, not the class's `Class` object.

If `@Retention` is omitted, the default policy for a custom annotation is `CLASS`. In that case, the annotation may be stored in the bytecode, but it is not visible through standard Reflection's `Method.getAnnotation(...)`.

### Step 2: Obtain the Annotation from the Right Annotated Element

```java
Method method = TicketService.class.getDeclaredMethod("issueTicket");
OperationInfo info = method.getAnnotation(OperationInfo.class);
```

`getDeclaredMethod("issueTicket")` looks up a directly declared method with a matching name and parameter type list in `TicketService`. In this example, the method takes no parameters, so no `Class<?>` parameter descriptors are needed.

`method.getAnnotation(OperationInfo.class)` accepts a `Class` object representing the annotation type. Thanks to generics in the Reflection API, the result has type `OperationInfo`, **not** `String`, `int`, or the value of an individual element. You must obtain **the annotation object first**, and only then call its elements.

**Check for `null` before reading.** `getAnnotation(...)` can return `null` if the method is not annotated with that annotation, or if the annotation is not available due to its retention policy. Calling `info.value()` when `info == null` will throw a `NullPointerException`.

### Step 3: Call Element Methods to Retrieve Metadata

```java
if (info != null) {
    System.out.println(info.value());
    System.out.println(info.retries());
}
```

The calls `info.value()` and `info.retries()` are **parameterless** calls on the annotation object. They return the metadata in the types declared in the `@interface`.

Do not write `info.value("ISSUE_TICKET")`: assigning a value happens at the **annotation usage site** using the syntax `value = ...`; element methods take no arguments when read.

## 3. Complete, Standalone Java 17+ Example

Create a file **`AnnotationElementValuesDemo.java`** containing all of the following code. The example does not require Spring or any external libraries.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface OperationInfo {
    String value();
    int retries() default 0;
    String[] labels() default {};
    Class<?> handler() default Object.class;
}

class TicketService {
    @OperationInfo(
        value = "ISSUE_TICKET",
        retries = 2,
        labels = {"ticket", "critical"},
        handler = String.class
    )
    public void issueTicket() {}

    // "value" is a special element name that can be written in shorthand form.
    @OperationInfo("LOOKUP")
    public void lookup() {}

    public void cancel() {}
}

public class AnnotationElementValuesDemo {
    private static void inspect(String methodName)
            throws NoSuchMethodException {

        Method method = TicketService.class
                .getDeclaredMethod(methodName);

        OperationInfo info = method.getAnnotation(OperationInfo.class);
        if (info == null) {
            System.out.println(methodName + ": (none)");
            return;
        }

        System.out.println(methodName
                + ": name=" + info.value()
                + ", retries=" + info.retries()
                + ", labels=" + String.join("|", info.labels())
                + ", handler=" + info.handler().getSimpleName());
    }

    public static void main(String[] args)
            throws NoSuchMethodException {

        inspect("issueTicket");
        inspect("lookup");
        inspect("cancel");

        Method retriesElement = OperationInfo.class
                .getDeclaredMethod("retries");
        System.out.println("Declared default retries: "
                + retriesElement.getDefaultValue());
    }
}
```

Compile and run from the directory containing the file using JDK 17 or later:

```bash
javac -encoding UTF-8 AnnotationElementValuesDemo.java
java AnnotationElementValuesDemo
```

**Exact stdout:**

```text
issueTicket: name=ISSUE_TICKET, retries=2, labels=ticket|critical, handler=String
lookup: name=LOOKUP, retries=0, labels=, handler=Object
cancel: (none)
Declared default retries: 0
```

### Output Analysis

**`issueTicket`:** the annotation supplies all four elements. `info.value()` returns `"ISSUE_TICKET"`; `info.retries()` returns `2`; `info.labels()` returns an array containing `"ticket"` and `"critical"` in the order written. `String.join("|", ...)` joins the array into `ticket|critical`. `info.handler()` returns the `Class<?>` object representing `String.class`, so `getSimpleName()` is `String`.

**`lookup`:** the syntax `@OperationInfo("LOOKUP")` is shorthand for `@OperationInfo(value = "LOOKUP")` when using the element named `value`. Unspecified elements take the defaults from the annotation type declaration: `retries() == 0`, `labels()` is an empty array, and `handler() == Object.class`. Because the array is empty, `String.join("|", ...)` returns an empty string after `labels=`.

**`cancel`:** the method is not annotated with `@OperationInfo`, so `getAnnotation` returns `null`; the program prints `cancel: (none)` and does not attempt to call elements on a nonexistent object.

**Final line:** `OperationInfo.class.getDeclaredMethod("retries")` retrieves the `Method` object describing the **declared element** itself in the annotation type. `getDefaultValue()` returns the default value object declared in the `@interface`, which here is `0`. This answers the question "what is the default in the element definition?", not "what element value does the `issueTicket` method have?".

In the example, `issueTicket()`, `lookup()`, and `cancel()` **are not invoked for execution**; the code only uses Reflection to read annotations. Therefore, no business side effects are automatically triggered by the attached annotations.

## 4. Distinguishing Two Kinds of Annotation-Related Method Calls

| Java Code | Target Object | Returns | Meaning |
| --- | --- | --- | --- |
| `method.getAnnotation(OperationInfo.class)` | `Method` describing the business method | `OperationInfo` or `null` | Finds the annotation attached to the method |
| `info.value()` | `OperationInfo` annotation object | `String` | Reads the `value` element value |
| `info.retries()` | `OperationInfo` annotation object | `int` | Reads the `retries` element value |
| `info.labels()` | `OperationInfo` annotation object | `String[]` | Reads the `labels` array value |
| `info.handler()` | `OperationInfo` annotation object | `Class<?>` | Reads the stored class type |
| `element.getDefaultValue()` | `Method` describing the element in the annotation type itself | `Object` or `null` | Reads the **declared default value**, not tied to a specific usage site |

The annotation object returned by Reflection is an object **implementing the corresponding annotation interface**, provided by the Java environment. Even though the `@interface` only contains bodyless element declarations, the program can still call those methods at runtime to retrieve the stored metadata. Developers do not need to write `new OperationInfo()` themselves, and in fact cannot instantiate an annotation in the usual way like a business class.

`OperationInfo.class` is the **annotation type**; `info` is **an annotation value read at the usage site**; `TicketService.class` is the class containing the business methods. These three objects serve different Reflection queries.

## 5. Required Values, Default Values, and the `value` Syntax

### Required Elements

```java
@interface Route {
    String path();
}
```

`path()` has no default value. The usage site must supply a value, for example `@Route(path = "/tickets")`. Applying `@Route` without supplying `path` is a compile-time error. When reading a valid annotation, `route.path()` returns the attached string.

### Elements with Defaults

```java
@interface RetryHint {
    int times() default 3;
}
```

If `@RetryHint` is used, calling `hint.times()` returns `3`. If `@RetryHint(times = 5)` is used, it returns `5`. The default value resides in the **annotation type definition**; when reading, the API already provides the actual value from the usage site or the corresponding default. There is no need to manually check "whether the element was written" in order to use its value.

**An important limitation:** after calling `hint.times()` and receiving `3`, this API does not directly indicate whether the author omitted the element to rely on the default or explicitly wrote `times = 3`. If distinguishing the **source syntax** between omission and explicit specification is required, an appropriate compile-time/source analysis approach is needed; you should not infer it from the runtime value.

### The Special `value` Element

```java
@interface Label {
    String value();
    int order() default 0;
}

// Both usages have the same meaning for the value element:
@Label("IMPORTANT")
class A {}

@Label(value = "IMPORTANT")
class B {}
```

The name `value` allows a simplified syntax when it is the element passed in shorthand form. If you want to assign multiple elements simultaneously, you must use explicit names following the proper syntax, such as `@Label(value = "IMPORTANT", order = 2)`.

Even though the usage site can write `@Label("IMPORTANT")`, when reading you still call **`label.value()`**, not `label.getValue()`. JavaBeans-style getter methods such as `getValue()` **are not automatically generated**.

## 6. Element Value Types and How to Handle Them When Reading

Annotation elements have the types permitted by Java: primitive types, `String`, `Class`, enums, another annotation, and **one-dimensional arrays** of those types. When reading them via element methods, Java returns the type matching the declaration:

| Element Declaration | Read Call | Typical Result |
| --- | --- | --- |
| `int retries();` | `info.retries()` | `int`, for example `2` |
| `String value();` | `info.value()` | `String`, for example `"ISSUE_TICKET"` |
| `Class<?> handler();` | `info.handler()` | `Class<?>`, for example `String.class` |
| `String[] labels();` | `info.labels()` | `String[]` |
| `Priority priority();`, where `Priority` is an enum | `info.priority()` | An enum constant such as `Priority.HIGH` |
| `Nested nested();`, where `Nested` is an annotation type | `info.nested()` | A `Nested` annotation object with its own elements |

An element value cannot be an arbitrary object/service, `List<String>`, `Map`, or `null`. This restricts metadata to the forms that Java can represent in annotations.

### Arrays: Reading and Handling Intentionally

Reading `info.labels()` returns a `String[]` array. You can:

- Iterate with a `for` loop or a stream if you need to process each label.
- Use `Arrays.toString(info.labels())` when you want to print it in the form `[ticket, critical]`.
- Use `String.join("|", info.labels())` if you want to join them into a single string as in the example.

For an array containing nested annotations, you must obtain each annotation object and then call the element methods of that nested annotation type. You cannot cast an annotation array to `String[]` if the element type is not `String`.

You should not modify a returned array and expect the underlying metadata to change. Annotation values are determined from metadata, not mutable configuration for the application to alter via getter calls.

### `Class<?>` Is Not an Instance of the Handler

When `info.handler()` returns `String.class`, that is **metadata representing the class type**, not an automatically created `String` object. If a framework wants to use that class to instantiate an object, it must have its own instantiation logic and conditions; the annotation does not do that automatically.

## 7. Reading Elements Using Dynamic Reflection

The previous examples knew the `OperationInfo` type ahead of time, so calling `info.value()` and `info.retries()` was simple and type-safe. If you are writing an annotation inspection tool that **does not know the element names at compile time**, you can inspect the methods of the annotation type itself:

```java
// Short illustration; assumes variable OperationInfo info != null already exists.
// This snippet uses java.lang.reflect.Method and requires handling Reflection exceptions.
Class<? extends java.lang.annotation.Annotation> annotationType =
        info.annotationType();

for (Method element : annotationType.getDeclaredMethods()) {
    String name = element.getName();
    Object actualValue = element.invoke(info);
    Object defaultValue = element.getDefaultValue();

    // A tool can store name, actualValue, defaultValue
    // or analyze based on the type of each element.
}
```

- `info.annotationType()` returns the `Class` object of the actual annotation type.
- `getDeclaredMethods()` returns the methods **declared in the annotation type**, which are the elements in this simple example. **Array ordering is not guaranteed**, so you need to sort by name if you want deterministic output.
- `element.invoke(info)` invokes the **element method** on the annotation object at runtime and returns `Object`. Primitive values such as `int` are boxed into `Integer`.
- `element.getDefaultValue()` reads the default value in the **annotation type declaration**, not the value at the usage site; for an element without `default`, the result is `null`.

Unlike calling a typed API such as `info.retries()`, calling `Method.invoke(...)` involves Reflection exceptions that must be handled, may require access control handling in general cases, and loses direct type safety since the result is returned as `Object`. **When the annotation type is known, prefer statically typed element methods**; use the dynamic mechanism only when genuinely building a general-purpose tool or framework.

### Do Not Confuse Elements with Methods of `java.lang.annotation.Annotation`

Every annotation object has several common APIs such as `annotationType()`, `equals(...)`, `hashCode()`, and `toString()`. These are not the custom elements `value()` and `retries()` belonging specifically to `OperationInfo`.

In particular, `info.toString()` can display the annotation as text, but you should not write a parser based on that string to extract metadata. Read each element directly or use appropriate Reflection instead.

## 8. Common Mistakes and How to Fix Them

**Mistake 1: Calling `method.value()` on the business `Method` object.** `Method` represents a method declaration and does not have `OperationInfo`'s `value()`. You must obtain `OperationInfo info = method.getAnnotation(OperationInfo.class)` first, and only then call `info.value()`.

**Mistake 2: Not checking for `null`.** Not every method is annotated; handle the case where metadata is absent before accessing elements.

**Mistake 3: Missing `@Retention(RUNTIME)`.** The annotation can still compile with the default `CLASS` retention, but standard Reflection will not see it on the target element.

**Mistake 4: Reading from the wrong location.** If an annotation is attached to a method, query it from `Method`; if attached to a class, query it from `Class`; if attached to a type use (`TYPE_USE`), APIs such as `getAnnotatedReturnType()` may be what is appropriate.

**Mistake 5: Assuming `default` means a getter with a method body.** `int retries() default 0;` is the default value of an annotation element, not a default method in a regular Java interface, and it executes no retry logic.

**Mistake 6: Thinking `getDefaultValue()` returns the value attached at the usage site.** It returns the declared default value, even when the usage site has overridden it with another value. To get the actual value, call `info.retries()`.

**Mistake 7: Calling `getValue()` instead of `value()`.** Elements do not follow JavaBeans getter naming conventions unless the designer explicitly names it that way (and uses a valid name). For `String value();`, the method to call is `value()`.

**Mistake 8: Treating an annotation as business logic.** `@OperationInfo(retries = 2)` is only metadata. To perform retries, there must be a consumer that uses `retries()` to orchestrate behavior and handle errors.

**Mistake 9: Relying on the order of `getDeclaredMethods()`.** The order of elements listed by Reflection is not guaranteed to match source order; tools requiring deterministic output must sort them.

**Mistake 10: Assuming every element value will always be read successfully in every environment.** In cases of binary incompatibility or when a referenced enum/class type is no longer valid, the runtime may throw errors such as `IncompleteAnnotationException`, `EnumConstantNotPresentException`, or `TypeNotPresentException`. In real-world systems where library versions change, you must manage compatibility and metadata-reading errors; the standalone example above does not encounter these situations.

## 9. Knowledge Check Exercises

**Exercise 1.** Given `@interface Rule { String code(); int priority() default 1; }` and `@Rule(code = "A")` on a method. After obtaining the `Rule rule` object via Reflection, what do you call to read the code and the priority level?

**Answer:** `rule.code()` gives `"A"` and `rule.priority()` gives `1`. Both are parameterless element methods.

**Exercise 2.** What is the difference between `method.getAnnotation(Rule.class)` and `rule.code()`?

**Answer:** The first call retrieves **the annotation object** attached to the method; the second call reads **a metadata element** from that object.

**Exercise 3.** In the runnable example, why does `lookup` have `retries=0` even though it is only annotated with `@OperationInfo("LOOKUP")`?

**Answer:** `retries()` has `default 0` in the annotation type declaration. When the usage site does not supply `retries`, calling the element method returns the default value.

**Exercise 4.** What does `OperationInfo.class.getDeclaredMethod("retries").getDefaultValue()` return if `issueTicket` has set `retries = 2`?

**Answer:** It still returns `0`, because that is the **default in the element declaration**. To read `2` for `issueTicket`, you must obtain the annotation from that method itself and call `info.retries()`.

**Exercise 5.** If a method is not annotated with `@OperationInfo`, what is the result of `method.getAnnotation(OperationInfo.class)`?

**Answer:** `null`; the program must check for it before calling `value()` or `labels()`.

**Exercise 6.** Does the value `handler = String.class` pre-create a `String` instance?

**Answer:** No. It represents the **class type** as metadata. `info.handler()` returns `Class<?>`, not a business object.

**Exercise 7.** If a tool needs to print the names of all annotation elements without knowing them before compile time, which API should it use?

**Answer:** `info.annotationType().getDeclaredMethods()` to list them, read `Method.getName()`, and you can use `Method.invoke(info)` to retrieve the value. Exceptions must be handled, and sorting is needed if a fixed order is required.

**Exercise 8.** Why is simply reading `info.toString()` and splitting the string not a recommended way to retrieve values?

**Answer:** That approach loses direct type information and can fail with arrays, nested annotations, special characters, and formatting differences; Java already provides strongly typed element methods.

## 10. Summary of the Thought Process

When you need to read an annotation at runtime, identify **what kind of element it is attached to**, verify `RUNTIME` retention, obtain the appropriate Reflection object (`Class`, `Method`, `Field`...), retrieve the annotation via `getAnnotation(...)` or `getDeclaredAnnotation(...)`, check for `null`, and then call **the element methods of the annotation type** such as `info.value()`, `info.retries()`, and `info.labels()`.

The result is a **metadata value** of the declared type, with defaults applied if the usage site did not assign them explicitly. If you want those values to produce logging, retries, mapping, or a business policy, you must write and invoke a separate **processor**; reading elements does not create behavior on its own.
