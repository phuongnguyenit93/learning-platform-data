# Enums and Annotation Types Cannot Declare Type Parameters in Java Generics

## 1. Problem and goals

Java Generics lets you define classes or interfaces with **type parameters**:

```java
class Box<T> {
    private T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}

interface Converter<I, O> {
    O convert(I input);
}
```

Callers can use `Box<String>`, `Box<Integer>`, or `Converter<String, Integer>`. However, **not every kind of type declaration in Java is permitted to place `<T>` right after its name**. Two important cases:

```java
// Invalid:
enum Choice<T> {
    FIRST, SECOND
}
```

```java
// Invalid:
@interface Info<T> {
    T value();
}
```

In Java 17, `javac` reports errors whose core messages are, respectively:

```text
error: enums cannot be generic
```

```text
error: annotation interface Info cannot be generic
```

This does not mean enums or annotations "cannot interact with Generics". An enum can still **implement a generic interface, declare generic methods, and have fields using parameterized types**. Annotations can still use **certain parameterized `Class` types** as element return types, and can be placed on generic classes, type parameters, or type arguments according to `@Target`.

This lesson helps distinguish:

- Generic declarations that are **forbidden** at the `enum` and `@interface` level.
- **Uses of Generics that remain valid** inside enums or when defining/applying annotations.
- Why `Enum<E extends Enum<E>>` in the standard library does **not** mean you can write `enum E<T>`.
- Why annotation elements restrict their return types and cannot be ordinary generic methods.
- How to model enums tied to generic APIs and annotation metadata in a type-safe way.
- Compiler errors, runnable Java 17 examples, exercises, and workarounds.

## 2. Start from four concepts not to confuse

| Concept | Example | Meaning |
| --- | --- | --- |
| Generic **class** | `class Holder<T> {}` | A class declaring one or more type parameters. |
| Generic **interface** | `interface Codec<T> {}` | An interface declaring type parameters. |
| **Parameterized type** | `Codec<Integer>`, `List<String>` | A generic type **used** with concrete type arguments. |
| Generic **method** | `<T> T echo(T x)` | A method declaring its own type parameter, independent of whether the enclosing type is generic. |

An `enum` can use **parameterized types** or declare **generic methods**, but it cannot be a **generic enum declaration** with `<T>` after its name.

An `@interface` cannot be a **generic annotation declaration**; moreover, the methods forming **annotation elements** cannot be generic like `<T> T value()`.

**Source-reading rule:** before concluding "Java forbids Generics here", check whether `<T>` is a type parameter **of the enum/annotation itself**, of **a method inside the enum**, or a type argument of an interface/class the enum uses. Different positions follow different rules.

## 3. Why does Java disallow `enum E<T>`?

Intentionally invalid example:

```java
enum State<T> {
    NEW, DONE
}
```

Compiling with Java 17 produces:

```text
error: enums cannot be generic
```

An enum declaration defines only a finite set of **enum constants** belonging to that enum type. Java does not support declaring type parameters on the enum itself as it does for ordinary classes or interfaces.

Notably, even an enum conceptually associated with a single value type `T` cannot be written like this:

```java
// Intentionally invalid:
enum Token<T> {
    TEXT, NUMBER
}
```

There is no valid syntax to "supply" `T` when referencing individual enum constants like `Token<String>.TEXT`. If a system needs values varying heavily by a type parameter, use a generic class, record, interface, or suitable domain model.

### 3.1. An enum is a distinct kind of type, not a user-declared generic class

An enum is still a reference type with fixed instances, able to:

- Declare constructors, fields, and instance methods.
- Declare static methods and generic methods.
- Implement interfaces.
- Contain constant-specific class bodies to override behavior.
- Use generic collections such as `List<String>` and `Map<String,Integer>` internally.

Yet it **cannot** place a type-parameter list after the enum name:

```java
// Invalid: generic enum declaration.
enum Status<T> { READY; }

// Valid: enum without type parameters.
enum Status { READY; }
```

### 3.2. `Enum<E extends Enum<E>>` is a different case

The Java API contains the standard abstract class:

```java
public abstract class Enum<E extends Enum<E>>
        implements Comparable<E>, java.io.Serializable {
    // Excerpt describing type relationships only.
}
```

This is **a built-in generic class in the JDK** serving as the superclass of enums. A concrete enum such as `Status` is given a type relationship corresponding to `Enum<Status>` by Java's special enum rules.

Therefore:

```java
enum Status {
    READY, DONE
}
```

does not declare `<T>` itself. The fact that the superclass `Enum` **is designed as generic** does not mean an `enum` declaration can itself be generic.

You cannot write:

```java
// Intentionally invalid: an enum cannot declare its own type parameter.
// enum Status<T> extends Enum<Status<T>> { ... }
```

In fact, enums have a specialized superclass relationship governed by Java; developers cannot even write an explicit `extends` clause on an enum as with ordinary classes.

## 4. Enums can still implement generic interfaces

A valid design solution:

```java
interface Decoder<T> {
    T decode(String source);
}

enum NumberLevel implements Decoder<Integer> {
    LOW(1), HIGH(3);

    private final int multiplier;

    NumberLevel(int multiplier) {
        this.multiplier = multiplier;
    }

    @Override
    public Integer decode(String source) {
        return Integer.valueOf(source) * multiplier;
    }
}
```

`NumberLevel` is **not** a generic enum: it declares no `<T>`. Instead, it implements the **parameterized interface** `Decoder<Integer>`.

Caller:

```java
Decoder<Integer> decoder = NumberLevel.HIGH;
Integer result = decoder.decode("7"); // 21
```

The compiler checks parameter and return types through `Decoder<Integer>`. Each enum constant remains a value of enum `NumberLevel`.

### 4.1. The type argument is fixed at the enum declaration

The entire `NumberLevel` enum implements `Decoder<Integer>`; one constant cannot implement `Decoder<String>` while another implements `Decoder<Double>` as optional specializations of the enum itself.

Desired but impossible syntax via `<T>` on an enum:

```java
// There is no per-constant type-argument syntax:
// NumberLevel<String>.LOW
// NumberLevel<Integer>.HIGH
```

If each kind of value needs a different generic contract, consider a generic sealed interface with multiple concrete implementations, or typed descriptor objects. Use a single enum when the constants genuinely share the same API and data types.

### 4.2. An enum can store data with generic types

Example of a field using a parameterized type:

```java
enum MessageType {
    INFO, ERROR;

    private final java.util.List<String> tags =
            new java.util.ArrayList<>();

    java.util.List<String> tags() {
        return java.util.List.copyOf(tags);
    }
}
```

`List<String>` is **the field/return type**, not a type parameter of the enum. This structure is valid.

Keep in mind that enum constants are shared instances across the program, akin to singletons per constant. If a field is mutable, consider ownership, thread safety, and how data is exposed. `List.copyOf` returns a snapshot unmodifiable via standard mutating APIs, though the enum itself still needs an appropriate mutation policy.

## 5. Generic methods inside an enum are valid

A method can declare its own `<T>` even though the enclosing enum is non-generic:

```java
enum Utility {
    INSTANCE;

    public <T> T echo(T value) {
        return value;
    }
}
```

Usage:

```java
String text = Utility.INSTANCE.echo("Java");
Integer number = Utility.INSTANCE.echo(42);
```

Here, type variable `T` belongs to **the `echo` method**. The compiler can infer the type independently at each call site; the class/enum does not need a fixed type parameter.

Do not confuse:

```java
enum Utility<T> { INSTANCE; } // Invalid.
```

with:

```java
enum Utility {
    INSTANCE;

    <T> T echo(T value) { return value; } // Valid.
}
```

### 5.1. Generic static methods with an enum bound

A practical case is operating generically on **any enum**:

```java
static <E extends Enum<E>> E parse(
        Class<E> enumClass, String name) {
    return Enum.valueOf(enumClass, name);
}
```

Call site:

```java
Level level = parse(Level.class, "HIGH");
```

`E extends Enum<E>` is a common **F-bound** when writing enum helpers. `E` is a **method** type parameter, not a type parameter declared on `enum Level`.

The `Class<E>` passed by the caller lets the method know the concrete enum class at runtime. This is not a substitute for a generic enum declaration; it is how to build generic APIs **that operate on enums**.

### 5.2. `EnumSet<E>` and `EnumMap<K,V>` are not generic enums

The JDK provides generic classes designed specifically for enums:

```java
java.util.EnumSet<Level> levels =
        java.util.EnumSet.of(Level.LOW, Level.HIGH);

java.util.EnumMap<Level, String> labels =
        new java.util.EnumMap<>(Level.class);

labels.put(Level.LOW, "Low");
```

`EnumSet` and `EnumMap` are **generic collection classes** using an enum as a type argument/key. That is completely different from declaring `enum Level<T>`.

`EnumMap<K,V>` requires `K` to be an appropriate enum type; `EnumSet<E>` likewise requires its type argument to be an enum type. They let you associate typed data with enum constants without a generic enum declaration.

## 6. Enum constants with class bodies: valid, yet do not create a generic enum

An enum can declare per-constant behavior:

```java
enum Action {
    START {
        @Override
        public String execute() {
            return "starting";
        }
    },
    STOP {
        @Override
        public String execute() {
            return "stopping";
        }
    };

    public abstract String execute();
}
```

Both constants still belong to enum `Action`. Constant-specific class bodies allow overriding instance methods, yet **do not give each constant a separate type parameter**.

This example has nothing to do with `Action` being generic. It is enum-specific polymorphism, distinct from creating independent generic subtypes.

If you attempt to write:

```java
// Intentionally invalid:
// enum Action { <T> START; }
```

the compiler rejects it because enum constant syntax does not allow declaring `<T>` like that.

## 7. `@interface` cannot declare type parameters

An annotation interface is declared as:

```java
@interface Label {
    String value();
}
```

You cannot append `<T>` to the name:

```java
// Intentionally invalid:
@interface Label<T> {
    T value();
}
```

On Java 17, the compiler reports:

```text
error: annotation interface Label cannot be generic
```

And it may also report that `T` is not a valid type for an annotation element.

The reason should not be oversimplified to "annotations do not hold objects": Java annotations are **structured metadata with a language-specified set of value types**, serving the compiler, class files, and Reflection. Java enforces a fixed declaration model rather than an arbitrary generic interface.

### 7.1. An annotation interface is a special declaration form

Although its keyword contains "interface", an annotation interface **is not equivalent to a normal interface with full interface syntax freedom**. Its element declarations carry specific constraints regarding:

- Return types.
- Taking no parameters.
- Not declaring type parameters on element methods.
- Default values.
- Representability of annotation values in class files and at annotation use sites.

You cannot work around `@interface X<T>` being invalid by adding a bound `<T extends SomeClass>`. The limit lies in **the annotation declaration form itself**.

## 8. What types can an annotation element have?

An annotation element like:

```java
@interface Label {
    String value();
}
```

looks like a method signature, but its return type is restricted. Essentially, the valid categories are:

1. Primitives (`int`, `boolean`, `long`, etc.).
2. `String`.
3. `Class` or an appropriate **parameterized invocation of `Class`** such as `Class<?>`, `Class<? extends Number>`.
4. An enum type.
5. Another annotation type.
6. A **one-dimensional array** of any of the above.

For example:

```java
@interface Rule {
    int priority() default 1;
    String name() default "default";
    Class<?> type();
    Class<? extends Number> numberType() default Integer.class;
    String[] tags() default {};
}
```

The appearance of `Class<? extends Number>` **does not make `Rule` a generic annotation**. It is simply **a valid return type of an annotation element**.

### 8.1. Table distinguishing element types

| Element return type | Permitted? | Notes |
| --- | --- | --- |
| `int`, `boolean`, `double` | Yes | Primitive. |
| `String` | Yes | A string; at use sites it must be a contextually valid constant value. |
| `Class<?>` | Yes | Can store any valid class literal. |
| `Class<? extends Number>` | Yes | Class literal must satisfy the bound. |
| `Class<String>` | Yes | A parameterized invocation of `Class`. |
| `SomeEnum` | Yes | An enum type. |
| `NestedAnnotation` | Yes | An annotation type. |
| `String[]`, `Class<?>[]`, `SomeEnum[]` | Yes | One-dimensional arrays of valid element types only. |
| `Object` | No | Return type outside the permitted set. |
| `List<String>` | No | Arbitrary generic collections cannot be annotation elements. |
| `Map<String, Object>` | No | Outside the valid element type set. |
| `T` in a hypothetical generic annotation | No | Annotations have no type parameter `T`. |
| `String[][]` | No | Multidimensional arrays are not valid annotation element types. |

**Subtlety:** `Class<?>` uses a generic wildcard and is completely valid as an annotation element; however, that does not mean arbitrary parameterized types like `List<String>` are permitted.

### 8.2. `Class<? extends Number>` stores a class type, not an instance

Annotation example:

```java
@interface NumberRule {
    Class<? extends Number> numberType()
            default Integer.class;
}
```

Usage:

```java
@NumberRule(numberType = Double.class)
class Report {
}
```

`Double.class` is a class literal with a compatible type relationship. The annotation does not hold a `Double` instance or a runtime-validated `List<Double>`. It stores **metadata denoting a class**.

Types like `Class<? extends Number>` are useful for specifying implementation, validator, or adapter classes in frameworks, yet when a framework wants to instantiate that class, it still has to handle constructor, dependency, and access rules. A class literal **does not guarantee** a no-argument constructor.

### 8.3. Annotation values must belong to permitted forms

When applying an annotation, element values are generally constant expressions/literals of the appropriate type, class literals, enum constants, annotations, or array initializers of valid forms. You cannot pass an arbitrary newly constructed object:

```java
// Invalid: annotations do not accept List<String> as an element.
// @Tag(values = new ArrayList<String>())
```

Even when a concrete type has a public constructor, that does not allow using `new SomeObject()` as an arbitrary annotation value.

### 8.4. `value()` has shorthand syntax

```java
@interface Title {
    String value();
}

@Title("Generics")
class Guide {
}
```

An element named `value` has shorthand assignment syntax. This is a convenience of annotation syntax, **not** a generic method, and it adds no type parameters to the annotation.

## 9. Generic methods in annotation interfaces are also invalid

An annotation element cannot declare a type parameter:

```java
// Intentionally invalid:
@interface InvalidElement {
    <T> T value();
}
```

On Java 17, the compiler reports:

```text
error: elements in annotation interface declarations cannot be generic methods
```

Adding `<T>` before the return type cannot turn an annotation element into an arbitrary factory or generic accessor. This is a major difference between generic methods allowed inside enums and annotation element declarations.

Summary table:

| Declaration site | Can `<T>` be placed here? |
| --- | --- |
| `class Holder<T>` | Yes |
| `interface Codec<T>` | Yes |
| `enum State<T>` | **No** |
| `@interface Label<T>` | **No** |
| `<T> T echo(T x)` inside an enum | Yes |
| `<T> T value()` as an annotation element | **No** |

An annotation type may contain constants and nested declarations under language rules, but element methods do not have the freedom of ordinary generic methods.

## 10. Annotations using enums as elements: valid and type-safe

Enums are often a good choice for defining fixed metadata values:

```java
enum Severity {
    INFO, WARNING, ERROR
}

@interface Audit {
    Severity severity() default Severity.INFO;
    String message() default "";
}
```

Usage:

```java
@Audit(severity = Severity.ERROR, message = "failed")
class Service {
}
```

The compiler verifies that `Severity.ERROR` matches the element's enum type. Passing an enum constant from a **different** enum is rejected for type mismatch.

The `Audit` annotation itself remains **non-generic**. It simply has an element of type `Severity`, which is a valid enum type.

### 10.1. Enums can be used in annotation element arrays

```java
@interface Allowed {
    Severity[] levels() default {
        Severity.INFO, Severity.WARNING
    };
}
```

A one-dimensional array of an enum is a valid element type. When reading the annotation via Reflection, callers receive the corresponding array. For runtime annotations, the API normally returns a fresh copy when needed to preserve immutability of annotation instances; do not treat the returned array as a way to mutate annotation metadata.

## 11. Nested annotations: instead of arbitrary objects

If you need to model metadata more complex than a single string or enum:

```java
@interface Range {
    int min();
    int max();
}

@interface Check {
    Range range();
    String label() default "";
}
```

Applied as:

```java
@Check(range = @Range(min = 1, max = 10), label = "age")
class ValidatedField {
}
```

This illustrative example uses the annotation type `Range` as the return type of the `range` element. This design leverages the exact type set supported by annotations instead of trying to declare `List<Range>` or a free-form data object as an element.

If metadata genuinely requires a collection of complex records, you can use **a one-dimensional array of annotations**:

```java
@interface RuleItem {
    String name();
    int weight();
}

@interface RuleSet {
    RuleItem[] value();
}
```

When designing an annotation schema, prioritize clarity and compatibility with compiler/class-file rules. Never turn an annotation into a full serialization mechanism for unbounded object graphs.

## 12. Complete Java 17 example: enum + generic interface + annotation

Create the file **`EnumAnnotationGenericsDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.List;

public class EnumAnnotationGenericsDemo {
    interface Codec<T> {
        T decode(String text);
    }

    enum Level implements Codec<Integer> {
        LOW(1), HIGH(3);

        private final int weight;

        Level(int weight) {
            this.weight = weight;
        }

        @Override
        public Integer decode(String text) {
            return Integer.valueOf(text) * weight;
        }

        public <T> T echo(T value) {
            return value;
        }
    }

    enum Action {
        START {
            @Override
            public String execute() {
                return "starting";
            }
        },
        STOP {
            @Override
            public String execute() {
                return "stopping";
            }
        };

        public abstract String execute();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface Rule {
        Class<?> type();
        Class<? extends Number> numberType()
                default Integer.class;
        Level level() default Level.LOW;
        String[] tags() default {};
    }

    @Rule(
            type = String.class,
            numberType = Double.class,
            level = Level.HIGH,
            tags = {"core", "generics"}
    )
    static class Example {
    }

    static <E extends Enum<E>> E parse(
            Class<E> kind, String name) {
        return Enum.valueOf(kind, name);
    }

    public static void main(String[] args) {
        System.out.println("enum=" + Level.HIGH.name());
        System.out.println("interface=" + Level.HIGH.decode("7"));
        System.out.println("method=" + Level.LOW.echo("ok"));
        System.out.println("action=" + Action.START.execute());
        System.out.println("parse=" + parse(Level.class, "LOW"));

        Rule rule = Example.class.getAnnotation(Rule.class);
        System.out.println("annotation="
                + rule.type().getSimpleName() + ":"
                + rule.numberType().getSimpleName() + ":"
                + rule.level());
        System.out.println("tags=" + List.of(rule.tags()));
    }
}
```

This program targets Java 17 or any newer JDK supporting `--release 17`. Run:

```bash
javac --release 17 -Xlint:all EnumAnnotationGenericsDemo.java
java EnumAnnotationGenericsDemo
```

Verified: compiled cleanly **with no warnings**, stdout:

```text
enum=HIGH
interface=21
method=ok
action=starting
parse=LOW
annotation=String:Double:HIGH
tags=[core, generics]
```

### 12.1. Analyzing `enum=HIGH` and `interface=21`

`Level.HIGH` is an enum constant of the non-generic enum `Level`. `Level` implements `Codec<Integer>`:

```java
enum Level implements Codec<Integer> { ... }
```

`decode("7")` returns an `Integer` equal to `7 * 3 = 21`. The compiler knows `Codec<Integer>` requires a return type compatible with `Integer`. No `enum Level<T>` is needed.

### 12.2. Analyzing `method=ok`

The method:

```java
public <T> T echo(T value) {
    return value;
}
```

is declared inside the enum. `T` belongs solely to the method scope, so the compiler infers `T = String` when calling `echo("ok")`.

This proves a **non-generic enum** can still have **generic methods**.

### 12.3. Analyzing `action=starting`

The `Action` enum uses constant-specific class bodies to override `execute()`. There is no generic parameter at the enum level. This is per-constant enum polymorphism, not enum specialization by `T`.

### 12.4. Analyzing `parse=LOW`

The generic helper:

```java
static <E extends Enum<E>> E parse(
        Class<E> kind, String name) {
    return Enum.valueOf(kind, name);
}
```

uses an enum bound to accept any specific enum type; `Level.class` is the class token provided by the caller. All required information is passed explicitly to the helper without requiring the enum declaration to have a type parameter.

If the name does not exist, `Enum.valueOf` throws `IllegalArgumentException`; it does not return null. Handle error policies according to your application.

### 12.5. Analyzing `annotation=String:Double:HIGH`

`@Rule` contains the elements:

- `Class<?> type()`: stores `String.class`.
- `Class<? extends Number> numberType()`: stores `Double.class`.
- `Level level()`: stores `Level.HIGH`.
- `String[] tags()`: stores a string array.

These elements are **valid** even though the annotation interface is non-generic. `@Retention(RUNTIME)` lets Reflection read the annotation from `Example`. Without runtime retention, `getAnnotation` would not find the annotation at runtime even though it is valid in source.

### 12.6. Where does `tags=[core, generics]` come from?

`rule.tags()` returns a `String[]` array. `List.of(rule.tags())` creates a list containing those string elements via the appropriate varargs overload. The output was verified by running the actual program.

No `List<String>` is used as **the annotation element's return type**: that is `String[]`, a permitted type. Converting the array to a List happens **after reading the annotation**, in ordinary Java code.

## 13. Intentionally non-compiling example: generic enum

Standalone file **`GenericEnum.java`**:

```java
enum GenericEnum<T> {
    A;
}
```

Compile:

```bash
javac --release 17 GenericEnum.java
```

The compiler returns:

```text
error: enums cannot be generic
```

Do not try to "fix" it by changing it to:

```java
// Still invalid:
// enum GenericEnum<T extends Number> { A; }
```

Bounds do not change the rule: enum declarations cannot declare type parameters.

If the application needs an object holding a generic value alongside a fixed enum tag, separate the tag and payload:

```java
enum Kind {
    TEXT, NUMBER
}

record TaggedValue<T>(Kind kind, T value) {
}
```

Example:

```java
TaggedValue<String> text =
        new TaggedValue<>(Kind.TEXT, "hello");
```

`TaggedValue<T>` is a generic record, while `Kind` remains a non-generic enum. Note that this model **does not automatically enforce** that `Kind.TEXT` always pairs with `String`, since a caller could construct `new TaggedValue<Integer>(Kind.TEXT, 7)`. If an invariant linking tag to payload type is required, design validators or concrete subtypes/constructors so the compiler or runtime enforces that rule.

## 14. Intentionally non-compiling example: generic annotation

File **`GenericAnnotation.java`**:

```java
@interface GenericAnnotation<T> {
    T value();
}
```

Command:

```bash
javac --release 17 GenericAnnotation.java
```

`javac` reports the main error:

```text
error: annotation interface GenericAnnotation cannot be generic
```

And an error on the element type:

```text
error: invalid type for annotation interface element
```

Changing the return type to `String` still does not make `<T>` on `@interface` valid. Remove the type parameter from the annotation declaration:

```java
@interface ValidAnnotation {
    String value();
}
```

If metadata needs to describe a chosen class, use a `Class<?>` element or an appropriate bound instead of a generic type parameter at the annotation level.

## 15. Intentionally non-compiling example: `List<String>` element

File **`ListElement.java`**:

```java
import java.util.List;

@interface ListElement {
    List<String> value();
}
```

Command:

```bash
javac --release 17 ListElement.java
```

The compiler returns:

```text
error: invalid type for annotation interface element
```

`List<String>` is a completely valid Java type for variables, fields, or ordinary method return types. Yet it **is not in the set of allowed return types for annotation elements**.

If multiple strings are needed, use an array:

```java
@interface Tags {
    String[] value();
}

@Tags({"java", "generics"})
class Article {
}
```

If rich structured metadata is needed, use an array of nested annotations. If dynamic runtime data with collection semantics is needed, use a separate config object or registry — annotations are not meant to store arbitrary objects.

## 16. Intentionally non-compiling example: generic method inside an annotation

File **`GenericAnnotationMethod.java`**:

```java
@interface GenericAnnotationMethod {
    <T> T value();
}
```

Compile:

```bash
javac --release 17 GenericAnnotationMethod.java
```

A key diagnostic:

```text
error: elements in annotation interface declarations
cannot be generic methods
```

The compiler may also warn that return type `T` is invalid for an annotation element. What needs fixing is **the element's type design**, not adding a bound.

If the element only needs to represent a class:

```java
@interface ClassHint {
    Class<?> value();
}
```

If business logic needs a generic method to process data, write that method in an ordinary class, interface, or service that can take the annotation metadata as input.

## 17. Intentionally non-compiling example: multidimensional array or `Object` element

An annotation element does not accept an arbitrary return type simply because the compiler understands that type in ordinary Java.

File **`InvalidArrayElement.java`**:

```java
@interface InvalidArrayElement {
    String[][] value();
}
```

The compiler returns:

```text
error: invalid type for annotation interface element
```

Likewise:

```java
@interface InvalidObjectElement {
    Object value();
}
```

is also invalid. You must choose a primitive, `String`, `Class`/parameterized invocation of `Class`, enum, annotation, or a **one-dimensional array** of those types.

### 17.1. Why is `Class<?>[]` valid?

Example:

```java
@interface Types {
    Class<?>[] value();
}
```

This is a **one-dimensional array** of a valid `Class<?>` element. There is no contradiction with `String[][]` being forbidden: `String[][]` is two-dimensional.

Another case verified to compile cleanly with Java 17:

```java
@interface Pick {
    Class<String> exact() default String.class;

    Class<? extends Number>[] types()
            default {Integer.class, Double.class};
}
```

Both `Class<String>` and `Class<? extends Number>[]` are valid; class literals in default values must have compatible type relationships.

## 18. Annotations can appear on generic declarations and type arguments

An annotation **does not need to be generic** to mark where a type parameter or type argument is declared or used. For example:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;
import java.util.List;

@Target({
    ElementType.TYPE_USE,
    ElementType.TYPE_PARAMETER
})
@interface TypeMarker {
}

class AnnotatedGeneric<@TypeMarker T> {
    List<@TypeMarker String> names;
    @TypeMarker T value;
}
```

This snippet was compiled with `javac --release 17 -Xlint:all` with no errors or warnings.

Points to distinguish:

- `TypeMarker` is an annotation interface declaring no `<T>`.
- `AnnotatedGeneric<T>` is an **ordinary generic class**.
- The annotation is **applied to a type parameter or type use** because `@Target` permits it.
- `List<@TypeMarker String>` has a **type annotation** on the type use `String`; it does not make `TypeMarker` generic.

### 18.1. `TYPE_PARAMETER` and `TYPE_USE` differ

`ElementType.TYPE_PARAMETER` targets **declarations** of a type parameter, such as `<@Marker T>`.

`ElementType.TYPE_USE` targets positions where types are used in permitted language contexts, such as `List<@Marker String>` or a suitable typed declaration.

An annotation with only `@Target(TYPE)` can annotate class/interface declarations, but cannot automatically be placed on every type argument. If your goal is static analysis or nullness/type checking on Generics, configure `@Target` accurately.

### 18.2. Do not confuse a type-use annotation with an annotation having type parameters

`@TypeMarker` is attached **to** `String` in `List<@TypeMarker String>`, yet `@TypeMarker` itself remains a metadata annotation with elements governed by its own rules. You cannot write `@TypeMarker<String>` to "parameterize the annotation".

Tools such as annotation processors or type checkers can use type-use annotations to enforce static rules. That **does not** cause the Java runtime to check erased generic type arguments automatically.

## 19. How to structure models when you want "an enum carrying a data type"

A common requirement is defining a list of data kinds:

```java
enum DataKind {
    TEXT, NUMBER
}
```

and wanting each kind to "carry" a different result type. This cannot be solved with:

```java
// Invalid:
// enum DataKind<T> { TEXT, NUMBER }
```

Several better designs exist:

### 19.1. Enum as a tag, generic record as payload

```java
enum DataKind {
    TEXT, NUMBER
}

record Value<T>(DataKind kind, T payload) {
}
```

The advantage is keeping a finite enum for displaying or storing tags while `Value<T>` provides a generic contract for the payload.

Limitation: the link between `DataKind.TEXT` and `T=String` needs an extra invariant if the application demands it. Do not assume `Value<Integer>(TEXT, 123)` is automatically a compiler error.

### 19.2. Generic interface with concrete implementations

```java
interface TypedKey<T> {
    T read(String source);
}

final class StringKey implements TypedKey<String> {
    @Override
    public String read(String source) {
        return source;
    }
}

final class IntKey implements TypedKey<Integer> {
    @Override
    public Integer read(String source) {
        return Integer.valueOf(source);
    }
}
```

When each kind truly has its own generic behavior, implementations like these let the compiler tie the result type to the instance type. You can organize a registry of them in collections or with enum tags when needed.

### 19.3. Using an enum to implement a fixed generic interface

If every constant returns the same type and differs only in logic:

```java
interface Rule<T> {
    T apply(String input);
}

enum TextRule implements Rule<String> {
    UPPER {
        @Override
        public String apply(String input) {
            return input.toUpperCase();
        }
    },
    LOWER {
        @Override
        public String apply(String input) {
            return input.toLowerCase();
        }
    };
}
```

This uses enums as intended: a fixed set of constants, a shared interface type `Rule<String>`, and polymorphic behavior. It **does not** make the enum generic.

## 20. How to structure metadata when you want "an annotation carrying a type"

Another requirement is marking a class with the data type it handles:

```java
@interface Handles {
    Class<?> type();
}
```

Usage:

```java
@Handles(type = String.class)
class StringHandler {
}
```

This annotation holds a class token, not a `T` inferred for the handler.

If you need to constrain choices:

```java
@interface HandlesNumber {
    Class<? extends Number> type();
}
```

The compiler can verify the class literal against the bound. However, the annotation does not verify that the implementation class `StringHandler` actually has a handle method taking that corresponding type.

To tie metadata tightly to behavior, you can combine:

- A generic interface `Handler<T>` for the compile-time contract.
- An annotation `@Handles(type = ...)` for registration/discovery.
- Startup validation or an annotation processor to enforce relationships that Java's type system does not automatically link between annotation elements and generic arguments.

Never claim that attaching an annotation automatically reifies all generic types of a class instance.

## 21. Reading annotations properly with Reflection

Only an annotation with `@Retention(RetentionPolicy.RUNTIME)` can be retrieved via Reflection at runtime through the standard runtime annotation mechanism.

```java
@Retention(RetentionPolicy.RUNTIME)
@interface Label {
    String value();
}
```

```java
@Label("hello")
class Example {
}
```

A method using Reflection:

```java
Label label = Example.class.getAnnotation(Label.class);
```

If the annotation is present and retention permits it, `label.value()` returns `"hello"`.

In the complete example in Section 12, `Rule` has `@Retention(RUNTIME)`, so:

```java
Rule rule = Example.class.getAnnotation(Rule.class);
```

reads the elements `type`, `numberType`, `level`, and `tags`.

### 21.1. Retention is orthogonal to Generics

`SOURCE`, `CLASS`, and `RUNTIME` govern where an annotation is retained or read; they do not decide whether an annotation can be generic. Even with runtime retention, declaring `@interface Info<T>` remains invalid.

### 21.2. Annotation metadata is not a free-form configuration object

Annotation element methods return types allowed by the JLS, not arbitrary object graphs. If you need runtime lists that mutate continuously or deeply nested data, use a dedicated config class/record and parser/validator. Annotations are suited to finite metadata readable by the compiler or Reflection.

## 22. Checklist for diagnosing compilation errors

When encountering a compiler error involving enums, annotations, and Generics:

1. **Locate `<T>` precisely:** is it directly after the `enum`/`@interface` name, or on another method/class/interface?
2. If it is `enum Name<T>`, that is a **declaration-structure error**; switch to a non-generic enum implementing a generic interface/method or separate a generic holder.
3. If it is `@interface Name<T>`, remove type parameters from the annotation declaration; determine the actual metadata to return using permitted element types.
4. If an annotation element is `<T> T value()` or `List<String> value()`, that is an **invalid element method/type**, not an erasure issue fixable with casts.
5. For an annotation describing a class, consider `Class<?>` or `Class<? extends Base>`; for multiple classes, use a one-dimensional array.
6. If an annotation needs richer data, consider enums, nested annotations, or one-dimensional arrays of supported types; if unsuitable, move to a configuration object.
7. For an enum implementing a generic interface, verify that the type argument and method implementations actually match the contract.
8. For generic helpers operating on enums, prefer `<E extends Enum<E>>` paired with `Class<E>` as needed by the API.
9. If reading annotations with Reflection, confirm `@Retention(RUNTIME)` and appropriate `@Target` placement.
10. Recompile with `javac --release 17 -Xlint:all` and write tests covering both valid declarations and cases that must be rejected.

### 22.1. Cause-and-fix table

| Diagnostic | Cause | Resolution |
| --- | --- | --- |
| `enums cannot be generic` | Placed a type parameter after the enum name. | Remove `<T>`; use generic classes/interfaces/methods around the enum. |
| `annotation interface ... cannot be generic` | Declared `@interface A<T>`. | Remove `<T>`; use valid elements to describe metadata. |
| `elements in annotation interface declarations cannot be generic methods` | Element declared its own `<T>`. | Use a fixed element type; move generic logic to a class/service. |
| `invalid type for annotation interface element` | Return type is `Object`, `List<String>`, `String[][]`, etc. | Use primitive, `String`, `Class`, enum, annotation, or a valid 1D array. |
| Enum `implements Codec<Integer>` reports missing method | Failed to override matching the interface's substituted signature. | Implement with exact types after substituting `T = Integer`. |
| Reflection returns `null` when reading annotation | Annotation missing or retention does not permit runtime access. | Check declaration, `@Retention`, `@Target`, and attachment site. |
| Wanting each enum constant to have a different type argument | Enum declaration cannot be generic; constants share one enum type. | Switch to typed hierarchies/descriptors or split into enums with fixed contracts. |

## 23. Common misconceptions

**Misconception 1 — "Because enums cannot be generic, `List<String>` cannot be used inside an enum."** False. Enums cannot declare type parameters, yet fields, parameters, and return types inside them can still be parameterized types.

**Misconception 2 — "`Enum<E>` in the JDK proves you can declare `enum X<T>`."** False. `Enum<E>` is the special generic superclass of enums, not syntax for a generic enum declaration.

**Misconception 3 — "Because enums are non-generic, they cannot have `<T> T method(T)`."** False. Methods have their own type parameters and are permitted inside enums.

**Misconception 4 — "An enum implementing `Codec<Integer>` turns the enum into `Enum<Integer>`."** False. The parameterized type here is the implemented **interface**, not a type parameter of the enum.

**Misconception 5 — "Because annotations cannot be generic, elements cannot use `Class<?>`."** False. `Class<?>`, `Class<? extends Number>`, and valid invocations of `Class` are supported in annotations.

**Misconception 6 — "An element `List<String>` is valid because `List<String>` is a valid Java type."** False. Annotation element types are much more tightly restricted than ordinary method return types.

**Misconception 7 — "`String[][]` is just an array so it works as an annotation element."** False. Annotations only support one-dimensional arrays of valid element types.

**Misconception 8 — "Annotations can declare generic methods because they are interfaces."** False. Element declarations of annotation interfaces cannot be generic methods.

**Misconception 9 — "`@TypeMarker` placed in `List<@TypeMarker String>` means `TypeMarker` has a type parameter."** False. The annotation is being **applied at a type use**, not declared as generic.

**Misconception 10 — "Simply having `Class<? extends Foo>` on an annotation makes a framework verify all generic behavior automatically."** False. Annotation metadata only records a class token or constant value; consistency between metadata and implementation must be checked separately.

**Misconception 11 — "`@Retention(RUNTIME)` fixes the generic annotation restriction."** False. Retention only controls runtime visibility of the annotation, not adding type parameters to `@interface`.

**Misconception 12 — "Every constant of an enum can independently choose a type argument for the same generic enum."** False. Enums cannot be generic; constants share one enum type, and constant-specific class bodies do not create specializations by `T`.

## 24. Practice exercises

### Exercise 1 — Classifying declarations

Consider:

```java
enum Mode<T> {
    A;
}

interface Provider<T> {
    T get();
}

enum DefaultMode implements Provider<String> {
    A;

    public String get() {
        return "ok";
    }
}
```

Which declarations are valid?

<details>
<summary>Answer</summary>

`enum Mode<T>` is invalid because enums cannot declare type parameters. `Provider<T>` is a valid generic interface. `DefaultMode implements Provider<String>` is valid because the enum is non-generic yet is allowed to implement a parameterized interface and override the method returning `String`.

</details>

### Exercise 2 — Generic method inside an enum

Can you add this method inside a non-generic enum?

```java
<T> T identity(T value) {
    return value;
}
```

<details>
<summary>Answer</summary>

Yes. `<T>` belongs to the generic method declaration, not the enum declaration. Java allows enums to have generic methods under normal method rules.

</details>

### Exercise 3 — Annotation element return types

Which types are valid: `String`, `Object`, `List<String>`, `Class<?>`, `Class<? extends Number>`, `String[]`, `String[][]`?

<details>
<summary>Answer</summary>

Valid: `String`, `Class<?>`, `Class<? extends Number>`, `String[]`. Invalid: `Object`, `List<String>`, `String[][]`. Annotation elements accept only the language-permitted type categories; arrays are one-dimensional only.

</details>

### Exercise 4 — Annotation with a generic method?

```java
@interface Pick {
    <T> T get();
}
```

Why is this rejected by the compiler?

<details>
<summary>Answer</summary>

Annotation element declarations cannot be generic methods. Being a kind of interface does not give annotation element methods the same freedom to declare type parameters as ordinary class/interface methods. Choose a valid element type or move generic logic to a method in another class.

</details>

### Exercise 5 — Why can `EnumSet<Level>` be used?

<details>
<summary>Answer</summary>

`EnumSet` is a Java **generic collection class**. The type argument `Level` is a concrete enum type, while the enum `Level` itself declares no `<T>`. There is no conflict with the rule that enums cannot be generic.

</details>

### Exercise 6 — Does placing an annotation on a type argument make the annotation generic?

```java
List<@TypeMarker String> names;
```

<details>
<summary>Answer</summary>

No. `TypeMarker` is used at a `TYPE_USE` position when its `@Target` declaration allows it. It does not itself have type parameters. The generic type here is `List<String>`; the annotation merely attaches metadata to the type use `String`.

</details>

### Exercise 7 — Choosing a design for an enum returning differently typed data

An application has tags `TEXT` and `NUMBER`, each needing its own payload type. Should you write `enum Item<T>`?

<details>
<summary>Answer</summary>

You cannot write that generic enum declaration in Java. You can use an enum as a tag paired with a generic record/class for the payload; if the compiler must enforce which tag pairs with which payload type, consider typed descriptors or concrete implementations via a generic interface, supplemented with appropriate invariants.

</details>

### Exercise 8 — Can an annotation store a list of strings?

If metadata needs to hold three labels `"a"`, `"b"`, `"c"`, how should the element be defined?

<details>
<summary>Answer</summary>

Use `String[] value()`:

```java
@interface Tags {
    String[] value();
}

@Tags({"a", "b", "c"})
class Tagged {
}
```

Do not use `List<String> value()`, because `List<String>` is not a valid annotation element type.

</details>

## 25. Key takeaways

**Java forbids declaring type parameters directly on `enum` and `@interface`**, though the scope of the restriction differs:

- An enum cannot write `enum E<T>`, yet **can still** implement `GenericInterface<Concrete>`, declare generic methods, use generic fields, and work with generic collections like `EnumSet<E>` and `EnumMap<E,V>`.
- An annotation cannot write `@interface A<T>`, and **annotation element methods cannot be generic either**. Element return types must belong to Java's permitted set: primitives, `String`, `Class` (including valid invocations of `Class`), enums, annotations, and one-dimensional arrays thereof.
- Annotations can still be **placed on generic type declarations and usages** via `TYPE_PARAMETER` and `TYPE_USE` without becoming generic annotations.

When facing a need for "an enum with a type parameter", ask whether the generic contract belongs on **an interface**, **a method**, or **an object holding the enum**. When facing a need for "a generic annotation", ask whether the metadata can be expressed with **a `Class` token, enum, array, or nested annotation**, or belongs in a configuration object and generic service. Separating responsibilities this way preserves type safety without fighting declarations Java does not support.