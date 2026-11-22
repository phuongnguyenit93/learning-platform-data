# `instanceof` with Concrete Class Types in Java

## 1. What does `instanceof` check when naming a class?

In Java, the `instanceof` operator checks whether the **object referenced at runtime** is an *instance* of the specified class **or a subclass of that class**. The result is a `boolean`: `true` if the type relationship matches, `false` otherwise.

Traditional class-checking syntax:

```java
reference instanceof ClassName
```

For example, given a `Dog` class and a reference variable `animal`:

```java
if (animal instanceof Dog) {
    // The object held by animal is a Dog or a subclass of Dog.
}
```

Since Java 16 (including Java 17+), you can use a **type pattern** to check the class and immediately declare a variable of that type:

```java
if (animal instanceof Dog dog) {
    // dog has static type Dog; no explicit cast needed.
}
```

Here, `Dog` is the **specific class name to check against**; `dog` is a *pattern variable* that is only in scope where Java determines the test has matched. Both expressions check the actual type relationship; the second syntax makes using `Dog` members more concise.

It is important to distinguish two concepts:

- **Declared type (static/declared type)** of the variable, e.g. `Animal animal`, tells the compiler which calls are valid.
- **Actual type (runtime class)** of the object, e.g. `new Dog()`, determines the result of `instanceof`.

An object can still pass a `Dog` check even if the variable holding it is declared as `Object` or the superclass `Animal`. `instanceof` does not check class name strings and does not create a new object.

## 2. Inheritance relationships: a subclass is also an instance of its superclass

Consider the following classes (these are **illustrative snippets**; the complete classes are in the runnable program in Section 3):

```java
class Animal {}
class Dog extends Animal {}
class Poodle extends Dog {}
class Cat extends Animal {}
```

Then:

```java
Animal pet = new Poodle();

pet instanceof Poodle  // true
pet instanceof Dog     // true
pet instanceof Animal  // true
pet instanceof Cat     // false
```

`Poodle` extends `Dog`, and `Dog` extends `Animal`. Therefore, a `Poodle` **is simultaneously** a `Dog` and an `Animal`. However, `Cat` is on a different inheritance branch, so the `Cat` check fails.

| Referenced object | `instanceof Animal` | `instanceof Dog` | `instanceof Poodle` | `instanceof Cat` |
| --- | --- | --- | --- | --- |
| `new Animal()` | `true` | `false` | `false` | `false` |
| `new Dog()` | `true` | `true` | `false` | `false` |
| `new Poodle()` | `true` | `true` | `true` | `false` |
| `new Cat()` | `true` | `false` | `false` | `true` |
| `null` | `false` | `false` | `false` | `false` |

These values are evaluated based on the **actual object**, not just the type name on the left side of `=`. Class-based `instanceof` includes indirect subclasses; it **does not require an exact runtime class match**.

The target class of `instanceof` can also be an `abstract` class; what is checked is the type relationship of the actual object. In the title of this lesson, "concrete class types" refers to specifying a class such as `Dog` or `Cat` to check against—it does not mean the operator only accepts `final` classes or classes that can be instantiated with `new`.

## 3. Complete Java 17+ example: checking concrete classes

Save with the exact filename `ClassInstanceofDemo.java`:

```java
public class ClassInstanceofDemo {
    static class Animal {}

    static class Dog extends Animal {
        String sound() {
            return "woof";
        }
    }

    static final class Poodle extends Dog {}
    static final class Cat extends Animal {}

    static void describe(Animal animal) {
        if (animal instanceof Poodle poodle) {
            System.out.println("Poodle: " + poodle.sound());
        } else if (animal instanceof Dog dog) {
            System.out.println("Dog: " + dog.sound());
        } else if (animal instanceof Cat) {
            System.out.println("Cat");
        } else if (animal == null) {
            System.out.println("null");
        } else {
            System.out.println("Animal");
        }
    }

    public static void main(String[] args) {
        Animal dog = new Dog();
        Animal poodle = new Poodle();
        Animal cat = new Cat();

        System.out.println("dog is Dog: " + (dog instanceof Dog));
        System.out.println("dog is Poodle: " + (dog instanceof Poodle));
        System.out.println("poodle is Dog: " + (poodle instanceof Dog));
        System.out.println("poodle is Poodle: " + (poodle instanceof Poodle));
        System.out.println("cat is Dog: " + (cat instanceof Dog));

        System.out.println("poodle exact Dog: "
                + (poodle.getClass() == Dog.class));
        System.out.println("poodle exact Poodle: "
                + (poodle.getClass() == Poodle.class));

        describe(poodle);
        describe(dog);
        describe(cat);
        describe(new Animal());
        describe(null);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac ClassInstanceofDemo.java
java ClassInstanceofDemo
```

Exact output:

```text
dog is Dog: true
dog is Poodle: false
poodle is Dog: true
poodle is Poodle: true
cat is Dog: false
poodle exact Dog: false
poodle exact Poodle: true
Poodle: woof
Dog: woof
Cat
Animal
null
```

**Key points explained:**

1. `dog` is declared as `Animal` but holds `new Dog()`, so `dog instanceof Dog` is `true`; it is not a `Poodle`, so the `Poodle` check is `false`.
2. `poodle` is declared as `Animal` but holds `new Poodle()`: both `instanceof Dog` and `instanceof Poodle` are true.
3. `cat` holds `new Cat()`; `Cat` and `Dog` both extend `Animal`, but a `Cat` is not a `Dog`.
4. `poodle.getClass() == Dog.class` is `false` because its exact class is `Poodle`, whereas `poodle instanceof Dog` is `true`.
5. In the `if` / `else if` chain, **check the specialized subclass `Poodle` before the superclass `Dog`**. If you check `Dog` first, `Poodle` will match the `Dog` branch immediately and never reach the `Poodle` branch.
6. `null` does not match any class via `instanceof`; the `animal == null` branch handles it separately.

This example uses `static` nested classes so it can be compiled directly from a single file. `Poodle` and `Cat` are declared `final` because the example does not require further subclassing; this **does not affect** their status as subclasses of `Dog` or `Animal`.

## 4. Checking before downcasting

A superclass-typed variable can hold a subclass object:

```java
Animal animal = new Dog();
```

However, the static type `Animal` does not declare the `sound()` method, so `animal.sound()` **will not compile**, even though the actual object is a `Dog`. To use `Dog`-specific APIs, you need to narrow the type for the compiler.

### 4.1. Traditional approach: `instanceof` then cast

The following snippet uses the classes declared in Section 3, placed inside a valid method:

```java
static void playSound(Animal animal) {
    if (animal instanceof Dog) {
        Dog dog = (Dog) animal;
        System.out.println(dog.sound());
    }
}
```

The cast `(Dog) animal` is only executed after `instanceof Dog` succeeds, so it will not throw a `ClassCastException` in that checked case. If you cast a `Cat` to `Dog` without ensuring type compatibility, the program can throw a `ClassCastException`.

### 4.2. Java 17+ approach: type pattern

```java
static void playSound(Animal animal) {
    if (animal instanceof Dog dog) {
        System.out.println(dog.sound());
    }
}
```

The variable `dog` has type `Dog` and is initialized when the object matches. Both `Dog` and `Poodle` pass this check; `sound()` can be called directly without casting.

When adding extra conditions, `&&` takes advantage of **short-circuiting**:

```java
if (animal instanceof Dog dog && dog.sound().equals("woof")) {
    System.out.println("A dog that says woof");
}
```

The right-hand side only runs after `Dog dog` has matched. Do not replace `&&` with `||` here, because the right-hand side of `||` is evaluated when the first check is false; at that point, `dog` is not available.

Pattern variables have **flow scope**: for example, outside a normal `if`, you cannot call `dog.sound()` because execution can still continue along the non-matching path. Inside a method, if the non-matching branch ends with `return` or `throw`, the pattern variable can be used after the `if` under the *definitely matched* rule.

## 5. How does `instanceof` differ from `getClass()` and `==`?

These three comparisons answer different questions:

| Expression | Meaning | Includes subclasses? |
| --- | --- | --- |
| `obj instanceof Dog` | Is `obj` a `Dog` or a subclass of `Dog`? | **Yes** |
| `obj.getClass() == Dog.class` | Is the runtime class of `obj` **exactly** `Dog`? | **No** |
| `obj1 == obj2` | Do two references point to the same object (or are both `null`)? | Not a type comparison |

Example:

```java
Animal animal = new Poodle();

System.out.println(animal instanceof Dog);           // true
System.out.println(animal.getClass() == Dog.class);  // false
System.out.println(animal.getClass() == Poodle.class); // true
```

Use `instanceof` when you want to accept the target class **and its subclasses** for compatible handling. Only use `getClass() == SomeClass.class` when you genuinely need to distinguish the **exact runtime class**—for example, a special rule that must not apply to subclasses.

`getClass()` is a method call: `obj.getClass()` when `obj == null` throws a `NullPointerException`. By contrast, `obj instanceof Dog` returns `false` when `obj == null`, without throwing an exception.

`instanceof` also does not compare the **content equality** of objects. If you need to compare values, check the `equals()` contract of the corresponding class.

## 6. Compiler rules and edge cases

### 6.1. Java rejects provably incompatible type checks

The compiler checks whether the static type of the operand and the target class type are **potentially compatible** under casting rules. For example, with two `final` classes that have no inheritance relationship, the following check is a compile-time error:

```java
String text = "hello";
// if (text instanceof Integer) { } // ERROR: incompatible types

Object value = text;
System.out.println(value instanceof Integer); // false, but valid
```

With `Object value`, the runtime object could belong to many different classes, so the `Integer` check is valid and evaluates to `false` in this example. However, `text` has static type `String` and cannot possibly be an `Integer` at runtime.

Similarly, in Java 17, a **redundant** type pattern check can be rejected:

```java
String text = "hello";
// if (text instanceof String s) { } // ERROR in Java 17
Object value = text;
if (value instanceof String s) {     // Valid
    System.out.println(s.length());  // 5
}
```

Because `text` already has static type `String`, declaring the pattern `String s` in that case provides no useful check. You do not need `instanceof` to verify the exact type of a `String` variable.

### 6.2. `null` and primitive types

`null instanceof Dog` is always `false` for reference-type `instanceof` in Java 17; any reference that is currently `null` produces the same result, even if it is declared as `Dog`.

In Java 17, `instanceof` applies to expressions with a **reference type**, not directly to primitive values:

```java
int count = 5;
// System.out.println(count instanceof Integer); // ERROR in Java 17

Object boxed = count; // Autoboxed to Integer.
System.out.println(boxed instanceof Integer); // true
```

The fact that a primitive-holding variable can be boxed into an object does not change the syntactic requirement of `instanceof`.

### 6.3. Generic classes

With a generic class, you cannot ask `instanceof` to check a type argument that is no longer known accurately at runtime (due to *type erasure*):

```java
Object value = new java.util.ArrayList<String>();

// if (value instanceof java.util.ArrayList<String>) { } // ERROR
if (value instanceof java.util.ArrayList<?> items) {
    System.out.println(items.size()); // 0
}
```

`ArrayList<?>` checks that the **actual class** is `ArrayList` or a subclass; it does not prove that the elements inside are of type `String`. Use `instanceof` on individual elements if you need to check element types.

### 6.4. Avoid `instanceof` chains when polymorphism is enough

If behavior truly varies by subclass, object-oriented design typically places the method in the superclass and overrides it in each subclass:

```java
abstract class Animal {
    abstract String sound();
}

class Dog extends Animal {
    @Override
    String sound() {
        return "woof";
    }
}

class Cat extends Animal {
    @Override
    String sound() {
        return "meow";
    }
}
```

You can then call `animal.sound()` through an `Animal` reference without writing an `if (animal instanceof Dog) ...` chain. Prefer polymorphism when you **control the classes** and each class should provide its own behavior.

`instanceof` remains useful at boundaries that receive `Object`, when processing heterogeneous inputs, in adapters, or when you need an operation specific to a subclass that is absent from the superclass API.

## 7. Common mistakes

1. **Confusing declared type with runtime type:** `Animal x = new Dog()` still makes `x instanceof Dog` true.
2. **Assuming `instanceof Dog` only matches `Dog`:** `new Poodle()` also matches `Dog`; if you want an exact class match, consider `getClass()`.
3. **Checking the superclass before the subclass:** in an `else if` chain, `Dog` will catch `Poodle` as well; order checks from most specific to most general.
4. **Calling a subclass-only method on a superclass reference:** use a pattern variable, a valid cast, or move common behavior into a polymorphic design.
5. **Casting without verifying the type relationship:** a `Cat` cannot be cast to `Dog` at runtime.
6. **Forgetting `null`:** `instanceof` returns `false`, whereas `getClass()` throws an exception when the object is `null`.
7. **Using `instanceof` with primitive types or non-reifiable generic type arguments:** invalid in Java 17.
8. **Using `==` to compare types or content:** `==` between two object variables compares references; it does not check class relationships and does not replace `equals()`.

## 8. Practice exercises

1. Using `Animal`, `Dog`, `Poodle`, and `Cat` from Section 3, predict the `instanceof` results for `Animal x` pointing to `new Dog()`, `new Poodle()`, `new Cat()`, and `null` in turn. Check your answers against the table in Section 2.
2. Swap the order of `if (animal instanceof Poodle)` and `else if (animal instanceof Dog)` in `describe`. Run with `new Poodle()` and explain why the resulting branch changes.
3. Write a method `static String kind(Animal a)` that returns `"dog"` if `a instanceof Dog`, `"cat"` if `a instanceof Cat`, and `"other"` otherwise. For `new Poodle()`, the return value must be `"dog"`.
4. Rewrite an `instanceof Dog` check plus `(Dog)` cast as `instanceof Dog dog`. State the valid scope of `dog`.
5. Compare `new Poodle()` using `instanceof Dog` and `getClass() == Dog.class`. Explain when matching the exact runtime class is actually a business requirement.

**Key takeaway:** `instanceof` with a class name asks whether **the actual object belongs to that class or one of its subclasses**. It is especially useful before using subclass-specific behavior through a superclass-typed variable; in Java 17+, type patterns let you check and obtain a typed variable in a single expression.

## References

- [Java SE 17 — `instanceof` operator and pattern matching](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html).
- [Java Language Specification 17, §15.20.2 — Type Comparison Operator `instanceof`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2).
- [OpenJDK JEP 394 — Pattern Matching for `instanceof`](https://openjdk.org/jeps/394).
