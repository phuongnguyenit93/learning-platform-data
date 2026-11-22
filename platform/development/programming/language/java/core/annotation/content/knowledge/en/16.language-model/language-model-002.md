# TypeElement, ExecutableElement, and VariableElement in the Java Language Model

## 1. Why Is a Language Model Needed?

When writing an **annotation processor** in Java, processing takes place during compilation. At that point, the compiler is analyzing declarations of types, methods, constructors, fields, and parameters. The processor needs a unified way to **describe those declarations in source code** without having to load them as runtime objects using `Class.forName(...)`.

Java provides the **Language Model API** primarily in these packages:

- `javax.lang.model.element`: describes **program elements** — type, method, variable, package, and annotation declarations...
- `javax.lang.model.type`: describes the **types** of elements in the form of `TypeMirror`.
- `javax.lang.model.util`: utilities such as `Elements`, `Types`, and `ElementFilter`.
- `javax.annotation.processing`: the annotation processing infrastructure, including `AbstractProcessor`, `RoundEnvironment`, and `ProcessingEnvironment`.

The three key interfaces in this lesson are:

| Interface | Represents | Examples |
| --- | --- | --- |
| `TypeElement` | A **type** declaration | `class Invoice`, `interface Service`, `enum Status`, `@interface Marker` |
| `ExecutableElement` | A declaration of a **method, constructor, or applicable kind of executable element** | `int total(int count)`, `Invoice(String code)`, `String value();` in an annotation type |
| `VariableElement` | A **variable** declaration in various positions | field `code`, parameter `count`, enum constant, local variable if provided by the model |

**Key takeaway:** the objects above are **program-structure representations provided by the compiler**, not business objects and not method invocation calls. They tell the processor **what a declaration is, what name it has, what type it has, and how it relates to other declarations**.

## 2. The `Element` Tree: Relationships Among the Three Interfaces

All three interfaces `TypeElement`, `ExecutableElement`, and `VariableElement` extend `Element`. Therefore, they share common methods:

- `getSimpleName()`: the simple name of the declaration, such as `Invoice` or `total`.
- `getKind()`: detailed classification via `ElementKind`.
- `getModifiers()`: the set of modifiers such as `PUBLIC`, `PRIVATE`, `STATIC` (if applicable).
- `getEnclosingElement()`: the **directly enclosing** element, for example a field inside a class or a parameter belonging to a method.
- `getEnclosedElements()`: the elements declared directly inside an element.
- `asType()`: retrieves the `TypeMirror` type representation of the element.
- `getAnnotationMirrors()`: reads annotations attached directly at the language-model level.

You can visualize the following source code:

```java
class Invoice {
    private String code;

    Invoice(String code) {
        this.code = code;
    }

    int total(int quantity, int unitPrice) {
        return quantity * unitPrice;
    }
}
```

and the conceptual structure:

```text
TypeElement: Invoice
├── VariableElement: code          (FIELD)
├── ExecutableElement: Invoice(...) (CONSTRUCTOR)
│   └── VariableElement: code      (PARAMETER)
└── ExecutableElement: total(...)   (METHOD)
    ├── VariableElement: quantity  (PARAMETER)
    └── VariableElement: unitPrice (PARAMETER)
```

The tree above is a **model diagram**, not default compiler output. The corresponding items are discovered via `TypeElement.getEnclosedElements()`, `ExecutableElement.getParameters()`, and `Element` methods.

Note: `TypeMirror` answers **“what is the type?”**, whereas `Element` answers **“which declaration is being described?”**. For example, `VariableElement` represents the field `code`; `field.asType()` represents that field's `java.lang.String` type. The two are related, but not interchangeable.

## 3. `TypeElement`: Type Declarations, Not Just Classes

`TypeElement` resides in `javax.lang.model.element`. It represents a **type declaration** in the compiler's model, including classes, interfaces, enums, annotation types, and records; it can also represent types provided from class files when the compiler knows about them.

For example:

```java
class Customer {}

interface Repository {}

enum Status { NEW, DONE }

@interface Audited {
    String value();
}

record Point(int x, int y) {}
```

All of those declarations can be represented by a `TypeElement`, while `getKind()` distinguishes them:

| Declaration | Typical `ElementKind` |
| --- | --- |
| `class Customer` | `CLASS` |
| `interface Repository` | `INTERFACE` |
| `enum Status` | `ENUM` |
| `@interface Audited` | `ANNOTATION_TYPE` |
| `record Point(...)` | `RECORD` |

Several specialized APIs:

- `type.getQualifiedName()`: the qualified name, such as `lesson.Invoice`. For named member types, the qualified name reflects the declaration relationship.
- `type.getSimpleName()`: the short name, such as `Invoice`.
- `type.getSuperclass()`: the `TypeMirror` representation of the superclass when meaningful.
- `type.getInterfaces()`: the list of implemented/extended interface types.
- `type.getTypeParameters()`: the type parameters for generic declarations, as `TypeParameterElement`.
- `type.getEnclosedElements()`: the declarations directly inside, including fields, constructors, methods, and nested types depending on the declaration.

`TypeElement` is **not** `java.lang.Class<?>`. A processor can inspect source code that has not yet been compiled into `.class`, whereas `Class<?>` is the runtime representation of a type already known to the JVM.

### `TypeElement` and Annotation Types

The declaration `@interface Marker { String value(); }` is also a `TypeElement` with `ElementKind.ANNOTATION_TYPE`. However, the `value()` element **inside** it is an `ExecutableElement` with `ElementKind.METHOD`.

This is a very important distinction for a processor: the **annotation type** is a type declaration; the **annotation element method** is a method declaration belonging to that type. If the element has `default`, the processor can query `ExecutableElement.getDefaultValue()` to retrieve the corresponding `AnnotationValue`.

## 4. `ExecutableElement`: Methods, Constructors, and Annotation Elements

`ExecutableElement` represents an executable declaration. For regular Java code, the two most common cases are:

- `ElementKind.METHOD`: method declaration.
- `ElementKind.CONSTRUCTOR`: constructor declaration.

In addition, elements declared inside an annotation type such as `String value();` also belong to the method group, and the language model can represent other special executable elements depending on the program structure.

Useful specialized methods:

| API | Meaning |
| --- | --- |
| `getParameters()` | List of `VariableElement` instances representing the **formal parameters**, in order |
| `getReturnType()` | `TypeMirror` of the return type; for a constructor or `void` method, has the `VOID` pseudo-type representation |
| `getTypeParameters()` | The `TypeParameterElement` instances declared for a generic method |
| `getThrownTypes()` | The exception types declared in `throws` |
| `isVarArgs()` | Checks whether the method/constructor has variable-arity parameters |
| `getDefaultValue()` | The default value of an **annotation element**, if any; otherwise `null` |
| `getReceiverType()` | The receiver type if applicable to the executable |
| `getSimpleName()` | The simple name of the executable; `getKind()` should be used to distinguish constructors from methods |

Example:

```java
class MathService {
    int sum(int left, int right) {
        return left + right;
    }

    public <T> T echo(T value) {
        return value;
    }
}
```

- `sum` and `echo` are `ExecutableElement` instances of kind `METHOD`.
- `sum.getParameters()` (inside the processor when `sum` is an `ExecutableElement` variable) contains two `VariableElement` instances named `left` and `right`.
- `echo.getTypeParameters()` contains one `TypeParameterElement` representing `T`.
- `sum.getReturnType()` represents the primitive type `int`.

**Do not confuse `getReturnType()` with method execution.** It returns information about the **declaration's return type**; it does not run `sum` and does not retrieve any computed value.

### Constructors Are Not Like Regular Methods

A constructor has `ElementKind.CONSTRUCTOR` and does not return a business result. Even though the model structure uses `ExecutableElement` for both, the compiler distinguishes it from `METHOD`. Therefore, when scanning `getEnclosedElements()`, check the kind or use `ElementFilter.constructorsIn(...)` and `ElementFilter.methodsIn(...)` so you do not confuse the two groups.

### Reading the Default Value of an Annotation Element

```java
@interface Endpoint {
    String path();
    int timeout() default 3000;
}
```

In the language model:

- `Endpoint` is a `TypeElement`.
- `path()` and `timeout()` are `ExecutableElement` instances.
- `timeout.getDefaultValue()` returns an `AnnotationValue` representing the integer `3000`.
- `path.getDefaultValue()` returns `null` because the element has no default.

This is a **compile-time API**. Do not confuse it with `java.lang.reflect.Method.getDefaultValue()` at runtime; the API names are the same, but the data types and operating environments differ.

## 5. `VariableElement`: Fields, Parameters, and Various Variable Kinds

`VariableElement` is the interface used for variable declarations in the compiler model. It does not represent only **class fields**.

| Declaration Code | `ElementKind` | Corresponding Element |
| --- | --- | --- |
| `private String code;` in a class | `FIELD` | `VariableElement` of field `code` |
| `void run(int count)` | `PARAMETER` | `VariableElement` of parameter `count` |
| `enum Stage { NEW }` | `ENUM_CONSTANT` | `VariableElement` of constant `NEW` |
| `int n = 5;` in a method | `LOCAL_VARIABLE` when the model includes that element | `VariableElement` of the local variable |
| `catch (Exception ex)` | `EXCEPTION_PARAMETER` when the model includes that element | `VariableElement` of `ex` |

Several other variable-related kinds may also be encountered in the language model. What is essential is to **read `getKind()` before concluding whether a `VariableElement` is a field or a parameter**.

Commonly used APIs:

- `variable.getSimpleName()`: the declaration name, for example `quantity`.
- `variable.asType()`: `TypeMirror` representing the type, for example `int`.
- `variable.getEnclosingElement()`: the directly enclosing element — the method for a parameter, the class for a field.
- `variable.getConstantValue()`: returns the compile-time constant value for a **`static final` field of primitive type or `String`** that satisfies the constant-variable requirements; other variables return `null`. Do not use this API to “read the current value” of an object.

### Identical Names Do Not Mean the Same `VariableElement`

```java
class Parcel {
    private String label;

    void rename(String label) {
        this.label = label;
    }
}
```

Here there are two declarations with the same name `label`:

1. `Parcel.label` is a field → `VariableElement` of kind `FIELD`.
2. The parameter `label` of `rename` is a parameter → `VariableElement` of kind `PARAMETER`.

A processor distinguishes them via `getKind()` and `getEnclosingElement()`. If you want to list a class's fields, use `ElementFilter.fieldsIn(type.getEnclosedElements())`; if you want to list a method's parameters, use `executable.getParameters()`.

### Local Variables Do Not Appear by Default in `getEnclosedElements()`

The annotation processing model typically serves declarations at the type, member, and parameter levels. **You should not assume** that traversing `TypeElement.getEnclosedElements()` will find every local variable inside a method body. If analyzing detailed expressions and statements inside a body is required, use the compiler's syntax tree APIs such as `com.sun.source.tree` / `com.sun.source.util.Trees` when supported by the environment; do not treat `Element` as a full AST.

## 6. Complete Java 17+ Example: An Annotation Processor Traversing All Three Element Types

To properly demonstrate the role of the **compile-time** API, this example uses two Java files in the `lesson` directory. We create a source-retained `@Inspect` annotation and a separate processor, then compile an `Invoice` class annotated with it. The processor will print the information provided by the compiler before running the program.

Directory structure:

```text
project/
└── lesson/
    ├── InspectProcessor.java
    └── Invoice.java
```

### File 1 — `lesson/InspectProcessor.java`

```java
package lesson;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.ExecutableElement;
import javax.lang.model.element.TypeElement;
import javax.lang.model.element.VariableElement;
import javax.lang.model.util.ElementFilter;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
@interface Inspect {}

@SupportedAnnotationTypes("lesson.Inspect")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class InspectProcessor extends AbstractProcessor {

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (roundEnv.processingOver()) {
            return true;
        }

        for (Element element :
                roundEnv.getElementsAnnotatedWith(Inspect.class)) {

            if (!(element instanceof TypeElement type)) {
                continue;
            }

            System.out.println("TYPE "
                    + type.getQualifiedName()
                    + " kind=" + type.getKind());

            for (VariableElement field :
                    ElementFilter.fieldsIn(type.getEnclosedElements())) {
                System.out.println("FIELD "
                        + field.getSimpleName()
                        + " type=" + field.asType());
            }

            for (ExecutableElement ctor :
                    ElementFilter.constructorsIn(type.getEnclosedElements())) {
                System.out.println("CONSTRUCTOR parameters="
                        + ctor.getParameters().size());
            }

            for (ExecutableElement method :
                    ElementFilter.methodsIn(type.getEnclosedElements())) {

                System.out.println("METHOD "
                        + method.getSimpleName()
                        + " returns=" + method.getReturnType());

                for (VariableElement parameter : method.getParameters()) {
                    System.out.println("PARAMETER "
                            + parameter.getSimpleName()
                            + " type=" + parameter.asType());
                }
            }
        }

        return true;
    }
}
```

Explanation:

- `@SupportedAnnotationTypes("lesson.Inspect")` specifies the annotation type that the processor handles.
- `@SupportedSourceVersion(RELEASE_17)` declares the supported language version.
- `roundEnv.getElementsAnnotatedWith(Inspect.class)` returns the `Element` instances directly annotated with `@Inspect` in the applicable processing round.
- Check `instanceof TypeElement` to process only type declarations.
- `ElementFilter.fieldsIn(...)`, `constructorsIn(...)`, and `methodsIn(...)` filter elements by kind, avoiding indiscriminate casting.
- `getParameters()` returns the `VariableElement` instances of a method or constructor.
- Returning `true` means the processor has claimed the annotation it supports in this processing round. The `processingOver()` state prevents printing extra data when the processing rounds end.

`@Retention(SOURCE)` is sufficient for the processor to work because it runs during compilation. You do not need to use `RUNTIME` to read annotations with `RoundEnvironment`.

### File 2 — `lesson/Invoice.java`

```java
package lesson;

@Inspect
class Invoice {
    private final String code;

    Invoice(String code) {
        this.code = code;
    }

    int total(int quantity, int unitPrice) {
        return quantity * unitPrice;
    }
}
```

In this example:

- `Invoice` → a `TypeElement` of kind `CLASS`.
- `code` (field) → `VariableElement` of kind `FIELD`, type `java.lang.String`.
- `Invoice(String code)` → `ExecutableElement` of kind `CONSTRUCTOR`, with one parameter.
- `total(int quantity, int unitPrice)` → `ExecutableElement` of kind `METHOD`, return type `int`.
- `quantity` and `unitPrice` → two `VariableElement` instances of kind `PARAMETER`, both of type `int`.

### Compilation and Output

Run the following commands from the `project` directory (the parent of the `lesson` directory). With JDK 17 or newer, use `--release 17` to stay consistent with `RELEASE_17`:

```bash
javac --release 17 -encoding UTF-8 lesson/InspectProcessor.java
javac --release 17 -encoding UTF-8 -cp . -processorpath . -processor lesson.InspectProcessor lesson/Invoice.java
```

The first command compiles the processor and the `Inspect` annotation. The second command explicitly invokes the processor via `-processor lesson.InspectProcessor` and then compiles `Invoice`. The program **has no `main`** because the goal is to observe the annotation processor's output at the **compilation stage**.

**Lines printed by the processor (stdout of the second compilation step):**

```text
TYPE lesson.Invoice kind=CLASS
FIELD code type=java.lang.String
CONSTRUCTOR parameters=1
METHOD total returns=int
PARAMETER quantity type=int
PARAMETER unitPrice type=int
```

The output above does not depend on running `java lesson.Invoice` (the `Invoice` class has no `main`). These are print statements from the `process(...)` method as the compiler traverses the declaration model.

The output order is stable because the processor deliberately prints in three separate groups: fields, constructors, and methods. Within each group in this example there is only one declaration, and the method has only two parameters in order. For large classes, if you need ordering independent of the compiler/source, explicitly sort the element lists using clear criteria.

### Walking Through the Processor Step by Step

1. The compiler recognizes `@Inspect` on `Invoice` and provides the corresponding `Element` via `RoundEnvironment`.
2. `element instanceof TypeElement` confirms the candidate is a **type declaration**.
3. `type.getQualifiedName()` prints `lesson.Invoice` and `type.getKind()` prints `CLASS`.
4. `ElementFilter.fieldsIn(...)` retains the field `code`; `field.asType()` prints `java.lang.String`.
5. `ElementFilter.constructorsIn(...)` retrieves the explicitly declared constructor, which has exactly one parameter `code`.
6. `ElementFilter.methodsIn(...)` retrieves the method `total`; `getReturnType()` is `int`.
7. `method.getParameters()` returns `quantity` and `unitPrice`, which are also `VariableElement` instances; their corresponding `asType()` returns `int`.

If you remove `@Inspect` from `Invoice`, the processor can still be invoked because `-processor` was specified, but `roundEnv.getElementsAnnotatedWith(Inspect.class)` will no longer contain `Invoice`. In a specific processor configuration, you cannot infer from “the processor is registered” that every class is a target: **the set of annotated elements and the candidate-selection policy are two things that must be distinguished**.

## 7. Choosing the Right API Based on the Analysis Goal

Suppose you are writing a checker tool: “Every method with `@Endpoint` must have a `requestId` parameter of type `String`.” An appropriate approach in annotation processing is:

1. Retrieve the elements annotated with `@Endpoint` from `RoundEnvironment`.
2. Check `getKind() == ElementKind.METHOD` before casting to `ExecutableElement`.
3. Iterate over `ExecutableElement.getParameters()`.
4. For each `VariableElement`, read `getSimpleName()` and `asType()`.
5. If violated, emit a diagnostic attached to the exact element using `processingEnv.getMessager().printMessage(...)`.

If you must distinguish two Java types **semantically** (for example generics, assignability, or subtypes), do not just compare `typeMirror.toString()` strings. Use `Types.isSameType(...)`, `Types.isAssignable(...)`, or the appropriate methods in `processingEnv.getTypeUtils()`. String-formatted type names are very useful for lessons, but they are not always a reliable type comparator in real-world processors.

### How Do `Elements`, `Types`, and `ElementFilter` Differ?

| Tool | Primary Function | Use Cases |
| --- | --- | --- |
| `Elements` | Looks up and assists in working with `Element` declarations | Finding a `TypeElement` by name, retrieving package or documentation info |
| `Types` | Analyzes and compares `TypeMirror` | Checking assignability, subtype relationships, type conversions |
| `ElementFilter` | Filters an `Element` collection into specialized groups | Extracting fields, methods, constructors from `getEnclosedElements()` |

These APIs complement one another. `TypeElement` indicates the **declaration object**, `TypeMirror` represents the **type**, and `Elements`/`Types` are **query helper tools**.

## 8. AnnotationMirror and Element Values at Compile Time

In the Java annotation module, besides knowing which class/method/field is marked, a processor also needs to read **the values of the annotation**. `Element.getAnnotationMirrors()` provides `AnnotationMirror` instances describing the annotations directly on the element.

You can use:

- `AnnotationMirror.getAnnotationType()` to determine the annotation type.
- `AnnotationMirror.getElementValues()` to receive a map from `ExecutableElement` (annotation element name) to `AnnotationValue`, with the values explicitly stated at the usage site.
- `processingEnv.getElementUtils().getElementValuesWithDefaults(mirror)` to retrieve the values **including defaults** of the annotation elements.

Conceptual example:

```java
@interface Policy {
    int retries() default 2;
}

@Policy
class Example {}
```

In the compiler, `retries()` of the `Policy` annotation is an **`ExecutableElement`**; the default `2` can be read via that executable's `getDefaultValue()`. For `@Policy` on `Example`, `AnnotationMirror.getElementValues()` does not have an explicit `retries` value, whereas `Elements.getElementValuesWithDefaults(...)` can provide the value `2`.

**Note:** `ExecutableElement.getDefaultValue()` refers to the **element definition**, whereas `Elements.getElementValuesWithDefaults(...)` refers to **how a specific annotation is used after accounting for defaults**.

This operates on the **compile-time model**, which differs from `java.lang.reflect.Method` and proxy annotations read at runtime. A processor does not need `@Retention(RUNTIME)` just to see an annotation at compile time.

## 9. Common Pitfalls When Writing an Annotation Processor

### Confusing `Element` with Reflection

`TypeElement` is not `Class<?>`. `ExecutableElement` is not `java.lang.reflect.Method`. `VariableElement` is not `java.lang.reflect.Field`. A processor inspects the source/compile-time model, so avoid loading the class being compiled with `Class.forName(...)` as a substitute — that class might not exist yet or might be an old version on the classpath.

### Casting Every `Element` to `TypeElement`

`RoundEnvironment.getElementsAnnotatedWith(...)` returns the kinds of `Element` matching the annotation and target. An annotation can be attached to a method, field, or parameter. If you always cast to `TypeElement`, the processor can easily cause a `ClassCastException`. Check `ElementKind` or use `instanceof`.

### Treating `VariableElement` Only as a Field

Method/constructor parameters are also `VariableElement`, and enum constants belong to this group as well. Use `getKind()` and `getEnclosingElement()` to tell them apart.

### Treating Constructors as Ordinary Methods

Both are described by `ExecutableElement`, but their `getKind()` differs. If you only want to process methods, use `ElementFilter.methodsIn(...)` instead of processing constructors too.

### Treating `getEnclosedElements()` as the Entire AST

This API describes **the declarations enclosed in an element**, not every statement and expression inside a method body. For local variables and method body contents, appropriate AST tools are required.

### Comparing `TypeMirror` via Strings

`toString()` is very useful for display, but type checking needs to account for generics, wildcards, boxing, subtypes, or erroneous types being compiled; use `Types` instead of just string comparison.

### Forgetting Multiple Processing Rounds

Annotation processing can run across multiple **rounds** when a processor generates additional source files. `process(...)` can be called multiple times. Pay attention to `roundEnv.processingOver()` and `roundEnv.errorRaised()`, and avoid printing/generating the same file multiple times when designing a real processor.

### Forgetting That `SOURCE` Can Still Be Processed at Compile Time

`@Retention(SOURCE)` does not make an annotation invisible to a processor during compilation. Retention only determines whether the metadata persists to bytecode/runtime.

### Choosing the Wrong Element to Report Errors

If a rule violation is on the `quantity` parameter, emit a diagnostic attached to that `VariableElement`; if the error belongs to the entire class declaration, attach it to the `TypeElement`. Identifying the right element kind helps the compiler/IDE report the error at a clear location.

## 10. Self-Check Exercises

**Question 1.** In `class User { String id; }`, which interfaces correspond to the class and the field?

**Answer:** `User` is a `TypeElement` (kind `CLASS`); `id` is a `VariableElement` (kind `FIELD`).

**Question 2.** Which elements make up `void save(String name)`?

**Answer:** `save` is an `ExecutableElement` (kind `METHOD`), while `name` is a `VariableElement` (kind `PARAMETER`). The `String` type of `name` is represented by a `TypeMirror` from `name.asType()`.

**Question 3.** When processing `@interface Marker { int level() default 4; }`, what are `Marker` and `level()`?

**Answer:** `Marker` is a `TypeElement` (kind `ANNOTATION_TYPE`), and `level()` is an `ExecutableElement` (kind `METHOD`). `level.getDefaultValue()` represents the default `4`.

**Question 4.** Why is `Class<?> c = Class.forName("lesson.Invoice")` not a reliable replacement for `TypeElement` in a processor?

**Answer:** The processor may be analyzing the `Invoice` source before the class file is compiled. Reflection loads a runtime class already present on the classpath and may not match the declaration currently being processed.

**Question 5.** If you want to get the parameter list of a method already represented as an `ExecutableElement`, what do you call?

**Answer:** `method.getParameters()`; the results are `VariableElement` instances and preserve the formal parameter order.

**Question 6.** Why is `getDeclaredMethods()` on `Class<?>` not the standard approach for listing methods currently being compiled by a processor?

**Answer:** That is runtime Reflection. A processor must use `TypeElement.getEnclosedElements()` and filter with `ElementFilter.methodsIn(...)` or check `ElementKind.METHOD`.

**Question 7.** Can `VariableElement.getConstantValue()` read the current value of a `private int counter` field in an instance?

**Answer:** No. It only provides a compile-time constant under qualifying conditions; it does not access runtime instance state.

**Question 8.** A processor wants to check whether `List<String>` is assignable to another type. Should it choose `Elements` or `Types`?

**Answer:** `Types` with its comparison/assignability methods on `TypeMirror` is appropriate. `Elements` serves declarations and element-related utilities.

**Question 9.** Does `@Retention(SOURCE)` prevent `roundEnv.getElementsAnnotatedWith(Inspect.class)` from finding the `Invoice` class during compilation?

**Answer:** No. The processor operates at compile time, so SOURCE annotations can still be observed, provided the processor is registered and the annotation type/target are correct.

**Question 10.** If `@Policy` does not specify `retries` while the element has `default 2`, which compile-time API retrieves the values including defaults?

**Answer:** `Elements.getElementValuesWithDefaults(annotationMirror)`. Meanwhile, `ExecutableElement.getDefaultValue()` directly reads the default of the `retries()` element in the annotation type definition.

## 11. Rules to Remember

**`TypeElement` = type declaration; `ExecutableElement` = executable declaration (method/constructor/annotation element); `VariableElement` = variable declaration (field/parameter/enum constant...).** All three belong to `javax.lang.model.element`, provided by the compiler to the annotation processor. Use `ElementKind` to verify the element type, `getEnclosedElements()` to traverse the declaration structure, `getParameters()` for parameters, `asType()`/`TypeMirror` for type information, and `ElementFilter` for safe filtering.

When moving from **compile time** to **runtime**, switch to the right mental model: Java Reflection uses `Class`, `Method`, and `Field` to inspect existing classes; it does not replace the interfaces of `javax.lang.model` in annotation processing.
