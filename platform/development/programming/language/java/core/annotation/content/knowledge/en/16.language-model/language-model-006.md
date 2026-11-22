# Elements and Types for Inspecting Names, Types, and Type Relationships in Java

In an **annotation processor** and compile-time Java code analysis tools, the two central interfaces are **`javax.lang.model.util.Elements`** and **`javax.lang.model.util.Types`**. They help determine what name a declaration has, what kind it belongs to, what members it has, or whether a type is a subtype of or assignable to another type. Those questions should be answered using the **compiler language model**, rather than trying to load the source being compiled with `Class.forName(...)`.

- **`Elements`** operates on **declarations** (`Element`): package, class, interface, field, method, constructor, parameter, type parameter; supporting lookup, members, override, hiding, and annotation mirrors.
- **`Types`** operates on **types** (`TypeMirror`): same type, subtype, assignment compatibility, generic instantiation, erasure, type substitutions, boxing/unboxing, and wildcard types.
- Both are provided by `ProcessingEnvironment` while `javac` runs the processor.

~~~java
Elements elements = processingEnv.getElementUtils();
Types types = processingEnv.getTypeUtils();
~~~

The snippet above is written **inside an initialized annotation processor**, not a program with `main`. Section 7 provides an example consisting of two Java files that can be compiled/run with `--release 17`.

## 1. How Does a Declaration (Element) Differ from a Type (TypeMirror)?

Consider:

~~~java
class Base<T> {
    T value;
}

class Derived extends Base<String> {}
~~~

There are two very different questions:

1. **Where is `Base` declared, and what are its simple name and full name?** The appropriate object is the `TypeElement` of `Base`.
2. **Is `Derived` a subtype of `Base<String>`?** The objects to compare are `TypeMirror` instances representing **types**, where `Base<String>` takes the form of a `DeclaredType`.

The field `Base.value` is a `VariableElement`. In the `Base<T>` class itself, the field type is represented as `T`; when referencing that field in `Derived extends Base<String>`, the appropriate type becomes `String`. `Elements` finds the **field declaration**, whereas `Types.asMemberOf` derives the **type of the field in another context**.

| Construct | Meaning | Example |
| --- | --- | --- |
| `Element` | A declaration known to the compiler | `Base`, `value`, `get()` |
| `TypeElement` | A class/interface/annotation/enum/record declaration | `demo.Derived` |
| `VariableElement` | A field or parameter declaration | `value` |
| `ExecutableElement` | A method or constructor declaration | `get()` |
| `PackageElement` | A package declaration | `demo` |
| `TypeMirror` | A Java type in the type system | `String`, `List<String>` |
| `DeclaredType` | A declared reference type, which may carry generic arguments | `Base<String>` |
| `Elements` | Operations on elements/symbols | `getTypeElement`, `getAllMembers` |
| `Types` | Operations on type mirrors | `isSubtype`, `isAssignable` |

**A `TypeMirror` cannot be replaced by a plain string name.** Two classes with the same simple name can still have different qualified names. Conversely, a type has generic instantiation and subtype information that a declaration name alone is insufficient to represent.

## 2. Obtaining Elements and Types in the Proper Processing Lifecycle

A processor typically extends `javax.annotation.processing.AbstractProcessor` and overrides:

~~~java
@Override
public boolean process(Set<? extends TypeElement> annotations,
                       RoundEnvironment roundEnv) {
    Elements elements = processingEnv.getElementUtils();
    Types types = processingEnv.getTypeUtils();
    // Analyze declarations/types in the current compilation round.
    return false;
}
~~~

This is an **illustrative snippet**, assuming the necessary imports are present and it resides inside an `AbstractProcessor` subclass. The complete code is in Section 7.

- `processingEnv` is provided by the compiler when the processor initializes; do not manually instantiate `new Elements()` or `new Types()` because they are interfaces.
- `RoundEnvironment` provides elements belonging to the current processing round, including `getElementsAnnotatedWith(...)`.
- Annotation processing can consist of **multiple rounds** if the processor generates additional source files; `roundEnv.processingOver()` indicates the ending round.
- Elements and TypeMirrors belong to the **compilation environment**, not runtime `Class`/`Method` objects that can be arbitrarily retained across different runs.

The standard packages remain **`javax.lang.model.element`**, **`javax.lang.model.type`**, **`javax.lang.model.util`**, and **`javax.annotation.processing`**. Do not change them to a `jakarta.lang.model` package name just because other frameworks have migrated to Jakarta.

## 3. Using Elements to Inspect Names and Members

### 3.1. Looking Up by Canonical Name

~~~java
TypeElement type = elements.getTypeElement("demo.Derived");
if (type == null) {
    // Could not resolve a type with this name in the compilation environment yet.
}
~~~

`Elements.getTypeElement(CharSequence)` looks up a `TypeElement` by name and returns `null` if not found. Data comes from the sources, classpath, and module path that the compiler is processing. Since Java 9, there is an overload taking a `ModuleElement` when you need to specify the module containing the type.

Once you have a `TypeElement`:

~~~java
Name simple = type.getSimpleName();       // Derived
Name qualified = type.getQualifiedName(); // demo.Derived
ElementKind kind = type.getKind();         // CLASS
TypeMirror mirror = type.asType();
~~~

- `getSimpleName()` gets the simple name; `getQualifiedName()` gets the full name.
- `Name.contentEquals("Derived")` compares content against a string; `Name` is not simply a String.
- `Elements.getBinaryName(TypeElement)` returns the binary name when needed at the JVM level; nested classes can differ in naming compared to the qualified name.
- `getKind()` helps verify that a declaration is `CLASS`, `INTERFACE`, `FIELD`, `METHOD`, `PARAMETER`... before casting.

Avoid doing `(TypeElement) element` if you do not yet know `element.getKind()`. For processors handling multiple groups of annotation targets, an invalid cast is a very common real-world bug.

### 3.2. Direct Declarations vs. Inherited Members

~~~java
var ownDeclarations = type.getEnclosedElements();
var allMembers = elements.getAllMembers(type);
~~~

- `getEnclosedElements()` lists elements **declared directly** inside the type (including the corresponding elements modeled by the compiler).
- `getAllMembers(type)` also lists **inherited members**; not every element in the list is declared by `type`.
- `member.getEnclosingElement()` helps identify where a field/method is declared.
- Do not rely on the returned array/list order as a fixed sorting rule for generated code.

For example, `Derived` inherits the field `Base.value`. `Derived.getEnclosedElements()` does not contain this declaration as its own field, whereas `elements.getAllMembers(derived)` can find that field. To compute the **type of the inherited field after substituting T with String**, you need `Types.asMemberOf`, not just `VariableElement.asType()` of the original field.

### 3.3. Checking Overriding and Hiding According to Java Rules

~~~java
boolean override = elements.overrides(
    derivedMethod, baseMethod, derivedTypeElement
);
~~~

`Elements.overrides(overrider, overridden, type)` returns a result based on Java method overriding rules, not merely matching names. Two methods with the same name but different parameters do not necessarily override each other. Nor is static hiding treated as instance overriding.

`Elements.hides(hider, hidden)` is used for the **hiding** relationship in the cases defined by the language. When writing a processor that checks an interface contract or an annotation placed on a method, determine whether you need overriding or hiding and then choose the right API.

### 3.4. Reading Annotations via the Compile-Time Model

`Element.getAnnotationMirrors()` returns `AnnotationMirror` instances for annotations **declared directly** on the element, without requiring the annotation to have `RetentionPolicy.RUNTIME`. `Elements.getAllAnnotationMirrors(element)` can additionally include annotations inherited according to `@Inherited` rules for class declarations; this does not mean annotations from a parent method are carried over to an overriding method.

To retrieve annotation element values including defaults, use `elements.getElementValuesWithDefaults(annotationMirror)`. This differs from reading via runtime reflection:

- An annotation processor works **at compile time** and can see `SOURCE` annotations.
- Runtime reflection generally requires `RUNTIME` annotations and compiled binaries.
- `AnnotationMirror` and `Class<?>, java.lang.annotation.Annotation` are two different models; do not rely on `Class.forName` to query Java sources that do not yet have bytecode.

## 4. Using Types to Inspect Types and Type Relationships

### 4.1. isSameType — Do Two TypeMirrors Have the Same Type?

~~~java
boolean same = types.isSameType(left, right);
~~~

`Types.isSameType` compares types according to the Java type system model. Do not use `left == right`, `left.equals(right)`, or compare two `toString()` outputs as a definitive semantic comparison; the same type may be represented differently across compiler implementations.

For example, `List<String>` and `List<Object>` do not have the same type. Note that the API has a special rule: **two wildcard types are not considered the same type by `isSameType`** according to this method's contract.

### 4.2. isSubtype — Subtype Relationship

~~~java
boolean childSubtype = types.isSubtype(child.asType(), baseOfString);
~~~

`isSubtype(t1, t2)` asks whether t1 is a **subtype** of t2. With `Derived extends Base<String>`, `isSubtype(Derived, Base<String>)` is true, while `isSubtype(Base<String>, Derived)` is false.

Construct the proper `Base<String>` type instead of guessing from the class declaration:

~~~java
TypeElement base = elements.getTypeElement("demo.Base");
TypeElement stringType = elements.getTypeElement("java.lang.String");
DeclaredType baseOfString = types.getDeclaredType(
    base, stringType.asType()
);
~~~

`base.asType()` represents the type associated with the generic declaration `Base<T>`, which is **not synonymous** with `Base<String>`. Constructing a `DeclaredType` with an explicit type argument ensures that the type relationship check accurately reflects the specialization.

### 4.3. isAssignable — Is It Assignable?

~~~java
boolean canAssign = types.isAssignable(sourceType, targetType);
~~~

Unlike `isSubtype`, `Types.isAssignable` checks whether a value of one type can be assigned to a variable of the other type according to Java assignment compatibility. Certain conversion cases (such as boxing/unboxing) can cause the results of these two checks to differ.

An important example:

~~~java
List<String> names;
List<Object> objects;
~~~

These two lines are **illustrative field declarations**, assuming `java.util.List` is imported. Java generics are **invariant**: `String <: Object` **does not imply** `List<String> <: List<Object>`. Therefore, `types.isAssignable(names.asType(), objects.asType())` is false when the mirrors correspond to those two declarations.

If an API wants to accept `List<? extends Object>`, you must obtain the exact wildcard type according to the JLS and compare against that type; do not "temporarily drop" generic arguments just to make tests pass.

### 4.4. erasure — Intentionally Stripping Generic Information

~~~java
TypeMirror erased = types.erasure(names.asType());
~~~

For `names` with type `List<String>`, the result is displayed as `java.util.List`. Erasure is useful when dealing with JVM-level signatures or compatibility, but it **loses** generic type argument information. If the goal is to distinguish `List<String>` from `List<Object>`, do not perform erasure before checking.

### 4.5. asMemberOf — Substituting Generic Parameters in a Subclass

Suppose:

~~~java
class Base<T> { public T value; }
class Derived extends Base<String> {}
~~~

Use:

~~~java
DeclaredType derivedType = (DeclaredType) derived.asType();
TypeMirror inheritedFieldType = types.asMemberOf(
    derivedType, baseValueField
);
~~~

`baseValueField` is the `VariableElement` of the `Base.value` declaration. The result when viewed from `Derived` is `java.lang.String`, not `T`. This API is very important when a processor generates serializers/mappers/validators for members inherited from generic base classes.

**Do not** call `asMemberOf` with an element that is not a valid member of the containing type; the API may throw `IllegalArgumentException`. Verify membership and `TypeKind` before casting a `TypeMirror` to `DeclaredType`.

## 5. From Elements to Types: A Practical Inspection Workflow

A safe workflow consists of:

1. **Select the symbol to analyze**: `elements.getTypeElement(qualifiedName)` or receive an `Element` from `RoundEnvironment`.
2. **Check existence and the right ElementKind**: do not dereference when `null`, and do not cast before verifying whether it is a field/method/type.
3. **Find the required member**: `getEnclosedElements` for direct declarations, `getAllMembers` if inherited members are needed.
4. **Obtain the TypeMirror**: `element.asType()`; when generic substitution is needed, use `types.asMemberOf` within the appropriate containing type.
5. **Choose a clear type question**: same type (`isSameType`), subtype (`isSubtype`), assignment (`isAssignable`), or erasure (`erasure`).
6. **Compare method relationships**: use `elements.overrides` or `elements.hides` instead of manually comparing names.
7. **Report diagnostics at the proper source**: production tools should use `processingEnv.getMessager().printMessage(Diagnostic.Kind.ERROR, msg, element)` pointing to the relevant element.

| What to Check | Appropriate API | Avoid |
| --- | --- | --- |
| Full class name | `TypeElement.getQualifiedName()` | Comparing only `getSimpleName()` |
| Whether a type exists in the current build | `elements.getTypeElement(...)` | `Class.forName` inside a processor |
| Direct declarations only | `getEnclosedElements()` | Using the inherited list and treating all items as direct |
| Including inherited members | `elements.getAllMembers(...)` | Scanning only the subclass's source fields |
| Type equivalence | `types.isSameType(...)` | Comparing `toString()` |
| Subtype–supertype relationship | `types.isSubtype(...)` | Parsing generic names as strings |
| Assignment compatibility | `types.isAssignable(...)` | Assuming it is identical to `isSubtype` |
| Generic substitution | `types.asMemberOf(...)` | Using the original member's type `T` as the specialized type |
| Method overriding | `elements.overrides(...)` | Comparing only method names |
| Compile-time annotation metadata | `getAnnotationMirrors()`, `Elements.getElementValuesWithDefaults` | Relying solely on runtime reflection |

## 6. What Problem Does the Example Solve?

We will inspect the following declarations inside an **annotation processor**:

- `demo.Base<T>` contains a field `T value` and a method `T get()`.
- `demo.Derived extends Base<String>` inherits the field, overrides the method with `String get()`, and has two fields `List<String> names`, `List<Object> objects`.
- The processor will look up the name `demo.Derived`, verify its kind/supertype, check subtype/assignability/generic invariance, find the inherited field, and verify `asMemberOf` and the override relationship.
- The processor also attempts to look up an absent type to demonstrate the `null` result.

The example uses **two Java files**, without needing a `main`. Output is printed when **javac compiles the model and invokes the processor**, not when running a program with `java`.

## 7. Complete, Verified Java 17 Example

Create the structure:

~~~text
project/
├── ModelInspector.java
└── demo/
    └── Model.java
~~~

### ModelInspector.java File

~~~java
import java.util.Set;
import javax.annotation.processing.*;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.*;
import javax.lang.model.type.*;
import javax.lang.model.util.*;

@SupportedAnnotationTypes("*")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class ModelInspector extends AbstractProcessor {
    private boolean printed = false;

    @Override
    public boolean process(Set<? extends TypeElement> annotations, RoundEnvironment round) {
        if (printed || round.processingOver()) return false;
        Elements elements = processingEnv.getElementUtils();
        Types types = processingEnv.getTypeUtils();

        TypeElement child = elements.getTypeElement("demo.Derived");
        TypeElement parent = elements.getTypeElement("demo.Base");
        TypeElement string = elements.getTypeElement("java.lang.String");

        VariableElement names = null, objects = null;
        ExecutableElement derivedMethod = null, baseMethod = null;
        VariableElement baseValue = null;
        for (Element e : child.getEnclosedElements()) {
            if (e.getSimpleName().contentEquals("names")) names = (VariableElement) e;
            if (e.getSimpleName().contentEquals("objects")) objects = (VariableElement) e;
            if (e.getKind() == ElementKind.METHOD &&
                    e.getSimpleName().contentEquals("get")) derivedMethod = (ExecutableElement)e;
        }
        for (Element e : parent.getEnclosedElements()) {
            if (e.getSimpleName().contentEquals("value")) baseValue = (VariableElement)e;
            if (e.getKind() == ElementKind.METHOD &&
                    e.getSimpleName().contentEquals("get")) baseMethod = (ExecutableElement)e;
        }
        DeclaredType baseOfString = types.getDeclaredType(parent, string.asType());
        boolean inheritedField = elements.getAllMembers(child).stream()
             .anyMatch(e -> e.getKind() == ElementKind.FIELD &&
                  e.getSimpleName().contentEquals("value"));
        System.out.println("type=" + child.getQualifiedName());
        System.out.println("kind=" + child.getKind());
        System.out.println("simpleName=" + child.getSimpleName());
        System.out.println("supertype=" + child.getSuperclass());
        System.out.println("subtype=" + types.isSubtype(child.asType(), baseOfString));
        System.out.println("assignable=" + types.isAssignable(child.asType(), baseOfString));
        System.out.println("reverseSubtype=" + types.isSubtype(baseOfString, child.asType()));
        System.out.println("sameListType=" + types.isSameType(names.asType(), objects.asType()));
        System.out.println("assignListType=" + types.isAssignable(names.asType(), objects.asType()));
        System.out.println("erasure=" + types.erasure(names.asType()));
        System.out.println("inheritedField=" + inheritedField);
        System.out.println("memberType=" + types.asMemberOf((DeclaredType)child.asType(), baseValue));
        System.out.println("overrides=" + elements.overrides(derivedMethod, baseMethod, child));
        System.out.println("missing=" + (elements.getTypeElement("demo.Missing") == null));
        printed = true;
        return false;
    }
}
~~~

This is a **minimal demo** with hardcoded type/field names. It assumes the elements exist exactly as in the sample source. A general-purpose processor must check for `null` and `ElementKind` before casting so it does not throw `NullPointerException`/`ClassCastException`, while also handling overloads accurately.

### demo/Model.java File

~~~java
package demo;
import java.util.List;

class Base<T> {
    public T value;
    public T get() { return value; }
}

class Derived extends Base<String> {
    public List<String> names;
    public List<Object> objects;
    @Override public String get() { return "ok"; }
}
~~~

Both classes here are package-private and can reside together in the `Model.java` file. A processor in the default package can still find them using `Elements.getTypeElement` when `javac` compiles.

### Compilation Commands and Results

From the `project` directory, using JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 -d processor ModelInspector.java
javac --release 17 -encoding UTF-8 -cp processor -processorpath processor -processor ModelInspector -d classes demo/Model.java
~~~

The first command produces the processor's bytecode. The second specifies it with `-processor ModelInspector`, allowing javac to load it from `-processorpath processor` and print the inspection output directly during compilation. You **do not need** to run `java ModelInspector` because the processor class does not declare `main`.

**Actual stdout of the second javac command** (tested with a JDK using `--release 17`):

~~~text
type=demo.Derived
kind=CLASS
simpleName=Derived
supertype=demo.Base<java.lang.String>
subtype=true
assignable=true
reverseSubtype=false
sameListType=false
assignListType=false
erasure=java.util.List
inheritedField=true
memberType=java.lang.String
overrides=true
missing=true
~~~

### Explanation of Each Result

1. `type`, `kind`, and `simpleName` are retrieved from `TypeElement`; this is declaration information, not runtime `Class<?>`.
2. `supertype=demo.Base<java.lang.String>` shows that the compiler preserves generic argument information in `TypeMirror`.
3. `subtype=true`, `assignable=true`: `Derived` is a subtype of and is assignable to a variable of type `Base<String>`.
4. `reverseSubtype=false`: `Base<String>` is not a subtype of `Derived`.
5. `sameListType=false`: `List<String>` and `List<Object>` have different types.
6. `assignListType=false`: type invariance prevents `List<String>` from being assigned to `List<Object>`.
7. `erasure=java.util.List`: type argument information is removed according to Java erasure.
8. `inheritedField=true`: `Elements.getAllMembers` sees the `value` field of `Base`.
9. `memberType=java.lang.String`: `Types.asMemberOf` substitutes the type variable `T` with `String` when inspecting the field through Derived.
10. `overrides=true`: `Derived.get()` overrides `Base.get()`, including generic return specialization.
11. `missing=true`: the compiler lookup for `demo.Missing` does not find a declaration in this environment, so it returns `null`.

## 8. Common Mistakes

### Comparing TypeMirrors via toString()

`TypeMirror.toString()` is useful for logging but must not be used as a semantic comparator. Generic capture, type variables, and wildcard representations mean that the string representation cannot replace `types.isSameType`, `isSubtype`, or `isAssignable`.

### Confusing Base<T> and Base<String>

`parent.asType()` belongs to the generic declaration, not the `Base<String>` instantiation type needed for checking. You must create a mirror with `types.getDeclaredType(parent, string.asType())` or obtain an actual type mirror that matches the source context.

### Treating Matching Method Names as Overriding

Having the same `getSimpleName()` is not enough; overloads, parameters, static/instance, visibility, generics, and covariance all matter. Use `elements.overrides(overrider, overridden, containingType)`.

### Equating isSubtype and isAssignable

These are two differently defined relationships in Java. `isSubtype` asks about the relationship in the type hierarchy; `isAssignable` evaluates valid assignment, which may involve conversions such as boxing/unboxing.

### Ignoring the Invariance of Generics

`String` being a subtype of `Object` does not automatically make `List<String>` a subtype of `List<Object>`. A processor checking an API with `List<?>`, `List<? extends X>`, or `List<? super X>` needs to construct and inspect the exact mirrors rather than only looking at the element type.

### Using Only getEnclosedElements to Find Inherited Members

`Derived.getEnclosedElements()` does not contain the `Base.value` declaration as a field of Derived. Use `elements.getAllMembers(derived)` and `getEnclosingElement()` to locate the origin; use `asMemberOf` if you need the generic-specialized type.

### Incorrect Casting or Missing Symbols

`getTypeElement` can return `null`. `TypeMirror` has many `TypeKind` values, and you may encounter `ErrorType` in an incomplete compile environment. Check before casting to `DeclaredType` or accessing related elements. Diagnostics should point to the proper source element using `Messager`.

### Using Runtime Reflection Instead of the Compile-Time Model

`Class.forName("demo.Derived")` can fail simply because the Java source has just been read by the compiler and does not yet have bytecode to load. `Elements` and `Types` exist specifically to work with the source/classpath model at compile time.

### Failing to Control Processing Rounds

Annotation processing can run across multiple rounds. Do not print duplicate output or regenerate the same source file on every round. When production code generates files, manage Filer and round semantics according to the processor contract.

## 9. APIs to Learn Next

Related methods in the standard API:

| API | When It Is Useful |
| --- | --- |
| `Types.directSupertypes(type)` | Looking up direct supertypes |
| `Types.boxedClass(primitiveType)` | Converting a primitive type to its boxed class element |
| `Types.unboxedType(type)` | Finding the corresponding primitive type |
| `Types.getArrayType(componentType)` | Creating an array type mirror |
| `Types.getWildcardType(extendsBound, superBound)` | Creating a wildcard with bounds |
| `Types.capture(type)` | Applying capture conversion |
| `Types.isSubsignature(method1, method2)` | Checking the signature relationship of executable types |
| `Elements.getBinaryName(typeElement)` | Retrieving the JVM binary name |
| `Elements.isFunctionalInterface(typeElement)` | Checking whether a type is a functional interface |
| `Elements.getElementValuesWithDefaults(annotationMirror)` | Retrieving the element-value mapping including defaults |

You need to check the exact parameter types of each method. For example, `Types.asMemberOf` requires a `DeclaredType` and an element with valid membership, while `boxedClass` accepts a `PrimitiveType`; every API has preconditions.

## 10. Knowledge Self-Check

**1. How do Elements and Types differ?** `Elements` operates on **declarations/symbols**, while `Types` operates on **Java types** (`TypeMirror`) and relationships between types.

**2. How do you read the simple name and qualified name?** `TypeElement.getSimpleName()` and `getQualifiedName()`; when comparing a `Name` with a string, you can use `contentEquals`.

**3. Why does `elements.getTypeElement("demo.Missing")` return null?** The compiler cannot find a type with that name in the provided compilation environment.

**4. How do you find the `Base.value` field from Derived?** Use `elements.getAllMembers(derived)`, checking `getKind() == FIELD` and `getSimpleName()`; `getEnclosedElements()` only gives direct declarations.

**5. Why is `List<String>` not assignable to `List<Object>`?** Java generic classes are invariant; a subtype of the whole generic type is not inferred solely from the type argument.

**6. How do you get the actual type of the field `Base<T>.value` when referenced through `Derived extends Base<String>`?** `types.asMemberOf((DeclaredType) derived.asType(), baseValueField)` returns `String`.

**7. What is the standard way to check method overriding?** `elements.overrides(childMethod, baseMethod, childType)`; do not compare names manually.

**8. Can a processor read SOURCE-retained annotations?** Yes, because the processor operates on compiler element/annotation mirrors during the compile phase; runtime reflection, on the other hand, does not have SOURCE annotations retained in the target class files.

## 11. Official Documentation

- Java SE 21 API — **Elements**: https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/lang/model/util/Elements.html
- Java SE 21 API — **Types**: https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/lang/model/util/Types.html
- Java SE 21 API — **Element, TypeElement, ExecutableElement**: https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/lang/model/element/package-summary.html
- Java SE 21 API — **TypeMirror, DeclaredType, TypeKind**: https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/lang/model/type/package-summary.html
- Java SE 21 API — **ProcessingEnvironment and AbstractProcessor**: https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/annotation/processing/package-summary.html
- JLS Java SE 21 — **Types, Values, Variables `4** and **Methods `8.4**: https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html and https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4

**Remember:** in an annotation processor, first ask "do I need to inspect a **declaration** or a **type**?". For names, kinds, members, method overriding, and annotations of declarations, choose `Elements`. For equality, subtypes, assignability, erasure, and generic substitution, choose `Types`. Combining both API groups helps your tool enforce accurate Java language semantics rather than relying on guesses from string names or runtime reflection.
