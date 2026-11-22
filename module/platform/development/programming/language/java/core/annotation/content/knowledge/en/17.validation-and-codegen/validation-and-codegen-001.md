# Designing Annotation Position, Type, and Value Validation Rules in Java

## 1. The Problem: Syntactically Valid Annotations Are Not Necessarily Business-Valid

In Java, an annotation is metadata attached to program elements. The `javac` compiler already knows the language rules, for example:

- Annotations may only be attached to locations allowed by `@Target`.
- Annotation elements must have valid types: primitive types, `String`, `Class`, enums, other annotations, or one-dimensional arrays of those types.
- Values at the annotation use site must match the element type, be in a value form accepted by Java, and required elements must be provided.
- The `default` value in an annotation definition must be valid.

However, a rule such as **“this annotation may only be used on a method that returns `String`, accepts exactly one `String` parameter, has a `path` starting with `/`, and has `timeoutMs` from 1 to 5000”** is a **business rule**. Java does not infer these rules automatically from the annotation name. To validate them at compile time, we build an **annotation processor** using the `javax.annotation.processing` and `javax.lang.model` APIs to read the declaration model, check conditions, and emit diagnostics.

This topic covers three validation axes:

1. **Position:** What declaration is the annotation attached to? A class, method, field, parameter, or a type-use location?
2. **Type:** Does the annotated target have an appropriate signature/type? Do the declared annotation elements and the values used have the right types?
3. **Value:** Does the metadata satisfy content constraints such as a non-empty string, a `/` prefix, a numeric range, or compatibility between elements?

Good design must distinguish between **what the compiler already checks** and **what the processor must actively validate**.

## 2. Rule Layering: Language, Annotation Declaration, and Application Policy

| Layer | Check | Who Is Responsible? | Example |
| --- | --- | --- | --- |
| Grammar and Java language rules | Annotation type exists, element names, element types, valid constant values | `javac` | `@EndpointRule(path = 42)` is invalid because `path()` is `String` |
| Position per `@Target` | Is the annotation placed on `METHOD`, `TYPE`, `FIELD`...? | `javac` | `@Target(METHOD)` does not allow attaching to a field |
| Semantics of the annotated declaration | The method must have exactly one `String` parameter and return `String` | Custom processor | A method returning `int` is rejected by library policy |
| Domain-specific metadata values | `path` must start with `/`; `timeoutMs` must be within the allowed range | Custom processor | `path = "orders"` is rejected |
| Runtime behavior | Using `path` to register routes and timeout to control processing | Separate runtime consumer/framework | The processor does not start an HTTP server itself |

**Principle:** use `@Target` and element types to **eliminate as many foundational errors as possible directly at the compiler**. Only write custom validators for conditions not expressed by the language.

The example below intentionally gives `@EndpointRule` two targets, `METHOD` and `TYPE`, to demonstrate an **additional position rule via the processor**: although Java syntax allows attaching it to a class, application policy only accepts methods. In a production design where only methods are wanted, change it to `@Target(METHOD)` so the compiler blocks invalid usage early, keeping the processor focused on signatures and values.

## 3. Designing the Annotation Contract

Suppose the system needs to declare an “endpoint” on a method:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target({ElementType.METHOD, ElementType.TYPE})
@interface EndpointRule {
    String path();
    int timeoutMs() default 1000;
}
```

This is a **contract illustration snippet**, not a standalone runnable program file. The full runnable example in Section 7 declares this annotation in the `lesson` package.

The intended policy is:

- **EP001 — Position:** only attach to a `METHOD` declaration, even though the example's `@Target` intentionally also allows `TYPE`.
- **EP002 — Return type:** the method must return `java.lang.String`.
- **EP003 — Parameter type and count:** there must be exactly one parameter of type `java.lang.String`.
- **EP004 — `path` value:** must start with `/`, be non-empty, and contain no spaces.
- **EP005 — `timeoutMs` value:** must be in the range **1–5000**, inclusive of both endpoints.

`timeoutMs() default 1000` allows usage sites to omit the timeout. Rule EP005 must still validate **the effective value after applying defaults**; do not assume that an element absent from the source means there is no value.

### Why Is `SOURCE` Sufficient?

The processor runs during **compilation** and reads the elements provided by the compiler. It does not require the annotation to exist via runtime Reflection. `@Retention(SOURCE)` is an appropriate choice if the annotation is only used for validation or code generation at build time. If a runtime framework also wants to read `EndpointRule` via Reflection, then you must evaluate the requirement to use `RUNTIME`.

## 4. Validating **Position** with `ElementKind`

A processor typically receives annotated elements via:

```java
for (Element element :
        roundEnv.getElementsAnnotatedWith(EndpointRule.class)) {

    if (element.getKind() != ElementKind.METHOD) {
        // Report diagnostic EP001 on the violating element.
        continue;
    }

    ExecutableElement method = (ExecutableElement) element;
    // Method-specific checks.
}
```

This is an **illustrative snippet**; the imports and processor class from Section 7 are required.

- `Element` is the base interface for declarations in the language model.
- `getKind()` returns an `ElementKind` such as `CLASS`, `INTERFACE`, `METHOD`, `FIELD`, `PARAMETER`...
- Cast to `ExecutableElement` **only after confirming** `ElementKind.METHOD`.
- If the rule is for a parameter, use `ElementKind.PARAMETER` and cast to `VariableElement`; if it is for a class, use `TypeElement` after checking the corresponding kind.

**Do not confuse `@Target` with a custom position rule.** `@Target` is the syntactic contract understood by the compiler. The processor adds stricter conditions when genuinely needed. An annotation placed on a `FIELD` in this example is rejected by the compiler via `@Target` even if the processor does not handle it.

For annotations attached to **type uses** (`TYPE_USE`), locating and analyzing the structure may require processing `TypeMirror` and the AST (`com.sun.source.tree`) rather than assuming every type-use annotation will be returned directly by `RoundEnvironment.getElementsAnnotatedWith(...)` as a separate `Element`. This lesson validates **declaration annotations** and the corresponding Language Model API.

## 5. Validating **Type** with `TypeMirror` and `Types`

A method may carry the annotation in the right position yet have an unsuitable signature:

```java
// Snippet violating application policy:
@EndpointRule(path = "/items")
int find(int id) {
    return id;
}
```

This snippet **may be valid in annotation syntax** but violates both EP002 and EP003.

In the processor, a method is represented by `ExecutableElement`; use:

- `method.getReturnType()`: gets a `TypeMirror` for the return type.
- `method.getParameters()`: gets the list of `VariableElement`s for the parameters.
- `parameter.asType()`: gets a `TypeMirror` for the parameter type.
- `processingEnv.getTypeUtils()`: gets `Types` for type comparison.
- `processingEnv.getElementUtils().getTypeElement("java.lang.String").asType()`: references the `String` type model.

Snippet:

```java
TypeMirror stringType = processingEnv.getElementUtils()
        .getTypeElement("java.lang.String").asType();

Types types = processingEnv.getTypeUtils();

boolean validReturn =
        types.isSameType(method.getReturnType(), stringType);

boolean validParameters =
        method.getParameters().size() == 1
        && types.isSameType(
                method.getParameters().get(0).asType(),
                stringType);
```

**Why not compare `toString()` of the types?** In practice, there are generic types, type variables, arrays, wildcards, type-use annotations, and cases where the compiler is recovering from errors. Textual comparison is not a general semantic check. Use `Types.isSameType(...)` when **the exact same type** is required.

If the contract allows subtypes or assignable types, you can use `Types.isAssignable(...)` or `Types.isSubtype(...)` in the proper direction. This lesson's example intentionally requires **exact `String`**, so `isSameType` is appropriate.

## 6. Validating **Values** and Default Values with `AnnotationMirror`

The return type of annotation elements is already checked by `javac`, but **the meaning of values** such as `path` and `timeoutMs` remains a library rule.

In a processor, a general approach is:

1. Retrieve the list `element.getAnnotationMirrors()`.
2. Select the `AnnotationMirror` representing `@EndpointRule`.
3. Call `processingEnv.getElementUtils().getElementValuesWithDefaults(mirror)` to get a map of elements along with their values, **including defaults**.
4. Iterate over the `ExecutableElement` → `AnnotationValue` entries, identify the element name via `getSimpleName()`, and obtain the data via `AnnotationValue.getValue()`.
5. Validate strings, numbers, and relationships between fields; emit diagnostics if invalid.

For example, if the usage site only writes:

```java
@EndpointRule(path = "/ping")
String ping(String name) { return "PONG:" + name; }
```

then `AnnotationMirror.getElementValues()` reflects **explicitly written** values, whereas `Elements.getElementValuesWithDefaults(...)` also shows `timeoutMs = 1000`, because `timeoutMs()` has `default 1000`.

If you use `mirror.getElementValues()` directly and forget defaults, the processor may miss constraints or mistakenly treat the element as having no value. To validate the **effective** contract, prefer retrieving the map **with defaults**.

In this example:

| Element | Java Type When Calling `AnnotationValue.getValue()` | Rule |
| --- | --- | --- |
| `path()` | `String` | Starts with `/`, non-empty, and contains no spaces |
| `timeoutMs()` | `Integer` | From 1 to 5000 |

For elements of type `Class<?>`, nested annotations, enums, or arrays, `AnnotationValue.getValue()` may return language constructs such as `TypeMirror`, `VariableElement`, `AnnotationMirror`, or a list of `AnnotationValue`, rather than runtime objects directly like `Class<?>`. That is why general-purpose tools often need an `AnnotationValueVisitor` or handling based on the compiler model's data types.

## 7. Complete Java 17+ Program: An Annotation Processor Reporting Rule Violations

This is a **compile-time** example: the processor inspects classes/methods and reports errors immediately when running `javac`. We create two Java files to run the valid case, and add a third file when we want to test errors.

Directory structure:

```text
project/
└── lesson/
    ├── EndpointRuleProcessor.java
    ├── ServiceEndpoints.java
    └── InvalidEndpoints.java   (create only when testing invalid cases)
```

### File 1: `lesson/EndpointRuleProcessor.java`

```java
package lesson;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
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
import javax.lang.model.element.VariableElement;
import javax.lang.model.type.TypeMirror;
import javax.lang.model.util.Elements;
import javax.lang.model.util.Types;
import javax.tools.Diagnostic;

@Retention(RetentionPolicy.SOURCE)
@Target({ElementType.METHOD, ElementType.TYPE})
@interface EndpointRule {
    String path();
    int timeoutMs() default 1000;
}

@SupportedAnnotationTypes("lesson.EndpointRule")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class EndpointRuleProcessor extends AbstractProcessor {

    private void error(String code, String message, Element element) {
        processingEnv.getMessager().printMessage(
                Diagnostic.Kind.ERROR,
                code + ": " + message,
                element);
    }

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (roundEnv.processingOver()) {
            return true;
        }

        Elements elements = processingEnv.getElementUtils();
        Types types = processingEnv.getTypeUtils();
        TypeMirror stringType =
                elements.getTypeElement("java.lang.String").asType();
        TypeMirror annotationType =
                elements.getTypeElement("lesson.EndpointRule").asType();

        for (Element element :
                roundEnv.getElementsAnnotatedWith(EndpointRule.class)) {

            if (element.getKind() != ElementKind.METHOD) {
                error("EP001", "EndpointRule chi duoc gan tren method",
                        element);
                continue;
            }

            ExecutableElement method = (ExecutableElement) element;

            if (!types.isSameType(method.getReturnType(), stringType)) {
                error("EP002", "Method phai tra ve String", method);
            }

            boolean validParameters =
                    method.getParameters().size() == 1;
            if (validParameters) {
                VariableElement parameter = method.getParameters().get(0);
                validParameters =
                        types.isSameType(parameter.asType(), stringType);
            }
            if (!validParameters) {
                error("EP003", "Can dung mot tham so String", method);
            }

            for (AnnotationMirror mirror :
                    element.getAnnotationMirrors()) {

                if (!types.isSameType(
                        mirror.getAnnotationType(), annotationType)) {
                    continue;
                }

                String path = null;
                Integer timeoutMs = null;

                Map<? extends ExecutableElement, ? extends AnnotationValue>
                        values = elements.getElementValuesWithDefaults(mirror);

                for (Map.Entry<? extends ExecutableElement,
                        ? extends AnnotationValue> entry : values.entrySet()) {
                    String name =
                            entry.getKey().getSimpleName().toString();
                    Object value = entry.getValue().getValue();

                    if ("path".equals(name)) {
                        path = (String) value;
                    } else if ("timeoutMs".equals(name)) {
                        timeoutMs = (Integer) value;
                    }
                }

                if (path == null || !path.startsWith("/")
                        || path.contains(" ")) {
                    error("EP004",
                            "path phai bat dau bang / va khong co dau cach",
                            element);
                }

                if (timeoutMs == null
                        || timeoutMs < 1 || timeoutMs > 5000) {
                    error("EP005",
                            "timeoutMs phai trong khoang 1..5000",
                            element);
                }
            }
        }

        return true;
    }
}
```

**Explanation of key decisions:**

- `@SupportedAnnotationTypes("lesson.EndpointRule")` announces the annotation being processed.
- `@SupportedSourceVersion(RELEASE_17)` declares the supported source version.
- `RoundEnvironment.getElementsAnnotatedWith(EndpointRule.class)` retrieves declarations annotated with the annotation in the relevant round.
- `ElementKind.METHOD` serves as a guard before casting to `ExecutableElement`.
- `Types.isSameType` performs an exact comparison of the return type and parameter type.
- `getElementValuesWithDefaults` ensures that the default `timeoutMs` is read as well.
- `Diagnostic.Kind.ERROR` causes the compiler to report an error and fail compilation if a violation is present.
- `roundEnv.processingOver()` skips work when the processing cycle finishes.

The EP001...EP005 messages use ASCII text in the source code for consistent output across terminals; the instructional prose still explains them in Vietnamese. A production processor may use message codes and internationalized content depending on requirements.

### File 2: `lesson/ServiceEndpoints.java` — Valid Case

```java
package lesson;

public class ServiceEndpoints {
    @EndpointRule(path = "/items", timeoutMs = 2500)
    public String find(String id) {
        return "ITEM:" + id;
    }

    @EndpointRule(path = "/ping")
    public String ping(String name) {
        return "PONG:" + name;
    }

    public static void main(String[] args) {
        ServiceEndpoints service = new ServiceEndpoints();
        System.out.println(service.find("A1"));
        System.out.println(service.ping("Lan"));
    }
}
```

Both `find` and `ping` satisfy the rules: attached to `METHOD`, returning `String`, accepting exactly one `String`, with `path` starting with `/`. `find` provides a timeout of `2500`, while `ping` receives the default `1000`; both are within the allowed range.

### Two-Step Compilation

From the `project` directory, run with JDK 17 or later:

```bash
mkdir -p out
javac --release 17 -encoding UTF-8 -d out lesson/EndpointRuleProcessor.java
javac --release 17 -encoding UTF-8 -cp out -processorpath out -processor lesson.EndpointRuleProcessor -d out lesson/ServiceEndpoints.java
java -cp out lesson.ServiceEndpoints
```

The `mkdir -p` command applies to Bash-style shells. If using Windows PowerShell, you can create the directory with `New-Item -ItemType Directory -Force out`; the `javac` and `java` commands afterward remain unchanged.

**Stdout of the final `java` command:**

```text
ITEM:A1
PONG:Lan
```

When compiling the valid file, the processor emits no `ERROR`, so `javac` finishes successfully and normally prints no diagnostic lines related to EP001...EP005.

Note the distinction: the processor **does not perform HTTP routing**. The example `main` simply calls two ordinary Java methods. The annotation is a compile-time contract to validate signatures and metadata; having an actual server requires a separate runtime consumer or registry-generating code.

## 8. Testing Invalid Cases and Reading Diagnostics

### File 3: `lesson/InvalidEndpoints.java`

This file **intentionally violates the processor's rules** and must not be mixed into the compilation step for the valid case:

```java
package lesson;

@EndpointRule(path = "/class")
class InvalidClass {}

class InvalidEndpoints {
    @EndpointRule(path = "orders", timeoutMs = 0)
    int broken(int id) {
        return id;
    }
}
```

With this file, `javac` still accepts **placing the annotation on a class** with respect to `@Target` because the demo declaration includes `TYPE`, yet the processor emits EP001. Similarly, the `broken` method has a signature and metadata consistent with Java syntax, but violates the business rules.

Compile the invalid file separately, after the processor is already in `out`:

```bash
javac --release 17 -encoding UTF-8 -cp out -processorpath out -processor lesson.EndpointRuleProcessor -d out lesson/InvalidEndpoints.java
```

This command **must fail**. Depending on the JDK and how diagnostics are formatted, line order/layout may vary; the **expected error codes** are:

| Code | Error Location | Reason |
| --- | --- | --- |
| `EP001` | `InvalidClass` | Policy only accepts `METHOD` even though the demo `@Target` also includes `TYPE` |
| `EP002` | `broken` | Returns `int`, not `String` |
| `EP003` | `broken` | Parameter is `int id`, not exactly one `String` |
| `EP004` | `broken` | `path = "orders"` does not start with `/` |
| `EP005` | `broken` | `timeoutMs = 0` is outside the range 1–5000 |

Messages may include the file name, line number, `error:` marker, caret position, and total error count depending on the compiler. **Do not treat the entire stderr as a fixed string**. What needs to be verified is that codes EP001...EP005 appear and that no valid class file is treated as a successful build artifact.

If you change `@EndpointRule(path = "orders")` to `@EndpointRule(path = 7)`, that becomes an **element type error detected automatically by javac** (`path()` is `String`), rather than a case where the processor must invent EP004.

If you attach `@EndpointRule` to a field in the demo, `javac` rejects it because `@Target` does not contain `FIELD`. These errors illustrate the boundary between Java language rules and a custom processor.

## 9. Designing a Reliable Processor: Checklist

### 9.1 Define Rules with Testable Conditions

Each rule should have:

- **Stable ID:** EP001, EP002,... so IDEs, CI, and tests can easily identify it.
- **Scope:** `ElementKind` category, annotation type, and packages/modules where it applies.
- **Validity condition:** a clear logical expression, for example `1 <= timeoutMs <= 5000`.
- **Severity:** `ERROR` when it must block the build, `WARNING` if it is only a warning.
- **Helpful diagnostic:** state **what is wrong** and what the **valid value** is.
- **Test suite:** one or more passing and failing examples right at the boundaries.

Do not use unchecked exceptions to report user contract violations. `processingEnv.getMessager().printMessage(ERROR, ..., element)` lets the compiler attach the error to the offending element. For specific annotation values, overloads of `Messager.printMessage` can also attach the diagnostic to an `AnnotationMirror` and `AnnotationValue` to pinpoint the exact location.

### 9.2 Design Type Policies Intentionally

The example above requires **exact `String`**, not accepting `CharSequence`. If the library wants to allow subtypes or assignable types, you must update the `Types` logic accordingly and add explicit tests. Do not accidentally widen the contract due to textual comparison or autoboxing.

Generics, varargs, constructors, static methods, abstract methods, or overloads need explicit rules if business requirements demand them. `getKind()` and `Types` are only inspection tools; they do not decide those restrictions on their own.

### 9.3 Do Not Miss Defaults or Nested Annotations

If a rule involves `timeoutMs`, validate **the effective value** even when the user omits the element. For enums, class literals, nested annotations, or arrays, handle the appropriate `javax.lang.model` objects properly rather than assuming every value is a `String` or `Integer`.

For repeatable annotations (`@Repeatable`), you may need to handle the container annotation and rules for multiple markers depending on the API and compiler. Do not infer from a single example that `getElementsAnnotatedWith` automatically handles all nesting patterns according to your business semantics.

### 9.4 Separate Validators, Rules, and Code-Generation Behavior

A “validation and code generation” problem typically has two roles:

1. **Validator:** reads `Element`/`TypeMirror`/`AnnotationMirror` and emits `ERROR` or `WARNING`.
2. **Generator:** from valid declarations, uses `Filer` to generate sources/resources once and handle multiple compilation rounds.

You should not generate code from data **known to be invalid**. If a generated registry of endpoints is needed, run code generation after the validation step, define how duplicate `path` values, generated class names, and deterministic ordering are handled, and avoid `FilerException` caused by trying to create the same file across multiple rounds.

This example intentionally **only validates**, without generating a registry, so the material stays focused on designing the three rule categories. That also avoids the misconception that the annotation automatically creates an HTTP endpoint.

### 9.5 Handle Multiple Rounds and Model Errors

Annotation processing can span multiple rounds, especially when other processors generate new source files. Do not assume `process` is called only once. When `roundEnv.processingOver()` is `true`, do not create new sources; use appropriate conditions to skip already processed items. For declarations with `TypeKind.ERROR` due to missing dependencies, a production processor must choose to continue, defer, or report a clear error rather than casting and throwing an exception.

In addition, a processor should not arbitrarily scan or load runtime classes via `Class.forName` to inspect sources currently being compiled. The `javax.lang.model` model is the more accurate data source for the compile-time phase.

## 10. Suggested Test Matrix by Rule

| Scenario | Expected Result |
| --- | --- |
| `@EndpointRule(path = "/ok") String run(String x)` | Valid; timeout uses default 1000 |
| `@EndpointRule(path = "/ok", timeoutMs = 1)` on a valid method | Valid at lower bound |
| `@EndpointRule(path = "/ok", timeoutMs = 5000)` on a valid method | Valid at upper bound |
| Annotation on a class (in the demo `@Target` includes `TYPE`) | EP001 |
| Method returning `int` | EP002 |
| Method with zero parameters or two parameters | EP003 |
| Method accepting `Integer` instead of `String` | EP003 |
| `path = ""`, `path = "items"`, or `path = "/has space"` | EP004 |
| `timeoutMs = 0` or `5001` | EP005 |
| `path = 123` | Compiler type error, before/outside custom rules |
| Annotation on a field in the demo | Compiler `@Target` error |

A comprehensive processor test suite should also cover error combinations, repeated annotation placements, multiple modules, and missing-dependency cases when those fall within the library's supported scope. Test output assertions should match **diagnostic codes/semantics**, without requiring an exact match on the entire stderr since line numbers and JDK formatting may change.

## 11. Common Design Mistakes

**Mistake 1 — Using a processor to recheck everything `javac` already checks.** If you only want to restrict placement to methods, declare `@Target(METHOD)`; do not mislead learners into thinking target-kind policies belong entirely to the processor.

**Mistake 2 — Casting `Element` to `ExecutableElement` before checking kind.** An annotation might be placed on a class or variable, causing an invalid cast. Check `ElementKind` first.

**Mistake 3 — Comparing types using `asType().toString()`.** Not general for generics, subtypes, or nested types. Use `Types` with the comparison operation required by the contract.

**Mistake 4 — Reading only explicit values from `AnnotationMirror`.** Ignoring `default` values can cause rules to be evaluated incorrectly. Use `getElementValuesWithDefaults` when the policy requires effective values.

**Mistake 5 — Thinking `@Retention(RUNTIME)` is required for a processor to see an annotation.** Processors run at compile time, so `SOURCE` is sufficient for compile-time rules.

**Mistake 6 — Confusing compiler errors with policy errors.** `path = 123` is a Java type error, whereas `path = "items"` is a business content error. The two should be explained differently.

**Mistake 7 — Feeding unvalidated data into generated code.** A generated registry could receive invalid paths, duplicates, or unsupported method signatures.

**Mistake 8 — Using `System.out.println` as the primary error-reporting channel.** Builds/IDEs may fail to categorize or pinpoint locations accurately. Use `Messager` with `Diagnostic.Kind.ERROR` or `WARNING`.

**Mistake 9 — Failing to test value range boundaries.** For the range `1..5000`, verify that both 1 and 5000 are valid while 0 and 5001 fail.

**Mistake 10 — Trying to infer runtime behavior from compile-time validation.** When the processor accepts `@EndpointRule(path = "/ok")`, the JVM does not yet have a router. A code-generating/registry consumer or runtime framework must be designed separately for the endpoint to actually work.

## 12. Self-Check Questions

**Question 1.** Is `@Target(METHOD)` sufficient to guarantee a method accepts exactly one `String` and returns `String`?

**Answer:** No. `@Target` only validates the placement target kind; the method signature must be checked by a processor or another mechanism.

**Question 2.** In the example with `@Target({METHOD, TYPE})`, why does `@EndpointRule` on a class trigger EP001 rather than a `javac` annotation syntax error?

**Answer:** `TYPE` is present in `@Target`, so the compiler permits the class placement. EP001 is **a stricter rule enforced by the processor**.

**Question 3.** Which API should you use to inspect a method's return type in a processor?

**Answer:** `ExecutableElement.getReturnType()` returns a `TypeMirror`, followed by `Types.isSameType` or another type comparison matching the contract.

**Question 4.** Why does `@EndpointRule(path="/ping")` still have a timeout value to validate?

**Answer:** `timeoutMs()` has `default 1000`; `Elements.getElementValuesWithDefaults(mirror)` returns values after applying defaults.

**Question 5.** Are `path = 7` and `path = "ping"` invalid for the same reason?

**Answer:** No. `7` has the wrong type for the `String path()` element, so the compiler handles it; `"ping"` has the right type but violates policy rule EP004.

**Question 6.** When the processor reports EP005 with `Diagnostic.Kind.ERROR`, what is `javac` expected to do?

**Answer:** Report the diagnostic on the corresponding element and terminate compilation with an error status; the build must not be considered successful.

**Question 7.** For an annotation containing a `Class<?>` element, is the result of `AnnotationValue.getValue()` in a processor always a runtime `java.lang.Class<?>`?

**Answer:** No. The compile-time model represents class literals using type data such as `TypeMirror`, avoiding the need to load a class that is currently being compiled.

**Question 8.** Once the processor validates successfully, does the annotation automatically generate endpoint code or start a web server?

**Answer:** No. A validator only validates. Code generation requires `Filer` logic; HTTP execution requires an appropriate consumer.

**Question 9.** Why should diagnostic codes EP001...EP005 be kept stable?

**Answer:** So tests, CI, and IDEs can reliably identify errors even when message wording or source line numbers change.

**Question 10.** If you want to change the rule from “exact `String`” to “assignable to `CharSequence`”, should you just modify string comparison?

**Answer:** No. You need to determine the assignment direction, use `Types.isAssignable(...)` or an appropriate type API, and add tests for subtypes/generics.

**Key takeaway:** Use `@Target` and element type declarations so `javac` enforces language constraints; use `ElementKind` to validate declaration position, `TypeMirror`/`Types` to validate signatures, and `AnnotationMirror`/`AnnotationValue` together with `getElementValuesWithDefaults` to validate metadata content; report errors with `Messager` and keep code-generation/runtime logic separate from validation.
