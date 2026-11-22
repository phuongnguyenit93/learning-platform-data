# Annotation Values in Java: Do Not Depend on Proxy Classes or JDK Internal Implementations

When using Reflection to read annotations at runtime, we receive a Java object on which elements such as `name()`, `value()`, or `timeout()` can be called. That object has the **public API type** of the annotation, whereas the **concrete class** that the JDK uses to implement it is an implementation detail. Reliable code must operate through **the annotation type, `java.lang.annotation.Annotation`, and `java.lang.reflect.AnnotatedElement`**, rather than relying on proxy class names, invocation handlers, private fields, or the internal structure of a specific JDK version.

This lesson explains how to read, compare, convert, and test **annotation values** according to the standard contract, especially distinguishing `annotation.annotationType()` from `annotation.getClass()`.

## 1. Practical scenario: reading an annotation on a class

Suppose we declare an annotation to describe a service configuration:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface ServiceInfo {
    String name();
    int timeoutMs() default 1000;
}

@ServiceInfo(name = "payment", timeoutMs = 2500)
class PaymentService {
}
```

When using Reflection:

```java
ServiceInfo info =
        PaymentService.class.getDeclaredAnnotation(ServiceInfo.class);
```

`info` carries **the contract of `ServiceInfo`**. We can call `info.name()` and `info.timeoutMs()`; there is no need to know which internal class the JDK used to create this object.

**Do not assume** that the returned object is always an instance of a class with a fixed name such as `$Proxy1`, a class located in some internal package, or a type created by the application itself. The official Java documentation clearly states that the annotation implementation class is **implementation-dependent**; using `getClass()` to determine the *annotation type* is therefore incorrect for that purpose.

This is a **compatibility** issue: a program should not stop working simply because the JDK, module, compiler, or the way Reflection implements annotations changes while still preserving the Java contract.

## 2. Distinguishing “annotation type” from “implementation class”

The following two statements **do not have the same meaning**:

```java
Class<? extends java.lang.annotation.Annotation> type =
        info.annotationType();

Class<?> implementation = info.getClass();
```

- `annotationType()` is a method of the public interface `java.lang.annotation.Annotation`. It returns **the exact annotation interface** declared in source code, for example `ServiceInfo.class`.
- `getClass()` is the `Object.getClass()` method that returns **the actual runtime class of the object**. For an annotation retrieved via Reflection, that class is chosen by the JDK, so it is not a stable way to determine the annotation type.
- The displayed name, package, fields, and implementation class structure are not considered part of the contract for using an annotation.

Stable check:

```java
if (info != null && info.annotationType() == ServiceInfo.class) {
    System.out.println(info.name());
}
```

Design-flawed check:

```java
// Wrong approach (illustrative, not recommended):
// if (info.getClass().getName().contains("$Proxy")) { ... }
// String realType = info.getClass().getName();
// Object handler = java.lang.reflect.Proxy.getInvocationHandler(info);
```

In a specific JDK release, code relying on `Proxy` might **accidentally** work; that does not make proxy details a mandatory API for all annotations. In addition, `Proxy.getInvocationHandler(...)` is only appropriate when the object is actually a dynamic proxy; using it as a condition to check whether an annotation is valid misses the point.

Simple rule: **to get the annotation type → `annotationType()`; to get the elements → call the methods of the annotation type; to find which annotations are attached to a declaration → use the `AnnotatedElement` API.**

## 3. Public APIs to use

| Purpose | Stable API |
| --- | --- |
| Retrieve an annotation directly on a class | `SomeClass.class.getDeclaredAnnotation(Config.class)` |
| Retrieve an annotation present under Reflection rules (inheritance may apply for classes) | `SomeClass.class.getAnnotation(Config.class)` |
| Read all directly declared annotations | `element.getDeclaredAnnotations()` |
| Find repeatable annotations, including through a container | `element.getDeclaredAnnotationsByType(Config.class)` or `getAnnotationsByType(...)` as needed |
| Determine the actual annotation type | `annotation.annotationType()` |
| Read each element | `config.name()`, `config.timeoutMs()`, `config.value()` |
| Compare two annotation values by content | `a.equals(b)` |
| Use an annotation as a key in a map/set | `equals()` combined with `hashCode()` per the standard contract |

`Class`, `Field`, `Method`, `Constructor`, and many other Reflection objects support the `AnnotatedElement` interface. Library users should accept a specific annotation type via a `Class<A>` argument and then call the standard API:

```java
static <A extends java.lang.annotation.Annotation> A read(
        java.lang.reflect.AnnotatedElement source, Class<A> annotationType) {
    return source.getDeclaredAnnotation(annotationType);
}
```

This is an **illustrative method snippet** that must be placed inside a class to compile; it returns `null` when the annotation is not directly declared. There is no access to proxies, internal modules, or private fields.

### `getAnnotation` and `getDeclaredAnnotation` are not completely identical

`getDeclaredAnnotation` only considers annotations **directly** on the declaration being read. `getAnnotation` may include inherited annotations at the class level if the annotation type is marked with `@Inherited` and the corresponding rules apply. Therefore, choose the API based on **the semantics you need**, not on the annotation's implementation class.

For `@Repeatable` annotations, the `getAnnotationsByType` and `getDeclaredAnnotationsByType` APIs support looking through the container. Annotation repeatability is a **language/API** feature, not the work of a custom proxy that application code needs to open up to read.

## 4. Complete Java 17+ example: using only the public contract

The following example shows two declarations containing annotations that are **equivalent in value**, even when one declaration uses default values and the other specifies values explicitly. The program relies solely on the `Annotation` contract and element methods.

Create the file **`AnnotationContractDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;
import java.util.Objects;

enum Mode {
    PROD, DEV
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface ServiceConfig {
    String name();
    int[] ports() default {8080, 8443};
    Mode mode() default Mode.PROD;
}

@ServiceConfig(name = "gateway")
class GatewayOne {
}

@ServiceConfig(name = "gateway", ports = {8080, 8443}, mode = Mode.PROD)
class GatewayTwo {
}

@ServiceConfig(name = "worker", ports = {9000}, mode = Mode.DEV)
class WorkerService {
}

public class AnnotationContractDemo {
    static ServiceConfig readConfig(Class<?> type) {
        return Objects.requireNonNull(
                type.getDeclaredAnnotation(ServiceConfig.class),
                () -> "Missing @ServiceConfig on " + type.getName()
        );
    }

    public static void main(String[] args) {
        ServiceConfig first = readConfig(GatewayOne.class);
        ServiceConfig second = readConfig(GatewayTwo.class);
        ServiceConfig other = readConfig(WorkerService.class);

        System.out.println("annotationType=" +
                first.annotationType().getSimpleName());
        System.out.println("name=" + first.name());
        System.out.println("ports=" + Arrays.toString(first.ports()));
        System.out.println("mode=" + first.mode());

        System.out.println("sameValues=" + first.equals(second));
        System.out.println("sameHash=" +
                (first.hashCode() == second.hashCode()));
        System.out.println("differentValues=" + !first.equals(other));
    }
}
```

Compile and run in the directory containing the file using JDK 17 or newer:

```bash
javac -encoding UTF-8 AnnotationContractDemo.java
java AnnotationContractDemo
```

**Stdout:**

```text
annotationType=ServiceConfig
name=gateway
ports=[8080, 8443]
mode=PROD
sameValues=true
sameHash=true
differentValues=true
```

Explanation:

1. `readConfig` retrieves the annotation using `Class.getDeclaredAnnotation(ServiceConfig.class)`, then reports a clear error if the declaration does not have the annotation. No cast from a proxy class is needed.
2. `first.annotationType().getSimpleName()` returns `"ServiceConfig"`, the name of the actual annotation type. It **does not** depend on the runtime implementation class name.
3. `first.name()` returns `"gateway"`. `first.ports()` is an `int[]` array, so the program uses `Arrays.toString(...)` to print its contents instead of printing the array identity.
4. `GatewayOne` uses the default values of `ports` and `mode`; `GatewayTwo` writes those exact values explicitly. According to the `Annotation.equals` contract, two annotations having the same type and the same values for every element are **equivalent**.
5. If two annotations are equivalent, their `hashCode()` values must be equal according to the contract. Therefore `sameHash=true`, even though the program does not know the concrete implementation class.
6. `WorkerService` has different elements, so `!first.equals(other)` is `true`.

The example **does not print `first.getClass().getName()`**, does not use `Proxy`, and does not assume that `first` and `second` share the same reference (`==`). The result depends only on the public API and declared values.

## 5. Comparing annotations must be based on value, not identity

An annotation is **value-based metadata**, not a domain object model managed by the application through reference identity. Calling Reflection multiple times may return objects with the same or different identities depending on the implementation mechanism; the application should not use that as a contract.

Correct way to compare:

```java
boolean same = first.equals(second);
```

Do not use:

```java
// Does not represent content equivalence:
// boolean same = first == second;
```

According to the Javadoc of `java.lang.annotation.Annotation`, two annotations are equivalent when:

- They have the same **annotation type**.
- Every corresponding element has an **equivalent value**.
- For primitive-type elements, comparison rules follow the corresponding type (in particular, `float` and `double` follow `Float.equals`/`Double.equals`, not simply the `==` operator).
- For `String`, `Class`, enum, or nested annotations, comparison uses `equals`.
- For array elements, **array contents** are compared using the corresponding `Arrays.equals` comparison, rather than comparing two array references.

Specifically, in the example, `ports` has type `int[]`. Two arrays `new int[]{8080, 8443}` and `new int[]{8080, 8443}` are normally two distinct objects, yet `Arrays.equals` yields `true`. Thus `@ServiceConfig(ports = {8080, 8443})` and the default value `{8080, 8443}` are equivalent at the element level.

### Hash code and use in collections

The `Annotation.hashCode()` contract is specified by the Javadoc per element. For each element pair with name `name` and value `value`, the contribution has the form:

```text
(127 * name.hashCode()) XOR valueHashCode
```

The hash code of the entire annotation is the sum of those contributions; array values use the corresponding `Arrays.hashCode`, while nested annotations use their own hash code. **There is no need to compute this formula manually** in the application: simply call `annotation.hashCode()`.

If using an annotation as a `HashMap` key or a `HashSet` element, rely on `equals`/`hashCode` just as with value objects. However, in long-lived business configuration code, it is usually better to **convert the elements into an explicit domain data type** rather than letting annotation objects become a dependency spread across application layers.

## 6. `toString()` is for observation only, not a stable data format

Example:

```java
String debug = first.toString();
```

The Javadoc allows generating a string representation of the annotation, typically close to the annotation syntax in source code. **The details of the string representation are implementation-dependent**. Factors such as fully qualified names, element ordering, parentheses, spaces, or how arrays are printed should not become a storage or inter-system communication contract.

Operations to avoid:

```java
// Anti-pattern example:
// String saved = first.toString();
// String name = saved.substring(saved.indexOf("name=") + 5);
// boolean gateway = first.toString().contains("gateway");
```

These approaches easily break when the `toString()` format changes or when string values contain commas, parentheses, quotes, and escapes.

If you need JSON, YAML, structured logs, or durable comparisons, retrieve the **elements** using public methods and convert them to appropriate data types:

```java
String name = first.name();
int[] ports = first.ports();
Mode mode = first.mode();
```

Then the system's serializer defines the fields and format itself. Do not use the annotation object's `toString()` as a serialization protocol.

## 7. Do not open proxy classes and internal packages to get the “real value”

Some implementations may provide runtime annotations through a dynamic proxy mechanism. However, the fact that one JDK implementation uses a proxy **does not guarantee** that:

- Every annotation in every JDK is a dynamic proxy of the same shape.
- The class name has a `$ProxyN` suffix or a fixed package.
- The invocation handler has a field with a specific name and type.
- An internal map holding values can be read using `setAccessible(true)` without module restrictions.
- A call to `getAnnotation` returns the exact same object by reference on every run.

In particular, packages such as `sun.reflect.annotation` are **internal APIs**, not a Java SE contract for applications. JPMS/module access may block reflection into unopened JDK members, and even if access succeeds, the code will depend on an internal layout that is not guaranteed to be stable.

The snippet below is an **anti-pattern to recognize, not code to run**:

```java
// Do not write business logic that depends on the following operations:
// String implementationName = config.getClass().getName();
// java.lang.reflect.InvocationHandler h =
//         java.lang.reflect.Proxy.getInvocationHandler(config);
// h.getClass().getDeclaredField("memberValues").setAccessible(true);
```

Instead:

```java
String name = config.name();
int[] ports = config.ports();
Class<? extends java.lang.annotation.Annotation> type =
        config.annotationType();
```

If you need to write a shared library for **multiple annotation types**, you can read the element methods from the annotation type itself using standard Reflection APIs such as `annotation.annotationType().getDeclaredMethods()`. However, that generic solution should be used **only when needed**; for a known annotation type, calling `config.name()` is more concise, statically type-checked, and easier to maintain.

Do not confuse `getDeclaredMethods()` of the **annotation type** with `getDeclaredMethods()` of the **implementation class**. Only the former describes the public elements belonging to the annotation contract.

## 8. When you need to iterate over elements generically

A framework might receive an arbitrary `Annotation` and want to list **element names/values** without knowing the type at compile time. This can be done through the annotation interface:

```java
import java.lang.annotation.Annotation;
import java.lang.reflect.Method;
import java.lang.reflect.InvocationTargetException;

public final class AnnotationReader {
    private AnnotationReader() {
    }

    public static void printElements(Annotation annotation) {
        Class<? extends Annotation> type = annotation.annotationType();

        for (Method element : type.getDeclaredMethods()) {
            try {
                Object value = element.invoke(annotation);
                System.out.println(element.getName() + "=" + value);
            } catch (IllegalAccessException | InvocationTargetException ex) {
                throw new IllegalStateException(
                        "Cannot read @" + type.getName(), ex
                );
            }
        }
    }
}
```

This is **a standalone illustrative helper class**, not a runnable `main` program, and it has an important limitation: for array-typed elements, `System.out.println(value)` does not provide readable array contents; `Arrays.toString` or `Arrays.deepToString` must be used according to the exact type. The return order of `getDeclaredMethods()` is also **not guaranteed**, so you must not rely on print order to create a storage protocol or test results.

The `AnnotationReader` example only queries the **annotation interface** and invokes **publicly declared element methods**, without inspecting private fields of the implementation. That is the difference between contract-compliant public Reflection and reflecting into internal JDK structures.

If the library needs deterministically ordered data, sort the `Method` objects by `getName()` before processing. If conversion to a DTO is needed, handle the valid annotation values yourself: primitives/wrappers, `String`, `Class`, enums, nested annotations, and one-dimensional arrays of these types.

When an attribute has type `Class<?>`, reading the annotation may trigger type resolution. If the referenced class does not exist at runtime or the metadata is no longer compatible, reading the element may raise specific exceptions; reading an annotation is not always an operation that cannot fail.

## 9. Annotation arrays and immutable values

An annotation element can return `String[]`, `int[]`, `Class<?>[]`, an enum array, or a nested annotation array. Arrays are objects **whose elements can be modified** in Java, so applications must be careful when passing them outward:

```java
int[] snapshot = first.ports().clone();
snapshot[0] = 9001; // Only mutates the copy created by the application.
System.out.println(Arrays.toString(snapshot));
```

The code above uses `Arrays` from the complete example in section 4 and illustrates how to create **a separate copy for editing**, without implying that the annotation itself is a place to store mutable state. Modifying elements in `snapshot` does not change the values declared on `@ServiceConfig`.

Do not write annotation identification logic using the array's address:

```java
// Incorrect for comparing contents:
// boolean samePorts = first.ports() == second.ports();
```

To check the contents of two arrays, use:

```java
boolean samePorts =
        java.util.Arrays.equals(first.ports(), second.ports());
```

If you want to compare the **entire** annotation, there is no need to compare each element manually: `first.equals(second)` already has a clear contract, including array handling. When mapping to a domain object, protect mutable arrays with appropriate copies.

## 10. When an annotation does not exist or lacks appropriate retention

The `getAnnotation` or `getDeclaredAnnotation` API can return `null`. Common cases:

- The declaration does not have that annotation attached.
- The annotation has `@Retention(SOURCE)`, so it no longer exists after compilation.
- The annotation has `@Retention(CLASS)` (the default if `@Retention` is omitted), so it cannot be retrieved via standard runtime Reflection.
- Searching directly on a subclass with `getDeclaredAnnotation` while the annotation is only on the superclass.
- Using `getAnnotation` to look up a repeatable annotation when multiple annotations are actually held inside a **container**; in this case `getAnnotationsByType` is more appropriate.

For application code that requires runtime Reflection, the annotation declaration needs `@Retention(RetentionPolicy.RUNTIME)`.

A safe way to use it when the annotation is optional:

```java
ServiceConfig config =
        SomeClass.class.getDeclaredAnnotation(ServiceConfig.class);

if (config == null) {
    // No metadata on the exact declaration queried.
} else {
    String name = config.name();
}
```

This is an **illustrative** snippet; you must replace `SomeClass` with a real type and place it inside a method. Do not treat `null` as proof that “the JDK renamed the proxy”: it is an issue of metadata presence, retention, target, or query API selection.

### Incompatible metadata

In systems with modules, classloaders, or independently upgraded libraries, an annotation type may change while previously compiled class files remain. These situations can lead to errors when accessing values:

- `IncompleteAnnotationException`: the annotation is missing a required element compared to the currently loaded definition.
- `AnnotationTypeMismatchException`: the value in the metadata is no longer compatible with the current annotation element type.
- `EnumConstantNotPresentException`: the enum constant referenced in the annotation no longer exists.
- `TypeNotPresentException`: the `Class` type referenced in the annotation is no longer available to resolve.

The usual solution is to check and align dependency versions, then recompile the affected code; **do not** access the private map of the annotation implementation to “fix” broken metadata. When handling reflection at plugin or application boundaries, catch and report compatibility errors properly rather than swallowing all exceptions and assuming the metadata is empty.

## 11. Depending on the right API layer in architectural design

A well-designed system using annotations typically has three layers of responsibility:

```text
Java declaration
    ↓  Reflection API: AnnotatedElement.get...Annotation(...)
Annotation interface + element values
    ↓  Convert to dedicated DTO/domain model
Validated configuration: name, ports, mode
    ↓
Business logic: initialization, validation, routing, etc.
```

For example, instead of passing `ServiceConfig` directly deep into the processing layer, you can create a configuration record:

```java
record ServiceSettings(String name, int[] ports, Mode mode) {
    ServiceSettings {
        ports = ports.clone();
    }

    @Override
    public int[] ports() {
        return ports.clone();
    }
}
```

This is an **illustrative Java 17 record example**, which can be used in the same package as `Mode` from the main example. The record creates defensive copies of the array to prevent external code from silently mutating array elements in the configuration.

You can map data from the annotation:

```java
ServiceSettings settings = new ServiceSettings(
        config.name(),
        config.ports(),
        config.mode()
);
```

Here `config` is a `ServiceConfig` variable that has already been read; it is not a standalone program with `main`.

Once converted to `ServiceSettings`, business layers do not need to know how the `ServiceConfig` object was constructed by the JDK. This separation makes unit testing simpler and reduces coupling to Reflection.

## 12. Testing behavior instead of implementation

You should test against what the public API **promises**:

- `annotation.annotationType() == ServiceConfig.class`.
- `annotation.name().equals("gateway")`.
- `Arrays.equals(annotation.ports(), new int[]{8080, 8443})`.
- `annotation.mode() == Mode.PROD`.
- Two annotations of the same type with the same element values return `true` from `equals()`; their hash codes are equivalent as well.
- When the annotation is missing, `getDeclaredAnnotation` returns `null` and the application handles it properly.
- When repeatable annotation support is needed, `getDeclaredAnnotationsByType()` returns the set of values according to API rules.

You should not write tests asserting:

```java
// Avoid:
// assertTrue(annotation.getClass().getName().startsWith("com.sun.proxy"));
// assertEquals("...", annotation.toString());
// assertSame(annotation1, annotation2);
```

These tests bind to implementation class details, unstable string formatting, or object identity. A project may pass on one JDK version and fail on another even though the annotation data and public contract have not changed.

You should run tests at least on the JDK versions that the application officially supports; when failures occur, prioritize checking `@Retention`, imports, classpath/module path, metadata presence, and element types/values.

## 13. Common pitfalls

| Practice | Problem | Alternative |
| --- | --- | --- |
| `annotation.getClass() == ServiceConfig.class` | Compares the implementation class with the annotation interface; violates the contract. | `annotation.annotationType() == ServiceConfig.class`. |
| Checking for a class name containing `$Proxy` | The name is implementation-dependent. | Use `annotationType()` or `instanceof` with the target annotation interface. |
| Using `Proxy.getInvocationHandler()` to look up values | Depends on proxy mechanisms and internal handlers. | Call `annotation.name()` / `annotation.value()`. |
| Accessing `sun.reflect.annotation.*` | Internal API with no stability guarantee. | Use the public `java.lang.annotation` and `java.lang.reflect` APIs. |
| Finding a field named `memberValues` and calling `setAccessible(true)` | Private layout can change and JPMS may block access. | Use the element methods of the annotation interface. |
| `a == b` to compare two annotations | Checks object reference equality, not annotation value. | `a.equals(b)`. |
| `a.ports() == b.ports()` | Arrays use reference equality. | `Arrays.equals(...)` or compare with `a.equals(b)`. |
| Parsing `annotation.toString()` | The string has no guaranteed format. | Read each element and serialize into your own format. |
| Guessing a proxy bug when `getAnnotation` returns `null` | May be due to a missing annotation or non-`RUNTIME` retention. | Check declaration, retention, target, query API, and classpath. |
| Using `getAnnotations()` to find all repeatable annotations | May only see the container. | `getAnnotationsByType(...)` or the corresponding `Declared` variant. |
| Reflecting on the implementation class to list elements | Mixes implementation methods with the annotation contract. | `annotation.annotationType().getDeclaredMethods()`. |

## 14. Self-check

1. Are `cfg.getClass()` and `cfg.annotationType()` guaranteed to be equal? **No**: one is the runtime implementation class, and the other is the annotation interface. Use `annotationType()` when you need to determine the annotation type.
2. If two different classes both have `@ServiceConfig` with the same values for every element, can the returned annotations be equal via `equals()`? **Yes**: `equals` compares the annotation contents, not the class carrying the annotation.
3. Why should `cfg.toString()` not be used to store configuration? **Because the string representation is an implementation detail**, not a stable serialization format.
4. What should be used to compare the `int[]` array returned by `cfg.ports()` with another array? **`Arrays.equals`**, or use `cfg.equals(otherCfg)` if comparing the entire annotation.
5. Which class should you reflect on to list annotation element names generically? **`cfg.annotationType().getDeclaredMethods()`**, not the class returned by `cfg.getClass()`.
6. What should you do first if `getDeclaredAnnotation` returns `null`? **Check whether the annotation is actually attached directly at the queried site and has `@Retention(RUNTIME)`**, instead of accessing internals.
7. Should you write a Java library that uses `Proxy.getInvocationHandler(cfg)` as the standard way to read annotations? **You should not**; use the elements and public APIs.
8. Why does converting annotations to a DTO make a system resilient? **Business logic depends on explicitly typed data rather than Reflection objects or implementation-specific classes**.

Standard references: [Java SE 17 – `java.lang.annotation.Annotation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Annotation.html) (especially the notes on `annotationType()`, `equals`, `hashCode`, and `toString`); [Java SE 17 – `java.lang.reflect.AnnotatedElement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html). These public contracts are the foundation for designing code that does not depend on proxies or internal JDK details.
