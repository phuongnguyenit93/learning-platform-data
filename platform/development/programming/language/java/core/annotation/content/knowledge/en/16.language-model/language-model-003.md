# TypeMirror and Distinguishing the Type Model from Class at Runtime in Java

In the Java annotation ecosystem, there are two perspectives on data types that need to be distinguished:

- **Compile-time language model:** `javax.lang.model.type.TypeMirror` represents a *Java type* that the compiler or annotation processor is analyzing. It can represent `List<String>`, `T extends Number`, wildcards, arrays, primitive types, and even types that cannot yet be fully resolved.
- **Runtime type object:** `java.lang.Class<?>` represents a class/interface/array/primitive/`void` in the JVM runtime. It is tied to class loading and reflection, not the full syntactic/semantic model of the compiler.

The two models serve different phases. **Do not cast `TypeMirror` to `Class<?>`**, nor assume that a type seen by the processor can already be loaded by the JVM. Annotation processing can run **before the class being processed is compiled into bytecode**.

Example of the same declaration:

```java
import java.util.List;

class Catalog {
    List<String> items;
}
```

- An annotation processor inspecting the `items` field can call `VariableElement.asType()` and receive a `DeclaredType` corresponding to `java.util.List<java.lang.String>`.
- After compilation, `List.class` is a `Class<List>` for the raw type `List` (according to how class literals are typed); there is no `List<String>.class` in Java.
- Runtime reflection **still has** the `Field.getGenericType()` API, which returns `java.lang.reflect.Type` and can report `List<String>` from the generic signature; do not confuse that with `Class<?>` itself holding all generic arguments.

This lesson focuses on using `TypeMirror` properly in **annotation processing, the language model, and type analysis**; the sections on `Class<?>` are used only to clarify the boundary with runtime.

## 1. Which Language Model Does TypeMirror Belong To?

The core APIs of `javax.lang.model` belong to the standard `java.compiler` module. Several related components include:

| API | Question it answers |
| --- | --- |
| `Element` | "Which **declaration/program element** is this?" |
| `TypeElement` | "Which class, interface, enum, record, or annotation type declaration is this?" |
| `VariableElement` | "Which field, parameter, variable, or enum constant is this?" |
| `ExecutableElement` | "Which method, constructor, or annotation element is this?" |
| `TypeMirror` | "What is the **Java type** of the element/expression in the compile-time model?" |
| `TypeKind` | "Which kind does that type belong to: `DECLARED`, `ARRAY`, `TYPEVAR`, ...?" |
| `Types` | "Are two types equal, assignable, in a subtype relationship, or what is the erasure?" |
| `Elements` | "How to look up a declaration by name and read its members and declaration information?" |

Example:

```java
// In a processor, suppose 'field' is a VariableElement for the items field.
TypeMirror type = field.asType();
TypeKind kind = type.getKind();
```

This is an **illustrative snippet**, not a standalone program (it requires `VariableElement`, `TypeMirror`, `TypeKind`, and the `field` variable). When the field is `List<String> items;`, `kind` is typically `TypeKind.DECLARED` because this is a parameterized declared reference type.

**Distinguishing `Element` from `TypeMirror`:**

- `TypeElement` gives you the **declaration of List** — where the name, modifiers, and members reside.
- `DeclaredType` gives you **a specific usage form of the List type**, such as `List<String>` or `List<Integer>`, with different type arguments.
- `VariableElement` gives you the **declaration of the items field**, while `items.asType()` gives the type of the field.

These are not two different names for the same object.

## 2. Common Forms of TypeMirror

`TypeMirror` is the root interface of the family of type-model interfaces. Some representative forms include:

| TypeKind or interface | Java example | How to inspect |
| --- | --- | --- |
| `PrimitiveType` / `INT` | `int` | `getKind()==TypeKind.INT` |
| `DeclaredType` / `DECLARED` | `String`, `List<String>` | `getTypeArguments()` |
| `ArrayType` / `ARRAY` | `String[]` | `getComponentType()` |
| `TypeVariable` / `TYPEVAR` | `T` in `class Box<T>` | `getUpperBound()` |
| `WildcardType` / `WILDCARD` | `? extends Number` | `getExtendsBound()` / `getSuperBound()` |
| `ExecutableType` / `EXECUTABLE` | Signature type of a method/constructor | `getParameterTypes()`, `getReturnType()` |
| `NoType`, `NullType` | Pseudo-types `void`, package/module, or the null type | Check `getKind()` |
| `ErrorType` / `ERROR` | A declared type not yet fully modeled | Needs handling when resolution is incomplete |

Note that `TypeKind` values such as `VOID`, `NONE`, and `NULL` have specific meanings. Not every `TypeMirror` corresponds to a loadable `Class` object. For example, `? extends Number` is merely a **wildcard type**, not a standalone class.

### What Is TypeMirror.toString() Used For?

`TypeMirror.toString()` provides an **informative text representation** of the type. Usually it prints the qualified form such as `java.util.List<java.lang.String>`, which is very useful for logs and error messages.

However, **do not** use that string to infer type-checking rules, parse it manually with regex, or treat it as an absolutely stable identifier. For compiler logic, use `Types`, `TypeKind`, and the specialized interfaces.

## 3. How Does TypeMirror Differ from Class<?>?

| Criterion | `TypeMirror` | `Class<?>` |
| --- | --- | --- |
| Package | `javax.lang.model.type` | `java.lang` |
| Primary usage phase | Compilation, annotation processing, source structure analysis | Runtime, class loading, reflection |
| Meaning | A **Java language type** in the compiler model | A **runtime class object** |
| Parameterized generics | Has `DeclaredType` with its own type arguments | `List.class` does not specifically represent `List<String>` |
| Wildcard/type variable | Has `WildcardType`, `TypeVariable` | A single `Class<?>` does not describe these constructs |
| Primitive | Has `PrimitiveType` | Has, for example, `int.class` |
| Error/incomplete types | May have `ErrorType` | Not an equivalent loadable runtime class |
| Type comparison operations | `Types.isSameType()`, `isAssignable()`, ... | Class comparison, `isAssignableFrom()`, ... |
| Accessing declaration info | `Types.asElement()`, `DeclaredType.asElement()` | `Class.getDeclaredMethods()`, `getDeclaredFields()`, ... |
| Class loader dependency | Does not require loading the modeled class as a runtime class | Tied to runtime class identity and class loader |

**A subtle point about generics:** Java reflection has the interfaces `java.lang.reflect.Type`, `ParameterizedType`, `TypeVariable`, `WildcardType`, and `GenericArrayType`. They can reflect **part of the generic structure stored in the class file** on fields/methods. Therefore, one should not say "runtime has no generic information at all." The accurate statement is: **`Class<?>` by itself does not represent a specific `List<String>`, and runtime reflection does not replace the full `TypeMirror` compiler model**.

### Why Not Convert TypeMirror Directly to Class?

When a processor is analyzing `com.example.FutureService`, the class file might **not have been generated yet**, or the source might even be missing a dependency or have temporary errors. Running `Class.forName("com.example.FutureService")` may fail; even if loading succeeds, it might load an **older version of the class** on the classpath rather than the new declaration currently being compiled.

Do not do this:

```java
// Conceptually WRONG: TypeMirror is not java.lang.Class.
Class<?> runtimeClass = (Class<?>) typeMirror;
```

This is **illustrative code intentionally designed not to compile** (where `typeMirror` has type `TypeMirror`). Calling `typeMirror.getClass()` also only returns the **class of the TypeMirror implementation object inside the compiler**, not the `Class` of the type it represents.

Let the processor handle types using `TypeMirror` and `Types`. Only use `Class<?>` when you are truly in the runtime model and need to interact with loaded classes.

## 4. DeclaredType Preserves Type Arguments Before Erasure

Suppose there are two fields:

```java
import java.util.List;

class Samples {
    List<String> names;
    List<Integer> counts;
}
```

An annotation processor reads:

```java
// The two variables fieldNames and fieldCounts are the respective VariableElement instances.
DeclaredType first = (DeclaredType) fieldNames.asType();
DeclaredType second = (DeclaredType) fieldCounts.asType();

// The resulting type arguments describe String and Integer, respectively.
first.getTypeArguments();
second.getTypeArguments();
```

This is an **illustrative snippet**, not a standalone runnable file. Each `DeclaredType` holds the type information being used (including type arguments), while `first.asElement()` and `second.asElement()` both point to the `java.util.List` declaration in the language model.

At runtime, both `ArrayList<String>` and `ArrayList<Integer>` instances belong to the same runtime class `ArrayList.class`. The difference in source generics undergoes *erasure* in ordinary runtime operations. Nevertheless, `Samples.class.getDeclaredField("names").getGenericType()` can reflect `List<String>` because the declaration carries a generic signature; that is the `java.lang.reflect.Type` API, not `Class<List<String>>`.

### Comparing Types Properly Using Types

`TypeMirror` does not guarantee that a type is always represented by the **same object instance**. Therefore, do not use `==` or `equals()` as a general rule to conclude that two Java types are semantically equivalent.

Inside a processor:

```java
Types types = processingEnv.getTypeUtils();

boolean same = types.isSameType(type1, type2);
boolean assignable = types.isAssignable(type1, type2);
boolean subtype = types.isSubtype(type1, type2);
TypeMirror erased = types.erasure(type1);
```

This is an **illustrative snippet** inside an `AbstractProcessor`; it requires importing `javax.lang.model.util.Types` and having two `TypeMirror` variables named `type1` and `type2`.

- `isSameType(a,b)`: checks whether two types are the same according to language model rules.
- `isAssignable(a,b)`: checks whether one type is assignable to another.
- `isSubtype(a,b)`: checks the subtype relationship (not completely synonymous with assignability).
- `erasure(t)`: returns the type representation after erasure according to `Types` rules.

**Do not equate** `Types.isAssignable(source,target)` at compile time with `Class.isAssignableFrom(otherClass)` at runtime: the latter API works with loaded classes, whereas the former works with Java types that may include generic arguments and constructs that do not exist as runtime classes.

## 5. Where Does an Annotation Processor Obtain TypeMirror From?

An annotation processor typically extends `javax.annotation.processing.AbstractProcessor`, which is invoked by `javac` across rounds during compilation. The key APIs are:

1. `RoundEnvironment.getElementsAnnotatedWith(...)` finds the elements annotated with the annotation to process.
2. `Element.asType()` retrieves the `TypeMirror` of the corresponding element.
3. `TypeMirror.getKind()` inspects the kind of type.
4. `DeclaredType.getTypeArguments()` inspects generic type arguments.
5. `DeclaredType.asElement()` navigates back to the type declaration if its name, modifiers, or members are needed.
6. `ProcessingEnvironment.getTypeUtils()` and `getElementUtils()` provide `Types` and `Elements`.

### Complete Java 17 Example with an Annotation Processor

Use **two files** in the same directory, with no package declaration. The example uses the built-in `@Deprecated` from the JDK as a marker on a field to keep the focus on the type model. The processor only prints metadata and **does not handle API deprecation**.

First file: **`TypeModelProcessor.java`**.

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
import javax.lang.model.type.DeclaredType;
import javax.lang.model.type.TypeMirror;

@SupportedAnnotationTypes("java.lang.Deprecated")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class TypeModelProcessor extends AbstractProcessor {
    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment roundEnv) {
        if (roundEnv.processingOver()) return false;

        for (Element element : roundEnv.getElementsAnnotatedWith(Deprecated.class)) {
            if (element.getKind() != ElementKind.FIELD) continue;

            TypeMirror type = element.asType();
            System.out.println("element=" + element.getSimpleName());
            System.out.println("type=" + type);
            System.out.println("kind=" + type.getKind());
            System.out.println("same=" +
                    processingEnv.getTypeUtils().isSameType(type, type));

            if (type instanceof DeclaredType declared) {
                System.out.println("arguments=" + declared.getTypeArguments());
                TypeElement raw = (TypeElement) declared.asElement();
                System.out.println("raw=" + raw.getQualifiedName());
            }
        }
        return false;
    }
}
```

Second file: **`Catalog.java`**.

```java
import java.util.List;

public class Catalog {
    @Deprecated
    List<String> items;
}
```

Run with JDK 17+ in the exact order:

```bash
javac --release 17 -encoding UTF-8 TypeModelProcessor.java
javac --release 17 -encoding UTF-8 -processor TypeModelProcessor -proc:only Catalog.java
```

The `-processor TypeModelProcessor` flag specifies the processor without needing a `META-INF/services` configuration. The `-proc:only` flag instructs javac to **only process annotations** without generating `Catalog.class`. This is a key point: the processor can still read the `List<String>` type **before the target class is generated**.

Stdout output of the **second** command, verified by running on JDK with `--release 17`:

```text
element=items
type=java.util.List<java.lang.String>
kind=DECLARED
same=true
arguments=java.lang.String
raw=java.util.List
```

Explanation:

- `element=items`: the `VariableElement` representing the field annotated with `@Deprecated`.
- `type=java.util.List<java.lang.String>`: `element.asType()` represents the declared type of the field, including its generic argument.
- `kind=DECLARED`: this is a declared reference type.
- `same=true`: `Types.isSameType(type,type)` confirms that a type equals itself.
- `arguments=java.lang.String`: the list of generic arguments contains one `TypeMirror` representing `String`.
- `raw=java.util.List`: `DeclaredType.asElement()` goes back to the `List` interface declaration, distinct from the type instance `List<String>`.

**The output belongs to the javac/processor phase, not the stdout of `java Catalog`.** `Catalog` has no `main` and is not executed as a program; in the second command, `-proc:only` even intentionally avoids emitting `Catalog.class`.

### Practical Workflow in a Project

Typically, a processor is compiled into a JAR and registered with `ServiceLoader` via `META-INF/services/javax.annotation.processing.Processor` or specified through a compiler/build tool option. The example above uses `-processor` so learners do not need to build a JAR or service file.

A processor can be invoked across multiple rounds. Check `roundEnv.processingOver()` and the relationships among existing/generated elements in each round, rather than assuming the callback occurs only once for the entire build.

## 6. When an Element Is Class<?>: MirroredTypeException

A common situation in **annotation processing** is an annotation that has an element of type `Class<?>`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@interface Mapper {
    Class<?> target();
}

@Mapper(target = java.util.List.class)
class MyMapping {}
```

These are **valid illustrative declarations**. When the processor reads metadata using:

```java
Mapper annotation = typeElement.getAnnotation(Mapper.class);
Class<?> target = annotation.target();
```

This snippet is **not a standalone program**; `typeElement` must be the `TypeElement` corresponding to `MyMapping`. In the `javax.lang.model` context, calling an element method that returns `Class<?>` **is not a reliable path for obtaining a runtime class**. The API can throw `javax.lang.model.type.MirroredTypeException` when the type must be represented as a `TypeMirror` instead of a loaded class.

Pattern for working with the compiler model:

```java
import javax.lang.model.type.MirroredTypeException;
import javax.lang.model.type.TypeMirror;

// In the processor, after verifying annotation != null:
try {
    annotation.target();
} catch (MirroredTypeException ex) {
    TypeMirror referencedType = ex.getTypeMirror();
    // Use Types/TypeKind/DeclaredType to process the type.
}
```

This is only an **API flow illustration**, not a standalone class. When writing a real processor, it is usually preferable to favor **`AnnotationMirror` + `AnnotationValue`**, avoiding trying to go through `Class<?>` in the first place.

### A Robust Approach: AnnotationMirror

`Element.getAnnotationMirrors()` returns the `AnnotationMirror` instances of the element in the language model. Each `AnnotationMirror`:

- Has `getAnnotationType()`, which returns the `DeclaredType` of the annotation type.
- Has `getElementValues()`, which returns a map from `ExecutableElement` to `AnnotationValue` **only for explicitly specified values**.
- Can be combined with `Elements.getElementValuesWithDefaults(annotationMirror)` when default values also need to be included.

For the annotation element `Class<?> target()`, `AnnotationValue.getValue()` in the annotation processing model corresponds to a `TypeMirror` according to the javax.lang.model contract, **without needing to load the target `Class<?>`**.

Illustrative example:

```java
// In the processor, given the selected AnnotationMirror mirror.
var withDefaults =
        processingEnv.getElementUtils().getElementValuesWithDefaults(mirror);

for (var entry : withDefaults.entrySet()) {
    Object value = entry.getValue().getValue();
    // If the element is Class<?>: value represents the type as a TypeMirror.
    System.out.println(entry.getKey().getSimpleName() + "=" + value);
}
```

This is a **code snippet dependent on a processor context** (not a standalone runnable file), suitable when you want to iterate over elements/values without coupling the processor directly to a single annotation proxy type.

If the annotation element has type `Class<?>[]`, the same situation can use `MirroredTypesException` or a list of `AnnotationValue` instances containing the corresponding values; one should not assume the JVM can always load every referenced class.

## 7. Elements, Types, and Looking Up Types by Name

In a processor, the way to "find a type by name" differs from runtime reflection:

```java
// Inside AbstractProcessor:
TypeElement element =
        processingEnv.getElementUtils().getTypeElement("java.util.List");

if (element != null) {
    TypeMirror declared = element.asType();
    System.out.println(declared);
}
```

This is a **code snippet in a processor context**. `Elements.getTypeElement(...)` looks up the type declaration in the **compiler's processing environment**, rather than calling `Class.forName` to load a runtime class. The result can depend on modules, symbol resolution, and whether the type exists in the current model.

If you need to distinguish **a declaration** from **a type using that declaration**:

- `TypeElement` represents the class/interface declaration.
- `TypeElement.asType()` provides the corresponding type of the declaration (which may have type parameters depending on context).
- `Types.getDeclaredType(typeElement, args...)` creates a `DeclaredType` with the type arguments accepted by the compiler model.
- `DeclaredType.getTypeArguments()` reads the type arguments.
- `Types.asElement(type)` is useful when you want to go from a declared type back to its declaration.

When processing module-aware code, the lookup APIs on `Elements` also have overloads taking a `ModuleElement` to avoid ambiguity between types with the same name in different modules. Do not write processors that rely on an arbitrary runtime classpath to replace the compiler's symbol table.

## 8. Type-Use Annotations and TypeMirror

Since Java 8, annotations can be placed not only on declarations but also on **type-use positions**, for example:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;
import java.util.List;

@Target(ElementType.TYPE_USE)
@interface Tag {}

class TypesWithTag {
    List<@Tag String> names;
}
```

These are valid declarations. In a processor, a `TypeMirror` also implements the `AnnotatedConstruct` interface, so it can provide `getAnnotationMirrors()` for **type-use annotations directly on the type construct under inspection**.

For example, when inspecting the `names` field:

1. `field.asType()` is a `DeclaredType` for `List<String>`.
2. Select `DeclaredType.getTypeArguments().get(0)` to get the `TypeMirror` of the `String` type argument.
3. Use `getAnnotationMirrors()` on that argument TypeMirror to inspect the `@Tag` type-use annotation.

Do not equate `field.getAnnotationMirrors()` (annotations **on the field declaration**) with annotations located **on a type argument inside the field's type**.

Runtime reflection provides a different model: `Field.getAnnotatedType()` and `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()`. These two APIs work with metadata retained after compilation and subject to retention conditions, and they do not share the same objects or lifecycle as `TypeMirror` in a processor.

## 9. ErrorType, Multiple Processing Rounds, and Model Limitations

In annotation processing, types are not necessarily all in a fully resolved state. `TypeKind.ERROR` and `ErrorType` can appear when a class/interface type has not yet been fully modeled (for example, due to a missing dependency or source code that will be generated in a subsequent round).

Design processors to:

- Check `getKind()` or use `TypeVisitor` instead of casting every type to `DeclaredType`.
- Handle unresolved types in a controlled manner, especially when the processor supports **generated sources**.
- Avoid retaining `TypeMirror` instances and comparing them by identity or using object hashes as stable keys across different environments/compilations.
- Do not load the class being compiled just to "verify" a type: doing so can hit stale bytecode and a different classloader.
- Emit useful diagnostics via `Messager` if a type/annotation violates the contract.

The `TypeMirror.accept(TypeVisitor,...)` API supports implementing analysis operations by type kind. For a processor that needs to handle arrays, wildcards, generics, and special types, a visitor is usually clearer and more robust than a chain of fixed casts.

**Round-dependent correctness:** When a processor generates additional source files, new declarations can appear in subsequent rounds. Do not assume that every symbol can be fully resolved on the very first pass.

## 10. Common Mistakes When Distinguishing TypeMirror and Class

| Misconception | Accurate rule to remember |
| --- | --- |
| "`TypeMirror` is basically `Class<?>` under another name" | They belong to two different models |
| "Having a `TypeMirror` means you can immediately call `Class.forName`" | The class being processed may not yet exist as a runtime class |
| "`getClass()` on a TypeMirror tells you the represented class" | It returns the class **of the TypeMirror object itself**, not the modeled Java type |
| "`TypeElement` and `DeclaredType` are interchangeable" | One is a declaration; the other is a type using that declaration |
| "`List<String>` cannot be distinguished from `List<Integer>` in the compiler" | `DeclaredType` preserves type arguments; erasure does not remove information from the compiler model |
| "Runtime has no generic APIs at all" | Runtime has `java.lang.reflect.Type` and its subinterfaces, though not the full compiler model |
| "Compare two TypeMirrors using `==`" | Use `Types.isSameType()` when semantic type comparison is needed |
| "Reading `Class<?>` directly from an annotation element during processing is always safe" | It may throw `MirroredTypeException`; use `AnnotationMirror`/`TypeMirror` |
| "An annotation with `Class<?>` means the processor must load that class" | The annotation processing model can describe it with `TypeMirror` without loading the class |
| "Every TypeMirror is a DeclaredType" | Primitives, arrays, wildcards, type variables, error, void, etc. have their own forms |
| "`TypeMirror.toString()` is a canonical identifier for comparing types" | Use operations on `Types` rather than relying on the display string |

## 11. Checklist for Implementing a Safe Annotation Processor

1. **Identify the phase:** are you only processing metadata at compile time or do you need runtime behavior? For compile time, use `javax.lang.model`.
2. **Choose the right Element:** `TypeElement` for type declarations, `VariableElement` for fields/parameters, and `ExecutableElement` for methods/constructors.
3. **Obtain TypeMirror from the right source:** `element.asType()`, type arguments, return type, or bounds as required.
4. **Branch by kind:** avoid blindly casting every type to `DeclaredType`.
5. **Compare using Types:** `isSameType`, `isAssignable`, `erasure`, etc., instead of `==` and strings.
6. **Look up declarations with Elements:** avoid loading classes just to inspect names/relationships in the compiler model.
7. **Read annotation values via the model:** prefer `AnnotationMirror` and default values when needed; handle `Class<?>`-valued elements carefully.
8. **Account for rounds/error types:** generated sources and incomplete symbols can change what is visible across rounds.
9. **Test in two phases:** compile the processor, then compile sample sources with `-processor` and verify the actual diagnostics/output.
10. **Do not mix responsibilities:** Processors analyze/generate code at compile time; `Class<?>` reflection operates on loaded runtime classes.

## 12. Self-Check Questions

**Question 1.** Why can `TypeMirror` model `List<String>` while `List<String>.class` does not exist?

**Answer:** `TypeMirror` belongs to the compile-time type model and `DeclaredType` can hold type arguments. A class literal only references the runtime class `List.class` and does not create a separate class object for each parameterized generic type.

**Question 2.** A processor encounters a `VariableElement` for the field `String[] names`. Should it cast `asType()` to `DeclaredType`?

**Answer:** No. The field type is an array; use `ArrayType` and `getComponentType()`.

**Question 3.** Which API should be used to check whether two `TypeMirror` instances represent the same Java type?

**Answer:** `Types.isSameType()`, rather than inferring from `==` or `toString()`.

**Question 4.** An annotation element has type `Class<?> target();`. Why should a processor not always call `annotation.target()` to obtain a `Class<?>`?

**Answer:** The compilation environment does not guarantee that the referenced class is loaded or even generated yet. Calling it can throw `MirroredTypeException`; the `AnnotationMirror`/`TypeMirror` model is more appropriate.

**Question 5.** When invoking `javac -proc:only` as in the example, can the processor still read `Catalog.items`?

**Answer:** Yes. The processor operates on the language model built by javac; `Catalog.class` does not need to be generated.

**Question 6.** Can runtime reflection read the generic signature `List<String>`?

**Answer:** Yes, it can. `Field.getGenericType()` can return a `ParameterizedType` for a field declared as `List<String>` when the necessary generic metadata is retained. However, that is the `java.lang.reflect.Type` API, not `TypeMirror` or a separate `Class<List<String>>`.

**Question 7.** What should a processor use to obtain the interface declaration of `List<String>`?

**Answer:** Given the appropriate `DeclaredType`, use `asElement()` or `Types.asElement()` to navigate back to the `TypeElement` of `List`.

## Official Sources

- [Java SE 17: TypeMirror](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/type/TypeMirror.html).
- [Java SE 17: DeclaredType](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/type/DeclaredType.html).
- [Java SE 17: TypeKind](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/type/TypeKind.html).
- [Java SE 17: Types](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/util/Types.html).
- [Java SE 17: Elements](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/util/Elements.html).
- [Java SE 17: AnnotationMirror](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/AnnotationMirror.html).
- [Java SE 17: MirroredTypeException](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/type/MirroredTypeException.html).
- [Java SE 17: Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html).

**Conclusion:** To understand **types as seen by the Java language at compile time**, use `TypeMirror` together with `Elements` and `Types`. To reflect on **classes existing in the JVM**, use `Class<?>` and the reflection APIs. The two models complement each other, but cannot replace one another through casting or mechanically calling `Class.forName`.
