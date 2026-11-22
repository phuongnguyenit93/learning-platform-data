# Name Clash Due to Identical Erased Signatures in Java Generics

A Java class can declare methods with the same name that accept different parameter types. However, when parameters use generics, **two signatures that look different in source code can still undergo type erasure to the same parameter form in bytecode**. If those methods do not form a valid override relationship, the compiler reports a **name clash** and rejects the program.

Typical example:

```java
// DOES NOT COMPILE: intentional name clash example.
import java.util.List;

class DuplicateProcessor {
    void process(List<String> names) { }
    void process(List<Integer> ids) { }
}
```

Both `List<String>` and `List<Integer>` erase to `List`. In Java, changing the **type argument** of a parameterized type is not enough to create two overloads with distinct signatures after erasure.

This lesson explains how to compute erasure yourself, why clashes occur during overloading or inheritance, when overriding is valid, the role of bridge methods, and how to design APIs to avoid name clashes.

## 1. Distinguish Three Concepts: Overload, Override, and Name Clash

**Overloading:** having multiple methods with the same name but different **parameter type lists** so the compiler can resolve calls. For instance, `send(String)` and `send(Integer)` are two valid overloads.

**Overriding:** a subclass or implementing class method replaces the behavior of an inherited method according to Java's signature, accessibility, return-type, and related rules. Overriding can involve generics and bridge methods.

**Name clash:** two methods produce conflicting signatures under language rules—for example, having the **same erasure without validly overriding one another**. In that case, the compiler cannot keep both as valid overloads.

Not every pair of methods with the same erasure is an error: **a valid override is specifically a case that must preserve the same dynamic dispatch after erasure**. Accurate diagnosis requires evaluating both erasure **and inheritance/override relationships**.

### Quick examples

| Declaration | Result | Reason |
| --- | --- | --- |
| `f(List<String>)` and `f(List<Integer>)` in one class | Name clash | Both erase to `f(List)` |
| `f(List<String>)` and `f(Set<Integer>)` | Valid | Erasures are `f(List)` and `f(Set)` |
| `f(List<String>, int)` and `f(List<Integer>, String)` | Valid | The second parameter distinguishes the erased signatures |
| `<T> f(T)` and `f(Object)` in one class | Name clash | Unbounded `T` erases to `Object` |
| `<T extends Number> f(T)` and `f(Number)` | Name clash | `T` erases to `Number` |
| `<T> f(T)` and `f(String)` | Valid | Parameter erasures are `Object` and `String`, respectively |
| Subclass overriding `Parent<String>.save(String)` | Can be valid | Proper generic override; compiler generates a bridge if needed |

The syntax illustrations in the table are assumed to be declarations in valid class contexts, with each pair evaluated separately.

## 2. What “Signature” Does a Method Have in Source and After Erasure?

In Java, **you cannot overload solely by return type**. When distinguishing overloads, the method name and parameter types/order matter; generic type arguments can make two parameter lists look different in source yet identical after erasure.

For example:

```java
// These two lines look different in source:
void save(java.util.List<String> names) { }
void save(java.util.List<Integer> ids) { }
```

How to compute the erasure of both:

```text
save(List<String>)   -> save(List)
save(List<Integer>)  -> save(List)
```

At the JVM level, for `void` methods, both would require the descriptor:

```text
(Ljava/util/List;)V
```

The notation `Ljava/util/List;` represents the `java.util.List` parameter type, and `V` represents the `void` return. That is the **exact same descriptor** in the example above; the JVM has no separate descriptor directly carrying `String` or `Integer` for the `List<E>` parameter.

Therefore, the compiler cannot generate two distinct methods just because two type arguments differ. The issue must be rejected at compile time.

### Erasure rules sufficient to spot most cases

1. `List<String>`, `List<Integer>`, and `List<?>` all erase to `List`.
2. `Map<String, Integer>` and `Map<Long, Long>` both erase to `Map`.
3. An **unbounded** type variable `T` erases to `Object`.
4. `T extends Number` erases to `Number`.
5. With multiple bounds, such as `T extends Number & Comparable<T>`, the erasure of `T` is its **first bound**, namely `Number`.
6. Array types with parameterized generic components also undergo element erasure: `List<String>[]` and `List<Integer>[]` both erase to an array of raw `List`. (Do not infer from this that every generic array creation is valid.)

In the context of method signatures, erase each parameter type and then compare the entire **parameter list** in order.

## 3. Overload Clashes: Changing Type Arguments Is Not Enough

This is the most common error.

```java
// DOES NOT COMPILE. This file illustrates an error, not a runnable exercise.
import java.util.List;

class Service {
    void handle(List<String> names) {
        System.out.println("names");
    }

    void handle(List<Integer> ids) {
        System.out.println("ids");
    }
}
```

The compiler reports a **name clash** error because the two methods have the same erasure. Variable names `names` and `ids`, method body contents, or what kind of elements the lists actually hold at runtime do not alter the signature.

It cannot be fixed by renaming parameters:

```java
// Still clashes if declared in the same class:
void handle(List<String> a) { }
void handle(List<Integer> b) { }
```

Nor can it be fixed by changing the return type:

```java
// DOES NOT COMPILE, illustrative only:
// int read(List<String> a) { return 1; }
// long read(List<Integer> b) { return 2L; }
```

Return types are not a criterion for distinguishing Java overloads. Moreover, Java rejects two methods differing only in return type **even without generics**.

### Not just `List`: any generic class or interface can run into this

```java
// DOES NOT COMPILE if both methods are in the same class:
void index(java.util.Map<String, Integer> mapping) { }
void index(java.util.Map<Long, Double> mapping) { }
```

Both parameters erase to `Map`. Likewise, `Comparable<String>` and `Comparable<Integer>` both erase to `Comparable`; an API trying to overload solely on their type arguments will hit the same problem.

## 4. Cases Where Type Variables Eliminate the Difference

Type variables can make two overloads look very different yet have the same erasure.

```java
// DOES NOT COMPILE:
class Operation {
    <T> void put(T value) { }
    void put(Object value) { }
}
```

Because `T` is unbounded, `T` erases to `Object`:

```text
<T> put(T)     -> put(Object)
put(Object)    -> put(Object)
```

Similarly:

```java
// DOES NOT COMPILE:
class NumberOperation {
    <T extends Number> void put(T value) { }
    void put(Number value) { }
}
```

Both become `put(Number)`. Note: the erasure of `T extends Number` is **Number**, not a concrete type inferred at one call site such as `Integer`.

Conversely, this is a **valid overload**:

```java
// Snippet: can be placed in the same class.
static <T> void print(T value) {
    System.out.println("Generic: " + value);
}

static void print(String value) {
    System.out.println("String: " + value);
}
```

After erasure, the generic method accepts `Object`; the other accepts `String`. Their descriptors differ, so there is no name clash. When calling `print("hello")`, the compiler normally chooses the more specific `String` overload, while `print(123)` can use the generic overload. **Overload resolution occurs at compile time based on static types**, not because the JVM sees a `String` at runtime and re-selects an overload.

## 5. Name Clashes Caused by Inherited Methods

Clashes do not happen only when writing two methods in the same class. A subclass can also write a method that looks different yet erases to the signature of an inherited method **without forming a valid override**.

```java
// DOES NOT COMPILE:
import java.util.List;

class Base {
    void process(List<String> names) { }
}

class Derived extends Base {
    void process(List<Integer> ids) { }
}
```

In `Base`, the erasure is `process(List)`; in `Derived`, it is also `process(List)`. Yet `process(List<Integer>)` is not a valid override of `process(List<String>)`. Thus the compiler can treat this neither as an independent overload nor as a valid override.

**Lesson:** when seeing a `name clash` error in a subclass that declares only **one** method, do not jump to blaming the compiler. Check all same-named methods in superclasses and interfaces that the class inherits from.

### Two interfaces demanding two incompatible generic versions

```java
// INVALID example if a class tries to implement both requirements
// using the same name and parameter list erasing to one signature.
interface NameReceiver {
    void receive(java.util.List<String> names);
}

interface IdReceiver {
    void receive(java.util.List<Integer> ids);
}

// A class attempting to implement both cannot declare two valid
// overloads receive(List<String>) and receive(List<Integer>).
```

This shows that clashes can originate from **inheriting multiple interface contracts**, even when each individual interface compiles cleanly. To redesign the API, you can unify a single generic contract, use different method names, or pass a genuinely distinct parameter type to the processing strategy.

### Why “two distinct generic types” is not enough

In theory, `List<String>` and `List<Integer>` are **two invariant static types** that cannot be assigned to each other directly. However, Java's overload and override rules must also satisfy **method compatibility after type erasure**. Hence two distinct type arguments do not guarantee signatures distinct enough to coexist.

## 6. Why Is a Valid Generic Override Not Treated as a Name Clash?

Consider a generic superclass:

```java
class Parent<T> {
    void save(T value) {
        System.out.println("Parent: " + value);
    }
}

class Child extends Parent<String> {
    @Override
    void save(String value) {
        System.out.println("Child: " + value);
    }
}
```

When binding `T = String`, `Child.save(String)` overriding `Parent<T>.save(T)` is valid at the language level. After erasure, however, the superclass method's descriptor accepts `Object`, while the subclass implementation accepts `String`.

The compiler resolves this with a **bridge method** in the subclass bytecode, roughly behaving like:

```java
// Pseudocode to understand the bridge, DO NOT add to Child:
void save(Object value) {
    save((String) value);
}
```

The bridge ensures that a call through `Parent<String> parent = new Child(); parent.save("abc");` still enters the overridden `Child.save(String)`. This bridge is compiler-generated, may be flagged `ACC_BRIDGE` and `ACC_SYNTHETIC` in bytecode, and is detected by reflection via `Method.isBridge()`.

This is **not** an overload clash between two methods a programmer tried to declare. The compiler knows this is a valid override relationship, so it can generate bridge code while preserving polymorphism. When encountering a name clash error, distinguish:

- **Two methods lacking a valid override relationship** that share the same erasure: rejected.
- **A valid generic override** whose erased descriptor differs: the compiler can insert a bridge to preserve dispatch.

Inside a subclass, if you try to manually declare a method whose erased signature competes with a bridge that needs to be generated, the compiler can also report a name clash. Do not hand-write `save(Object)` to “replace” the bridge for `Child.save(String)`; keep the specialized override and let the compiler do that job.

## 7. Subsignature and Compatibility with Legacy Code

A subtle point in Java is the **subsignature** relationship: Java permits certain override cases where the subclass method signature matches the erased form of the superclass method. This rule supports migrating legacy libraries to generics without breaking every existing subclass.

Conceptual example:

```java
// Snippet illustrating source compatibility mechanism on inheritance:
class GenericParent {
    <T> void accept(T value) { }
}

class LegacyChild extends GenericParent {
    @Override
    void accept(Object value) { }
}
```

In this context, `accept(Object)` in the subclass can override `<T> accept(T)` in the superclass thanks to an erasure-compatible signature. Although both have an `Object` parameter in their descriptors, this is a **valid override**, not an overload needing disambiguation.

This differs from `accept(List<String>)` and `accept(List<Integer>)` sharing the erasure `accept(List)`: they do not automatically form an override relationship just because their erasures match.

Do not mechanically use the trick “replace all generics with raw types” to fix a name clash. Raw types and unchecked conversions weaken type checking, alter overload selection, and hide data bugs. A proper solution must preserve the API contract and real inheritance relationships.

## 8. Java 17+ Program Demonstrating Valid Cases

Save the entire code below into **`NameClashDemo.java`**:

```java
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Set;

public class NameClashDemo {
    // Valid: List and Set have different erasures.
    static void inspect(List<String> values) {
        System.out.println("List: " + values.get(0));
    }

    static void inspect(Set<Integer> values) {
        System.out.println("Set: " + values.iterator().next());
    }

    // Valid: T extends Number erases to Number, distinct from String.
    static <T extends Number> void describe(T value) {
        System.out.println("Number: " + value);
    }

    static void describe(String value) {
        System.out.println("String: " + value);
    }

    // Valid: unbounded T erases to Object, distinct from String.
    static <T> void log(T value) {
        System.out.println("Generic: " + value);
    }

    static void log(String value) {
        System.out.println("Specific: " + value);
    }

    static class Parent<T> {
        void save(T value) {
            System.out.println("Parent: " + value);
        }
    }

    static final class Child extends Parent<String> {
        @Override
        void save(String value) {
            System.out.println("Child: " + value.toUpperCase(Locale.ROOT));
        }
    }

    public static void main(String[] args) {
        inspect(List.of("Java"));
        inspect(Set.of(7));
        describe(42);
        describe("erasure");
        log("hello");
        log(100);

        Parent<String> parent = new Child();
        parent.save("bridge");

        boolean hasBridge = Arrays.stream(Child.class.getDeclaredMethods())
                .anyMatch(Method::isBridge);
        System.out.println("Bridge method: " + hasBridge);
    }
}
```

Use JDK 17 or newer:

```bash
javac -encoding UTF-8 NameClashDemo.java
java NameClashDemo
```

Output:

```text
List: Java
Set: 7
Number: 42
String: erasure
Specific: hello
Generic: 100
Child: BRIDGE
Bridge method: true
```

Explanation:

1. `inspect(List<String>)` and `inspect(Set<Integer>)` share the same name but have **different erasures**: `List` and `Set`. Therefore both coexist in one class.
2. `describe(T extends Number)` erases to `describe(Number)`, sufficiently distinct from `describe(String)`.
3. `log(T)` erases to `log(Object)`, sufficiently distinct from `log(String)`. Calling `log("hello")` selects the `String` overload; `log(100)` selects the generic overload.
4. `parent.save("bridge")` invokes `Child`'s override logic through a parent reference bound to `String`.
5. Reflection detects the compiler-generated **bridge method** on `Child`. The presence of the bridge proves the compiler preserved the override after erasure, rather than generating a separate `Parent<String>` class for the type argument.

This example is a standalone program; the **DOES NOT COMPILE** examples in other sections must be tested separately, not copied directly into `NameClashDemo.java`.

## 9. Fixing Name Clashes According to API Needs

### Approach 1: Rename methods by business meaning

From two conflicting overloads:

```java
// Invalid if placed in the same class:
// void process(List<String> names) { }
// void process(List<Integer> ids) { }
```

Change to:

```java
// Valid snippet:
void processNames(List<String> names) { /* ... */ }
void processIds(List<Integer> ids) { /* ... */ }
```

This is usually the clearest option when each list requires different business logic. It preserves static type checking and makes the API easy to discover by name.

### Approach 2: Choose two parameter types that genuinely differ after erasure

If two operations **inherently have different input structures**, use appropriate abstractions whose erasures still differ:

```java
// Valid snippet if it fits the design:
void process(List<String> names) { /* ... */ }
void process(Set<Integer> ids) { /* ... */ }
```

However, do not swap `List` for `Set` merely to “trick the compiler”: `Set` has different semantics regarding duplicate elements and ordering, affecting program behavior. Parameter types must reflect the real data contract.

### Approach 3: Use one unified generic method

If both element types are processed by **the exact same algorithm**, two overloads are unnecessary:

```java
// Valid snippet: one API for any type T.
static <T> int count(List<T> items) {
    return items.size();
}
```

You can call `count(List<String>)` or `count(List<Integer>)` with full source-level type checking; bytecode only needs a single method taking `List`.

If the algorithm varies by element type, pass the variation via a strongly typed **strategy** or callback:

```java
// Valid snippet; illustrates only the generic signature using a callback:
static <T> void processAll(
        List<T> items,
        java.util.function.Consumer<? super T> operation) {
    for (T item : items) {
        operation.accept(item);
    }
}
```

At call sites you can pass `processAll(names, System.out::println)`. Processing differences are thus expressed through the `Consumer` argument without duplicating overload signatures on `List<T>`.

### Approach 4: Use dedicated domain types when contracts genuinely differ

If two datasets represent two distinct domain concepts, you can create wrapper types:

```java
// Java 17 illustrative snippet:
record NameBatch(List<String> values) { }
record IdBatch(List<Integer> values) { }

void process(NameBatch names) { /* ... */ }
void process(IdBatch ids) { /* ... */ }
```

The two record types `NameBatch` and `IdBatch` are **two distinct runtime classes**, so overloads are distinguishable. This approach is helpful when representing real domain concepts with their own validation or metadata. Do not create pointless wrappers solely to mask an unclear API.

## 10. Easily Misunderstood Cases

**Misconception 1 — “`List<String>` differs from `List<Integer>`, so overloading must work.”** False. Differing in static types does not imply differing in erased signatures.

**Misconception 2 — “Same erasure means every override fails.”** False. A valid generic override can require a bridge method; the compiler does not treat it as two competing overloads.

**Misconception 3 — “Changing the return type resolves the clash.”** False. Return types are not used to distinguish two Java overloads.

**Misconception 4 — “Different parameter names produce different signatures.”** False. `process(List<String> names)` and `process(List<Integer> ids)` still have a name clash.

**Misconception 5 — “A bounded `T extends Number` still erases to `Object`.”** False. The erasure of `T` is its first bound, namely `Number`.

**Misconception 6 — “Raw types are a universal fix.”** False. Switching to raw `List` still leaves the erasure `List`, while sacrificing type safety.

**Misconception 7 — “The compiler inspects the actual elements inside the list to pick an overload.”** False. Overload selection uses compile-time type information, and `List<String>` carries no separate runtime class from `List<Integer>`.

**Misconception 8 — “Having two methods differing only in generics is a reflection error.”** False. Name clashes are diagnosed during Java compilation, before runtime reflection is ever reached.

**Misconception 9 — “A bridge method is an overload programmers must write.”** False. A bridge is compiler-generated bytecode emitted when needed to preserve polymorphism.

## 11. Step-by-Step Name Clash Diagnosis

When `javac` reports `name clash: ... have the same erasure` or a similar message:

1. **List all methods with the same name**, including methods from superclasses and interfaces; do not look only at the method you just edited.
2. **Write down the full parameter list** of each method in order. Ignore parameter variable names and return types.
3. **Erase type arguments:** `List<String>` → `List`; `Map<K,V>` → `Map`.
4. **Erase type variables to their first bound:** `<T>` → `Object`; `<T extends Number>` → `Number`.
5. **Compare the erased parameter lists.** If they differ, they may still be valid overloads (subject to other Java rules).
6. **If they match, check for a valid override/subsignature.** A valid override relationship can use a bridge; two non-overriding methods risk a name clash.
7. **Choose a fix at the API contract level:** distinct names, genuinely different parameters, a single generic method, a strategy, or domain wrappers; re-check call sites and subclasses.

Do not treat the error message as a “hint to drop generics and move on”. The compiler is pointing out an inconsistency in your method set after erasure. Resolving it requires examining both API design and inheritance structure.

## 12. Self-Check Exercises

**Question 1.** Two methods `void run(List<String> a)` and `void run(List<Integer> b)` belong to the same class. Is this valid?

No. Both erase to `run(List)`; you cannot create two overloads differing only in type arguments.

**Question 2.** Two methods `<T extends Number> void run(T x)` and `void run(String s)` are in the same class. Is this valid?

Yes. Their erasures are `run(Number)` and `run(String)`.

**Question 3.** `<T> void run(T x)` and `void run(Object x)` are in the same class. Is this valid?

No. Unbounded type variable `T` erases to `Object`, causing a signature collision.

**Question 4.** `Child extends Parent<String>` and properly overrides `void save(String)`. Why can the compiler generate `save(Object)` in bytecode without reporting a name clash?

Because this is a **valid override relationship**, and `save(Object)` is a compiler-generated bridge enabling dynamic calls compatible with the erased superclass method, not a competing user-declared overload.

**Question 5.** Do `sum(List<String>, int)` and `sum(List<Integer>, long)` have a name clash just because of generics?

No. After erasure they are `sum(List,int)` and `sum(List,long)`, so their parameter lists remain distinct. Other Java rules still must be satisfied.

**Question 6.** An API needs to process lists of `String` and `Integer` with the exact same algorithm. Are two overloads necessary?

No. Using a single generic method such as `<T> void process(List<T> values)` is much more natural.

## 13. Conclusion and Practical Rules

**A name clash due to erasure** occurs when generic methods have parameter signatures that erase to the same form yet **cannot coexist under Java's overload/override rules**. The key is comparing **erased parameter types** and **override relationships**, not just looking at differences between source-level type arguments `<String>` and `<Integer>`.

When designing generic APIs, do not overload methods merely by changing the type argument of the same generic class. Use clear domain-specific names, choose genuinely distinct parameter types when justified, or unify shared behavior into a generic method. For subclasses, verify inherited signatures and let the compiler generate bridge methods for valid generic overrides.
