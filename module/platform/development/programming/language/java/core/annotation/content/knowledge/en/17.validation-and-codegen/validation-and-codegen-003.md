# Attaching Diagnostics to a Specific Declaration, Annotation, or Element in Java Annotation Processing

## 1. Goal: Reporting the Right Error in the Right Place in Source Code

When writing an **annotation processor** in Java, detecting an invalid configuration is only half the job. The other half is reporting the error so the developer knows **which declaration**, **which annotation**, and, if possible, **which element value** needs to be fixed.

For example:

```java
@Endpoint(path = "", retries = -1)
class OrderService {}
```

A generic message like `Invalid annotation` does not make it clear whether the user needs to fix `path` or `retries`. Java SE provides **`javax.annotation.processing.Messager`** with multiple overloads of `printMessage` to attach diagnostics to different location levels:

- **`Element`**: a declaration in the language model, such as a class, method, field, or parameter.
- **`AnnotationMirror`**: a specific annotation usage on that declaration.
- **`AnnotationValue`**: the value of an element in that annotation usage, such as the `""` string of `path`.

If the compiler/IDE supports source location mapping, passing the appropriate object to `Messager` can make the error message appear right next to the problematic declaration, annotation name, or value expression, rather than becoming a general message that is hard to locate.

This is a **compile-time diagnostic**, not an exception thrown at application runtime. This API resides in the standard `java.compiler` module in Java SE 17+, without needing Spring, Lombok, or external annotation libraries.

## 2. Three Objects for Locating Diagnostics

### 2.1. Element — The Declaration to Point To

In `javax.lang.model.element`, `Element` describes a program element at the compile-time model level. Common kinds include:

| Source element | Typical model type | Example |
| --- | --- | --- |
| Class/interface | `TypeElement` | `class OrderService {}` |
| Method or constructor | `ExecutableElement` | `void save() {}` |
| Field or parameter | `VariableElement` | `int timeout;`, parameter `int count` |
| Package | `PackageElement` | `package com.example;` |
| Module | `ModuleElement` | `module my.module {}` |

From an annotation processor, you can retrieve annotated elements with:

```java
Set<? extends Element> elements =
        roundEnv.getElementsAnnotatedWith(Endpoint.class);
```

This illustrative snippet is **inside `process`**, with `roundEnv` and `Endpoint` already defined. `Element` is **not** `java.lang.reflect.Element`, nor is it an instance object of class `OrderService` at application runtime. It is the program model provided by the compiler.

### 2.2. AnnotationMirror — The Annotation Usage

An `Element` can carry multiple annotations:

```java
@Deprecated
@Endpoint(path = "/orders", retries = 2)
class OrderService {}
```

If you only pass `Element`, the message location may be attached to the entire `OrderService` declaration. To target the **`@Endpoint(...)` usage**, retrieve the matching `AnnotationMirror` from `element.getAnnotationMirrors()` and pass it together with `Element`.

`AnnotationMirror` represents an annotation usage according to compiler semantics, consisting of the **annotation type** and element/value pairs. It is not the `Endpoint` object obtained via runtime reflection. A class can carry multiple annotations of different types; therefore, you must **select the right mirror by annotation type**, rather than always using the first mirror in the list.

### 2.3. AnnotationValue — The Annotation Element Value

In the declaration:

```java
@Endpoint(path = "/orders", retries = -1)
class OrderService {}
```

`path` and `retries` are **annotation elements**. The value `-1` of `retries` is represented by an `AnnotationValue`. When you have the corresponding `Element`, `AnnotationMirror`, and `AnnotationValue`, you can ask the compiler to position the diagnostic near that value.

Be careful to distinguish three terms that are often all translated into Vietnamese as “phần tử” (“element”):

- **Program element (`Element`)**: the class declaration `OrderService`.
- **Annotation element (`ExecutableElement`)**: the `retries()` accessor defined in `@interface Endpoint`.
- **Annotation value (`AnnotationValue`)**: the `-1` value supplied to `retries` in a specific usage.

Both `ExecutableElement` and `AnnotationValue` play a role when iterating over `AnnotationMirror.getElementValues()`: the key is the **annotation element**, while the value is the **value**.

## 3. Four Overloads of Messager.printMessage

`javax.annotation.processing.Messager` defines four main overloads:

```java
void printMessage(Diagnostic.Kind kind, CharSequence msg);

void printMessage(Diagnostic.Kind kind, CharSequence msg,
                  Element e);

void printMessage(Diagnostic.Kind kind, CharSequence msg,
                  Element e, AnnotationMirror a);

void printMessage(Diagnostic.Kind kind, CharSequence msg,
                  Element e, AnnotationMirror a, AnnotationValue v);
```

These are **illustrative API signatures**, not a code snippet defining a new interface. The differences:

| Overload | Diagnostic location provided | When to use |
| --- | --- | --- |
| `(kind, msg)` | No source element specified | Global processor errors/messages |
| `(kind, msg, e)` | An **`Element` declaration** | The entire class/method/field is invalid, or the error cannot be attached to a specific annotation |
| `(kind, msg, e, a)` | An **`AnnotationMirror` annotation** on the declaration | The annotation is invalid as a whole; a specific value cannot be identified |
| `(kind, msg, e, a, v)` | An annotation's **`AnnotationValue` value** | An explicit argument of the annotation has an invalid value |

**Important:** The three location parameters must be objects *with a real relationship*: `a` is an annotation on `e`, and `v` is a value inside `a`. You should not take a mirror from class A and attach it to the Element of class B.

`Messager` and the enum type `Diagnostic.Kind` come from two packages:

```java
import javax.annotation.processing.Messager;
import javax.tools.Diagnostic;
```

Normally, you do not need to create `new Messager()` yourself. Inside `AbstractProcessor`, use:

```java
Messager messager = processingEnv.getMessager();
```

The exact output (file name, line, column, highlight level) is determined by the compiler/IDE. The API **provides location context**, without guaranteeing that every tool will highlight a single exact token or print the message in the same format.

## 4. Diagnostic.Kind: Severity Levels and Meanings

Some values of `javax.tools.Diagnostic.Kind`:

| Kind | Typical meaning |
| --- | --- |
| `ERROR` | Reports an error that prevents the compilation from being considered successful |
| `WARNING` | A standard warning; does not fail the build by default |
| `MANDATORY_WARNING` | A mandatory warning displayed by the tool according to its rules |
| `NOTE` | Additional information, often useful when checking the processor |
| `OTHER` | A diagnostic not belonging to the categories above |

An annotation processor can choose:

```java
processingEnv.getMessager().printMessage(
        Diagnostic.Kind.ERROR,
        "retries phải lớn hơn hoặc bằng 0",
        element, mirror, retriesValue);
```

This is an illustrative snippet assuming `element`, `mirror`, and `retriesValue` have already been validly obtained in the processor. The result is a **compiler diagnostic**, not `throw new IllegalArgumentException(...)`.

For genuinely unacceptable configurations, use `ERROR` to prevent the project from building successfully. For informational guidance or non-mandatory policies, consider `WARNING` or `NOTE`. The `-Werror` option in `javac` can turn warnings into build errors; therefore, you must not assume that every warning is always harmless in every pipeline.

## 5. Retrieving the Right AnnotationMirror and AnnotationValue

### 5.1. Select the Mirror by Type, Not by Array Index

An element can have multiple annotations attached. Rely on `AnnotationMirror.getAnnotationType()` and `Types.isSameType` to select the right one:

```java
TypeElement endpointType =
        processingEnv.getElementUtils().getTypeElement("Endpoint");

for (AnnotationMirror mirror : element.getAnnotationMirrors()) {
    if (processingEnv.getTypeUtils().isSameType(
            mirror.getAnnotationType(), endpointType.asType())) {
        // This is the @Endpoint usage to check.
    }
}
```

This code resides inside `process` with an appropriate `element` and `processingEnv`. In a project with packages, use the **fully qualified name** of the annotation, such as `com.example.annotations.Endpoint`; the short name `Endpoint` is only used in examples without a package.

You should not compare `mirror.toString()` strings or take the first element of `getAnnotationMirrors()` to locate an annotation: the display string and order of appearance are not safe type-selection mechanisms.

### 5.2. getElementValues() vs. getElementValuesWithDefaults()

An annotation can have elements with defaults:

```java
@interface Endpoint {
    String path() default "/default";
    int retries() default 0;
}
```

When `@Endpoint` is used, both effective values still exist semantically, even though they **do not appear explicitly in the source**. Two APIs must be distinguished:

- `AnnotationMirror.getElementValues()`: returns a map of elements whose values are **explicitly supplied** in the annotation usage. Elements omitted to use their defaults are not included in this map.
- `Elements.getElementValuesWithDefaults(mirror)`: returns a map of elements and their effective values **including defaults**, which is useful when validation must inspect all elements.

For example:

```java
@Endpoint(path = "/users")
class UserService {}
```

With the annotation above, `getElementValues()` contains `path`, but does not contain `retries`; whereas `getElementValuesWithDefaults()` can return both `path = "/users"` and `retries = 0`.

**Why does this matter when locating errors?** If a value is a **default** and the user did not write it on `@Endpoint`, there is no corresponding value expression in the declaration under inspection for the compiler to point to. You should attach the diagnostic to the **annotation `(e,a)`** or to the **declaration `(e)`**, rather than assuming the `(e,a,v)` overload always has an exact source token to highlight.

### 5.3. Accessing Element Names and Typed Values

`getElementValuesWithDefaults()` returns a map type:

```java
Map<? extends ExecutableElement, ? extends AnnotationValue> values =
        processingEnv.getElementUtils()
                .getElementValuesWithDefaults(mirror);
```

Each entry contains:

- An `ExecutableElement` key, such as the `path()` or `retries()` element. Retrieve the name using `entry.getKey().getSimpleName().toString()`.
- An `AnnotationValue` value, whose `getValue()` returns an object based on the element kind: `String` for `String`, `Integer` for `int`, and specialized model types when the value is an enum, class literal, or nested annotation.

For code that only checks `String` and `int`, you can cast appropriately based on the annotation definition. Do not assume every `AnnotationValue.getValue()` is a `String`. For annotation arrays, the returned value is not a runtime Java array of the annotation; for an annotation processor, the model API has its own representations (such as a list of `AnnotationValue`).

## 6. Complete Java 17+ Example: Attaching Diagnostics at All 3 Levels

The example consists of **four Java files** in the same empty directory. The processor uses `Messager.printMessage` at three levels:

1. **`Element`**: warns the `LegacyService` class about naming conventions.
2. **`Element + AnnotationMirror`**: reports an error when `@Endpoint` is placed on an interface (even though `@Target(TYPE)` allows it syntactically).
3. **`Element + AnnotationMirror + AnnotationValue`**: reports an error directly on an empty `path` value or a negative `retries` value supplied by the developer.

The **default value** case will be handled with a reasonable fallback location, without assuming there is always an argument in the source.

### 6.1. Endpoint.java File

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
@interface Endpoint {
    String path() default "/default";
    int retries() default 0;
}
```

`@Target(TYPE)` allows placing `@Endpoint` on classes and interfaces, letting the processor enforce an **additional business rule**: in this example, only classes are allowed. `@Retention(SOURCE)` is sufficient for the processor because validation occurs at compile time; the runtime program does not need reflection to read `@Endpoint`.

### 6.2. EndpointProcessor.java File

```java
import java.util.Map;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.AnnotationMirror;
import javax.lang.model.element.AnnotationValue;
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.ExecutableElement;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;

@SupportedAnnotationTypes("Endpoint")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class EndpointProcessor extends AbstractProcessor {

    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment roundEnv) {
        if (roundEnv.processingOver()) {
            return true;
        }

        TypeElement endpointType = processingEnv
                .getElementUtils().getTypeElement("Endpoint");
        if (endpointType == null) {
            return false;
        }

        for (Element element :
                roundEnv.getElementsAnnotatedWith(endpointType)) {
            for (AnnotationMirror mirror : element.getAnnotationMirrors()) {
                boolean matches = processingEnv.getTypeUtils()
                        .isSameType(mirror.getAnnotationType(),
                                    endpointType.asType());
                if (!matches) {
                    continue;
                }

                if (element.getSimpleName()
                        .contentEquals("LegacyService")) {
                    processingEnv.getMessager().printMessage(
                            Diagnostic.Kind.WARNING,
                            "Nên đổi tên LegacyService",
                            element);
                }

                if (element.getKind() != ElementKind.CLASS) {
                    processingEnv.getMessager().printMessage(
                            Diagnostic.Kind.ERROR,
                            "@Endpoint chỉ hỗ trợ class theo quy tắc dự án",
                            element, mirror);
                    continue;
                }

                Map<? extends ExecutableElement,
                    ? extends AnnotationValue> effectiveValues =
                        processingEnv.getElementUtils()
                                .getElementValuesWithDefaults(mirror);

                for (Map.Entry<? extends ExecutableElement,
                               ? extends AnnotationValue> entry
                        : effectiveValues.entrySet()) {
                    String name = entry.getKey()
                            .getSimpleName().toString();
                    Object raw = entry.getValue().getValue();

                    if (name.equals("path")
                            && ((String) raw).isBlank()) {
                        reportValueError(element, mirror,
                                entry.getKey(), entry.getValue(),
                                "path không được rỗng");
                    }

                    if (name.equals("retries")
                            && ((Integer) raw) < 0) {
                        reportValueError(element, mirror,
                                entry.getKey(), entry.getValue(),
                                "retries phải >= 0");
                    }
                }
            }
        }
        return true;
    }

    private void reportValueError(
            Element element, AnnotationMirror mirror,
            ExecutableElement key, AnnotationValue value,
            String message) {

        if (mirror.getElementValues().containsKey(key)) {
            // Value is explicitly written in @Endpoint(...).
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR, message,
                    element, mirror, value);
        } else {
            // No source expression exists for the default value.
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR,
                    message + " (từ giá trị mặc định)",
                    element, mirror);
        }
    }
}
```

**Explanation:**

- `@SupportedAnnotationTypes("Endpoint")` declares the annotation type handled by the processor; because the example is in the **default package**, the name `Endpoint` works. In a real project with packages, declare the fully qualified name.
- `@SupportedSourceVersion(RELEASE_17)` indicates that the processor supports Java 17 source.
- `processingOver()` prevents the processor from trying to process new elements in the final round.
- `getElementsAnnotatedWith(endpointType)` retrieves the elements annotated with `@Endpoint` in the current round.
- `getAnnotationMirrors()` + `isSameType` selects the right `@Endpoint` instance when an element has multiple annotations.
- `getElementValuesWithDefaults()` ensures that validation rules also inspect **default values**.
- `mirror.getElementValues().containsKey(key)` determines whether **there is an explicit expression** to target with `AnnotationValue`.
- `printMessage(ERROR, ..., element, mirror, value)` places the diagnostic at the value level.
- `printMessage(ERROR, ..., element, mirror)` attaches the diagnostic at the annotation level when there is no explicit value or when the annotation placement itself is inappropriate.
- `return true` means claiming the annotation types; it does **not** mean there are no more processing rounds.

### 6.3. GoodDemo.java File

```java
@Endpoint(path = "/orders", retries = 2)
class OrderService {}

@Endpoint
class DefaultService {}

@Endpoint(path = "/legacy")
class LegacyService {}
```

This is valid source code according to the processor's rules. A `WARNING` may appear on the `LegacyService` declaration, but there are no error diagnostics from the code above.

### 6.4. BadDemo.java File

```java
@Endpoint(path = "", retries = -1)
class BrokenService {}

@Endpoint(path = "/interface")
interface InvalidContract {}
```

This program is **intentionally written to violate the processor's contract**, even though the annotation/type syntax itself is valid. The processor reports:

- **A `path` value error** at `""`.
- **A `retries` value error** at `-1`.
- **An annotation error** at `@Endpoint(...)` on the `InvalidContract` interface, because the project rule only accepts classes.

Exact line/column numbers and underlining style depend on the compiler. These errors are reported by the processor via `Messager`, not as a `RuntimeException` at runtime.

### 6.5. javac Test Commands

With JDK 17+, create the `build` directory, and then from the directory containing the four files, run:

```bash
mkdir -p build

javac --release 17 -d build Endpoint.java EndpointProcessor.java

javac --release 17 -cp build -processorpath build \
  -processor EndpointProcessor -d build GoodDemo.java

javac --release 17 -cp build -processorpath build \
  -processor EndpointProcessor -d build BadDemo.java
```

The **first** command compiles the annotation type and the processor. The **second** command invokes the processor on valid source code and is expected to finish successfully, despite a warning. The **third** command intentionally triggers ERROR diagnostics and is therefore expected to return a non-zero exit code; this demonstrates how the processor rejects invalid source code.

In PowerShell, create the directory with `New-Item -ItemType Directory -Force build` and write each `javac` command on a single line; the trailing `\` character in the `bash` block is Unix-style shell syntax.

Core messages expected to appear in the diagnostics:

```text
Nên đổi tên LegacyService
path không được rỗng
retries phải >= 0
@Endpoint chỉ hỗ trợ class theo quy tắc dự án
```

**These are the message strings** emitted by the processor, **not the verbatim stdout of the compiler**. `javac` also adds the `warning:`/`error:` severity level, file path, line/column, source snippet, and diagnostic count; you should not test by comparing the entire compiler output verbatim.

## 7. When to Choose Element, AnnotationMirror, or AnnotationValue?

Use the narrowest level that **is meaningful and has a valid origin**:

| Scenario | Level to attach | Reason |
| --- | --- | --- |
| Class name violates naming conventions, unrelated to a specific annotation | `Element` | The error belongs to the class declaration |
| An annotation is disallowed on this kind of declaration by library rules | `Element + AnnotationMirror` | The entire annotation usage is what needs to be fixed |
| `@Endpoint(retries = -1)` where `-1` is explicitly written | `Element + AnnotationMirror + AnnotationValue` | The element's specific value is the cause of the error |
| The annotation uses an invalid default, so there is no argument expression | `Element + AnnotationMirror` | There is no value token at the usage site to highlight |
| Invalid global processor configuration, not attributable to any declaration | `kind + message` | The diagnostic has no specific element coordinates |

**Do not force a diagnostic down to the value level** if the error is actually a combination of multiple elements. For example, `min = 100, max = 1` is invalid due to the relationship between two values; depending on UX, you can attach the error to the annotation as a whole or to a specific element chosen by policy.

## 8. Boundaries and Pitfalls When Attaching Error Locations

### 8.1. No Guarantee That the IDE/Compiler Always Highlights Exactly

Some integrated compilers provide exact source positions for annotation values; other tools may only point to the annotation or declaration. `Messager` specifies the **semantic** location associated with a diagnostic, while rendering the message/path/line/column is the job of the compiler and IDE.

Therefore, write self-explanatory messages even when the user only sees:

```text
error: retries phải >= 0
```

You should not rely solely on a pointer arrow beneath a literal to explain the error.

### 8.2. Default Values Are Not Located at the Usage Site

With:

```java
@Endpoint
class DefaultService {}
```

`path` and `retries` are taken from the defaults of the annotation type. If a default is ever defined incorrectly according to custom rules, querying `getElementValuesWithDefaults()` will still detect the invalid value, but the source at `@Endpoint` **does not write that argument**. Attach the message to the annotation/class and clearly state the name of the element/default causing the error.

### 8.3. Arrays and Nested Annotations Require Sub-models

For example:

```java
@interface Rule {
    String name();
}

@interface Policy {
    Rule[] rules();
}
```

When `rules` is an annotation array, `AnnotationValue.getValue()` at the element level can represent the child values in the **javax.lang.model model**. Do not cast to a runtime `Rule[]` or expect an application `List<Rule>` value. You must traverse the value using model types, such as via `AnnotationValueVisitor` or `List<? extends AnnotationValue>`, and preserve the correct mirror/value context when issuing a diagnostic.

If the compiler API does not allow pinpointing diagnostics down to a nested child as desired, choose the parent annotation/array location along with a message clearly stating the logical path, such as `rules[2].name`.

### 8.4. Distinguishing the Compiler Model from Runtime Reflection

Inside an annotation processor:

```java
element.getAnnotationMirrors()
```

retrieves language-model metadata at compile time, including annotations without `RUNTIME` retention in the source being processed.

In a runtime program:

```java
SomeClass.class.getAnnotation(Endpoint.class)
```

uses reflection, which depends on retention and runtime APIs. These are two different representations, and there is no reason to convert an `AnnotationMirror` into a runtime `Endpoint` object in order to report an error.

### 8.5. Do Not Retain Elements Across Compilation Runs

`Element`, `AnnotationMirror`, and `AnnotationValue` belong to the **processing environment** of the compilation session. If you need to store an error list long-term or across builds, store appropriate logical information (type name, element name, message code) rather than directly serializing compiler model objects.

Within the same session, a processor may run across multiple rounds; when storing accumulated data, note that elements from an earlier round may no longer be suitable for accurately identifying locations in a later round. It is better to report errors immediately when invalid source is encountered in the current round.

### 8.6. Language Errors vs. Business Rule Errors

The compiler checks annotation syntax, element types, and `@Target`. For example, `@Endpoint(retries = "three")` will be rejected by the compiler because `String` does not match `int`. A processor is suited for checking **custom constraints**, such as `retries >= 0` or “this annotation only supports concrete classes”.

You should not try to fix compiler type errors inside a processor; a syntactically invalid program can result in an incomplete source model or cause the processor not to be invoked as expected.

## 9. Standard Diagnostic Workflow for an Annotation Processor

1. **Initialize:** obtain `processingEnv.getMessager()`, `getElementUtils()`, and `getTypeUtils()`; declare the supported annotations.
2. **Select the round:** if `roundEnv.processingOver()`, do not process new sources through the normal workflow.
3. **Retrieve elements:** use `getElementsAnnotatedWith(TypeElement)` to find targets for the current round.
4. **Select the annotation:** compare `AnnotationMirror.getAnnotationType()` against the exact annotation type rather than relying on array index or `toString` strings.
5. **Retrieve values:** read `getElementValues()` if you only care about explicitly written values; use `getElementValuesWithDefaults()` when validating all effective values.
6. **Check invariants:** determine whether the error belongs to the whole declaration, the annotation as a whole, or a specific element/value.
7. **Emit the diagnostic:** use the `Messager.printMessage` overload that provides sufficient context without exceeding what can actually be located.
8. **Stop generating invalid code:** if validation fails, avoid generating output that would be treated as valid; `Diagnostic.Kind.ERROR` ensures an error diagnostic is recorded for the build.
9. **Test:** run `javac -processor ...` on both valid and invalid sources; verify the messages, diagnostic kinds, and, when necessary, the displayed locations in the specific compiler/IDE.
10. **Keep messages clear:** include the element name and expectation, such as `retries phải >= 0`, instead of just writing `Invalid value`.

## 10. Common Mistakes and How to Fix Them

**1. Using printMessage(kind, msg) for every error.** You lose the ability to attach errors to source locations. Pass `Element`, `AnnotationMirror`, and `AnnotationValue` whenever valid locations exist.

**2. Taking the first mirror to report an error.** A declaration can have multiple annotations; you must locate the right annotation type using the type model.

**3. Using AnnotationMirror.toString() as an annotation selector.** That is a display representation, not a reliable type comparison. Use `Types.isSameType`.

**4. Ignoring default values.** `AnnotationMirror.getElementValues()` does not include elements that use defaults. Use `Elements.getElementValuesWithDefaults()` for complete validation.

**5. Always attaching errors to AnnotationValue even when the element uses a default.** There is no token for that value at the annotation usage site. Fall back to the mirror or declaration level.

**6. Confusing ExecutableElement and AnnotationValue.** The map key is the element's accessor declaration; the map value is the supplied value. The five-argument overload requires `AnnotationValue`, not `ExecutableElement`.

**7. Casting every AnnotationValue.getValue() to String.** Enums, class literals, nested annotations, and arrays have different model representations. Rely on the element type and a visitor when needed.

**8. Thinking Messager.ERROR immediately throws a Java exception.** Diagnostics are collected by the compilation tool. The processor still needs to control the flow of `process` and avoid generating invalid code.

**9. Thinking return true guarantees there are no errors.** `true` only claims the annotation types; it does not mean compilation succeeded.

**10. Using runtime reflection to look up SOURCE annotations.** Annotation processors use the compile-time model API, not `Class.getAnnotation` as a substitute.

**11. Testing exact path strings, columns, and carets from javac.** Diagnostic formatting can vary across environments. Tests should prioritize the ERROR/WARNING kind, message content, and relative position when supported by the tool.

**12. Reporting errors after already generating files from invalid data.** Validate before calling `Filer` to avoid broken artifacts and cascading errors.

## 11. Practice Exercises

1. **Change the warning location:** In the processor, change `printMessage(WARNING, ..., element)` to `printMessage(WARNING, ..., element, mirror)`. Compare whether the IDE/`javac` position points to `LegacyService` or `@Endpoint`.
2. **Add a constraint:** Change the default of `retries` to `-1` in `@interface Endpoint`. Verify that `@Endpoint` without specifying `retries` still triggers an error from the processor; explain why falling back to the mirror is necessary.
3. **Read the explicit map:** Print the names of the `ExecutableElement` keys from `mirror.getElementValues()` and from `getElementValuesWithDefaults()` on `DefaultService`. Explain the difference.
4. **Annotation on the wrong target:** Remove the `ElementKind.CLASS` branch and try `@Endpoint` on an interface. Design a clear diagnostic explaining why the project rule does not support interfaces.
5. **Multiple annotations:** Add another annotation onto `BrokenService`. Explain why you must not call `element.getAnnotationMirrors().get(0)`.
6. **Array element:** Add `String[] roles() default {};` to `Endpoint`. For an empty role, show how to traverse the array using the `AnnotationValue` model instead of trying to cast to a runtime array.
7. **Improve UX:** For the `path = ""` and `retries = -1` errors, propose messages that clearly state how to fix them. Open an IDE to see whether the diagnostic cursor points directly to the corresponding literal.
8. **Project organization:** Place `Endpoint` and the processor in their own packages, update `@SupportedAnnotationTypes` to the fully qualified name, and re-run both the passing and failing `javac` commands.
9. **Testing in the build:** Use test compilation to check the diagnostic count, severity, and emitted messages. Do not require character-by-character caret comparisons across two JDK versions.

## 12. Java SE 17 References

- [Messager — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Messager.html): the four `printMessage` overloads and how diagnostics are associated with source positions.
- [AnnotationMirror — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/AnnotationMirror.html): the model of an annotation usage and `getElementValues()`.
- [AnnotationValue — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/AnnotationValue.html): how annotation element values are represented.
- [Elements — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/util/Elements.html): `getElementValuesWithDefaults()` and model utilities.
- [RoundEnvironment — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html): retrieving `Element` instances by annotation in each round.
- [Diagnostic.Kind — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/Diagnostic.Kind.html): diagnostic levels supported by the compiler.

**In summary:** In an annotation processor, report errors at the **narrowest level supported by the source model**: `Element` for declarations, `Element + AnnotationMirror` for annotations, and `Element + AnnotationMirror + AnnotationValue` for explicitly supplied values. Read defaults via `getElementValuesWithDefaults()`, but do not assume defaults have an argument position in the source. Clear messages and accurate positioning help users fix annotations quickly and reduce build errors.
