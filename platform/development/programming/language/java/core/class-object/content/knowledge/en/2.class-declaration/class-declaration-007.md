# Class Modifiers and Invalid Combinations in Java

A **class modifier** is a keyword placed in a class declaration to specify the **accessibility**, **inheritability**, **instantiability**, or declaration characteristics of the class. The same keyword may be valid for a **top-level class**, a **member/nested class**, or only in another position. Some modifiers are valid individually, but **cannot be combined** because their meanings conflict with each other.

For example:

```java
public abstract class Animal {
    public abstract void sound();
}
```

In `public abstract class Animal`, `public` specifies the access scope; `abstract` indicates that the class cannot be instantiated directly using `new Animal()` and may contain abstract methods.

Conversely, the declaration `abstract final class Animal { }` is **invalid**: `abstract` allows a subclass to complete the missing parts, whereas `final` forbids inheritance. The goal of this article is to determine **which modifiers can be used where, which combinations make sense, and which cases are rejected by `javac`**.

## 1. Syntax and Three Questions to Distinguish

General syntax of a regular class:

```java
[annotations] [modifiers] class ClassName
        [extends Superclass]
        [implements Interface1, Interface2] {
    // class members
}
```

This is a **syntax diagram**, not Java code meant to be compiled verbatim. Square brackets indicate optional components.

When you see a modifier, check:

1. **Declaration position:** Is this a top-level class, a member class, or a local class inside a method/block?
2. **Element being modified:** Does the modifier affect **the class itself**, or does it precede a **method**, **field**, or **constructor**? The same word `final` has different effects depending on its position.
3. **Compatibility:** Does a modifier conflict with another modifier, an `extends`/`implements` clause, or `sealed` rules?

There is no `default` keyword to represent a class's "default access scope". **Omitting the access modifier** is how you declare a package-private class in contexts where it is allowed.

## 2. Top-Level Class Modifiers

A top-level class is a class declared directly in a source file, **not inside the body of another type**.

| Modifier | Valid for a top-level class? | Primary meaning |
| --- | --- | --- |
| `public` | **Yes** | The type can be accessed from another package if additional conditions regarding modules, the classpath, and the members being used are met |
| Omitting the access modifier | **Yes** | The class has **package-private** access |
| `abstract` | **Yes** | Cannot be instantiated directly; may contain abstract methods |
| `final` | **Yes** | Cannot be subclassed |
| `sealed` | **Yes** (Java 17+) | Restricts which classes may directly extend this class |
| `non-sealed` | **Conditionally yes** (Java 17+) | Removes the inheritance restriction on a direct subclass in a hierarchy with a `sealed` supertype |
| `strictfp` | **Yes**, though it has no practical effect since Java 17 | Historical modifier related to floating-point operations |
| `private` | **No** | Does not apply to top-level classes |
| `protected` | **No** | Does not apply to top-level classes |
| `static` | **No** | Only used with nested member classes in appropriate contexts |

**Note:** `sealed` and `non-sealed` are *contextual keywords/modifiers* starting in Java 17; in class declarations, they act as modifiers. `@Deprecated` and annotations are not access modifiers, even though they can appear before `class`.

Valid examples at the source-file level:

```java
public class Application { }

abstract class AbstractTask { }

final class Utility { }

class PackageHelper { }
```

This snippet illustrates declarations and has no `main` method. If placed together in a single file, name the file **`Application.java`** because `Application` is the `public` top-level type. The remaining classes are all package-private.

The rule of **at most one `public` top-level type in a `.java` file** applies to standard source organization and compilation with `javac`. If there is a `public` type, the file name must match that type's name (case-sensitive). The file-naming rule is a constraint of the **compilation unit**, separate from whether two modifiers on the **same class** are valid together.

## 3. `public` and Package-Private: Class Access Scope

### 3.1. Top-Level `public`

```java
package school;

public class Student {
    public String name() {
        return "An";
    }
}
```

Saved in `src/school/Student.java`. The class can be referenced by code in another package if it is loaded and accessible according to the module/classpath configuration. The `name()` method is also declared `public` so that code outside the package can call it.

`public` **does not mean every member inside the class is automatically `public`**. For example, an explicitly written `Student()` constructor without a modifier will be package-private; in the example above, however, because no constructor is declared, Java provides a default constructor with the same access level as the `public` class.

### 3.2. Top-Level Package-Private

```java
package school;

class StudentFormatter {
    static String upper(String text) {
        return text.toUpperCase();
    }
}
```

Saved in `src/school/StudentFormatter.java`. Writing neither `public` nor any access modifier before `class` makes `StudentFormatter` accessible only to code in the `school` package. Adding `import school.StudentFormatter;` from another package **does not expand** that access.

Two classes in **two different source files** that both declare `package school;` can still access each other's package-private types. Conversely, merely placing two files in the same directory with different package declarations does not put them in the same package.

### 3.3. Why Are `private class` and `protected class` Invalid at the File Level?

```java
private class Hidden { }        // INVALID if declared top-level
protected class Inherited { }   // INVALID if declared top-level
```

`private` and `protected` are not allowed modifiers on a top-level class. To hide details from other packages, **package-private** is typically used. If you want a type to actually be a `private` member of another class, you can declare a **private nested class** (see Section 7).

Do not write:

```java
default class Helper { }       // INVALID: default is not a class access modifier
```

"Default access" is an informal name for **omitting the access modifier**, not an instruction to add the `default` keyword.

## 4. `abstract`: A Class That Cannot Be Instantiated Directly

An **abstract class** is declared with `abstract` and **cannot be instantiated directly**. It can contain methods with bodies, abstract methods, fields, constructors, and other members permitted by Java.

For example:

```java
abstract class Animal {
    private final String name;

    protected Animal(String name) {
        this.name = name;
    }

    String name() {
        return name;
    }

    abstract String sound();
}

class Dog extends Animal {
    Dog(String name) {
        super(name);
    }

    @Override
    String sound() {
        return "Gâu";
    }
}
```

`Animal` is marked `abstract` and `Dog` is a concrete class that implements the `sound()` method. Code placed inside a method can write `Animal pet = new Dog("Milu");`, but **cannot** write `new Animal("Milu")` because `Animal` is abstract.

Important principles:

- A class with an `abstract` instance method **must** be an abstract class (aside from the separate rules for interfaces).
- An abstract class is **not required** to contain abstract methods. It is still useful to prevent direct instantiation or to serve as a base class in an inheritance design.
- An abstract class **can have constructors**, though those constructors are not used to create an `Animal` instance directly; a constructor is invoked during the creation of a subclass object.
- A concrete subclass must implement the abstract methods it inherits, except for those already appropriately implemented at an intermediate level; if it is not yet complete, the subclass must also be declared `abstract`.
- An abstract class **can still have `final` methods**. An "abstract class" and a "final method" do not contradict each other: the class can be inherited, while the final method itself cannot be overridden.

Invalid example:

```java
class Animal {
    abstract void sound();      // INVALID: class contains an abstract method but is not abstract
}
```

Valid example:

```java
abstract class Animal {
    final void breathe() {
        System.out.println("Thở");
    }

    abstract void sound();
}
```

This final `Animal` snippet is an independent illustrative declaration and must not be placed in the same package/source set as the earlier `Animal` class because their names would collide.

## 5. `final`: Prohibiting Class Inheritance

When `final` is placed before a class declaration, the class **cannot have subclasses**:

```java
final class Token {
    private final String value;

    Token(String value) {
        this.value = value;
    }

    String value() {
        return value;
    }
}
```

`Token` can be created with `new Token("abc")` wherever the constructor is accessible, whereas `class SpecialToken extends Token { }` will not compile. `final` **does not** mean the class cannot be instantiated; it only forbids **class inheritance**.

Three uses of `final` need to be distinguished:

| Position | Example | Effect |
| --- | --- | --- |
| Class | `final class Token { }` | Cannot `extends Token` |
| Method | `final void log() { }` | Subclasses cannot override that method |
| Variable / field | `final int id = 1;` | The variable cannot be reassigned after being properly initialized |

A `final class` is **not automatically immutable**. It can still have mutable fields:

```java
final class Counter {
    private int value;

    void increment() {
        value++;
    }

    int getValue() {
        return value;
    }
}
```

`Counter` cannot be inherited from, yet its instances still change state after each `increment()` call. Achieving immutability requires designing the fields, related objects, and API appropriately.

## 6. `sealed` and `non-sealed` in Java 17: Restricting the Inheritance Hierarchy

Java 17 supports **sealed classes** and **sealed interfaces**. `sealed` specifies **which types may be direct subclasses**; `permits` lists the permitted subtypes if the applicable list-inference mechanism is not used.

A **direct subclass** of a `sealed` type must declare one of three states:

- `final`: ends the inheritance branch at that class.
- `sealed`: continues controlling direct subclasses at the next level.
- `non-sealed`: opens this branch to further subclasses according to regular inheritance rules.

`abstract` can appear together with `sealed` or `non-sealed` because the two modifier groups address **instantiability** and **inheritance restriction** separately.

### 6.1. Complete Java 17 Example

Save the entire content below into **`ModifierDemo.java`**:

```java
public class ModifierDemo {
    public static void main(String[] args) {
        Shape a = new Square(3);
        Shape b = new Rectangle(2, 5);

        System.out.println("Square: " + a.area());
        System.out.println("Rectangle: " + b.area());
        System.out.println("Square type: " + (a instanceof Square));
        System.out.println("Rectangle type: " + (b instanceof Rectangle));
    }
}

abstract sealed class Shape permits Square, OpenShape {
    abstract int area();
}

final class Square extends Shape {
    private final int side;

    Square(int side) {
        this.side = side;
    }

    @Override
    int area() {
        return side * side;
    }
}

abstract non-sealed class OpenShape extends Shape {
    // This branch is permitted to have further subclasses.
}

class Rectangle extends OpenShape {
    private final int width;
    private final int height;

    Rectangle(int width, int height) {
        this.width = width;
        this.height = height;
    }

    @Override
    int area() {
        return width * height;
    }
}
```

Compile and run with **JDK 17 or later**:

```bash
javac -encoding UTF-8 ModifierDemo.java
java ModifierDemo
```

Expected output:

```text
Square: 9
Rectangle: 10
Square type: true
Rectangle type: true
```

Explanation of each modifier:

- `ModifierDemo` is **top-level `public`**; the file name must be `ModifierDemo.java` when using `javac` in the standard way.
- `Shape` is **`abstract sealed`**: `new Shape()` cannot be called directly; only **`Square` and `OpenShape`** are valid direct subclasses because they appear in `permits`.
- `Square` is **`final`**, so nothing can subclass `Square`.
- `OpenShape` is **`abstract non-sealed`**: it still cannot be instantiated directly, but allows subclasses such as `Rectangle` to extend this branch.
- `Rectangle` is **not a direct subclass** of `Shape` (it extends `OpenShape`), so it does not need to be in `Shape permits ...` and is not required to be declared `final`, `sealed`, or `non-sealed`.
- `sealed` does not automatically make a class abstract. A `sealed` class **without `abstract`** can still be instantiated directly if its constructor is accessible and the class satisfies the other rules.

Use `abstract sealed` when you want to prevent the base class from being instantiated directly and precisely restrict its derived types. Use `abstract non-sealed` when you want to allow the hierarchy to continue expanding through a permitted branch.

### 6.2. Multi-Level `sealed` Branches

The following snippet illustrates valid declaration forms (not a standalone program):

```java
sealed class Vehicle permits Car, Truck { }

final class Car extends Vehicle { }

sealed class Truck extends Vehicle permits SmallTruck { }

final class SmallTruck extends Truck { }
```

Here, `Vehicle` allows only `Car` and `Truck` to inherit **directly**. `Truck` is still `sealed`, so it must specify its valid direct subclass `SmallTruck`; `SmallTruck` closes the branch with `final`.

You cannot declare another subclass that directly `extends Vehicle` unless it is permitted in `permits`.

### 6.3. Source and Module Rules for `sealed`

- Permitted types must be **direct subtypes** via the appropriate `extends` or `implements`; merely being named in `permits` is not enough.
- In a **named module**, permitted direct subtypes must belong to the **same module** as the `sealed` type. In an **unnamed module**, they must belong to the **same package**.
- If all direct subclasses appear in the **same compilation unit**, `permits` can be **inferred** according to Java's rules; writing `permits` explicitly often helps learners and maintainers see the intent.
- `non-sealed` only makes sense when the class **directly extends or implements at least one `sealed` supertype**. You cannot use `non-sealed` standalone on an arbitrary regular class.
- Java restricts the **direct subtypes** of a `sealed` type; from a `non-sealed` branch, descendant classes can inherit according to normal rules.

## 7. Member/Nested Classes: Adding `private`, `protected`, and `static`

For a **member class** located inside another class, access modifiers and `static` can be used according to valid contexts.

Save as **`NestedDemo.java`**:

```java
public class NestedDemo {
    private final String owner;

    public NestedDemo(String owner) {
        this.owner = owner;
    }

    private class Label {
        String text() {
            return "Owner: " + owner;
        }
    }

    protected static class Formatter {
        static String bracket(String text) {
            return "[" + text + "]";
        }
    }

    public void show() {
        Label label = new Label();
        System.out.println(Formatter.bracket(label.text()));
    }

    public static void main(String[] args) {
        new NestedDemo("An").show();
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 NestedDemo.java
java NestedDemo
```

Stdout:

```text
[Owner: An]
```

- `NestedDemo` is top-level `public`.
- `Label` is a **private member inner class**; it belongs to the body of `NestedDemo` and is not declared `static`. A `Label` instance can access `owner` belonging to the enclosing `NestedDemo` instance.
- `Formatter` is a **protected static nested class**. `static` means it does not require an enclosing `NestedDemo` instance like the `Label` class does. `protected` is a valid access modifier for a member class; access from other classes is determined by Java's protected rules.
- `Formatter.bracket()` is a static method called via `Formatter` inside the enclosing class.
- `private` and `protected` are valid here **because `Label` and `Formatter` are inside the body of the `NestedDemo` class**, not at the file level.

Comparison table:

| Class context | Allowed access modifiers | `static`? | Notes |
| --- | --- | --- | --- |
| **Top-level class** | `public` or omit the modifier (package-private) | **No** | No enclosing class |
| **Member class inside a class** | `public`, `protected`, `private`, or omit the modifier | **Yes** | `static class` is a static nested class |
| **Local class inside a method/block** | Cannot use `public`, `protected`, `private` | **No** | Local classes have their own rules; can be `abstract` or `final` |
| **Anonymous class** | No `class Name` declaration line to place modifiers on | Not applicable | Instantiates and declares an unnamed class in a single expression |

**Invalid** examples when placed directly at the file level:

```java
private class FileHelper { }       // INVALID: private top-level
protected class FileFormatter { }  // INVALID: protected top-level
static class FileCache { }         // INVALID: static top-level
```

To make a class `private static`, it must be placed **inside** an enclosing type:

```java
class Service {
    private static final class InternalCache {
        // Nested class, private, static, and final: valid.
    }
}
```

A non-`static` member class is called an **inner class**, whereas a `static` member class is a **static nested class**. You should not call every class written in the same file a nested class: only declarations **actually located inside the body of another type** are member/nested classes.

## 8. Valid and Invalid Modifier Combinations

### 8.1. Common Combinations Table

| Declaration / combination | Result | Explanation |
| --- | --- | --- |
| `public class A` | **Valid** | Publicly accessible top-level class, when placed in file `A.java` |
| `abstract class A` | **Valid** | Can serve as a base class, cannot be instantiated directly |
| `final class A` | **Valid** | The class can be instantiated, but cannot be subclassed |
| `abstract sealed class A permits B` | **Conditionally valid** | `B` must be a valid direct subclass and declare `final`, `sealed`, or `non-sealed` |
| `abstract non-sealed class B extends A` | **Conditionally valid** | `A` must be an appropriate direct `sealed` supertype |
| `private static final class Helper` | **Valid for member classes** | The class must be inside the body of an appropriate type; it cannot be top-level |
| `static abstract class Nested` | **Valid for member classes** | An abstract static nested class |
| `abstract final class A` | **Invalid** | Requires inheritance for completion while simultaneously forbidding inheritance |
| `final sealed class A` | **Invalid** | `final` blocks all subclasses; `sealed` defines permitted subclasses |
| `sealed non-sealed class A` | **Invalid** | Cannot simultaneously close and open the same direct branch |
| `final non-sealed class A` | **Invalid** | `final` forbids inheritance; `non-sealed` opens inheritance |
| `non-sealed class A`, with no direct `sealed` supertype | **Invalid** | `non-sealed` has no sealed supertype to relax |
| `private class A` at file level | **Invalid** | `private` is not a top-level class modifier |
| `protected class A` at file level | **Invalid** | `protected` is not a top-level class modifier |
| `static class A` at file level | **Invalid** | Static top-level classes do not exist |
| `public private class A` | **Invalid** | Two conflicting access levels; at top-level it also violates the `private` rule |
| `public public class A` | **Invalid** | Duplicate `public` modifier |

The rows in the table describe **declaration patterns**, not declarations meant to be placed together in a single file: multiple patterns use the name `A` for comparison. When trying out each pattern, make sure there are no name collisions in the same package and follow the file-naming rule if the pattern includes `public`.

### 8.2. Why Is `abstract final` Invalid?

```java
abstract final class Impossible {
}
```

`abstract` means the class cannot be instantiated directly and is typically intended for subclasses to inherit/complete. `final` forbids all subclasses. The JLS prohibits this combination **even when the class body has no abstract methods**.

How to fix it depends on your intent:

- Need a **base class** that allows extension without direct instantiation: use `abstract class Base`.
- Need to **prevent inheritance** while still allowing instantiation: use `final class Value`.
- Need to **control a specific set of subclasses**: use `sealed class Base permits ...` and declare the appropriate subclasses.

No ordering of modifiers makes `abstract final` valid; reordering it to `final abstract` is still invalid.

### 8.3. Why Are `final sealed`, `sealed non-sealed`, and `final non-sealed` Invalid?

```java
final sealed class FrozenHierarchy { }          // INVALID
sealed non-sealed class ConflictingHierarchy { } // INVALID
final non-sealed class OpenYetFinal { }          // INVALID
```

The three states `final`, `sealed`, and `non-sealed` specify **three ways to manage inheritance at a class branch**: closing it completely, permitting subclasses selectively, or opening it freely after a sealed parent. Java does not allow attaching two of those states simultaneously to **a single class declaration**.

Specifically, `abstract` can accompany `sealed` or `non-sealed` because it specifies a different axis: **direct instantiability**.

### 8.4. Why Is Standalone `non-sealed` Invalid?

```java
non-sealed class FreeClass { }  // INVALID: no sealed direct supertype
```

The `non-sealed` keyword is not an alternative way to write a normal class. For a regular class where you want to allow inheritance, **simply omit `final` and `sealed`**:

```java
class FreeClass { }             // VALID
```

Only declare `non-sealed` when the class is a **direct child of a sealed class or a type that directly implements a sealed interface**, and you need to allow deeper subclasses.

### 8.5. Why Must a Subclass of a `sealed` Type Mark Its Inheritance State?

The following snippet is **invalid** even though `Leaf` is already listed in `permits`:

```java
sealed class Root permits Leaf { }

class Leaf extends Root { }     // INVALID: missing final / sealed / non-sealed
```

Fixed example:

```java
sealed class Root permits Leaf { }

final class Leaf extends Root { }    // VALID
```

If you want `Leaf` to have subclasses under regular inheritance, use `non-sealed class Leaf extends Root { }`. If you want `Leaf` to control its own subclasses, use `sealed class Leaf extends Root permits ...` and declare the valid branch.

A `sealed` type **does not have to be abstract**. If `Root` does not have `abstract` and its constructor is accessible, `new Root()` can be valid; `sealed` only restricts **which types can inherit directly**.

## 9. Keywords Commonly Mistaken for Class Modifiers

Not every keyword that appears inside a class body is permitted before a `class` declaration.

| Keyword | Where is it normally used? | Is it a modifier of a regular top-level class? |
| --- | --- | --- |
| `static` | Fields, methods, and member/nested classes | **No** |
| `synchronized` | Methods or `synchronized (...) { ... }` statements | **No** |
| `native` | Methods bound to a native implementation | **No** |
| `transient` | Fields (related to default serialization) | **No** |
| `volatile` | Fields to express visibility/access-ordering rules of the Java Memory Model | **No** |
| `default` | Interface `default` methods or the `default` branch in a `switch` | **No** |
| `strictfp` | Classes/interfaces/methods in historical syntax | **Yes**, though redundant since Java 17 |
| `extends` | Clause specifying a superclass or inherited interface depending on the declaration kind | **No**, it is another part of the declaration |
| `implements` | Clause specifying interfaces implemented by a class | **No**, it is another part of the declaration |
| `permits` | Clause on a sealed class/interface listing direct permitted subtypes | **No**, it is another part of the declaration |

Invalid examples:

```java
synchronized class Task { }    // INVALID: synchronized does not apply to classes
native class NativeTask { }    // INVALID: native does not apply to classes
volatile class State { }       // INVALID: volatile does not apply to classes
transient class Data { }       // INVALID: transient does not apply to classes
```

A `volatile` field **inside** a class can be completely valid, but that does not make `volatile` a class modifier.

**About `strictfp`:** Prior to Java 17, this modifier was related to requiring floating-point expressions to be evaluated under strict semantics. Since Java 17, Java consistently uses strict floating-point semantics, so `strictfp` is considered **obsolete in effect**, even though the syntax is still accepted in supported positions and `javac` may issue a warning. New Java 17 code rarely needs to declare `strictfp`.

**About `@Deprecated`:** the annotation is written before the declaration:

```java
@Deprecated
public class LegacyApi {
}
```

This is valid syntax if placed in `LegacyApi.java`. Annotations add metadata; they do not replace `public`, `final`, `abstract`, or class inheritance rules.

## 10. Declaration Kinds Other Than Regular Classes: interface, record, and enum

When moving from `class` to `interface`, `record`, or `enum`, do not mechanically apply the entire set of modifiers for regular classes.

- **Interface:** an interface is inherently abstract and cannot be declared `final`. It can be `sealed` or `non-sealed` when the rules are satisfied; classes that **directly implement** a sealed interface must comply with being marked `final`, `sealed`, or `non-sealed` if they are regular classes. Member types declared inside an interface have implicit modifier rules—for example, a member class is treated as `public static`.
- **Record:** a record class is implicitly **final** by language design, cannot `extends` an arbitrary class, and cannot be declared `abstract`. The primary purpose of a record is modeling structured data; do not use `sealed`/`non-sealed` on a record class itself to create inheritance branches.
- **Enum:** an enum has its own rules regarding inheritability and enum constants; another class cannot arbitrarily `extends` an enum.
- **Annotation type:** `@interface` declares an annotation type, not a regular `class` declaration; its valid set of modifiers must be evaluated according to annotation rules.

The practical takeaway is to always check the **declaration kind** before choosing modifiers. Most examples in this article focus on **class declarations** so as not to confuse the type-specific rules of each kind.

## 11. Guide to Diagnosing `javac` Errors

When encountering an error related to class modifiers:

1. **Check where the declaration begins:** Is `class A` at the file level, inside the body of a class/interface, or inside a method?
2. **Separate modifier groups:** access (`public`/`private`/`protected`), instantiation/inheritance (`abstract`, `final`, `sealed`, `non-sealed`), and nesting context (`static`).
3. **Check for conflicts:** especially `abstract final`, any pairwise combination of `final`/`sealed`/`non-sealed`, and duplicate or conflicting access modifiers.
4. **Check `extends`/`implements`:** Is a `final` class being extended; does a `non-sealed` class have a direct sealed supertype; is a direct subclass of a sealed type properly marked and permitted?
5. **Check the file name if `public` top-level:** `public class Report` belongs in `Report.java` under standard compilation rules.
6. **Read the actual error message:** `javac` usually points to the faulty declaration line. Exact wording depends on the JDK; there is no need to memorize the error messages word for word.

Practical example:

```java
// INVALID when declared top-level:
public static final class Toolbox { }
```

Reading through the checklist: `public` is valid top-level; `final` is also valid; **`static` is invalid at the top level**. Fix:

```java
// File: Toolbox.java
public final class Toolbox {
    private Toolbox() {
    }

    public static String hello() {
        return "Hello";
    }
}
```

`Toolbox` is now a valid `public final` top-level class with a static utility method and a private constructor to prevent calling the constructor from outside the class. Creating a utility class **does not require the `static` modifier on the class itself**.

If you want a `static class Toolbox`, declare it as a **member class** inside an enclosing class:

```java
class Container {
    static final class Toolbox {
        static String hello() {
            return "Hello";
        }
    }
}
```

In this case, `Toolbox` is a static nested class; it differs from top-level `Toolbox` in position and type name.

## 12. Self-Practice Exercises with Answers

**Exercise 1.** Which modifiers in the following declaration are invalid if the class is placed directly in a source file?

```java
private static final class Cache { }
```

**Answer:** `private` and `static` are invalid for a **top-level class**; `final` alone is valid. If `Cache` is moved inside the body of a class, the `private static final` combination can be valid.

**Exercise 2.** Can the declaration `abstract sealed class Base permits Child` be valid? Must the subclass `Child` also be `abstract`?

**Answer:** It can be valid if the `sealed` and direct-subclass requirements are met. `Child` **does not have to be abstract**; for example, `final class Child extends Base { }` is valid as long as no unimplemented abstract methods remain.

**Exercise 3.** Why does `non-sealed class A { }` normally result in an error, while `class A { }` does not?

**Answer:** `non-sealed` must belong to a branch that **directly extends or implements a sealed type**, whereas a regular class allows inheritance by default and does not need that special modifier.

**Exercise 4.** Consider:

```java
sealed class A permits B { }
non-sealed class B extends A { }
class C extends B { }
```

Are the declarations valid? **Yes.** `B` is a permitted direct branch of `A` and is marked `non-sealed`; `C` extends `B` under regular rules. `C` does not need to appear in `A permits ...`.

**Exercise 5.** Do `final class Config` and `final String name` have the same meaning?

**Answer:** No. The `final` modifier on a class forbids subclasses; the `final` modifier on a variable forbids reassigning the variable after it has been properly initialized. It does not automatically make all object state immutable.

**Exercise 6.** Can `private class Helper` and `protected static class Formatter` be used in the same Java file?

**Answer:** Yes, **if those classes are member classes inside the body of an enclosing class** and the corresponding modifiers are valid. They cannot be used directly at the file level.

## Summary

Keep four foundational rules in mind:

- **Top-level classes:** can be `public` or package-private (omitting the access modifier); **cannot be `private`, `protected`, or `static`**.
- **Instantiability/inheritance:** `abstract` prevents direct instantiation, `final` forbids inheritance, `sealed` allows only permitted direct subclasses, and `non-sealed` reopens inheritance from a sealed direct supertype.
- **Invalid combinations:** `abstract final`; any pair among `final`, `sealed`, and `non-sealed`; and modifiers inappropriate for the declaration position. `abstract sealed` and `abstract non-sealed` can be valid.
- **Member classes differ from top-level classes:** member classes can use `private`, `protected`, and `static` in appropriate contexts. Every declaration must also comply with file naming, access control, and sealed-type subclass contracts.
