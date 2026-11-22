# Element, ElementKind, and Declaration Structure in Java Annotation Processing

## 1. The Language Model: Reading Java Declarations at Compile Time

When building an **annotation processor** with `javax.annotation.processing`, Java provides a language model in the `javax.lang.model` package. This model allows the compiler and processors to describe a class, interface, annotation type, record, field, method, constructor, parameter, type parameter, package, or module **without running the program**.

Three related but distinct concepts:

- **`Element`** (`javax.lang.model.element.Element`): represents **a declaration or program element** that can be represented by the language model, such as the class `User`, the method `save`, the parameter `id`, or the record component `name`.
- **`ElementKind`**: an enum that classifies the **declaration role** of an `Element`, for example `CLASS`, `METHOD`, `FIELD`, `PARAMETER`, `RECORD`.
- **`TypeMirror`** (`javax.lang.model.type.TypeMirror`): represents the associated **Java type**, for example `String`, `List<String>`, type variable `T`, primitive type `int`, or array `String[]`.

Mind map:

~~~text
Declaration model (javax.lang.model.element)
    Element
      +-- TypeElement           class / interface / enum / annotation / record
      +-- ExecutableElement     method / constructor
      +-- VariableElement       field / parameter / enum constant / ...
      +-- TypeParameterElement  declaration of T in class Box<T>
      +-- RecordComponentElement record component
      +-- PackageElement        package
      +-- ModuleElement         module

Type model (javax.lang.model.type)
    TypeMirror             String, T, int, List<String>, String[], ...
      +-- TypeKind          DECLARED, TYPEVAR, INT, ARRAY, ...
~~~

A method named `read` is an `Element` with `ElementKind.METHOD`; that method's return type `String` is a `TypeMirror`. **Do not confuse “which declaration?” with “which type?”**.

This API belongs to the **`java.compiler`** module, included in the JDK. The examples below use **Java 17+**, where records and record components are standard features.

## 2. Example Declaration Structure from a Java File

Consider the file `Demo.java`:

~~~java
package demo;

import java.lang.annotation.*;

@Retention(RetentionPolicy.SOURCE)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface Label {
    String value();
    String category() default "general";
}

@Label("box")
class Box<T> {
    private T value;

    Box(T value) {
        this.value = value;
    }

    @Label("reader")
    public T getOr(T fallback) {
        return value == null ? fallback : value;
    }

    static class Nested {}
}

record Pair(int left, int right) {}
~~~

Part of the declaration structure can be visualized as follows:

~~~text
package demo                             PACKAGE
├── annotation interface Label          ANNOTATION_TYPE
│   ├── value()                          METHOD
│   └── category() default "general"     METHOD
├── class Box<T>                         CLASS
│   ├── T                                TYPE_PARAMETER
│   ├── field value                      FIELD
│   ├── constructor Box(T)               CONSTRUCTOR
│   │   └── parameter value              PARAMETER
│   ├── method getOr(T)                   METHOD
│   │   └── parameter fallback           PARAMETER
│   └── nested class Nested              CLASS
└── record Pair(int left, int right)     RECORD
    ├── record component left            RECORD_COMPONENT
    └── record component right           RECORD_COMPONENT
~~~

This is a **conceptual diagram** focusing on the declarations relevant for learning, not an exact printout of all `getEnclosedElements()`. The compiler also represents corresponding **implicit/mandated members**, such as record accessors and constructors, default constructors when present, or generated members of an enum. The exact member set and where members appear depend on the declaration kind.

Some key relationships:

1. `Box` is a **`TypeElement`** with kind `CLASS`.
2. `T` in `Box<T>` is a **`TypeParameterElement`**, with kind `TYPE_PARAMETER`.
3. `value` is a **`VariableElement`** with kind `FIELD`.
4. `getOr` is an **`ExecutableElement`** with kind `METHOD`; the parameter `fallback` is a `VariableElement` with kind `PARAMETER`.
5. `Label` is a **`TypeElement`** with kind `ANNOTATION_TYPE`, while the `value()` and `category()` elements of the annotation type are modeled as **`ExecutableElement` with kind `METHOD`**.
6. `Pair` is a **`TypeElement`** with kind `RECORD`; `left` and `right` in the record header are **`RecordComponentElement`**, not `VariableElement` of kind `FIELD`.

**Consequence:** knowing the name of a declaration is not enough to decide how to handle it. You must check `getKind()` and use the appropriate subinterface.

## 3. `ElementKind`: Classifying the Exact Declaration Kind

`ElementKind` is an enum in `javax.lang.model.element`. Very commonly encountered values:

| `ElementKind` | Declaration / Construct Type | Commonly Used Specialized Interface |
|---|---|---|
| `PACKAGE` | Package | `PackageElement` |
| `MODULE` | Java module | `ModuleElement` |
| `CLASS` | Regular class | `TypeElement` |
| `INTERFACE` | Interface | `TypeElement` |
| `ENUM` | Enum type | `TypeElement` |
| `ANNOTATION_TYPE` | Annotation interface declared with `@interface` | `TypeElement` |
| `RECORD` | Record type | `TypeElement` |
| `FIELD` | Field | `VariableElement` |
| `ENUM_CONSTANT` | Enum constant | `VariableElement` |
| `METHOD` | Method, including element methods in an annotation interface | `ExecutableElement` |
| `CONSTRUCTOR` | Constructor | `ExecutableElement` |
| `PARAMETER` | Method/constructor parameter | `VariableElement` |
| `TYPE_PARAMETER` | Type variable declaration such as `T` | `TypeParameterElement` |
| `RECORD_COMPONENT` | Component declared in a record header | `RecordComponentElement` |
| `LOCAL_VARIABLE` | Local variable | `VariableElement` |
| `EXCEPTION_PARAMETER` | Exception-catching variable in `catch` | `VariableElement` |
| `RESOURCE_VARIABLE` | Resource variable declared in try-with-resources | `VariableElement` |
| `BINDING_VARIABLE` | Variable introduced by a pattern, e.g., `instanceof String s` | `VariableElement` |

The enum also includes specialized kinds such as `STATIC_INIT`, `INSTANCE_INIT`, and `OTHER`. The list may be expanded in newer Java versions, as the language can add new declaration constructs.

Example of safe branching:

~~~java
void inspect(Element element) {
    switch (element.getKind()) {
        case CLASS:
        case INTERFACE:
        case RECORD:
        case ENUM:
        case ANNOTATION_TYPE:
            TypeElement type = (TypeElement) element;
            System.out.println(type.getQualifiedName());
            break;
        case METHOD:
        case CONSTRUCTOR:
            ExecutableElement executable = (ExecutableElement) element;
            System.out.println(executable.getParameters().size());
            break;
        case FIELD:
        case PARAMETER:
            VariableElement variable = (VariableElement) element;
            System.out.println(variable.asType());
            break;
        default:
            // There are many other kinds: do not cast unconditionally.
            break;
    }
}
~~~

The snippet above illustrates handling each `kind`; to use it standalone, you need to import `javax.lang.model.element.*` and place the method in an appropriate class.

**Do not cast every `Element` to `TypeElement`** just because it has `getSimpleName()`. A `FIELD` is not a class; a `RECORD_COMPONENT` is not a field; a `PARAMETER` is not a method.

The methods `ElementKind.isClass()`, `isInterface()`, and `isField()` support certain groupings, but make sure to read each method's contract. For example, `RECORD` is treated as a class kind for classification purposes, while `ANNOTATION_TYPE` belongs to the interface group. When you need to distinguish a record from a regular class specifically, compare directly with `getKind() == ElementKind.RECORD`.

## 4. Common Operations via the `Element` Interface

Whether it is a package, type, field, or method, all `Element` objects support a set of common operations:

| API | Meaning | Notes |
|---|---|---|
| `getKind()` | Returns `ElementKind` | Use before casting down to a subinterface |
| `getSimpleName()` | Returns the `Name` of the declaration | `Name` supports `contentEquals(...)`; it is not necessarily a `String` |
| `getEnclosingElement()` | Returns the enclosing element | A method usually has an enclosing type; a parameter has an enclosing executable |
| `getEnclosedElements()` | Declarations contained within this element | **Not** synonymous with all inherited members |
| `getModifiers()` | Set of modifiers such as `PUBLIC`, `PRIVATE`, `STATIC` | Do not assume every kind supports the same group of modifiers |
| `getAnnotationMirrors()` | Annotation declarations modeled as `AnnotationMirror` | Can see annotations with `SOURCE` retention at compile time |
| `asType()` | Gets the corresponding Java type as a `TypeMirror` | A type is different from the declaration kind `ElementKind` |
| `accept(visitor, p)` | Allows an `ElementVisitor` to process by kind | Useful when multiple element kinds have distinct logic |

Example of isolated operations:

~~~java
Element e = /* obtain element from RoundEnvironment or Elements */;
System.out.println(e.getKind());
System.out.println(e.getSimpleName());
System.out.println(e.getEnclosingElement());
System.out.println(e.asType());
~~~

Note: the snippet above is an **API sample**, not a standalone Java program; the variable `e` must be obtained from the annotation processing environment.

### 4.1. Enclosing and Enclosed Relationships

- For a top-level class `demo.Box`, its `getEnclosingElement()` is **package `demo`**.
- For the method `Box.getOr`, the enclosing element is **`Box`**.
- For the parameter `fallback`, the enclosing element is **method `getOr`**.
- For the type parameter `T`, the enclosing element is the generic class or method that declares `T`.
- For the record component `Pair.left`, the enclosing element is the record `Pair`.
- For a `ModuleElement`, the enclosing element is `null`.

`getEnclosedElements()` is not a recursive call over the entire tree: to traverse deeply, you must visit each child. When you only need the fields or methods of a type, use `ElementFilter` to filter by kind instead of casting blindly.

### 4.2. Direct Declarations Differ from Inherited Members

For a `TypeElement`:

~~~java
List<? extends Element> direct = type.getEnclosedElements();
List<? extends Element> all = processingEnv.getElementUtils()
        .getAllMembers(type);
~~~

- `getEnclosedElements()` focuses on the **direct members and mandated elements** of that type.
- `Elements.getAllMembers(type)` retrieves **the members of the type, including inherited members** according to the Java model.
- **Do not** call `getEnclosedElements()` and conclude that a class has no inherited methods.

For source declarations, the API generally returns the list in natural source order, but **the ordering of implicit/mandated elements is not guaranteed as a fixed layout**. When writing tools, filter by kind and name rather than relying on an index such as `getEnclosedElements().get(2)`.

## 5. Specialized Interfaces and Essential Properties

### 5.1. `TypeElement`

`TypeElement` describes the **declaration** of a class, interface, enum, annotation interface, or record. Several important methods:

- `getQualifiedName()`: canonical name such as `demo.Box`, unlike `getSimpleName()`, which is `Box`.
- `getNestingKind()`: distinguishes top-level, member, local, and anonymous.
- `getTypeParameters()`: the `TypeParameterElement` instances of a generic class.
- `getSuperclass()`, `getInterfaces()`: the **TypeMirror** instances in the inheritance relationship.
- `getRecordComponents()`: the `RecordComponentElement` instances in the record header order (Java 16+).
- `getEnclosedElements()`: the members declared in the type, including associated mandated elements.

The qualified name does not necessarily hold a value like a top-level class in every context: local and anonymous classes do not have a canonical name suitable for use as a regular fully qualified name.

### 5.2. `ExecutableElement`

`ExecutableElement` describes a method or constructor. It provides:

- `getReturnType()`: the **TypeMirror** of the return type; constructors have a special return type according to the model.
- `getParameters()`: the list of **VariableElement** instances for each parameter.
- `getThrownTypes()`: the exception types declared in `throws`.
- `getTypeParameters()`: type parameters if the method or constructor is generic.
- `getDefaultValue()`: the default value if the element is a method declaring an element of an **annotation interface**; returns `null` if there is no default.
- `isVarArgs()` and `isDefault()`: identify varargs methods and default methods where applicable.

For example, `String category() default "general"` in `@interface Label` is an `ExecutableElement` of kind `METHOD`; `category.getDefaultValue()` describes the default value. **There is no separate kind named “ANNOTATION_ELEMENT” in Java 17's `ElementKind`.**

### 5.3. `VariableElement` and `TypeParameterElement`

`VariableElement` is used for fields, parameters, enum constants, and other variable kinds. It has `asType()`; `getConstantValue()` only returns a value for a **constant variable** of a primitive type or `String` that is initialized with a suitable constant expression.

`TypeParameterElement` is for a **type parameter declaration**, such as `T` in `Box<T>`; you can read `getBounds()` and the generic element that owns it. Do not confuse the declaration `T` with the type `T` used by the field `value`.

### 5.4. `RecordComponentElement` and the Two Different Surfaces of a Record

For `record Pair(int left, int right) {}`:

- `Pair` has kind `RECORD`.
- The two declarations in the header have kind `RECORD_COMPONENT`.
- `TypeElement.getRecordComponents()` returns the list of components in the order `left`, `right`.
- `RecordComponentElement.getAccessor()` returns the `ExecutableElement` for the corresponding accessor such as `left()`.
- The compiler also processes component fields and the canonical constructor; these constructs are **distinct declarations** with appropriate kinds such as `FIELD`, `METHOD`, and `PARAMETER`.

Important for annotation processing: an annotation with `@Target(RECORD_COMPONENT)` describes the component, which differs from an annotation targeting only `FIELD` or `METHOD`. Always query the exact element your tool intends to inspect.

### 5.5. `PackageElement` and `ModuleElement`

`PackageElement` represents a package, supporting `getQualifiedName()` and access to the types within the package according to the compiler model. `ModuleElement` represents a module, providing access to directives (`requires`, `exports`, `opens`, etc.) through its own API. Under the module system, a package or type name may require module context to resolve uniquely.

## 6. How Does `ElementKind` Differ from `TypeKind`?

This is the most easily confused pair of concepts.

For example, `private T value;` inside `class Box<T>`:

~~~java
VariableElement field = /* find the "value" field in Box */;
System.out.println(field.getKind());       // FIELD
System.out.println(field.asType());        // T
System.out.println(field.asType().getKind()); // TYPEVAR
~~~

The last line uses **`TypeKind.TYPEVAR`**, not `ElementKind.TYPE_PARAMETER`. Meaning:

- `FIELD`: the declaration is a field.
- `T` / `TYPEVAR`: the type of the field is a type variable.
- `TYPE_PARAMETER`: the kind of the **declaration `T`** in `Box<T>`.

Comparison:

| Question | API / Enum |
|---|---|
| Is this a class, a method, or a parameter? | `Element.getKind()` returns **ElementKind** |
| Is this a primitive `int`, an array, a declared type, or a type variable? | `TypeMirror.getKind()` returns **TypeKind** |
| What type does this method return? | `ExecutableElement.getReturnType()` → **TypeMirror** |
| What type does this field have? | `VariableElement.asType()` → **TypeMirror** |
| Which `T` parameters does the generic class declare? | `TypeElement.getTypeParameters()` → **TypeParameterElement** |

A `TypeElement` describes the **declaration `Box<T>`**; the type used at `Box<String>` is a `DeclaredType` with type argument `String`, not a new `TypeElement` for each parameterization. This model is also not synonymous with `java.lang.Class<?>` or runtime erasure.

When performing type checking, you can use `javax.lang.model.util.Types` (obtained from `processingEnv.getTypeUtils()`), such as `isSameType` or `isAssignable`; do not use `String.equals` on `TypeMirror.toString()` as the basis for type-system correctness.

## 7. Complete Hands-On Example: Annotation Processor Printing Declaration Structure

This exercise has **two source files** in the same directory: `ModelProcessor.java` (the annotation processor) and `Demo.java` (the declarations to analyze). All code is compatible with Java 17.

### 7.1. File `ModelProcessor.java`

~~~java
import java.util.Set;
import javax.annotation.processing.*;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.*;
import javax.lang.model.util.ElementFilter;
import javax.lang.model.util.Elements;

@SupportedAnnotationTypes("*")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class ModelProcessor extends AbstractProcessor {
    private boolean done;

    @Override
    public boolean process(Set<? extends TypeElement> annotations, RoundEnvironment round) {
        if (done || round.processingOver()) return false;
        done = true;

        Elements elements = processingEnv.getElementUtils();
        TypeElement box = elements.getTypeElement("demo.Box");
        TypeElement pair = elements.getTypeElement("demo.Pair");
        TypeElement label = elements.getTypeElement("demo.Label");

        System.out.println("box-kind=" + box.getKind());
        System.out.println("box-name=" + box.getQualifiedName());
        System.out.println("box-parent=" + box.getEnclosingElement().getKind());
        System.out.println("type-param-kind=" + box.getTypeParameters().get(0).getKind());

        VariableElement field = ElementFilter.fieldsIn(box.getEnclosedElements())
                .stream().filter(e -> e.getSimpleName().contentEquals("value"))
                .findFirst().orElseThrow();
        System.out.println("field-kind=" + field.getKind());
        System.out.println("field-type=" + field.asType());

        ExecutableElement getter = ElementFilter.methodsIn(box.getEnclosedElements())
                .stream().filter(e -> e.getSimpleName().contentEquals("getOr"))
                .findFirst().orElseThrow();
        System.out.println("method-kind=" + getter.getKind());
        System.out.println("method-return=" + getter.getReturnType());
        System.out.println("method-param-kind=" + getter.getParameters().get(0).getKind());
        System.out.println("method-param-type=" + getter.getParameters().get(0).asType());
        System.out.println("method-parent=" + getter.getEnclosingElement().getSimpleName());

        AnnotationMirror mirror = box.getAnnotationMirrors().get(0);
        System.out.println("declared-annotation=" + mirror.getAnnotationType());
        System.out.println("explicit-values=" + mirror.getElementValues().size());
        System.out.println("values-with-defaults="
                + elements.getElementValuesWithDefaults(mirror).size());

        System.out.println("record-kind=" + pair.getKind());
        System.out.println("record-components=" + pair.getRecordComponents().size());
        RecordComponentElement first = pair.getRecordComponents().get(0);
        System.out.println("record-component-kind=" + first.getKind());
        System.out.println("record-accessor=" + first.getAccessor().getSimpleName());

        System.out.println("annotation-kind=" + label.getKind());
        ExecutableElement category = ElementFilter.methodsIn(label.getEnclosedElements())
                .stream().filter(e -> e.getSimpleName().contentEquals("category"))
                .findFirst().orElseThrow();
        System.out.println("annotation-member-kind=" + category.getKind());
        System.out.println("annotation-default=" + category.getDefaultValue());
        return false;
    }
}
~~~

### 7.2. File `Demo.java`

~~~java
package demo;
import java.lang.annotation.*;

@Retention(RetentionPolicy.SOURCE)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface Label {
    String value();
    String category() default "general";
}

@Label("box")
class Box<T> {
    private T value;

    Box(T value) {
        this.value = value;
    }

    @Label("reader")
    public T getOr(T fallback) {
        return value == null ? fallback : value;
    }

    static class Nested {}
}

record Pair(int left, int right) {}
~~~

**Note:** `Label` has `SOURCE` retention. The annotation processor **still sees it during compilation**, even though this annotation will not be retained for Java runtime reflection queries after compilation.

### 7.3. Commands to Compile and Invoke the Processor

Run inside the directory containing the two files:

~~~bash
mkdir out
javac --release 17 -d out ModelProcessor.java
javac --release 17 -cp out -processorpath out -processor ModelProcessor -proc:only -d out Demo.java
~~~

In the first step, `javac` compiles `ModelProcessor` into a class in `out`. The second step specifies the processor with `-processor ModelProcessor`, puts it on the processor path, and runs annotation processing on `Demo.java`.

`-proc:only` requests **running annotation processing only, without generating regular class files for `Demo`**. If you need to build a runnable artifact, compile `Demo.java` separately without `-proc:only` or use an appropriate build configuration.

Output printed by the processor when using `javac --release 17`:

~~~text
box-kind=CLASS
box-name=demo.Box
box-parent=PACKAGE
type-param-kind=TYPE_PARAMETER
field-kind=FIELD
field-type=T
method-kind=METHOD
method-return=T
method-param-kind=PARAMETER
method-param-type=T
method-parent=Box
declared-annotation=demo.Label
explicit-values=1
values-with-defaults=2
record-kind=RECORD
record-components=2
record-component-kind=RECORD_COMPONENT
record-accessor=left
annotation-kind=ANNOTATION_TYPE
annotation-member-kind=METHOD
annotation-default="general"
~~~

### 7.4. Explanation of Key Outputs

- **`box-kind=CLASS`**, **`record-kind=RECORD`**, **`annotation-kind=ANNOTATION_TYPE`**: all use the `TypeElement` model, yet have different `ElementKind` values.
- **`box-parent=PACKAGE`**: the top-level class `demo.Box` is enclosed by package `demo`, not by another method or class.
- **`type-param-kind=TYPE_PARAMETER`**: `T` is a type parameter declaration.
- **`field-kind=FIELD`**, **`field-type=T`**: the field `value` is a field declaration with type `T`.
- **`method-kind=METHOD`**, **`method-return=T`**: the method `getOr` returns type `T`, not `ElementKind.TYPE_PARAMETER`.
- **`method-param-kind=PARAMETER`**, **`method-param-type=T`**: the parameter `fallback` is its own declaration with type `T`; its enclosing element is the method `getOr`.
- **`declared-annotation=demo.Label`**: the processor retrieves `Box`'s annotation as an `AnnotationMirror`, **without needing to load `Box`'s `java.lang.Class`**.
- **`explicit-values=1`**: the annotation `@Label("box")` provides only the `value` element explicitly.
- **`values-with-defaults=2`**: `Elements.getElementValuesWithDefaults` includes the `category` element with default `"general"`.
- **`record-component-kind=RECORD_COMPONENT`** and **`record-accessor=left`**: record components and accessors are separate models with specialized APIs.
- **`annotation-member-kind=METHOD`**, **`annotation-default="general"`**: the `category()` element of `@interface Label` has kind `METHOD` and holds a default value.

The example intentionally filters `field` and `method` by name via `ElementFilter`. The reason: you should not assume `getEnclosedElements()` contains only those two members or that the order of implicit members is always fixed.

### 7.5. Why Does the Example Print Only Once?

A processor can be invoked across **multiple annotation processing rounds**. The `done` flag prevents duplicate printing; the `round.processingOver()` condition avoids processing the final round.

`@SupportedAnnotationTypes("*")` means the processor accepts every annotation type in order to receive processing rounds in this demo. `return false` indicates that the processor **does not claim all annotations**, so other processors can still process them if needed.

In real-world projects, do not assume every symbol exists: `elements.getTypeElement("demo.Box")` can return `null` if the name/type cannot be resolved in the current environment. Production code should check for `null` and report errors via `processingEnv.getMessager().printMessage(...)`. In this demo, the two files are compiled together exactly as instructed, so the expected elements are present.

## 8. `RoundEnvironment`, `Elements`, and `ElementFilter` in the Processor Workflow

An annotation processor typically extends `AbstractProcessor` and overrides:

~~~java
@Override
public boolean process(Set<? extends TypeElement> annotations,
                       RoundEnvironment roundEnv) {
    for (Element root : roundEnv.getRootElements()) {
        // Find the top-level declarations belonging to this compilation round.
    }
    return false;
}
~~~

There are two common ways to locate elements:

**(A) From supported annotations:**

~~~java
for (Element element : roundEnv.getElementsAnnotatedWith(MyAnnotation.class)) {
    // Process only declarations with the target annotation.
}
~~~

**(B) From a name or declaration structure:**

~~~java
TypeElement type = processingEnv.getElementUtils()
        .getTypeElement("demo.Box");
~~~

These are two complementary strategies. `getElementsAnnotatedWith` is useful when a processor framework is designed around an annotation; `getTypeElement` is useful for resolving a type by name from the compiler environment.

`ElementFilter` provides helpers such as:

~~~java
var fields = ElementFilter.fieldsIn(type.getEnclosedElements());
var methods = ElementFilter.methodsIn(type.getEnclosedElements());
var constructors = ElementFilter.constructorsIn(type.getEnclosedElements());
var types = ElementFilter.typesIn(type.getEnclosedElements());
~~~

They **do not modify `getEnclosedElements()`**; they only filter elements by the appropriate kind. For record components, use `type.getRecordComponents()` or the helper for record components in Java 17.

### Visitor Instead of Long Branched Casts

If you have to handle many kinds, you can use `ElementVisitor` or utility classes such as `SimpleElementVisitor14` (`javax.lang.model.util`). Visitors provide extension points per element kind and help reduce hard-to-maintain `instanceof` chains. However, visitor versions are tied to the language version; when upgrading the JDK, check for the visitor class that supports newer kinds such as records.

## 9. Annotations in the `Element` Model: `AnnotationMirror` and Default Values

An `Element` supports:

~~~java
List<? extends AnnotationMirror> mirrors = element.getAnnotationMirrors();
~~~

`AnnotationMirror` represents an annotation being analyzed by the compiler. It has:

- `getAnnotationType()`: the annotation type as a `DeclaredType`.
- `getElementValues()`: a map from `ExecutableElement` (the annotation elements) to `AnnotationValue`; **includes only values explicitly specified** at the use site.
- `processingEnv.getElementUtils().getElementValuesWithDefaults(mirror)`: also retrieves elements that use the annotation interface's `default` values.

With `@Label("box")`:

~~~java
@interface Label {
    String value();
    String category() default "general";
}
~~~

The annotation has two elements at the API level, but only one is written at the use site:

~~~java
@Label("box")
class Box<T> {}
~~~

Therefore, `mirror.getElementValues().size()` is `1`, while `getElementValuesWithDefaults(mirror).size()` is `2`. This result was verified in the example above.

**Prefer `AnnotationMirror` in an annotation processor** when inspecting compile-time metadata, especially for `SOURCE` retention, types that cannot yet be loaded into the JVM running the processor, or elements with class-typed values. Do not assume every annotation can always be safely retrieved as a runtime annotation proxy and used with reflection.

Also distinguish between:

- `element.getAnnotationMirrors()`: annotations reflected on the element according to the `AnnotatedConstruct` contract.
- `processingEnv.getElementUtils().getAllAnnotationMirrors(element)`: a utility to obtain present annotations taking inheritance mechanisms into account where applicable.
- `typeMirror.getAnnotationMirrors()`: annotations placed on **a type use**; these may differ from annotations on the **declaration**.

If an annotation only has `@Target(TYPE_USE)`, inspect the type model (`TypeMirror`) and where it is used, rather than mistakenly looking for it among declaration annotations on the `Element`.

## 10. `Element` Is Neither an AST Nor Reflection

Three different perspectives:

| Model | Represents | Appropriate When |
|---|---|---|
| `javax.lang.model.element` | Java declarations with symbol/type checking | Compile-time annotation processing, code generation, declaration structure analysis |
| `javax.lang.model.type` | Java types in the compiler environment | Comparing/checking types, generics, assignability |
| AST / `com.sun.source.tree` (javac Tree API) | Source syntax such as if, for, invocations, expressions | Analyzing statement structure, expressions, and source code positions |
| `java.lang.reflect` | Classes/methods/fields of code loaded into the JVM | Reading `RUNTIME` annotations and members at runtime |
| `javap -v` / class-file parser | Structure of compiled class files | Inspecting stored metadata and bytecode |

For example, `Element` tells you that the method `getOr` has a parameter `fallback`, but it **is not a complete AST for the method body** containing the `?:` operator, the `==` comparison, and the `return` expression. If a tool needs to analyze individual expressions in the body, use an appropriate source-tree API such as `Trees`/`TreePathScanner`, rather than trying to find all nodes via `getEnclosedElements()`.

Conversely, Java reflection provides `Class<?>`, `Method`, and `Field` for already-loaded classes; it does not fully describe **type variables, compile-time SOURCE annotations, and uncompiled declarations** the way the annotation processing model does.

## 11. Common Mistakes When Working with Elements

### 11.1. Casting Every Element to `TypeElement`

~~~java
// WRONG if e is FIELD, METHOD, PARAMETER, or RECORD_COMPONENT:
TypeElement t = (TypeElement) e;
~~~

Check `getKind()` before casting, or use pattern `instanceof` when appropriate:

~~~java
if (e instanceof TypeElement type) {
    System.out.println(type.getQualifiedName());
}
~~~

### 11.2. Comparing Names Instead of Comparing Kinds

Two declarations in different scopes can share the same name `value`, while one is a field and the other is an annotation member method. Use **`getKind()` + enclosing context + name**; do not rely on name strings.

### 11.3. Confusing `ElementKind.TYPE_PARAMETER` and `TypeKind.TYPEVAR`

`T` in the type parameter declaration list has kind `TYPE_PARAMETER`; the type `T` of a field/method is a `TypeMirror` of kind `TYPEVAR`. Place both enums side by side to avoid mixing them up.

### 11.4. Confusing a Record Component with a Component Field

`RECORD_COMPONENT` describes the declaration in the record header. The corresponding field and accessor are separate elements. Use `TypeElement.getRecordComponents()` and `RecordComponentElement.getAccessor()` when you need to process records directly.

### 11.5. Missing Annotation `default` Values

`AnnotationMirror.getElementValues()` returns only the map of **explicit** values. Use `Elements.getElementValuesWithDefaults(...)` if your logic needs the complete picture.

### 11.6. Assuming `getEnclosedElements()` Includes All Inherited Members

It is not a “get every member” API. For a class, use `Elements.getAllMembers(type)` when inherited members are also needed.

### 11.7. Retaining `Element` Instances Beyond the Compile Task Lifecycle

`Element` instances are tied to the **processing/compiler environment**. Do not store object references and expect reliable reuse in another compilation or at runtime. If you need to persist information for another tool, convert it into an explicit data model containing the qualified name, kind, and appropriate signature details.

### 11.8. Relying on the Order of Implicit Members

The compiler may add a default constructor, accessors, or enum methods. Select members using `ElementFilter`, name, kind, and signature; do not read by fixed list index.

### 11.9. Processing Only the First Processing Round Unintentionally

A processor can generate additional sources, causing further annotation processing rounds to continue. Without proper control, the code may print duplicate output or generate duplicate files. For a real processor, design state and round handling policy explicitly; the hands-on example uses `done` to print only once.

### 11.10. Retrieving `SOURCE` Annotations via Java Reflection

A `RetentionPolicy.SOURCE` annotation may exist **in the compiler model while the processor runs**, but it is not retained to be read via `Class.getAnnotation` after compilation. This is another reason to use `AnnotationMirror` instead of runtime reflection.

## 12. Checklist Before Writing a Processor

1. **Is the target a declaration or a type?** Choose `Element`/`ElementKind` or `TypeMirror`/`TypeKind`.
2. **Which kinds need to be handled?** Recognize `CLASS`, `ANNOTATION_TYPE`, `RECORD`, `METHOD`, `PARAMETER`, and newer kinds as well.
3. **Do you need to traverse direct members or all members?** Distinguish `getEnclosedElements()`, `getAllMembers()`, and `getRecordComponents()`.
4. **Is the name enough to identify the element?** Use the qualified name, enclosing chain, and signature when needed, not a bare name.
5. **Do you need to read SOURCE/CLASS annotations?** Use the compiler model, retention rules, and `AnnotationMirror` in the right place.
6. **Do you need default values?** Use `getElementValuesWithDefaults`.
7. **Which round is being processed?** Consider `processingOver()`, root elements, and the possibility of re-invocation.
8. **Are there unsafe casts?** Filter by `ElementKind`/use `ElementFilter` before casting.
9. **Have you tested with the compiler using a standalone example?** Run `javac --release 17 -processor ...` and verify the output; for real-world logic, add unit/integration tests.
10. **Do you need an AST instead of the symbol model?** If the task requires analyzing expressions/statements, use the appropriate source tree.

## 13. Official Documentation

- [Java SE 17 — `Element`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/Element.html): operations and enclosing/enclosed relationships.
- [Java SE 17 — `ElementKind`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/ElementKind.html): declaration kinds in the model.
- [Java SE 17 — `TypeElement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/TypeElement.html): class/interface/enum/annotation/record, members, and record components.
- [Java SE 17 — `ExecutableElement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/ExecutableElement.html): method, constructor, parameters, and default value.
- [Java SE 17 — `RecordComponentElement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/RecordComponentElement.html): record components and accessors.
- [Java SE 17 — `Elements`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/util/Elements.html): looking up types, inspecting inherited members, and including annotation defaults.
- [Java SE 17 — `AnnotationMirror`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/AnnotationMirror.html): representation of annotations and values in the compiler.
- [Java SE 17 — `RoundEnvironment`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html): roots, annotated elements, and processing rounds.

**Takeaway:** **`Element` answers “which declaration?”, `ElementKind` answers “which kind of declaration?”, and `TypeMirror`/`TypeKind` answer “what is its type?”.** In an annotation processor, traverse the model via enclosing/enclosed relationships, check the kind, and then choose the specialized interface. Use `AnnotationMirror` for compile-time metadata, understand record components and annotation defaults clearly, and avoid confusing the declaration model with an AST or runtime reflection.
