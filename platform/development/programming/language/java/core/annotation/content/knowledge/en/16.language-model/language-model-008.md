# Visitors and Structured Traversal of the Language Model in Java Annotation Processing

When writing an annotation processor, reading a few annotated classes with `RoundEnvironment.getElementsAnnotatedWith(...)` is only the first step. A class also has fields, methods, constructors, parameters, nested types, and generic parameters; each type has a different structure: `List<String>`, `Map<K,V>`, arrays, wildcards `? extends Number`, etc. To analyze them accurately, we need **structured traversal of the language model** instead of converting everything into strings and splitting them with `split`.

Java provides the Visitor API in the `java.compiler` module, particularly in the packages:

- `javax.lang.model.element`: **declaration elements** (*elements*) such as classes, methods, fields, and packages.
- `javax.lang.model.type`: **types** (*types*) such as `DeclaredType`, `ArrayType`, `WildcardType`, and `TypeVariable`.
- `javax.lang.model.util`: visitors and utilities such as `ElementScanner14`, `SimpleElementVisitor14`, `SimpleTypeVisitor14`, `ElementFilter`, `Elements`, and `Types`.

In a processor, **`ElementVisitor` handles the kinds of declaration elements**, while **`TypeVisitor` handles the kinds of type structures**. The two visitor hierarchies are related but do not replace each other.

## 1. Two Different Trees: `Element` and `TypeMirror`

Example Java input:

```java
@InspectMe
class Customer {
    String name;
    java.util.List<? extends Number> scores;

    int count() {
        return scores.size();
    }
}
```

This can be viewed from two perspectives.

**Declaration tree** (`Element`s):

```text
TypeElement Customer
├─ VariableElement name       (FIELD)
├─ VariableElement scores     (FIELD)
└─ ExecutableElement count    (METHOD)
```

The actual compiler structure may also include constructors, type parameters, and elements added by the language/compiler. The diagram above **only illustrates the key hand-written declarations**, not an assertion that `getEnclosedElements()` will return exactly three nodes.

**Type structure tree** of the `scores` field (`TypeMirror`s):

```text
DeclaredType List<? extends Number>
└─ WildcardType ? extends Number
   └─ DeclaredType Number
```

Differences:

| Question | Appropriate Model |
| --- | --- |
| What fields does a class have? | `TypeElement.getEnclosedElements()` and `ElementVisitor`. |
| Is an element a field or a method parameter? | `Element.getKind()` or the visitor's `visitVariable(...)`. |
| What type does a method return? | `ExecutableElement.getReturnType()` to get a `TypeMirror`. |
| What is argument 0 of `List<? extends Number>`? | `DeclaredType.getTypeArguments()` and then `TypeVisitor`. |
| What type is the bound of `? extends Number`? | `WildcardType.getExtendsBound()`. |
| What annotations are on the declaration? | `Element.getAnnotationMirrors()`. |
| What type annotations are at a type-use position? | `TypeMirror.getAnnotationMirrors()` on the corresponding node. |

**Do not confuse this with Java Reflection.** The `javax.lang.model.*` APIs model the program **at compile time**; they do not require loading and running the input classes. `java.lang.reflect.*`, on the other hand, is used for the metadata of classes loaded at runtime. They are two different worlds, even though they share many similar terms.

## 2. The Visitor Pattern: Calling the Right Method by Node Type

`Element` has the method:

```java
<R, P> R accept(ElementVisitor<R, P> visitor, P parameter);
```

Similarly, `TypeMirror` has:

```java
<R, P> R accept(TypeVisitor<R, P> visitor, P parameter);
```

When calling `element.accept(visitor, context)`, the language model dispatches to the appropriate method of the visitor, such as:

- `visitType(TypeElement, P)` for a class/interface/enum/record declaration.
- `visitExecutable(ExecutableElement, P)` for a method/constructor.
- `visitVariable(VariableElement, P)` for a field, parameter, or enum constant.
- `visitTypeParameter(TypeParameterElement, P)` for a generic parameter.
- `visitDeclared(DeclaredType, P)` for a declared type.
- `visitArray(ArrayType, P)` for an array type.
- `visitWildcard(WildcardType, P)` for a wildcard.

The two groups of `visit...` names above belong to **two different visitor interfaces**. If you manually write a series of `instanceof` checks, the code easily becomes verbose and hard to extend. Visitors leverage the dispatch mechanism provided by `Element`/`TypeMirror`; however, a visitor **does not decide every edge to traverse on its own**.

Commonly used generic parameters:

- `R`: the **result** type returned by the visit operation. If only printing or collecting into an external structure, use `Void`.
- `P`: the type of **additional context** passed along the traversal path. For example, using a `String` containing the path `"scores.arg0.extends"`, a `Context` object, or `Void` if not needed.

For example, `SimpleTypeVisitor14<Void, String>` has `R=Void`, `P=String`. This is a statically typed dispatch model, not Reflection into internal implementation classes.

## 3. Three Main Helper Groups for `ElementVisitor`

### `AbstractElementVisitor...`

`AbstractElementVisitor9` and classes in the same family help create a visitor by forcing you to decide how to handle the supported element kinds. It is useful when strict control is needed, though you may have to override many methods depending on the version level and the structures to support.

### `SimpleElementVisitor...`

`SimpleElementVisitor14<R, P>` provides default behavior for element kinds: if a specific method is not overridden, the logic goes through `defaultAction(...)`. For example, it is used to **classify a node** without automatically scanning child elements.

```java
import javax.lang.model.element.Element;
import javax.lang.model.element.TypeElement;
import javax.lang.model.util.SimpleElementVisitor14;

class NameVisitor extends SimpleElementVisitor14<String, Void> {
    @Override
    public String visitType(TypeElement type, Void ignored) {
        return type.getQualifiedName().toString();
    }

    @Override
    protected String defaultAction(Element element, Void ignored) {
        return element.getSimpleName().toString();
    }
}
```

This is an **illustrative helper class snippet**, without `main`. It resolves a `TypeElement` to its qualified name and other elements to their simple names. `SimpleElementVisitor14` **is not an automatic deep traverser**; to traverse children, the code additionally calls the appropriate API.

### `ElementScanner...`

`ElementScanner14<R, P>` is designed for **traversing child elements** with certain default strategies. For instance, `visitType` scans the elements enclosed in the type; `visitExecutable` scans the parameters of the executable. When overriding, you can call `super.visitType(...)` to preserve the downward traversal behavior.

```java
@Override
public Void visitType(TypeElement type, Void ignored) {
    System.out.println("type=" + type.getSimpleName());
    return super.visitType(type, ignored); // Continue to child elements.
}
```

If you **do not** call `super.visitType(...)` or do not call `scan(...)` yourself, the child traversal provided by the scanner's `visitType` method will not occur. This is a very common mistake when the author only cares about the logic at the parent node.

In JDK 17, the visitor group has variants by source version: for example, `ElementScanner9` suits constructs up to Java 9, whereas `ElementScanner14` handles `record` components that appeared later. When writing a processor that needs to support Java 17 records, you should use the visitor version with the corresponding methods rather than expecting an older visitor to automatically understand every new `ElementKind`.

## 4. Starting from `RoundEnvironment` and the Roots

In an annotation processor, `process` receives the inputs:

```java
@Override
public boolean process(Set<? extends TypeElement> annotations,
                       RoundEnvironment roundEnv) {
    if (roundEnv.processingOver()) {
        return true;
    }

    for (TypeElement annotationType : annotations) {
        for (Element target :
                roundEnv.getElementsAnnotatedWith(annotationType)) {
            new MyScanner().scan(target);
        }
    }
    return true;
}
```

This is a **snippet to place inside a processor** with `MyScanner` defined by yourself. `roundEnv.getElementsAnnotatedWith(annotationType)` finds the elements bearing the annotation being processed in the **current round**. `roundEnv.getRootElements()` is another set of entry points when you want to traverse the roots of the round without restricting to a specific annotation.

Several details to understand accurately:

1. The `annotations` set contains **the annotation types assigned to the processor in this round**, not a collection of runtime annotation objects.
2. `getRootElements()` reflects the **current round**, not by default every class in the project across every round.
3. A processor can be invoked across multiple rounds when processors generate additional sources/classes. You should not assume `process` is called only once.
4. `ElementScanner` traverses from **the node passed into `scan`**, and does not automatically discover all dependencies and superclasses in the project.
5. If `return true` is used, the processor claims the received annotation types; `true` does not mean compilation succeeded.

To retrieve metadata from a root type: use `TypeElement` and its child elements, rather than needing `Class.forName(...)` to load the class being compiled. The source class may not even have bytecode to load yet.

## 5. Structured Traversal with `ElementScanner14`

A declaration scanner can do the following:

```java
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.TypeElement;
import javax.lang.model.element.VariableElement;
import javax.lang.model.util.ElementScanner14;

final class FieldScanner extends ElementScanner14<Void, Void> {
    @Override
    public Void visitType(TypeElement type, Void ignored) {
        System.out.println("type=" + type.getSimpleName());
        return super.visitType(type, ignored);
    }

    @Override
    public Void visitVariable(VariableElement variable, Void ignored) {
        if (variable.getKind() == ElementKind.FIELD) {
            System.out.println("field=" + variable.getSimpleName());
        }
        return super.visitVariable(variable, ignored);
    }
}
```

This is an **illustrative helper class**, without `main`. Why check `ElementKind.FIELD` inside `visitVariable`? Because the same `VariableElement` type also represents **method parameters, constructor parameters, enum constants, and several other variable kinds**. Being dispatched to `visitVariable` **does not by itself prove that the element is a field**.

When scanning a class, `super.visitType(...)` causes the scanner to continue descending into enclosed declarations. `super.visitVariable(...)` preserves the default mechanism at the variable node. If you only need the **direct** fields of a class, a recursive scanner is not needed:

```java
java.util.List<VariableElement> directFields =
        javax.lang.model.util.ElementFilter.fieldsIn(
                type.getEnclosedElements()
        );
```

Using `ElementFilter` is simple and does not visit nested types. When you need to inspect an entire tree of nested classes or handle elements differently by element kind, a scanner is clearer. If **inherited** members are needed, you must consider `Elements.getAllMembers(type)` and inheritance semantics; `getEnclosedElements()` by itself does not traverse superclasses.

## 6. `TypeVisitor`: Traversing Type Structures Without String Parsing

From a field `VariableElement`:

```java
TypeMirror type = variable.asType();
```

`TypeMirror` represents the **type** of the element, unlike `Element` which represents the **declaration**. Although `variable.asType().toString()` may print `"java.util.List<? extends java.lang.Number>"`, this string **is not a stable parsing API** for type analysis.

Branches that typically need to be handled:

| `TypeMirror` Subtype | Methods to Retrieve Structural Parts |
| --- | --- |
| `DeclaredType` | `getTypeArguments()`, `asElement()`, `getEnclosingType()` |
| `ArrayType` | `getComponentType()` |
| `WildcardType` | `getExtendsBound()`, `getSuperBound()`; may be `null` |
| `TypeVariable` | `getUpperBound()`, `getLowerBound()`, `asElement()` |
| `IntersectionType` | `getBounds()` |
| `UnionType` | `getAlternatives()` |
| `ExecutableType` | `getReturnType()`, `getParameterTypes()`, `getThrownTypes()`, `getTypeVariables()` |
| `PrimitiveType` | Rely on `getKind()` if you need to distinguish `INT`, `BOOLEAN`, etc. |

A nested generic type like `Map<String, List<? extends Number>>` requires traversing through the `DeclaredType` of `Map`, the second argument `List`, the wildcard, and the upper bound `Number`. **Merely getting `asElement()` of `Map` does not reveal the arguments `String` or `List<? extends Number>`**.

With `SimpleTypeVisitor14<R, P>`, you can override the necessary branches, for example:

```java
@Override
public Void visitDeclared(DeclaredType type, String path) {
    for (int i = 0; i < type.getTypeArguments().size(); i++) {
        type.getTypeArguments().get(i)
            .accept(this, path + ".arg" + i);
    }
    return null;
}
```

`SimpleTypeVisitor14` handles dispatch by kind, but **does not automatically traverse all generic arguments**: that is the decision of the method you override. Thus, **ElementScanner** comes with a child-scanning step for the element model built into certain `visit...` methods; whereas **SimpleTypeVisitor** mainly provides default behavior by kind, and traversing into child `TypeMirror`s requires explicit code.

## 7. Complete Java 17 Example: Element Scanner Combined with a Type Visitor

The following example reads a class marked with `@InspectMe`, and prints the class name, fields, and **type tree** of each field. Everything uses standard JDK APIs, requiring no external libraries.

We prepare **three source files** in the same directory.

### File `InspectMe.java`

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface InspectMe {
}
```

`SOURCE` is appropriate: the processor observes the annotation during compilation, without needing runtime reflection.

### File `ModelWalkerProcessor.java`

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
import javax.lang.model.element.VariableElement;
import javax.lang.model.type.DeclaredType;
import javax.lang.model.type.TypeMirror;
import javax.lang.model.type.WildcardType;
import javax.lang.model.util.ElementScanner14;
import javax.lang.model.util.SimpleTypeVisitor14;

@SupportedAnnotationTypes("InspectMe")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class ModelWalkerProcessor extends AbstractProcessor {

    private static final class PrintType extends SimpleTypeVisitor14<Void, String> {
        @Override
        public Void visitDeclared(DeclaredType type, String path) {
            System.out.println(
                    path + ".declared=" + type.asElement().getSimpleName());

            for (int i = 0; i < type.getTypeArguments().size(); i++) {
                TypeMirror argument = type.getTypeArguments().get(i);
                argument.accept(this, path + ".arg" + i);
            }
            return null;
        }

        @Override
        public Void visitWildcard(WildcardType type, String path) {
            System.out.println(path + ".wildcard");

            TypeMirror upper = type.getExtendsBound();
            TypeMirror lower = type.getSuperBound();

            if (upper != null) {
                upper.accept(this, path + ".extends");
            }
            if (lower != null) {
                lower.accept(this, path + ".super");
            }
            return null;
        }
    }

    private static final class PrintElements extends ElementScanner14<Void, Void> {
        private final PrintType types = new PrintType();

        @Override
        public Void visitType(TypeElement type, Void unused) {
            System.out.println("type=" + type.getSimpleName());
            return super.visitType(type, unused);
        }

        @Override
        public Void visitVariable(VariableElement variable, Void unused) {
            if (variable.getKind() == ElementKind.FIELD) {
                String path = variable.getSimpleName().toString();
                System.out.println("field=" + path);
                variable.asType().accept(types, path);
            }
            return super.visitVariable(variable, unused);
        }
    }

    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment roundEnv) {
        if (roundEnv.processingOver()) {
            return true;
        }

        for (TypeElement annotationType : annotations) {
            for (Element element :
                    roundEnv.getElementsAnnotatedWith(annotationType)) {
                if (element instanceof TypeElement type) {
                    new PrintElements().scan(type);
                }
            }
        }
        return true;
    }
}
```

The methods have different roles:

- `process` only selects elements annotated with `@InspectMe`.
- `PrintElements.scan(type)` initiates scanning the declaration tree, thanks to `ElementScanner14`.
- `visitType` prints the class name, then calls `super.visitType` to continue scanning its members.
- `visitVariable` handles only `FIELD`, without confusing parameters or enum constants.
- `variable.asType().accept(types, path)` transitions from the **element** to the **type model**.
- `PrintType.visitDeclared` prints the declared type name and then descends into **the generic arguments**.
- `PrintType.visitWildcard` prints the wildcard marker and proceeds into the bounds if present.

This is a **read-only** processor that does not generate sources, does not invoke the application, and does not use runtime Reflection to analyze the input class.

### File `Customer.java`

```java
@InspectMe
public class Customer {
    String name;
    java.util.List<? extends Number> scores;
}
```

### Commands to Compile/Run the Processor

Open a terminal in the directory containing the three files. First, compile the annotation type and the processor so that `javac` can load the existing processor:

```bash
javac -encoding UTF-8 InspectMe.java ModelWalkerProcessor.java
```

Then invoke the processor explicitly:

```bash
javac -encoding UTF-8 -cp . -processorpath . \
    -processor ModelWalkerProcessor -proc:only Customer.java
```

In `bash`, the `\` character continues the command onto the next line. If using PowerShell/cmd, put the command on **a single line**:

```powershell
javac -encoding UTF-8 -cp . -processorpath . -processor ModelWalkerProcessor -proc:only Customer.java
```

**Expected lines printed by the processor to `stdout`:**

```text
type=Customer
field=name
name.declared=String
field=scores
scores.declared=List
scores.arg0.wildcard
scores.arg0.extends.declared=Number
```

Analysis:

1. `Customer` is marked with `@InspectMe`, so it appears in the result of `getElementsAnnotatedWith(...)`.
2. The scanner enters `visitType(Customer)` and prints the type name.
3. `String name` is the first field. `asType()` returns the type `String`, corresponding to the `DeclaredType` of `java.lang.String`.
4. `scores` has the type `java.util.List<? extends Number>`, corresponding to the `DeclaredType` of `List`.
5. The argument `scores.arg0` is a `WildcardType`, because the type argument is `? extends Number`.
6. `getExtendsBound()` returns the type `Number`, which is also a `DeclaredType`, producing the line `.extends.declared=Number`.
7. In the example, the processor filters for `FIELD`, so if the compiler includes an implicit constructor element, **it does not produce a `field=` line**.
8. The `-proc:only` option instructs `javac` to perform annotation processing without continuing to compile `Customer.class`; this is a structure-inspection example, not an application with `main` to run via `java Customer`.

The example is designed to have visual output; `System.out.println` is used for learning purposes. In a real-world processor, `Messager` is more appropriate for reporting NOTE/WARNING/ERROR with compiler integration.

## 8. Additionally Traversing Arrays, Type Variables, and Multiple Bounds

`PrintType` in the example only implements **two kinds**: `DeclaredType` and `WildcardType`. For the general case, you must continue adding overrides.

### Arrays with `visitArray`

If a field has the type `String[][]`, `variable.asType()` is the `ArrayType` of the outer array. Each call to `getComponentType()` strips **one level** of `[]`:

```java
@Override
public Void visitArray(javax.lang.model.type.ArrayType type, String path) {
    System.out.println(path + ".array");
    type.getComponentType().accept(this, path + ".component");
    return null;
}
```

This is an **additional method inside `PrintType`**, not a standalone program. When traversing `String[][]`, it can print `.array` twice (the outer array and then the inner array), followed by `.declared=String` for the element. `TypeVisitor` does not automatically step through array dimensions unless you write this recursive step.

### Type Variables with `visitTypeVariable`

A generic declaration:

```java
class Box<T extends Number> {
    T value;
}
```

`variable.asType()` of the `value` field is a `TypeVariable`. To navigate from `T` to its upper bound, you can override:

```java
@Override
public Void visitTypeVariable(
        javax.lang.model.type.TypeVariable type, String path) {
    System.out.println(path + ".variable=" +
            type.asElement().getSimpleName());
    type.getUpperBound().accept(this, path + ".upper");
    return null;
}
```

For `T extends A & B`, `getUpperBound()` can be an `IntersectionType`. To see each bound inside, also implement `visitIntersection` and call `getBounds()` on each `TypeMirror`.

### Intersection, Union, and Executable Types

```java
@Override
public Void visitIntersection(
        javax.lang.model.type.IntersectionType type, String path) {
    for (int i = 0; i < type.getBounds().size(); i++) {
        type.getBounds().get(i)
            .accept(this, path + ".bound" + i);
    }
    return null;
}
```

For a union type in a multi-catch (`IOException | SQLException`), handle `UnionType.getAlternatives()`. For a method type, `ExecutableType` allows reading the return type, parameter types, thrown types, and type variables.

A general-purpose traverser must define **its goal**: whether to analyze only field types, or also method signatures, constraints, superinterfaces, type parameters, and type annotations. Not every branch is needed for all processors.

### Beware of Recursive Cycles in Generics

For example, `T extends Comparable<T>` has self-reference. If you keep traversing from `TypeVariable T` into its upper bound `Comparable<T>`, then into the argument `T`, and repeat, the program can cause a `StackOverflowError`.

For a deep-traversing visitor handling real-world data, you should:

1. Track the type variables or structures currently on the **current traversal path**.
2. When encountering a node in a cycle again, record the reference instead of descending infinitely.
3. If only shallow information is needed (for example, the type argument name), stop at the exact level needed for the business logic.

`TypeMirror.toString()` is not a good substitute for cycle detection. You should rely on the semantics of `Types`, `Element`, and a visited set appropriate to your goal; storing every type name string as a unique key can mistakenly merge distinct type-use positions.

## 9. When to Use `ElementFilter`, Visitors, and Scanners?

| Need | Appropriate Choice |
| --- | --- |
| Only finding direct fields of a class | `ElementFilter.fieldsIn(type.getEnclosedElements())`. |
| Only getting direct methods | `ElementFilter.methodsIn(type.getEnclosedElements())`. |
| Handling only one kind of element, without needing child traversal | `SimpleElementVisitor14` or `switch(element.getKind())`. |
| Traversing a class and nested member declarations | `ElementScanner14` with the appropriate `super.visit...`. |
| Analyzing parameterized types, arrays, and wildcards | `SimpleTypeVisitor14` or a `TypeVisitor` with corresponding overrides. |
| Checking subtype or assignability | `processingEnv.getTypeUtils()` (`Types.isSubtype`, `isAssignable`, ...), without parsing `toString`. |
| Finding a declaration by canonical name | `processingEnv.getElementUtils().getTypeElement(...)` when appropriate. |
| Needing to analyze expressions, statements, or method bodies | `javax.lang.model` **is not a full AST**; with `javac`, look into `com.sun.source.util.Trees` or `TreePathScanner` if the goal is source syntax. |

A `javax.lang.model` visitor **is not synonymous with** an AST visitor. `ElementScanner` traverses the **declaration model**, and does not automatically expand every statement, `if`, loop, assignment, or expression inside a method body. `TypeVisitor` traverses **type structures**, does not execute methods, and does not fully infer all types at runtime.

## 10. Reading Annotations During Traversal

At compile time, both `Element` and `TypeMirror` objects can provide annotation metadata at the appropriate positions. Distinguish between them:

```java
element.getAnnotationMirrors();
typeMirror.getAnnotationMirrors();
```

- `Element.getAnnotationMirrors()` reads annotations on that **declaration**, such as `@InspectMe` on `Customer`.
- `TypeMirror.getAnnotationMirrors()` reads **type annotations** located at a type-use position, such as `List<@Marker String>`; you must navigate to the exact `String` node to read the type's annotation at that position.
- `AnnotationMirror` provides metadata in the compile-time model; there is no need to instantiate runtime annotation objects.

For example, if an annotation has an element with a default value:

```java
@Config(timeout = 1000)
class Endpoint {
}
```

A processor can read `AnnotationMirror.getElementValues()` to get the element pairs that were **explicitly written**. To also receive default values, use `processingEnv.getElementUtils().getElementValuesWithDefaults(mirror)`. The two APIs are not completely equivalent.

`AnnotationValue` has the method `accept(AnnotationValueVisitor<R,P>,P)`. When you need to handle multiple kinds of annotation values (primitives, strings, enum constants, type literals, nested annotations, arrays), you can use `SimpleAnnotationValueVisitor9`/the corresponding visitor family instead of relying on the value's `toString()`.

**Do not confuse** `AnnotationValueVisitor` with `ElementVisitor` or `TypeVisitor`: this third hierarchy handles **values inside annotations**. These three model layers help a processor select the right declaration, traverse the right type structure, and decode metadata accurately.

## 11. Passing Context and Building Results Instead of Only Printing

The example above passes `String path` through the `P` parameter of the type visitor. In real-world code, the context can be a Java 17 record:

```java
record VisitContext(String owner, String path, int depth) {
    VisitContext child(String segment) {
        return new VisitContext(owner, path + "." + segment, depth + 1);
    }
}
```

Then you can write a `SimpleTypeVisitor14<Result, VisitContext>` visitor to return a `Result` tree, accumulate warnings, or generate documentation from the type model.

Benefits of this approach:

- No need to use mutable static variables to track which class/field is currently being visited.
- Can pass the owner name, depth, configuration, and visited set explicitly along the traversal path.
- Easier to write unit tests by comparing result structures rather than matching log strings from the compiler.
- Allows multiple independent scan passes without unintentionally sharing state.

`R` is the type of the result data, and `P` is the context type. If the visitor has `R=Void`, returning `null` is correct; it is not a sign that processing failed.

One note: in `ElementScanner`, methods that scan multiple children **do not by default aggregate all results** into a list for you. If you want to collect multiple results, decide on an appropriate accumulator structure and processing order yourself.

## 12. Visitor Versions and Compatibility with Java 17+

The `javax.lang.model.util` API has multiple classes with version suffixes: `ElementScanner6`, `ElementScanner7`, `ElementScanner8`, `ElementScanner9`, `ElementScanner14`; similarly for `SimpleTypeVisitor...` and `SimpleElementVisitor...`. The suffixes indicate the processing semantics level of the visitor according to **the language constructs recognized at the corresponding version**.

You should not conclude that a processor automatically understands every new Java construct merely because it is running on a newer JDK. For example:

- Java 9 added several elements related to modules (`ModuleElement`).
- Java 14+ added support for record components in the language model.
- When an older visitor encounters a new `ElementKind`/`TypeKind`, it may fall back to `visitUnknown` or its superclass's compatibility behavior; you must not assume `visitType` can substitute for handling every new kind.
- Choose a visitor class recent enough for the source level you need, and define a clear strategy for handling unknown elements.

JDK 17 provides `ElementScanner14` and `SimpleTypeVisitor14`, so the example uses these two classes to handle modern Java code more easily than very old visitors. `@SupportedSourceVersion(SourceVersion.RELEASE_17)` on the processor describes the language version that the processor supports; it **does not automatically upgrade** how a visitor traverses new elements.

When upgrading the Java version, you should run a test suite with the new constructs (records, sealed classes, patterns...) and verify the metadata published by the compiler; do not infer from the API suffix name that every construct is already fully handled.

## 13. Common Mistakes

| Misconception | Correct Understanding |
| --- | --- |
| `ElementScanner` automatically traverses generic `List<? extends Number>` | The scanner traverses **element declarations**; generic arguments need to be traversed with `TypeVisitor`/`TypeMirror`. |
| `SimpleTypeVisitor` automatically descends into all arguments and bounds | It only dispatches by kind; to recurse, you must override and call `accept(...)` on children. |
| Overriding `visitType` while forgetting `super.visitType` | Loses the child-element scanning step provided by the scanner. |
| `visitVariable` is only called for fields | `VariableElement` also includes parameters, enum constants, etc.; you must inspect `ElementKind`. |
| Casting every `TypeMirror` to `DeclaredType` | Arrays, wildcards, type variables, primitives, unions, etc. require different branches. |
| `getEnclosedElements()` contains all inherited members | It only contains elements declared/enclosed at the current location; for inheritance, use the appropriate `Elements` model. |
| `getRootElements()` is always all sources across every round | Roots change per round; a newly generated file can become input for the next round. |
| Parsing `typeMirror.toString()` to look for `<`, `?`, `[]` | Unstable and error-prone with nested types, annotations, and complex generics; use the structured API. |
| Using `Class.forName(...)` to read the class being compiled | The class may not have bytecode generated yet; use `TypeElement` and `TypeMirror`. |
| Thinking `ElementVisitor` traverses the entire method body like an AST | No; to analyze the syntax tree, you need the appropriate `Trees`/`TreePathScanner` API. |
| Handling `T extends Comparable<T>` with infinite recursion | Detect cycles or bound traversal appropriately. |
| `Element.getAnnotationMirrors()` includes all type-use annotations deep inside generics | You must descend to the exact child `TypeMirror` and read the annotations at that corresponding position. |
| Believing `SimpleElementVisitor9` fully supports Java 17 records automatically | Choose the visitor with the matching version and test the new kinds. |

## 14. Self-Check Exercises

Given the following example (illustrative snippet only):

```java
class Container<K extends Number> {
    java.util.Map<String, java.util.List<? super K>> values;
}
```

Answer the following:

1. What kind of element is `Container`? **`TypeElement`**.
2. What kind of element is `values`? **`VariableElement` with `ElementKind.FIELD`**.
3. What kind of `TypeMirror` is `values.asType()`? **`DeclaredType`** of `Map`.
4. What is the second argument of `Map`? **Another `DeclaredType`**, `List<? super K>`.
5. What is the first argument of `List`? **`WildcardType`** with lower bound `K`.
6. What is the type of `K` in that lower bound? **`TypeVariable`**.
7. To find the upper bound of `K` at the generic declaration, what should you use? **The information from `TypeParameterElement.getBounds()` or `TypeVariable.getUpperBound()`**, and additionally handle intersection when there are multiple bounds.
8. Should you choose `ElementScanner` or `TypeVisitor` to extract the wildcard `? super K`? **`TypeVisitor`**, after obtaining the field's `TypeMirror` from the element.
9. When you only want to get direct fields, do you need to write a scanner yourself? **No**; you can use `ElementFilter.fieldsIn(type.getEnclosedElements())`.
10. To find annotations on the field declaration itself and annotations on the `String` argument, do you use the same single `getAnnotationMirrors()` call? **No**; you need to read the right `Element` or `TypeMirror` at each position.
11. Does the processor need `Container.class` to exist at runtime to read that generic? **No**; the processor works with the language model at compile time.

Remember the workflow: **select the right root `Element` → traverse the declaration tree with `ElementScanner` → where type analysis is needed, get `TypeMirror` → dispatch with `TypeVisitor` → handle annotation values with the `AnnotationMirror`/`AnnotationValue` APIs when necessary**. This organization allows a processor to analyze real code without inferring from printed type strings.

## Official Documentation

- [Java SE 17 — `ElementVisitor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/ElementVisitor.html)
- [Java SE 17 — `ElementScanner14`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/util/ElementScanner14.html)
- [Java SE 17 — `SimpleElementVisitor14`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/util/SimpleElementVisitor14.html)
- [Java SE 17 — `TypeVisitor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/type/TypeVisitor.html)
- [Java SE 17 — `SimpleTypeVisitor14`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/util/SimpleTypeVisitor14.html)
- [Java SE 17 — `ElementFilter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/util/ElementFilter.html)
