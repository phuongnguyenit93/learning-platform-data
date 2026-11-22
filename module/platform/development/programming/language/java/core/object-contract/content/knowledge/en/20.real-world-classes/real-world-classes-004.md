# Class Literal `Type.class` and Comparison with `getClass()` in Java

## 1. Lesson Objectives

When working with an object in Java, there are at least two type concepts to distinguish:

- **Declared/expression type** (*static type*): the type the compiler knows when analyzing code, such as a variable `Animal animal` declared as `Animal`.
- **Actual class at runtime** (*runtime class*): the concrete class of the object that the variable references, such as an object created by `new Dog()`.

Java allows a variable to reference an instance of a subclass or a class implementing an interface. Thus, the declared type **does not necessarily** match the actual class. The two ways of obtaining a `Class` object express two different questions:

- `Animal.class`: the `Class<Animal>` object representing the `Animal` type explicitly named in **source code**.
- `animal.getClass()`: the `Class<?>` object representing the **actual class** of the instance `animal` points to, determined at runtime.

Within Java Core – Object Contract, understanding this difference helps with type checks, reflection, and avoiding confusion when designing `equals()` for classes with inheritance, proxies, or multiple implementations.

After this lesson, you will be able to explain and apply `Type.class`, `obj.getClass()`, `instanceof`, `Class.isInstance`, and `Class.isAssignableFrom`; handle `null`; understand `Class` for primitives/arrays/interfaces; and choose the comparison style suited to business semantics.

## 2. What Actually Is `Type.class`?

A **class literal** is an expression with the syntax `TypeName.class`. For example:

```java
Class<String> stringType = String.class;
Class<Integer> boxedType = Integer.class;
Class<?> arrayType = String[].class;
Class<?> primitiveType = int.class;
Class<?> noValueType = void.class;
```

These are illustrative statements placed inside a method or suitable initializer block, not a standalone runnable Java file.

In each case, the expression returns a `java.lang.Class` object representing the named type. It **does not create an instance** of that type:

- `String.class` does not create a new `String`.
- `Dog.class` does not invoke the `Dog` constructor.
- `SomeInterface.class` represents the interface, even though an interface cannot be instantiated with `new SomeInterface()`.
- `int.class` represents the primitive type `int`, not `Integer.class`.
- `String[].class` represents the runtime class of an array of `String` elements, distinct from `String.class`.

For an ordinary class defined in a given class loader, repeated evaluations of `T.class` return the same `Class` object for that definition. However, **having the same class name does not guarantee it is the same runtime class** if two different class loaders load two definitions: a class's identity is tied to both its binary name and its defining class loader.

`Class` is metadata representing a type, not a business instance of that type. `String.class` is an object of type `Class<String>`, not a `String`.

### Does a Class Literal Proactively Initialize the Class?

Evaluating a class literal such as `T.class` does not itself trigger **class initialization** of `T` merely because that literal was referenced. This is a notable difference from other proactive actions such as calling a static method, reading a non-compile-time-constant static field, or calling the single-argument `Class.forName(String)`, which typically require loading and initializing the class.

However, "does not initialize automatically" does not mean the JVM avoids resolving/loading type information to obtain the `Class` object. **Loading, linking, and initialization** are distinct phases in the JVM lifecycle; do not use a class literal as a technique that promises "not to touch the class loader".

## 3. How Does `obj.getClass()` Obtain the Actual Class?

`getClass()` is the `public final native Class<?> getClass()` method of `java.lang.Object` at the API level; every Java object has this method and subclasses cannot override it. The exact return type in the Java API's generic declaration is bounded by the receiver's type; in practical usage you can write `Class<?>` if you only need general metadata.

Example:

```java
class Animal {}
class Dog extends Animal {}

Animal animal = new Dog();
System.out.println(Animal.class == animal.getClass()); // false
System.out.println(Dog.class == animal.getClass());    // true
```

This is an illustration placed where class declarations and statements in a method are allowed. The **declared type** of variable `animal` is `Animal`. The **object currently held** is a `Dog`. When `animal.getClass()` is called, the JVM returns `Dog`'s metadata because that is the object's actual class.

You can write:

```java
Object any = "hello";
Class<?> runtimeType = any.getClass(); // String.class
```

You do not need to cast `any` to `String` to know the object's runtime class. However, `getClass()` **requires a non-null object**. If `any == null`, calling `any.getClass()` throws `NullPointerException`. By contrast, `String.class` needs no instance variable at all and evaluates normally.

### Comparison with `getClass().getName()`

- `obj.getClass()` returns the `Class` object for checking identity/metadata.
- `obj.getClass().getName()` returns the **binary name string** of the class (with special runtime notation for arrays).
- `obj.getClass().getSimpleName()` returns the simple name, which can be empty in some cases, such as anonymous classes.
- `obj.getClass().getCanonicalName()` can return `null` for classes that have no canonical name.
- `obj.toString()` is how an object chooses to represent itself, not always synonymous with the class name.

When you want to check for the exact same class, use **`Class` identity** (for example `obj.getClass() == Dog.class`) instead of comparing simple name strings. Two classes in different packages can share the same `getSimpleName()`; two class loaders can also load classes with identical names yet different identities.

## 4. Quick Comparison Table

| Scenario | `Type.class` | `obj.getClass()` |
|---|---|---|
| Source of determination | Type name written in source code | Actual instance at runtime |
| Requires an instance? | No | Yes, and must be non-`null` |
| Parent-type variable holding subclass object | `Base.class` is still `Base` | Returns `Derived.class` |
| Interface | `Interface.class` is valid | Instance returns the actual implementing class |
| Primitive `int` | `int.class` is valid | Primitives are not objects, so `getClass()` cannot be called directly |
| Boxed value `Integer` | `Integer.class` | `Integer.valueOf(1).getClass()` is `Integer.class` |
| Array | `String[].class` | `new String[0].getClass()` is `String[].class` |
| `null` variable | `Type.class` is still valid | Calling `getClass()` throws `NullPointerException` |
| Changes with the referenced object | No | Can differ when the variable is assigned an instance of another class |

A variable with static type `Object` does not become an instance of `Object` just because it is declared that way; `new String("x")` assigned to that variable still has runtime class `String`.

## 5. When Do You Need `==`, `equals`, `instanceof`, and `isAssignableFrom`?

These checks are easily confused as answering the same question, yet in practice they differ.

### 5.1. Exact Comparison of Two `Class` Objects

```java
boolean exact = value.getClass() == Dog.class;
```

This asks: **is the runtime class of `value` literally `Dog`?** An instance of subclass `SpecialDog extends Dog` (if `Dog` is not `final`) will not pass an exact-class check for `Dog`.

`Class.equals` also compares `Class` object identity, so `Dog.class.equals(value.getClass())` is semantically equivalent to `Dog.class == value.getClass()`. `==` is the customary choice because the `Class` object representing a given runtime class is reused.

### 5.2. `instanceof` and `Class.isInstance` Check Type Compatibility

```java
boolean compatible = value instanceof Dog;
boolean reflectiveCheck = Dog.class.isInstance(value);
```

For non-null `value`, both checks are true if the object is a `Dog` or a subclass of `Dog`. For `null`, both return `false` (`isInstance(null)` returns `false`). `instanceof` also checks interface implementation without needing to fetch `getClass()`.

In ordinary Java code with statically known types, prefer `instanceof` when simply asking about castability/type compatibility. Use `Class.isInstance` when the `Class<?>` object is obtained dynamically, such as from configuration or plugins.

### 5.3. `Class.isAssignableFrom` Compares **Two Types**, Without Needing an Object

```java
boolean canAssignDogToAnimal =
        Animal.class.isAssignableFrom(Dog.class); // true
boolean canAssignAnimalToDog =
        Dog.class.isAssignableFrom(Animal.class); // false
```

Read `A.class.isAssignableFrom(B.class)` as "can a value of type `B` be assigned to a reference variable of type `A` according to Java's type-assignment rules?". For reference classes, interfaces, and arrays, it describes runtime type relationships, including inheritance and interface implementation.

**The parameter direction is very easy to write backwards:** `Animal.class.isAssignableFrom(Dog.class)` is `true`, whereas the reverse is `false`. This method does not inspect a concrete object on its own because its input is a `Class<?>` object.

Note that primitive `Class` objects do not apply autoboxing when checking assignability: `int.class.isAssignableFrom(Integer.class)` is `false`. Boxing is a language and method-invocation mechanism; it does not make `int.class` and `Integer.class` the same runtime type.

### 5.4. Choosing the Right Tool for the Purpose

| Question | Tool |
|---|---|
| "Which type `Dog` is named in source code?" | `Dog.class` |
| "Which class does this instance actually belong to?" | `obj.getClass()` |
| "Can this instance be viewed/cast as `Dog`?" | `obj instanceof Dog` |
| "Does a type known only at runtime accept this instance?" | `selectedClass.isInstance(obj)` |
| "Does the definition of class `Animal` encompass a `Dog`?" | `Animal.class.isAssignableFrom(Dog.class)` |
| "Do two instances have the exact same runtime class?" | `a.getClass() == b.getClass()` (after null check) |
| "Are two instances equal according to business semantics?" | `a.equals(b)` per the class's contract; do not replace with `Class` comparison |

## 6. Standalone Runnable Java 17 Program

Create the file **`ClassLiteralDemo.java`**. The program fixes its inputs and prints only results that do not depend on hidden class names or runtime hashes.

```java
public class ClassLiteralDemo {
    static class Animal { }

    static class Dog extends Animal { }

    static class Cat extends Animal { }

    interface Tagged { }

    static final class TaggedDog extends Dog implements Tagged { }

    public static void main(String[] args) {
        Animal animal = new Dog();
        Object sameObject = animal;

        System.out.println("declared literal: "
                + Animal.class.getSimpleName());
        System.out.println("runtime class: "
                + animal.getClass().getSimpleName());
        System.out.println("base exact: "
                + (animal.getClass() == Animal.class));
        System.out.println("dog exact: "
                + (animal.getClass() == Dog.class));
        System.out.println("same Class object: "
                + (animal.getClass() == sameObject.getClass()));

        System.out.println("instanceof Animal: "
                + (animal instanceof Animal));
        System.out.println("instanceof Dog: "
                + (animal instanceof Dog));
        System.out.println("Animal.isInstance: "
                + Animal.class.isInstance(animal));
        System.out.println("Animal <- Dog: "
                + Animal.class.isAssignableFrom(Dog.class));
        System.out.println("Dog <- Animal: "
                + Dog.class.isAssignableFrom(Animal.class));

        Animal tagged = new TaggedDog();
        System.out.println("subclass exact Dog: "
                + (tagged.getClass() == Dog.class));
        System.out.println("subclass instanceof Dog: "
                + (tagged instanceof Dog));
        System.out.println("tag interface: "
                + Tagged.class.isInstance(tagged));

        Object absent = null;
        System.out.println("null isInstance: "
                + Animal.class.isInstance(absent));
        System.out.println("null instanceof: "
                + (absent instanceof Animal));

        System.out.println("primitive name: " + int.class.getName());
        System.out.println("wrapper name: " + Integer.class.getName());
        System.out.println("primitive equals wrapper: "
                + int.class.equals(Integer.class));
        System.out.println("array exact: "
                + (new String[0].getClass() == String[].class));
        System.out.println("array as Object: "
                + Object.class.isAssignableFrom(String[].class));
        System.out.println("interface literal: "
                + Tagged.class.isInterface());
    }
}
```

In the directory containing the file, use JDK 17 or newer:

```bash
javac --release 17 ClassLiteralDemo.java
java ClassLiteralDemo
```

Output:

```text
declared literal: Animal
runtime class: Dog
base exact: false
dog exact: true
same Class object: true
instanceof Animal: true
instanceof Dog: true
Animal.isInstance: true
Animal <- Dog: true
Dog <- Animal: false
subclass exact Dog: false
subclass instanceof Dog: true
tag interface: true
null isInstance: false
null instanceof: false
primitive name: int
wrapper name: java.lang.Integer
primitive equals wrapper: false
array exact: true
array as Object: true
interface literal: true
```

### Explanation of Output Groups

**Group one — Declared type differs from runtime class.** Variable `animal` has declared type `Animal`, while the instance is created from `Dog`. Therefore `Animal.class` is still `Animal`, but `animal.getClass()` is `Dog.class`. Both `animal` and `sameObject` point to the same object, so they retrieve the same `Class` object.

**Group two — Inheritance and assignability.** `Dog extends Animal`, so a Dog is an Animal; `instanceof Animal` is true and `Animal.class.isAssignableFrom(Dog.class)` is true. The direction `Dog.class.isAssignableFrom(Animal.class)` is false: not every Animal is a Dog.

**Group three — Further subclass.** `TaggedDog extends Dog`, so that object is compatible with `Dog`, yet its exact runtime class is `TaggedDog`. The check `tagged.getClass() == Dog.class` is false while `tagged instanceof Dog` is true. It also implements `Tagged`, so `Tagged.class.isInstance(tagged)` is true.

**Group four — Null.** `Class.isInstance(null)` and `null instanceof Animal` return `false`. However, `absent.getClass()` would throw `NullPointerException` and is not called here.

**Group five — Primitive, wrapper, array, interface.** `int.class` and `Integer.class` represent two different types; primitives do not autobox when represented by `Class` objects. Array `String[]` has its own runtime `Class`, and an array is an object so it can be assigned to `Object`. `Tagged.class` represents an interface, even though an interface itself cannot be instantiated directly.

### Conclusions That Must Not Be Drawn

- `animal instanceof Animal` being true does **not** imply `animal.getClass() == Animal.class`.
- `animal.getClass() == Dog.class` being true does **not** mean you must cast before calling `getClass()`.
- `Dog.class.isAssignableFrom(Animal.class)` being false does **not** mean an `Animal` variable cannot hold a `Dog`.
- `Object.class.isAssignableFrom(String[].class)` being true does **not** mean `String[].class == Object.class`.
- Two instances with the same runtime class **are not automatically equal** under `equals`; that remains the responsibility of the class.

## 7. Implications for `equals()`: Class Literals Do Not Decide Equality Policy on Their Own

`Type.class` describes a type **fixed in source code**, whereas `getClass()` describes the runtime class of each instance. When writing `equals(Object)`, the following two checks express two different policies:

```java
// Inside equals(Object) of a Base class:
if (other == null || getClass() != other.getClass()) return false;

// Alternative approach, only when the domain allows subclasses to participate in equality:
if (!(other instanceof Base that)) return false;
```

These are **two alternative snippets**, not used simultaneously; they assume we are inside class `Base` and the remainder of `equals` compares the value-defining fields. The first lets only instances of the **same runtime class** proceed. The second accepts subclasses as well, so classes in the inheritance hierarchy must agree on equality criteria: if `base.equals(sub)` is true while `sub.equals(base)` is false, **symmetry** is violated. Whichever approach is chosen, `equals` must remain reflexive, symmetric, transitive, consistent, and compatible with `hashCode`.

Do not mechanically replace `getClass() == other.getClass()` with `other.getClass() == Base.class`: the class literal `Base.class` is always fixed, whereas `this.getClass()` can be a subclass if the method is inherited. For `final` value objects or records, subclass-related risks are generally reduced; for runtime entities/proxies, an exact-class check may reject an object representing the same record. Choose the equality policy according to your model and the framework contract in use.

The point to remember in this **class literal** lesson is that `Base.class` and `obj.getClass()` do not automatically substitute for each other. They only supply type information; by themselves they do not decide whether two objects have the **same business value**.

## 8. Primitives, Arrays, Interfaces, Enums, and Records

### Primitives and `void`

`int.class` is the `Class` of primitive `int`; `Integer.class` is the `Class` of the wrapper class. These two objects are distinct. `void.class` is also a valid class literal representing the `void` type. There is no normal Java instance of `int` or `void` on which to call `getClass()` directly.

In reflection APIs, `Class.isPrimitive()` can be used to check that `int.class.isPrimitive()==true`, whereas `Integer.class.isPrimitive()==false`. `void.class.isPrimitive()` is also considered primitive according to the `Class` API.

### Arrays

`new String[0].getClass() == String[].class` is true. Array length does not change the runtime class. Primitive arrays and wrapper arrays are two different types: `int[].class != Integer[].class`. `String[]` and `Object[]` are also distinct `Class` objects, even though `Object[].class.isAssignableFrom(String[].class)` is true due to reference-array covariance.

Arrays also implement `Cloneable` and `java.io.Serializable`. `Object.class.isAssignableFrom(int[].class)` returns true, because a primitive array is still an object. Yet `int.class.isAssignableFrom(Integer.class)` remains false.

### Interfaces

`Runnable.class` represents an interface. An object can implement `Runnable`, yet `obj.getClass()` returns the implementing class, not `Runnable.class`. If you want to ask whether an object implements an interface, use `obj instanceof Runnable` or `Runnable.class.isInstance(obj)`.

### Enums

`DayOfWeek.MONDAY.getClass()` returns the runtime class of the enum object. For an enum with **constant-specific class bodies** (where each constant has its own body), the runtime class may be a special subclass, while `getDeclaringClass()` returns the enum type declaring the constant; therefore do not assume `constant.getClass() == MyEnum.class` holds in every enum declaration style. For ordinary enums without constant-specific class bodies, both results usually match.

### Records

A record is a `final` class, so for a normally instantiated record instance, `recordInstance.getClass() == RecordType.class`. It is still a Java object, inherits `Object.getClass`, and is checked with `instanceof` like other reference types. The fact that the compiler generates `equals`/`hashCode` for a record based on its components **is not** because Java compares a class name string.

### Anonymous Classes and Lambdas

An anonymous class has its own runtime class, so `new Runnable() { public void run() {} }.getClass()` is not `Runnable.class`. A lambda also has a JVM-generated runtime implementation class; do not rely on the name, numbering, stability, or path of this class as a public API. If you only need to know whether an object implements a given interface, use `instanceof` or `Class.isInstance`.

## 9. Class Loaders and the Difference Between Class Name and Identity

`Class.getName()` can produce the same string from two classes loaded by two different defining class loaders, yet those two runtime classes **are not the same type**. This matters in plugin systems, application servers, modular runtimes, and systems with isolated class loaders.

Do not infer that:

```java
left.getClass().getName().equals(right.getClass().getName())
```

is enough for two objects to have the same runtime class. This is an illustrative expression with non-null `left`/`right`, not a standalone program. The proper `Class` identity comparison when an exact class is needed is:

```java
left.getClass() == right.getClass()
```

Note: equality of entities/value objects is a separate matter; having the same runtime class is also not sufficient to conclude that two objects have the same value or business identity.

### Comparison with `Class.forName`

`Type.class` uses a type name known at compile time. `Class.forName("mypackage.Type")` looks up a type by runtime string via the class-loading mechanism; the single-argument overload can initialize the class. If control is needed, there is an overload `Class.forName(name, initialize, loader)`, allowing selection of initialization and loader.

Use `Class.forName` only when a dynamic name is truly needed, such as reading configuration, and handle `ClassNotFoundException` or appropriate visibility/security concerns. When the type is already known at compile time, a class literal is clearer and more type-safe.

## 10. Generics: `Class<T>` and the Limitations of `getClass()`

`Class<String>` carries a generic type parameter indicating it represents `String`, enabling better-typed reflection APIs. `Class<?>` is a safe type when only an arbitrary class is known.

```java
Class<String> stringClass = String.class;
Class<?> runtimeClass = "text".getClass();

System.out.println(stringClass == runtimeClass); // true
```

This snippet resides inside a method. Certain direct comparison expressions between `Class<...>` with incompatible generic types can trigger compile errors due to type checking; when an API needs to work with unknown `Class` objects, store them as `Class<?>` and use `Class.equals` or typed reflection APIs.

**Type erasure** still exists: `List<String>` and `List<Integer>` both have the runtime class of the same implementation type, such as `ArrayList`, when both are created from `new ArrayList<>()`. There is no `List<String>.class` because a class literal does not accept a parameterized type. Calling `list.getClass()` cannot guarantee that every element of the list is a `String`.

Therefore, `getClass()` is a source of the **runtime class**, not full generic source-type information. When generic declaration metadata is needed, reflection APIs such as `getGenericSuperclass()`/`getGenericInterfaces()` are limited and reflect only the declared structure; they do not recover every generic argument erased at runtime.

## 11. Pitfalls and How to Fix Them

| Common Mistake | Why It Is Wrong | Correct Approach |
|---|---|---|
| `animal.getClass() == Animal.class` to ask whether it is an `Animal` | Subclasses are rejected because their runtime class differs | `animal instanceof Animal` or `Animal.class.isInstance(animal)` |
| Calling `obj.getClass()` when `obj` can be null | Throws `NullPointerException` | Check for `null` or use `X.class.isInstance(obj)` |
| Using `getSimpleName()` to check identity | Classes in different packages/loaders can share the same simple name | Compare `Class` identity directly |
| Using `int.class == Integer.class` as if testing boxing | Primitives and wrappers are different types | Distinguish primitive types from wrappers; do not infer from boxing |
| Writing `Dog.class.isAssignableFrom(Animal.class)` to check whether `Dog` is an `Animal` | Reversed assignment direction | `Animal.class.isAssignableFrom(Dog.class)` |
| Thinking `getClass()` returns the variable's declared type | It returns the class of the runtime object | Use a class literal when you want a fixed type from source code |
| Using `getClass()` too strictly in equality for entities using ORM proxies | A proxy can be a runtime subclass | Follow the equality/proxy rules of the actual ORM |
| Accepting subclasses via `instanceof` when subclasses change equality | Can break symmetry/transitivity | Design a contract for the hierarchy or use `final` value objects |
| Using `getName()` as class identity | Different class loaders can define the same name | Compare `Class` objects, considering the defining class loader |
| Thinking `getClass()` recovers `List<String>` | Generic erasure | Design a type token or other metadata when needed |
| Coupling runtime class names of lambdas/proxies to business logic | Synthetic names/classes are implementation details | Check interfaces/API contracts, not auto-generated names |

## 12. Practice Exercises

### Exercise 1 — Inheritance and Runtime Class

Create `Animal` and `Dog extends Animal`. Assign `Animal x = new Dog()`, then predict:
- `x.getClass() == Animal.class` → `false`.
- `x.getClass() == Dog.class` → `true`.
- `x instanceof Animal` → `true`.
- `Animal.class.isAssignableFrom(Dog.class)` → `true`.
- `Dog.class.isAssignableFrom(Animal.class)` → `false`.

Explain using static type and runtime class, rather than merely memorizing the answers.

### Exercise 2 — Interface Type and Multiple Implementations

Create `interface Payment` and two classes `CardPayment` and `CashPayment` implementing `Payment`. Use a `Payment payment` variable pointing to each object in turn. `Payment.class` always represents the interface; `payment.getClass()` returns each corresponding implementation in turn; `payment instanceof Payment` is always true for non-null objects.

### Exercise 3 — Null and Dynamic APIs

Given `Object maybeNull = null`. Compare the results of `maybeNull instanceof String`, `String.class.isInstance(maybeNull)`, and try `maybeNull.getClass()` inside a `try/catch`. The first two return `false`, while the last throws `NullPointerException`. Explain why a class literal does not require an instance.

### Exercise 4 — `equals` for a Value Object

Create a `final` class with two immutable fields `code` and `version`. Write `equals` checking `this==other`, exact type, and both fields; write `hashCode` using the same fields. Create two separate instances with the same values, confirming they are equal and have equal hashes. Then explain why `getClass()` in a `final` class does not encounter subclass issues.

### Exercise 5 — Arrays and Primitives

Compare `int.class` with `Integer.class`, `int[].class` with `Integer[].class`, and `String[].class` with `Object[].class`. Also check `Object[].class.isAssignableFrom(String[].class)` and `Object.class.isAssignableFrom(int[].class)`, then explain array covariance and why arrays are objects.

### Exercise 6 — Comparison When Using Proxies

Simulate `ProxyEntity extends Entity` with `Entity normal = new Entity(...)` and `Entity proxy = new ProxyEntity(...)`. Compare `normal.getClass() == proxy.getClass()` and `proxy instanceof Entity`. State why an exact-class comparison can be unsuitable for ORM proxies, and why the equality policy must be unified before using entities as collection keys.

### Exercise 7 — Class Loaders

Explore a plugin application loading the same fully qualified class name via two separate class loaders. Explain why `getName()` can match while the `Class` objects differ, and why cross-casting between two runtime classes does not necessarily succeed even with the same name. You do not need to write a custom class loader yourself to understand the definition.

## 13. Project Application Checklist

- Distinguished the static type in source code from the runtime class of an instance.
- Used `Type.class` when wanting metadata of a type determined from source code.
- Used `getClass()` when the concrete runtime class is truly needed and the object is non-null.
- Used `instanceof`/`Class.isInstance` when wanting to accept subclasses or interface implementations.
- Used `Class.isAssignableFrom` in the right direction when comparing the relationship between two types.
- Did not equate primitive `Class` with wrapper `Class`; knew arrays/interfaces have their own `Class`.
- Did not rely on `getSimpleName()` or auto-generated lambda/proxy names for type identity.
- When using `getClass()` in `equals`, reviewed inheritance, symmetry, proxies, and business semantics.
- When using reflection/generics, understood `Class<?>` and the limits of type erasure.
- Ran the `ClassLiteralDemo.java` example and can explain every line of output.

**Key Takeaway:** `Type.class` describes the **explicitly named type** in the program, whereas `obj.getClass()` describes the **actual class of the object at runtime**. Exact-class comparison differs from inheritance-compatibility checks. Choosing the right check is an important part of designing a clear, safe, and maintainable Object Contract.