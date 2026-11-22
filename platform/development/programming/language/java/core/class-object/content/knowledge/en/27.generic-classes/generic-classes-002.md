# Declaring the `Box<T>` Class, Fields, and Methods Using `T` in Java 17+

A **generic class** allows a class to work with multiple data types while still being **type-checked at compile time**. Sample syntax:

~~~java
class Box<T> {
    private T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }

    void set(T value) {
        this.value = value;
    }
}
~~~

`T` is a **type parameter**, representing a reference type chosen by the user of Box when declaring `Box<String>`, `Box<Integer>`, `Box<Customer>`, etc.

~~~java
Box<String> title = new Box<>("Java");
String text = title.get();       // The compiler knows the result is String.
title.set("Generics");          // Valid.
// title.set(123);             // Compile error: int/Integer is not String.
~~~

This lesson focuses on **declaring the `Box<T>` class and designing fields/constructors/methods that use `T`**. Extended topics such as bounds, wildcards, type erasure, generic methods, and restrictions are explained so you can use Box properly, but all examples refer back to a simple generic class.

**Environment:** Java 17 and above. Examples with a filename are **standalone programs**; each example contains all necessary classes, along with `javac --release 17` and `java` commands and expected stdout. Snippets illustrating compiler errors are always commented out or separated; they are not mixed into runnable programs.

## 1. Learning Outcomes

After this lesson, you will be able to:

- Declare a generic class with one type parameter `T`.
- Distinguish between **type parameter** `T` and **type argument** `String`.
- Use `T` for an instance field, constructor parameter, method parameter, and return type.
- Instantiate `Box<String>` and `Box<Integer>` using the diamond syntax `<>`.
- Explain how the compiler prevents passing the wrong type to `set(T)`.
- Know that `T` is scoped within the class declaration and related instance members.
- Write methods to change a value, get the previous value, check for emptiness, and transform data.
- Understand the difference between a mutable `Box<T>` and an immutable Box.
- Distinguish a **class** type parameter from a **generic method** type parameter.
- Know that static members cannot directly reference the class type parameter `T`.
- Understand generic type erasure at the level it affects `new T()`, `T.class`, and runtime tests.
- Avoid using raw `Box` unless there is a clear legacy interop reason.
- Understand autoboxing when using primitive-like values.
- Know that `Box<String>` is not a subtype of `Box<Object>`.
- Use wildcard references when an API needs to read multiple types of Box.
- Use bounded type parameters to call methods not present on Object.
- Distinguish null policy from type safety.
- Avoid exposing mutable objects with improper ownership.
- Design a generic Box compatible with `equals/hashCode/toString` if needed.
- Write unit-like tests demonstrating behavior and expected compile errors.

## 2. What Is Inconvenient Without Generics?

Before generics, a container could store `Object`:

~~~java
class ObjectBox {
    private Object value;

    ObjectBox(Object value) {
        this.value = value;
    }

    Object get() {
        return value;
    }
}
~~~

Clients must cast:

~~~java
ObjectBox box = new ObjectBox("Java");
String text = (String) box.get();
~~~

If the box holds an Integer instead of a String, a wrong cast can lead to a `ClassCastException` at runtime. The compiler does not guarantee that ObjectBox holds only one type.

With `Box<T>`:

~~~java
Box<String> box = new Box<>("Java");
String text = box.get();
~~~

The compiler knows the contract of the Box instance from the String type argument. Attempting `box.set(42)` will be rejected early at compile time.

**Generics provide compile-time type safety and reduce casts**, without manually creating new class source code for each type.

## 3. Runnable Program: First Box

Create **`BasicBoxDemo.java`**:

~~~java
public class BasicBoxDemo {
    static final class Box<T> {
        private T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        void set(T value) {
            this.value = value;
        }
    }

    public static void main(String[] args) {
        Box<String> message = new Box<>("Java");
        Box<Integer> count = new Box<>(17);

        System.out.println("before=" + message.get());
        message.set("Generics");

        System.out.println("after=" + message.get());
        System.out.println("count=" + count.get());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 BasicBoxDemo.java
java BasicBoxDemo
~~~

Stdout:

~~~text
before=Java
after=Generics
count=17
~~~

The same Box<T> declaration is used with String and Integer. `get()` returns the exact type of each `Box<String>` or `Box<Integer>` reference.

## 4. Anatomy of the `class Box<T>` Declaration

~~~java
class Box<T> {
    private T value;
}
~~~

| Component | Meaning |
| --- | --- |
| `class` | Class declaration |
| `Box` | Class name |
| `<T>` | List of type parameters, here containing one `T` |
| `T value` | Instance field whose type is the type parameter |
| `Box<String>` | Parameterized type with actual type argument String |
| `Box<Integer>` | Parameterized type with actual type argument Integer |

`T` is not a Java keyword, and it is not a class named "T". It is an identifier representing a type chosen by the caller.

The name can be changed:

~~~java
class Container<Element> {
    private Element value;
}
~~~

However, by Java convention, common single-uppercase-letter names are `T` (type), `E` (element), `K` (key), `V` (value), and `R` (result). Choose readable names when a class has multiple parameters.

## 5. Type Parameter and Type Argument Are Two Different Concepts

In the declaration:

~~~java
class Box<T> {}
~~~

`T` is a **type parameter**.

At the use site:

~~~java
Box<String> words;
Box<Integer> numbers;
~~~

`String` and `Integer` are **type arguments**.

When the type argument is String, the positions in the Box API that use `T` are seen as String at compile time:

~~~java
Box<String> box = new Box<>("A");
String value = box.get();
box.set("B");
~~~

There is no Java syntax to use a primitive directly as a reference type argument:

~~~java
// Box<int> error;       // Invalid: primitive int is not a reference type argument.
Box<Integer> correct;   // Valid: Integer is a reference type.
~~~

Autoboxing supports writing `new Box<>(17)` when the target type is `Box<Integer>`.

## 6. Scope of `T` Inside the Class

The class type parameter `T` can be used in:

- Instance fields: `private T value;`
- Constructor parameters: `Box(T initial)`
- Instance method parameters: `void set(T next)`
- Instance method returns: `T get()`
- Local variables: `T previous = value;`
- Parameterized types: `List<T>` or `Optional<T>`
- Nested instance/member type contexts according to Java scope rules.

A class type parameter cannot be treated as a global type variable for static methods to use arbitrarily.

~~~java
class Box<T> {
    private T value;     // Valid.

    T get() {
        return value;    // Valid.
    }

    // static T shared; // Invalid.
    // static T getShared() { return null; } // Invalid.
}
~~~

A static member is not tied to a specific `Box<String>` or `Box<Integer>` instance; therefore, the class parameter `T` cannot be used directly in that static context.

## 7. Fields Using `T` and Data Ownership

Example:

~~~java
class Box<T> {
    private T value;
}
~~~

The `value` field stores:
- a reference to an object if T is a reference type;
- `null` if you allow it;
- a reference to a wrapper if using Box<Integer>, Box<Boolean>, etc.

A generic field **does not clone the object** and does not control mutability. With `Box<ArrayList<String>>`, the caller and the Box can point to the same mutable list if the constructor stores a direct reference.

**Design:** Fields should be `private`. A public mutable `T value` allows callers to bypass the setter's validation/logic. If you want a read-only Box, choose `private final T value` and do not declare a setter.

## 8. Constructor Accepting a Parameter of Type `T`

~~~java
class Box<T> {
    private T value;

    Box(T value) {
        this.value = value;
    }
}
~~~

The constructor name **does not add `<T>` to the name itself**. `T` is already declared on `class Box<T>` and is in scope for the constructor.

Incorrect:

~~~java
// Box<T>(T value) {} // Invalid constructor declaration syntax.
~~~

Overloaded constructors are allowed, but pay attention to type erasure when creating overloads with the same erasure signature.

Example of a no-arg constructor:

~~~java
Box() {
    this.value = null;
}
~~~

Accepting an empty state is an API decision, not a required property of generics.

## 9. Runnable Program: Overloaded Constructors

Create **`BoxConstructorsDemo.java`**:

~~~java
public class BoxConstructorsDemo {
    static final class Box<T> {
        private T value;

        Box() {
            this.value = null;
        }

        Box(T value) {
            this.value = value;
        }

        boolean isEmpty() {
            return value == null;
        }

        T get() {
            return value;
        }
    }

    public static void main(String[] args) {
        Box<String> empty = new Box<>();
        Box<String> filled = new Box<>("Java");

        System.out.println("empty=" + empty.isEmpty());
        System.out.println("filled=" + filled.isEmpty());
        System.out.println("value=" + filled.get());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 BoxConstructorsDemo.java
java BoxConstructorsDemo
~~~

Stdout:

~~~text
empty=true
filled=false
value=Java
~~~

A class can have multiple constructors; the type parameter T still applies consistently. If the API forbids null, validate it and only provide constructors that follow that contract.

## 10. Getter: Method Returning `T`

~~~java
T get() {
    return value;
}
~~~

For `Box<String>`, the compiler sees the `get()` method as returning String. For `Box<Integer>`, the compiler sees it as returning Integer.

~~~java
Box<String> words = new Box<>("hello");
String text = words.get();

// Integer wrong = words.get(); // Compile error.
~~~

This is the compile-time view of the generic API. At runtime, metadata may differ due to type erasure, but the caller does not need to cast manually when using the parameterized type properly.

### Naming

`get()` is appropriate when Box holds only one value. If the field carries domain meaning, a `value()` method can also be clear. You should use a consistent contract so the API is easy to learn.

## 11. Setter: Method Accepting `T`

~~~java
void set(T newValue) {
    value = newValue;
}
~~~

For `Box<String>`, the parameter `T` corresponds to String at the call site; for Box<Integer>, it corresponds to Integer.

Not allowed:

~~~java
Box<String> names = new Box<>("Mai");
// names.set(42); // Wrong argument type.
~~~

If the setter validates null or enforces a domain invariant, every setter call must go through that check. However, do not assume that generics make the compiler check whether the String *content* is blank: generics only check the type.

## 12. Runnable Program: Getter, Setter, and Errors Prevented at Compile Time

Create **`GetterSetterDemo.java`**:

~~~java
public class GetterSetterDemo {
    static final class Box<T> {
        private T value;

        Box(T initial) {
            this.value = initial;
        }

        T get() {
            return value;
        }

        void set(T next) {
            value = next;
        }
    }

    public static void main(String[] args) {
        Box<String> box = new Box<>("first");

        String before = box.get();
        box.set("second");

        System.out.println(before);
        System.out.println(box.get());

        // box.set(123); // Uncomment: compile error.
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 GetterSetterDemo.java
java GetterSetterDemo
~~~

Stdout:

~~~text
first
second
~~~

Uncomment `box.set(123)` to see javac reject an argument that cannot be converted to String.

## 13. Method Both Accepting and Returning `T`: `replace`

A generic Box can change its value and return the previous value:

~~~java
T replace(T next) {
    T previous = value;
    value = next;
    return previous;
}
~~~

`T` in both input and output enforces the same type contract.

### Runnable Program

Create **`ReplaceBoxDemo.java`**:

~~~java
public class ReplaceBoxDemo {
    static final class Box<T> {
        private T value;

        Box(T initial) {
            value = initial;
        }

        T replace(T next) {
            T previous = value;
            value = next;
            return previous;
        }

        T get() {
            return value;
        }
    }

    public static void main(String[] args) {
        Box<Integer> count = new Box<>(10);

        Integer old = count.replace(20);

        System.out.println("old=" + old);
        System.out.println("now=" + count.get());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ReplaceBoxDemo.java
java ReplaceBoxDemo
~~~

Stdout:

~~~text
old=10
now=20
~~~

Returning `T` does not require the same object reference; it is the same **type parameter contract**.

## 14. Methods Do Not Have to Use `T` Everywhere

A generic class can still have ordinary methods:

~~~java
class Box<T> {
    private T value;

    int descriptionLength() {
        return String.valueOf(value).length();
    }

    boolean isEmpty() {
        return value == null;
    }
}
~~~

`isEmpty()` returns boolean, not T. `descriptionLength()` returns int. Generics do not require all methods of a generic class to be generic.

Distinguish between:
- **Generic class:** a class with a `<T>` parameter.
- **Method uses T:** an instance method that uses the existing type parameter.
- **Generic method:** a method that **declares its own type parameter**, for example `<U> U convert(...)`.

## 15. Runnable Program: Ordinary Methods in a Generic Class

Create **`BoxMethodsDemo.java`**:

~~~java
public class BoxMethodsDemo {
    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        boolean isEmpty() {
            return value == null;
        }

        String describe() {
            return "Box(" + value + ")";
        }
    }

    public static void main(String[] args) {
        Box<String> first = new Box<>("Java");
        Box<String> second = new Box<>(null);

        System.out.println(first.describe());
        System.out.println(first.isEmpty());
        System.out.println(second.isEmpty());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 BoxMethodsDemo.java
java BoxMethodsDemo
~~~

Stdout:

~~~text
Box(Java)
false
true
~~~

Use `String.valueOf(value)` when you need null-safe formatting; string concatenation with a nullable reference prints the text "null" instead of throwing an NPE.

## 16. Mutable Box and Immutable Box: Choosing the Intent

**Mutable Box**:

~~~java
class Box<T> {
    private T value;

    Box(T value) {
        this.value = value;
    }

    void set(T next) {
        value = next;
    }
}
~~~

**Immutable-by-field Box**:

~~~java
final class ImmutableBox<T> {
    private final T value;

    ImmutableBox(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
~~~

`final T value` prevents reassigning the field. However, if T is a mutable object (such as ArrayList), the field is only a final reference — the object inside can still be mutated.

Choose a mutable Box if the lifecycle requires changing the reference, and an immutable Box if you want a **value holder** whose reference does not change after construction.

## 17. Runnable Program: Immutable Box Creating a New Instance on Change

Create **`ImmutableBoxDemo.java`**:

~~~java
public class ImmutableBoxDemo {
    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        Box<T> withValue(T next) {
            return new Box<>(next);
        }
    }

    public static void main(String[] args) {
        Box<String> before = new Box<>("A");
        Box<String> after = before.withValue("B");

        System.out.println("before=" + before.get());
        System.out.println("after=" + after.get());
        System.out.println("same instance=" + (before == after));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ImmutableBoxDemo.java
java ImmutableBoxDemo
~~~

Stdout:

~~~text
before=A
after=B
same instance=false
~~~

The `withValue` method returns another Box<T>; it does not mutate the current Box.

## 18. Null Policy for a Generic Box

`T` is a reference type, so null is usually type-correct:

~~~java
Box<String> box = new Box<>(null);
~~~

If the API forbids null, use validation:

~~~java
Box(T value) {
    this.value = java.util.Objects.requireNonNull(
            value, "value");
}
~~~

The setter must also validate:

~~~java
void set(T next) {
    value = java.util.Objects.requireNonNull(next, "value");
}
~~~

**Generic type safety does not automatically provide null safety.** `Box<String>` guarantees the right kind of reference at compile time, but does not guarantee it is non-null.

If null represents an empty state, clearly provide `isEmpty()`, `getOrDefault()`, or consider `Optional<T>` when the API truly represents “having or not having a value”.

## 19. Runnable Program: Checking Null in Constructor and Setter

Create **`NonNullBoxDemo.java`**:

~~~java
import java.util.Objects;

public class NonNullBoxDemo {
    static final class Box<T> {
        private T value;

        Box(T value) {
            this.value = Objects.requireNonNull(value, "value");
        }

        void set(T next) {
            value = Objects.requireNonNull(next, "value");
        }

        T get() {
            return value;
        }
    }

    public static void main(String[] args) {
        Box<String> box = new Box<>("Java");

        try {
            box.set(null);
        } catch (NullPointerException ex) {
            System.out.println("rejected=" + ex.getMessage());
        }

        System.out.println("after=" + box.get());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 NonNullBoxDemo.java
java NonNullBoxDemo
~~~

Stdout:

~~~text
rejected=value
after=Java
~~~

If the setter throws before assigning the field, Box retains its previous value. This is a simple invariant-preservation principle.

## 20. Diamond `<>` and Type Inference

The two forms are usually equivalent in terms of type:

~~~java
Box<String> first = new Box<String>("Java");
Box<String> second = new Box<>("Java");
~~~

The diamond `<>` lets the compiler infer the type arguments of the constructor expression from the context and arguments.

However, do not be mistaken:

~~~java
var box = new Box<>("Java");
~~~

Here the target type is not a declared `Box<String>`, yet the compiler can still infer T from the constructor argument `"Java"`. In the case where the constructor receives null:

~~~java
// var box = new Box<>(null);
~~~

inference may result in a type that is broader than intended. Prefer specifying an explicit declared type:

~~~java
Box<String> box = new Box<>(null);
~~~

if null is a state allowed by the contract.

## 21. Runnable Program: Diamond and Local `var`

Create **`DiamondBoxDemo.java`**:

~~~java
public class DiamondBoxDemo {
    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    public static void main(String[] args) {
        Box<String> declared = new Box<>("Java");
        var inferred = new Box<>(17);

        System.out.println(declared.get());
        System.out.println(inferred.get());

        Integer value = inferred.get();
        System.out.println(value + 1);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 DiamondBoxDemo.java
java DiamondBoxDemo
~~~

Stdout:

~~~text
Java
17
18
~~~

`var inferred = new Box<>(17)` infers Box<Integer> from the argument; it does not turn Java into dynamic typing.

## 22. Autoboxing: Why Does `Box<Integer>` Accept `17`?

Java generic type arguments must be reference types. Primitive `int` cannot appear in `Box<int>`.

~~~java
Box<Integer> number = new Box<>(17);
~~~

`17` is an int literal, but autoboxing creates/converts to Integer when needed. The getter can unbox:

~~~java
int value = number.get();
~~~

However, if Box<Integer> allows null, auto-unboxing null will throw a `NullPointerException`.

### Performance

Using wrappers can incur allocation/boxing overhead in some workloads. Do not optimize by guessing; if you are processing millions of primitive values, primitive arrays or specialized APIs may be more suitable than a generic Box<Integer>.

## 23. Runnable Program: Box<Integer> and Unboxing

Create **`BoxingBoxDemo.java`**:

~~~java
public class BoxingBoxDemo {
    static final class Box<T> {
        private T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    public static void main(String[] args) {
        Box<Integer> number = new Box<>(21);

        int doubled = number.get() * 2;
        System.out.println("doubled=" + doubled);

        Box<Integer> empty = new Box<>(null);
        try {
            int ignored = empty.get();
            System.out.println(ignored);
        } catch (NullPointerException ex) {
            System.out.println("cannot unbox null");
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 BoxingBoxDemo.java
java BoxingBoxDemo
~~~

Stdout:

~~~text
doubled=42
cannot unbox null
~~~

Box<Integer> does not protect against null on its own. If null is forbidden, constructor validation helps prevent late errors.

## 24. Raw `Box` Differs from `Box<T>`

`Box raw = new Box("value")` is usage of a raw type, not shorthand syntax for `Box<String>`. Raw aliases bypass generic compile-time checks when calling the setter. New code should declare the proper type argument or use `Box<?>` if the API only needs to read an unknown type.

## 25. Runnable Program: Raw Alias Causes Errors to Surface at the Typed Getter

Save **`RawBoxBoundaryDemo.java`**:

~~~java
public class RawBoxBoundaryDemo {
    static final class Box<T> {
        private T value;
        Box(T value) { this.value = value; }
        void set(T next) { value = next; }
        T get() { return value; }
    }

    @SuppressWarnings({"rawtypes", "unchecked"})
    static void legacyWrite(Box<String> typed) {
        Box raw = typed;
        raw.set(17);
    }

    public static void main(String[] args) {
        Box<String> words = new Box<>("Java");
        legacyWrite(words);
        try {
            String value = words.get();
            System.out.println(value);
        } catch (ClassCastException ex) {
            System.out.println("unsafe read rejected");
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RawBoxBoundaryDemo.java
java RawBoxBoundaryDemo
~~~

~~~text
unsafe read rejected
~~~

The annotation only isolates **demonstrating** unsafe legacy code; it is not a fix for the bug. Do not try to add a raw cast to make a method compile when type arguments do not match.

## 26. Type Erasure Does Not Remove Type Relationships in Source Code

`Box<String>` and `Box<Integer>` use the same runtime declaration. The unbounded field `T value` has the erased field type `Object`, while typed getter calls have matching casts. The compiler still rejects `words.set(17)` when only typed `Box<String>` references are used according to the contract.

## 27. Two Parameterizations Share the Same Runtime Class

~~~java
// With the Box<T> declaration above:
Box<String> text = new Box<>("A");
Box<Integer> count = new Box<>(3);
boolean sameRuntimeClass = text.getClass() == count.getClass();
~~~

This is an **explanatory fragment**, not standalone source code; the boolean is true if both objects are created from the same Box declaration/classloader. Generic signatures/reflection/bridge methods are covered in depth in the erasure section; the focus here is the **consistent relationship between the field of type T, constructor, setter, and getter**, not JVM bytecode structure.

## 28. Cannot Write `new T()`, `T.class`, or `new T[]`

The following snippets are invalid with an unbounded T:

~~~java
class Box<T> {
    // T create() { return new T(); }    // Error.
    // Class<T> type() { return T.class; } // Error.
    // T[] values = new T[10];            // Error.
}
~~~

Reason: `T` is a type parameter; after erasure, the compiler/JVM lacks the necessary information to construct the exact runtime class in that way.

### Alternatives

1. **Accept the object from the caller** via `Box(T value)`.
2. **Accept a factory** such as `Supplier<? extends T>` if a new instance must be created.
3. **Accept a Class<T> type token** if the API needs to inspect/validate the runtime type.
4. Use a collection such as `List<T>` instead of a generic array when appropriate.

Nor can you assume a constructor can use `new T()` just because T has a bound. A bound does not automatically provide a generic constructor call.

## 29. Runnable Program: `Supplier<? extends T>` Factory

Create **`SupplierBoxDemo.java`**:

~~~java
import java.util.Objects;
import java.util.function.Supplier;

public class SupplierBoxDemo {
    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        static <U> Box<U> from(Supplier<? extends U> factory) {
            Objects.requireNonNull(factory, "factory");
            return new Box<>(factory.get());
        }

        T get() {
            return value;
        }
    }

    public static void main(String[] args) {
        Box<StringBuilder> box =
                Box.from(() -> new StringBuilder("Java"));

        System.out.println(box.get().toString());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SupplierBoxDemo.java
java SupplierBoxDemo
~~~

Stdout:

~~~text
Java
~~~

`Supplier` is responsible for creating the object; Box does not need `new T()`. Because StringBuilder is mutable, the Box above is not deeply immutable even though the value field is final.

## 30. Class Type Parameter `T` and Static Generic Method `<U>`

Invalid:

~~~java
class Box<T> {
    // static Box<T> of(T value) { ... } // Cannot use class T in a static context.
}
~~~

Valid:

~~~java
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    static <U> Box<U> of(U value) {
        return new Box<>(value);
    }
}
~~~

`<U>` is placed **before the return type** of the static method to declare a completely separate method type parameter. This is not the class-level T.

Callers use:

~~~java
Box<String> text = Box.of("Java");
Box<Integer> number = Box.of(17);
~~~

The compiler usually infers `U` from the arguments and target context. You can write an explicit invocation `Box.<String>of("Java")` when needed.

## 31. Runnable Program: Static Generic Factory

Create **`StaticFactoryBoxDemo.java`**:

~~~java
public class StaticFactoryBoxDemo {
    static final class Box<T> {
        private final T value;

        private Box(T value) {
            this.value = value;
        }

        static <U> Box<U> of(U value) {
            return new Box<>(value);
        }

        T get() {
            return value;
        }
    }

    public static void main(String[] args) {
        Box<String> text = Box.of("Java");
        Box<Integer> count = Box.of(17);

        System.out.println(text.get());
        System.out.println(count.get());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 StaticFactoryBoxDemo.java
java StaticFactoryBoxDemo
~~~

Stdout:

~~~text
Java
17
~~~

The `Box.of` factory has a method type parameter and does not try to reference the class T from a static context.

## 32. Instance Generic Method with a New Parameter `U`

The class has `T` for the stored value. A method can add `U` to transform the type:

~~~java
<U> Box<U> map(java.util.function.Function<? super T, ? extends U> f) {
    return new Box<>(f.apply(value));
}
~~~

- `T` is the type of the current value.
- `U` is the type of the result.
- `Function<? super T, ? extends U>` allows the mapper to accept T and return a subtype of U.
- The return type `Box<U>` is a new Box.

You do not have to use wildcards right away when just learning; a `Function<T,U>` version also illustrates the idea. The broader form is widely used in collection/functional APIs.

## 33. Runnable Program: `map` from `Box<String>` to `Box<Integer>`

Create **`MapBoxDemo.java`**:

~~~java
import java.util.Objects;
import java.util.function.Function;

public class MapBoxDemo {
    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        <U> Box<U> map(Function<? super T, ? extends U> mapper) {
            Objects.requireNonNull(mapper, "mapper");
            return new Box<>(mapper.apply(value));
        }
    }

    public static void main(String[] args) {
        Box<String> text = new Box<>("Java");
        Box<Integer> length = text.map(String::length);

        System.out.println("text=" + text.get());
        System.out.println("length=" + length.get());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 MapBoxDemo.java
java MapBoxDemo
~~~

Stdout:

~~~text
text=Java
length=4
~~~

`map` transforms the type argument: from Box<String> to Box<Integer>, without assigning an Integer into the old Box<String> itself.

## 34. Reusing the Name `T` for a Method Type Parameter Can Be Confusing

Consider:

~~~java
class Box<T> {
    // <T> T transform(T input) { return input; }
}
~~~

A method can declare a type parameter **with the same name T** and shadow the class-level T according to lexical scope rules (when declared validly), but it is very easy to misread: the method's T is not necessarily the class's T.

**Avoid this pattern**. Use `<U>` or another meaningful name for the method-level parameter:

~~~java
<U> U convert(U value) {
    return value;
}
~~~

If a method needs to refer to the class T itself, do not declare a method type parameter with the same name: use `T` directly in the method signature.

## 35. A Generic Method and a Method Using T Are Different

Example placed inside `class Box<T>`:

~~~java
T echoStoredType(T value) {
    return value;
}

<U> U echoAnyType(U value) {
    return value;
}
~~~

`echoStoredType` constrains the argument to the class parameter T. `echoAnyType` has a method type parameter U, which can accept a different type from T.

Given `Box<String> box`:
- `box.echoStoredType("A")` is valid; `box.echoStoredType(17)` is a compile error.
- `box.echoAnyType(17)` is valid, and method U is inferred as Integer.

### Runnable Program

Create **`MethodTypeParameterDemo.java`**:

~~~java
public class MethodTypeParameterDemo {
    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T echoStoredType(T input) {
            return input;
        }

        <U> U echoAnyType(U input) {
            return input;
        }
    }

    public static void main(String[] args) {
        Box<String> box = new Box<>("Java");

        String a = box.echoStoredType("A");
        Integer b = box.echoAnyType(17);

        System.out.println(a);
        System.out.println(b);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 MethodTypeParameterDemo.java
java MethodTypeParameterDemo
~~~

Stdout:

~~~text
A
17
~~~

Method U does not change the type argument of the Box instance.

## 36. Multiple Type Parameters Are Allowed

A class can use `<K,V>` or `<A,B>`:

~~~java
class Pair<A, B> {
    private final A first;
    private final B second;

    Pair(A first, B second) {
        this.first = first;
        this.second = second;
    }

    A first() {
        return first;
    }

    B second() {
        return second;
    }
}
~~~

`Box<T>` uses one parameter because it only needs to hold one kind of data. When a model has two distinct type roles, defining two explicit parameters is useful.

### Do Not Overcomplicate Unnecessarily

Do not add `<T,U,V>` if the type parameters do not actually carry a contract. A type parameter should appear where callers benefit from a compile-time relationship between fields/parameters/returns.

## 37. Runnable Program: Box Holding a Pair

Create **`PairInBoxDemo.java`**:

~~~java
public class PairInBoxDemo {
    record Pair<A, B>(A first, B second) {}

    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    public static void main(String[] args) {
        Pair<String, Integer> pair = new Pair<>("Java", 17);
        Box<Pair<String, Integer>> box = new Box<>(pair);

        System.out.println(box.get().first());
        System.out.println(box.get().second());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 PairInBoxDemo.java
java PairInBoxDemo
~~~

Stdout:

~~~text
Java
17
~~~

The nested parameterized type `Box<Pair<String,Integer>>` is still fully type-checked.

## 38. When `Box<T>` Needs a New Capability: Bounding `T`

An unbounded Box only knows the operations of `Object`. If the object must process numbers, you can use `class NumericBox<T extends Number>` to call `doubleValue()` on the value of field T. A bound restricts type arguments, but does not automatically check for `null`, overflow, or precision.

## 39. Runnable Program: Bounded Field of Type T

Save **`NumericBoxBoundDemo.java`**:

~~~java
public class NumericBoxBoundDemo {
    static final class NumericBox<T extends Number> {
        private final T value;

        NumericBox(T value) {
            this.value = java.util.Objects.requireNonNull(value);
        }

        double twice() {
            return value.doubleValue() * 2;
        }
    }

    public static void main(String[] args) {
        NumericBox<Integer> integer = new NumericBox<>(7);
        NumericBox<Double> decimal = new NumericBox<>(2.5);

        System.out.println(integer.twice());
        System.out.println(decimal.twice());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 NumericBoxBoundDemo.java
java NumericBoxBoundDemo
~~~

~~~text
14.0
5.0
~~~

`NumericBox<String>` is invalid because String is not a Number. The example uses `doubleValue()` to demonstrate a type bound, **not** as an accurate monetary calculation formula.

## 40. A Type Parameter Can Have Multiple Bounds

`<T extends Number & Comparable<T>>` requires the capabilities of both Number and Comparable<T>; if there is a class bound, it must come before the interface bounds. You should not add multiple bounds just to be "more generic" when Box actually only needs to hold/return a value.

## 41. Comparable Can Be a Standalone Bound

With `<T extends Comparable<? super T>>`, a Box can call `value.compareTo(other)` according to the natural ordering contract. This is a **case where the API genuinely needs comparison**, not a default property of a generic Box. Intersection bounds, Comparable variance, and F-bounded patterns each have their own dedicated in-depth explanation. In this lesson on declaring `Box<T>`, choose the **minimal bounds needed to implement the behavior**.

## 42. `Box<String>` Is Not `Box<Object>`

Java generic parameterized types are **invariant** in general:

~~~java
Box<String> strings = new Box<>("Java");
// Box<Object> objects = strings; // Compile error.
~~~

Although String extends Object, `Box<String>` does not extend `Box<Object>`.

**Why?** If that assignment were allowed with a mutable Box:

~~~java
Box<Object> objects = strings;
objects.set(42);
String text = strings.get();
~~~

It breaks the String contract of the original Box. Java prevents the very first assignment.

### Do Not Cast Manually to Bypass This

Unchecked casts can turn a compile-time error into a runtime ClassCastException. Adjust the API with wildcards if the goal is to accept multiple Box variants.

## 43. Runnable Program: Using a Wildcard to Read Multiple Boxes

Create **`ReadWildcardBoxDemo.java`**:

~~~java
public class ReadWildcardBoxDemo {
    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    static void print(Box<?> box) {
        System.out.println(box.get());
    }

    public static void main(String[] args) {
        print(new Box<>("Java"));
        print(new Box<>(17));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ReadWildcardBoxDemo.java
java ReadWildcardBoxDemo
~~~

Stdout:

~~~text
Java
17
~~~

`Box<?>` can be read via `get()` and the result is assignable to Object. It does not allow writing an arbitrary non-null value because the compiler does not know the captured type.

## 44. `? extends` to Read Subtype Values

A method wanting to accept Boxes holding Number subclasses:

~~~java
static double read(Box<? extends Number> box) {
    return box.get().doubleValue();
}
~~~

Accepts `Box<Integer>` and `Box<Double>`:

~~~java
read(new Box<>(7));
read(new Box<>(2.5));
~~~

However, you cannot arbitrarily call `box.set(10)` when the parameter is `Box<? extends Number>`: the actual boxed subtype is unknown and could be Double, BigDecimal, etc.

PECS mnemonic: **Producer Extends**, **Consumer Super**. With `Box<? extends Number>`, Box is a producer of Number values for the method, primarily for reading.

## 45. Runnable Program: Producer Extends

Create **`ExtendsWildcardBoxDemo.java`**:

~~~java
public class ExtendsWildcardBoxDemo {
    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    static double read(Box<? extends Number> box) {
        return box.get().doubleValue();
    }

    public static void main(String[] args) {
        System.out.println(read(new Box<>(7)));
        System.out.println(read(new Box<>(2.5)));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ExtendsWildcardBoxDemo.java
java ExtendsWildcardBoxDemo
~~~

Stdout:

~~~text
7.0
2.5
~~~

An upper-bounded wildcard opens up a read API without having to assign `Box<Integer>` to `Box<Number>`.

## 46. `? super` for Type-Safe Writing

A method accepting `Box<? super Integer>` can accept:
- `Box<Integer>`;
- `Box<Number>`;
- `Box<Object>`.

Because all storage types are supertypes of Integer, the method can write an Integer:

~~~java
static void putInt(Box<? super Integer> box) {
    box.set(10);
}
~~~

However, `box.get()` can only be safely inferred as Object rather than Integer, because the actual Box could be Box<Object>.

PECS mnemonic: **Consumer Super** when Box is the receiver of values.

## 47. Runnable Program: Consumer Super

Create **`SuperWildcardBoxDemo.java`**:

~~~java
public class SuperWildcardBoxDemo {
    static final class Box<T> {
        private T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        void set(T next) {
            value = next;
        }
    }

    static void putInt(Box<? super Integer> box) {
        box.set(10);
    }

    public static void main(String[] args) {
        Box<Number> number = new Box<>(0);
        Box<Object> object = new Box<>("old");

        putInt(number);
        putInt(object);

        System.out.println(number.get());
        System.out.println(object.get());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SuperWildcardBoxDemo.java
java SuperWildcardBoxDemo
~~~

Stdout:

~~~text
10
10
~~~

`Box<? super Integer>` is not a way of expressing “Box<Integer>”; it is a wildcard reference to a Box whose actual type argument belongs to the allowed supertypes.

## 48. Wildcards Do Not Replace Class-Level `T`

If a method needs to **preserve an exact relationship between input and output**, its own type parameter is usually better than a wildcard:

~~~java
static <T> T roundTrip(Box<T> box, T replacement) {
    T old = box.get();
    box.set(replacement);
    return old;
}
~~~

Because the same type parameter T appears on Box, replacement, and the return type, the compiler checks that relationship.

By contrast, `Box<?>` says “there is some type argument, though the specific one is unknown,” which is useful for general reading/observation.

**Choose:**
- `Box<T>` inside a class to bind the stored value and methods.
- `Box<?>` when you do not care about the type argument.
- `Box<? extends X>` when reading values belonging to family X.
- `Box<? super X>` when writing values of type X.
- Method `<T>` when you need to correlate multiple parameters/return values.

## 49. Runnable Program: Generic Utility Using the Same `T`

Create **`RoundTripBoxDemo.java`**:

~~~java
public class RoundTripBoxDemo {
    static final class Box<T> {
        private T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        void set(T next) {
            value = next;
        }
    }

    static <T> T replaceAndReturnOld(Box<T> box, T next) {
        T old = box.get();
        box.set(next);
        return old;
    }

    public static void main(String[] args) {
        Box<String> box = new Box<>("A");

        String old = replaceAndReturnOld(box, "B");

        System.out.println("old=" + old);
        System.out.println("new=" + box.get());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RoundTripBoxDemo.java
java RoundTripBoxDemo
~~~

Stdout:

~~~text
old=A
new=B
~~~

The generic helper ensures that values have the same T without needing unchecked casts.

## 50. Type Erasure Can Cause a Method Signature Clash

Because an unbounded T erases to Object:

~~~java
class Box<T> {
    // void set(T value) {}
    // void set(Object value) {}
}
~~~

The two signatures have the same erasure `set(Object)`, so they cannot be overloaded as shown above. The Java compiler reports a name clash.

Similarly, you cannot overload methods that differ only in type arguments:

~~~java
// void accept(Box<String> box) {}
// void accept(Box<Integer> box) {}
~~~

Both erase to the same raw Box parameter signature. Use different method names, a single generic method, or an appropriate API structure.

**Remember:** Generics provide type checks at compile time, but do not create distinct overloads in the JVM descriptor solely from String vs Integer type arguments.

## 51. `instanceof` with Generic Types

Valid:

~~~java
Object value = new Box<>("Java");
boolean isBox = value instanceof Box<?>;
~~~

Invalid for testing a reified parameterization:

~~~java
// boolean isStringBox = value instanceof Box<String>; // Compile error.
~~~

Because the runtime class does not keep Box<String>/Box<Integer> separate as distinct class identities. Avoid building logic based on erased type arguments.

You can use the `instanceof Box<?> box` pattern (Java 17) to check the outer shape and retrieve an Object from `box.get()`:

~~~java
if (value instanceof Box<?> box) {
    Object content = box.get();
}
~~~

## 52. Runnable Program: `instanceof Box<?>`

Create **`InstanceofBoxDemo.java`**:

~~~java
public class InstanceofBoxDemo {
    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    static String describe(Object input) {
        if (input instanceof Box<?> box) {
            return "boxed:" + box.get();
        }
        return "other";
    }

    public static void main(String[] args) {
        System.out.println(describe(new Box<>("Java")));
        System.out.println(describe(17));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 InstanceofBoxDemo.java
java InstanceofBoxDemo
~~~

Stdout:

~~~text
boxed:Java
other
~~~

Java 17 `instanceof` patterns do not make erased type arguments runtime-reifiable.

## 53. When You Need to Know the Runtime Type: Passing `Class<T>`

A generic Box can accept a runtime class token:

~~~java
class TypedBox<T> {
    private final Class<T> type;
    private final T value;

    TypedBox(Class<T> type, T value) {
        this.type = type;
        this.value = type.cast(value);
    }
}
~~~

`Class<T>` helps perform runtime checks when data comes from an untyped boundary, however:
- `Class<List<String>>` cannot fully represent nested parameterized arguments using a simple reified Class object;
- a null policy is still needed;
- a type token only performs the role the API was designed for; it does not magically restore erased Java generics.

### Runnable Program

Create **`ClassTokenBoxDemo.java`**:

~~~java
import java.util.Objects;

public class ClassTokenBoxDemo {
    static final class TypedBox<T> {
        private final Class<T> type;
        private final T value;

        TypedBox(Class<T> type, Object value) {
            this.type = Objects.requireNonNull(type);
            this.value = type.cast(value);
        }

        T get() {
            return value;
        }

        String typeName() {
            return type.getSimpleName();
        }
    }

    public static void main(String[] args) {
        TypedBox<String> text =
                new TypedBox<>(String.class, "Java");

        System.out.println(text.typeName());
        System.out.println(text.get());

        try {
            new TypedBox<>(String.class, 17);
        } catch (ClassCastException ex) {
            System.out.println("wrong runtime type");
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ClassTokenBoxDemo.java
java ClassTokenBoxDemo
~~~

Stdout:

~~~text
String
Java
wrong runtime type
~~~

A class token is one solution when receiving an Object from reflection/parsing/boundaries; for normal generic code, compile-time typing is sufficient.

## 54. Does Box Guarantee That the Data Inside Is Immutable?

No. Consider:

~~~java
Box<java.util.List<String>> box = new Box<>(sourceList);
~~~

If Box keeps a direct reference, when the caller modifies sourceList, `box.get()` sees the change as well. Adding `final` to the Box field only prevents reassigning the reference; it does not snapshot the List structure.

### Three Design Approaches

1. **Document shared ownership:** Box holds the same reference, and consumers must understand mutability.
2. **Immutable element API:** Box only stores immutable values such as String, Integer, or immutable records.
3. **Explicit copier/factory:** accept a `UnaryOperator<T>`/copy function or design a dedicated wrapper type to snapshot mutable input.

You cannot write an accurate **generic deepCopy(T)** for any arbitrary T solely from a type parameter, because Java does not know the cloning/copy contract of all objects.

## 55. Runnable Program: Generic Box and Aliasing

Create **`AliasingBoxDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class AliasingBoxDemo {
    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A"));
        Box<List<String>> box = new Box<>(source);

        source.add("B");
        System.out.println(box.get());

        box.get().add("C");
        System.out.println(source);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 AliasingBoxDemo.java
java AliasingBoxDemo
~~~

Stdout:

~~~text
[A, B]
[A, B, C]
~~~

This is ordinary reference aliasing, not a bug in the generic type system. If the API wants a snapshot, switch to List.copyOf at an appropriate boundary or a domain-specific wrapper.

## 56. Defensive Copying Requires a Type-Specific Policy

Example of a specialized Box for List:

~~~java
final class ListBox<E> {
    private final java.util.List<E> value;

    ListBox(java.util.List<? extends E> input) {
        value = java.util.List.copyOf(input);
    }

    java.util.List<E> get() {
        return value;
    }
}
~~~

`List.copyOf` protects the **list structure** from mutations by the caller and returns an unmodifiable list, but **does not deep-copy mutable elements**. In addition, List.copyOf does not accept null elements.

You should not force the core `Box<T>` to call `List.copyOf` for every T: not every T is a List, and copy/immutability semantics depend on the domain.

If Box holds a `byte[]`, you can create a `BytesBox` using a cloning constructor/getter and appropriate content equality.

## 57. Runnable Program: Specialized ListBox<E>

Create **`ListBoxDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ListBoxDemo {
    static final class ListBox<E> {
        private final List<E> values;

        ListBox(List<? extends E> input) {
            values = List.copyOf(input);
        }

        List<E> get() {
            return values;
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A"));
        ListBox<String> box = new ListBox<>(source);

        source.add("B");
        System.out.println("source=" + source);
        System.out.println("box=" + box.get());

        try {
            box.get().add("C");
        } catch (UnsupportedOperationException ex) {
            System.out.println("unmodifiable");
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ListBoxDemo.java
java ListBoxDemo
~~~

Stdout:

~~~text
source=[A, B]
box=[A]
unmodifiable
~~~

The generic element parameter E and `List.copyOf` together protect the structure, but if E is mutable, the referenced elements can still be mutated.

## 58. `equals`/`hashCode` for Generic Box

If Box is a **value holder**, you can implement:

~~~java
@Override
public boolean equals(Object other) {
    return other instanceof Box<?> box &&
            java.util.Objects.equals(value, box.value);
}

@Override
public int hashCode() {
    return java.util.Objects.hashCode(value);
}
~~~

This compares `value` according to the equals contract of the contained type. With mutable values, equality/hash can change after mutation. With arrays, Object.equals uses array identity rather than element content.

If Box is a mutable reference holder with a distinct identity, overriding value equality may be **inappropriate**. Base the decision on domain semantics, not just syntax.

## 59. Runnable Program: Immutable Value Box with Equality

Create **`ValueBoxDemo.java`**:

~~~java
import java.util.Objects;

public class ValueBoxDemo {
    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof Box<?> box &&
                    Objects.equals(value, box.value);
        }

        @Override
        public int hashCode() {
            return Objects.hashCode(value);
        }

        @Override
        public String toString() {
            return "Box[" + value + "]";
        }
    }

    public static void main(String[] args) {
        Box<String> first = new Box<>("Java");
        Box<String> second = new Box<>("Java");

        System.out.println("equal=" + first.equals(second));
        System.out.println("hash equal=" +
                (first.hashCode() == second.hashCode()));
        System.out.println(first);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ValueBoxDemo.java
java ValueBoxDemo
~~~

Stdout:

~~~text
equal=true
hash equal=true
Box[Java]
~~~

If you want equality to distinguish parameterized types even when stored values are the same, type erasure makes the design more complex. This example defines equality by the contained value and does not promise runtime generic type argument identity.

## 60. Generic Box and Generic Record

Java 17 allows generic records:

~~~java
record Box<T>(T value) {}
~~~

Usage code:

~~~java
Box<String> box = new Box<>("Java");
String text = box.value();
~~~

A record automatically generates the `value()` accessor, canonical constructor, and equals/hashCode/toString based on its component.

### When to Use a Record?

- Need an immutable-by-field data carrier.
- The stored value is the logical state.
- Component-based equality makes sense.
- No setter or hidden instance state is needed.
- The defensive-copy policy can live in the canonical/compact constructor.

### When to Use a Class?

- Need a setter/mutable state.
- Need hidden caches/fields or to extend a base class.
- Need an API that does not expose its representation as a component.
- Need a constructor/behavior/lifecycle other than a value carrier.

## 61. Runnable Program: Generic Record Box<T>

Create **`GenericRecordBoxDemo.java`**:

~~~java
public class GenericRecordBoxDemo {
    record Box<T>(T value) {}

    public static void main(String[] args) {
        Box<String> a = new Box<>("Java");
        Box<String> b = new Box<>("Java");

        System.out.println(a.value());
        System.out.println(a.equals(b));
        System.out.println(a);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 GenericRecordBoxDemo.java
java GenericRecordBoxDemo
~~~

Stdout:

~~~text
Java
true
Box[value=Java]
~~~

Record<T> in the example is a generic reference type without a mutable setter. When T is mutable, a final component reference does not create deep immutability.

## 62. Inheritance with Generic Box

A subclass can **preserve the type parameter**:

~~~java
class NamedBox<T> extends Box<T> {
    private final String name;

    NamedBox(String name, T value) {
        super(value);
        this.name = name;
    }
}
~~~

Or **fix the type argument**:

~~~java
class StringBox extends Box<String> {
    StringBox(String value) {
        super(value);
    }
}
~~~

The two snippets above require the Box base class to be **non-final** and have an accessible constructor. If `Box` is final, it cannot be subclassed regardless of generic type parameters.

### Rules

- `NamedBox<T>` preserves generic extensibility.
- `StringBox` is a concrete class that fixes T=String.
- Do not manually cast wrong parameterizations to “inherit” from Box<Integer> to Box<String>.

## 63. Runnable Program: Subclasses Preserving T and Fixing T

Create **`GenericSubclassBoxDemo.java`**:

~~~java
public class GenericSubclassBoxDemo {
    static class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    static final class NamedBox<T> extends Box<T> {
        private final String name;

        NamedBox(String name, T value) {
            super(value);
            this.name = name;
        }

        String name() {
            return name;
        }
    }

    static final class StringBox extends Box<String> {
        StringBox(String text) {
            super(text);
        }
    }

    public static void main(String[] args) {
        NamedBox<Integer> number = new NamedBox<>("count", 7);
        StringBox word = new StringBox("Java");

        System.out.println(number.name() + "=" + number.get());
        System.out.println(word.get());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 GenericSubclassBoxDemo.java
java GenericSubclassBoxDemo
~~~

Stdout:

~~~text
count=7
Java
~~~

The subclass declaration decides whether the type parameter T is still supplied by the caller or fixed to String.

## 64. Generic Interface: `Holder<T>`

An interface can define a contract:

~~~java
interface Holder<T> {
    T get();
    void set(T value);
}
~~~

Box implements it:

~~~java
class Box<T> implements Holder<T> {
    private T value;

    public T get() {
        return value;
    }

    public void set(T value) {
        this.value = value;
    }
}
~~~

Because interface methods are public, implementations must also be public and cannot reduce accessibility.

### Benefits

Clients can write algorithms accepting `Holder<T>` without depending on a specific Box implementation. The generic interface parameter T maintains the compile-time type relationship.

## 65. Runnable Program: Box Implements Holder<T>

Create **`HolderInterfaceDemo.java`**:

~~~java
public class HolderInterfaceDemo {
    interface Holder<T> {
        T get();
        void set(T value);
    }

    static final class Box<T> implements Holder<T> {
        private T value;

        Box(T value) {
            this.value = value;
        }

        @Override
        public T get() {
            return value;
        }

        @Override
        public void set(T next) {
            value = next;
        }
    }

    static <T> void replace(Holder<T> holder, T next) {
        holder.set(next);
    }

    public static void main(String[] args) {
        Holder<String> holder = new Box<>("A");

        replace(holder, "B");
        System.out.println(holder.get());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 HolderInterfaceDemo.java
java HolderInterfaceDemo
~~~

Stdout:

~~~text
B
~~~

`Holder<String>` has the same type safety as Box<String>. The API can replace Box with another implementation without changing the contract.

## 66. Generics and Static Nested Classes

A static nested class does **not** directly use the type parameter T of the outer generic class:

~~~java
class Box<T> {
    static class Metadata {
        // T value; // Invalid: static nested context.
    }
}
~~~

However, a static nested class can declare its own type parameter:

~~~java
class Box<T> {
    static class Metadata<U> {
        U value;
    }
}
~~~

An ordinary non-static inner class tied to an outer instance can use the enclosing type parameter T according to scope rules.

You should not expand Box into a complex nested hierarchy if you only need to hold one field; however, understanding the static boundary helps avoid confusing compile errors.

## 67. Reflection of `T` Differs from Runtime Value Type

`Box<String>` and `Box<Integer>` share the runtime class Box; `getClass()` does not automatically indicate whether the parameter is String or Integer.

A class declaration can carry generic signature metadata for **type parameter declarations**, but an ordinary Box instance does not automatically have a runtime Class<String> attached just because it was declared as Box<String>.

If a framework has to deserialize JSON into `Box<List<User>>`, it usually needs a generic type descriptor (for example, `Type`, `ParameterizedType`, or a library-specific type token) instead of just `Box.class`.

This is a boundary concern; for the core Box<T> in type-safe Java source code, reflection is not needed to get/set values.

## 68. Exception Policy and Invariants

Box<T> can be a pure reusable container that does not know the domain of T. Therefore, only enforce invariants that **Box truly owns**:
- a non-null value if the contract forbids null;
- an immutable container if intended as a value holder;
- thread-safety if the API promises it;
- lifecycle state if there is ownership.

Rules such as “String is not blank” or “Integer must be positive” **cannot be inferred from T in general**. To validate by domain, you can:
- use a factory method accepting `Predicate<? super T>`;
- accept a validation strategy in the constructor;
- use a specialized class `PositiveIntegerBox`;
- validate at the boundary before creating Box.

## 69. Runnable Program: Validator Injected into Box

Create **`ValidatedBoxDemo.java`**:

~~~java
import java.util.Objects;
import java.util.function.Predicate;

public class ValidatedBoxDemo {
    static final class Box<T> {
        private T value;
        private final Predicate<? super T> validator;

        Box(T initial, Predicate<? super T> validator) {
            this.validator = Objects.requireNonNull(
                    validator, "validator");
            set(initial);
        }

        void set(T candidate) {
            if (!validator.test(candidate)) {
                throw new IllegalArgumentException("invalid value");
            }
            value = candidate;
        }

        T get() {
            return value;
        }
    }

    public static void main(String[] args) {
        Box<String> names = new Box<>(
                "Mai", text -> text != null && !text.isBlank());

        names.set("An");
        System.out.println(names.get());

        try {
            names.set(" ");
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected=" + ex.getMessage());
        }
        System.out.println(names.get());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ValidatedBoxDemo.java
java ValidatedBoxDemo
~~~

Stdout:

~~~text
An
rejected=invalid value
An
~~~

The generic container only knows how to call the supplied Predicate; the domain decides what constitutes a valid String. The setter does not modify value when validation fails.

## 70. Thread Safety of a Mutable Box

~~~java
class Box<T> {
    private T value;

    T get() {
        return value;
    }

    void set(T value) {
        this.value = value;
    }
}
~~~

This is **not an automatically thread-safe concurrent container**. If multiple threads read/write the same instance, you must define visibility/ordering/synchronization.

A `volatile T value` can provide visibility and atomic reference reads-writes for a single field; however, compound operations such as check-then-set or increment still require synchronized/atomic APIs.

A generic Box does not replace `AtomicReference<T>` for multi-threaded shared reference updates. If atomic compare-and-set is needed, `AtomicReference<T>` is usually better than reimplementing concurrency primitives.

## 71. Runnable Program: AtomicReference<T> as a Thread-Aware Box

Create **`AtomicReferenceDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicReference;

public class AtomicReferenceDemo {
    public static void main(String[] args) {
        AtomicReference<String> box =
                new AtomicReference<>("A");

        String old = box.getAndSet("B");

        System.out.println("old=" + old);
        System.out.println("now=" + box.get());
        System.out.println("swap=" +
                box.compareAndSet("B", "C"));
        System.out.println("final=" + box.get());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 AtomicReferenceDemo.java
java AtomicReferenceDemo
~~~

Stdout:

~~~text
old=A
now=B
swap=true
final=C
~~~

AtomicReference<T> is a JDK generic class with a clear concurrency contract. Only create a custom Box<T> if the API needs different behavior.

## 72. Generic Box and `Optional<T>`

Both Box<T> and Optional<T> can involve holding a value, but their purposes differ:

- `Box<T>` is a container you design yourself, which can be mutable and can allow null.
- `Optional<T>` represents the presence/absence of a value according to the JDK API, with methods such as `isPresent`, `orElse`, and `map`.
- There is no need to write your own Box if you actually just need to express a **possibly absent return value**.
- Do not use Optional as an arbitrary mutable field holder simply because it is generic.

For example, a data-lookup method can return `Optional<User>`; whereas a UI editor needing a mutable T reference can use StateHolder<T> or another domain class.

## 73. Runnable Program: Box's Own Map vs. Optional.map

Create **`BoxOptionalDemo.java`**:

~~~java
import java.util.Optional;

public class BoxOptionalDemo {
    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    public static void main(String[] args) {
        Box<String> box = new Box<>("Java");
        Optional<String> present = Optional.of("Java");
        Optional<String> absent = Optional.empty();

        System.out.println("box=" + box.get());
        System.out.println("present length=" +
                present.map(String::length).orElse(-1));
        System.out.println("absent length=" +
                absent.map(String::length).orElse(-1));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 BoxOptionalDemo.java
java BoxOptionalDemo
~~~

Stdout:

~~~text
box=Java
present length=4
absent length=-1
~~~

Optional has explicit “absence” semantics. Box only carries that meaning if your own API defines it.

## 74. Generic API Design: Do Not Overuse `Object`

You should not write a generic class and then lose its benefits by having public methods return Object:

~~~java
class Box<T> {
    private T value;

    Object get() {
        return value;
    }
}
~~~

If the goal is to preserve the type, return `T`:

~~~java
T get() {
    return value;
}
~~~

Similarly, the setter should accept `T` rather than accepting Object and doing an unchecked cast to T. If the API truly accepts an arbitrary Object, consider dropping the generic parameter or writing a clearly checked conversion method.

## 75. Type Parameter Naming Conventions

Common names:

| Name | Common Meaning |
| --- | --- |
| `T` | Type |
| `E` | Element |
| `K` | Key |
| `V` | Value |
| `R` | Result |
| `U`, `S` | Another parameter when T is already used |

`class Box<T>` is a common convention for an object container. If a class has multiple type parameters, clear names help understand return/argument relationships.

### Do Not Use `T` as a Logical Variable Name

~~~java
class Box<T> {
    private T value;
}
~~~

The type parameter `T` and the field `value` have different responsibilities. Naming the field `t` is still valid, but communicates meaning less clearly.

## 76. Common Compiler Errors with `Box<T>`

| Mistake | Why | How to Fix |
| --- | --- | --- |
| `Box<int>` | Primitive is not a reference type argument | `Box<Integer>` |
| `Box<String> b = new Box<Integer>(1)` | Incompatible type arguments | Align the types |
| `Box<Object> b = new Box<String>("x")` | Generics are invariant | `Box<?>` or wildcard API |
| `static T value` | Class T cannot be used in a static context | Instance field or static `<U>` factory |
| `new T()` | T is erased, cannot construct directly | Supplier/factory |
| `T.class` | Type parameter is not a reified Class literal | `Class<T>` token |
| `new T[10]` | Generic array creation restriction | List<T>/array factory |
| `value.someMethod()` with unbounded T | Compiler knows no methods beyond Object | Add bound/interface |
| `instanceof Box<String>` | Non-reifiable parameterization | `instanceof Box<?>` |
| Overload `set(T)` and `set(Object)` | Same erased signature | Change API/method names |
| Overload `accept(Box<String>)` / `accept(Box<Integer>)` | Same erased signature | Generic method/unique names |
| Raw `Box` | Loses compile-time safety | Parameterized Box |
| `get()` returning Object in a type-safe Box | Requires casts | Return T |
| Assigning null to an unboxing target | Runtime NullPointerException | Null policy |
| Holding a mutable List in a final T field | Aliasing | Ownership/copying |
| Accidentally declaring method `<T>` | Shadows class T | Use U or the class T properly |
| Overriding interface get() without public | Reduced access | Public method |
| Writing a thread-safe Box yourself with a plain field | Visibility/races | AtomicReference/locks |

## 77. Exercise 1 — Write `Box<T>` Yourself

Requirement: private field T, constructor accepting T, `get()` returning T, `set(T)` replacing value.

**Answer:**

~~~java
class Box<T> {
    private T value;

    Box(T initial) {
        this.value = initial;
    }

    T get() {
        return value;
    }

    void set(T value) {
        this.value = value;
    }
}
~~~

Use `Box<String>` and `Box<Integer>` to verify the compile-time relationship.

## 78. Exercise 2 — Predict the Result

~~~java
Box<String> names = new Box<>("Mai");
names.set("An");
String result = names.get();
~~~

**Answer:** `result` is `"An"`. The setter updates the field value, and the getter returns the new field value. Adding `names.set(123)` will cause a compile error.

## 79. Exercise 3 — Fix the Error

~~~java
// Box<int> count = new Box<>(7);
~~~

**Answer:** Use `Box<Integer> count = new Box<>(7);` because a type argument must be a reference type. Autoboxing handles the int literal.

## 80. Exercise 4 — Static Field T

~~~java
class Box<T> {
    // static T cache; // Invalid.
}
~~~

**Answer:** Do not use class-level T directly from a static context. If cache is per-instance, declare `private T cache;`. If a static method needs its own type parameter, declare `static <U> ...`.

## 81. Exercise 5 — Generic Method vs. Class Method

~~~java
class Box<T> {
    T echo(T x) { return x; }
    <U> U identity(U x) { return x; }
}
~~~

Given `Box<String> box`, what happens with `box.echo(10)` and `box.identity(10)`?

**Answer:** `box.echo(10)` is a compile error because T=String; `box.identity(10)` is valid with method U=Integer.

## 82. Exercise 6 — Type Erasure

Do `Box<String>` and `Box<Integer>` have different runtime classes?

**Answer:** No, if created from the same Box class declaration/class-loader context; `getClass()` usually returns the same Class object. Type arguments are still checked by the compiler.

## 83. Exercise 7 — `new T()`

A method wants to create a new object of type T inside Box. Why is `new T()` invalid?

**Answer:** T is an erased type parameter; Java does not know the corresponding constructor/runtime type. Accept `Supplier<? extends T>` or an appropriate factory/type token strategy.

## 84. Exercise 8 — Invariance

Why can `Box<String>` not be assigned to `Box<Object>` even though String extends Object?

**Answer:** If it were allowed, code using Box<Object> could set an Integer, causing Box<String> to hold the wrong type. Java generics invariance prevents that behavior.

## 85. Exercise 9 — Producer

A method only reads Number values from Box<Integer> or Box<Double>. Signature?

**Answer:**

~~~java
static double read(Box<? extends Number> box) {
    return box.get().doubleValue();
}
~~~

`? extends Number` opens the API for producer values. Do not set an Integer when the subtype type argument is unknown.

## 86. Exercise 10 — Consumer

A method wants to set an Integer into Box<Integer>, Box<Number>, or Box<Object>. Signature?

**Answer:**

~~~java
static void put(Box<? super Integer> box) {
    box.set(42);
}
~~~

`? super Integer` ensures the storage target types can accept an Integer.

## 87. Exercise 11 — Null Policy

A non-null Box<String> allows constructor "A" and setter "B", but rejects null. How should the setter be written?

**Answer:**

~~~java
void set(T next) {
    value = java.util.Objects.requireNonNull(next, "value");
}
~~~

Remember to validate in the constructor as well. Java generics by themselves do not exclude null.

## 88. Exercise 12 — Mutable Component

`Box<List<String>>` has a private final List reference, but the caller holds the mutable List and modifies it.

**Answer:** Box still sees the mutation if a shared reference is used. `final` prevents reassigning the field, not mutating the List object. Choose a clear ownership/defensive-copy policy.

## 89. Exercise 13 — `map` Changing Type

`Box<String> text = new Box<>("Java")`, and you want to create a `Box<Integer>` holding the length of the text.

**Suggested Answer:**

~~~java
Box<Integer> length = text.map(String::length);
~~~

With the method:

~~~java
<U> Box<U> map(java.util.function.Function<? super T, ? extends U> f) {
    return new Box<>(f.apply(value));
}
~~~

This is a snippet inside the Box<T> body. `U` is a method type parameter, distinct from class T.

## 90. Exercise 14 — Primitive Performance

A program processes millions of int values using `List<Box<Integer>>`. Should it be changed just because “generics are slow”?

**Answer:** Do not decide based on slogans. Profile it. Boxing, allocations, and locality can have costs; if the workload is truly performance-critical, consider primitive arrays/specialized structures/algorithms.

## 91. Exercise 15 — Raw Type

A `Box<String>` is assigned to a raw Box and then raw.set(42) is called. What can happen when getting the String afterward?

**Answer:** The compiler warns of an unchecked call at the raw boundary; retrieving the String can throw a ClassCastException at runtime. Avoid raw types to preserve type safety.

## 92. Exercise 16 — Generic Interface

`interface Holder<T> { T get(); void set(T x); }`. Must `Box<T> implements Holder<T>` implement the methods as public?

**Answer:** Yes. Interface abstract methods are public, and the implementation cannot reduce access. Use `@Override public T get()` and `@Override public void set(T x)`.

## 93. Safe Box<T> Design Process

**Step 1 — Define the purpose.** Mutable holder, immutable value, optional state, or domain wrapper?

**Step 2 — Declare the type parameter.** `class Box<T>` and apply T consistently to fields/constructor/getter/setter.

**Step 3 — Set visibility.** Private field; intentional public/package API. Avoid a public mutable field.

**Step 4 — Choose a null policy.** Allow null or reject it? Enforce it in both the constructor and setter.

**Step 5 — Choose a mutation policy.** Should a setter mutate the field or should `withValue` return a new Box?

**Step 6 — Consider a generics factory.** Static `<U> Box<U> of(U)`, without using class T inside the static method.

**Step 7 — Add bounds only when needed.** If you need `doubleValue()`, use `T extends Number`; do not force every Box to extend Number.

**Step 8 — Choose the API when accepting family types.** `Box<?>`, `? extends`, `? super`, or a method `<T>` with the right relationship.

**Step 9 — Avoid raw types and unchecked casts.** Preserve compiler type checks from caller to storage.

**Step 10 — Define ownership.** T may be a mutable object; does Box copy or share it? Document this clearly.

**Step 11 — Define the equality/hash policy.** A mutable holder usually does not need value equality; an immutable holder may need it.

**Step 12 — Review concurrency.** If updates are shared, use synchronization or AtomicReference<T> according to the contract.

**Step 13 — Test compile-time errors and runtime behavior.** Getter/Setter, replace, null, map, and erasure/rawtypes restrictions.

## 94. End-of-Lesson Checklist

- [ ] I write `class Box<T>` correctly.
- [ ] I know T is a type parameter and String is a type argument.
- [ ] I declare the field `private T value`.
- [ ] I write the constructor `Box(T value)`.
- [ ] I write the getter `T get()`.
- [ ] I write the setter `void set(T next)`.
- [ ] I can write `T replace(T next)`.
- [ ] I know methods that do not use T are also valid.
- [ ] I know class type parameter scope does not apply directly to static members.
- [ ] I can write `static <U> Box<U> of(U)`.
- [ ] I distinguish between class T and method U.
- [ ] I do not try to write `new T()` or `T.class`.
- [ ] I understand `Box<String>` and `Box<Integer>` share the same runtime Box class after erasure.
- [ ] I avoid raw Box and unchecked operations.
- [ ] I know `Box<int>` is invalid and `Box<Integer>` is valid.
- [ ] I understand boxing/unboxing and the null runtime hazard.
- [ ] I understand diamond `new Box<>(value)`.
- [ ] I know generic types are invariant.
- [ ] I use `Box<?>` when only general reading is needed.
- [ ] I use `? extends Number` when reading Number-family values.
- [ ] I use `? super Integer` when writing Integer values.
- [ ] I know the type bound `T extends Number` allows Number methods.
- [ ] I do not assume a generic T supports the + operator.
- [ ] I know generic type safety does not guarantee domain validity.
- [ ] I include null validation if the contract requires it.
- [ ] I do not confuse a final T reference with a deeply immutable value.
- [ ] I apply defensive-copying appropriately for the actual T type.
- [ ] I have a clear policy for Box's equals/hashCode.
- [ ] I know the generic record `record Box<T>(T value)` is an immutable-by-field alternative.
- [ ] I know a generic class can implement the `Holder<T>` interface.
- [ ] I understand a subclass can preserve T or fix String.
- [ ] I do not assume thread safety from generics.
- [ ] I can compare Box<T> with AtomicReference<T>/Optional<T>.
- [ ] I recognize the compile-time errors in this lesson and can predict the stdout of the programs.

**Conclusion:** `class Box<T>` is the most foundational example of a Java generic class. **A type parameter T maintains a consistent relationship across the stored field, constructor input, getter return, and setter input**, helping the compiler catch type mismatches before the program runs. Keep `T` in its proper instance context, use a static generic method `<U>` when a factory is needed, avoid raw types/unchecked casts, and understand that type erasure does not remove the benefits of compile-time type safety. Finally, choose appropriate null/mutation/ownership/equality/concurrency policies: **generics check data types, and do not automatically enforce the quality, immutability, or thread safety of the data inside**.
