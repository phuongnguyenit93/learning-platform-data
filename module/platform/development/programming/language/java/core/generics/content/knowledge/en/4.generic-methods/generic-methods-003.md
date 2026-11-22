# Distinguishing Methods with Their Own Type Parameters from Methods Using the Class's `T`

Java allows declaring **type parameters on a class** and **separate type parameters on a method**. Both can appear in the same class, yet they have different scopes and meanings. In `class Box<T>`, the method `T get()` **uses the class's `T`** and thus does not declare a type parameter of its own. Meanwhile, `<U> U echo(U input)` **is a generic method**, declaring `U` itself and able to infer a new type `U` for each call.

Lesson objectives: read both signature forms accurately, choose where to declare type parameters, understand how types are determined at use sites, use `static` methods validly, combine the class's `T` with the method's `R`, and avoid type-parameter name shadowing bugs. Examples target Java 17 and later.

## 1. The Difference Lies in Where It Is Declared

```java
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

    <U> U echo(U input) {
        return input;
    }
}
```

`<T>` right after `Box` **declares a type parameter belonging to the class**. The field `T value`, constructor `Box(T)`, `get()`, and `set(T)` all use that `T`. `get()` and `set()` are **not generic methods in the sense of declaring their own type parameter**: there is no separate `<...>` before the return type.

Conversely, `<U>` before the return type `U` in `<U> U echo(U input)` is the type parameter declaration **of the method itself**. `U` is independent of `T`: when a `Box<String>` calls `echo(42)`, the compiler can infer `U = Integer` without changing `T = String`.

```java
Box<String> text = new Box<>("Java");
String a = text.get();           // Class's T = String.
text.set("Generics");            // Must pass String.
// text.set(42);                 // Compile error: set requires String.

Integer b = text.echo(42);       // U for this call = Integer.
Boolean c = text.echo(true);     // U for another call = Boolean.
```

These short snippets are illustrations within the same `Box<T>` declaration context; the complete `Main.java` example is in section 5.

| Criterion | Using the Class's `T` | Declaring the Method's Own Type Parameter |
|---|---|---|
| Declaration site | `class Box<T>` | `<U>` before the return type |
| Examples | `T get()`, `void set(T)` | `<U> U echo(U input)` |
| Type scope | Shared across instance members of `Box<T>` | Only within the signature and body of the method declaring it |
| How is the type chosen? | By `Box<String>`, `Box<Integer>`, etc. | Typically inferred at **each call site** |
| Can it be static? | Cannot reference the class's `T` directly from a static member | Yes, if the static method declares its own `<U>` |
| Relation to object state | Can read/write a `T` field | Relates to state only when the signature/body explicitly expresses a relationship |

**Quick recognition criterion:** look at the declaration right before the return type. The mere appearance of `T` in a return type or parameter is **not enough** to conclude that the method is generic on its own.

## 2. Methods Using the Class's `T`

```java
final class Holder<T> {
    private T current;

    Holder(T initial) {
        this.current = initial;
    }

    T read() {
        return current;
    }

    void replace(T next) {
        current = next;
    }
}
```

At use sites:

```java
Holder<String> name = new Holder<>("An");
String old = name.read();
name.replace("Bình");
// name.replace(18); // Invalid: the reference's type T is String.

Holder<Integer> age = new Holder<>(18);
Integer value = age.read();
age.replace(21);
```

The same `Holder<T>` definition is reused for both strings and numbers, yet the caller is checked against **each reference's type argument**. The type parameter `T` is tied to `Holder<T>`'s contract: `replace` must accept the exact type that `read` returns.

The multi-type-parameter case is similar:

```java
class Pair<K, V> {
    private final K key;
    private final V value;

    Pair(K key, V value) {
        this.key = key;
        this.value = value;
    }

    K key() {
        return key;
    }

    V value() {
        return value;
    }
}
```

Both `key()` and `value()` use the type parameters declared on `Pair<K,V>` and **do not declare generic type parameters of their own**. For `Pair<String,Integer>`, the return types are `String` and `Integer`, respectively.

An ordinary constructor of a generic class can take the class's `T` without **being a separate generic constructor**. A constructor is a generic constructor only if it declares its own type parameter list before the constructor name.

## 3. A Method Can Be Generic Even If Its Class Is Not

A regular class does not need to declare a type parameter in order to contain a generic method:

```java
class ArrayTools {
    static <E> E first(java.util.List<E> xs) {
        return xs.get(0);
    }
}
```

Here `E` exists only in `first`. When passing `List<String>`, the result has static type `String`; when passing `List<Integer>`, the result can be `Integer`. This lesson uses this example to **contrast with `T get()` of a generic class**, not to require `ArrayTools` to put `<E>` on the class name.

## 4. Combining the Class's `T` with the Method's Own `<R>`

Many APIs need to keep the data type stored in the object while returning a different type after transformation:

```java
import java.util.function.Function;

final class TransformBox<T> {
    private final T value;

    TransformBox(T value) {
        this.value = value;
    }

    <R> R transform(Function<? super T, ? extends R> converter) {
        return converter.apply(value);
    }
}
```

`T` is declared on the **class**: the converter's input must be able to handle the stored `T` object. `<R>` is declared on the **method**: the result can vary from call to call.

```java
TransformBox<String> box = new TransformBox<>("Java");
String upper = box.transform(String::toUpperCase);
Integer length = box.transform(String::length);
```

`T` is always `String` across both calls, while `R` is `String` and `Integer`, respectively. `String::length` returns `int`, and boxing makes the result compatible with `Integer`.

In the signature `Function<? super T, ? extends R>`:

- `? super T` lets the converter accept `T` or an appropriate supertype, meaning it can **consume** the stored value.
- `? extends R` lets the converter return `R` or a subtype of `R`, meaning it can **produce** a compatible result.
- `R transform(...)` ties the output to the method-level type parameter; it does not alter the object's type argument `T`.

Another example combines `T` and `U` in the return type:

```java
record Tuple<A, B>(A first, B second) {}

class TupleMaker<T> {
    private final T saved;

    TupleMaker(T saved) {
        this.saved = saved;
    }

    <U> Tuple<T, U> pairWith(U extra) {
        return new Tuple<>(saved, extra);
    }
}
```

`TupleMaker<String>.pairWith(7)` infers `U = Integer`, returning `Tuple<String,Integer>`. This is a useful type relationship: the first part has the object's type `T`, and the second part has the call's own type. This snippet is illustrative and not a standalone runnable program.

## 5. Complete Example: One Class with Both Kinds of Methods

Create a file named exactly **`Main.java`** with all the code below. The program illustrates methods using the class's `T`, a method `<R>` using both `T` and `R`, a method `<U>` independent of `T`, and a static generic method `<E>`.

```java
import java.util.List;
import java.util.function.Function;

public class Main {
    record Pair<L, R>(L left, R right) {}

    static final class Box<T> {
        private T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        void set(T replacement) {
            this.value = replacement;
        }

        <R> R map(Function<? super T, ? extends R> mapper) {
            return mapper.apply(value);
        }

        <U> Pair<T, U> pairWith(U extra) {
            return new Pair<>(value, extra);
        }

        <U> U echo(U arg) {
            return arg;
        }

        static <E> E first(List<E> items) {
            if (items.isEmpty()) {
                throw new IllegalArgumentException("empty");
            }
            return items.get(0);
        }
    }

    public static void main(String[] args) {
        Box<String> text = new Box<>("Java");

        System.out.println("initial: " + text.get());
        System.out.println("upper: " + text.map(String::toUpperCase));
        System.out.println("length: " + text.map(String::length));

        Pair<String, Integer> pair = text.pairWith(7);
        System.out.println("pair: " + pair.left() + "/" + pair.right());

        System.out.println("echo: " + text.<Boolean>echo(true));
        System.out.println("first: " + Box.first(List.of(10, 20)));

        text.set("Generics");
        System.out.println("updated: " + text.get());

        Box<Integer> number = new Box<>(25);
        System.out.println("formatted: " + number.map(n -> "N=" + n));

        // text.set(42); // Does not compile: text's T is String.
    }
}
```

Compile and run on **JDK 17 or later**:

```bash
javac -encoding UTF-8 Main.java
java Main
```

Stdout:

```text
initial: Java
upper: JAVA
length: 4
pair: Java/7
echo: true
first: 10
updated: Generics
formatted: N=25
```

### Reading Each Signature in the Example

| Method | Source of Type Parameter | Meaning for `Box<String> text` |
|---|---|---|
| `T get()` | `T` belongs to the class | Returns `String` |
| `void set(T)` | `T` belongs to the class | Accepts `String`; rejects `Integer` |
| `<R> R map(Function<? super T, ? extends R>)` | `T` belongs to the class, `R` belongs to the method | Converter input compatible with `String`, output follows `R` |
| `<U> Pair<T,U> pairWith(U)` | `T` belongs to the class, `U` belongs to the method | Returns a pair of `String` and the extra type |
| `<U> U echo(U)` | Only `U` belongs to the method | Allows `Boolean`, `Integer`, etc. |
| `static <E> E first(List<E>)` | Only `E` belongs to the static method | Independent of any `Box`'s type argument |

`text.<Boolean>echo(true)` illustrates **specifying a type argument for an instance generic method**, unlike `new Box<String>(...)` which chooses the class's type argument. The `<Boolean>` after the dot does not change `text` into `Box<Boolean>`.

The line `text.set("Generics")` updates the field through a method using the class's `T`. Conversely, `echo` simply returns whatever argument it receives: `text.echo(42)` does not cause `text` to change type or become `Box<Integer>`.

## 6. Static Methods and the Scope of `T`

A `static` method belongs to the class, so it cannot directly access the type variable `T` of `class Box<T>` as if it were a type parameter available to a static context:

```java
class Box<T> {
    // static T bad(T input) { return input; } // Invalid.
    static <U> U ok(U input) { return input; } // Valid.
}
```

`U` is declared by the static method itself; it does not depend on the type argument of a `Box<String>` or `Box<Integer>` instance.

## 7. Name Shadowing: `<T>` on a Method Is Not the Class's `T`

Java **allows** a method to declare a type parameter named `T` directly inside `class Container<T>`. In that case, the method's `T` **shadows** the class's `T` within the method's scope:

```java
class ShadowDemo<T> {
    private T stored;

    ShadowDemo(T stored) {
        this.stored = stored;
    }

    <T> T echo(T value) {
        return value;
    }
}
```

Suppose:

```java
ShadowDemo<String> demo = new ShadowDemo<>("Java");
Integer n = demo.echo(42); // Valid: echo's T = Integer.
```

Here, the type of `stored` is `String` while `T` inside `echo` is `Integer`. The two type parameters merely happen to **share the same name**; they are not the same.

Potential harm: if a reader assumes `echo(T)` takes the type of the `stored` field, they may write incorrect callers or an implementation needing unsafe casts. You should name the method-level parameter differently, such as `<U> U echo(U value)`. If you want the method to accept the exact type of the field, **omit `<T>` from the method** and simply write `T echo(T value)`.

Do not try to return `stored` from a method declared with `<T> T echo(...)` without an appropriate constraint: the field's `T` and the method's `T` are two distinct type variables.

## 8. Type Inference Happens at Two Different Points

**Class-level inference:** `Box<String> x = new Box<>("Java")` uses the diamond `<>` to infer the **class's** type argument from context. When calling `x.get()`, the class's `T` already means `String` in the type of `x`.

**Method-level inference:** `x.echo(10)` infers `echo`'s own type parameter at **that call site**, which can become `Integer` even though `x` is a `Box<String>`. If the caller writes `x.<Long>echo(10L)`, that is an explicit type argument for the method, not changing the class's type argument.

The type inference mechanism is part of the compiler and **does not generate a specialized runtime class** for each usage.

## 9. Class Bounds and Method Bounds Are Also Independent

If every `NumberBox<T>` object must hold a number:

```java
class NumberBox<T extends Number> {
    private final T value;

    NumberBox(T value) {
        this.value = value;
    }

    double asDouble() {
        return value.doubleValue();
    }
}
```

The bound `T extends Number` is declared on the **class**. `asDouble()` uses the `doubleValue()` capability guaranteed by the bound, yet it is still **not a generic method declaring a new parameter**.

If a standalone method only needs an argument with `length()`:

```java
class TextTools {
    static <S extends CharSequence> int length(S value) {
        return value.length();
    }
}
```

The bound `<S extends CharSequence>` belongs **to the method**, without requiring `TextTools` to be generic. Both kinds of bounds can also be combined:

```java
class NumberBox<T extends Number> {
    private final T saved;

    NumberBox(T saved) {
        this.saved = saved;
    }

    <U extends CharSequence> String join(U suffix) {
        return saved + ":" + suffix;
    }
}
```

Here `T` is fixed per `NumberBox<T>`, while `U` is chosen at the `join` call site, provided it satisfies `CharSequence`.

## 10. Common Mistakes and How to Fix Them

**Mistake 1 — Mistaking a method that uses `T` for a generic method:** `T get()` in `Box<T>` uses the type parameter from the class; only when the method itself writes `<U>` or `<R>` before the return type does it declare its own type parameter.

**Mistake 2 — Writing `static T` with `T` belonging only to the class:** a static method has no instance `T`. Make it an instance method if it uses `T` state, or declare `static <U> U...` if the algorithm is independent.

**Mistake 3 — Accidentally shadowing `T`:** writing `<T> T echo(T)` inside `class Box<T>` creates a **separate** type parameter; prefer `<U>` for clarity or remove `<T>` if you want to use the class's type parameter.

**Mistake 4 — A method lacking a mechanism to guarantee the output type:** `<R> R read()` that merely casts from `Object` without verification can produce unchecked warnings and `ClassCastException`. Generics do not convert actual data into the type the caller expects.

**Mistake 5 — Two overloads with the same erasure:** in `class Clash<T>` with unbounded `T`, `void use(T value)` and `<U> void use(U value)` both erase to `use(Object)`; they **cannot coexist** with those signatures. Choose a different contract or give the methods meaningful distinct names.

**Mistake 6 — Using `U` out of scope:** a method declaring `<U>` does not allow fields or other methods to use `U`; if multiple members need to share the same type relationship, declare the parameter on the class or interface.

**Mistake 7 — Thinking a method's type argument changes the object's type:** `text.echo(42)` does not change `Box<String>` into `Box<Integer>`. The field `T` and method parameter `U` remain independent unless the signature explicitly binds them.

**Mistake 8 — Confusing generics with validation:** `Box<String>` can still hold `null` if the code allows it; `first(List<E>)` still needs an emptiness check. Type checking does not replace business data constraints.

**Mistake 9 — Assuming each type argument creates a separate runtime class:** Java uses *type erasure* for most generics. `Box<String>` and `Box<Integer>` do not create two new runtime classes; nor is a method `<U>` duplicated into separate bytecode per `U`.

## 11. Self-Check

**Question 1:** Does `class Box<T> { T get() { ... } }` have a generic method `get`?

**Answer:** No. `get()` only uses the class's `T`. It does not declare any type parameter list of its own.

**Question 2:** In `Box<String> text`, why is `text.set(10)` wrong while `Integer x = text.echo(10)` is valid?

**Answer:** `set(T)` requires `String` according to the class-level `T`; `echo` declares its own `<U>` and infers `U = Integer`. Calling `echo` does not change the object's type.

**Question 3:** How many type parameters does `<R> R map(Function<? super T, ? extends R>)` use, and where are they?

**Answer:** There is `T` from the class and `R` from the method. Correspondingly, the converter's input relates to the stored data type, and the output is determined per call.

**Question 4:** Can `static <U> U identity(U value)` be declared in a non-generic class?

**Answer:** Yes. The type parameter `U` is declared by the method itself; the class does not need `<U>`.

**Question 5:** Does `class ShadowDemo<T> { <T> T echo(T x) { return x; } }` use the class's `T` inside `echo`?

**Answer:** No. The method's `T` shadows the class's `T`. Rename the method's type parameter if you want to keep the relationship clear.

**Question 6:** In `Box<String> text`, which call is valid?

```java
// A: text.set(9);
// B: text.<Integer>echo(9);
// C: text.<Integer>echo("9");
```

**Answer:** B is valid. A is wrong because `set` requires `String`; C is wrong because `U = Integer` was specified yet a `String` was passed.

## Conclusion

**A method using the class's `T`** obtains its type relationship from a declaration such as `class Box<T>`; examples include `T get()` and `void set(T)`. **A generic method with its own type parameter** directly declares `<U>` or `<R>` before the return type; that type can be inferred per call, even when the class is not generic. When stored data needs to be transformed, a method can combine **the class's `T`** and **the method's `R`** in the same signature. Placing type parameters in the right scope keeps type contracts clear and avoids static errors, shadowing, and unsafe casts.