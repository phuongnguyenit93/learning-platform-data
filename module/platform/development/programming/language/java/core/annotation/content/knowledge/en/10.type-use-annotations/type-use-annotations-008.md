# The Role of Type Checkers: Type Annotations Do Not Enforce Constraints on Their Own

In Java, you can place annotations on **type-use positions** (*type use*), such as `@NonNull String`, `List<@NonNull String>`, or `String @NonNull []`. This syntax allows programs and tools to store or read additional information about how types are used. However, **merely defining and applying `@NonNull` does not cause `javac` to forbid `null` assignments by default**.

For example:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.TYPE_USE)
@interface NonNull {}

class Example {
    @NonNull String name = null; // Java 17 javac still accepts this
}
```

Here, the `@NonNull` annotation properly has `@Target(TYPE_USE)`, so its placement is valid. However, Java Core **is not provided with any nullness analysis rule for this custom annotation**. The name `NonNull` and the characters in the annotation name do not create constraint rules on their own. If you want the compiler or build process to warn about or reject this kind of assignment, you must use **a type checker or static analysis tool that understands that annotation**, installed and configured to run; or write the appropriate checking rules yourself.

This lesson clarifies the responsibilities of the Java language, annotations, type checkers, annotation processors, reflection, and runtime checks, and shows how to observe this behavior using Java 17.

## 1. Java performs built-in type checking, but does not automatically understand every qualifier

Java is a statically type-checked language. `javac` already analyzes the validity of assignments, parameters, generic types, overrides, and many other rules:

```java
int count = 10;     // Valid
// int wrong = "10"; // Compile-time error: String cannot be assigned to int
```

This mechanism is based on **the Java language's type system and assignment rules**. A custom annotation adds *metadata* to the code; by itself, it does not become a new kind of Java type with new assignment rules.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.TYPE_USE)
@interface Trusted {}

class UserInput {
    @Trusted String value = "data";
}

class OtherInput {
    String value = "data";
}
```

At the level of standard Java types, both fields have the type `String`. `@Trusted` does not generate a subclass of `String`, a new runtime type, or a rule stating “only validated Strings may be assigned”. If a checker knows about `Trusted` and data-trust rules, it can **interpret** the metadata as its own analysis condition.

Therefore, it is necessary to distinguish:

1. **Core Java type rules**: the compiler always enforces these; custom annotations cannot bypass core type errors.
2. **Annotation usage rules**: the compiler checks whether the annotation exists, whether the usage location matches `@Target`, and whether element values have the correct type.
3. **Enhanced semantic rules**: for example, “do not assign null to `@NonNull`”, “only sanitized input may flow into SQL”, “meters cannot be mixed with seconds”. These rules require a tool that understands the qualifiers and implements the corresponding analysis.

### An annotation is a description; the checker is where rules are enforced

`@NonNull` may carry a very clear descriptive meaning for human readers, but **Java SE does not standardize a general meaning for custom annotations named `NonNull`**. A specific checker may define its own convention for interpreting it; another checker may use a different set of annotations or level of strictness. You should not infer that simply seeing `@NonNull` means the build is already protected.

## 2. What is TYPE_USE? How does it differ from declaration annotations?

Java 8 introduced the ability to attach annotations at **type-use positions**, defined in the JLS (`4.11` and `9.7.4`). The `@Target(ElementType.TYPE_USE)` meta-annotation confirms that an annotation can be placed in those positions.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;
import java.util.List;

@Target(ElementType.TYPE_USE)
@interface NonNull {}

class TypeUseExamples {
    @NonNull String title;
    List<@NonNull String> labels;
    @NonNull String[] elementsAnnotated;
    String @NonNull [] arrayAnnotated;

    @NonNull String describe(@NonNull String input) {
        @NonNull String local = input;
        return local;
    }
}
```

The snippet above is a syntax example; uninitialized fields have their default values when they are instance fields according to standard Java rules. `TYPE_USE` allows placing a qualifier on:

- A type in the declaration of a variable, field, parameter, return type, or local variable.
- A type argument in generics, such as `List<@NonNull String>`.
- Component types and array dimensions; annotation placement matters because `@NonNull String[]` and `String @NonNull []` target different parts of the array type.
- Certain casts, type arguments, wildcards/bounds, `implements`/`extends`, and other valid type-use positions according to the Java grammar.

**Important distinction:** `@NonNull String[]` can describe the **String element type**, whereas `String @NonNull []` attaches the annotation to the **array dimension**. A type checker may treat “non-null array” and “non-null elements” as two separate constraints. `javac` does not enforce either of them by default merely because the annotation appears.

When writing an annotation for a **type parameter declaration** (for example, the generic parameter `T`), `ElementType.TYPE_PARAMETER` is the target designed for that declaration site, whereas `TYPE_USE` refers to where a type is used. An annotation can allow both:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target({ElementType.TYPE_USE, ElementType.TYPE_PARAMETER})
@interface Marked {}

class Box<@Marked T> {
    @Marked T value;
}
```

For an annotation declared with only `@Target(ElementType.METHOD)`, it cannot simply be placed on a type argument such as `List<@OnlyMethod String>`; the compiler will report that the annotation is not applicable to that location. **This is a placement/syntax error checked directly by Java**, which is completely different from checking nullness/taint for a valid qualifier.

## 3. Runnable example: Java accepts null even when the type has @NonNull

Create a single file `TypeUseCheckerDemo.java`. The program uses an annotation with `@Retention(RUNTIME)` so that we can also read the type-use location via reflection.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.Field;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface NonNull {}

class Submission {
    public @NonNull String title = null;
    public List<@NonNull String> tags = new ArrayList<>();

    void populate() {
        tags.add(null);
    }
}

public class TypeUseCheckerDemo {
    public static void main(String[] args) throws ReflectiveOperationException {
        Submission submission = new Submission();
        submission.populate();

        Field titleField = Submission.class.getDeclaredField("title");
        Field tagsField = Submission.class.getDeclaredField("tags");
        AnnotatedType titleType = titleField.getAnnotatedType();
        AnnotatedParameterizedType tagsType =
                (AnnotatedParameterizedType) tagsField.getAnnotatedType();
        AnnotatedType elementType = tagsType.getAnnotatedActualTypeArguments()[0];

        System.out.println("title type annotated: "
                + titleType.isAnnotationPresent(NonNull.class));
        System.out.println("tag type annotated: "
                + elementType.isAnnotationPresent(NonNull.class));
        System.out.println("field declaration annotated: "
                + titleField.isAnnotationPresent(NonNull.class));
        System.out.println("null title accepted: " + (submission.title == null));
        System.out.println("null tag accepted: " + (submission.tags.get(0) == null));

        try {
            Objects.requireNonNull(submission.title, "title");
        } catch (NullPointerException e) {
            System.out.println("runtime guard: " + e.getMessage());
        }
    }
}
```

Compile and run with Java 17:

```bash
javac --release 17 -Xlint:all TypeUseCheckerDemo.java
java TypeUseCheckerDemo
```

Exact output:

```text
title type annotated: true
tag type annotated: true
field declaration annotated: false
null title accepted: true
null tag accepted: true
runtime guard: title
```

What the experiment proves:

1. Both the type of the `title` field and the generic type argument in `tags` have the `@NonNull` annotation and can still be read using `AnnotatedType`/`AnnotatedParameterizedType`.
2. `Field.isAnnotationPresent(NonNull.class)` returns `false` in this example because `@NonNull` is placed only on the **type use**, not as an annotation declared on the **field** with a `FIELD` target. Reading annotations on the type requires the `Field.getAnnotatedType()` API.
3. `@NonNull String title = null` still **compiles**. `tags.add(null)` also **compiles and runs** with standard Java 17 `javac`.
4. `Objects.requireNonNull(...)` is the actual runtime check in the example; it throws a `NullPointerException` when it encounters `null`. The annotation above does not automatically invoke this method.

**Experiment conclusion:** the annotation name, TYPE_USE target, and RUNTIME retention only determine how it is used and stored. By themselves, these properties neither create a null-rejection rule for the Java compiler nor automatically inject validation into bytecode.

## 4. What must a “type checker” do?

A static analysis tool that understands annotations can **extend standard type analysis** with the concept of a *qualifier* (a property attached to a type). For example, in a nullness model:

```text
@NonNull String  : the reference must be non-null according to the checker contract
@Nullable String : the reference may be null according to the checker contract
```

Depending on the ruleset, the tool can establish an assignment relationship such as:

```text
Value guaranteed @NonNull
       |
       v
Target accepting @Nullable      (usually valid)

Value possibly @Nullable
       |
       x
Target requiring @NonNull       (the checker may report an error)
```

The `?` symbol or specific annotations used to express nullness depend on the library and checker. The two lines above describe **a common contract of nullness checkers**, not a built-in rule of `javac` for any annotation named `NonNull` or `Nullable`.

To reliably detect violations, a tool typically needs to:

- **Read qualifiers at the exact type-use position:** for example, an annotation attached to the element of `List<...>` differs from an annotation attached to the list variable itself.
- **Check assignments and method calls:** a possibly null value must not be passed to a parameter requiring non-null without first being checked.
- **Perform data-flow/flow-sensitive analysis:** after `if (x != null)` or `Objects.requireNonNull(x)`, the checker can narrow the nullness state of `x` within the scope where it can prove it.
- **Check method contracts:** annotations on return types, parameters, fields, and override/implementation relationships.
- **Analyze generics, arrays, and wildcards:** for instance, `List<@NonNull String>` differs from `@NonNull List<@Nullable String>`.
- **Default policies and metadata from libraries:** determine whether an unannotated type is interpreted as “unknown”, “nullable”, “nonnull by default”, or another state.

A tool **does not automatically do all of the above merely because an annotation declares TYPE_USE**. It must have its own checking model, rules, compiler/AST integration APIs, and mechanism for emitting warnings or errors.

## 5. Looking at a piece of code from three perspectives

Consider the illustrative snippet below, assuming `@NonNull` and `@Nullable` have already been declared for use on type uses:

```java
class GreetingService {
    @Nullable String findName(boolean exists) {
        return exists ? "Alice" : null;
    }

    void greet(@NonNull String name) {
        System.out.println(name.toUpperCase());
    }

    void run() {
        @Nullable String candidate = findName(false);
        greet(candidate); // May cause NullPointerException
    }
}
```

**Java Core `javac` perspective:** if the annotations are valid with respect to `@Target` and their declarations, the standard compiler still treats `candidate` as a reference of Java type `String`; passing it to the `String` parameter of `greet` conforms to the core type system. It is not a standard Java type error.

**Dedicated nullness checker perspective:** if the tool supports the exact set of qualifiers in use, it can determine that `findName` returns a potentially null value and report an error when passing `candidate` to a `@NonNull` parameter. The tool may also accept an explicitly checked branch:

```java
@Nullable String candidate = findName(false);
if (candidate != null) {
    greet(candidate);
}
```

**Runtime perspective:** if `candidate` is actually null and the code calls `name.toUpperCase()`, a `NullPointerException` will still occur regardless of the annotation. Static analysis helps catch issues early within the scope of data and paths that it understands; it is not an absolute guarantee for reflection, native code, external data, or locations the tool does not analyze.

The two snippets in this section **only illustrate the rules when a compatible checker is present**; they cannot compile standalone unless `@Nullable` and `@NonNull` are defined. A complete example that does not require external tools is already in section 3.

## 6. @Target, @Retention, and the checker are three distinct responsibilities

| Concept | Definition | Built into Java Core | What does not happen automatically |
|---|---|---|---|
| `@Target(TYPE_USE)` | Allows the annotation to appear at type-use positions | Checks where it is applied | Does not check the meaning of “nonnull”, “trusted”, “positive” |
| `@Target(TYPE_PARAMETER)` | Allows it to appear on type parameter declarations | Checks declaration placement | Does not check enhanced generic rules |
| `@Retention(SOURCE)` | Retains annotation usages in source during compile-time processing | Can be seen by the compiler/processor when compiling source | Usages are no longer present in `.class` |
| `@Retention(CLASS)` | Retains metadata in the binary when the applied position is stored per JLS rules | The compiler stores it accordingly | Standard Java reflection does not see it automatically |
| `@Retention(RUNTIME)` | Stores and allows reflection to read it at API-supported locations | Runtime reflection can retrieve the metadata | Does not automatically run validation/null checks |
| **Type checker** | Defines and enforces rules on types with qualifiers | Exists only if a specific tool and configuration are present | Not automatically generated by `@interface` |

Choose retention depending on **when the metadata is consumed**:

- If the tool analyzes code during source compilation, a SOURCE annotation may be sufficient.
- If the tool must analyze libraries already compiled into `.class`/JAR files, the annotation may need to be saved into the class file (CLASS or RUNTIME, if the location is preserved).
- If the application wants to use reflection to inspect type annotations at runtime, RUNTIME and the appropriate `AnnotatedType` API are required.

Simply setting `RUNTIME` does not mean a checker will automatically run at runtime. Retention is only a contract for storing metadata. A checker runs when the build/tooling is invoked; runtime validation requires separate execution code.

## 7. Annotation processor and type checker: related, but not synonymous

An **annotation processor** is a program that runs during compilation under the `javax.annotation.processing` API. It can read metadata, generate source files, and emit warnings or errors via `Messager`. However, a simple processor that scans annotations **does not automatically have the capability to analyze all assignments, data flow, or qualified type relationships**.

A **dedicated type checker** can be implemented through a compiler plugin, a type-analysis framework, or a build/IDE integration component. It typically has a deeper understanding of expressions, types, control flow, and generics.

For example, consider a processor that only checks a declaration rule: every field whose name ends with `Id` must use the type annotation `@NotNullType`. This rule **only checks for the presence of the annotation**; it does not prove that the field's value is actually non-null. The following experiment clarifies tool responsibilities.

### Java 17 experiment: a processor generating compilation errors from a custom rule

Create four files in the same directory.

**File `NotNullType.java`:**

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE_USE)
public @interface NotNullType {}
```

**File `FieldRuleProcessor.java`:**

```java
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;

@SupportedAnnotationTypes("*")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class FieldRuleProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations, RoundEnvironment round) {
        for (Element root : round.getRootElements()) {
            for (Element element : root.getEnclosedElements()) {
                if (element.getKind() == ElementKind.FIELD
                        && element.getSimpleName().toString().endsWith("Id")
                        && element.asType().getAnnotation(NotNullType.class) == null) {
                    processingEnv.getMessager().printMessage(
                            Diagnostic.Kind.ERROR,
                            "Field ending in Id needs @NotNullType", element);
                }
            }
        }
        return false;
    }
}
```

In the processor code, `element.asType()` provides the `TypeMirror` of the field; `getAnnotation(NotNullType.class)` checks the annotation **on the type** of the field. `Messager` reports an error at the field declaration when the specified rule is not met. The logic is intentionally limited to learn the mechanism; it does not yet analyze assigned values or methods.

**File `ValidOrder.java`:**

```java
class ValidOrder {
    @NotNullType String orderId = null;
}
```

**File `InvalidOrder.java`:**

```java
class InvalidOrder {
    String orderId = "123";
}
```

Compile the annotation definition and processor:

```bash
javac --release 17 NotNullType.java FieldRuleProcessor.java
```

Invoke the processor explicitly for each input:

```bash
javac --release 17 -cp . -processorpath . -processor FieldRuleProcessor ValidOrder.java
javac --release 17 -cp . -processorpath . -processor FieldRuleProcessor InvalidOrder.java
```

- For `ValidOrder.java`: the compiler **succeeds**, even though `orderId = null`. The processor only verifies that the type annotation is present; it does not check the value.
- For `InvalidOrder.java`: the compiler **fails** because the processor emits `Diagnostic.Kind.ERROR`. Key message:

```text
InvalidOrder.java:2: error: Field ending in Id needs @NotNullType
    String orderId = "123";
           ^
1 error
```

Note: `InvalidOrder`'s field actually has a non-null string, yet the processor still rejects it because the **field naming and annotation rule** was programmed that way. This illustrates that the additional errors produced depend strictly on what the tool was written to check.

**This experiment cannot replace a nullness type checker.** A real nullness checker must inspect assignment paths, values, parameters, returns, generics, flow, and contracts; merely seeing `@NotNullType` is not enough.

One workflow detail: you must specify `-processor`/`-processorpath` (or configure the processor through the build). Simply adding a dependency containing the annotation and expecting warnings to appear automatically is not enough. The class names, paths, and processor activation method may differ in an actual build tool.

## 8. Checking TYPE_USE on generics: the meaning of annotation placement

Use qualifiers on the list type and element type to illustrate:

```java
List<@NonNull String> names;
@NonNull List<String> listReference;
@NonNull List<@NonNull String> both;
```

These are three different metadata configurations:

| Example | What the annotation targets | What the checker may want to enforce |
|---|---|---|
| `List<@NonNull String>` | `String` as a type argument | No element in the list may be null |
| `@NonNull List<String>` | The list reference | The list variable must not be null |
| `@NonNull List<@NonNull String>` | Both the list reference and the elements | Both conditions simultaneously |

The metadata values reside at different type-use positions; therefore, a rigorously designed checker must know how to look in the right position. Java provides reflection APIs such as `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()` to inspect type annotations on type arguments when the retention is appropriate, yet **being able to read them does not mean values are automatically constrained**.

With generic methods, return types, wildcards, or arrays, the problem grows more complex: each position has its own qualifier, and generic inference and type transformations must respect the qualifier rules defined by the checker. For example, if a `List<@NonNull String>` is allowed to contain null, the contract has failed at runtime; if a checker is configured, it must detect `add(null)` or data coming from a potentially null source.

## 9. Real Java errors vs. additional checker errors: distinguishing them in logs

Suppose there are three cases:

**Case A — standard Java type error:**

```java
// Does not compile in standard Java:
int number = "forty-two";
```

No annotation or additional checker is needed to detect this.

**Case B — incorrect @Target:**

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;
import java.util.List;

@Target(ElementType.METHOD)
@interface OnlyMethod {}

class WrongPlacement {
    // Does not compile: OnlyMethod is not intended for TYPE_USE.
    // List<@OnlyMethod String> values;
}
```

The compiler checks where the annotation is applied, even though it does not understand any business semantics of `OnlyMethod`.

**Case C — violation of a convention defined by a checker:**

```java
class Person {
    @NonNull String nickname = null;
}
```

If `@NonNull` is a self-declared type-use annotation and you run plain `javac`, this is not an error from the standard Java type system. If you enable a checker that **actually understands that annotation** and its null-prohibition rule, it may emit an error or warning. The severity level is determined by the tool configuration: one project might configure diagnostics as errors that fail the build, while another treats them as warnings.

Do not handle every “annotation warning” mechanically with `@SuppressWarnings`. Different tools use different suppression keys and APIs for adjusting severity levels; you must consult the documentation of the actual checker or build plugin.

## 10. Static checking and runtime checking complement each other

**Static type checking** finds bugs from source/type information before execution, helping reduce errors early. It is strong when analyzing types, data assignments, and control flow; it has limitations when data comes from reflection, external systems, dynamic proxies, or logic that cannot be proven at compile time.

**Runtime validation** checks actual values at a specific point in execution:

```java
import java.util.Objects;

class AccountService {
    static String normalize(String name) {
        Objects.requireNonNull(name, "name");
        return name.trim();
    }
}
```

Here, `Objects.requireNonNull` actually checks `name` and throws an exception if it is null. It operates independently of annotations. Validation frameworks also run only when the execution flow **actually invokes** the corresponding validator/hook.

A project can combine:

1. Qualifiers/annotations to declare contracts.
2. Type checkers to analyze contracts at compile time.
3. Guards/validation to protect trust boundaries at runtime.
4. Tests to verify business and integration cases.

No single option automatically guarantees complete safety for every scenario; you must understand **which tool enforces which rule at which stage**.

## 11. SOURCE, CLASS, or RUNTIME retention for a type checker?

`@Target(TYPE_USE)` and `@Retention` are two independent axes. For example:

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface NonNull {}

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE_USE)
@interface CompileTimeChecked {}
```

A SOURCE annotation can be observed by the compiler/processor during source compilation, but is not stored in the binary representation. A RUNTIME annotation can be queried through the appropriate `AnnotatedType` APIs. A CLASS annotation can reside in the class file, though it is not visible to standard runtime reflection.

If the checker needs to analyze **already-compiled libraries**, the qualifier and build design must consider retaining metadata in the binary or providing an external *stub/annotation specification*. If the checker runs only when compiling the full source, SOURCE may suffice. Tools vary in the retention levels and input metadata they support or require; check the contract of the specific checker.

Not every compiler plugin, annotation processor, or static analyzer can automatically read all generic information via reflection; runtime reflection is not equivalent to the Java compiler model (Element/TypeMirror) and does not provide every source/data-flow detail.

## 12. When should you use a dedicated checker?

Use a checker when the project has recurring classes of bugs that static checking rules can help detect before execution, for example:

- **Nullness:** potentially null data passed to places requiring non-null; insufficient null-check conditions.
- **Taint/trust:** unvalidated input reaching sensitive locations; “trusted/untrusted” can be represented with qualifiers and a corresponding ruleset.
- **Units of measurement:** preventing mixing of different units or quantities, provided the qualifier system and checker are fully built out.
- **Immutability/ownership:** restricting mutation or transfer of data according to the rules that the tool actually supports.

An example in the ecosystem is the **Checker Framework**, which provides the mechanism and specialized annotation-based checkers. This is a feature of **the library/tool and its configuration**; it does not mean Java Core understands every annotation named `NonNull`, `Nullable`, or `Untainted` by default. Some IDEs and analyzers also have their own nullness checks. When choosing a tool, you need to standardize the annotation namespace, compiler configuration, and the status of libraries that have not yet been annotated with qualifiers.

For small applications, you can start with null checks at data boundaries and keep Java types clear. When contracts are reused across the project, qualifiers paired with a compatible checker deliver broader benefits.

## 13. Common misconceptions

**Misconception 1 — Creating your own @NonNull and thinking javac will forbid null.**  
No. `@interface NonNull` + `@Target(TYPE_USE)` only declares valid metadata. An additional checker is needed to produce nullness diagnostics.

**Misconception 2 — Thinking RUNTIME retention means validation runs automatically.**  
No. RUNTIME only enables storing and reading the annotation at reflection-supported positions. Without code that reads and checks it, there is no validation behavior.

**Misconception 3 — Confusing an annotation on a field with an annotation on the field's type.**  
`Field.getAnnotation(...)` queries annotations on the **field declaration**; `Field.getAnnotatedType()` queries the **type use** of the field. For a qualifier targeting only TYPE_USE, these two lookup paths can yield different results, as shown in the full example.

**Misconception 4 — Thinking a simple processor is equivalent to a comprehensive type checker.**  
The processor in section 7 only checks whether the field is annotated. It still accepts `@NotNullType String orderId = null`. Nullness analysis requires dedicated rules and data-flow analysis.

**Misconception 5 — Running javac -Xlint:all and assuming all annotations are semantically checked.**  
`-Xlint:all` enables the warning categories supported by `javac`; it **does not automatically activate all external checkers**. The build must run the right tool with the right configuration.

**Misconception 6 — Placing @NonNull in the wrong position on an array or generic.**  
A qualifier placed on a list element differs from a qualifier on the list itself. The same applies to arrays: whether it is attached to the element type or an array dimension affects its meaning according to the checker. Write the intended contract explicitly.

**Misconception 7 — Mixing annotations from multiple libraries.**  
Two annotations both named `NonNull` in different packages do not automatically have the same meaning or get supported by the same checker. Know precisely which annotation types the tool reads.

**Misconception 8 — Suppressing warnings too broadly.**  
Suppressing on a large class can hide new violations, while warning categories and suppression keys depend on the tool. If there is a compelling reason, narrow the scope and document the reason, while keeping runtime guards where external data needs validation.

**Misconception 9 — Seeing runtime metadata and assuming the value is guaranteed.**  
`AnnotatedType` reading `@NonNull` says nothing about the actual value stored. Representing metadata and verifying data are two distinct operations.

## 14. Workflow for adopting type-checking annotations in a project

1. **Identify the bugs you want to prevent:** null dereferences, trusted input, units of measurement, mutability, and so on. Express the constraints as valid and invalid examples.
2. **Choose the annotation and checker as a pair:** verify that the checker actually understands the qualifier, the required TYPE_USE positions, generics/arrays, and override behavior.
3. **Integrate the checker into the build/CI:** run it on the appropriate source sets/modules with a compatible compiler version; errors that should block a release should be enforced at the build level.
4. **Define defaults:** determine what an unannotated type means, and which rules apply to legacy code and external libraries.
5. **Write negative examples:** for instance, `@NonNull String s = null` must produce a checker diagnostic; if the build still passes, the tool has not been enabled or does not understand the annotation.
6. **Review runtime boundaries:** JSON data, databases, reflection, and deserialization require appropriate guards and validation.
7. **Update contracts when versions change:** JDKs, checkers, annotation dependencies, and IDEs may change their level of support; always test with the project's actual compiler and build.

Success is measured by **specific bugs accurately detected** and **valid code still being accepted**, not by the number of annotations added.

## 15. Exercises and review questions

### Exercise 1: Java Core rules

Given:

```java
@Target(ElementType.TYPE_USE)
@interface NonNull {}

class Data {
    @NonNull String name = null;
}
```

Without adding an external checker, is Java 17 `javac` required to report an error on the null-assignment line?

**Answer:** no. The self-declared annotation is used in a valid position; the Java language has no default nullness checking rule for this qualifier.

### Exercise 2: Understanding positions accurately

Compare:

```java
List<@NonNull String> a;
@NonNull List<String> b;
```

Where is the qualifier attached?

**Answer:** `a` attaches the qualifier to the type argument `String`; `b` attaches it to the reference type `List<String>`. A checker that supports nullness may interpret these as two different constraints.

### Exercise 3: Is an annotation processor enough?

The processor only checks that fields named `...Id` must have `@NotNullType`. Why does `@NotNullType String orderId = null` still pass?

**Answer:** the processor only checks *whether the metadata is present*; it does not evaluate the initializer value or data flow. Additional analysis rules must be implemented if you truly want to forbid null.

### Exercise 4: Retention levels

If you need to read a type annotation from `Field.getAnnotatedType()` in a running program, which retention is appropriate?

**Answer:** `RUNTIME`. With SOURCE or CLASS, standard runtime reflection does not expose the annotation usage.

### Exercise 5: Wrong @Target

If an annotation has only `@Target(ElementType.METHOD)` and is placed in `List<@OnlyMethod String>`, is javac allowed to report an error?

**Answer:** yes, because the annotation placement is invalid. This is a Java placement rule and does not require a separate semantic checker.

### Exercise 6: Criteria to prove a checker is working

How do you know that nullness checking is actually enabled in CI?

**Answer:** create a build test that intentionally uses a potentially null value in a `@NonNull` position; verify that the compiler/checker step emits the intended diagnostic and that the build fails on severe violations. Valid annotation syntax and a passing compile alone are not sufficient proof.

## References

- [Java Language Specification 17 `4.11` — Where Types Are Used](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.11): type-use positions in Java.
- [JLS 17 `9.6.4.1` — @Target](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.1): TYPE_USE, TYPE_PARAMETER, and application limits.
- [JLS 17 `9.7.4` — Where Annotations May Appear](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.4): type annotations and declaration annotations.
- [Java SE 17 API — AnnotatedType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedType.html): how to read type-use metadata at runtime.
- [Java SE 17 API — AnnotatedParameterizedType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html): reading annotations on type arguments of generic types.
- [Java SE 17 API — TypeMirror](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/type/TypeMirror.html): type model for compile-time processors.
- [Java SE 17 API — AbstractProcessor](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/AbstractProcessor.html): compile-time annotation processing mechanism.
- [Checker Framework](https://checkerframework.org/): example tool ecosystem supporting annotation-based type checking with tool-defined qualifiers and rules.
