# Distinguishing Between Declared Type and Actual Object Class in Java

## 1. Two Kinds of Information on the Same Reference Variable

When reading Java code, you need to distinguish the **declared type** (*declared/static type*) of a variable or expression from the **actual class** (*runtime class*) of the object that the reference points to.

```java
Animal pet = new Dog();
```

This is **an illustrative statement** (assuming `Dog extends Animal`), not a complete program:

- `Animal` is the **declared type** of the variable `pet`, known to the compiler during code checking.
- `new Dog()` creates the **actual object** belonging to class `Dog` at runtime.
- The variable `pet` holds a reference to the `Dog` object. Having a variable of type `Animal` does not turn the `Dog` object into a plain `Animal` object.
- Because `Dog` is a subclass of `Animal`, this assignment is valid **upcasting** and requires no explicit cast.

The same concept applies when a variable is declared with an **interface**:

```java
CharSequence text = new StringBuilder("Java");
```

In this example, `CharSequence` is the declared type, and `StringBuilder` is the actual class. An interface only specifies a contract that an object can implement; an interface itself is not a concrete class instantiated with `new CharSequence()`.

## 2. What Does the Compiler Decide Using the Declared Type?

The declared type governs what operations can be written **validly at the call site being compiled**:

- Method names and signatures that can be called (the method must be visible and compatible through the declared type).
- Accessible fields, including access-scope rules and **field** selection.
- **Overloading** resolution: choosing a signature when multiple methods share the same name with different parameter lists, based on types known at compile time.
- Reference assignability, generic type parameter bounds, and casting requirements when accessing APIs that exist only on a subclass.

Example:

```java
Animal pet = new Dog();
pet.speak();     // Valid if Animal declares or inherits speak()
// pet.fetch();  // COMPILE ERROR if only Dog has fetch()
```

Even though the actual object is a `Dog`, the compiler only knows that the expression `pet` has type `Animal`, so it does not allow calling a method that exists only on `Dog` directly without checking/casting first.

**Note on `var`:** `var pet = new Dog()` causes the compiler to **infer the declared type as `Dog`** at the declaration site. `var` does not mean the variable becomes dynamically typed or changes its type according to the object on subsequent assignments.

## 3. What Does the JVM Decide Using the Actual Class?

For **overridable instance methods**, once the call signature has been validated, Java uses **dynamic dispatch**: the executed implementation depends on the actual class of the receiver.

```java
class Animal {
    String speak() { return "Animal"; }
}

class Dog extends Animal {
    @Override
    String speak() { return "Dog"; }
}

// Inside a method:
Animal pet = new Dog();
System.out.println(pet.speak()); // Dog
```

The snippet above illustrates multiple class declarations and a call, not a file with `main`. The compiler accepts `pet.speak()` because the `Animal` type has a `speak()` method. At runtime, the receiver object is a `Dog`, so the overridden `Dog.speak()` implementation is called.

**Not every operation dispatches on the actual class:** field access, overload selection, `static` method calls (method hiding), and valid API selection still depend on the compile-time type. `private` methods are not overridden; `final` methods cannot be overridden; constructors are not overridden either.

## 4. Complete Java 17+ Example: Methods, Fields, Overloads, Casts, and `getClass()`

Save the following program to **`DeclaredVsRuntimeTypeDemo.java`**:

```java
public class DeclaredVsRuntimeTypeDemo {
    static class Animal {
        String label = "Animal field";

        String speak() {
            return "Animal.speak";
        }

        String describe(Animal other) {
            return "describe(Animal)";
        }
    }

    static class Dog extends Animal {
        String label = "Dog field";

        @Override
        String speak() {
            return "Dog.speak";
        }

        String describe(Dog other) {
            return "describe(Dog)";
        }

        String fetch() {
            return "fetch";
        }
    }

    static class ServiceDog extends Dog {}

    static class Cat extends Animal {}

    public static void main(String[] args) {
        Animal pet = new Dog();

        System.out.println("declared Animal, speak: " + pet.speak());
        System.out.println("declared Animal, field: " + pet.label);
        System.out.println("runtime class: "
                + pet.getClass().getSimpleName());
        System.out.println("instanceof Dog: " + (pet instanceof Dog));
        System.out.println("overload via Animal: "
                + pet.describe(new Dog()));

        Dog dog = (Dog) pet;
        System.out.println("cast Dog, field: " + dog.label);
        System.out.println("overload via Dog: "
                + dog.describe(new Dog()));

        if (pet instanceof Dog matchedDog) {
            System.out.println("pattern instanceof: " + matchedDog.fetch());
        }

        Animal service = new ServiceDog();
        System.out.println("service instanceof Dog: "
                + (service instanceof Dog));
        System.out.println("service exact Dog class: "
                + (service.getClass() == Dog.class));

        Animal missing = null;
        System.out.println("null instanceof Dog: "
                + (missing instanceof Dog));
        try {
            missing.getClass();
        } catch (NullPointerException ex) {
            System.out.println("null.getClass: NullPointerException");
        }

        Animal cat = new Cat();
        try {
            Dog invalid = (Dog) cat;
            System.out.println(invalid.fetch());
        } catch (ClassCastException ex) {
            System.out.println("Cat cast to Dog: ClassCastException");
        }
    }
}
```

Compile and run with JDK 17 or higher:

```bash
javac DeclaredVsRuntimeTypeDemo.java
java DeclaredVsRuntimeTypeDemo
```

Output:

```text
declared Animal, speak: Dog.speak
declared Animal, field: Animal field
runtime class: Dog
instanceof Dog: true
overload via Animal: describe(Animal)
cast Dog, field: Dog field
overload via Dog: describe(Dog)
pattern instanceof: fetch
service instanceof Dog: true
service exact Dog class: false
null instanceof Dog: false
null.getClass: NullPointerException
Cat cast to Dog: ClassCastException
```

The output depends only on the class relationships and calls defined in the example, not on reference identity or collection ordering.

## 5. Explaining Why the Output Lines Differ

**Method overriding — uses the actual class.** `pet.speak()` runs `Dog`'s implementation even though `pet` is declared as `Animal`, because `speak()` is an instance method overridden by `Dog`.

**Field hiding — uses the type of the access expression.** Both `Animal` and `Dog` declare a field named `label`. `pet.label` is viewed through an expression of type `Animal`, so it reads `"Animal field"`; after casting, `dog.label` is viewed through type `Dog`, so it reads `"Dog field"`. Fields do not have dynamic overriding like instance methods. Having two fields with the same name should generally be avoided because it makes code confusing.

**Overloading — signature chosen at compile time.** `pet.describe(new Dog())` only sees `describe(Animal)` through the declared type `Animal`, so it picks that signature. With `dog.describe(new Dog())`, the expression type is `Dog`, which has both `describe(Animal)` and `describe(Dog)` and chooses the more specific signature `describe(Dog)`. In this program `Dog` does not override `describe(Animal)`, so the first result comes from the inherited method.

**Casting does not change the actual object.** `(Dog) pet` only produces an expression of type `Dog` after the JVM verifies that the actual object is compatible. No new object is created, and the object's own class does not change. If `pet` is actually a `Cat`, downcasting to `Dog` throws `ClassCastException`.

**`instanceof` checks type compatibility.** A `ServiceDog` is a subclass of `Dog`, so `service instanceof Dog` is `true` even though `service.getClass() == Dog.class` is `false` (the exact actual class is `ServiceDog`). In Java 17, the syntax `pet instanceof Dog matchedDog` both checks the type and declares a narrowed-type variable inside the conditional branch.

## 6. `getClass()` and `instanceof` Answer Two Different Questions

| Expression | Question Answered | Example `new ServiceDog()` |
| --- | --- | --- |
| `obj.getClass() == Dog.class` | Is the object's **exact actual class** `Dog`? | `false` |
| `obj instanceof Dog` | Is the object an instance of `Dog` **or a subclass of `Dog`**? | `true` |
| `Dog.class.isInstance(obj)` | Checks runtime compatibility via a class token | `true` |
| `obj.getClass().getSuperclass()` | Gets the direct superclass of the runtime class | `Dog.class` for `ServiceDog` |

`Object.getClass()` is a `final` method that returns a `Class<?>` object representing the **actual class** of the receiver. When `obj == null`, `obj.getClass()` throws `NullPointerException`; `obj instanceof Dog` returns `false` when `obj` is `null`.

In systems using proxies or runtime framework-generated subclasses, `getClass()` may return a **proxy class**. Therefore, when you want to know whether an object supports an interface or base type, you should usually check with `instanceof` or an appropriate framework API rather than relying solely on an exact `getClass() == SomeClass.class` comparison.

## 7. Connection to the `equals()` Contract in `object-contract`

`equals(Object)` is declared in `java.lang.Object` and can be overridden by subclasses. Therefore:

```java
Object left = new ValueKey(7);
Object right = new ValueKey(7);
System.out.println(left.equals(right));
```

The snippet above assumes a `ValueKey` class with an appropriate `equals(Object)`; although the **declared type of `left` is `Object`**, the call `left.equals(right)` can still execute the override from the runtime class `ValueKey` and return `true` by value. If `ValueKey` does not override `equals`, the default `Object.equals` compares identity, and two different `new` objects will normally not be equal.

When implementing `equals`, two common ways to check the type are:

```java
if (obj == null || getClass() != obj.getClass()) return false;

// Or under a policy that allows compatible subtypes:
if (!(obj instanceof ValueKey other)) return false;
```

These are **two alternative design options**, not two statements to use simultaneously. The `getClass()` approach requires the exact same runtime class; the `instanceof` approach can accept subclasses. Whichever option you choose, `equals()` must still satisfy reflexivity, symmetry, transitivity, consistency, and `null` handling, and `hashCode()` must stay in sync. In particular, allowing a subclass to equal a superclass in only one direction can violate symmetry or transitivity if each class uses different criteria.

Example of a `final` value class that disallows inheritance:

```java
final class ValueKey {
    private final int id;

    ValueKey(int id) { this.id = id; }

    @Override
    public boolean equals(Object obj) {
        return obj instanceof ValueKey other && id == other.id;
    }

    @Override
    public int hashCode() {
        return Integer.hashCode(id);
    }
}
```

This is a **compilable class declaration when placed in an appropriate Java file**, not a program with `main`. Because `ValueKey` is `final`, checking `instanceof ValueKey` does not create issues with user-defined subclasses; two `new ValueKey(7)` objects are considered equal by `id`. The `equals` call still dispatches to `ValueKey.equals` even when the reference is declared as `Object`.

## 8. Safe Casting and Limitations to Remember

**Upcasting** (subclass to superclass/interface) is a valid reference conversion: `Animal pet = new Dog()`. However, you can only directly call methods visible through the declared type.

**Downcasting** (superclass/interface to subclass) requires a runtime check: `Dog d = (Dog) pet`. If the actual class is incompatible, the JVM throws `ClassCastException`. Java 17 provides pattern matching for `instanceof` to handle this more safely and concisely:

```java
if (pet instanceof Dog d) {
    System.out.println(d.fetch());
}
```

The snippet above assumes `pet`, `Dog`, and `fetch()` as in the larger example. `instanceof` does not turn a plain `Animal` object into a `Dog`; it only **checks and then narrows the type of the reference** inside the valid branch.

**`null` has no actual class.** The variable `Animal pet = null;` still has declared type `Animal`, but points to no object. Do not invoke instance methods through `pet` when it is `null`. Check `pet == null` or `pet instanceof Dog` depending on your goal (the latter returns `false` for `null`).

**Generic types cannot be recovered directly from `getClass()`.** For example, `List<String>` and `List<Integer>` share the same runtime implementation class such as `ArrayList` when created via `new ArrayList<>()` due to type erasure. Type parameters `<String>`/`<Integer>` help the compiler check usage, but `list.getClass()` does not provide separate `Class<List<String>>` metadata to distinguish them at runtime.

## 9. Common Misconceptions

| Misconception | Correct Understanding |
| --- | --- |
| `Animal pet = new Dog()` means there is only an `Animal` object | The created object is a `Dog`; `Animal` is the declared type of the reference |
| Method calls always follow the declared type | Overridden instance methods run according to the actual receiver class |
| `pet.label` uses `Dog`'s field because runtime is `Dog` | Field access uses the type of the expression (`Animal`) |
| Overload is selected by the runtime class of arguments | The overload signature is decided at compile time by the applicable types of the expression and arguments |
| `(Dog) pet` creates a new `Dog` object | Casting only changes the type view of the reference after a runtime check |
| `instanceof Dog` is the same as `getClass() == Dog.class` | `instanceof` accepts subclasses; `getClass() ==` requires the exact runtime class |
| Every reference variable has a runtime object | A variable can be `null`; in that case there is no actual object class |
| Declaring `Object x = new ValueKey(7)` will always call `Object.equals` | If `ValueKey` overrides `equals`, the call runs the override based on the actual class |

## 10. Self-Check

1. `Animal x = new Dog();` — what is the declared type of `x`, and what is the actual class? **`Animal` and `Dog`.**
2. Which method does `x.speak()` call when `Dog` overrides `speak`? **`Dog.speak()`** due to dynamic dispatch.
3. Which field does `x.label` read if both classes have a `label` field? **The field visible through the `Animal` type**.
4. For `Animal x = new ServiceDog();`, what are `x instanceof Dog` and `x.getClass() == Dog.class`? **`true` and `false`.**
5. Does `Animal x = null; x.getClass()` return `Animal.class`? **No**; it throws `NullPointerException`.
6. If a method exists only on `Dog`, can you call `x.fetch()` directly when `x` is declared as `Animal`? **No**; you must check the type and then narrow/cast the reference.

**Key Takeaway:** The **declared type** determines which calls Java lets you *write* and selects signatures/fields at compile time; the **actual class** determines *which override is executed* at runtime as well as the results of `getClass()` and `instanceof`. Distinguishing these two layers of information helps you understand polymorphism, casting, and object contracts accurately.