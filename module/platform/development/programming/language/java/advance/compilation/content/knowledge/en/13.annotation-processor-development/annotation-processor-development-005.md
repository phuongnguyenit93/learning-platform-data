# Using Elements and Types Instead of Guessing from Type Name Strings When Building Annotation Processors

## 1. The Problem: Do Not Treat Printed Type Names as the Java Type Model

In Java annotation processing, we often want to answer questions such as:

- Does a method return a type implementing `CharSequence`?
- Is `List<String>` assignable to `List<Object>`?
- What type does the `get()` method declared in `Box<T>` return when viewed from `Box<String>`?
- Does a method override an inherited method?
- Which qualified name, binary name, and owner does a nested type have?

An easy-to-write yet unreliable approach is calling `typeMirror.toString()`, then using `equals`, `startsWith`, `contains`, or splitting strings by `<`, `>`, commas, and dots. For example:

~~~java
// WRONG design direction: illustrates how NOT to decide type relationships.
String printed = method.getReturnType().toString();
if (printed.equals("java.lang.String")
        || printed.endsWith("StringBuilder")) {
    // May miss subtypes and falsely match types that merely look similar in name.
}
~~~

This approach confuses **the text representation of a type** with **the semantics of a type in the compiler**. Java has generic type arguments, type variables, wildcards, intersection bounds, arrays, nested types, overloaded methods, module boundaries, and temporarily unresolved types. Having similar-looking names does not prove two types are identical, share an inheritance relationship, or are assignable to each other.

The right direction is using the **language model API** in the `java.compiler` module:

- `javax.lang.model.element.*`: **declarations** such as classes, interfaces, fields, methods, type parameters, packages, modules.
- `javax.lang.model.type.*`: **types** of declarations and expressions at the type-model level, such as `DeclaredType`, `ArrayType`, `TypeVariable`, `WildcardType`, `ExecutableType`, `ErrorType`.
- `javax.lang.model.util.Elements`: utilities for querying and comparing **program elements**.
- `javax.lang.model.util.Types`: utilities for constructing and checking **type relationships**.
- `javax.annotation.processing.ProcessingEnvironment`: provides the two utilities above via `getElementUtils()` and `getTypeUtils()`.

**Principle:** use `TypeMirror.toString()` to print human-readable messages when appropriate; use `Types` to decide whether types match, are subtypes, or are assignable. Use `Elements` to identify actual declarations instead of manually parsing class and method names.

## 2. Distinguishing Element and TypeMirror

Example declaration:

~~~java
// Illustration, not a complete runnable program.
class Box<T> {
    T value;
    T get() { return value; }
}
~~~

- `TypeElement` of `Box` represents the **class declaration** `Box` with its type parameters.
- `TypeParameterElement` of `T` represents the **type parameter declaration**.
- `VariableElement` of field `value` represents the **field declaration**.
- `ExecutableElement` of `get` represents the **method declaration**.
- `TypeMirror` of the field describes that field's **type**. For field `T value`, this is the type variable type `T`, not a `TypeElement` named `T`.
- `DeclaredType` of `Box<String>` describes a **parameterized usage of the class**, not a new class declaration named `Box<String>`.

For declaration `TypeElement box`, `box.asType()` is the type of the declaration with the associated type variables; it does not automatically become `Box<String>`. To represent `Box<String>`, use `Types.getDeclaredType(box, stringElement.asType())` when that is an appropriate type.

| Want to Know | Choose API |
| --- | --- |
| Is a class/package/module declared/observable? | `Elements.getTypeElement`, `getPackageElement`, `getModuleElement` |
| Canonical/qualified or binary name of a class? | `TypeElement.getQualifiedName`, `Elements.getBinaryName` |
| Which methods/fields belong to or are inherited by a class? | `getEnclosedElements` and `Elements.getAllMembers` |
| Is a class a subtype of an interface? | `Types.isSubtype` |
| Is a value of type A assignable to a variable of type B? | `Types.isAssignable(A,B)` |
| Do two type representations denote the same Java type? | `Types.isSameType` |
| Is a generic type parameterized properly? | `Types.getDeclaredType`, `DeclaredType.getTypeArguments` |
| Type of a method when inherited through `Box<String>`? | `Types.asMemberOf` then `ExecutableType` |
| Is there a true override/hiding relationship? | `Elements.overrides`, `Elements.hides` |
| Component type of an array or corresponding primitive? | `ArrayType.getComponentType`, `Types.getArrayType`, `getPrimitiveType` |

`Element.getSimpleName()` is useful for displaying names; it is not sufficient to distinguish identically named types across different packages/modules.

## 3. Obtaining Elements and Types in an Annotation Processor

A processor can extend `AbstractProcessor`. After the compiler invokes `init`, the `processingEnv` field provides utilities and `Messager`:

~~~java
// Fragment inside an AbstractProcessor; not a standalone file.
Elements elements = processingEnv.getElementUtils();
Types types = processingEnv.getTypeUtils();
Messager messages = processingEnv.getMessager();

TypeElement charSequence =
        elements.getTypeElement("java.lang.CharSequence");
if (charSequence == null) {
    messages.printMessage(Diagnostic.Kind.ERROR,
            "Cannot resolve java.lang.CharSequence");
    return true;
}
~~~

`getTypeElement` accepts the **canonical name** of the type visible to the compiler, not the name of a parameterized type like `java.util.List<java.lang.String>`. It can return `null` if the type is not uniquely resolved in the current environment. In projects with JPMS, there are module-scoped overloads to avoid ambiguity; do not automatically assume every package/class resides on the classpath.

`Element`/`TypeMirror` objects belong to **the model currently being processed by the compiler**. Do not use `Class.forName` to inspect classes from user source: that class may not yet be compiled/loaded into the JVM running the processor, and reflection looks at the processor's classpath rather than the current compilation model.

## 4. Complete Java 17+ Example: Annotation Validating Return Types

We build an annotation processor requiring methods carrying `@CheckReturn` to have a return type **assignable to `java.lang.CharSequence`**. This condition accepts `String`, `StringBuilder`, and other genuinely matching types; it rejects `Object` even though the implementation might return a `String` at runtime.

Do not use string checks on return type names. The processor uses `Types.isAssignable` directly.

Project structure:

~~~text
project/
├── src/
│   ├── processor/java/demo/validation/
│   │   ├── CheckReturn.java
│   │   └── ReturnTypeProcessor.java
│   └── main/java/demo/
│       ├── App.java
│       └── BadApp.java          # used specifically for failure case
└── build/
    ├── processor/
    └── classes/
~~~

### 4.1. File src/processor/java/demo/validation/CheckReturn.java

~~~java
package demo.validation;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.SOURCE)
public @interface CheckReturn {
}
~~~

`SOURCE` retention means the annotation is used during compilation; runtime does not need to retain it. `@Target(METHOD)` prevents placing the annotation on classes/fields at compile time.

### 4.2. File src/processor/java/demo/validation/ReturnTypeProcessor.java

~~~java
package demo.validation;

import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.ExecutableElement;
import javax.lang.model.element.TypeElement;
import javax.lang.model.type.TypeKind;
import javax.lang.model.type.TypeMirror;
import javax.lang.model.util.Elements;
import javax.lang.model.util.Types;
import javax.tools.Diagnostic;

@SupportedAnnotationTypes("demo.validation.CheckReturn")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class ReturnTypeProcessor extends AbstractProcessor {
    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment roundEnv) {
        if (roundEnv.processingOver()) {
            return true;
        }

        Elements elements = processingEnv.getElementUtils();
        Types types = processingEnv.getTypeUtils();
        TypeElement expected =
                elements.getTypeElement("java.lang.CharSequence");

        if (expected == null) {
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR,
                    "Cannot resolve java.lang.CharSequence");
            return true;
        }

        TypeMirror target = expected.asType();

        for (Element element :
                roundEnv.getElementsAnnotatedWith(CheckReturn.class)) {
            if (element.getKind() != ElementKind.METHOD) {
                continue;
            }

            ExecutableElement method = (ExecutableElement) element;
            TypeMirror returned = method.getReturnType();

            // Avoid drawing wrong conclusions when the type is still erroneous/unresolved.
            if (returned.getKind() == TypeKind.ERROR) {
                continue;
            }

            if (!types.isAssignable(returned, target)) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "@CheckReturn requires a type assignable to "
                                + "java.lang.CharSequence",
                        method);
            }
        }
        return true;
    }
}
~~~

Explanation of key lines:

1. `getElementsAnnotatedWith(CheckReturn.class)` returns **actual declarations** annotated; no need to search for `@CheckReturn` strings in source.
2. `ElementKind.METHOD` confirms the element is a method. `@Target(METHOD)` already enforces this; the check branch still illustrates cautious handling.
3. `((ExecutableElement) element).getReturnType()` retrieves the `TypeMirror` of the return type resolved by the compiler, rather than a text signature.
4. `elements.getTypeElement("java.lang.CharSequence").asType()` supplies the target type in the compiler model.
5. `types.isAssignable(returned, target)` checks **Java's type assignability relationship**. This check is not limited to manually listed classes or names ending with some suffix.
6. `Messager.printMessage(ERROR, ..., method)` attaches the error to the method declaration, helping users pinpoint the cause instead of emitting out-of-band logs via `System.out.println`.
7. `return true` states this processor **claims** the annotation types it processes. Other processors are not expected to keep processing the same annotation in that dispatch pass; choosing to return `true/false` must match actual processor design.

The `TypeKind.ERROR` branch is a minimalist policy in the example to avoid cascading diagnostics when the compiler already failed to resolve the return type; production processors can defer/record across subsequent rounds per generator and compiler requirements. Never treat `ERROR` as a valid type or silently ignore dependency errors.

### 4.3. File src/main/java/demo/App.java

~~~java
package demo;

import demo.validation.CheckReturn;

public final class App {
    @CheckReturn
    static String first() {
        return "ready";
    }

    @CheckReturn
    static StringBuilder second() {
        return new StringBuilder("built");
    }

    public static void main(String[] args) {
        System.out.println(first());
        System.out.println(second());
    }
}
~~~

Both `String` and `StringBuilder` implement `CharSequence`, so both methods are valid without comparing type name strings.

### 4.4. Compile the Processor Then Compile the Application

From the `project/` directory in Bash, with JDK 17+:

~~~bash
mkdir -p build/processor build/classes

javac --release 17 -encoding UTF-8 -d build/processor src/processor/java/demo/validation/CheckReturn.java src/processor/java/demo/validation/ReturnTypeProcessor.java

javac --release 17 -encoding UTF-8 -cp build/processor -processorpath build/processor -processor demo.validation.ReturnTypeProcessor -d build/classes src/main/java/demo/App.java

java -cp build/classes demo.App
~~~

Stdout of the final `java` command:

~~~text
ready
built
~~~

The first `javac` creates the annotation class and processor class. The second `javac`:

- Uses `-cp build/processor` so application source **sees the annotation type** during compilation.
- Uses `-processorpath build/processor` so the compiler **loads the processor implementation**.
- Uses `-processor demo.validation.ReturnTypeProcessor` to select the exact processor to run, without relying on auto-discovery via `META-INF/services`.
- Uses `-d build/classes` to write application class files; processor class outputs remain separated in `build/processor`.

On PowerShell, you can replace `mkdir -p build/processor build/classes` with:

~~~powershell
New-Item -ItemType Directory -Force build/processor, build/classes | Out-Null
~~~

The `javac` commands above have only one directory per classpath/processorpath so no separator change is needed; when adding multiple entries, Unix uses `:` and Windows uses `;`.

### 4.5. Case Rejected by the Processor

Create a standalone file **src/main/java/demo/BadApp.java**:

~~~java
package demo;

import demo.validation.CheckReturn;

public final class BadApp {
    @CheckReturn
    static Object invalid() {
        return "text";
    }
}
~~~

Compile BadApp separately with the created processor:

~~~bash
javac --release 17 -encoding UTF-8 -cp build/processor -processorpath build/processor -processor demo.validation.ReturnTypeProcessor -d build/classes src/main/java/demo/BadApp.java
~~~

This is a **command designed to fail**: the *declared* type of `invalid()` is `Object`, which cannot be directly assigned to a `CharSequence` variable. The fact that the method body happens to return a `String` does not change the declared return type. The compiler receives a `Diagnostic.Kind.ERROR` with the message:

~~~text
@CheckReturn requires a type assignable to java.lang.CharSequence
~~~

Do not expect the entire stderr (file, line, caret, error count) to look identical across all JDK versions. The processor does not run the `BadApp` program; the error occurs right at compile time.

**Only changing the return type to `String` or a genuinely matching type**, if the API contract permits, is a valid way to satisfy the condition. Disabling the processor or comparing `Object` name suffixes does not solve the semantics being checked.

## 5. Three Distinct Type Relationships: Same Type, Subtype, Assignable

The following checks have different meanings:

| API | Question | Example |
| --- | --- | --- |
| `types.isSameType(a, b)` | Do two TypeMirrors describe the same type? | `String` and `String` |
| `types.isSubtype(a, b)` | Is type a a subtype of b? | `String` is a subtype of `CharSequence` |
| `types.isAssignable(a, b)` | Is a value of type a assignable to a variable of type b? | `int` can be assigned to `long` via widening primitive conversion |
| `types.erasure(a)` | What is the type after erasing generic type arguments? | `List<String>` has erasure `List` |
| `types.directSupertypes(a)` | What are the direct supertypes? | `String` has its relevant supertypes |

**Argument order matters:** `isAssignable(sourceType, destinationType)`. Swapping the two arguments checks the opposite direction.

For example, `Integer` being a subtype of `Number` does not make `List<Integer>` a subtype of `List<Number>`; Java generics are not covariant that way. However, `List<Integer>` is assignable to `List<? extends Number>` under wildcard rules. Comparing strings `"java.util.List<java.lang.Integer>"` and `"java.util.List<? extends java.lang.Number>"` cannot express all these relationships.

`isSameType` also has a **notable exception from the API contract**: when an argument is a wildcard type, the method returns false, even when passing the very same wildcard TypeMirror twice. Do not write `isSameType(w, w)` and conclude the model is broken. When working with wildcards/capture, choose the appropriate relational operator and check `TypeKind`.

`isAssignable` under assignment conversion is also not strictly synonymous with `isSubtype`; there are widening/boxing or unchecked conversions evaluated by the language model according to Java rules. If the requirement is “must implement an interface”, `isSubtype` usually expresses it more accurately; if the requirement is “return value can be assigned to CharSequence”, `isAssignable` fits better for the example above.

## 6. Do Not Parse Type Names to Handle Generics and Wildcards

A type expression such as:

~~~java
// Source type illustration:
java.util.Map<String, java.util.List<? extends Number>>
~~~

contains multiple levels of `DeclaredType` and a `WildcardType`. Manually splitting strings by commas, `<`, or `>` breaks easily as nesting deepens or when encountering type annotations, raw types, capture variables, and type variables.

In a processor, the right path is:

1. Check `mirror.getKind() == TypeKind.DECLARED`.
2. Cast `DeclaredType declared = (DeclaredType) mirror`.
3. Read `declared.asElement()` to identify the element owning the type declaration.
4. Read `declared.getTypeArguments()` for type arguments; traverse recursively using `TypeKind`.
5. For `TypeKind.WILDCARD`, use `WildcardType.getExtendsBound()` or `getSuperBound()` instead of parsing `?` characters and whitespace.
6. For `TypeKind.ARRAY`, use `ArrayType.getComponentType()`, without inferring from a `[]` suffix.
7. For `TypeKind.TYPEVAR`, use `TypeVariable.asElement()` and bounds via the model; do not try searching for a top-level class named `T`.

Short structural inspection snippet (used inside a processor when `TypeMirror mirror` is already available):

~~~java
// Fragment, not a standalone program:
if (mirror.getKind() == TypeKind.DECLARED) {
    DeclaredType declared = (DeclaredType) mirror;
    TypeElement raw = (TypeElement) declared.asElement();
    String owner = raw.getQualifiedName().toString();
    for (TypeMirror argument : declared.getTypeArguments()) {
        // Check each TypeKind/type relationship using Types.
    }
}
~~~

The `owner` string here is used to **display the declaration name**, not to infer inheritance relationships or generic compatibility.

If needing to construct the `List<String>` type in the compiler model, retrieve the `TypeElement`s of `java.util.List` and `java.lang.String`, then call:

~~~java
// Fragment inside processor:
TypeElement list = elements.getTypeElement("java.util.List");
TypeElement str = elements.getTypeElement("java.lang.String");
if (list != null && str != null) {
    DeclaredType listOfString = types.getDeclaredType(list, str.asType());
    // This is the List<String> model, not a class named List<String>.
}
~~~

`Elements.getTypeElement("java.util.List<java.lang.String>")` is not a valid way to retrieve a parameterized type. Do not use a JAR/source file's qualified name as a “generic type string” to replace `DeclaredType`.

## 7. asMemberOf: Same Method Whose Signature Changes by Generic Owner

Consider:

~~~java
// Generic model illustration; not a standalone file to run.
class Box<T> {
    T get() { return null; }
}

class StringBox extends Box<String> {
}
~~~

`get()` is declared in `Box<T>`, so at **the declaration site** the return type is type variable `T`. However, when viewing that method as a member of `Box<String>` or subtype `StringBox`, API users see the return type replaced with `String`.

Do not take `method.getReturnType().toString()` and replace `T` with `String` as text: this approach breaks with multiple type variables, nested generics, bounds, and inheritance chains.

Use:

~~~java
// Fragment inside processor; assume already available:
//   DeclaredType viewedAs
//   ExecutableElement inheritedGet
//   Types types
TypeMirror viewedMember = types.asMemberOf(viewedAs, inheritedGet);
if (viewedMember.getKind() == TypeKind.EXECUTABLE) {
    ExecutableType signature = (ExecutableType) viewedMember;
    TypeMirror actualReturn = signature.getReturnType();
    // actualReturn reflects the type of get() viewed from viewedAs.
}
~~~

`viewedAs` must genuinely be a declared type of which that method can be viewed as a member. That is why the `asMemberOf` method accepts **both owner context and element**, instead of accepting only a signature string. It handles generic substitution accurately according to the Java Language Specification.

When needing to view inherited members, use `elements.getAllMembers(typeElement)`; `element.getEnclosedElements()` primarily returns directly declared members. If wanting to filter methods/fields, use `ElementKind` or `ElementFilter.methodsIn(...)` for a properly typed list.

**Note:** `getAllMembers` does not automatically replace every accessibility or overload check specific to a processor's goal. The set of members and whether a caller in another package/module has permission to use a member are two separate questions.

## 8. Avoiding Guessing Overrides and Method Signatures from Text

Two methods sharing the same simple name `run` do not necessarily override each other: they might be overloads with different parameters, a static method hiding another method, or declarations not in a valid inheritance relationship.

APIs to use:

- `elements.overrides(overrider, overridden, contextType)`: asks whether an `ExecutableElement` overrides the other method **when viewed in a type context**.
- `elements.hides(hider, hidden)`: asks whether a type/method/field hides the other declaration per Java rules.
- `types.isSubsignature(methodType1, methodType2)`: compares method signature relationships per language rules, without relying on `toString()`.
- `types.asMemberOf(contextDeclaredType, methodElement)`: retrieves the signature after generic substitution in the examined owner.

For a method `m(List<String>)`, text and erasure can match or differ according to rules that string comparison cannot adequately express. Use the compiler model instead of comparing character counts or method names.

`Elements.getBinaryName(TypeElement)` can return a name different from `getQualifiedName()` for member/nested classes: for example, the binary name has `$` like `Outer$Inner`, while the qualified name uses a dot `Outer.Inner`. Pick the right name type for your purpose (displaying Java source, class-file lookup, code generation), rather than manually writing regex to replace `.` with `$` in every case.

## 9. Annotation Class<?> and MirroredTypeException

Suppose an annotation declares the attribute:

~~~java
// Illustrative fragment, not a standalone file.
@interface UsesType {
    Class<?> value();
}
~~~

When a processor reads `@UsesType(SomeClass.class)`, class `SomeClass` may **not yet be loaded** into the JVM running the processor. Calling `annotation.value()` on the annotation proxy supplied by the language model can throw `MirroredTypeException`; this is part of the annotation processing mechanism, not an indication that the class is broken.

There are two suitable approaches:

1. Read `AnnotationMirror` and `AnnotationValue` via `Element.getAnnotationMirrors()` (or use `Elements.getElementValuesWithDefaults` when default values are needed). Class-typed attributes are normally represented as `TypeMirror`.
2. If intentionally using the annotation proxy API, handle `MirroredTypeException` and call `getTypeMirror()` instead of trying to load the class with reflection.

Once you have the `TypeMirror`, use `Types` to query type relationships; do not force `Class<?>.getName()` as the source of truth for code being compiled.

For repeatable annotations, inherited annotations, and type-use annotation cases, the model API has specific details. Do not treat parsing source text as equivalent to the compiler's symbol table.

## 10. Handling Error Types, Rounds, and Incomplete Models

Annotation processing can span **multiple rounds**. When a processor creates source in one round, the compiler can receive those sources in the next round. Therefore, a type unresolved initially does not necessarily retain the same status across all rounds.

What you need to know:

- `TypeKind.ERROR` represents a type that cannot be validly resolved in the current model. It can appear when a dependency is absent or generated source is not yet ready.
- `getTypeElement(...)` may return `null` when lookup fails or is not uniquely resolved; do not force null into an arbitrary type string.
- `roundEnv.processingOver()` indicates the final round meant to wrap up processing; `roundEnv.errorRaised()` indicates error status related to the previous round per contract.
- `Messager` should attach diagnostics to the relevant `Element`, `AnnotationMirror`, or `AnnotationValue` whenever possible, so users see the exact location.
- `Filer` must only be used to create new outputs per contract. Do not manually edit user source or overwrite the same generated file across rounds.
- Model objects are meaningful only within the active processing environment context; do not serialize `TypeMirror.toString()` as a semantic cache across separate builds.

A large processor can choose to **defer** processing elements containing `ErrorType` until code generation finishes, or report contextual errors when rounds end, depending on the ecosystem. Do not conclude “not assignable” merely because early on the compiler has not yet resolved a type.

**Distinguishing ERROR and NONE/VOID:** `TypeKind.ERROR` indicates a resolution issue; `TypeKind.VOID` is the `void` return type; `TypeKind.NONE` is a pseudo-type in places lacking an actual type. Do not assume every `TypeMirror` is a `DeclaredType` and cast directly.

## 11. Common Processor Design Mistakes

| Mistake | Why It Is Dangerous | Replacement |
| --- | --- | --- |
| `mirror.toString().equals("java.lang.String")` | Only matches one printed form, misses subtypes/aliases/generics | `Elements.getTypeElement` + `Types.isSameType/isAssignable/isSubtype` |
| `printed.contains("List")` | Other package/class names can contain the same substring | Check `DeclaredType.asElement()`, `getQualifiedName()` |
| Parsing `List<Map<A,B>>` by commas | Nested generics and wildcards break splitting | `getTypeArguments()`, `TypeKind`, `WildcardType` |
| Comparing `typeMirror1 == typeMirror2` | Object identity is not Java type equality | `types.isSameType` with wildcard caveat |
| Using `Class.forName` to resolve user source | Code is not compiled/loaded yet; processor classloader differs | `Elements.getTypeElement` |
| Using `method.toString()` to detect overrides | Lacks owner, inheritance, and overload context | `Elements.overrides`, `Types.isSubsignature` |
| Taking return type of generic method at declaration and substituting T manually | Substitution can be multi-level and nested | `Types.asMemberOf` |
| Comparing class name `endsWith("Entity")` to check interface implementation | Matching names do not prove relationship | `Types.isSubtype` / `isAssignable` |
| Ignoring null or ErrorType | Processor can crash or emit cascading false errors | Check lookup, `TypeKind.ERROR`, round policy |
| Calling `getTypeElement("List<String>")` | API finds **class declarations**, not parameterized uses | `getTypeElement("java.util.List")` + `getDeclaredType` |
| Using erasure to decide all generic compatibility | Erasure strips type argument info | Erase only when actually required (e.g., signature-level logic) |
| Assuming `getAllMembers` filters caller access | Inheritance/membership is not an accessibility API for every caller | Check modifiers, packages, JPMS, and context |
| Printing errors with System.out | Loses source location and javac diagnostic mechanism | `Messager.printMessage` |

Some tasks **genuinely need string names**: generating file names, generating source code, logging, and matching explicitly configured annotation names. In those cases use `Name`, `getQualifiedName()`, or `getBinaryName()` as appropriate; simply avoid turning **type relationship checks** into string processing.

## 12. Compile-Time Verification Process for a Processor

For the `@CheckReturn` example, you can verify step by step:

1. Compile both annotation and processor files into `build/processor`.
2. Compile `App.java` with all of `-cp`, `-processorpath`, and `-processor`; confirm the processor does not block `String` and `StringBuilder`.
3. Run `java -cp build/classes demo.App`; confirm the two lines `ready`, `built`.
4. Compile `BadApp.java` separately; confirm **compilation fails** and a processor-generated diagnostic appears for the `Object` return type.
5. Test a method returning an interface implementation other than `String` to verify the processor does not rely on type names.
6. Test `void`, primitive, or unresolved declared types to observe the policy; compare results with `TypeKind` and `isAssignable`.
7. For generic methods or inherited members, use `Types.asMemberOf` and type relations to verify signatures after substitution.
8. Verify on clean build/CI: processor artifacts must be built first, processorpath and compile classpath must be right, without picking up stale outputs.

**Reading compiler logs accurately:** when `BadApp` is rejected, it is an error **emitted by the annotation processor via Messager** during compilation. You do not need to and cannot run `BadApp` to reproduce that error. Do not claim stderr has an exact fixed line count since `javac` output varies across environments.

## 13. Integrating with Gradle/Maven Without Confusing Dependency Roles

In real projects, the processor typically sits in a separate artifact from the annotations/API to avoid pulling processor implementations into application runtime.

With Gradle, the dependency configuration idea is:

~~~groovy
dependencies {
    compileOnly project(':annotations')
    annotationProcessor project(':processor')
}
~~~

This is an **illustrative fragment**, requiring corresponding `annotations` and `processor` subprojects, and the processor artifact must see its annotation API. When the annotation is also needed at runtime, choose an appropriate actual scope rather than defaulting to compileOnly.

With Maven, processors are declared via Maven Compiler Plugin / annotation processor paths configuration matching the plugin version and JDK. Do not randomly replace processor paths with runtime dependencies. Processor code uses `javax.lang.model` in the JDK `java.compiler` module; it is not a reflection API reading already-loaded classes.

When packaging a processor for auto-discovery, provide the proper service provider declaration or processor declaration mechanism supported by the toolchain. The explicit `-processor` example in this lesson is intentional to avoid relying on service discovery while letting learners see exactly which processor runs.

## 14. Checklist: Which Decisions Must Rely on the Language Model?

Check each item sequentially before emitting a diagnostic from a processor:

- **Am I looking at a declaration or a type?** If a declaration, use `Element`; if relationships/type arguments, use `TypeMirror` and `Types`.
- **Can the name be uniquely looked up?** `getTypeElement` may return null; on module systems there are module-scoped overloads.
- **Is the TypeKind right?** `DeclaredType`, array, type variable, wildcard, error, void, and primitive cannot all be cast uniformly.
- **Do I want to check exact equality, subtype, or assignability?** Choose `isSameType`, `isSubtype`, or `isAssignable` with the right semantics and parameter direction.
- **Am I losing generic information?** Avoid `erasure` when type arguments matter; use `getTypeArguments`, `capture`, or `asMemberOf` where appropriate.
- **Am I guessing overrides/method signatures?** Use `Elements.overrides` or methods of `Types`.
- **Is an unresolved type being wrongly condemned?** Handle `ErrorType` and processing rounds under a clear policy.
- **Is the diagnostic attached to the right element?** `Messager` is better than printing to console when wanting users to pinpoint errors.
- **Does the problem truly need text or semantics?** Text is for display and output names; type relationships belong to language model APIs.

**Conclusion:** `Elements` helps locate exact *Java declarations* and relationships between declarations; `Types` helps query exact *relationships among Java types*. `TypeMirror.toString()` is merely a diagnostic-aiding representation, not a parser or basis for defining type compatibility. Building processors around these two utilities keeps code accurate across generics, inheritance, nested types, and compiler rounds, while avoiding false errors when users rewrite types yet preserve semantics.

## References

- [Java SE 17: Elements API](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/util/Elements.html).
- [Java SE 17: Types API](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/util/Types.html).
- [Java SE 17: ProcessingEnvironment API](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/ProcessingEnvironment.html).
- [Java SE 17: TypeMirror and TypeKind](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/type/TypeMirror.html).
