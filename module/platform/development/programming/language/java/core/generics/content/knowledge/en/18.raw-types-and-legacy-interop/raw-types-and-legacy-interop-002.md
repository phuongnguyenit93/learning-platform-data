# Distinguishing Raw Types from Ordinary Non-Generic Types in Java

## 1. Two Easily Confused Concepts

In Java, a **raw type** is the use of a type name **that was declared as generic** while **omitting its type parameter list** at the use site.

For example, the Java library declares the `List<E>` interface. When you write:

~~~java
List<String> names = new ArrayList<>(); // Parameterized type: List<String>.
List rawNames = new ArrayList();        // Raw type: List and ArrayList.
~~~

`List` and `ArrayList` on the second line are **raw types**, because the types themselves are declared with type parameters, yet the use site omits them.

In contrast, a **non-generic type** is declared from the start **without any type parameters**:

~~~java
final class Person {
    private final String name;

    Person(String name) {
        this.name = name;
    }

    String name() {
        return name;
    }
}
~~~

Writing `Person person = new Person("Lan");` uses an ordinary type, **not a raw type**. You cannot write `Person<String>` because `Person` is not declared as a generic type.

**Foundational conclusion:** to identify a raw type, you must check **whether the definition of that type declares a type parameter**, and then check whether the use site omits the type argument. You cannot rely solely on whether `<...>` appears in a line of code.

## 2. Terms to Distinguish Precisely

- **Type parameter**: a type variable in a declaration, such as `T` in `class Box<T>` or `E` in `interface List<E>`.
- **Type argument**: a type argument supplied when using a generic type, such as `String` in `Box<String>` and `List<String>`.
- **Parameterized type**: a generic type supplied with type arguments, such as `List<String>`, `List<Object>`, `List<?>`.
- **Raw type**: a generic name missing its type argument list in an applicable usage context, such as `List`, `Map`, `Box` when their corresponding declarations are generic.
- **Non-generic type**: a class, interface, or type declaration that does not take type arguments at all, such as `String`, `Integer`, or a `LegacyRecord` class without `<T>`.
- **Type erasure**: a compilation mechanism whereby most generic parameter information is no longer part of JVM method descriptors. It is an implementation mechanism, **not synonymous with raw types**.

In other words: *raw* describes how a **generic type** is used; *non-generic* describes a type declaration itself that is **not generic**.

## 3. Comparing with Two Custom Classes

Consider two declarations:

~~~java
// Non-generic: declares no type parameters.
class LegacyBox {
    private final Object value;

    LegacyBox(Object value) {
        this.value = value;
    }

    Object get() {
        return value;
    }
}

// Generic: declares type parameter T.
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
~~~

Usage:

~~~java
LegacyBox ordinary = new LegacyBox("Java");
Object fromOrdinary = ordinary.get();

Box<String> typed = new Box<>("Generics");
String fromTyped = typed.get();

Box raw = new Box("Raw");
Object fromRaw = raw.get();
~~~

| Aspect | `LegacyBox` | `Box<String>` | `Box` |
| --- | --- | --- | --- |
| Does the base type declare `<T>`? | No | Yes | Yes |
| Is the usage a raw type? | No | No | Yes |
| What does `get()` return from source perspective? | Object as declared | String thanks to T = String | Object after erasure/default bound |
| Can `<String>` be written for this type? | No | Already written | Can be updated to `Box<String>` |
| Meaning | API inherently non-generic | API with concrete type information | Generic API missing type arguments |
| Risk of unchecked warning due to raw? | No, from this type itself | No, if used properly | Possible when calling members taking T or converting to parameterized form |

Both `LegacyBox` and raw `Box` can return Object when calling get, but **for completely different reasons**. With `LegacyBox`, the method was declared by its author to return Object. With raw `Box`, the method originally returns T, but raw usage drops part of the parameterized compile-time type guarantees.

Do not conclude a type is raw just because it has a method returning Object. Many non-generic classes intentionally have APIs using Object.

### "No `<>` Visible" Does Not Mean Raw

~~~java
String text = "hello";         // String is non-generic.
Integer number = 17;          // Integer is non-generic.
Runnable action = () -> {};   // Runnable is non-generic.
Object obj = new Object();    // Object is non-generic.
~~~

The classes/interfaces above declare no type parameters, so they are **non-generic types**. No type argument is omitted.

The expression `new ArrayList<>()` is a different case: the **diamond operator** asks the compiler to infer type arguments for a generic type. It is not equivalent to `new ArrayList()` using a raw constructor type.

## 4. Complete Runnable Example on Java 17+

Save the entire program below as **RawVsOrdinaryDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class RawVsOrdinaryDemo {
    static final class NonGenericBox {
        private final Object value;

        NonGenericBox(Object value) {
            this.value = value;
        }

        Object get() {
            return value;
        }
    }

    static final class GenericBox<T> {
        private final T value;

        GenericBox(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    public static void main(String[] args) {
        NonGenericBox oldStyle = new NonGenericBox("plain");
        System.out.println("plain=" + oldStyle.get());

        GenericBox<String> typed = new GenericBox<>("typed");
        String text = typed.get();
        System.out.println("typed=" + text);

        // Omit the type parameter of GenericBox<T>: using a raw type.
        GenericBox rawBox = new GenericBox("raw");
        Object fromRaw = rawBox.get();
        System.out.println("rawBox=" + fromRaw);

        List<String> words = new ArrayList<>();
        words.add("Java");

        // Raw List and List<String> both point to the same ArrayList.
        List raw = words;
        raw.add(42);
        System.out.println("rawList=" + raw);

        Object first = words.get(0);
        System.out.println("first=" + first);

        try {
            String second = words.get(1);
            System.out.println(second);
        } catch (ClassCastException ex) {
            System.out.println("typedRead=ClassCastException");
        }

        // Wildcard is still a parameterized type, not raw.
        List<?> unknown = words;
        System.out.println("wildcardSize=" + unknown.size());

        // Ordinary generics are implemented via type erasure.
        System.out.println(
                "sameRuntimeClass=" +
                (typed.getClass() == rawBox.getClass())
        );
    }
}
~~~

Compile to see warnings at the exact raw usage sites:

~~~bash
javac -Xlint:rawtypes -Xlint:unchecked RawVsOrdinaryDemo.java
java RawVsOrdinaryDemo
~~~

The compiler may emit **rawtypes** warnings at declarations/instantiations of `GenericBox` and `List` without type arguments; **unchecked** warnings appear at potentially unsafe calls such as `raw.add(42)` or raw constructors. Compiler warnings are not part of the program's stdout.

Program stdout:

~~~text
plain=plain
typed=typed
rawBox=raw
rawList=[Java, 42]
first=Java
typedRead=ClassCastException
wildcardSize=2
sameRuntimeClass=true
~~~

Explanation:

1. `NonGenericBox` uses Object by its original design; there are no raw generics in this type.
2. `GenericBox<String>` has String type information at compile time, so the compiler checks that `typed.get()` can be used as String.
3. `GenericBox rawBox` omits the type argument of `GenericBox<T>`; `get()` is seen via its erased signature, which in this example is Object.
4. `List raw = words` creates **a raw reference** to the exact same existing `List<String>` list; no copy is created and no elements are converted.
5. `raw.add(42)` slips past generic checks along the raw path with an unchecked warning. Because the ArrayList holds an Integer at the second position, calling `words.get(1)` and using the result as String throws ClassCastException.
6. `List<?> unknown` still has a type argument—the wildcard `?`—so it is **not raw**.
7. `typed.getClass() == rawBox.getClass()` evaluates to `true`: raw and parameterized uses share the same generic class at runtime under normal type erasure. This does **not** make the compile-time types of the variables equal.

The demonstration intentionally uses a raw type to explain the risk; in application code, fix the raw source instead of catching ClassCastException as a long-term solution.

## 5. A Raw Type Is Not `List<Object>`

An important mistake is assuming the following declarations are equivalent:

~~~java
List raw;              // Raw type.
List<Object> objects;  // Parameterized type with E = Object.
List<?> unknown;       // Parameterized type with unbounded wildcard.
List<String> names;    // Parameterized type with E = String.
~~~

They are not equivalent.

### `List<Object>` is still generically checked

~~~java
List<Object> objects = new ArrayList<>();
objects.add("Java");
objects.add(42);
Object value = objects.get(0);
~~~

`List<Object>` is a generic type with a concrete type parameter Object. It allows adding String/Integer because both are subtypes of Object, yet **the compiler still checks against E = Object**.

Meanwhile, raw `List` drops E information when using members affected by erasure, creating the possibility of slipping wrong-typed data into collections that are used elsewhere with a concrete type argument.

### `List<?>` preserves uncertainty about the element type

~~~java
List<String> names = new ArrayList<>();
names.add("Java");
List<?> unknown = names;

Object value = unknown.get(0);
// unknown.add("Kotlin"); // Compile error.
~~~

`List<?>` is a parameterized type: it describes a `List` with some unknown element type. The compiler forbids adding an arbitrary String because that value might be incompatible with the actual element type. Adding `null` is allowed under general wildcard rules, though a concrete collection might not support modification operations.

In contrast:

~~~java
List raw = names;
raw.add(42); // Unchecked warning: may break the assumption of List<String>.
~~~

**`List<?>` is usually the right choice when you only need to read elements as Object without knowing the specific type**, especially in read-only/observing APIs.

### `List<Object>` is not a supertype of `List<String>`

Even though String extends Object, Java generics are generally **invariant**:

~~~java
List<String> names = new ArrayList<>();
// List<Object> wrong = names; // Does not compile.
List<?> acceptable = names;    // Valid.
List rawButUnsafe = names;     // Valid, raw usage.
~~~

If `List<Object>` could accept a `List<String>` and then add an Integer, type soundness would be broken. Wildcards represent unknownness more safely; raw types exist only for legacy code compatibility and very specific situations.

## 6. Raw Types Differ from Generic Types Using Diamond

Look at:

~~~java
List<String> a = new ArrayList<>();
var b = new ArrayList<String>();
var c = new ArrayList<>();
List raw = new ArrayList();
~~~

- `a` has static type List<String>; the expression `new ArrayList<>()` uses diamond and the List<String> context to infer E = String.
- `b` has type ArrayList<String> inferred from the initializer that explicitly writes String.
- `c` has type ArrayList<Object> in the empty constructor case, with no other information to infer E; **this is still a parameterized type**, not raw.
- `raw` uses the raw type List and raw construction ArrayList, truly omitting type arguments at the use site.

Therefore, **you cannot conclude that using `var` with diamond is raw**. Even when the compiler infers E as Object, `ArrayList<Object>` is still a generic type with a type argument.

Another example:

~~~java
var inferred = new ArrayList<>(List.of("Java", "Kotlin"));
// ArrayList<String>, because the constructor receives String data.
~~~

Type argument information can come from the target type, constructor arguments, or a suitable inference context. A raw type is **omitting the type arguments of a generic type**, not any situation where the compiler infers the type automatically.

## 7. A Generic Method Does Not Mean the Class Is Generic

Do not conflate two concepts:

~~~java
final class Utilities {
    static <T> T same(T value) {
        return value;
    }
}
~~~

The `Utilities` class is **not generic** because the class itself has no `<T>`. However, the `same` method is a **generic method** declaring its own type parameter.

Usage:

~~~java
String result = Utilities.same("Java");
Integer number = Utilities.same(17);
~~~

This is normal and does not use a raw type. There is no `Utilities<String>` syntax because Utilities does not accept a type parameter at the class level.

A non-generic method returning Object:

~~~java
final class PlainFactory {
    static Object create() {
        return "Java";
    }
}
~~~

`PlainFactory` is also non-generic. A caller wanting to cast an Object to String is an ordinary check/cast situation, not automatically a raw type issue.

**Identification question:** is `<T>` placed on the **class/interface declaration** or only on the **method declaration**? A raw type is determined by the generic type itself, not by whether a class happens to have a standalone generic method.

## 8. A Non-Generic Subclass Can Still Extend a Generic Class

Example:

~~~java
class Base<T> {
    T value;

    Base(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}

// FixedStringBox declares no type parameter.
final class FixedStringBox extends Base<String> {
    FixedStringBox(String value) {
        super(value);
    }
}
~~~

`FixedStringBox` is a **non-generic class**: it has no type parameter list in its own declaration. However, it extends `Base<String>`, so:

~~~java
FixedStringBox box = new FixedStringBox("Java");
String text = box.get(); // Return type is specialized to String.
~~~

Using `FixedStringBox` is **not raw**, and the compiler still checks the members specialized from Base<String>.

If you replace the superclass with `extends Base` without String, that is a **raw use of Base** in the inheritance clause. The subclass itself can still be non-generic, but extending a raw superclass loses type information for the related generic members.

This is an important counterexample to the misconception that "any class that ever touches generics must write `<...>` on its own name".

## 9. Are `rawtypes` and `unchecked` Warnings the Same Error?

These two warning groups often appear together but are not identical:

- **rawtypes**: you used a generic name in raw form, such as `List raw;`.
- **unchecked**: the compiler detects a generic-related operation whose type safety cannot be fully proved, such as calling `raw.add(42)` or converting raw List to List<String>.

Example intentionally triggering warnings:

~~~java
List raw = new ArrayList();
raw.add("Java");
List<String> strings = raw; // Unchecked conversion.
~~~

Assigning a raw List to List<String> can be accepted by the compiler with a warning due to legacy compatibility. It **does not check every element of the list at runtime**. If the raw List already held a non-String object, a failure may surface later when data is retrieved as String.

For a non-generic class:

~~~java
final class Plain {
    Object read() {
        return 42;
    }
}
~~~

Writing `Plain p = new Plain(); Object n = p.read();` has no reason to emit rawtypes or unchecked warnings simply because Plain does not use generics. If you cast `(String) p.read()`, that is a runtime cast that may fail—a separate issue.

### Using javac options properly

~~~bash
javac -Xlint:rawtypes -Xlint:unchecked YourFile.java
~~~

This command asks javac to report warnings related to raw and unchecked usage. Line numbers and diagnostic formatting vary by JDK and source code; do not write logic that depends on exact warning lines.

**Do not hide all warnings** with `@SuppressWarnings({"rawtypes", "unchecked"})` across an entire file. If you must use a legacy API, keep the raw section as small as possible, validate data before converting to a parameterized type, and document the verified assumption.

## 10. Why Do Raw Types Exist in Java?

Generics were added in Java 5. Many libraries and applications already had interfaces or classes using collections before then. To support compilation and binary compatibility with legacy code, Java allows generic names to be used in raw form.

~~~java
// Pre-generics style:
List legacy = new ArrayList();

// Modern style:
List<String> modern = new ArrayList<>();
~~~

Raw types are an **intentional backward-compatibility mechanism**, not required syntax for new Java programs.

This also explains why generics mostly use type erasure in bytecode. But make the distinction: **type erasure happens even when generics are used properly**, such as `List<String>`. You cannot look at a bytecode descriptor returning Object and conclude the source code used a raw type.

### Sharing the same runtime class does not make two compile-time types equal

Example in a running program:

~~~java
GenericBox<String> typed = new GenericBox<>("A");
GenericBox raw = new GenericBox("B");
boolean sameClass = typed.getClass() == raw.getClass();
~~~

`sameClass` is true for ordinary generic classes due to erasure. However, the typed variable is still checked by the compiler as `GenericBox<String>`, while raw loses parameter information in many operations. This is a **compile-time difference** with real consequences, even though `getClass()` matches.

## 11. Easily Misunderstood Cases

### Case A: `Class` and `Class<?>` are not the same

`java.lang.Class<T>` is a generic class:

~~~java
Class rawClass = String.class; // Raw type.
Class<?> anyClass = String.class; // Parameterized type with wildcard.
Class<String> stringClass = String.class; // Concrete parameterized type.
~~~

`Class<?>` is usually appropriate when handling metadata about a class whose type parameter is unknown. Raw `Class` easily drops related type checks. The fact that `String.class` has type `Class<String>` does not make `String` a generic type.

### Case B: Arrays are not raw generics

~~~java
String[] words = {"A", "B"};
int[] numbers = {1, 2};
~~~

Array types do not have type parameters the way `List<E>` does. Using String[] or int[] arrays is not a raw type. Arrays have a different runtime type-checking mechanism than generics; the two mechanisms should not be equated.

### Case C: A non-generic interface can be a functional interface

~~~java
Runnable task = () -> System.out.println("run");
task.run();
~~~

`Runnable` has no type parameter, so it is not raw. The presence of a lambda does not make that interface generic either.

### Case D: A list loses String because Object is inferred, yet is still not raw

~~~java
var values = new ArrayList<>();
values.add("Java");
values.add(42);
~~~

`values` is inferred as ArrayList<Object> in this case. This is a parameterized type with E = Object. Adding both String and Integer is permitted **under proper generic type checking for Object**, not because of raw usage.

### Case E: Non-generic subclass of a generic superclass

~~~java
final class StringList extends ArrayList<String> {}
StringList list = new StringList();
list.add("Java");
// list.add(42); // Rejected by compiler.
~~~

`StringList` has no `<T>` in its declaration, so using StringList is not raw. This class extends ArrayList<String>, so the add method is specialized to add(String) at the Java source checking level.

### Case F: Raw types do not erase every type structure in the program

The statement "using raw turns everything into Object" is overly broad. Members that do not use a type parameter can retain their explicit types, and the erasure of a bounded type parameter such as `T extends Number` is Number rather than Object. You need to inspect **the specific signature after erasure**, not assume every method/field has type Object.

## 12. How to Fix Raw Type Code When Encountered in a Project

When you see:

~~~java
List items = loadItems();
~~~

do not rush to replace it with `List<String>` without knowing the actual data contract. There are three approaches:

**When you know all elements have a specific type:** declare `List<String>`, update the signature of `loadItems` and data creation sites so the compiler checks types end to end.

**When you only need to read and the element type is unknown:** use `List<?>`, iterate over elements as Object, and check types where processing requires them.

**When receiving data from legacy APIs or untrusted code:** validate the data before converting it into an explicitly typed collection:

~~~java
static List<String> validatedCopy(List<?> source) {
    List<String> result = new ArrayList<>();

    for (Object element : source) {
        if (!(element instanceof String text)) {
            throw new IllegalArgumentException("Only String is allowed");
        }
        result.add(text);
    }

    return result;
}
~~~

The code above works with Java 17+, uses pattern matching for instanceof, and creates a new list containing elements verified to be String. It rejects null; if business rules allow null, you must design a separate policy.

This is a safer conversion path than:

~~~java
@SuppressWarnings("unchecked")
List<String> assumed = (List<String>) raw;
~~~

Casting raw List to List<String> does not verify the type of each element, so errors can surface late when reading.

**Legacy code upgrade workflow:**

1. Identify the base declaration: is the type being used generic or non-generic?
2. For raw generics, determine the right type argument from the business domain instead of picking Object arbitrarily.
3. Use `?` if the type argument is genuinely unknown and the API does not need to add elements.
4. Locate unchecked warnings, data write paths, and raw aliases that could cause heap pollution.
5. Update one API boundary at a time under control and test collection reads/writes.
6. For non-generic types that fit the design, there is no need to "generify" them just to eliminate warnings that do not exist.

## 13. Quick Identification Table

| Syntax | Base type declaration | Classification |
| --- | --- | --- |
| `String s` | String has no type parameter | Non-generic type |
| `Runnable r` | Runnable has no type parameter | Non-generic type |
| `LegacyBox x` | LegacyBox is declared non-generic | Non-generic type |
| `List list` | List<E> has E, omitted at use site | Raw type |
| `ArrayList list` | ArrayList<E> has E, omitted | Raw type |
| `List<Object> list` | List<E> with E = Object | Parameterized type |
| `List<?> list` | List<E> with wildcard type argument | Parameterized type |
| `var list = new ArrayList<>()` | Diamond infers ArrayList<Object> when no other constraint exists | Parameterized type, not raw |
| `class Fixed extends Base<String>` | Fixed has no type parameter, Base does | Fixed is a non-generic class using a parameterized superclass |
| `Class clazz` | Class<T> omits T | Raw type |
| `Class<?> clazz` | Class<T> with wildcard | Parameterized type |
| `String[] array` | Array type of String | Array type, not raw |

Classification must be based on **the base declaration and the use site**, not merely surface appearance. In particular, `Object` appearing after erasure is not enough to conclude a snippet uses raw types.

## 14. Self-Check Questions

**Question 1.** Is `class A {}` followed by `A a = new A();` a raw type?

**Answer:** No. A declares no type parameter, so it is inherently a non-generic type. No generic parameter was omitted.

**Question 2.** Is `List<?> a = new ArrayList<String>();` a raw type?

**Answer:** Variable a has parameterized type `List<?>`, not raw. Likewise, the expression `new ArrayList<String>()` is also a parameterized constructor type; both use generics, even though the wildcard does not reveal the concrete element type.

**Question 3.** `var a = new ArrayList<>();` infers ArrayList<Object>. Should a be called a raw type?

**Answer:** No. Object is a concrete type argument inferred by the compiler; a still has type `ArrayList<Object>`.

**Question 4.** Is `class StringBox extends Box<String>` a generic class?

**Answer:** No, if StringBox does not declare a type parameter of its own. However, it extends a parameterized superclass, so the generic methods are specialized accordingly for String.

**Question 5.** Why can `List<Object>` not accept a `List<String>`, whereas raw `List` can be assigned from `List<String>`?

**Answer:** Java generics are invariant to prevent inserting wrong-typed elements. Raw List exists for legacy code compatibility and drops type argument checking on related operations, thus allowing risky aliases.

**Question 6.** How do `Class<String>`, `Class<?>`, and `Class` differ?

**Answer:** The first two forms are parameterized types (concrete and wildcard); the last form is a raw use of the generic class `Class<T>`.

**Question 7.** Why is a non-generic class returning Object not automatically a source of unchecked warnings?

**Answer:** Returning Object is the directly declared API type. Unchecked warnings relate to generic operations that cannot be proved safe, such as raw conversions/calls; a non-generic class itself has no omitted type argument.

## 15. Key Takeaways

**Raw type = using an inherently generic type while omitting type arguments. Non-generic type = a type declaration that inherently has no type parameters.** Both cases may contain methods returning Object, yet they are fundamentally different.

In modern Java, prefer `List<String>` when the exact element type is known, `List<?>` when you only need to handle a list of unknown element type, and use raw generics only in narrow scopes when integrating legacy code with a clear reason. The compiler and `-Xlint:rawtypes -Xlint:unchecked` help point out where type information was dropped, while actual data validation is necessary when crossing unsafe boundaries.
