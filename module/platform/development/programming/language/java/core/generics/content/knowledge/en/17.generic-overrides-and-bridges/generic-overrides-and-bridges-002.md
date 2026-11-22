# Erased Signatures and the Subsignature Concept in Java Generics

## Learning Objectives

After this lesson, you can:

1. Distinguish **method signatures in the Java language**, **erased signatures**, and bytecode **method descriptors**.
2. Apply the **subsignature** definition to determine the valid override direction between a generic/parameterized method and an erased-signature version.
3. Explain why two methods with the same erasure sometimes form a valid override and sometimes cause a `name clash` error.
4. Understand the relationship between source-level overriding, *type erasure*, *bridge methods*, and dynamic dispatch in the JVM.
5. Diagnose errors using `javac`, `@Override`, and `javap`, and choose fixes that avoid raw types in new API designs.

Context: Java generics are primarily implemented through **type erasure**. Meanwhile, overriding must still remain sound with respect to the source-level type system. These two mechanisms meet in the **subsignature** rule, which supports compatibility when libraries evolve from legacy APIs to generic APIs.

## 1. What Does “Method Signature” Mean?

According to Java's method signature rules (JLS 8.4.2), a signature considers the **name**, **the method's own type parameters if any**, and **the types of the formal parameter list** after applying the corresponding rules for type equivalence and renaming of type parameters.

For example:

```java
// Signature illustration examples, do not place in the same scope because their signatures clash:
void find(java.util.List<String> values);
void find(java.util.List<Integer> values);

<T> void transfer(T value);
<U> void transfer(U value);
```

The two `find` declarations do not have the same source signature because the parameterizations `List<String>` and `List<Integer>` differ. However, they **have the same erasure**, so they cannot be declared as two overloads in the same class. The two `transfer` declarations actually have the **same signature** after renaming the type parameter (`T` ↔ `U`), so they cannot be placed side by side in a class either.

Elements **not part of a Java method signature** include:

- **Return type**: you cannot overload merely by changing `String output()` to `Object output()`.
- Parameter variable names: `void log(String name)` and `void log(String text)` have the same signature.
- `throws`: `void read() throws IOException` and `void read()` do not create two overloads.
- Modifiers such as `public`, `private`, `static`, `final`: they affect inheritance/override validity, not whether two methods have different signatures.
- Annotations and method bodies.

Varargs `String...` and array `String[]` yield the same array parameter kind when determining signatures; they cannot be used as two independent overloads. However, because varargs also governs how arguments are passed at call sites, the two declarations can differ in usage experience even though their signatures are equivalent.

Do not confuse a **source signature** with a **JVM descriptor**: a descriptor encodes parameter types **and return type** in bytecode. They serve two different levels; Section 6 explains this.

## 2. How Does Type Erasure Transform Signatures?

During compilation, type erasure removes or reduces parameterized parts of types to their appropriate erased forms. Several key transformations:

| Type written in Java | Type after erasure | Meaning |
| --- | --- | --- |
| `List<String>` | `List` | Generic type argument is removed from the reference type. |
| `Map<String, Integer>` | `Map` | Both generic arguments are absent from the erased type description. |
| `T`, where `T` has no explicit bound | `Object` | Implicit bound is `Object`. |
| `T extends Number` | `Number` | Takes the erasure of the leftmost bound. |
| `T extends Number & Comparable<T>` | `Number` | Erasure of a type variable is based on its first bound. |
| `List<String>[]` | `List[]` | Erasure applies to the array component type. |
| `int`, `String`, `String[]` | Unchanged | Types without generic type parameters retain their corresponding types. |

Illustrative example:

```java
// Before type erasure:
<T> T identity(T value);
<T extends Number> T twice(T value);
void display(java.util.List<String> values);

// Conceptual representation after type erasure:
// Object identity(Object value);
// Number twice(Number value);
// void display(java.util.List values);
```

This is a **conceptual diagram**: do not copy both groups into a class as separate methods. The Java compiler may retain generic information in the `Signature` metadata to support reflection/tooling, but JVM descriptors and invocations use erased types as appropriate.

**The erased signature of a method** is a signature with the same name, where each formal parameter's type is replaced by its corresponding erasure. To determine it, look at the **parameters** and generic types; the return type is erased during compilation but **does not participate in defining a source method signature**.

For example:

- `void submit(List<String> values)` → erased signature: `submit(List)`.
- `void submit(List<Integer> values)` → erased signature: `submit(List)`.
- `<T> void inspect(T value)` → erased signature: `inspect(Object)`.
- `<T extends Number> void inspect(T value)` → erased signature: `inspect(Number)`.

Thus, two methods differing only in generic type arguments can become the same call target after erasure.

## 3. Definition of Subsignature and Relationship Direction

Let `sig(m)` denote the Java method signature of `m` and `erasure(sig(m))` denote its erased signature.

**The signature of `m1` is a subsignature of `m2` if and only if one of two cases holds:**

1. `sig(m1)` is the **same** as `sig(m2)` according to Java signature rules; or
2. `sig(m1)` is the **same as the erased signature of `m2`**.

In short:

```text
m1 subsignature m2
⇔ sig(m1) == sig(m2)
   or sig(m1) == erasure(sig(m2))
```

The `==` symbol in the diagram above denotes **signature equivalence under Java rules**, not an object comparison operator or ordinary string comparison.

An easily missed point: **subsignature is directional**. If `m1` is a subsignature of `m2`, you cannot automatically conclude the reverse holds. When signatures are identical, both directions hold; when equivalence holds only via erasure, it may hold in only one direction.

For example:

```java
// Method m1:
void accept(java.util.List items);

// Method m2:
void accept(java.util.List<String> items);
```

- `sig(m1) = accept(List)`.
- `sig(m2) = accept(List<String>)`.
- `erasure(sig(m2)) = accept(List)`.
- **m1 is a subsignature of m2** because `m1`'s signature equals the erasure of `m2`.
- **m2 is not a subsignature of m1**: `accept(List<String>)` is neither the same as `accept(List)` nor the same as the erasure of `accept(List)`.

These two illustrative methods **must not be placed side by side in the same class**. The subsignature relationship is useful when evaluating overrides between declarations in classes/interfaces related by inheritance.

### How does override-equivalent differ from subsignature?

Two signatures are **override-equivalent** if the first is a subsignature of the second **or vice versa**. This concept is symmetric, unlike the one-way subsignature check.

However, two signatures being override-equivalent **does not automatically guarantee one method actually overrides the other**. Java still checks the inheritance relationship, whether the method is suitably inherited/accessible, `static` vs. instance, access privileges, return-type compatibility, checked exceptions, and related rules.

For example, a `static` method can hide another `static` method (*hiding*) instead of overriding it. A `private` method in a superclass is not overridden the way inherited instance methods are. A class also cannot override a `final` method.

## 4. Why Does Java Have the Subsignature Rule?

Consider a legacy API before generics:

```java
// Old API version, illustrative:
class Library {
    void consume(java.util.List items) { }
}

class Client extends Library {
    @Override
    void consume(java.util.List items) { }
}
```

Later, the library author wants to describe the elements more explicitly:

```java
// Generified version of Library:
class Library {
    void consume(java.util.List<String> items) { }
}
```

The signature `Client.consume(List)` is a subsignature of `Library.consume(List<String>)`, so the old method in `Client` can still override the generified method. This is a capability supporting compatibility when migrating legacy APIs to generics.

The reverse direction is **not equivalent**. If the superclass has `consume(List)`, and the subclass tries to declare `consume(List<String>)`, then the subclass signature is **not a subsignature** of the superclass signature. Because the two signatures have the same erasure without forming a valid override, the compiler usually reports `name clash`.

You can remember this with a table:

| Superclass declaration | Subclass declaration | Result |
| --- | --- | --- |
| `void f(List<String> x)` | `void f(List x)` | Can override via erasure subsignature; raw types have limitations. |
| `void f(List x)` | `void f(List<String> x)` | Not a valid override; `name clash`. |
| `<T> void f(T x)` | `void f(Object x)` | Can override because `f(Object)` is the erasure of `f(T)`. |
| `void f(Object x)` | `<T> void f(T x)` | Not a valid override direction; may cause `name clash`. |
| `<T> void f(T x)` | `<U> void f(U x)` | Same signature after type parameter renaming; can override. |

The table considers signature rules assuming instance methods and that all other override requirements are met. It does not make raw types the default choice: `List` itself has no type argument, reducing type safety and potentially producing `rawtypes` warnings.

## 5. Java 17 Program: Valid Overrides and Bridges

This is a standalone program demonstrating three related scenarios:

- Overriding a generic method with an erased signature.
- Overriding a method taking `List<String>` with raw `List` in the implementing class.
- Overriding when a generic class is specialized, resulting in a bridge method; also observing a bridge for a covariant return type.

**File `ErasureSignatureDemo.java`:**

```java
import java.lang.reflect.Method;
import java.util.List;

public class ErasureSignatureDemo {
    static class Base {
        public <T> String render(T value) {
            return "base:" + value;
        }
    }

    static final class LegacyOverride extends Base {
        @Override
        public String render(Object value) {
            return "legacy:" + value;
        }
    }

    interface Catalog {
        void add(List<String> names);
    }

    static final class RawCatalog implements Catalog {
        @Override
        public void add(List names) {
            System.out.println("added:" + names.size());
        }
    }

    static class Box<T> {
        T echo(T input) {
            return input;
        }
    }

    static final class StringBox extends Box<String> {
        @Override
        String echo(String input) {
            return "str:" + input;
        }
    }

    static class Animal {
        Animal copy() {
            return this;
        }
    }

    static final class Dog extends Animal {
        @Override
        Dog copy() {
            return this;
        }
    }

    public static void main(String[] args) {
        Base base = new LegacyOverride();
        System.out.println(base.render(42));

        new RawCatalog().add(List.of("A", "B"));

        Box<String> box = new StringBox();
        System.out.println(box.echo("Java"));

        for (Method method : StringBox.class.getDeclaredMethods()) {
            if (method.isBridge()) {
                System.out.println("bridge:" + method.getName()
                    + "(" + method.getParameterTypes()[0].getSimpleName()
                    + ")->" + method.getReturnType().getSimpleName());
            }
        }

        Animal animal = new Dog();
        System.out.println(animal.copy().getClass().getSimpleName());

        for (Method method : Dog.class.getDeclaredMethods()) {
            if (method.isBridge()) {
                System.out.println("covariant bridge:" + method.getName()
                    + "()->" + method.getReturnType().getSimpleName());
            }
        }
    }
}
```

Compile and run:

```bash
javac --release 17 ErasureSignatureDemo.java
java ErasureSignatureDemo
```

**Verified stdout:**

```text
legacy:42
added:2
str:Java
bridge:echo(Object)->Object
Dog
covariant bridge:copy()->Animal
```

The program uses Java 17 or newer. With `javac --release 17 -Xlint:rawtypes ErasureSignatureDemo.java`, the compiler warns about a raw type on the `List names` parameter in `RawCatalog`; that is **intentional to illustrate legacy API compatibility**. In new applications, prefer writing `void add(List<String> names)` matching the interface unless you need to demonstrate the subsignature mechanism.

### 5.1. Why does `LegacyOverride.render(Object)` override?

In `Base`, `render` is a **generic method**:

```java
public <T> String render(T value)
```

Type variable `T` has no explicit bound, so the erasure of parameter `T` is `Object`. `LegacyOverride.render(Object)` has a signature equal to the erasure of the superclass method, meaning it is a subsignature of it. Therefore `@Override` is valid, and calling through a `Base` variable still executes the subclass code:

```text
legacy:42
```

No bridge needs to be generated solely to connect these two signatures: the relevant bytecode signature already uses an `Object` parameter. Both return types here are `String`.

### 5.2. Why is `RawCatalog.add(List)` accepted?

`Catalog.add(List<String>)` has parameter erasure `List`. The signature `RawCatalog.add(List)` matches that erasure exactly, so the override is permitted. At runtime, the method prints the list size `2`.

`RawCatalog` illustrates how legacy code using raw `List` can continue satisfying a contract that has been enhanced with generics. Raw types can allow unsafe element operations in the implementation; subsignature **does not automatically validate the data inside the List** and does not suppress compiler warnings.

### 5.3. Why does `StringBox.echo(String)` need a bridge?

`Box<T>` has the method `T echo(T)`. In the context of `StringBox extends Box<String>`, `T` is substituted with `String` for source-level override checking, so `String echo(String)` is a valid override.

However, when compiling `Box<T>`, the erasure of `T` is `Object`. The JVM can still invoke `Box.echo(Object)` through a variable of type `Box<String>`. The compiler therefore generates a **bridge** method, typically with equivalent logic like:

```java
// Illustrates the bridge mechanism auto-generated by javac, DO NOT copy into StringBox:
Object echo(Object input) {
    return echo((String) input);
}
```

The bridge carries the erased descriptor, casts the argument to `String`, and delegates the call to `StringBox.echo(String)`. The program prints:

```text
str:Java
bridge:echo(Object)->Object
```

`Method.isBridge()` lets you identify bridge methods via reflection. Bridge methods are usually also marked synthetic (`Method.isSynthetic()`); in this example, `javap` confirms the `ACC_BRIDGE` and `ACC_SYNTHETIC` flags.

Important: **subsignature is a rule used during source-level override resolution; a bridge is compiler-generated code to preserve proper behavior after erasure.** Not every subsignature requires generating a bridge: the `render` and `add` examples above override validly without needing a corresponding bridge.

### 5.4. Bridges due to covariant return types

`Dog.copy()` returns `Dog` while `Animal.copy()` returns `Animal`. The subclass return type is valid under *covariant return* rules. At the bytecode level, descriptors include the return type, so the compiler can generate a bridge:

```text
Dog.copy()    -> Dog
Dog.copy()    -> Animal  // bridge, conceptual form
```

Calling through `Animal animal = new Dog()` still returns the `Dog` instance; the program prints `Dog`. This is an important example because **bridge methods do not arise solely from generics**; covariant return types can also lead to bridges.

## 6. Where Do Java Signatures and JVM Descriptors Differ?

Consider two declarations:

```java
// Illustration:
class Parent<T> {
    T get(T value) {
        return value;
    }
}

class Child extends Parent<String> {
    @Override
    String get(String value) {
        return value;
    }
}
```

They are valid when placed in the same file as appropriate classes. At the source level, the compiler knows `Parent<String>` and sees `Child.get(String)` overriding the inherited method specialized to `String get(String)`.

Yet the class file of `Parent` still uses erased types:

```text
Parent.get(T)
  descriptor: (Ljava/lang/Object;)Ljava/lang/Object;

Child.get(String)
  descriptor: (Ljava/lang/String;)Ljava/lang/String;

Child.get(Object)  // bridge typically generated by javac
  descriptor: (Ljava/lang/Object;)Ljava/lang/Object;
```

JVM descriptors represent types in internal notation: `Ljava/lang/String;` is a `String` reference, `Ljava/lang/Object;` is an `Object` reference, and `V` stands for `void`. A JVM descriptor **includes the return type**. Java source signatures **do not** use the return type to distinguish overloads.

To inspect the Section 5 program after compilation:

```bash
javap -p -v ErasureSignatureDemo$StringBox
javap -p -v ErasureSignatureDemo$Dog
```

On Unix-like shells, quote names containing `$` so the shell does not treat it as a variable, for example:

```bash
javap -p -v 'ErasureSignatureDemo$StringBox'
javap -p -v 'ErasureSignatureDemo$Dog'
```

On PowerShell, placing the name in single quotes like above is also safe. If you only need a source-like method listing, you can use `javap -p ...`; the `-v` flag displays detailed descriptors, flags, and metadata.

`javap -v` output for the relevant methods in `StringBox` (excerpted to the parts we want to observe) includes:

```text
java.lang.String echo(java.lang.String);
  descriptor: (Ljava/lang/String;)Ljava/lang/String;

java.lang.Object echo(java.lang.Object);
  descriptor: (Ljava/lang/Object;)Ljava/lang/Object;
  flags: (0x1040) ACC_BRIDGE, ACC_SYNTHETIC
```

In `Dog`, there are also two forms of `copy()`: one returning `Dog`, and a bridge returning `Animal`. This is why you should not look only at programmer-written methods to guess every method that may appear via reflection at runtime.

**Note:** Generic information is stored via `Signature` metadata when needed, but `Signature` does not turn `List<String>` and `List<Integer>` into two distinct JVM descriptors. Java does not support overloading based solely on generic type arguments of the same parameterized class after erasure.

## 7. Name Clash: Same Erasure Yet Cannot Override

### Case A: Two overloads differing only in generic type arguments

**File `ErasureOverloads.java` — intentionally does not compile:**

```java
import java.util.List;

public class ErasureOverloads {
    void log(List<String> a) {}
    void log(List<Integer> a) {} // Error: same erasure
}
```

Command:

```bash
javac --release 17 ErasureOverloads.java
```

Core error message reported by `javac`:

```text
name clash: log(List<Integer>) and log(List<String>) have the same erasure
```

Both erase to `log(List)`. There is insufficient difference in parameter types at the erased level to represent them as two independent Java overloads. The right fix depends on your need: choose distinct names such as `logStrings` and `logIntegers`, or use **a single** `log(List<T>)` method with a shared contract. Adding another parameter whose erased type actually differs also separates the signatures, but do not add a dummy parameter just to work around the error if it has no design purpose.

### Case B: Putting `List<String>` in a subclass of a raw API

**File `WrongDirection.java` — intentionally does not compile:**

```java
import java.util.List;

class LegacyBase {
    void save(List items) {}
}

public class WrongDirection extends LegacyBase {
    @Override
    void save(List<String> items) {}
}
```

Command:

```bash
javac --release 17 WrongDirection.java
```

Two important messages:

```text
name clash: save(List<String>) in WrongDirection and save(List) in LegacyBase
have the same erasure, yet neither overrides the other
method does not override or implement a method from a supertype
```

The subsignature direction is reversed: the subclass's `save(List<String>)` is **not** a subsignature of `save(List)` in the superclass. If you need to override the legacy API, use `save(List)` matching the inherited signature; if you control the parent API and want greater type safety, consider generifying the parent contract itself after assessing compatibility impact.

### Case C: Arbitrarily specializing a generic method

**File `GenericMethodClash.java` — intentionally does not compile:**

```java
import java.util.List;

class GenericBase {
    <T> void use(List<T> items) {}
}

public class GenericMethodClash extends GenericBase {
    void use(List<String> items) {}
}
```

Command:

```bash
javac --release 17 GenericMethodClash.java
```

Core error message:

```text
name clash: use(List<String>) in GenericMethodClash and
use(List<T>) in GenericBase have the same erasure,
yet neither overrides the other
```

`GenericBase.use` is a **generic method**: each call site can choose `T`. A subclass method accepting only `List<String>` cannot be considered an implementation of a contract that works for any `T`. The erasures of both parameters are `List`, turning the conflict into a compile error instead of an independent overload.

**Distinction from class-level generics:** in `class Box<T> { T echo(T v); }`, `Box<String>` fixes `T` to `String` **for viewing inherited methods on that type**. Thus `StringBox.echo(String)` overrides validly, with a bridge resolving the bytecode difference. By contrast, `<T> void use(List<T>)` in `GenericBase` has `T` scoped **to the method itself**; the subclass cannot turn an “any `T`” contract into “`String` only”.

## 8. How to Recognize Overloads, Overrides, and Name Clashes

When encountering two methods with the same name, analyze them in order:

1. **Place them in their exact type context.** Determine whether the methods are in the same class, in a superclass/subclass pair, or in two interfaces. For class-level generics, substitute type parameters along the inheritance relationship before comparing source-level methods.
2. **Compare source signatures.** If the signatures are identical, they cannot be two overloads in the same class; in an inheritance relationship they may form an override if other conditions hold.
3. **Check subsignature in the right direction.** To check whether `mChild` overrides `mParent`, ask whether the **child's** signature matches the **parent's** signature or the **parent's** erasure.
4. **Compare the erasure of each parameter.** If two methods have the same erasure yet cannot override under Java rules, you risk a `name clash`.
5. **Check additional override conditions.** `static`/instance, `private`, `final`, accessibility, return-type compatibility, and checked exceptions can all make a declaration invalid even when signatures match.
6. **Inspect how Java compiles to bytecode when needed.** If a specialized method has a different erased descriptor from the inherited method, the compiler may add a bridge to preserve proper dispatch.

Quick comparison table:

| Two methods | Source signature | Erasure | Conclusion in the stated context |
| --- | --- | --- | --- |
| Same class: `f(List<String>)` and `f(List<Integer>)` | Different | Same `f(List)` | `name clash`, cannot overload. |
| Same class: `f(String)` and `f(Integer)` | Different | Different | Can overload. |
| Parent `f(List<String>)`, child `f(List)` | Different | Same | Child can override via one-way subsignature. |
| Parent `f(List)`, child `f(List<String>)` | Different | Same | `name clash`; does not override. |
| Parent `<T> f(T)`, child `f(Object)` | Different | Same | Child can override; `Object` is the erasure of unbounded `T`. |
| Parent `<T> f(T)`, child `<U> f(U)` | Same after renaming type variable | Same | Can override if other rules hold. |
| `Box<T>.echo(T)`, `Box<String>` has `echo(String)` | Matches after specializing `T` | Descriptor may differ | Valid override; compiler may generate a bridge. |

In the table, abbreviated signatures such as `f(List)` illustrate only the parameter portion; other method override conditions still apply.

## 9. Important Misconceptions

**Misconception 1 — “Same erasure always means override”.** False. Having the same erasure can be the condition causing a `name clash`. You must check subsignature and other override rules.

**Misconception 2 — “Subsignature is a symmetric (two-way) relationship”.** False. Between a raw declaration and a parameterized declaration, the raw → parameterized direction can satisfy the criterion via erasure; the reverse direction does not hold by default.

**Misconception 3 — “Two methods with different return types have different signatures”.** False at the Java source level. The return type is not part of a source method signature; return-type-substitutability rules govern override validity. However, JVM descriptors do contain the return type, which enables the compiler to generate bridges for covariant returns.

**Misconception 4 — “A bridge is an overload added by the programmer”.** Incorrect. A bridge is a compiler-generated method to preserve overriding semantics in bytecode. You should not manually write a method whose erased signature collides with an expected bridge; doing so can cause conflicts or break the contract.

**Misconception 5 — “Changing `List<String>` to `List<Integer>` is a valid overload”.** Incorrect: both parameterized types have the same erasure. You may need a different API name or a single generic method.

**Misconception 6 — “To fix a `name clash`, cast to raw `List`”.** Casting at a call site does not change the signatures of the two conflicting declarations. You must fix the method signatures/design.

**Misconception 7 — “No bridge is visible in source, so none exists in the JVM”.** The compiler can generate bridges in the class file. Use `Method.isBridge()` or `javap -p -v` to observe them when diagnosing.

## 10. Diagnostic Practice with Tools

For suspected invalid override cases:

1. **Place `@Override`** on the subclass instance method. If the compiler reports it does not override, do not remove the annotation right away; re-examine the signature, subsignature direction, and parameter types after substituting the superclass's generic parameters.
2. Compile with warnings when dealing with legacy APIs: `javac --release 17 -Xlint:rawtypes -Xlint:unchecked File.java`. `rawtypes` warns about raw types, and `unchecked` warns about operations the compiler cannot prove fully type-safe.
3. For a `name clash`, write down both source signatures and their erasures on paper or in a table and check the `child → parent` direction. Changing a type argument such as `List<String>` to `List<Object>` usually **does not** resolve an erasure collision.
4. If the override is accepted but dispatch behavior is puzzling, run `javap -p -v 'ClassName$Subclass'` and look for `descriptor:` and `ACC_BRIDGE`/`ACC_SYNTHETIC`.
5. With reflection, `getDeclaredMethods()` can return bridges too. If you want to process **author-declared methods**, consider filtering `isBridge()` and `isSynthetic()` depending on the tool's purpose; do not filter them unconditionally if you are analyzing ABI or runtime dispatch.

When designing new APIs, prefer fully parameterized types like `List<String>`. Raw method overrides are a compatibility mechanism worth understanding, but usually not the desired style for new code.

## 11. Self-Check

### Question 1

`Class A` has `void put(List<String> xs)`; `Class B extends A` has `void put(List xs)`. Which signature is a subsignature of which?

**Answer:** `B.put(List)` is a subsignature of `A.put(List<String>)` because it equals the erasure of `A`'s declaration. Provided other override conditions are met, `B` overrides `A`.

### Question 2

Reversed: `A` has `void put(List xs)`, `B` has `void put(List<String> xs)`. What happens?

**Answer:** `B` cannot override `A` because the parameterized signature equals neither `A`'s raw signature nor its erasure. Both declarations have the same erasure; the compiler reports `name clash`.

### Question 3

Can you write `void show(List<String> xs)` and `void show(List<Long> xs)` as two overloads in the same class?

**Answer:** No. Both have the erasure `show(List)`.

### Question 4

`class Parent<T>` has `T id(T x)`. `class Child extends Parent<String>` declares `@Override String id(String x)`. Why is the override valid, yet an `id(Object)` method can appear when inspecting bytecode?

**Answer:** At the source level, `Parent`'s `T` is specialized to `String` when viewing `Child`. At the bytecode level, `Parent` is compiled with erasure `Object`; the compiler adds a bridge `id(Object)` forwarding to `id(String)` to maintain dispatch.

### Question 5

Can a method returning `String` and a method with the same name and parameters returning `Object` be two overloads?

**Answer:** No. The return type is not part of a Java source signature; a change in return type can only be valid within an override relationship if it satisfies return-type-substitutability rules, or through a compiler-generated bridge in bytecode.

### Question 6

Does every method that is a subsignature of another method require a bridge?

**Answer:** No. `render(Object)` overriding `render(T)` in the example still shares the same descriptor after erasure, so no separate bridge is needed for that case. Bridges are needed in situations where the compiler must preserve method dispatch across different JVM descriptors.

## 12. Key Takeaways

- **Java Signature**: name and parameter types (along with method type parameter rules); does not use return type or `throws` to distinguish overloads.
- **Erased signature**: name and parameter types after applying erasure; `List<String>` and `List<Integer>` both become `List`.
- **Subsignature**: `m1`'s signature equals `m2`'s signature **or** the erasure of `m2`'s signature; this is a **directional** relationship.
- **Override-equivalent**: subsignature holds in at least one direction; actual overriding must also satisfy inheritance and return-type rules.
- **Name clash**: signatures collide after erasure yet cannot coexist or override under Java rules.
- **Bridge method**: compiler-generated method to maintain proper dispatch after erasure or with covariant return types; observable via `javap` and `Method.isBridge()`.

Understanding all of these rules together lets you explain accurately why the compiler accepts an override using an erased signature, rejects a method that looks “more specialized”, and generates bridges even when the source code declares only a single overriding method.
