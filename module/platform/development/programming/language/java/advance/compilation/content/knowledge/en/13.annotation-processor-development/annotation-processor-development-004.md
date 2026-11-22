# Reading Element, TypeMirror, and the Language Model When Building a Java Annotation Processor

## 1. Goal: Analyzing Java Code Before a Class Exists at Runtime

An annotation processor runs during `javac` compilation, while the program is undergoing syntax and type checking. At this time, many classes in source **do not yet have `.class` files**, so calling `Class.forName(...)` or Java Reflection cannot be treated as a reliable way to inspect source declarations.

Java provides the **Language Model API** in the `java.compiler` module to model declarations and types:

- **`Element`** answers: *what declaration is this* — class, interface, method, constructor, field, parameter, type parameter, package, or module?
- **`TypeMirror`** answers: *what is the Java type of a position/declaration* — primitive, declared type, array, type variable, wildcard, executable type, error type, etc.?
- **`Elements`** and **`Types`** are two utility groups querying names, packages, members, comparing, and transforming types according to **compiler semantics**.
- **`RoundEnvironment`** indicates which declarations in the current processing pass carry annotations supported by the processor.
- **`ProcessingEnvironment`** provides `Elements`, `Types`, `Messager`, `Filer`, and processor options.

In this lesson, we will write a real processor that reads a generic class `Store<T extends Number>`, collects field names/types using `Element` and `TypeMirror`, calls `Types.erasure(...)`, and generates a runnable Java source class. The example is compiled and run using OpenJDK 21 with `--release 17`; the main APIs are usable starting from Java 17.

### Learning Outcomes

1. Distinguish **declaration** (`Element`) and **type** (`TypeMirror`), avoiding misusing Reflection.
2. Navigate from `TypeElement` down to fields/methods/constructors and up to packages, superclasses, and interfaces.
3. Distinguish `TypeKind`, `DeclaredType`, `TypeVariable`, `ArrayType`, `ExecutableType`, and `ErrorType`.
4. Use `Elements` and `Types` for semantically accurate operations: `isSameType`, `isAssignable`, `erasure`, `asMemberOf`.
5. Design a stable reader when encountering generics, inheritance, annotations, and multiple processing rounds.
6. Know when to read the model, when to use `Filer`/`Messager`, and when syntax tree APIs are needed.

## 2. Three Distinct Layers: Source, Language Model, and Reflection

Consider a Java declaration:

```java
class Store<T extends Number> {
    private T id;
    private java.util.List<String> names;
}
```

In source code, `T` is a type parameter with bound `Number`; `List<String>` is a parameterized type. The compiler must verify these types **before** generating bytecode.

| Layer | Representation | What Is It Suitable For? |
| --- | --- | --- |
| Source code | `class Store<T extends Number>`, `List<String>` | Human-authored, IDE-edited |
| **Language Model API** | `TypeElement` of `Store`; `VariableElement` of field; `TypeMirror` of `T` and `List<String>` | Processor reading declarations and types right at compile time |
| Binary/runtime | `Store.class`; JVM descriptors; `java.lang.Class`, `java.lang.reflect.Field` | Loading/linking/reflecting on already-created classes |

A field `names` can be modeled by **two objects carrying different meanings**:

- `VariableElement`: *which field, what name, what modifiers, inside which class?*
- `TypeMirror` returned from `field.asType()`: *what type is declared on that field?* — `java.util.List<java.lang.String>`.

Multiple positions can use **the same type** `List<String>`, yet each field is a different `VariableElement`. Conversely, a `TypeElement` such as `java.util.List` represents the **generic declaration** `List<E>`, while multiple `DeclaredType`s can represent different usage types like `List<String>` and `List<Integer>`.

**Key takeaway:** `Element` does not mean “an object of that type exists in the JVM”. `TypeMirror` is not `Class<?>`. Do not use `instanceof java.lang.Class` to reason about the compile-time model.

## 3. Element: Map of Declaration Kinds

`Element` is the root interface in `javax.lang.model.element`. Commonly encountered subtypes:

| Subtype | Represents | Useful APIs |
| --- | --- | --- |
| `PackageElement` | Java package | `getQualifiedName()`, `getEnclosedElements()` |
| `ModuleElement` | JPMS module | `getQualifiedName()`, `getDirectives()` |
| `TypeElement` | Class, interface, record, enum, annotation interface | `getQualifiedName()`, `getTypeParameters()`, `getSuperclass()`, `getInterfaces()` |
| `ExecutableElement` | Method or constructor | `getParameters()`, `getReturnType()`, `getThrownTypes()`, `getTypeParameters()` |
| `VariableElement` | Field, parameter, enum constant, etc. | `getSimpleName()`, `asType()`, `getConstantValue()` |
| `TypeParameterElement` | Declaration of `T`, `E`, `K` | `getBounds()`, `getGenericElement()` |
| `RecordComponentElement` | Record component | `getAccessor()`, `asType()` |

`ElementKind` accurately distinguishes the nature of a declaration, e.g., `CLASS`, `INTERFACE`, `ENUM`, `RECORD`, `METHOD`, `CONSTRUCTOR`, `FIELD`, `PARAMETER`, `TYPE_PARAMETER`, `PACKAGE`, `MODULE`. For a field, check `member.getKind() == ElementKind.FIELD` **before** casting `(VariableElement) member`.

Some core APIs of `Element`:

- `getSimpleName()`: simple name, usually without package name. For certain special kinds, the name may not match the format learners guess from source code.
- `getKind()`: declaration kind; this is a more reliable branching criterion than manually parsing strings from `toString()`.
- `getModifiers()`: set of `Modifier`s such as `PUBLIC`, `PRIVATE`, `STATIC`, `FINAL`. Modifiers on a declaration differ from semantic constraints inferred only from context.
- `getEnclosingElement()`: directly enclosing declaration, e.g., a field belongs to a class, a top-level class belongs to a package.
- `getEnclosedElements()`: **directly** enclosed child declarations; not automatically all inherited members.
- `getAnnotationMirrors()`: annotations as compiler models, not requiring runtime reflection.
- `asType()`: the type defined or held by this declaration, with semantics depending on element kind.

**Note:** `getEnclosedElements()` can contain constructors, methods, fields, inner classes, and record components; never assume “the first element is always a field”. If a generator needs deterministic output, **filter by `ElementKind` and sort** rather than accidentally depending on the traversal order of one compiler implementation.

## 4. TypeMirror: Model of Types, Not Declaration Names

`TypeMirror` resides in `javax.lang.model.type`. It describes the types the compiler is resolving. The first API to inspect is `getKind()` to determine `TypeKind`. Common forms:

| TypeKind / Subtype | Java Example | How to Analyze |
| --- | --- | --- |
| `INT`, `BOOLEAN`, ... / `PrimitiveType` | `int`, `boolean` | Primitive kinds, not `DeclaredType` |
| `DECLARED` / `DeclaredType` | `String`, `List<String>`, `Map<String, Integer>` | `asElement()`, `getTypeArguments()`, `getEnclosingType()` |
| `ARRAY` / `ArrayType` | `String[]`, `T[]` | `getComponentType()` |
| `TYPEVAR` / `TypeVariable` | `T` in `class Box<T>` | `asElement()`, `getUpperBound()`, `getLowerBound()` |
| `WILDCARD` / `WildcardType` | `? extends Number`, `? super String` | `getExtendsBound()`, `getSuperBound()` |
| `EXECUTABLE` / `ExecutableType` | Type of a method/constructor | `getParameterTypes()`, `getReturnType()`, `getThrownTypes()` |
| `VOID`, `NONE` / `NoType` | `void` return type; case with no superclass | Do not treat `NONE` as `Object` |
| `NULL` / `NullType` | Special null type | Does not represent a Java class |
| `ERROR` / `ErrorType` | Unresolved/unresolvable type reference | Handle cautiously, especially across rounds |
| `INTERSECTION` / `IntersectionType` | Combined upper bounds | `getBounds()` |
| `UNION` / `UnionType` | Type of multi-catch (`IOException | SQLException`) | `getAlternatives()` |

Complex forms can be nested: `List<? extends Number[]>` is a `DeclaredType` with argument `WildcardType`, whose upper bound is `ArrayType`, whose component type is `Number`. A serious processor should traverse **subtype structure** or use `TypeVisitor`, not regex on the string returned by `TypeMirror.toString()`.

### An Important Confusion: ElementKind Differs from TypeKind

`TypeElement` for `List` has `ElementKind.INTERFACE`, whereas a **type expression** `List<String>` has `TypeKind.DECLARED`. Classes, interfaces, enums, and records can all appear as `DeclaredType` when used as reference types; there is no `TypeKind.CLASS`. Therefore:

```java
ElementKind declarationKind = element.getKind();
TypeKind valueTypeKind = element.asType().getKind();
```

The snippet above is only an example placed inside processor code that already has variable `element`. The two lines answer two different questions and should not be compared directly.

## 5. Types and Elements: Do Not Resolve Semantics via Strings

Retrieve the two utilities through `ProcessingEnvironment`:

```java
javax.lang.model.util.Elements elements =
        processingEnv.getElementUtils();
javax.lang.model.util.Types types =
        processingEnv.getTypeUtils();
```

This is an illustrative snippet inside a processor; `processingEnv` is a field provided by `AbstractProcessor` after initialization.

### 5.1. Elements: Operations on Declarations

- `getTypeElement("java.util.List")`: finds the `TypeElement` declaration by canonical name. May return `null` if the compiler cannot find the type in this environment.
- `getPackageOf(element)`: determines the package of the declaration.
- `getAllMembers(typeElement)`: inspects the set of members of the type, including inherited members according to API rules; differs from `getEnclosedElements()`.
- `overrides(overrider, overridden, type)` and `hides(hider, hidden)`: checks method overriding/hiding relationships according to Java semantics.
- `getBinaryName(typeElement)`: retrieves the binary name, useful for nested classes (differs from source-qualified name).
- `getAllAnnotationMirrors(element)`: includes inherited annotations per relevant rules, differing from only reading direct mirrors.

### 5.2. Types: Operations on Types

| API | What Does It Answer? |
| --- | --- |
| `isSameType(a, b)` | Are two types equivalent under the compiler's type model? |
| `isSubtype(a, b)` | Is `a` a subtype of `b`? |
| `isAssignable(a, b)` | Can a value of type `a` be assigned to a variable of type `b` per API rules? |
| `erasure(type)` | What type results from applying Java type erasure? |
| `directSupertypes(type)` | What are the direct supertypes of this type? |
| `asElement(type)` | For a type having a corresponding declaration, returns the associated `Element` (may be null). |
| `asMemberOf(declaredType, member)` | What **type** is a member viewed as **in the context of a specific declared/parameterized type**? |
| `getDeclaredType(typeElem, args...)` | Constructs a parameterized declared type model from a declaration and argument mirrors |
| `capture(type)` | Applies capture conversion to a type using wildcards |

**Do not compare types using `a.toString().equals(b.toString())`** when deciding assignability or generic compatibility. `toString()` is very useful for human-readable logging, but it is only a text representation; subtype rules, boxing, erasure, wildcards, and generic substitutions are more complex than string equality. Also do not use `==` as a contract for testing semantic equality between two types.

## 6. Runnable Example: Reading Fields, Type Variables, and Erasure

We will create the `@Inspect` annotation, use a processor to read class `Store<T extends Number>`, sort fields by name, obtain both original types and post-erasure types, and generate `demo.StoreModel`. `Main` will call `StoreModel.summary()` so results are observable on stdout.

### 6.1. Project Structure

```text
model-demo/
├── processor-src/
│   └── tool/
│       └── ModelProcessor.java
└── src/
    └── demo/
        ├── Inspect.java
        ├── Store.java
        └── Main.java
```

The project uses a simple Java classpath, **without** `module-info.java` and without third-party libraries. The processor file sits separately to be compiled first, because the processor must exist as a class for `javac` to execute it.

### 6.2. src/demo/Inspect.java

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface Inspect {}
```

`RetentionPolicy.SOURCE` is completely sufficient because the processor runs **before** class files are finalized; the annotation only needs to appear in source for this compilation pass. `@Target(TYPE)` restricts placement, while the processor actively checks for `ElementKind.CLASS`.

### 6.3. src/demo/Store.java

```java
package demo;

import java.util.List;

@Inspect
public final class Store<T extends Number> {
    private final T id;
    private final List<String> names;

    public Store(T id, List<String> names) {
        this.id = id;
        this.names = names;
    }

    public T id() {
        return id;
    }

    public List<String> names() {
        return names;
    }
}
```

These two fields were chosen intentionally:

- `id` has source type `T`, a **type variable**, first bound `Number`, erasure `Number`.
- `names` has source type `List<String>`, a **declared parameterized type**, erasure raw `List`.
- `id()` and `names()` are **methods**, so a processor filtering `FIELD` will not mistake methods for fields.
- The constructor is `CONSTRUCTOR`, not `FIELD`.

### 6.4. src/demo/Main.java

```java
package demo;

import java.util.List;

public class Main {
    public static void main(String[] args) {
        System.out.println(StoreModel.summary());
        System.out.println(
                new Store<>(7, List.of("Ada", "Lin")).names().size());
    }
}
```

`StoreModel` does not yet exist in the handwritten source files. It must be generated by the processor. This helps confirm both the **model reading phase** and the **class generation phase** succeeded.

### 6.5. processor-src/tool/ModelProcessor.java

```java
package tool;

import java.io.IOException;
import java.io.Writer;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
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
import javax.lang.model.type.TypeMirror;
import javax.tools.Diagnostic;
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("demo.Inspect")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class ModelProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (roundEnv.processingOver()) {
            return true;
        }

        for (TypeElement annotation : annotations) {
            for (Element element
                    : roundEnv.getElementsAnnotatedWith(annotation)) {

                if (element.getKind() != ElementKind.CLASS) {
                    processingEnv.getMessager().printMessage(
                            Diagnostic.Kind.ERROR,
                            "@Inspect requires a class",
                            element);
                    continue;
                }

                TypeElement type = (TypeElement) element;
                String pkg = processingEnv.getElementUtils()
                        .getPackageOf(type).getQualifiedName().toString();
                String simple = type.getSimpleName().toString() + "Model";
                String fullName = pkg.isEmpty() ? simple : pkg + "." + simple;

                List<VariableElement> fields = new ArrayList<>();
                for (Element member : type.getEnclosedElements()) {
                    if (member.getKind() == ElementKind.FIELD) {
                        fields.add((VariableElement) member);
                    }
                }
                fields.sort(Comparator.comparing(
                        f -> f.getSimpleName().toString()));

                List<String> tokens = new ArrayList<>();
                tokens.add("class=" + type.getQualifiedName());

                for (VariableElement field : fields) {
                    TypeMirror mirror = field.asType();
                    tokens.add(field.getSimpleName() + ":" + mirror
                            + "->" + processingEnv.getTypeUtils()
                                    .erasure(mirror));
                }

                String report = String.join("|", tokens);

                try {
                    JavaFileObject file = processingEnv.getFiler()
                            .createSourceFile(fullName, type);

                    try (Writer writer = file.openWriter()) {
                        if (!pkg.isEmpty()) {
                            writer.write("package " + pkg + ";\n");
                        }
                        writer.write(
                                "public final class " + simple + " {\n");
                        writer.write(
                                "  private " + simple + "() {}\n");
                        writer.write(
                                "  public static String summary() { return "
                                        + quote(report) + "; }\n");
                        writer.write("}\n");
                    }
                } catch (IOException ex) {
                    processingEnv.getMessager().printMessage(
                            Diagnostic.Kind.ERROR,
                            "Cannot generate " + fullName + ": " + ex,
                            element);
                }
            }
        }
        return true;
    }

    private static String quote(String text) {
        return "\"" + text.replace("\\", "\\\\")
                .replace("\"", "\\\"")
                .replace("\n", "\\n")
                .replace("\r", "\\r")
                + "\"";
    }
}
```

This is a complete processor, independently compilable with JDK 17+. It **does not import `demo.Inspect`** in the processor's runtime classpath: the annotation name is declared as a string, and the processor receives `TypeElement` from `annotations`. This approach allows compiling the processor before compiling the annotation and application.

### 6.6. Compiling and Running from the model-demo Directory

Linux/macOS, with working directory `model-demo`:

```bash
mkdir -p build/processor build/classes build/generated
javac --release 17 -d build/processor processor-src/tool/ModelProcessor.java
javac --release 17 -processorpath build/processor -processor tool.ModelProcessor -s build/generated -d build/classes src/demo/Inspect.java src/demo/Store.java src/demo/Main.java
java -cp build/classes demo.Main
```

On Windows PowerShell, create directories with equivalent commands:

```powershell
New-Item -ItemType Directory -Force build/processor,build/classes,build/generated | Out-Null
javac --release 17 -d build/processor processor-src/tool/ModelProcessor.java
javac --release 17 -processorpath build/processor -processor tool.ModelProcessor -s build/generated -d build/classes src/demo/Inspect.java src/demo/Store.java src/demo/Main.java
java -cp build/classes demo.Main
```

**Stdout of `demo.Main` when using OpenJDK 21 and the files above:**

```text
class=demo.Store|id:T->java.lang.Number|names:java.util.List<java.lang.String>->java.util.List
2
```

Verified with OpenJDK 21 using `--release 17`: the processor is called, generated source compiles, and the program prints those exact two lines. Note: `TypeMirror.toString()` is a human-oriented representation; you should not treat the string format of every TypeMirror as a stable serialization protocol across all compilers. When generating long-lived config/schema files, use API structures rather than relying verbatim on `toString()`.

Generated file:

```text
build/generated/demo/StoreModel.java
```

Content on the test tool:

```java
package demo;
public final class StoreModel {
  private StoreModel() {}
  public static String summary() { return "class=demo.Store|id:T->java.lang.Number|names:java.util.List<java.lang.String>->java.util.List"; }
}
```

Related class files in `build/classes/demo/`: `Inspect.class`, `Store.class`, `Main.class`, and `StoreModel.class`. `-s` specifies where to write **generated source**, `-d` specifies where to write **class output**, while `-processorpath` contains the processor implementation (separate from the application's classpath).

### 6.7. Walking Step-by-Step Through the Processor

1. `roundEnv.getElementsAnnotatedWith(annotation)` returns elements annotated with `demo.Inspect` in the round. Because the annotation marks class `Store`, the element is a `TypeElement`.
2. `element.getKind()` ensures we genuinely have a class declaration before casting.
3. `getPackageOf(type)` determines the package, `getSimpleName()` determines the class name to construct the new source class name.
4. `getEnclosedElements()` retrieves direct declarations belonging to `Store`. Only members with `ElementKind.FIELD` are kept.
5. `field.asType()` retrieves `TypeMirror`: field `id` is `TYPEVAR`; `names` is `DECLARED`.
6. `Types.erasure(mirror)` yields `Number` for `T extends Number` and `List` for `List<String>`.
7. `Filer.createSourceFile(...)` creates Java source and records the originating `TypeElement`. The generated file is fed by the compiler into subsequent compilation.
8. `return true` means the processor **claims** the annotation types requested for processing in the round; it is not a status saying “all files were written successfully”.

The example only creates one file from one top-level class. In real projects, design a naming policy avoiding collisions among nested classes, identical simple names across packages, and multiple processors wanting to generate the same generated class.

## 7. Reading Generic Types Properly

### 7.1. Type of Generic Declaration and Used Type Are Not the Same

Suppose we have:

```java
class Box<T> {
    T value;
}
Box<String> box;
```

- `TypeElement` of `Box` states it has type parameter `T`. `getTypeParameters()` returns `TypeParameterElement`.
- `TypeElement.asType()` describes the generic form of the declaration itself, usually corresponding to `Box<T>`.
- The type of a field/variable declared `Box<String>` is a `DeclaredType` carrying a type argument `String`. `getTypeArguments()` lets you read that argument.
- `Types.asElement(declaredType)` can return the `Box` declaration, yet looking only at the declaration does not tell whether the field is used with `String` or `Integer`; you must read `DeclaredType.getTypeArguments()`.

Do not think `TypeElement` has a separate instance per `Box<String>`. This is the difference between **declaration identity** and **applied/parameterized type**.

### 7.2. Type Variables and Bounds

With `Store<T extends Number>`:

```java
for (var p : type.getTypeParameters()) {
    // p: TypeParameterElement, e.g., named T
    // p.getBounds(): list of upper bounds, e.g., Number
}
```

This is a **code snippet inside a processor having a `type` variable of type `TypeElement`**, not a standalone program. `TypeParameterElement` describes the `T` declaration; whereas `field.asType()` of `T id` returns `TypeVariable` (a kind of `TypeMirror`). `Types.erasure(T)` yields `Number` from the first bound; a `T` without an explicit bound has erasure `Object`.

If a generator only prints `typeMirror.toString()` and ignores bounds, it can miss constraints needed for type checking and generating valid code.

### 7.3. Wildcards Are Not TypeParameterElements

`List<? extends Number>` has a `WildcardType` argument, with no dedicated type parameter name. `? extends Number` is a **use-site type argument**, unlike a declaration `T extends Number`. Use `WildcardType.getExtendsBound()`/`getSuperBound()` when needing to read wildcard structure. A visitor checking generics must distinguish these two forms.

### 7.4. Arrays and Primitives

- `int`: `PrimitiveType` with kind `INT`.
- `String[]`: `ArrayType`, `getComponentType()` yields `String`.
- `T[]`: component type can be `TypeVariable`.
- `void` when a method return type: `NoType` with kind `VOID`, **not** a `TypeElement` for a class named “void”.

Poorly designed generators often cast every `TypeMirror` to `DeclaredType`; that causes errors with primitives, arrays, type variables, wildcards, and no-type.

## 8. Methods and Constructors: ExecutableElement vs ExecutableType

Suppose source has the method:

```java
public List<String> names() {
    return names;
}
```

In the model:

- **`ExecutableElement`** describes the `names` method declaration; `getSimpleName()` is the name, `getParameters()` contains parameter `VariableElement`s, `getReturnType()` returns the `TypeMirror` of the return type, and `getThrownTypes()` lists declared checked exceptions.
- **`ExecutableType`** describes the **callable type** of the method with parameter types, return type, thrown types, and type variables. `ExecutableElement.asType()` can return `ExecutableType`.

A constructor is also an `ExecutableElement` yet has `ElementKind.CONSTRUCTOR`; do not assume it behaves like a method named after the class in all respects. Use `getKind()` and corresponding APIs.

When using an annotation processor to validate method contracts, check:

1. `ElementKind.METHOD`.
2. `getModifiers()` and `getParameters()`.
3. `getReturnType()` and parameter type mirrors.
4. `Types.isAssignable` / `isSubtype` / `isSameType` when type rules are genuinely needed.
5. Generic methods: `getTypeParameters()`; a method `<T> T identity(T t)` has **its own method type variable**, not automatically a type variable of the enclosing class.

`ExecutableElement.getReturnType()` returns the type according to the declaration the element represents. When a method is inherited from a generic base and viewed through a concrete subtype, you sometimes must use `Types.asMemberOf(...)` to obtain **the type with generic parameters substituted in the subtype's context**.

## 9. Why Is asMemberOf Important for Generic Inheritance?

Consider the following **illustrative** Java snippet:

```java
class Base<T> {
    T get() {
        return null;
    }
}

class StringBox extends Base<String> {
}
```

In declaration `Base<T>`, the return type of method `get()` is `T`. Yet when that method is viewed as a member of `StringBox`, the logical return type is `String`.

A processor can use:

```java
DeclaredType containing = (DeclaredType) stringBoxType.asType();
TypeMirror memberType = types.asMemberOf(containing, getMethodElement);
ExecutableType adapted = (ExecutableType) memberType;
TypeMirror returnType = adapted.getReturnType();
```

This is a **code snippet inside a processor**, assuming you already have:

- `stringBoxType` is the `TypeElement` of `StringBox`;
- `getMethodElement` is the `ExecutableElement` declaring the `Base.get()` method;
- `types` is `processingEnv.getTypeUtils()`.

With `asMemberOf`, the processor asks the compiler to perform generic substitution when the member is viewed inside the containing declared type; the resulting return type represents `String`. If you merely call `getMethodElement.getReturnType()` on the declaration in `Base<T>`, you may receive type `T` and generate wrong APIs for `StringBox`.

**Do not apply `asMemberOf` to a member that is not valid in the containing type.** The API documentation permits throwing `IllegalArgumentException` if the element is not a matching member. Determine the exact context; do not try forcing an arbitrary method into an unrelated class.

## 10. Reading Annotations via the Model, Without Necessarily Loading Annotation Classes

A processor can read:

```java
for (AnnotationMirror mirror : element.getAnnotationMirrors()) {
    TypeMirror annotationType = mirror.getAnnotationType();
    // Read annotation type and element values via AnnotationMirror
}
```

This is a code snippet where `element` is a found `Element`. `AnnotationMirror` and `AnnotationValue` allow viewing annotation declarations and values in the compile environment. `Elements.getElementValuesWithDefaults(mirror)` helps retrieve default values too if the code generator needs a complete configuration.

Using `element.getAnnotation(MyAnnotation.class)` also has valid uses, especially when the processor has the annotation API on the processor classpath. However, it creates a dependency on the runtime `Class` of the annotation, which the compiler may not have loaded the way the author imagines. For general-purpose processors, using `AnnotationMirror`, `TypeElement`, and `TypeMirror` is usually safer and more flexible.

`@Retention(SOURCE)` **does not prevent** a processor from reading annotations on source; it only specifies retention after compilation. Do not change an annotation to `RUNTIME` just so the processor “sees” it.

## 11. The Model Is a Semantic Model, Not a Full AST

The Language Model API provides declarations and types already interpreted by the compiler. It does **not** by default reveal every addition operation, literal, if/else condition, or exact source characters inside a method body.

Distinguish:

- **Language model (`javax.lang.model.*`):** declaration/type semantics; very suitable for API generators, schema checkers, DI metadata, mapper validation.
- **Tree API (`com.sun.source.tree`, `com.sun.source.util.Trees`) of the JDK compiler:** accesses the syntax tree at statement/expression level when tools and environments support it. This is a different API; it does not mean every `TypeMirror` has a child AST.
- **Runtime reflection:** observes loaded classes; cannot substitute for the compile-time model when source is not yet compiled into classes.
- **Compiler internal AST (`com.sun.tools.javac.*`):** internal implementation details, not standard `javax.lang.model` contracts; tightly coupled to the `javac` version.

If the goal is merely “generating mappers based on fields, methods, modifiers, and generic types”, prefer `Element`/`TypeMirror`. If you need to analyze method bodies, switch to an appropriate AST tool instead of trying to parse `Element.toString()` output.

## 12. ErrorType, Incomplete Code, and Multiple Processing Rounds

Source being compiled may reference a type **not yet resolved** because another processor will generate it in the next round. In this situation, the compiler may represent part of the type as an `ErrorType`. That requires thoughtful handling:

- Do not blindly cast `ErrorType` to a Java class or assume the type already exists at runtime.
- When unable to validate a type relationship, you can emit a relevant diagnostic or defer processing to a subsequent round according to the processor's specific contract.
- Do not “spin wait” or repeatedly emit the same file to force the compiler to re-resolve: `FilerException` or an unstable processing loop can occur.
- Do not cache model objects across **multiple compilation runs** or build invocations as if they were immutable metadata. Model objects belong to the compilation environment and can change resolution state across rounds.
- During `roundEnv.processingOver() == true`, do not create new Java source expecting the compiler to open another round for it.

According to the `Processor` API, once a processor has been invoked in a round, it will continue to be invoked in subsequent rounds, including the final round. `RoundEnvironment.errorRaised()` reports errors in the previous round; it does not mean every typed lookup at this moment is already stable.

If a processor handles multiple annotation types, `process(Set<? extends TypeElement> annotations, ...)` may receive a **subset** of the types it supports in a round. Do not make the assumption “every process call always has exactly one annotation type”; the lesson's example runs on one annotation to keep focus.

## 13. Accurate Error Diagnostics with Messager and Originating Elements

### 13.1. Attaching Errors to an Element

When encountering an invalid declaration:

```java
processingEnv.getMessager().printMessage(
        Diagnostic.Kind.ERROR,
        "Unsupported declaration for @Inspect",
        element);
```

This snippet belongs to the `process` method with `element` in scope. The compiler/IDE can attach the diagnostic to the declaration's location; better than `System.out.println` printing a line unrelated to source.

`Diagnostic.Kind.WARNING` fits issues that should not stop the build; `ERROR` fits conditions that must be fixed before codegen is trustworthy. Do not swallow configuration errors and generate an empty class as if successful.

### 13.2. Filer Has File Ownership Boundaries

`Filer.createSourceFile(qualifiedName, originatingElements...)` creates **new source**. Avoid recreating the same name within one compilation run, avoid colliding with existing source files, and avoid conflicts when multiple processors generate the same name. `FilerException` is an `IOException` subtype commonly seen for this violation.

Originating elements give build tools clues about **the inputs causing an output to be generated**. They support incremental annotation processing mechanisms, yet do not by themselves prove every processor runs incrementally correctly. Additionally, a processor may need to distinguish “isolating” and “aggregating” outputs depending on the build system's specific contract.

When using values from annotations to generate Java literals, escape strings and validate names. `TypeMirror.toString()` is not an API guaranteed to produce valid corresponding source code in every case; for critical generators, construct source structure from the model and use per-`TypeKind` type-name printing logic or a reliable generation library.

## 14. When to Use a Visitor Instead of if/instanceof?

For simple processors, branching on `getKind()` is clear enough. However, when needing to support many `TypeMirror` kinds — nested arrays, wildcards, intersections, executables, generics — a visitor structure misses fewer cases:

```java
import javax.lang.model.type.TypeMirror;
import javax.lang.model.util.SimpleTypeVisitor14;

class TypeKinds extends SimpleTypeVisitor14<String, Void> {
    @Override
    protected String defaultAction(TypeMirror type, Void unused) {
        return type.getKind().name();
    }
}
```

**This is an illustration of a separate Java class**, not a complete processor. `SimpleTypeVisitor14` exists in Java 17 and handles type shapes under the visitor framework. If wanting to actively handle each kind, override additional methods such as `visitDeclared`, `visitArray`, `visitTypeVariable`, `visitWildcard`, `visitExecutable`, ... and recurse into components/type arguments. Choose a visitor version matching the type kinds and compilers the project must support.

Similarly, `ElementVisitor` / `SimpleElementVisitor...` helps analyze `TypeElement`, `VariableElement`, and `ExecutableElement` in a structured way. A major benefit is when Java adds new declarations (e.g., record components), missing/default branches can be caught instead of silently ignored.

## 15. Using javac and Tests to Verify the Processor

After creating the files as in section 6, you can enable round logs:

```bash
javac --release 17 -XprintRounds -XprintProcessorInfo -processorpath build/processor -processor tool.ModelProcessor -s build/generated -d build/classes src/demo/Inspect.java src/demo/Store.java src/demo/Main.java
```

Logs show whether the processor was called and whether it triggered another round. Do not treat literal `-XprintRounds` lines as invariant output across compiler versions; verify **generated files, diagnostics, and runtime behavior**.

### Negative Test: Disabling the Processor

In a separate clean output directory, try:

```bash
javac --release 17 -proc:none -d build/no-processor src/demo/Inspect.java src/demo/Store.java src/demo/Main.java
```

Without a handwritten `StoreModel.java`, unless the classpath contains an old `demo.StoreModel`, compilation must **fail** at `Main` because `StoreModel` cannot be resolved. This proves the program genuinely depends on generated code. **Do not use an output directory containing old class files**, as it can mask the issue.

### Verifying the Effect of Erasure

Source `id` has type variable `T extends Number`, whose erasure is `Number`. You can inspect the class file:

```bash
javap -p -s -classpath build/classes demo.Store
```

`javap -s` will show the descriptor for field `id` as `Ljava/lang/Number;`, while the processor read type mirror `T` during compilation. These are two matching yet distinct perspectives: **compile-time generic type** and **binary field descriptor**.

### Checking Toolchain Lifecycle

The `-processor` option is specified explicitly to avoid relying on processor auto-discovery differences across JDK releases. Starting from JDK 23, annotation processing no longer runs automatically by default just because a processor happens to appear on the classpath; therefore, configure processor path and processing mode explicitly in build tools/CI.

## 16. Common Mistakes When Reading the Model

| Misconception or Error | Cause | Right Approach |
| --- | --- | --- |
| `Class.forName("demo.Store")` in processor | Class being compiled may not yet exist on processor runtime classpath | `Elements.getTypeElement("demo.Store")` |
| Treating `Element` as `TypeMirror` itself | Declarations and types are two different concepts | `Element.asType()` and check `TypeKind` |
| Casting every `Element` to `TypeElement` | Fields, methods, and parameters have other subtypes | Check `getKind()` before casting |
| Casting every `TypeMirror` to `DeclaredType` | Primitives/arrays/typevars/wildcards are not declared types | Use `getKind()` or `TypeVisitor` |
| Comparing `TypeMirror` by string name | Ignores generic substitution, wildcards, and assignability | Use `Types.isSameType` / `isAssignable` / `asMemberOf` |
| Using `getEnclosedElements()` to get inherited members | API only retrieves direct declarations | Check `Elements.getAllMembers()` |
| Reading return type of generic parent without substituting `T` | Looking at declaration instead of subtype context | Use `Types.asMemberOf(...)` |
| Treating `TypeElement` of `List` as `List<String>` | Declaration differs from applied parameterized type | Read `DeclaredType.getTypeArguments()` |
| Assuming `ErrorType` is always a permanent error | Type may be generated in the next round | Check rounds and deferral/diagnostic policy |
| Processor operating via reflection | Mixing runtime model with compile-time model | Use `javax.lang.model` |
| Generated code has different order each build | Relying on iteration order/mtime/HashMap | Sort and keep output deterministic |
| Trying to create the same class twice | `Filer` / multi-round collision | Track naming/output ownership, create only once |
| Processor reading SOURCE annotation from `.class` file | Annotation is not retained in runtime binary as assumed | Supply source and process in proper compile round |
| Using internal AST instead of standard model for every problem | Coupled to compiler internals and JDK build | Prefer `Element`/`TypeMirror` when sufficient |
| Running on another JDK with unsuitable `SourceVersion` | Processor declared source version lower/higher than compilation | Choose appropriate source-version policy and check `javac --release` |

## 17. Self-Check Exercises

**Question 1.** With source `class Box<T extends Number> { T x; }`, what kind of `Element` is `x`? What kind of `TypeMirror` is the type of `x`?

**Answer:** `x` is a `VariableElement` with `ElementKind.FIELD`. `x.asType()` is a `TypeVariable` with `TypeKind.TYPEVAR`; `Types.erasure(...)` yields `Number`.

**Question 2.** Why can't you retrieve the type arguments of field `List<String> names` solely via `Types.asElement(names.asType())`?

**Answer:** `asElement(...)` returns the declaration of `List`, which does not carry use-site type argument information like a dedicated `TypeElement`. You must cast `names.asType()` to `DeclaredType` after checking kind and then read `getTypeArguments()`.

**Question 3.** Does `getEnclosedElements()` automatically list methods inherited from a superclass?

**Answer:** No; it directly lists declarations inside the element. `Elements.getAllMembers(type)` is the relevant tool when needing a member set including inherited ones, then use `asMemberOf` to adapt types to context when appropriate.

**Question 4.** A method in `Base<T>` returns `T`, while the subclass is `Derived extends Base<String>`. To get the return type as viewed from `Derived`, which API do you use?

**Answer:** `Types.asMemberOf((DeclaredType) derived.asType(), baseMethodElement)`, then read the return type from `ExecutableType`. Do not use only `baseMethodElement.getReturnType()` in the context of `Base<T>`.

**Question 5.** Do `String[]` and `List<String>` share `TypeKind.DECLARED`?

**Answer:** No. `String[]` has `TypeKind.ARRAY`; `List<String>` has `TypeKind.DECLARED`.

**Question 6.** Can a processor read a `@Retention(SOURCE)` annotation on a class being compiled?

**Answer:** Yes. SOURCE annotations exist in the source model and can be processed by annotation processors. They do not need runtime retention.

**Question 7.** After the first round, an unresolved type is represented as `ErrorType`. Should the processor call `Class.forName(...)` to force it to appear?

**Answer:** No. Runtime reflection does not create classes currently being compiled. Process across rounds, manage generated sources, and emit diagnostics or defer appropriately.

**Question 8.** Two builds produce fields in different orders. How should the generator be fixed?

**Answer:** Filter specifically for `FIELD`, apply sorting by name or a stable business criterion before generating output; do not depend on accidental collection iteration order.

**Question 9.** When is `Messager` more suitable than `Filer`?

**Answer:** When the goal is only reporting an invalid condition/warning at compile time, with no new artifact needed. `Filer` is for generating source/class/resource files.

**Question 10.** The generator wants to directly edit the body of a method being compiled. Does `TypeMirror` provide a statement tree to modify?

**Answer:** No. `TypeMirror` describes types, not a method body AST. Standard JSR 269 focuses on declaration/type models and file generation; AST rewriting tasks require an appropriate dedicated mechanism.

## 18. Official References

- **Java SE 21 `Element` API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/lang/model/element/Element.html — declarations, `getKind`, `asType`, `getEnclosedElements`.
- **Java SE 21 `TypeElement` API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/lang/model/element/TypeElement.html — class/interface declarations, type parameters, interfaces, and superclass.
- **Java SE 21 `TypeMirror` API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/lang/model/type/TypeMirror.html — root interface for compile-time types.
- **Java SE 21 `Types` API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/lang/model/util/Types.html — `isAssignable`, `erasure`, `asMemberOf`, `getDeclaredType`.
- **Java SE 21 `Elements` API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/lang/model/util/Elements.html — querying declarations, packages, members, annotation mirrors.
- **Java SE 21 `RoundEnvironment` API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html — round elements and processing status.
- **Java SE 21 `Processor` API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/annotation/processing/Processor.html — lifecycle and semantics of `process`.
- **Oracle JDK 21 `javac`:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html — `-processor`, `-processorpath`, `-s`, `-XprintRounds`.

**Conclusion:** when building an annotation processor, view **`Element` as a declaration** and **`TypeMirror` as the Java type resolved by the compiler**. Use `Elements`/`Types` to work according to language semantics — especially with generics and inheritance — and use `Filer` strictly to generate new artifacts and `Messager` to report errors. This model keeps processors reliable, testable, and minimally dependent on implementation details of a specific `javac` version.
