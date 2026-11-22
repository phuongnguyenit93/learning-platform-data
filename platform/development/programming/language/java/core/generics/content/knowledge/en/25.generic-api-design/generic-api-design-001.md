# Choosing Class-Level or Method-Level Type Parameters in Java Generics

## Objectives

In Java, both of the following signatures use generics:

```java
class Box<T> {
    private T value;
    Box(T value) { this.value = value; }
    T get() { return value; }
}

static <T> T identity(T value) {
    return value;
}
```

However, the meanings of the two type variables `T` are different. In `Box<T>`, `T` is part of the **object's type contract**: the constructor, field, and instance methods can together maintain an invariant. In `identity`, `T` only needs to link the input to the result of **a single call**. Subsequent calls may infer a completely different `T`.

The most useful principle is to **place a type parameter in the smallest scope that still covers all type relationships the API must guarantee**. If an object holds that type across multiple operations, use a generic class/interface. If the type belongs only to an algorithm, use a generic method. If a name `T` is not needed to relate input to output, consider a wildcard.

After this lesson, you will be able to:

- Distinguish type parameters of classes, interfaces, methods, and constructors.
- Choose the right scope for `Box<T>`, `Repository<E>` state, and utility methods.
- Combine class-level `E` with method-level `K`/`R`/`U`.
- Write a static generic factory and avoid referencing the class's `T` in a static context.
- Identify type parameter shadowing, unsafe pseudo-generic methods, raw types, and erasure name clashes.
- Use wildcards, PECS, target typing, and type inference to optimize public APIs.
- Run a valid Java 17 program and verify examples that are intentionally rejected by the compiler.

## 1. Does T belong to the object or to the call?

| Aspect | Class-level type parameter | Method-level type parameter |
| --- | --- | --- |
| Syntax | `class Box<T>`, `interface Store<E>` | `static <T> T identity(T)` |
| Scope | Eligible members of the class, especially instance fields/methods | Only the method that declares `T` |
| Type determined at | Use of the class/interface such as `Box<String>` | Each method call |
| Commonly expressed relationship | `set(T)` and `get():T` must stay consistent | `convert(T):R` of a single operation |
| Examples | `Repository<User>`, `Cache<K,V>` | `<T,R> map(...)`, `<T> copy(...)` |
| Can use class T in static? | No | A static method declares its own new `<T>` |
| Need to store a T value? | Not required, though usually tied to a long-lived contract | Does not create generic state for the class |

Class-level `T` does not mean the JVM creates a separate class for each `T`. After *type erasure*, `Box<String>` and `Box<Integer>` usually share the same runtime class `Box`. It is the compiler that enforces the corresponding type relationships in source code.

The first question during a review: **Does `T` represent something this object holds or consistently provides across multiple operations, or is it just a one-time variable in a single operation?**

## 2. Class-level T: preserving an invariant across multiple methods

A box can be declared as:

```java
final class Box<T> {
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
```

Caller:

```java
Box<String> title = new Box<>("Java");
String current = title.get();
title.set("Generics");

// title.set(42); // Compile error.
```

The same `T` binds the field, constructor, getter, and setter. When a reference has type `Box<String>`, `get()` returns `String` and `set` requires `String`. That is the appropriate reason to declare `T` at the class level.

Another instance can have a different type:

```java
Box<Integer> counter = new Box<>(7);
counter.set(9);
```

`T` is not fixed for every `Box` across the entire application; each parameterization of the class has its own compile-time contract.

### Real-world cases where a class-level type parameter should be used

- `Repository<E>` stores multiple `E` elements, accepts `E` in `add`, and returns `E` in `get`.
- `Cache<K,V>` always uses `K` as the key and `V` as the value.
- `Queue<T>` supports `offer(T)` and `poll():T`.
- `Result<T>` describes a typed result.
- `ConfiguredMapper<T,R>` stores a `T→R` callback to be applied repeatedly.
- `Comparable<T>` expresses the type of object that an implementation knows how to compare.

A class without a field of type `T` is not barred from being generic: an interface can declare a **contract linking multiple methods** even if it owns no state. The primary criterion is the scope over which a consistent `T` must be maintained.

## 3. Method-level T: an algorithm used per call

Example:

```java
static <T> T identity(T value) {
    return value;
}
```

Calls:

```java
String name = identity("An");
Integer count = identity(3);
```

The compiler infers `T` independently for each call. The method does not need to know or retain the type `T` between calls.

General syntax:

```text
[modifiers] <TypeParameters> ReturnType methodName(parameters)
```

`<T>` is placed **before the return type**. Do not write `static T <T> identity(...)`.

### Multiple type parameters in a single method

```java
static <T, R> R convert(
        T input, Function<? super T, ? extends R> mapper) {
    return mapper.apply(input);
}
```

`T` relates to the input type; `R` relates to the output type. One call might be `String→Integer`, another `Integer→String`. If there is no configuration or state holding the `T`/`R` relationship long-term, placing both variables on the method is natural.

Java infers generic method type arguments from arguments, target types, lambdas/method references, and bounds. When explicitness is needed:

```java
List<Integer> lengths =
        Operations.<String, Integer>mapAll(
                List.of("A", "Java"), String::length);
```

However, the shorter call is usually enough:

```java
List<Integer> lengths =
        Operations.mapAll(List.of("A", "Java"), String::length);
```

`Operations` is the utility class in the program in section 8. Explicit type arguments should be used when needed to help inference or clarify intent; they should not be written everywhere if they only repeat what the compiler already knows.

### A generic method does not have to be static

Both are valid:

```java
class Worker {
    <T> T apply(T input) {
        return input;
    }

    static <T> T echo(T input) {
        return input;
    }
}
```

Method-level classification refers to where the type variable is declared, not the `static` keyword. `static` adds its own restriction regarding class-level type variables in section 6.

## 4. Class-level Repository and method-level grouping

A common design:

```java
final class Repository<E> {
    private final List<E> items = new ArrayList<>();

    void add(E element) {
        items.add(element);
    }

    List<E> snapshot() {
        return List.copyOf(items);
    }

    <K> Map<K, List<E>> groupBy(
            Function<? super E, ? extends K> classifier) {
        return items.stream().collect(Collectors.groupingBy(
                classifier,
                LinkedHashMap::new,
                Collectors.toList()));
    }
}
```

This snippet requires imports for `List`, `ArrayList`, `Map`, `LinkedHashMap`, `Function`, and `Collectors`. The complete example is in section 8.

Suppose:

```java
Repository<String> names = new Repository<>();
names.add("An");
names.add("Binh");
names.add("Anh");

Map<Integer, List<String>> byLength =
        names.groupBy(String::length);

Map<Character, List<String>> byFirstLetter =
        names.groupBy(text -> text.charAt(0));
```

`E=String` is preserved throughout the repository's state. However, `K` is inferred **per grouping call**, which can be `Integer` or `Character`. You should not add `K` to `Repository<E,K>` if the repository does not have a fixed key type for the entire lifetime of the object.

### Why does the callback have wildcards?

`Function<? super E, ? extends K>` describes a mapper:

- It **consumes** `E`, so it can accept a supertype of `E` (`super`).
- It **produces** a `K`-compatible result, so it can return a subtype of `K` (`extends`).

This is the **PECS — Producer Extends, Consumer Super** principle. The method's type variable `K` links the mapper's result type to the key type of `Map<K,List<E>>`.

### Snapshot and mutability are a separate contract

`List.copyOf(items)` creates an unmodifiable list structurally, rejects `null` elements, and does not deep-copy mutable `E` objects. Those properties do not change the decision of whether `E` belongs at the class level or `K` at the method level.

## 5. A generic class can still contain its own generic methods

A `Box` with a fixed value type `T` can support mapping to any type `R`:

```java
final class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    <R> R map(Function<? super T, ? extends R> mapper) {
        return mapper.apply(value);
    }
}
```

Calls:

```java
Box<String> title = new Box<>("Java");
Integer length = title.map(String::length);
String upper = title.map(String::toUpperCase);
```

In both calls, `Box` still holds `String`. However, the method's `R` is `Integer` in the first call and `String` in the next. If `R` were placed on the class (`Box<T,R>`), a caller might have to determine `R` at the time of creating `Box` without even knowing what it will map to.

Conversely, if a class is created to **hold the `T→R` mapper itself long-term**:

```java
final class ConfiguredMapper<T, R> {
    private final Function<? super T, ? extends R> mapper;

    ConfiguredMapper(Function<? super T, ? extends R> mapper) {
        this.mapper = mapper;
    }

    R apply(T value) {
        return mapper.apply(value);
    }
}
```

then class-level `T`/`R` is completely reasonable. There is no rule that "every `map` function puts `R` on the method"; scope is determined by the lifetime of the contract.

## 6. Static members cannot use the class's T as a type variable

**File BadStaticScope.java, intentionally does not compile:**

```java
class BadStaticScope<T> {
    static T cache;
    static T create() { return null; }
}
```

`javac --release 17` rejects both uses of `T`:

```text
non-static type variable T cannot be referenced from a static context
```

A `static` member belongs to the class, not to a specific instance of `BadStaticScope<String>` or `BadStaticScope<Integer>`. An instance's `T` cannot automatically become a type for a `static` field.

### Proper static generic factory

```java
final class Box<T> {
    private final T value;

    private Box(T value) {
        this.value = value;
    }

    static <X> Box<X> of(X value) {
        return new Box<>(value);
    }
}
```

Calls:

```java
Box<String> text = Box.of("hello");
Box<Integer> number = Box.of(10);
```

`X` is **the static method's own type variable**, inferred at each call. The static factory does not reference the `T` of an existing `Box`.

Java allows using the same name `T` for the class's type parameter and the static method's type parameter, but they are **two different declarations**. Choosing the name `X` in the example makes the scope clear.

**There is no generic field with syntax like `static <T> T cache`**: methods/constructors can declare their own type parameters, whereas fields have no such mechanism.

## 7. Type parameter shadowing

**File BadShadowing.java, intentionally does not compile:**

```java
class BadShadowing<T> {
    private T value;

    <T> void replace(T next) {
        value = next;
    }
}
```

The compiler reports:

```text
incompatible types: T#1 cannot be converted to T#2
```

`T` in `<T> void replace(...)` is a new type variable and **shadows** the class's `T`. Both `T`s are written identically, yet they are two distinct declarations.

If the goal is to update `Box`'s field of type `T`, fix it to:

```java
class GoodBox<T> {
    private T value;

    void replace(T next) {
        value = next;
    }
}
```

If the method genuinely needs another type, use the name `U`:

```java
<U> Pair<T, U> pairWith(U extra) {
    return new Pair<>(value, extra);
}
```

This is a method of `Box<T>` in the complete program in section 8, which has the field `value` and the record `Pair<A,B>`.

`T`/`E`/`K`/`V`/`R`/`U`/`X` are only naming conventions. The compiler cares about **declaration site and bounds**, and does not assume that two `T` characters in different scopes must be equivalent.

## 8. Complete verified Java 17 program

The program combines `Box<T>`, `Repository<E>`, utility methods with their own `T`/`R`, a generic constructor with its own `U`, and a static generic factory.

**File GenericScopeDemo.java:**

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.BinaryOperator;
import java.util.function.Function;
import java.util.stream.Collectors;

public class GenericScopeDemo {
    record Pair<A, B>(A first, B second) {}

    static final class Box<T> {
        private T value;
        Box(T value) { this.value = value; }
        T get() { return value; }
        void set(T next) { value = next; }

        <R> R map(Function<? super T, ? extends R> mapper) {
            return mapper.apply(value);
        }

        <U> Pair<T, U> pairWith(U extra) {
            return new Pair<>(value, extra);
        }

        static <X> Box<X> of(X value) {
            return new Box<>(value);
        }
    }

    static final class Repository<E> {
        private final List<E> items = new ArrayList<>();
        void add(E element) { items.add(element); }
        List<E> snapshot() { return List.copyOf(items); }

        <K> Map<K, List<E>> groupBy(
                Function<? super E, ? extends K> classifier) {
            return items.stream().collect(Collectors.groupingBy(
                    classifier, LinkedHashMap::new, Collectors.toList()));
        }
    }

    static final class Operations {
        private Operations() {}

        static <T> T choose(T a, T b, BinaryOperator<T> chooser) {
            return chooser.apply(a, b);
        }

        static <T, R> List<R> mapAll(
                List<? extends T> source,
                Function<? super T, ? extends R> mapper) {
            List<R> result = new ArrayList<>();
            for (T item : source) {
                result.add(mapper.apply(item));
            }
            return result;
        }

        static <T> void append(
                List<? extends T> source, List<? super T> destination) {
            destination.addAll(source);
        }

        static void printSize(List<?> items) {
            System.out.println("size=" + items.size());
        }
    }

    static final class Envelope<T> {
        final T payload;
        final String audit;

        <U> Envelope(T payload, U auditData) {
            this.payload = payload;
            this.audit = String.valueOf(auditData);
        }
    }

    public static void main(String[] args) {
        Box<String> title = Box.of("Java");
        System.out.println("box=" + title.get());
        title.set("Generics");
        System.out.println("updated=" + title.get());
        System.out.println("mapped=" + title.map(String::length));
        System.out.println("pair=" + title.pairWith(2026));

        Box<Integer> count = Box.of(7);
        System.out.println("otherBox=" + count.get());

        Repository<String> names = new Repository<>();
        names.add("An");
        names.add("Binh");
        names.add("Anh");
        System.out.println("repo=" + names.snapshot());
        System.out.println("groups=" + names.groupBy(String::length));

        int chosen = Operations.choose(4, 9, Integer::max);
        System.out.println("chosen=" + chosen);
        System.out.println("lengths="
                + Operations.mapAll(List.of("A", "Java"), String::length));

        List<Number> destination = new ArrayList<>(List.of(1.5));
        Operations.append(List.of(2, 3), destination);
        System.out.println("append=" + destination);
        Operations.printSize(names.snapshot());

        Envelope<String> e = new Envelope<>("payload", 1001L);
        System.out.println("envelope=" + e.payload + "/" + e.audit);
        System.out.println("classGenericAndMethodGeneric="
                + title.<Integer>map(String::length));
    }
}
```

Run:

```bash
javac --release 17 -Xlint:all GenericScopeDemo.java
java GenericScopeDemo
```

**Verified exact stdout:**

```text
box=Java
updated=Generics
mapped=8
pair=Pair[first=Generics, second=2026]
otherBox=7
repo=[An, Binh, Anh]
groups={2=[An], 4=[Binh], 3=[Anh]}
chosen=9
lengths=[1, 4]
append=[1.5, 2, 3]
size=3
envelope=payload/1001
classGenericAndMethodGeneric=8
```

`javac --release 17 -Xlint:all` emits no warnings for the test program. `LinkedHashMap` in `groupBy` ensures keys are printed in the order encountered in the data: 2, 4, 3.

### Box's T and map's R are two scopes

`title` is always `Box<String>`: `set/get` use `String`. `map(String::length)` returns `Integer`. Another call `map(String::toUpperCase)` returns `String`. `R` is inferred independently; `Box` does not turn into `Box<String,Integer>`.

### pairWith's U does not change Box's T

`pairWith(2026)` returns `Pair<String,Integer>`. `String` is tied to `Box`; `Integer` is tied to the method. The record prints `Pair[first=Generics, second=2026]`.

### Repository's E and groupBy's K

`E=String` applies to the repository and its snapshot. `K=Integer` applies only to a single call grouping by string length.

### Utility class without generic state

`Operations.choose`, `mapAll`, and `append` use different `T`/`R` variables in each method. There is no need for `Operations<T,R>`, and no object needs to be created to use these algorithms.

## 9. Generic constructors also have their own scope

`Envelope<T>` in section 8 has the constructor:

```java
<U> Envelope(T payload, U auditData) {
    this.payload = payload;
    this.audit = String.valueOf(auditData);
}
```

`T` belongs to the class and is kept in the `payload` field. `U` belongs only to a single initialization; the constructor receives `auditData` of type `U` and converts it to `String`. The caller writes:

```java
Envelope<String> e = new Envelope<>("payload", 1001L);
```

`T` is determined as `String`, and `U` is compatible with `Long`. The object is still `Envelope<String>`, not `Envelope<String,Long>`.

The diamond `<>` in `new Envelope<>(...)` helps infer **class type arguments**. The constructor type parameter `U` is inferred from the constructor signature, independently of `T`.

A generic constructor is useful if a temporary input has a type relationship that needs to be expressed at initialization time. If `U` appears only once and does not need to relate to any other position at all, an `Object` input can sometimes suffice; there is no need to use generics just to add more angle brackets to the code.

## 10. Bounded type parameters at both class and method levels

Class-level bound:

```java
class NumericBox<N extends Number> {
    private final N value;

    NumericBox(N value) {
        this.value = value;
    }

    double asDouble() {
        return value.doubleValue();
    }
}
```

If the entire instance always holds a `Number` subtype, a class-level bound makes sense.

Method-level bound:

```java
static <N extends Number> double square(N value) {
    double x = value.doubleValue();
    return x * x;
}
```

The method only processes a single `Number` value and holds no state of type `N`.

Multiple bounds:

```java
static <T extends Number & Comparable<T>> T max(T a, T b) {
    return a.compareTo(b) >= 0 ? a : b;
}
```

If there is a class bound, it comes before the interface bounds; for example, `Number` before `Comparable`. **Bound and scope are two independent decisions**: bound determines the capabilities of the type, while scope determines where the type relationship must exist.

## 11. When naming T is unnecessary, use a wildcard

A method that only retrieves the size:

```java
static <T> int size(List<T> values) {
    return values.size();
}
```

can be expressed more concisely:

```java
static int size(List<?> values) {
    return values.size();
}
```

These are two alternatives; **do not place both with the same name in one class** due to having the same erasure.

`List<?>` indicates that the element type does not matter. When a type variable does not link the output, a callback, or another parameter, a wildcard can be clearer.

Conversely, a copy method needs a constraint between source and destination:

```java
static <T> void append(
        List<? extends T> source,
        List<? super T> destination) {
    destination.addAll(source);
}
```

`T` links the producer with the consumer. `List<Integer>` can be passed as `source`, and `List<Number>` as `destination`. Two independent `List<?>` parameters do not guarantee a shared element type, so this signature cannot be replaced while still supporting `addAll` safely.

A pure read from a `Number` subtype can accept:

```java
static double sum(List<? extends Number> values) {
    double total = 0;
    for (Number value : values) {
        total += value.doubleValue();
    }
    return total;
}
```

`<T extends Number>` is unnecessary if `T` adds no useful relationship. However, "always drop `T` when `T` appears only once" is not an absolute rule; inference, overloads, compatibility, and implementation bodies can still affect the choice.

## 12. Anti-pattern: generic return without proof

A method:

```java
// Anti-pattern: does not prove type safety on its own.
@SuppressWarnings("unchecked")
static <T> T pretend(Object value) {
    return (T) value;
}
```

allows the caller to request a `String` from an `Integer`. `<T>` does not make the cast safe; `ClassCastException` may occur when the result is used as a `String`.

If an actual runtime class check is needed:

```java
static <T> T checked(Class<T> token, Object value) {
    return token.cast(value);
}
```

A class token provides the runtime type to check. However, `Class<T>` cannot directly represent `List<String>` because `List`'s type arguments are not reifiable; nested generic data requires separate validation.

A safe generic method must express a **verifiable relationship between the type parameter and data/callbacks**, not merely have the symbol `T` in the return type.

## 13. Overloading and type erasure

**File BadErasureOverloads.java, intentionally does not compile:**

```java
import java.util.List;

class BadErasureOverloads {
    void store(List<String> list) {}
    void store(List<Integer> list) {}
}
```

Both signatures erase to `store(List)`, so `javac` reports `name clash ... have the same erasure`.

If both methods perform the same algorithm, consider merging them into `<T> void store(List<T>)`. If they perform two distinct business operations, choose names that reflect those operations. Do not add a dummy parameter or raw cast just to bypass the compiler and make the API confusing.

## 14. Type inference does not imply the same runtime class

A method:

```java
static <T> void combine(T a, T b) {
    System.out.println(a + " / " + b);
}
```

does not require both objects to have the same `getClass()`. The compiler can choose `T` as a valid **common supertype** for two arguments of different runtime classes, depending on the context.

Therefore, the same `T` expresses a compile-time assignability relationship, **not a runtime check that `a` and `b` have the same exact class**. When business logic has stricter requirements, use specific domain types, a class token, or separate validation.

## 15. Changing generic scope can break public APIs

Compare:

```java
interface Store<E> {
    void add(E value);
    E get(int index);
}
```

with:

```java
interface Store {
    <E> void add(E value);
    <E> E get(int index);
}
```

The first version has a consistent `E` for the same typed `Store`. In the latter, `add`'s `E` and `get`'s `E` are inferred independently, and there is no longer proof that the values are related to one another. Callers using `Store<String>` also can no longer declare it as before.

Moving a type parameter from class to method (or vice versa) can affect source compatibility, overload resolution, overriding, reflection signatures, and in some changes also binary compatibility. **Do not assume it is a purely syntactic refactoring.**

A utility class carrying too many type parameters—forcing callers to write type arguments unrelated to state—can be simplified with method-level generics, but callers and public contracts must be checked before making changes.

## 16. Quick decision table

| Need | Where to place the type parameter? | Reason |
| --- | --- | --- |
| Box holds T, set/get T | `Box<T>` | State and multiple methods need a consistent T. |
| Repository only stores E | `Repository<E>` | E is an instance invariant. |
| Repository groups by key K depending on callback | `Repository<E>` + `<K> groupBy` | K belongs to a single call only. |
| Typed key/value Cache | `Cache<K,V>` | Both types belong to long-lived state. |
| One-off T→R conversion | `static <T,R> R convert(...)` | No generic state. |
| Configured, reusable mapper | `ConfiguredMapper<T,R>` | Mapping function is held inside the object. |
| Compute size of any List | `int size(List<?>)` | No need to name the type. |
| Copy source into destination | `static <T> append(List<? extends T>,List<? super T>)` | T links the two positions. |
| Factory creating any Box<X> | `static <X> Box<X> of(X)` | Static method has an independent X. |
| Constructor with one-off audit U | `Envelope<T>`, constructor `<U>` | T belongs to the class, U belongs to construction. |

## 17. API review checklist

1. Which fields, parameters, and results is `T` linking?
2. Is the same `T` needed across multiple calls on one receiver?
3. Does the caller need to specify `T` when creating an instance?
4. Can the result of a `map` operation change type on each call? If so, `R` belongs on the method.
5. Is a static method trying to use a class-level `T`?
6. Does a method redeclare `<T>` and shadow the class-level `T`?
7. Can an unnecessary generic variable be replaced with `?`?
8. Is PECS needed to allow reading subtypes or writing into supertypes?
9. Does a generic return prove a relationship between the type and actual data?
10. Do any generic overloads collide after erasure?
11. Are type arguments inferred cleanly without excessive casting?
12. When changing scope, does it alter the public contract, overrides, or caller declarations?
13. Have `String`/`Integer` cases and different type combinations been tested in a real compiled program?

## 18. Exercises and answers

**1.** A `Box` has a `value` field, a getter, and a setter. Choose a generic class or a generic method?

**Answer:** `Box<T>`, because `T` is an invariant of the state and all operations.

**2.** A method reverses a `Pair<A,B>` without holding state?

**Answer:** It can be `static <A,B> Pair<B,A> reverse(Pair<A,B>)`, because `A`/`B` are related within a single call.

**3.** Why is `K` in `Repository<E>.<K>groupBy` not at the class level?

**Answer:** A repository holds a fixed `E` but can group by different key types in independent calls.

**4.** Where is the error in `class Box<T> { T x; <T> void set(T v) { x=v; } }`?

**Answer:** The method redeclares `T`, shadowing the class's `T`. Remove `<T>` from the method.

**5.** Can a static factory use the class's `T`?

**Answer:** Not directly; declare `static <X> Box<X> of(X)` with its own `X`.

**6.** When should `List<?>` be used instead of `<T> List<T>`?

**Answer:** When the element type does not need to be linked with the output/other parameters, such as only reading the size.

**7.** Why does copying a `List` of `Integer` into a `List` of `Number` need a `T`?

**Answer:** `T` links the producer's element type with a compatible destination type, usually via `? extends T` and `? super T`.

**8.** Does a generic constructor `<U> Envelope(T,U)` cause the object to carry two type arguments?

**Answer:** No; the object still has class type `Envelope<T>`. `U` is only within the constructor.

**9.** Does the same `T` in `combine(T,T)` force the runtime classes to be identical?

**Answer:** No; the compiler can choose a valid common supertype.

**10.** When is `ConfiguredMapper<T,R>` better than a method `<T,R> convert(...)`?

**Answer:** When the object actually holds the `T→R` mapper for reuse across multiple calls.

**11.** Should `<T> T pretend(Object)` be used to cast data of unknown type?

**Answer:** No; there is no safety relationship. Use a `Class` token or validator matching the runtime contract.

**12.** Can `Store<E>` be changed into a non-generic interface with `<E>` methods without changing the contract?

**Answer:** No. The type relationship between `add`/`get` calls is lost, and caller declarations may no longer be valid.

## 19. Summary

- **Class/interface level:** choose when `T` is part of the object's contract, tied to multiple methods or long-lived state.
- **Method level:** choose when `T`/`R`/`K` only expresses the relationship of a single call; it can be re-inferred in subsequent calls.
- **Combining both:** `Box<T>` with `<R> map`, `Repository<E>` with `<K> groupBy`.
- **Generic constructor:** can accept a temporary type `U` without adding another type parameter to the class.
- **Static context:** do not directly use the class's `T`; static generic factories declare their own type variable.
- **Wildcard:** use when naming a type parameter is unnecessary, merely for reading or observing data.
- **Avoid pitfalls:** shadowing, unchecked casts, generic methods without an invariant, erasure-colliding overloads, and refactorings that break public contracts.

**Final rule:** Place type parameters in the smallest scope that still fully preserves the invariants and type relationships the API promises to callers.
