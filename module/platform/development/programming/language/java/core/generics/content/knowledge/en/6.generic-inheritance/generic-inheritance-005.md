# Why Cannot a Class Inherit the Same Interface with Two Different Type Arguments?

In Java Generics, a class can implement multiple interfaces, and a generic interface can be used with many different type arguments. However, **the same class or interface cannot simultaneously inherit two different parameterizations of the same generic interface**. For example, Java does not allow a class to be both `Handler<String>` and `Handler<Integer>` through two inheritance paths, even if you plan to write two overloaded methods `handle(String)` and `handle(Integer)`.

This rule often comes as a surprise when designing interfaces such as `Listener<T>`, `Handler<T>`, `Repository<T>`, `Comparable<T>`, or `Converter<I, O>`. The cause relates to **consistency of the inheritance hierarchy** and how Java compiles generics using **type erasure**. This article analyzes both direct and indirect errors, why overloading cannot rescue the design, when inheriting the same type argument is valid, and safer ways to model the need to handle multiple types.

## 1. Recap: Generic Declarations and Parameterized Types

Suppose there is an interface:

```java
interface Handler<T> {
    void handle(T value);
}
```

`T` is the **type parameter** declared on `Handler<T>`. The following types are two different **parameterizations** of the same interface:

```java
Handler<String>
Handler<Integer>
```

Those two lines are illustrative type names, **not standalone Java statements**. For `Handler<String>`, the compiler requires a method taking `String`; for `Handler<Integer>`, it requires taking `Integer`.

A class handling strings is completely valid:

```java
final class TextHandler implements Handler<String> {
    @Override
    public void handle(String value) {
        System.out.println(value.toUpperCase());
    }
}
```

Another class handling integers is also valid:

```java
final class NumberHandler implements Handler<Integer> {
    @Override
    public void handle(Integer value) {
        System.out.println(value * 2);
    }
}
```

Key point: **different classes are allowed to choose different type arguments**. What is prohibited is **a single type simultaneously inheriting both parameterizations of the same interface**.

## 2. Direct Error: A Class Trying `implements Handler<String>, Handler<Integer>`

The snippet below is **intentionally invalid**:

```java
interface Handler<T> {
    void handle(T value);
}

// DOES NOT COMPILE:
class Impossible implements Handler<String>, Handler<Integer> {
    public void handle(String value) { }
    public void handle(Integer value) { }
}
```

The error lies directly in the inheritance relationship `implements Handler<String>, Handler<Integer>`. Java does not allow listing two different parameterizations of the same generic interface for one class. With this direct declaration form, the compiler may also report that interface `Handler` is repeated in the `implements` list.

It is easy to mistakenly think that since `handle(String)` and `handle(Integer)` are two valid overloads in an ordinary class, Java will accept this. However, **method-level overloading does not resolve validity conditions at the type-hierarchy level**.

This is completely different from declaring two overloaded methods in a class that does not implement `Handler<T>`:

```java
final class MultiMethod {
    void handle(String text) {
        System.out.println(text);
    }

    void handle(Integer number) {
        System.out.println(number);
    }
}
```

`MultiMethod` is a valid Java class declaration. It has two methods accepting two different types, without claiming that the object is simultaneously both `Handler<String>` and `Handler<Integer>`. The difference lies in the **inherited interface contracts**, not in the general ability to write overloads.

## 3. Indirect Error Through Two Interface Branches: The Harder-to-Spot Case

Even without writing `Handler<...>` twice directly in the same `implements` list, the rule still applies.

```java
interface Handler<T> {
    void handle(T value);
}

interface TextHandler extends Handler<String> { }

interface NumberHandler extends Handler<Integer> { }

// INTENTIONALLY INVALID:
class BothHandlers implements TextHandler, NumberHandler {
    public void handle(String value) { }
    public void handle(Integer value) { }
}
```

Inheritance diagram:

```text
             Handler<T>
              /     \
     Handler<String> Handler<Integer>
            |             |
       TextHandler    NumberHandler
             \           /
              BothHandlers
                  X
```

Each branch individually is valid: `TextHandler` picks `String`, and `NumberHandler` picks `Integer`. However, when `BothHandlers` wants to inherit both, the hierarchy forces the same class to simultaneously be two incompatible parameterizations of `Handler`.

The compiler will reject this declaration. The exact message varies by compiler and context, usually stating that `Handler` cannot be inherited with different type arguments. **Adding both overloads into the class body still does not fix it.**

The rule also applies when one of the two branches passes through a **superclass** instead of an intermediate interface.

```java
interface Reader<T> {
    T read();
}

abstract class BaseReader<T> implements Reader<T> { }

// INTENTIONALLY INVALID:
class MixedReader extends BaseReader<String>
        implements Reader<Integer> {
    public Integer read() {
        return 1;
    }
}
```

`BaseReader<String>` has already established the `Reader<String>` relationship. `MixedReader` cannot simultaneously add `Reader<Integer>`. The error cannot be fixed simply by choosing one return type for `read()`; the inheritance hierarchy itself is inconsistent.

## 4. Java's Rule: No Two Superinterfaces May Be Different Parameterizations of the Same Generic Interface

The principle can be stated as follows:

> Within the hierarchy of a Java type, the same generic interface must not be inherited with two different type arguments.

Here **"the same generic interface"** means the same declaration, such as `Handler<T>`, not "any two interfaces that happen to use the letter `T`".

**"Inherit"** includes both direct and indirect paths via `extends` or `implements`. If a class `Child` already receives `Handler<String>` from a superclass or superinterface, it cannot also receive `Handler<Integer>` from another branch.

However, two paths leading to **the exact same parameterization** is a different case. For instance, `Left extends ValueSource<String>` and `Right extends ValueSource<String>` can both be implemented by one class, provided other contracts do not conflict. The following section has a runnable program illustrating this valid case.

An important note: the rule does not exist merely because certain method pairs collide after erasure. **Even if a generic interface declares no methods at all**, two different parameterizations of the same interface still cannot appear together in one hierarchy.

```java
interface Marker<T> { }
interface TextMarker extends Marker<String> { }
interface NumberMarker extends Marker<Integer> { }

// INTENTIONALLY INVALID, even though Marker<T> has no methods:
// final class TwoMarkers implements TextMarker, NumberMarker { }
```

Therefore, treat this as **Java's superinterface identity consistency rule**, not merely a problem of avoiding method name collisions that could be cured with overloading.

## 5. Type Erasure Explains Why Two Signatures Do Not Become Two Independent Contracts

Java Generics are primarily checked at **compile time** and implemented via **type erasure**. Consider the interface:

```java
interface Handler<T> {
    void handle(T value);
}
```

In source code:

- `Handler<String>` needs an operation accepting `String`.
- `Handler<Integer>` needs an operation accepting `Integer`.

Yet when the compiler erases an unbounded type parameter, the generic method of `Handler<T>` has a JVM signature essentially like:

```java
void handle(Object value);
```

The snippet above is only **a model of the post-erasure signature**, not an instruction to edit the original interface. There is a single runtime interface declaration `Handler`, not two separate runtime interfaces for `Handler<String>` and `Handler<Integer>`.

When a class implements **one** parameterization, such as `Handler<String>`, the compiler can automatically generate a **bridge method** to maintain polymorphic invocation matching the erased signature. However, you should not assume the compiler will automatically create two independent "generic interface slots" for two different type arguments. Java proactively rejects conflicting hierarchies, rather than waiting until runtime to discover inconsistencies.

### Valid Example to Understand Bridge Methods

Save the file **`BridgeDemo.java`**:

```java
public class BridgeDemo {
    interface Handler<T> {
        T transform(T value);
    }

    static final class UppercaseHandler
            implements Handler<String> {
        @Override
        public String transform(String value) {
            return value.toUpperCase();
        }
    }

    public static void main(String[] args) {
        Handler<String> handler = new UppercaseHandler();
        System.out.println(handler.transform("java"));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 BridgeDemo.java
java BridgeDemo
```

`stdout`:

```text
JAVA
```

In source code, `UppercaseHandler` only needs to write `String transform(String)`. After erasure, the interface has a method of the form `Object transform(Object)`, so the compiler generates a synthetic bridge method in the implementing class to preserve calls through `Handler<String>`.

You can inspect bytecode details:

```bash
javap -p -v 'BridgeDemo$UppercaseHandler'
```

The command above uses the class-file naming of the nested class `BridgeDemo$UppercaseHandler` in a shell supporting single quotes; in Windows PowerShell, this name is also preserved inside single quotes. With the `javac` compiler, the output shows flags `ACC_BRIDGE` and `ACC_SYNTHETIC` on the corresponding bridge method.

**A bridge method is automatic compiler work to support a valid inheritance contract**, not a mechanism allowing inheritance of two different parameterizations.

## 6. Valid Case: Two Branches Inheriting the Exact Same Type Argument

Two interface branches can both point to `ValueSource<String>`.

Save the standalone program **`SameTypeDiamondDemo.java`**:

```java
public class SameTypeDiamondDemo {
    interface ValueSource<T> {
        T value();
    }

    interface FromDatabase extends ValueSource<String> { }

    interface FromCache extends ValueSource<String> { }

    static final class SharedSource
            implements FromDatabase, FromCache {
        @Override
        public String value() {
            return "ready";
        }
    }

    public static void main(String[] args) {
        SharedSource source = new SharedSource();
        ValueSource<String> generic = source;
        FromDatabase database = source;
        FromCache cache = source;

        System.out.println(generic.value());
        System.out.println(database.value());
        System.out.println(cache.value());
    }
}
```

Compile and run with Java 17:

```bash
javac -encoding UTF-8 SameTypeDiamondDemo.java
java SameTypeDiamondDemo
```

Output:

```text
ready
ready
ready
```

Although there are two inheritance paths, both require **the exact same type** `ValueSource<String>`. Class `SharedSource` only needs to implement one `String value()` contract.

Comparison:

| Two inheritance paths | Valid? | Reason |
|---|---|---|
| `ValueSource<String>` and `ValueSource<String>` | Yes, if no other conflicts exist | Same parameterization. |
| `ValueSource<String>` and `ValueSource<Integer>` | No | Two different parameterizations of the same `ValueSource`. |
| `Handler<String>` and `Formatter<Integer>` | Possible | Two different generic interfaces; still must check their signatures. |
| `InterfaceA<String>` and `InterfaceB<String>` | Possible | Same `String` argument, but two different interface declarations. |

Thus **not every diamond inheritance is an error**. The problem lies in inheriting **inconsistent type arguments of the same generic interface**.

## 7. Different Generic Interfaces Can Use Different Type Arguments

Java allows a class to implement multiple **different generic interfaces**, provided the methods they require can be implemented consistently.

Save **`DifferentInterfacesDemo.java`**:

```java
public class DifferentInterfacesDemo {
    interface TextProvider<T> {
        T text();
    }

    interface NumberProvider<T> {
        T number();
    }

    static final class Combined
            implements TextProvider<String>, NumberProvider<Integer> {
        @Override
        public String text() {
            return "hello";
        }

        @Override
        public Integer number() {
            return 42;
        }
    }

    public static void main(String[] args) {
        Combined combined = new Combined();

        TextProvider<String> textProvider = combined;
        NumberProvider<Integer> numberProvider = combined;

        System.out.println(textProvider.text());
        System.out.println(numberProvider.number() + 1);
    }
}
```

Run:

```bash
javac -encoding UTF-8 DifferentInterfacesDemo.java
java DifferentInterfacesDemo
```

`stdout`:

```text
hello
43
```

One class `Combined` simultaneously implements `TextProvider<String>` and `NumberProvider<Integer>`. There is no "same generic interface with two type arguments" error, because `TextProvider` and `NumberProvider` are **two different interfaces**.

Be cautious: not every pair of distinct interfaces is automatically compatible. If they define methods with colliding signatures yet incompatible return types or override requirements, Java can still report an error. The rule being studied is only a **necessary condition of the type hierarchy**, not a replacement for all overload, override, and method erasure rules.

## 8. First Solution: Composition — Keeping Two Separate Handlers and Delegating

If business requirements genuinely call for handling both strings and integers, a natural solution is to use **two separate objects** implementing the same generic interface under two parameterizations, and have a coordinator class hold references to them.

Instead of forcing one class to be both `Handler<String>` and `Handler<Integer>`, the coordinator class **contains** two separate handlers and exposes clear domain methods.

Save **`CompositionDemo.java`**:

```java
public class CompositionDemo {
    interface Handler<T> {
        String handle(T value);
    }

    static final class TextHandler implements Handler<String> {
        @Override
        public String handle(String value) {
            return "text=" + value.toUpperCase();
        }
    }

    static final class NumberHandler implements Handler<Integer> {
        @Override
        public String handle(Integer value) {
            return "number=" + (value * 2);
        }
    }

    static final class Router {
        private final Handler<String> textHandler = new TextHandler();
        private final Handler<Integer> numberHandler = new NumberHandler();

        String processText(String value) {
            return textHandler.handle(value);
        }

        String processNumber(Integer value) {
            return numberHandler.handle(value);
        }
    }

    public static void main(String[] args) {
        Router router = new Router();

        System.out.println(router.processText("java"));
        System.out.println(router.processNumber(21));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 CompositionDemo.java
java CompositionDemo
```

`stdout`:

```text
text=JAVA
number=42
```

Advantages:

1. `TextHandler` is a `Handler<String>` and is type-checked at compile time.
2. `NumberHandler` is a `Handler<Integer>` and has an independent type contract.
3. `Router` does not `implements Handler<String>, Handler<Integer>`; it only **coordinates** two objects.
4. There are no unchecked casts, no raw types needed, and the code is free of superinterface conflicts.

This is usually the best choice if the two behaviors have different logic or different lifecycles/dependencies. Composition is not a trick to "bypass the compiler"; it expresses a different object model that fits the requirement better.

## 9. Second Solution: One Meaningful Common Type for All Cases

If you want **a single handler** processing multiple event forms with a unified contract, model a **common domain type**. Instead of requiring the object to play two `Handler<...>` roles, it implements `Handler<Event>` with a clear event hierarchy.

Java 17 supports `sealed interface` and `record`, convenient for describing a closed set of event types.

Save **`EventHandlerDemo.java`**:

```java
public class EventHandlerDemo {
    interface Handler<T> {
        String handle(T value);
    }

    sealed interface Event permits TextEvent, NumberEvent { }

    record TextEvent(String text) implements Event { }

    record NumberEvent(int number) implements Event { }

    static final class UnifiedHandler implements Handler<Event> {
        @Override
        public String handle(Event event) {
            if (event instanceof TextEvent text) {
                return "text:" + text.text().toUpperCase();
            }
            if (event instanceof NumberEvent number) {
                return "number:" + (number.number() * 2);
            }
            throw new IllegalStateException("Unexpected event");
        }
    }

    public static void main(String[] args) {
        Handler<Event> handler = new UnifiedHandler();

        System.out.println(handler.handle(new TextEvent("java")));
        System.out.println(handler.handle(new NumberEvent(21)));
    }
}
```

Run on JDK 17+:

```bash
javac -encoding UTF-8 EventHandlerDemo.java
java EventHandlerDemo
```

`stdout`:

```text
text:JAVA
number:42
```

Here:

- `Event` is the common type representing data the handler accepts.
- `TextEvent` and `NumberEvent` are the two concrete types in the hierarchy.
- `UnifiedHandler` implements **only `Handler<Event>`**, so it does not violate generic inheritance rules.
- `instanceof` with pattern variables has been supported since Java 16 and is available in Java 17.
- The `if` branches express explicit business logic; their correctness is the program's responsibility, not automatically guaranteed solely by generics.

You could use `Handler<Object>` if the requirement were truly to accept any object, but `Object` widens the contract and reduces the ability to restrict inputs. A domain supertype like `Event` is usually better when the input set is defined.

## 10. Third Solution: Keep the Implementation Generic and Specialize at Instantiation

Sometimes the same algorithm handles any type without needing to distinguish `String` from `Integer`. In that case, the implementing class should **remain generic**:

```java
interface Handler<T> {
    T handle(T value);
}

final class IdentityHandler<T> implements Handler<T> {
    @Override
    public T handle(T value) {
        return value;
    }
}
```

These are illustrative declarations. Now create **two objects** of the same generic class:

```java
Handler<String> texts = new IdentityHandler<>();
Handler<Integer> numbers = new IdentityHandler<>();
```

Each object has a type contract determined at its use site. Neither **a single object nor a single class** is declared to simultaneously inherit two parameterizations of `Handler<T>`.

When designing generic classes, remember to distinguish:

- `class IdentityHandler<T> implements Handler<T>`: declares a generic class forwarding its type parameter to the interface.
- `Handler<String> h = new IdentityHandler<>()`: one **use** of that class with type argument `String`.
- `Handler<Integer> h = new IdentityHandler<>()`: another use with type `Integer`.
- `class Impossible implements Handler<String>, Handler<Integer>`: attempts to create **an invalid inheritance relationship**, fundamentally different from the two instantiations above.

You can specialize once via a subclass for a specific type. For instance, `class StringIdentity extends IdentityHandler<String>` is valid if `IdentityHandler<T>` is not declared `final`. However, that subclass still cannot add `implements Handler<Integer>` because it has already inherited `Handler<String>` from its parent class.

## 11. Why Don't Wildcard `<?>` and Raw Types Fix the Inheritance Error?

### 11.1. Wildcards Express an Unknown Type at the Use Site

A wildcard is appropriate when you need to hold a reference to a handler whose type argument is **unknown**:

```java
Handler<?> anyHandler;
```

This is a variable declaration in a context where `Handler<T>` exists. It does not declare a new interface, nor does it turn `Handler<String>` and `Handler<Integer>` into two roles that one class is allowed to inherit.

If the method is `void handle(T value)`, a `Handler<?>` reference **does not allow arbitrarily calling** `handle("text")` or `handle(42)`, because the compiler does not know what type parameter the wildcard is hiding. You can store different handlers in a collection of wildcard references, but when actually invoking them you must preserve **the relationship between the handler and the input data type**.

Generic helper example:

```java
static <T> void dispatch(Handler<T> handler, T value) {
    handler.handle(value);
}
```

This is an **illustrative method**. When passing `Handler<String>` together with a `String`, the compiler can check the type relationship. If you only have a `Handler<?>` and an arbitrary input object, you need additional type information or a model that properly packages the handler–value pair.

### 11.2. Raw Types Bypass Checking Without Making the Hierarchy Valid

A raw type is writing `Handler` without type arguments. It exists primarily for compatibility with pre-generics Java code.

You should not fix a design by dropping `<String>` or `<Integer>` just to dodge an error. Raw types strip away the type contract and can cause `rawtypes` and `unchecked` warnings, or even cause type errors to surface at runtime. If the original inheritance relationship conflicts, fix the **object model**, do not hide the generic arguments.

### 11.3. Unchecked Casts Do Not Turn a Class into a Different Interface

A cast like `(Handler<Integer>) (Object) handlerOfString` might get past some compile-time checks with warnings or unsafe operations, yet it **does not change the interface structure the class actually implements**. Values passed with the wrong type can cause `ClassCastException` when going through a bridge method or processing code. This is not a solution to inheriting two parameterizations.

## 12. How Else Does Erasure Affect Overloading?

Even without interface inheritance, Java also prohibits certain overloads that share the same signature after type erasure. **Intentionally invalid** example:

```java
import java.util.List;

class WrongOverloads {
    void process(List<String> texts) { }

    // Cannot declare both at the same time:
    // void process(List<Integer> numbers) { }
}
```

If you uncomment the second method, the compiler reports a signature clash: both erase to parameter type `List`. Java does not use generic arguments `String` or `Integer` to distinguish two methods with the same name at runtime.

However, distinguish two rules:

- **Name clash due to erasure**: can occur when defining or inheriting methods whose erased signatures are identical.
- **Cannot inherit two different parameterizations of the same generic interface**: a constraint of the type hierarchy itself. This rule even applies when the interface **has no methods**, as `Marker<T>` illustrated.

Understanding the difference helps pinpoint the root cause. Do not read every generic compiler message and conclude "I just need to rename or add an overloaded method".

## 13. Common Mistakes and How to Handle Them

| Scenario | Problem | How to handle |
|---|---|---|
| `implements Handler<String>, Handler<Integer>` | Two different parameterizations of the same interface. | Use two independent handlers, composition, or a common type. |
| Two parent interfaces respectively `extends Handler<String>` and `extends Handler<Integer>` | **Indirect** inheritance conflict. | Redesign the hierarchy; do not force both branches into one class. |
| `extends Base<String> implements Handler<Integer>` where `Base<T> implements Handler<T>` | Superclass already brings `Handler<String>`. | Keep the same type argument or remove the conflicting relationship. |
| Adding `handle(String)` and `handle(Integer)` | Overloads cannot fix the superinterface relationship. | Do not claim to inherit two `Handler<...>`; use overloads on a coordinator class if needed. |
| Thinking two different interfaces are always forbidden too | The rule applies to **the same generic interface declaration**. | `A<String>` and `B<Integer>` can coexist if methods are compatible. |
| Thinking two branches both having `Handler<String>` is always an error | Inheriting the exact same parameterization can be valid. | Check separately for method/default conflicts if any. |
| Thinking an empty interface `Marker<T>` is exempt from the rule | Inheriting two different type arguments is still invalid. | Do not create conflicting inheritance relationships even on marker interfaces. |
| Using `Handler<?>` and passing `String`/`Integer` arbitrarily | Wildcard is an unknown type, not confirming a writable parameter type. | Preserve type info via generic methods or specialized APIs. |
| Using raw `Handler` or unchecked casts | Loses compile-time protection and risks runtime errors. | Keep parameterized interfaces explicit; fix the root design. |
| Trying to overload `process(List<String>)` and `process(List<Integer>)` | Name clash due to erasure. | Rename methods or design a generic API with a valid signature. |

## 14. Design Checklist When Multiple Generic Roles Are Needed

When faced with a requirement for a class to handle multiple types, check:

1. **Are you inheriting the same generic interface via two paths?** Trace all relevant `extends`/`implements`, not just the direct list.
2. **Are the final type arguments completely identical?** Two branches both being `Source<String>` can be valid; one `Source<String>` and one `Source<Integer>` is not.
3. **Are they truly two different generic interfaces?** If they are `TextProvider<String>` and `NumberProvider<Integer>`, inspect signatures next to decide whether they can be implemented together.
4. **Does one object really need to play both roles?** If you only need to coordinate two strategies, composition is usually simpler than inheritance.
5. **Is there a natural domain supertype?** When handling common event types, `Handler<Event>` can make more sense than `Handler<Object>` or two parameterizations.
6. **Can the same generic algorithm be used for multiple instances?** `IdentityHandler<T>` can create independent `IdentityHandler<String>` and `IdentityHandler<Integer>` instances.
7. **Is the compiler reporting a name clash due to erasure?** Check overloaded methods and bridge methods; avoid fixing an inheritance error by introducing a signature error.
8. **Are you using raw types, wildcards, or unchecked casts to hide the issue?** These techniques do not change inheritance constraints and can make the API less safe.

## 15. Self-Check

**Question 1.** Why is the following snippet invalid?

```java
interface Consumer<T> {
    void accept(T value);
}
interface TextConsumer extends Consumer<String> { }
interface IntegerConsumer extends Consumer<Integer> { }

// class Both implements TextConsumer, IntegerConsumer { ... }
```

**Question 2.** Do two interfaces `A extends Provider<String>` and `B extends Provider<String>` necessarily conflict when a class `implements A, B`?

**Question 3.** Why do two methods `handle(String)` and `handle(Integer)` in a class not solve the `implements Handler<String>, Handler<Integer>` error?

**Question 4.** If `interface Marker<T> {}` has no methods, why can't `Marker<String>` and `Marker<Integer>` still be combined in one hierarchy?

**Question 5.** Name two alternative design approaches for a class that wants to handle both string messages and integer messages.

**Question 6.** Does `Handler<?>` mean a handler accepts any kind of value? If not, what must be done to call a data-consuming method safely?

**Suggested answers:**

1. `Both` would inherit `Consumer<String>` and `Consumer<Integer>` through two branches — two different parameterizations of the same interface.
2. No. If both branches keep the exact same parameterization and method requirements do not conflict, the class can implement both.
3. Because the rule checking **superinterface relationships** happens independently of whether the class body has matching overloads.
4. Because this is a structural constraint of the Java type hierarchy, not merely whether methods collide after erasure.
5. Composition with two objects `Handler<String>`/`Handler<Integer>`, or a `Handler<Event>` with a common event type. Alternatively, multiple instances of a generic `Handler<T>` class can be used.
6. No. `<?>` hides the type argument so the compiler does not know which values are valid to pass to a method taking `T`; you must preserve or recover the type relationship through a generic API or the right object model.

**Key takeaway:** A generic interface can be used with many different type arguments **across different objects and hierarchies**, yet **a single Java type cannot inherit the same generic interface with two different type arguments**, even through indirect branches. Type erasure explains the JVM method difficulties; the hierarchy consistency rule is even stricter than signature clashes. When you need to handle multiple types, choose **composition, independent interfaces, or a common domain type**, rather than discarding generics checking.