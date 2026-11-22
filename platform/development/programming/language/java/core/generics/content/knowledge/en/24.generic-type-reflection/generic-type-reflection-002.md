# Java Reflection: `Class.cast`, `Class.isInstance`, and `Class.asSubclass`

## Objectives

When working with `Object`-typed data, a dynamically loaded class name, or an API using generics, you sometimes do not know the concrete type at compile time. `java.lang.Class<T>` provides a **type token** representing a type at runtime. Its three key methods — **`cast`**, **`isInstance`**, and **`asSubclass`** — allow you to check or narrow types soundly without scattering unchecked casts.

After this lesson, you will be able to:

- Distinguish the question "does this object belong to the expected type?" from "is this class a subtype of the required class/interface?".
- Use `Class<T>.isInstance(Object)` to check **an instance**, even when the `Class<T>` token is passed from outside.
- Use `Class<T>.cast(Object)` to perform a **runtime check and obtain a value of type `T`**.
- Use `Class.asSubclass(Class<U>)` to check the **inheritance relationship of a `Class` object** and narrow `Class<?>` to `Class<? extends U>`.
- Accurately predict `false`, `null`, and `ClassCastException` in matching and mismatching type cases.
- Understand the limitation of type erasure: `List.class` cannot check whether a `List` currently contains only `String`s.
- Build an adapter that validates a list from a legacy API, or load a concrete implementation using controlled reflection.
- Distinguish these three APIs from `instanceof`, ordinary casts, `Class.isAssignableFrom`, `getClass`, and generic metadata.

**Requirements:** JDK 17 or later. Examples use `javac`, `java`, `javap`, with no external libraries needed. The three complete programs are verified with Java 17 and `-Xlint:all`; small snippets marked "illustrative" should be placed in an appropriate class/method.

## 1. Starting from `Class<T>` — Runtime Type Token

In Java, the expressions:

```java
String.class
Integer.class
Number.class
java.util.List.class
```

return `Class` objects representing the corresponding classes/interfaces. At compile time, for example, `String.class` has type `Class<String>`; `Number.class` has type `Class<Number>`.

A generic method can require an explicit token:

```java
static <T> T readAs(Object source, Class<T> expected) {
    return expected.cast(source);
}
```

Illustrative calls:

```java
String name = readAs("Java", String.class);
Integer age = readAs(18, Integer.class);
```

The compiler infers `T` from the token, so the return type of `readAs` is clear in source code. At runtime, `Class.cast` compares the actual object against the type the token points to. It does not automatically convert an integer to a string or convert arbitrary values into the expected type.

**Distinction:** `Class<T>` is a token for a concrete runtime class/interface/type; it does **not** mean the JVM creates a separate `List<String>` class. For `List<String>`, the ordinary class token is `List.class`, which has no `String` information for the elements.

## 2. Comparison Table of the Three Methods

| API | Receiver | Argument | Return Value | When Incompatible |
| --- | --- | --- | --- | --- |
| `Class<T>.isInstance(Object obj)` | Type token to check against | **Instance** or `null` | `boolean` | `false` |
| `Class<T>.cast(Object obj)` | Target type token | **Instance** or `null` | `T` | `ClassCastException` if non-null and incompatible |
| `Class<T>.asSubclass(Class<U> superclass)` | An existing **`Class`** object | Required supertype class/interface | `Class<? extends U>` | `ClassCastException` if receiver is not a subtype of the argument |

Three examples for the same class name `Dog`:

```java
Object animal = new Dog();
boolean yes = Animal.class.isInstance(animal);
Dog dog = Dog.class.cast(animal);
Class<? extends Animal> type = Dog.class.asSubclass(Animal.class);
```

This is an illustrative snippet assuming `Dog extends Animal` and placed inside an appropriate class/method. The first two statements operate on a **`Dog` object**, while the third operates on the **`Class` object representing `Dog`**.

Tips to tell them apart:

- `isInstance`: **asks** about an object, returns true/false.
- `cast`: **retrieves an object with the desired type**, fails if incompatible.
- `asSubclass`: **asks about the relationship between two class tokens**, returns a more tightly bounded token.

## 3. `Class.isInstance` — Checking an Object Using a Token

Usage:

```java
boolean accepted = String.class.isInstance(value);
```

In this example `value` is an `Object` already in scope. `isInstance` returns `true` when the object is non-`null` and belongs to a class, subclass, or interface compatible with the token.

Example:

```java
Object x = "hello";
System.out.println(String.class.isInstance(x));       // true
System.out.println(CharSequence.class.isInstance(x)); // true
System.out.println(Integer.class.isInstance(x));      // false
```

**`null` is especially important:** `String.class.isInstance(null)` is `false`. This does not mean `null` "is a String of the wrong type"; it means `isInstance` does not consider `null` an instance of any class/interface.

If the token is an **interface**, `isInstance` checks whether the object implements that interface. If the token is an **array class** such as `String[].class`, it checks whether the object belongs to the corresponding array class according to Java's type compatibility rules.

For a **primitive class literal** such as `int.class`, `int.class.isInstance(Integer.valueOf(7))` returns `false`; an `Integer` wrapper is not an instance of primitive `int`. This reflection API does not perform boxing/unboxing to "turn" an object into an instance of a primitive class.

### Compared to `instanceof`

```java
if (value instanceof String) { ... }
```

and:

```java
if (String.class.isInstance(value)) { ... }
```

both answer the object type question in the fixed `String.class` case, but `isInstance` has a strength: **The class token can be a runtime parameter**.

```java
static boolean matches(Object item, Class<?> type) {
    return type.isInstance(item);
}
```

Place this in a class; the caller can pass `String.class`, `Number.class`, or an interface token depending on the situation. Writing `instanceof` usually requires a type name expressible directly in source code; Java 17 cannot generally write `value instanceof T` for a non-reifiable type variable `T`.

**Do not equate type-checking `instanceof` with pattern matching** such as `value instanceof String text`. Pattern matching also binds a typed variable `text` at the source-code level; `Class.isInstance` only returns a boolean, so to use the value as type `T` you need `Class.cast` or corresponding checked logic.

## 4. `Class.cast` — Checking and Obtaining a Value of Type `T`

Conceptual signature:

```java
public T cast(Object obj);
```

With a `Class<T>` token, the method can return a result treated by the compiler as `T`. At runtime, if `obj` is non-`null` and does not belong to a compatible type, the method throws `ClassCastException`.

```java
Object candidate = "Java";
String text = String.class.cast(candidate);
System.out.println(text.toUpperCase()); // JAVA
```

Invalid call:

```java
Object candidate = Integer.valueOf(42);
// String text = String.class.cast(candidate);
// Compiles, but throws ClassCastException at runtime.
```

You should distinguish **compiles** from **succeeds at runtime**. `Class.cast` does not turn an `Integer` value into a `String`; it verifies whether using it as type `T` is valid.

### What does `cast(null)` return?

```java
String missing = String.class.cast(null);
System.out.println(missing == null); // true
```

`Class.cast(null)` **returns `null`**, and does not throw `ClassCastException` on its own. Unlike `isInstance(null)` which returns `false`, casting a `null` reference to a reference type is permitted.

If your API **does not accept `null`**, write an explicit policy, for example checking `Objects.requireNonNull` or `isInstance` and throwing a contextual exception. Do not assume that merely calling `Class.cast` rejects `null` from inputs.

### `Class.cast` vs. Ordinary Cast

```java
String a = (String) candidate;
String b = String.class.cast(candidate);
```

When the token is fixed, both approaches can throw `ClassCastException` if the object has the wrong type. However, `Class.cast` is suitable when the target type comes from a **runtime `Class<T>` variable**, whereas a direct cast like `(T) candidate` inside a generic method can be an **unchecked cast** or only cast to the erased upper bound after type erasure.

For example:

```java
static <T> T checked(Object input, Class<T> expected) {
    return expected.cast(input);
}
```

This lets the compiler know the result is `T` and performs the check using the actual token passed in.

## 5. `Class.asSubclass` — Narrowing a **Class Token**, Not an Instance

This is the method most easily misread.

Signature:

```java
public <U> Class<? extends U> asSubclass(Class<U> clazz);
```

Suppose you currently have:

```java
Class<?> discovered = Dog.class;
```

You do not yet know how the discovered class relates to `Animal`. You can check:

```java
Class<? extends Animal> type =
        discovered.asSubclass(Animal.class);
```

If `discovered` represents `Dog` and `Dog extends Animal`, the call succeeds. The returned value still represents the same `Dog` class, but its **compile-time type is narrowed** to `Class<? extends Animal>`.

If:

```java
Class<?> discovered = String.class;
// Class<? extends Animal> type = discovered.asSubclass(Animal.class);
```

then the call throws `ClassCastException`, because `String` is not a subtype of `Animal`.

### What Exactly Does `asSubclass` Check?

It checks **whether the class represented by the receiver can be viewed as a subclass/subtype of the type represented by the argument**. The target type can be a class or an interface. For example, for a class `Dog implements Pet`:

```java
Class<? extends Pet> token = Dog.class.asSubclass(Pet.class);
```

is valid, even though `Pet` is an interface. In terms of subtyping checks, the target class itself as receiver is also valid: `Animal.class.asSubclass(Animal.class)` succeeds.

**Do not infer from the name `asSubclass` that the method creates a new subclass.** It does not build a class, does not alter the inheritance hierarchy, does not create an object, and does not invoke a constructor. It returns a `Class` object representing the existing class, under a generic type guaranteeing the subtype bound.

### `Class<?>` and `Class<? extends Animal>`

- `Class<?>`: a class token not bound to a specific parent type.
- `Class<? extends Animal>`: a token representing a class that can be used as `Animal` or a subclass of it.

After the `asSubclass` step, an API can work with verified class tokens instead of using unchecked casts:

```java
Class<? extends Animal> safeType =
        unknownClass.asSubclass(Animal.class);
```

The next section illustrates this pattern with a plugin/service interface.

## 6. Program A — Comparing All Three APIs on the Same Type Model

Create the file **`ClassReflectionDemo.java`**:

```java
import java.util.List;

public class ClassReflectionDemo {
    interface Pet {
        String sound();
    }

    static class Animal {}

    static final class Dog extends Animal implements Pet {
        @Override
        public String sound() {
            return "woof";
        }
    }

    static final class Cat extends Animal {}

    public static void main(String[] args) {
        Object candidate = new Dog();

        System.out.println("animal instance: "
                + Animal.class.isInstance(candidate));
        System.out.println("dog instance: "
                + Dog.class.isInstance(candidate));
        System.out.println("cat instance: "
                + Cat.class.isInstance(candidate));
        System.out.println("null instance: "
                + Dog.class.isInstance(null));
        System.out.println("interface instance: "
                + Pet.class.isInstance(candidate));
        System.out.println("primitive instance: "
                + int.class.isInstance(Integer.valueOf(7)));
        System.out.println("array instance: "
                + String[].class.isInstance(new String[2]));

        Dog dog = Dog.class.cast(candidate);
        System.out.println("cast result: " + dog.sound());
        System.out.println("cast null: "
                + (Dog.class.cast(null) == null));

        try {
            Cat.class.cast(candidate);
        } catch (ClassCastException ex) {
            System.out.println("bad cast: "
                    + ex.getClass().getSimpleName());
        }

        Class<?> runtime = candidate.getClass();
        Class<? extends Animal> subtype =
                runtime.asSubclass(Animal.class);
        System.out.println("subclass: "
                + subtype.getSimpleName());

        Class<? extends Pet> petSubtype =
                runtime.asSubclass(Pet.class);
        System.out.println("interface subclass: "
                + petSubtype.getSimpleName());

        try {
            String.class.asSubclass(Animal.class);
        } catch (ClassCastException ex) {
            System.out.println("bad subclass: "
                    + ex.getClass().getSimpleName());
        }

        List<Integer> numbers = List.of(1, 2);
        Object collection = numbers;
        System.out.println("list instance: "
                + List.class.isInstance(collection));
        System.out.println("list cast: "
                + List.class.cast(collection).get(0));
    }
}
```

Compile and run:

```bash
javac -Xlint:all ClassReflectionDemo.java
java ClassReflectionDemo
```

**Verified stdout:**

```text
animal instance: true
dog instance: true
cat instance: false
null instance: false
interface instance: true
primitive instance: false
array instance: true
cast result: woof
cast null: true
bad cast: ClassCastException
subclass: Dog
interface subclass: Dog
bad subclass: ClassCastException
list instance: true
list cast: 1
```

The program compiles cleanly with no warnings under `-Xlint:all`.

### Analyzing the Instance Checks

`candidate` points to a `Dog` object.

- `Animal.class.isInstance(candidate)` returns `true` because `Dog extends Animal`.
- `Dog.class.isInstance(candidate)` returns `true` because it is a `Dog` instance.
- `Cat.class.isInstance(candidate)` returns `false`: both `Dog` and `Cat` are subclasses of `Animal`, but neither is a subtype of the other.
- `Pet.class.isInstance(candidate)` returns `true` because `Dog implements Pet`.
- `Dog.class.isInstance(null)` returns `false`.
- `int.class.isInstance(Integer.valueOf(7))` returns `false`; it does not convert a wrapper into a primitive instance.
- `String[].class.isInstance(new String[2])` returns `true` because the actual object is a `String[]` array.

`isInstance` calls **do not modify data**, nor do they make the compiler treat the variable `candidate: Object` as a `Dog`. They only return true/false information.

### Analyzing the Cast Checks

`Dog.class.cast(candidate)` returns the same `Dog` object to be used as type `Dog`; then `sound()` yields `woof`.

`Dog.class.cast(null)` returns `null`.

`Cat.class.cast(candidate)` fails with `ClassCastException` even though both `Cat` and `Dog` are `Animal`s. Casting does not change the runtime class of an object.

### Analyzing `asSubclass`

`candidate.getClass()` returns the runtime token for `Dog`. Since `Dog` is a subtype of `Animal` **and** implements `Pet`, both `asSubclass` calls succeed.

`String.class.asSubclass(Animal.class)` fails because the subtype relationship does not hold. The failure here concerns the **relationship between two `Class` objects**, unlike `Cat.class.cast(candidate)` which concerns the **instance `candidate`**.

## 7. How Does `Class.isAssignableFrom` Relate to `asSubclass`?

Another reflective method on `Class` is:

```java
boolean parentAcceptsChild =
        Animal.class.isAssignableFrom(Dog.class);
```

The result is `true`: a variable of type `Animal` can hold a reference to a `Dog`.

The direction rule is very important:

```java
Animal.class.isAssignableFrom(Dog.class) // true
Dog.class.isAssignableFrom(Animal.class) // false
```

These snippets are illustrative expressions placed inside a method where `Animal`/`Dog` are declared.

Comparing with `asSubclass`:

```java
Class<?> found = Dog.class;
Class<? extends Animal> typed =
        found.asSubclass(Animal.class);
```

You can think of the checking step as **`Animal.class.isAssignableFrom(found)`**. If it succeeds, `asSubclass` also **provides a type-bounded result** `Class<? extends Animal>`, whereas `isAssignableFrom` only returns a boolean.

| Method | Receiver | Parameter | Return Value |
| --- | --- | --- | --- |
| `Animal.class.isAssignableFrom(Dog.class)` | Expected parent class | Assignable child class | `true` |
| `Dog.class.asSubclass(Animal.class)` | Actual child class | Required parent class/interface | `Class<? extends Animal>` token |
| `Animal.class.isInstance(new Dog())` | Expected parent class | **Object** | `true` |

Reversing the direction is a common reflection bug. Ask yourself: "A variable of which type needs to receive an object of which class?" If an `Animal` variable can hold a `Dog`, then `Animal.class.isAssignableFrom(Dog.class)` is true.

## 8. Generic Erasure: These Checks Do **Not** Validate Nested Type Arguments

Example:

```java
List<Integer> integers = List.of(1, 2);
Object object = integers;

System.out.println(List.class.isInstance(object)); // true
List rawView = List.class.cast(object);
```

`List.class` only speaks about the **`List` interface at runtime**. It does not separately store the `Integer` or `String` type argument of the instance.

Therefore, it is a design mistake to think that:

```java
// INVALID in Java:
// Class<List<String>> token = List<String>.class;
```

There is no class literal `List<String>.class` corresponding to a separate runtime class. Both a `List<Integer>` object and a `List<String>` object satisfy `List.class.isInstance(...)`.

In particular, **do not** perform an unchecked cast from `List.class.cast(rawObject)` to `List<String>` and treat that as validation. `Class.cast` here only checks that the object implements `List`; it does not iterate over the elements.

If you need a safe `List<String>` result from an unknown source, do the following:

1. Verify that the source is a `List` at runtime.
2. Iterate through the elements.
3. Check that each element belongs to `String.class` or apply an explicit conversion policy.
4. Build a new typed list, avoiding keeping a raw mutable reference that could continue mutating the data.

The complete pattern in the next section uses a `Class<T>` token to generalize the checking step.

## 9. Program B — Validating Data from a Legacy API Using `Class<T>`

Create the file **`TypedBoundaryDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class TypedBoundaryDemo {
    static <T> T requireNonNullType(Object value, Class<T> expected) {
        Objects.requireNonNull(expected, "expected");
        if (!expected.isInstance(value)) {
            throw new IllegalArgumentException(
                    "Expected " + expected.getSimpleName());
        }
        return expected.cast(value);
    }

    static <T> List<T> checkedCopy(List<?> source,
                                   Class<T> expected) {
        Objects.requireNonNull(source, "source");
        Objects.requireNonNull(expected, "expected");

        List<T> result = new ArrayList<>();
        for (int i = 0; i < source.size(); i++) {
            Object value = source.get(i);
            if (!expected.isInstance(value)) {
                throw new IllegalArgumentException(
                        "Invalid element at " + i);
            }
            result.add(expected.cast(value));
        }
        return List.copyOf(result);
    }

    public static void main(String[] args) {
        Object input = "Java";
        System.out.println("scalar: "
                + requireNonNullType(input, String.class));

        List<?> oldData = List.of("Lan", "Minh");
        System.out.println("checked: "
                + checkedCopy(oldData, String.class));

        try {
            checkedCopy(List.of("Lan", 42), String.class);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected: " + ex.getMessage());
        }

        System.out.println("class cast null: "
                + (String.class.cast(null) == null));
        try {
            requireNonNullType(null, String.class);
        } catch (IllegalArgumentException ex) {
            System.out.println("null rejected: "
                    + ex.getMessage());
        }

        List<Integer> integers = List.of(10);
        System.out.println("list token permits integers: "
                + List.class.isInstance(integers));
        System.out.println("list class cast first: "
                + List.class.cast(integers).get(0));
    }
}
```

Compile and run:

```bash
javac -Xlint:all TypedBoundaryDemo.java
java TypedBoundaryDemo
```

**Verified stdout:**

```text
scalar: Java
checked: [Lan, Minh]
rejected: Invalid element at 1
class cast null: true
null rejected: Expected String
list token permits integers: true
list class cast first: 10
```

There are no `rawtypes` or `unchecked` warnings in this program under `-Xlint:all`.

### Why Does `requireNonNullType` Combine Two Methods?

```java
if (!expected.isInstance(value)) {
    throw new IllegalArgumentException(...);
}
return expected.cast(value);
```

`isInstance` enforces a **business data policy**—here rejecting `null` or wrong-typed values—and throws an `IllegalArgumentException` with an API-controlled message.

Then `cast` returns `T` under a runtime check matching the token. No unchecked cast `(T)value` is needed.

If an API wants to allow `null`, it can call `expected.cast(value)` directly with a non-`null` token, and clearly document in its contract that the result may be `null`. The choice regarding `null` is an **API policy**, not a hidden limitation of `Class.cast`.

### `checkedCopy` Solves the Limitation of `List.class`

`checkedCopy(List<?> source, Class<T> expected)` accepts a **list whose element type is unknown**. It reads each element as `Object`, checks `expected.isInstance`, and adds `expected.cast(value)` to an `ArrayList<T>`.

For `List.of("Lan","Minh")`, all elements are `String`, so it returns a valid `List<String>`.

For `List.of("Lan",42)`, the element at index 1 is an `Integer`, so the adapter **rejects it right at the boundary**, rather than letting a `ClassCastException` happen later when business code reads the value.

`List.copyOf(result)` returns a list that cannot be modified via ordinary list operations and does not retain the original mutable structure. However, for `T` elements with mutable state, copying the list does **not** automatically make them deeply immutable.

### `List.class` Does Not Know What Is Inside

The last two lines intentionally illustrate:

```text
list token permits integers: true
list class cast first: 10
```

`List<Integer>` is still a runtime `List`. `List.class.cast(integers)` succeeds, yet it only returns a `List` view of that object and does not validate that it matches `List<String>`. Therefore, an adapter must check **each element** when it needs to provide a typed collection.

## 10. `Class.asSubclass` in Implementation Loading and Plugin Mechanisms

A typical use case for `asSubclass` is **loading a class by name**, then checking whether it implements the required interface.

A typical processing pipeline:

```text
Class name provided by config
                |
                v
        Class.forName(name)
                |
                v
             Class<?>
                |
                v
   asSubclass(Service.class)
                |
          subtype check
          /             \
       valid          wrong type
        |                  |
        v                  v
 Class<? extends      ClassCastException
     Service>
        |
        v
getDeclaredConstructor()
    .newInstance()
        |
        v
   Service instance
```

Notice there are **two independent concerns**:

1. Does the found class implement `Service`? — `asSubclass` solves this.
2. Can the class be validly instantiated? — this also depends on constructors, access, abstract/interface status, exceptions from the constructor, access permissions, and runtime constraints.

`asSubclass` **does not check** whether a constructor exists or is public, nor does it create an object. It only checks the subtype relationship so the result has an appropriate `Class<? extends Service>` type.

## 11. Program C — Loading a Service Class Type-Safely

Create the file **`PluginServiceDemo.java`**:

```java
public class PluginServiceDemo {
    public interface Service {
        String id();
    }

    public static class FastService implements Service {
        public FastService() {}

        @Override
        public String id() {
            return "fast";
        }
    }

    public static class NotAService {
        public NotAService() {}
    }

    static Service load(String className)
            throws ReflectiveOperationException {
        Class<?> unknown = Class.forName(className);
        Class<? extends Service> implementation =
                unknown.asSubclass(Service.class);

        return implementation
                .getDeclaredConstructor()
                .newInstance();
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Service service = load(FastService.class.getName());
        System.out.println("loaded: " + service.id());

        try {
            load(NotAService.class.getName());
        } catch (ClassCastException ex) {
            System.out.println("wrong plugin type: "
                    + ex.getClass().getSimpleName());
        }

        try {
            load("not.existing.Plugin");
        } catch (ClassNotFoundException ex) {
            System.out.println("missing plugin: "
                    + ex.getClass().getSimpleName());
        }
    }
}
```

Compile and run:

```bash
javac -Xlint:all PluginServiceDemo.java
java PluginServiceDemo
```

**Verified stdout:**

```text
loaded: fast
wrong plugin type: ClassCastException
missing plugin: ClassNotFoundException
```

The program runs successfully with no compiler warnings under `-Xlint:all`.

### Analyzing Each Scenario

**Loading `FastService`:** `Class.forName` returns `Class<?>`, meaning the actual class is known but without a generic constraint on the interface. `asSubclass(Service.class)` verifies that it implements `Service`. `getDeclaredConstructor().newInstance()` creates an instance via the public no-arg constructor in the example.

**Loading `NotAService`:** the class name exists, so `Class.forName` succeeds. However, the class does not implement `Service`, so `asSubclass` throws `ClassCastException`. The problem is a **wrong type relationship**, not a missing class.

**Loading a non-existent name:** `Class.forName` throws `ClassNotFoundException` before `asSubclass` is ever called. This is a class-loading failure, distinct from a subtype-check failure.

### Practical Notes for Real Applications

- If the class is abstract/an interface, lacks a matching constructor, or the constructor throws an error, the instantiation step can still fail.
- `newInstance()` on `Constructor` can throw reflective exceptions such as `InstantiationException`, `IllegalAccessException`, `InvocationTargetException`, or `NoSuchMethodException`; handle them according to your actual contract.
- Java module access rules can restrict reflection on members that have not been opened.
- Do not load/execute **arbitrary class names from untrusted sources** merely because `asSubclass` succeeds. Implementing `Service` does not mean that code is safe to run. In production, use a registry/allowlist and a separate trust process.

The illustrative example only uses two nested classes in your own program; it does not implement an external plugin installation mechanism.

## 12. Summary of the Three Forms of "Type Checking" Across a Data Flow

A system can have class names, objects, and untyped collections all together:

```text
CONFIG: "com.example.FastService"
        |
        +--> Class.forName(...) -> Class<?>
                |
                +--> asSubclass(Service.class)
                |        |
                |        +--> Class<? extends Service>
                |
                +--> Constructor.newInstance()
                         |
                         +--> Actual Object

DATA: Object input
        |
        +--> Service.class.isInstance(input) -> boolean
        |
        +--> Service.class.cast(input)       -> Service

COLLECTION: List<?> data
        |
        +--> iterate each Object
                |
                +--> type.isInstance(element)
                +--> type.cast(element)
                |
                +--> New verified List<T>
```

Depending on the data point, choose the right tool:

- If you **already have an object** and need to ask whether it belongs to the target type: `isInstance`.
- If you **already have an object** and want to bring the value to generic type `T`: `cast`.
- If you **only have a `Class<?>`** and want to guarantee it is a subtype of the required interface/class: `asSubclass`.
- If you **have a collection from an uncertain source**, these three APIs alone cannot recover `List<String>` past erasure; check each element using a class token.

## 13. Difference Between a `ClassCastException` Failure and a `false` Result

The same `Dog` object is not a `Cat`:

```java
Object obj = new Dog();
boolean check = Cat.class.isInstance(obj); // false
// Cat cat = Cat.class.cast(obj);           // ClassCastException
```

`isInstance` suits **conditional branches**, input probing, and soft validation. `cast` suits cases where the target type is a **mandatory precondition** and a type mismatch must abort the execution flow.

Similarly for class tokens:

```java
Class<?> found = String.class;
// Class<? extends Animal> t = found.asSubclass(Animal.class);
// ClassCastException because String does not extend Animal.
```

If you only need to ask without throwing an exception, you can use:

```java
boolean ok = Animal.class.isAssignableFrom(found); // false
```

So deciding between a boolean and an exception is a **decision about API design and error flow**, not about which method is "stronger" in the sense of fixing data automatically.

### `null` Cases That Must Be Specified

- `Animal.class.isInstance(null)` → `false`.
- `Animal.class.cast(null)` → `null`.
- Calling an instance method on a variable `Class<?> token = null` (for example `token.cast(obj)`) → `NullPointerException` due to a null receiver.
- The `Class<U>` argument to `asSubclass` must be a valid token; APIs should require non-null rather than treating null as a supertype.
- `Class.forName(null)` is likewise not a valid class-lookup request; configuration validation is needed before loading.

If the contract requires a **present value of the right type**, combine `Objects.requireNonNull` and `Class.cast`, or apply `isInstance` and report a contextual error like `TypedBoundaryDemo`.

## 14. Special Types: Interface, Array, Primitive

Not only ordinary classes can be used as tokens.

### Interface Token

```java
CharSequence.class.isInstance(new StringBuilder("A"))
```

returns `true` because `StringBuilder implements CharSequence`.

With `asSubclass`, a class implementing an interface also satisfies the check:

```java
StringBuilder.class.asSubclass(CharSequence.class)
```

yielding `Class<? extends CharSequence>` representing `StringBuilder`.

### Array Token

```java
String[].class.isInstance(new String[]{"A", "B"})
```

returns `true`; array classes have runtime identity and a component type. Still, do not use `List.class` as a substitute token for the nested parameterized type `List<String>`.

### Primitive Token

```java
int.class.isInstance(Integer.valueOf(7))
```

returns `false`: `Integer` is not a runtime instance of primitive `int`. When checking an object containing a boxed integer value, use `Integer.class` instead of `int.class`. Java boxing/unboxing does not turn `Class.isInstance` into an arbitrary conversion operation.

## 15. `Class.cast` Is Not Data Conversion

A familiar misconception:

```java
Object number = Integer.valueOf(17);
// String text = String.class.cast(number); // Runtime error.
```

`Class.cast` **checks type compatibility**; it does not turn `17` into `"17"`. If you genuinely want to convert a number to text, use a proper conversion API:

```java
String text = String.valueOf(number); // "17"
```

Likewise, `Class.cast` does not parse a string `"17"` into an `Integer`; that is the job of `Integer.parseInt` or an appropriate parser.

Distinguish two questions:

- "Is this object **already** of type `T`?" → `Class.isInstance`/`Class.cast`.
- "Do I want to **transform** a value from data domain A to B?" → conversion/parser/mapper.

Conflating them causes reflection APIs to throw unexpected `ClassCastException`s that are hard to debug.

## 16. Type Reflection and Erasure in Bytecode

Consider the method in `TypedBoundaryDemo`:

```java
static <T> T requireNonNullType(Object value, Class<T> expected) {
    Objects.requireNonNull(expected, "expected");
    if (!expected.isInstance(value)) {
        throw new IllegalArgumentException(
                "Expected " + expected.getSimpleName());
    }
    return expected.cast(value);
}
```

Run after compiling:

```bash
javap -p -s TypedBoundaryDemo
```

Part of the verified output:

```text
static <T> T requireNonNullType(java.lang.Object, java.lang.Class<T>);
  descriptor: (Ljava/lang/Object;Ljava/lang/Class;)Ljava/lang/Object;

static <T> java.util.List<T> checkedCopy(
    java.util.List<?>, java.lang.Class<T>);
  descriptor: (Ljava/util/List;Ljava/lang/Class;)Ljava/util/List;
```

The generic signature metadata shown by `javap` contains `T`, `List<T>`, and `Class<T>`, but the **JVM descriptors** use `Object`, `List`, and `Class` after erasure.

Thanks to the explicitly passed `Class<T>` token, the method body **can still check the runtime class** of the object, even though generic method `<T>` is erased in the descriptor. This is a way to **actively supply runtime type information to an API**, rather than expecting `T` to be "recovered" from erasure on its own.

When typed code assigns the result of `requireNonNullType(..., String.class)` to a `String` variable, the compiler may also emit a cast at the call site to fulfill the source contract. The token and compiler-inserted casts support type safety; they do not generate a separate specialized class for `T=String`.

## 17. Do Not Use `getClass()` to Guess Arbitrary Generic Arguments

Example:

```java
List<String> names = new java.util.ArrayList<>();
List<Integer> counts = new java.util.ArrayList<>();
boolean same = names.getClass() == counts.getClass(); // true
```

The two variables have different generic arguments yet share the same runtime class `ArrayList`. Calling `getClass()` on a collection object is not enough to know whether `String` or `Integer` was declared as the type argument in source code.

Similarly, `Class<List>` based on `List.class` only checks whether an object is a `List`, **not whether it is `List<String>`**. If code must validate a complex value like `Map<String,Integer>`, it must use an appropriate schema/metadata and check specific keys/values; a `Class<Map>` token is not enough.

Reflection can read generic metadata on **field, method, and superclass declarations** via `Type`/`ParameterizedType`, but that is information about the **declaration site**, not an arbitrary decoder of type arguments for every runtime object.

Therefore, even when using `Class.cast`, `isInstance`, and `asSubclass`, keep the boundary clear: they operate on runtime classes/interfaces, not as an automatic checker for every erased generic type argument.

## 18. Which API Should You Choose in Practice?

| Need | Preferred API | Explanation |
| --- | --- | --- |
| Ask whether an object is a subtype/implementation | `Class.isInstance` | Returns boolean, works with a runtime token |
| Require an object to belong to target type `T` | `Class.cast` | Returns typed value or throws `ClassCastException` |
| Check whether two class tokens have a subtype relationship | `Class.isAssignableFrom` | Returns boolean, pay attention to receiver direction |
| Narrow `Class<?>` into a checked `Class<? extends U>` | `Class.asSubclass` | Runtime subtype check and narrowed generic token |
| Look up a class by name | `Class.forName` | Loads/looks up class; does not guarantee interface implementation |
| Create an instance via reflection | `getDeclaredConstructor().newInstance()` | Needs a valid class, constructor, and access permission |
| Validate `List<String>` from dynamic data | Iterate elements with `String.class.isInstance/cast` | `List.class` token is insufficient due to erasure |
| Convert `Integer` to `String` | Conversion API such as `String.valueOf` | `Class.cast` does not convert data |
| Enforce type correctness at compile time | Generic types `List<T>`, `Function<T,R>` | Avoids unchecked casts before execution |

Each tool addresses a different layer. A clear design usually combines them at system boundaries rather than trying to use one method to validate every data structure.

## 19. Common Mistakes to Avoid

**Mistake 1 — Thinking `asSubclass` casts an object to a subclass.** It takes and returns a **`Class` object**, not a domain `Object` like `Dog`. If you already have an object, use `isInstance` or `cast`.

**Mistake 2 — Thinking `isInstance` returns a typed object.** It only returns `boolean`. If you need `T`, use `cast` after checking or let `cast` throw on a type mismatch.

**Mistake 3 — Thinking `cast(null)` rejects null automatically.** `Class.cast(null)` returns `null`. If null violates the contract, check it explicitly.

**Mistake 4 — Reversing the direction of `isAssignableFrom`.** `Animal.class.isAssignableFrom(Dog.class)` is right, not the reverse. In `asSubclass`, the receiver is usually the discovered class, and the argument is the required parent type.

**Mistake 5 — Thinking `List.class.cast(list)` proves the list has `String` elements.** Runtime only checks that it is a `List`. Validating generic elements requires per-element/schema checking.

**Mistake 6 — Writing an unchecked cast `(Class<? extends Service>) unknown` without verification.** This can create a false sense of type safety. `unknown.asSubclass(Service.class)` expresses an actual runtime subtype check.

**Mistake 7 — Treating `Class.cast` as a parser or converter.** Casting does not turn `Integer` into `String` or repair incompatible values.

**Mistake 8 — Assuming a class implementing an interface can always be instantiated.** `asSubclass` does not check constructors, access, abstract status, or constructor logic; instantiation needs separate handling.

**Mistake 9 — Loading arbitrary classes unchecked from untrusted configuration.** Checking subtyping does not make code inside the class safe; an allowlist or trust mechanism is required.

**Mistake 10 — Mistakenly thinking `getClass()` carries the `String` type argument of `List<String>`.** Generic erasure prevents `getClass()` from inferring arbitrary type arguments from a collection object.

**Mistake 11 — Thinking `isInstance` treats primitives like wrappers via boxing.** `int.class.isInstance(Integer.valueOf(1))` is still `false`; use the wrapper token when checking objects.

**Mistake 12 — Ignoring null and invalid-input policies.** One API returns `false`, one returns `null`, and one throws `ClassCastException`; choose the right handling rather than merely switching syntax.

## 20. Exercises to Check Understanding

### Exercise 1 — Predict `isInstance` Results

Given:

```java
Object value = new StringBuilder("x");
boolean a = CharSequence.class.isInstance(value);
boolean b = String.class.isInstance(value);
boolean c = Object.class.isInstance(null);
```

**Answer:** `a=true`, `b=false`, `c=false`. `StringBuilder` implements `CharSequence` but is not a `String`; `null` is not an instance of any class.

### Exercise 2 — Predict `Class.cast`

```java
Object value = Integer.valueOf(9);
Number n = Number.class.cast(value);
// String s = String.class.cast(value);
```

**Answer:** casting to `Number` succeeds, whereas casting to `String` compiles if uncommented/used but throws `ClassCastException` at runtime.

### Exercise 3 — Does `asSubclass` Modify an Object?

```java
Class<?> unknown = Integer.class;
Class<? extends Number> numberType =
        unknown.asSubclass(Number.class);
```

**Answer:** succeeds because `Integer extends Number`. No `Integer` object is created and no class is modified; it simply returns the token with the same runtime class under type `Class<? extends Number>`.

### Exercise 4 — Reversing Subtype Direction

```java
boolean a = Number.class.isAssignableFrom(Integer.class);
boolean b = Integer.class.isAssignableFrom(Number.class);
```

**Answer:** `a=true`, `b=false`. A `Number` variable can hold an `Integer`, whereas an `Integer` variable cannot hold every `Number`.

### Exercise 5 — `null` with Both APIs

```java
boolean a = String.class.isInstance(null);
String b = String.class.cast(null);
```

**Answer:** `a=false`, `b=null`. To reject null from inputs, add an explicit API rule.

### Exercise 6 — Interface Plugin

You have `Class<?> loaded` returned by `Class.forName`, want to know whether the class implements `Runnable`, and instantiate it only if valid.

**Guided Answer:** `Class<? extends Runnable> type = loaded.asSubclass(Runnable.class)`. If the check passes, proceed to verify the constructor and access permissions before calling `newInstance`; otherwise, `ClassCastException` indicates a wrong type relationship. Do not use a direct unchecked cast from `Class<?>`.

### Exercise 7 — Generic Collection from a Legacy API

`List.class.isInstance(List.of(1,2))` returns `true`. Can you conclude the object is a `List<String>`?

**Answer:** no. `List.class` does not contain the `String` type argument. To obtain a safe `List<String>`, check each element and build a typed copy like `checkedCopy`.

### Exercise 8 — Choosing Between Boolean and Exception

A validation form needs to check whether an object is a `LocalDate` and produce a custom message "Invalid input date". Should you use `Class.cast` directly or `isInstance` and then report an error?

**Guided Answer:** `LocalDate.class.isInstance(value)` is suitable for deciding the branch and creating the domain message; afterwards you can use `LocalDate.class.cast(value)` to obtain the typed value. Direct `cast` makes sense when a type mismatch is considered a programming bug requiring `ClassCastException`.

### Exercise 9 — Reading a Generic Method After Erasure

A method `<T> T requireNonNullType(Object, Class<T>)` has a JVM descriptor returning `Object`. Why does source code still safely return `T` when using `expected.cast(value)`?

**Answer:** the compiler checks the relationship between the `Class<T>` token and the generic return type `T`, while `Class.cast` performs the runtime check using the passed token. The erased descriptor does not remove this check and does not create a specialized runtime class for `T`.

### Exercise 10 — Correcting a False Statement

"A successful `asSubclass(Service.class)` proves the plugin is safe to execute and has a public no-arg constructor."

**Answer:** false. It only proves that the class implements/extends `Service` according to runtime subtyping. Constructors, access, instantiability, and code trustworthiness are separate checks.

## 21. Checklist Before Using a Java Reflection Type Token

- [ ] Am I checking an **instance** or a **class token**?
- [ ] If I only need true/false on an object, did I choose `isInstance`?
- [ ] If I need an object typed as `T`, did I choose `cast` and define an error policy?
- [ ] If I need a `Class<? extends U>` token, did I use `asSubclass(U.class)` instead of an unchecked cast?
- [ ] Is `null` handled according to the contract?
- [ ] Did I distinguish class/interface subtyping from erased generic type arguments?
- [ ] If the source is a collection, did I check each element against the schema rather than only `List.class`?
- [ ] When loading classes dynamically, did I separate handling for `ClassNotFoundException`, `ClassCastException`, and constructor errors?
- [ ] Is there an allowlist of permitted classes when input is untrusted?
- [ ] Have compile-time examples and runtime outputs been tested with both valid and invalid data?
- [ ] Have raw types, unverified unchecked casts, and unsafe conversions been avoided?

## Conclusion

The three methods solve three related but distinct reflection needs:

- **`Class.isInstance(Object)`** checks whether an object is compatible with a runtime token; returns `true` or `false`, with `null` yielding `false`.
- **`Class.cast(Object)`** checks an object and returns a typed value `T`; a non-null type mismatch throws `ClassCastException`, whereas a `null` input returns `null`.
- **`Class.asSubclass(Class<U>)`** checks the subtype relationship of the `Class` object itself, returning `Class<? extends U>` or throwing `ClassCastException`. It does not instantiate objects.

When paired with a **`Class<T>` token**, generics and reflection help build boundary APIs that are both flexible and runtime-checked. However, because of **type erasure**, these three methods cannot automatically check `List<String>` at the element level. Keep promises within their true scope, use adapters to validate nested data, and clearly separate type checking from conversion.
