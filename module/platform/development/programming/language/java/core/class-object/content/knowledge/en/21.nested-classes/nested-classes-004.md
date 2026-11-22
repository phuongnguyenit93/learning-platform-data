# Syntax for Creating `Outer.Nested` and `outer.new Inner` in Java

## Learning Objectives

After studying this, you will be able to:

- Distinguish between a **static nested class** and a **non-static member inner class**, two forms of member classes commonly declared inside an enclosing class.
- Correctly read the syntax `new Outer.Nested(...)` and `outer.new Inner(...)`; understand when an existing `Outer` object is required.
- Declare variable types using `Outer.Nested` or `Outer.Inner`, while understanding that **how a type is named** does not necessarily match **how an instance is created**.
- Predict that each inner object is bound to a specific **enclosing instance**; use `Outer.this` to reference the correct outer object when needed.
- Create an inner instance inside an instance method/constructor of Outer using `new Inner(...)` or `this.new Inner(...)`, and in a static context via an outer reference.
- Know why `new Outer.Inner()` is invalid for a non-static inner class from outside when an enclosing instance is missing; distinguish compile-time errors from a `NullPointerException` when the qualifier is null.
- Write constructors with parameters for Nested and Inner, choose the right syntax for passing arguments, and understand that the outer qualifier **is not a user-declared constructor argument**.
- Use nested classes with private members, static/instance members, access modifiers, generic outer types, and nested generic classes correctly in Java 17.
- Understand the differences from local classes, anonymous classes, member records, and nested interfaces; do not equate everything “declared inside” with an inner class.
- Recognize the impact on lifetime/aliasing, retaining an outer object through an inner reference, and storing inner instances from different outers in collections.
- Fix common errors on your own, run standalone Java 17+ examples, and verify reliable output.

## 1. Two Core Syntaxes

A class can contain two kinds of **member classes**:

~~~java
class Outer {
    static class Nested {
    }

    class Inner {
    }
}
~~~

From another class in the same accessible scope:

~~~java
Outer.Nested nested = new Outer.Nested();

Outer outer = new Outer();
Outer.Inner inner = outer.new Inner();
~~~

**Important differences:**

- `Nested` is declared `static` in `Outer`; to create an instance, use `new Outer.Nested()`. You do not need to create an Outer object first.
- `Inner` is **not** declared `static`; to create an instance from outside, you must first have an **Outer object** such as `outer`. Use `outer.new Inner()`.
- `Outer.Inner` **is still a valid type name** when declaring variables, even though the syntax to create an instance is `outer.new Inner()`.
- An `Inner` object is bound to a specific enclosing `Outer` object. A `Nested` object does not have an **automatic enclosing Outer instance** like Inner.

Separate two questions:

1. **What is the data type?** → `Outer.Nested` or `Outer.Inner`.
2. **How is the object created?** → `new Outer.Nested(...)` or `outer.new Inner(...)`.

Do not treat the presence of the dot in `Outer.Inner` in the **type name** as proof that you can write `new Outer.Inner()`.

## 2. Instance Relationship Diagram

For static nested:

~~~text
Outer class
    |
    +--- member class: static Nested

new Outer.Nested()
        |
        v
  [Nested object]

No accompanying [Outer object] needed.
~~~

For member inner:

~~~text
Outer outer = new Outer();
Outer.Inner inner = outer.new Inner();

outer -----------------------> [Outer object]
                                    ^
                                    |
                          enclosing instance
                                    |
inner -----------------------> [Inner object]
~~~

The second diagram depicts the **enclosing instance link**: Inner is created via `outer`, so it can use `Outer.this` to access that outer. This does not mean Java clones/copies outer each time an Inner is created.

One Outer object can create multiple Inner objects. A variable of type `Outer.Inner` can also hold an inner created from another Outer, as long as the reference/type/access is valid. The type `Outer.Inner` does not encode the **specific** identity of the enclosing outer in the type name.

## 3. First Runnable Program: Both Types in One File

Save **`NestedCreationDemo.java`**:

~~~java
public class NestedCreationDemo {
    static class Outer {
        private final String name;
        private static final String FAMILY = "Java";

        Outer(String name) {
            this.name = name;
        }

        static class Nested {
            String describe() {
                return "Nested@" + FAMILY;
            }
        }

        class Inner {
            String describe() {
                return "Inner@" + name;
            }
        }
    }

    public static void main(String[] args) {
        Outer.Nested nested = new Outer.Nested();

        Outer outer = new Outer("Alpha");
        Outer.Inner inner = outer.new Inner();

        System.out.println(nested.describe());
        System.out.println(inner.describe());
        System.out.println("different types=" +
                !nested.getClass().equals(inner.getClass()));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac NestedCreationDemo.java
java NestedCreationDemo
~~~

**Stdout:**

~~~text
Nested@Java
Inner@Alpha
different types=true
~~~

In this file, `Outer` is a **static member class of the demo class** simply so that the program has one `public` top-level class and is easy to run; inside `Outer`, `static class Nested` and `class Inner` are declared. The syntax to learn remains exact: `new Outer.Nested()` and `outer.new Inner()`.

`Nested.describe()` directly uses the static field `FAMILY`. `Inner.describe()` uses the instance field `name` of the enclosing Outer. Having an instance method `describe()` on `Nested` is completely normal: **a static nested class does not mean all methods/fields of Nested itself must be static**.

## 4. “Static” Belongs to the Nesting Relationship, Not Each Object's State

Consider:

~~~java
class Outer {
    static class Nested {
        private int counter;

        void increment() {
            counter++;
        }
    }
}
~~~

Each `new Outer.Nested()` call still creates a Nested object with an independent `counter` instance field. The `static` keyword on the Nested declaration only says that **Nested does not need an enclosing Outer instance**.

A static nested class can:

- Have constructors, instance fields, and instance methods like a regular class.
- Have its own static members.
- Extend a class, implement interfaces, and have generic type parameters.
- Access static members of Outer according to access rules.
- Access an Outer instance **if provided an explicit reference**, rather than having an automatic `Outer.this`.

**Incorrect:** “`Outer.Nested` has no object instances because it is static”.  
**Correct:** “`Outer.Nested` has normal object instances, but is not implicitly attached to a specific Outer object”.

## 5. Program: Two Nested Objects with Separate State

Save **`StaticNestedStateDemo.java`**:

~~~java
public class StaticNestedStateDemo {
    static class Outer {
        private static final String PREFIX = "count";

        static class Nested {
            private int value;

            Nested(int initial) {
                value = initial;
            }

            void increase() {
                value++;
            }

            String report() {
                return PREFIX + "=" + value;
            }
        }
    }

    public static void main(String[] args) {
        Outer.Nested first = new Outer.Nested(2);
        Outer.Nested second = new Outer.Nested(10);

        first.increase();
        first.increase();
        second.increase();

        System.out.println("first " + first.report());
        System.out.println("second " + second.report());
    }
}
~~~

Run:

~~~bash
javac StaticNestedStateDemo.java
java StaticNestedStateDemo
~~~

Output:

~~~text
first count=4
second count=11
~~~

The two Nested objects **do not share the instance field `value`**. Both have permission to read Outer's static `PREFIX` due to Java access/nesting rules, but their `value` fields are initialized separately.

## 6. Enclosing Instance of `Inner`

A non-static member inner class can access instance fields/methods of **the enclosing object bound to it**, including private members under Java access rules.

~~~java
class Outer {
    private String name = "A";

    class Inner {
        String show() {
            return Outer.this.name;
        }
    }
}
~~~

`Outer.this` is a **qualified this**: it refers to the enclosing Outer instance of the current inner object. It differs from `this`, which refers to **the current Inner object** when used inside an Inner instance method.

If you create two Outer objects and then create an Inner from each Outer, each Inner keeps a link to its corresponding Outer. Changes to a mutable field of an Outer can be observed by the Inner bound to it.

### 6.1. Program Demonstrating Multiple Enclosing Instances

Save **`EnclosingInstanceDemo.java`**:

~~~java
public class EnclosingInstanceDemo {
    static class Outer {
        private String label;

        Outer(String label) {
            this.label = label;
        }

        void rename(String next) {
            label = next;
        }

        class Inner {
            private final int index;

            Inner(int index) {
                this.index = index;
            }

            boolean belongsTo(Outer candidate) {
                return Outer.this == candidate;
            }

            String describe() {
                return label + "#" + index;
            }
        }
    }

    public static void main(String[] args) {
        Outer left = new Outer("Left");
        Outer right = new Outer("Right");

        Outer.Inner a = left.new Inner(1);
        Outer.Inner b = right.new Inner(1);

        System.out.println("a owner left=" + a.belongsTo(left));
        System.out.println("a owner right=" + a.belongsTo(right));
        System.out.println("b owner right=" + b.belongsTo(right));
        System.out.println("a=" + a.describe());
        System.out.println("b=" + b.describe());

        left.rename("Changed");

        System.out.println("a after change=" + a.describe());
        System.out.println("b after change=" + b.describe());
    }
}
~~~

Compile/run:

~~~bash
javac EnclosingInstanceDemo.java
java EnclosingInstanceDemo
~~~

Stdout:

~~~text
a owner left=true
a owner right=false
b owner right=true
a=Left#1
b=Right#1
a after change=Changed#1
b after change=Right#1
~~~

`a` is linked to `left` and `b` is linked to `right`. Both Inner references have the same **static type `Outer.Inner`**, but separate enclosing objects.

`left.rename` is a mutation of the **Outer object**, not a reassignment of Inner's enclosing instance. `a`'s link to left remains intact, so `a.describe()` reads the new state of left itself.

## 7. When Creating Outside Outer: Required Syntax for Inner

Inside an instance method of a class **other than Outer** and without an implicit enclosing Outer instance, the valid syntax is:

~~~java
Outer outer = new Outer();
Outer.Inner item = outer.new Inner();
~~~

Here it is assumed that Outer/Inner have appropriate no-argument constructors and are both accessible.

You can create a temporary Outer and immediately create an Inner:

~~~java
Outer.Inner item = new Outer().new Inner();
~~~

This does not create an “Inner without an outer”. An Outer object is still created; you simply do not store its reference in a separate local variable. The Inner is still linked to that Outer.

If the Outer constructor takes arguments:

~~~java
Outer.Inner item = new Outer("A").new Inner(7);
~~~

`"A"` is passed to the **Outer constructor**, and `7` is passed to the **Inner constructor**. The constructors and accessibility must be appropriate.

### 7.1. Two Syntaxes That Are Easy to Get Wrong

~~~java
// Outer.Inner bad = new Outer.Inner();
// Invalid when Inner is a non-static member class from this context:
// no enclosing Outer instance is provided.

// Outer.Inner bad = new Inner();
// Invalid in a context without an appropriate enclosing Outer
// and without Inner imported/resolved as an appropriate type.
~~~

The commented-out invalid lines **are not standalone runnable examples**. Actual diagnostics depend on the compiler and how the code is placed in scope.

**Comparison:**

~~~java
Outer.Nested nested = new Outer.Nested(); // static member class.
Outer.Inner inner = outer.new Inner();    // non-static member class.
~~~

Although the **type name** declarations both start with `Outer.`, the expression after the `new` keyword differs depending on whether there is an **enclosing instance**.

## 8. Constructor Arguments: `outer` Is Not a Formal Parameter

Example:

~~~java
class Outer {
    private final String prefix;

    Outer(String prefix) {
        this.prefix = prefix;
    }

    class Inner {
        private final int number;

        Inner(int number) {
            this.number = number;
        }

        String text() {
            return prefix + number;
        }
    }
}
~~~

Creation:

~~~java
Outer outer = new Outer("ID-");
Outer.Inner inner = outer.new Inner(42);
~~~

The constructor `Inner(int number)` declares exactly **one** parameter: number. The `outer.` part only provides the enclosing instance according to language rules, **not an int/String argument or an `Outer` parameter declared by the programmer in the constructor signature**.

If you want the inner API to accept another Outer as a business parameter, you can explicitly declare an additional `Outer someOther`, but it **does not replace** the enclosing instance passed by the qualified creation syntax.

## 9. Program: Separate Outer Constructor and Inner Constructor

Save **`NestedConstructorDemo.java`**:

~~~java
public class NestedConstructorDemo {
    static class Outer {
        private final String prefix;

        Outer(String prefix) {
            this.prefix = prefix;
        }

        static class Nested {
            private final int id;

            Nested(int id) {
                this.id = id;
            }

            String display() {
                return "Nested-" + id;
            }
        }

        class Inner {
            private final int id;

            Inner(int id) {
                this.id = id;
            }

            String display() {
                return prefix + id;
            }
        }
    }

    public static void main(String[] args) {
        Outer.Nested staticMember = new Outer.Nested(7);

        Outer outer = new Outer("ORD-");
        Outer.Inner inner = outer.new Inner(42);
        Outer.Inner oneExpression =
                new Outer("TMP-").new Inner(9);

        System.out.println(staticMember.display());
        System.out.println(inner.display());
        System.out.println(oneExpression.display());
    }
}
~~~

Run:

~~~bash
javac NestedConstructorDemo.java
java NestedConstructorDemo
~~~

Output:

~~~text
Nested-7
ORD-42
TMP-9
~~~

`new Outer.Nested(7)` only calls the Nested constructor. `outer.new Inner(42)` creates an Inner bound to the existing Outer. `new Outer("TMP-").new Inner(9)` creates a new Outer and then creates an Inner bound to that Outer, even without a local `outer` variable holding the reference.

## 10. Inside an Instance Method of Outer: Using `new Inner()`

When code is running inside an instance context of Outer itself, Java already has an **implicit** enclosing instance: Outer's `this`.

~~~java
class Outer {
    class Inner {
    }

    Inner create() {
        return new Inner();
    }
}
~~~

Inside `Outer.create()`, `new Inner()` is equivalent in terms of the enclosing instance to `this.new Inner()`.

### 10.1. Is `this.new Inner()` Valid?

Yes, inside an Outer instance context and when Inner is an appropriate member class:

~~~java
Inner createAnother() {
    return this.new Inner();
}
~~~

The explicit form is useful for emphasizing the outer instance, though `new Inner()` is usually more concise and natural when there is no ambiguity about the enclosing context.

### 10.2. What About Inside a `static` Method?

A `static` method **does not have an Outer `this`**. Therefore, you cannot simply write `new Inner()` inside a static method of Outer without providing an enclosing Outer.

You need:

~~~java
static Inner createFor(Outer owner) {
    return owner.new Inner();
}
~~~

Or if a new Outer is genuinely needed:

~~~java
static Inner createWithNewOwner() {
    return new Outer().new Inner();
}
~~~

All snippets in this section assume an Outer with corresponding constructors and member Inner, with valid access.

## 11. Runnable Program: Instance Context and Static Context

Save **`CreationContextDemo.java`**:

~~~java
public class CreationContextDemo {
    static class Outer {
        private final String name;

        Outer(String name) {
            this.name = name;
        }

        class Inner {
            String say() {
                return name;
            }
        }

        Inner makeImplicit() {
            return new Inner();
        }

        Inner makeExplicit() {
            return this.new Inner();
        }

        static Inner makeFrom(Outer supplied) {
            return supplied.new Inner();
        }

        static Inner makeFresh() {
            return new Outer("Fresh").new Inner();
        }
    }

    public static void main(String[] args) {
        Outer current = new Outer("Current");

        Outer.Inner a = current.makeImplicit();
        Outer.Inner b = current.makeExplicit();
        Outer.Inner c = Outer.makeFrom(current);
        Outer.Inner d = Outer.makeFresh();

        System.out.println("implicit=" + a.say());
        System.out.println("explicit=" + b.say());
        System.out.println("supplied=" + c.say());
        System.out.println("fresh=" + d.say());
    }
}
~~~

Run:

~~~bash
javac CreationContextDemo.java
java CreationContextDemo
~~~

Output:

~~~text
implicit=Current
explicit=Current
supplied=Current
fresh=Fresh
~~~

The paths to create inner differ, yet `a`, `b`, and `c` are all bound to Outer `current`; `d` is bound to a different Outer object created by the static factory.

## 12. A Static Nested Class Can Still Use an Outer Instance If Passed a Reference

There is no **implicit** enclosing Outer in a static nested class, but Java does not forbid Nested from receiving an Outer reference via a constructor, method, or field.

~~~java
class Outer {
    private String state = "ready";

    static class Nested {
        String from(Outer owner) {
            return owner.state;
        }
    }
}
~~~

Nested is permitted to read private `Outer.state` if it has an appropriate `owner` object due to nested-class private access rules. This does **not** mean Nested has an `Outer.this`.

### 12.1. Runnable Program

Save **`StaticNestedAccessDemo.java`**:

~~~java
public class StaticNestedAccessDemo {
    static class Outer {
        private static final String VERSION = "v1";
        private final String state;

        Outer(String state) {
            this.state = state;
        }

        static class Nested {
            String showVersion() {
                return VERSION;
            }

            String showStateOf(Outer owner) {
                return owner.state;
            }
        }

        class Inner {
            String showOwnState() {
                return state;
            }
        }
    }

    public static void main(String[] args) {
        Outer.Nested nested = new Outer.Nested();

        Outer first = new Outer("A");
        Outer second = new Outer("B");

        System.out.println("version=" + nested.showVersion());
        System.out.println("first=" + nested.showStateOf(first));
        System.out.println("second=" + nested.showStateOf(second));

        Outer.Inner inner = first.new Inner();
        System.out.println("inner=" + inner.showOwnState());
    }
}
~~~

Run:

~~~bash
javac StaticNestedAccessDemo.java
java StaticNestedAccessDemo
~~~

Output:

~~~text
version=v1
first=A
second=B
inner=A
~~~

`Nested.showStateOf(first)` reads the state of the **explicitly passed Outer**. Meanwhile, `Inner.showOwnState()` uses the enclosing Outer bound **when Inner is created**.

## 13. `this`, `Outer.this`, and Field Name Shadowing

Inside an Inner method:

- `this` is the Inner object.
- `Outer.this` is the enclosing Outer instance.
- Accessing the simple name `name` follows name resolution rules; if Inner declares a field with the same name as Outer, the Inner field can shadow the Outer field.
- `Outer.this.name` always explicitly specifies the field of the corresponding enclosing Outer.

### 13.1. Program Distinguishing the Two Forms of `this`

Save **`QualifiedThisDemo.java`**:

~~~java
public class QualifiedThisDemo {
    static class Outer {
        private final String name;

        Outer(String name) {
            this.name = name;
        }

        class Inner {
            private final String name;

            Inner(String name) {
                this.name = name;
            }

            String bothNames() {
                return this.name + "/" + Outer.this.name;
            }

            boolean isInner(Object candidate) {
                return this == candidate;
            }

            boolean isOwner(Outer candidate) {
                return Outer.this == candidate;
            }
        }
    }

    public static void main(String[] args) {
        Outer owner = new Outer("Outer");
        Outer.Inner child = owner.new Inner("Inner");

        System.out.println("names=" + child.bothNames());
        System.out.println("this is child=" + child.isInner(child));
        System.out.println("outer is owner=" + child.isOwner(owner));
    }
}
~~~

Run:

~~~bash
javac QualifiedThisDemo.java
java QualifiedThisDemo
~~~

Output:

~~~text
names=Inner/Outer
this is child=true
outer is owner=true
~~~

Do not confuse `this.name` with `Outer.this.name` when Inner and Outer declare fields with the same name. Also do not use `Outer.this` inside a static nested class: Nested has no implicit enclosing instance for qualified-this to reference.

## 14. When the Qualifier `outer` Is `null`

The expression:

~~~java
Outer outer = null;
Outer.Inner inner = outer.new Inner();
~~~

is allowed by the compiler if the Outer/Inner types and access rights are valid, but **at runtime it will throw a `NullPointerException`** when attempting to create an inner via a null enclosing reference.

This is **not** a `ClassCastException` or a checked-exception-style “unable to create Outer” error. Nor is an Outer object automatically created in place of null.

### 14.1. Verifiable Error-Catching Program

Save **`NullOuterDemo.java`**:

~~~java
public class NullOuterDemo {
    static class Outer {
        class Inner {
            String text() {
                return "created";
            }
        }
    }

    public static void main(String[] args) {
        Outer owner = null;

        try {
            Outer.Inner value = owner.new Inner();
            System.out.println(value.text());
        } catch (NullPointerException expected) {
            System.out.println("null enclosing instance");
        }

        Outer valid = new Outer();
        Outer.Inner safe = valid.new Inner();
        System.out.println(safe.text());
    }
}
~~~

Run:

~~~bash
javac NullOuterDemo.java
java NullOuterDemo
~~~

Output:

~~~text
null enclosing instance
created
~~~

You should not rely on the verbatim text of the exception message or stack trace, as it may differ across JDKs. The example catches by **exception type** and prints an explicit message to keep stdout stable.

## 15. Changing the Outer Reference After Inner Is Created

`outer.new Inner()` binds the Inner object to the **current Outer object** that `outer` references at creation time, not to the **local variable outer** itself.

If the `outer` variable is later assigned a reference to another Outer, the already-created Inner **does not change its owner**.

### 15.1. Program Testing the Binding

Save **`OwnerReassignmentDemo.java`**:

~~~java
public class OwnerReassignmentDemo {
    static class Outer {
        private final String id;

        Outer(String id) {
            this.id = id;
        }

        class Inner {
            String ownerId() {
                return Outer.this.id;
            }
        }
    }

    public static void main(String[] args) {
        Outer owner = new Outer("A");
        Outer.Inner oldInner = owner.new Inner();

        owner = new Outer("B");
        Outer.Inner newInner = owner.new Inner();

        System.out.println("old owner=" + oldInner.ownerId());
        System.out.println("new owner=" + newInner.ownerId());
    }
}
~~~

Run:

~~~bash
javac OwnerReassignmentDemo.java
java OwnerReassignmentDemo
~~~

Output:

~~~text
old owner=A
new owner=B
~~~

The line `owner = new Outer("B")` only reassigns the outer variable in the caller; it does not alter the enclosing instance link of `oldInner`.

## 16. Inner Bound to Outer Affects Lifetime and Memory

When an inner object is still referenced, the enclosing outer object **can remain reachable** through the inner's link. If you retain inner objects long-term in a static list/cache, you can unintentionally extend the lifetime of large Outer objects.

~~~text
Long-lived collection
       |
       v
   Inner object
       |
       v
 enclosing Outer
       |
       v
 outer's other data
~~~

**This is not a claim that “Inner always causes memory leaks”.** Garbage collection is based on reachability; retaining a reference to Inner may also be the intended design. The problem arises when the program expects Outer to be reclaimed, yet a long-lived structure still holds an Inner.

With a **static nested class**, there is no implicit enclosing Outer instance. Therefore, static nested classes are often suitable for helpers that do not need the state of a specific Outer.

### 16.1. When Is an Explicit Outer Reference Needed?

If the helper occasionally needs Outer, a static nested class can receive the reference in a method:

~~~java
Outer.Nested helper = new Outer.Nested();
helper.process(outer);
~~~

This illustration requires `Nested.process(Outer)` to be declared appropriately. The helper does not necessarily keep outer as a field after the method finishes.

If the helper must work with **a fixed Outer throughout its lifetime**, Inner can express that relationship clearly and conveniently, though lifetime/ownership must be considered.

## 17. Access Rules and Constructor Visibility

Having the right creation syntax **is not enough** to compile. Outer, Nested/Inner, and constructors must be accessible from the call site.

~~~java
public class Outer {
    public static class Nested {
        public Nested() {
        }
    }

    public class Inner {
        public Inner() {
        }
    }
}
~~~

This is a valid **standalone top-level class** in the file `Outer.java`. If located outside Outer's package:

~~~java
Outer.Nested a = new Outer.Nested();
Outer outer = new Outer();
Outer.Inner b = outer.new Inner();
~~~

can be valid when `Outer` is imported properly and all types/constructors are public as shown above.

If Inner is `private class Inner`, code outside Outer cannot use `Outer.Inner`/`outer.new Inner()` simply by having an Outer reference. Outer can create it within its own body and expose its behavior through another API.

### 17.1. `private` Between Outer and Member Classes

Java allows member classes to access private members of the enclosing class and outer to access private members of nested classes under access rules within nested declarations. Since Java 11, the JVM has the *nestmates* mechanism to support private access; this is not a reason to expose fields carelessly.

### 17.2. Program Where Private Member Classes Are Created Only by Outer

Save **`PrivateNestedAccessDemo.java`**:

~~~java
public class PrivateNestedAccessDemo {
    static class Outer {
        private static class HiddenNested {
            String name() {
                return "hidden nested";
            }
        }

        private class HiddenInner {
            String name() {
                return "hidden inner";
            }
        }

        String useHiddenClasses() {
            HiddenNested a = new HiddenNested();
            HiddenInner b = new HiddenInner();
            return a.name() + " + " + b.name();
        }
    }

    public static void main(String[] args) {
        Outer outer = new Outer();
        System.out.println(outer.useHiddenClasses());

        // Outer.HiddenNested denied = new Outer.HiddenNested();
        // Outer.HiddenInner denied = outer.new HiddenInner();
        // Both lines are commented out because private member types are not
        // accessible from this NestedAccessDemo main.
    }
}
~~~

Run:

~~~bash
javac PrivateNestedAccessDemo.java
java PrivateNestedAccessDemo
~~~

Output:

~~~text
hidden nested + hidden inner
~~~

**Important:** an external class file or a different scope only sees the exposed API. The `new Outer.Nested` and `outer.new Inner` syntax **does not bypass Java access control**.

## 18. Generic Outer: Inner Variable Type Carries Outer's Type Argument

If Outer is generic:

~~~java
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    class Inner {
        T read() {
            return value;
        }
    }
}
~~~

From outside:

~~~java
Box<String> box = new Box<>("hello");
Box<String>.Inner inner = box.new Inner();
String text = inner.read();
~~~

The exact type name of the inner instance can carry `Box<String>.Inner`, because Inner is non-static and can use the type parameter `T` of the enclosing Box.

### 18.1. Static Nested Class Inside a Generic Outer

A static nested class **has no enclosing generic instance** and cannot use Outer's type parameter `T` as an instance member type variable in its own class declaration. It can declare its own type parameter:

~~~java
class Box<T> {
    static class Nested<U> {
        U value;
    }
}
~~~

Creation:

~~~java
Box.Nested<Integer> x = new Box.Nested<>();
~~~

**Do not use** `Box<String>.Nested<Integer>` as a way to bind a static nested class to a Box<String> instance. A static nested class is identified via the raw enclosing type name `Box.Nested` and its own parameters (if any).

## 19. Complete Generic Program

Save **`GenericMemberCreationDemo.java`**:

~~~java
public class GenericMemberCreationDemo {
    static class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        class Inner {
            T read() {
                return value;
            }
        }

        static class Nested<U> {
            private final U data;

            Nested(U data) {
                this.data = data;
            }

            U read() {
                return data;
            }
        }
    }

    public static void main(String[] args) {
        Box<String> words = new Box<>("hello");
        Box<String>.Inner inner = words.new Inner();

        Box<Integer> numbers = new Box<>(7);
        Box<Integer>.Inner other = numbers.new Inner();

        Box.Nested<Double> nested = new Box.Nested<>(2.5);

        System.out.println("words=" + inner.read());
        System.out.println("number=" + other.read());
        System.out.println("nested=" + nested.read());
    }
}
~~~

Run:

~~~bash
javac GenericMemberCreationDemo.java
java GenericMemberCreationDemo
~~~

Output:

~~~text
words=hello
number=7
nested=2.5
~~~

With `Box<T>.Inner`, `T` comes from the actual Box type, giving `inner.read()` the corresponding compile-time type. With `Box.Nested<U>`, `U` belongs to Nested and does not depend on any Box instance.

### 19.1. Raw Types Warning

If you use `Box raw = new Box(...); Box.Inner inner = raw.new Inner();`, the code can encounter unchecked/raw-type warnings and lose type information. In modern Java, prefer a safe generic type such as `Box<String>.Inner`.

## 20. Multiple Inner Levels: Each Level Has Its Own Qualifier

You can nest further:

~~~java
class Outer {
    class Middle {
        class Leaf {
        }
    }
}
~~~

From outside:

~~~java
Outer outer = new Outer();
Outer.Middle middle = outer.new Middle();
Outer.Middle.Leaf leaf = middle.new Leaf();
~~~

`Leaf` is an inner of `Middle`, and `Middle` is an inner of `Outer`. In each qualified creation, the qualifier is the **corresponding immediate enclosing object**.

**Do not write** `outer.new Leaf()` if Leaf is not a direct member class or an inherited member class resolvable from Outer; here, the name `Leaf` belongs to Middle.

### 20.1. Complete Program with Two qualified-this References

Save **`MultiLevelInnerDemo.java`**:

~~~java
public class MultiLevelInnerDemo {
    static class Outer {
        private final String name;

        Outer(String name) {
            this.name = name;
        }

        class Middle {
            private final String section;

            Middle(String section) {
                this.section = section;
            }

            class Leaf {
                private final int number;

                Leaf(int number) {
                    this.number = number;
                }

                String describe() {
                    return Outer.this.name + "/"
                            + Middle.this.section + "/"
                            + number;
                }
            }
        }
    }

    public static void main(String[] args) {
        Outer outer = new Outer("O");
        Outer.Middle middle = outer.new Middle("M");
        Outer.Middle.Leaf leaf = middle.new Leaf(3);

        System.out.println(leaf.describe());

        Outer.Middle.Leaf another =
                new Outer("X").new Middle("Y").new Leaf(5);
        System.out.println(another.describe());
    }
}
~~~

Run:

~~~bash
javac MultiLevelInnerDemo.java
java MultiLevelInnerDemo
~~~

Output:

~~~text
O/M/3
X/Y/5
~~~

`Outer.this` and `Middle.this` in Leaf access the exact two enclosing instances in the chain. Writing a single expression `new Outer("X").new Middle("Y").new Leaf(5)` creates each enclosing instance sequentially.

## 21. Inner Does Not Mean “Only One Object Can Be Created”

Each time:

~~~java
Outer.Inner one = outer.new Inner();
Outer.Inner two = outer.new Inner();
~~~

normally creates two distinct Inner objects, **with the same enclosing Outer**. Outer can have any number of Inner instances depending on the program; there is no implicit singleton limit.

An Outer class can also have both a `static Nested` and an `Inner` with their own constructors/methods. Nested being static does not by itself determine the identity/equality of Nested instances; if `equals` is not overridden, Object equality is generally based on identity.

## 22. Program: Multiple Inner Objects with the Same Outer

Save **`ManyInnerObjectsDemo.java`**:

~~~java
public class ManyInnerObjectsDemo {
    static class Outer {
        private final String ownerName;

        Outer(String ownerName) {
            this.ownerName = ownerName;
        }

        class Inner {
            private final int number;

            Inner(int number) {
                this.number = number;
            }

            String label() {
                return ownerName + ":" + number;
            }

            boolean sameOwner(Inner other) {
                return Outer.this == other.owner();
            }

            Outer owner() {
                return Outer.this;
            }
        }
    }

    public static void main(String[] args) {
        Outer a = new Outer("A");
        Outer b = new Outer("B");

        Outer.Inner first = a.new Inner(1);
        Outer.Inner second = a.new Inner(2);
        Outer.Inner third = b.new Inner(3);

        System.out.println("first==second=" + (first == second));
        System.out.println("first & second owner=" +
                first.sameOwner(second));
        System.out.println("first & third owner=" +
                first.sameOwner(third));

        System.out.println(first.label());
        System.out.println(second.label());
        System.out.println(third.label());
    }
}
~~~

Run:

~~~bash
javac ManyInnerObjectsDemo.java
java ManyInnerObjectsDemo
~~~

Output:

~~~text
first==second=false
first & second owner=true
first & third owner=false
A:1
A:2
B:3
~~~

Two different inner objects can share a single enclosing Outer object, and checking the owner here uses `==` to compare the **reference identity** of Outer, not content equality of the names.

## 23. Inner and Nested Inside Another Static Nested Context

A `static class Helper` inside Outer does not have an automatic `Outer.this`. If you want to create Outer.Inner from Helper, Helper must have an explicit Outer reference:

~~~java
class Outer {
    class Inner {
    }

    static class Helper {
        Inner make(Outer owner) {
            return owner.new Inner();
        }
    }
}
~~~

The method `Helper.make` can be an instance method of Helper, but that does not turn Helper into an **enclosing Outer instance**. Both a static nested class and another top-level class require an explicit `owner` to create Outer.Inner.

### 23.1. Runnable Program

Save **`NestedHelperCreationDemo.java`**:

~~~java
public class NestedHelperCreationDemo {
    static class Outer {
        private final String tag;

        Outer(String tag) {
            this.tag = tag;
        }

        class Inner {
            String tag() {
                return Outer.this.tag;
            }
        }

        static class Helper {
            Inner create(Outer owner) {
                return owner.new Inner();
            }
        }
    }

    public static void main(String[] args) {
        Outer owner = new Outer("Owner");
        Outer.Helper helper = new Outer.Helper();
        Outer.Inner inner = helper.create(owner);

        System.out.println("inner tag=" + inner.tag());
    }
}
~~~

Run:

~~~bash
javac NestedHelperCreationDemo.java
java NestedHelperCreationDemo
~~~

Output:

~~~text
inner tag=Owner
~~~

The key point is not whether Helper has instance or static methods, but that Helper **is not automatically bound to an Outer object** merely because Helper is declared nested static.

## 24. Java 17 and Static Members Inside Inner

Many older Java resources state that an inner class cannot declare static members except constant variables. This syntax restriction has changed: **Java 16 onward** allows inner classes to declare static members, including static methods/static nested classes, under the new rules.

This **does not turn Inner itself into a static nested class**. To create an **Inner instance**, you still need an enclosing Outer:

~~~java
Outer outer = new Outer();
Outer.Inner inner = outer.new Inner();
~~~

A static method of Inner does not need an Inner instance to be called, but that is the rule for static methods; it **does not prove that Inner is a static member class**.

### 24.1. Illustrative Java 17 Program

Save **`InnerStaticMemberDemo.java`**:

~~~java
public class InnerStaticMemberDemo {
    static class Outer {
        private final String name;

        Outer(String name) {
            this.name = name;
        }

        class Inner {
            static int constructed;

            Inner() {
                constructed++;
            }

            static int total() {
                return constructed;
            }

            String ownerName() {
                return name;
            }
        }
    }

    public static void main(String[] args) {
        System.out.println("before=" + Outer.Inner.total());

        Outer outer = new Outer("A");
        Outer.Inner a = outer.new Inner();
        Outer.Inner b = outer.new Inner();

        System.out.println("after=" + Outer.Inner.total());
        System.out.println("a owner=" + a.ownerName());
        System.out.println("b owner=" + b.ownerName());
    }
}
~~~

Run with Java 17+:

~~~bash
javac InnerStaticMemberDemo.java
java InnerStaticMemberDemo
~~~

Output:

~~~text
before=0
after=2
a owner=A
b owner=A
~~~

Do not mechanically carry old Java 8/11 restrictions over to Java 17. At the same time, do not mistake `Outer.Inner.total()` for Inner instance creation syntax.

## 25. Member Records, Member Interfaces, and Enums Are Not Like Non-Static Inner Classes

Inside a class, you can declare a nested **record**, nested **interface**, or nested **enum**. Member record/interface/enum declarations are implicitly static according to Java rules and are not bound to an enclosing Outer instance like a non-static `class Inner`.

Example:

~~~java
class Outer {
    record Point(int x, int y) {
    }

    interface Converter {
        int apply(int n);
    }

    enum Mode {
        FAST, SAFE
    }
}
~~~

Using the record member:

~~~java
Outer.Point point = new Outer.Point(1, 2);
~~~

Do not use `outer.new Point(1,2)` because Point is not a non-static member inner class.

### 25.1. Runnable Example

Save **`NestedRecordDemo.java`**:

~~~java
public class NestedRecordDemo {
    static class Outer {
        record Point(int x, int y) {
            int sum() {
                return x + y;
            }
        }

        class Inner {
            private final int offset;

            Inner(int offset) {
                this.offset = offset;
            }

            int addTo(int value) {
                return value + offset;
            }
        }
    }

    public static void main(String[] args) {
        Outer.Point point = new Outer.Point(2, 3);

        Outer owner = new Outer();
        Outer.Inner inner = owner.new Inner(4);

        System.out.println("point sum=" + point.sum());
        System.out.println("inner sum=" +
                inner.addTo(point.sum()));
    }
}
~~~

Run:

~~~bash
javac NestedRecordDemo.java
java NestedRecordDemo
~~~

Output:

~~~text
point sum=5
inner sum=9
~~~

**Remember:** the word “nested” only indicates declaration position; to know whether an enclosing instance is needed, check the **static/implicit-static status** of the member type.

## 26. Local Classes and Anonymous Classes: Not Used Like Member Names

A **local class** is declared inside a block/method, not a member class referred to as `Outer.Local` from outside code. An **anonymous class** has no programmer-chosen class name, so it cannot be created again with `outer.new Anonymous()`.

~~~java
class Outer {
    Runnable create() {
        class LocalTask implements Runnable {
            public void run() {
                System.out.println("local");
            }
        }

        return new LocalTask();
    }
}
~~~

This code snippet is an illustrative fragment (without a main method), used to distinguish location/class kind. It is not the answer for the two specific syntaxes `Outer.Nested` and `outer.new Inner`, which apply to appropriate **named member types**.

An anonymous class expression takes the form `new Runnable() { ... }`, which is completely different from `outer.new Inner()`.

### 26.1. How to Decide When You See a Class Inside

- Declaration **`static class Nested`** directly inside Outer → create with `new Outer.Nested(...)` if accessible.
- Non-static **`class Inner`** declaration directly inside Outer → create via an enclosing instance `outer.new Inner(...)` from outside.
- Member **`record Point`** declaration inside Outer → this is an implicitly static nested record, `new Outer.Point(...)`.
- Local class declaration inside a method → usable only within its local scope and enclosing rules.
- Anonymous class → has no simple class name for a caller to instantiate again by name.

## 27. Sharing Inner Objects in Collections

A `List<Outer.Inner>` can hold inner objects created by **multiple different Outer instances**. The static type of the list element does not force them to have the same enclosing owner.

### 27.1. Runnable Program

Save **`InnerCollectionDemo.java`**:

~~~java
import java.util.List;

public class InnerCollectionDemo {
    static class Outer {
        private final String name;

        Outer(String name) {
            this.name = name;
        }

        class Inner {
            private final int number;

            Inner(int number) {
                this.number = number;
            }

            String label() {
                return name + "#" + number;
            }
        }
    }

    public static void main(String[] args) {
        Outer first = new Outer("A");
        Outer second = new Outer("B");

        List<Outer.Inner> items = List.of(
                first.new Inner(1),
                second.new Inner(2),
                first.new Inner(3));

        for (Outer.Inner item : items) {
            System.out.println(item.label());
        }
    }
}
~~~

Run:

~~~bash
javac InnerCollectionDemo.java
java InnerCollectionDemo
~~~

Output:

~~~text
A#1
B#2
A#3
~~~

`List.of` produces a structurally unmodifiable list, but that does not determine whether the Outer objects have mutable state. If Outer.name were mutable, Inner.label could change with its enclosing outer; in this example, name is a final String.

## 28. Static Nested Helper vs. Inner for API Design

A pragmatic design rule:

**Prefer a static nested class if the member does not need an automatic Outer instance.**

Examples:
- A `Builder` only constructs a new product from the builder's own data, without needing to hold an existing outer object.
- `Node` is an implementation detail of a data structure that does not need direct access to an outer instance.
- `Result`/`Options` are auxiliary types whose namespace is tied to Outer.

**Prefer a non-static inner class when binding to a specific Outer instance is a core relationship with a clear contract.**

Examples:
- A view/iterator that directly interacts with the state of the Outer instance itself by design.
- A helper that needs to access instance fields/methods of the specific enclosing Outer and retain that link over the helper's lifetime.

Consider lifetime and memory retention, especially when storing an Inner in a long-lived static singleton/cache/listeners.

### 28.1. Do Not Overuse Inner to “Save Passing Parameters”

If a helper only needs a small immutable value such as a String ID, creating a non-static Inner just to read the ID can pull along a reference to the entire large Outer object. A static nested helper that accepts the ID directly usually has clearer ownership/lifetime.

If genuine instance-bound behavior is needed, an inner class can be the right design — there is no absolute prohibition.

## 29. Distinguishing Method Overloads, Class Names, and Constructors

The expressions:

~~~java
new Outer.Nested(1)
outer.new Inner(1)
~~~

are both **class instance creation expressions**, but their type resolution and enclosing instance requirements differ.

If Outer has two constructors `Outer()`/`Outer(String)`, that does **not** change the constructor parameter list of Inner or Nested. Which constructor gets called depends on the arguments following the corresponding type name.

`outer.new Inner(7)` is not syntax for calling a “new method” on outer; `.new` is Java's **qualified inner instance creation syntax**.

### 29.1. Example to Avoid Confusing with a Method Call

~~~java
Outer.Inner inner = outer.new Inner(7);
~~~

- `outer`: an expression of an appropriate Outer type, which must be non-null at runtime.
- `new Inner(7)`: creates an instance of member Inner bound to outer.
- `7`: explicit argument to the Inner constructor.
- `Outer.Inner` on the left: the type name of the variable inner.
- `inner`: reference to the newly created Inner instance, not a reference to Outer.

## 30. Table of Common Compile-Time and Runtime Errors

| Code or Situation | Outcome | Explanation |
| --- | --- | --- |
| `new Outer.Nested()` with accessible static member | Valid | No Outer object required |
| `outer.new Inner()` with accessible non-static Inner | Valid if outer is non-null at runtime | Requires enclosing instance |
| `new Outer.Inner()` from an external class without enclosing context | Compile-time error | No Outer instance provided |
| `new Inner()` from a static method of Outer (no qualifier) | Compile-time error | Static context has no Outer `this` |
| `new Inner()` from an instance method of Outer | Valid | Uses implicit enclosing `this` |
| `this.new Inner()` from an instance method of Outer | Valid | Explicitly uses the same enclosing Outer |
| `new Outer().new Inner()` | Valid | Creates temporary Outer then creates Inner |
| `outer.new Inner()` with null outer | `NullPointerException` | No actual enclosing object |
| `outer.new Nested()` with static Nested | Do not use this syntax | Create with `new Outer.Nested()` |
| `Outer.this` inside an Inner instance | Valid | Accesses enclosing Outer |
| `Outer.this` inside a static Nested | Compile-time error | No implicit enclosing Outer instance |
| `Outer.Inner` as variable type | Valid if accessible | Type name does not imply instantiation syntax |
| `Box<String>.Inner` with non-static member of Box<T> | Valid | Inner uses T of enclosing Box |
| `Box.Nested<U>` with static nested generic | Valid | U is Nested's type parameter |
| `Outer.Point` is a member record | Create with `new Outer.Point(...)` | Member record is implicitly static |
| `Outer.PrivateInner` outside permitted scope | Compile-time access error | Syntax does not bypass access modifiers |

Compiler diagnostics may be phrased differently depending on the JDK/IDE. Identify **whether the error is due to a missing enclosing instance, type name, constructor signature, null qualifier, or accessibility**, rather than relying entirely on a single error message string.

## 31. Step-by-Step Analysis of a Typical Error

Suppose:

~~~java
class School {
    class Student {
        Student(String name) {
        }
    }
}
~~~

Another place in the package calls:

~~~java
// School.Student a = new School.Student("Lan"); // Invalid.
~~~

Why?

1. `Student` is a **non-static member class**.
2. `School.Student` is a **type name**, which does not guarantee a School instance exists.
3. `new School.Student("Lan")` is missing an **enclosing School object**.
4. Fix:

~~~java
School school = new School();
School.Student a = school.new Student("Lan");
~~~

If Student does not need to access a School object, another design option is to change the declaration to `static class Student` (if scope/domain permits), and then use `new School.Student("Lan")`.

**Do not arbitrarily change Inner to static just to fix a syntax error** if associating Student with a specific School instance is a business relationship that must be preserved.

## 32. Practice: What Needs to Change When Converting Static Nested to Inner?

Initially:

~~~java
class Container {
    static class Entry {
    }
}

Container.Entry entry = new Container.Entry();
~~~

If you replace `static class Entry` with `class Entry`, the expression `new Container.Entry()` in external code is no longer appropriate instance creation syntax.

You need:

~~~java
Container container = new Container();
Container.Entry entry = container.new Entry();
~~~

Beyond syntax, this is an **object model change**:

- Entry is now bound to a Container instance.
- Entry can access Container's state directly.
- Entry can extend Container's reachability/lifetime.
- Constructors/factories/callers may need adjustments.
- Tests must verify that Entry belongs to the right Container, not just that it compiles.

Conversely, when changing a non-static Inner to static nested, you must remove code relying on `Outer.this`/implicit outer instance and supply an Outer reference via the API if still needed.

## 33. Comprehensive Comparison Program via a Common Interface

Save **`NestedVsInnerIntegrationDemo.java`**:

~~~java
public class NestedVsInnerIntegrationDemo {
    interface Descriptor {
        String describe();
    }

    static class Outer {
        private final String owner;
        private static final String KIND = "static";

        Outer(String owner) {
            this.owner = owner;
        }

        static class Nested implements Descriptor {
            private final String label;

            Nested(String label) {
                this.label = label;
            }

            @Override
            public String describe() {
                return KIND + ":" + label;
            }
        }

        class Inner implements Descriptor {
            private final String label;

            Inner(String label) {
                this.label = label;
            }

            @Override
            public String describe() {
                return owner + ":" + label;
            }
        }
    }

    static void show(Descriptor value) {
        System.out.println(value.describe());
    }

    public static void main(String[] args) {
        Outer.Nested nested = new Outer.Nested("N");

        Outer first = new Outer("A");
        Outer second = new Outer("B");
        Outer.Inner firstInner = first.new Inner("I1");
        Outer.Inner secondInner = second.new Inner("I2");

        show(nested);
        show(firstInner);
        show(secondInner);
    }
}
~~~

Run:

~~~bash
javac NestedVsInnerIntegrationDemo.java
java NestedVsInnerIntegrationDemo
~~~

Output:

~~~text
static:N
A:I1
B:I2
~~~

**Observations:**

- Nested and Inner can both implement an interface and both be passed into a polymorphic method.
- `Nested` reads the static field `KIND`; `Inner` reads the owner's instance field `owner`.
- How each object is created differs, yet usage through the interface can be unified.
- Static nested and inner are **mechanisms for associating a class with an enclosing context**, not two kinds of “incompatible objects” with polymorphism.

## 34. Testing the Syntaxes with Defined Conditions

When writing unit tests or a self-practice exercise, you should verify:

1. `new Outer.Nested()` creates a Nested object without needing an Outer instance.
2. `outer.new Inner()` creates an inner object with the right owner identity.
3. Two outers create inner objects with different data when outer state differs.
4. One outer creates two inner objects with separate identities.
5. `Outer.this` inside Inner references the right outer object.
6. Changing the local outer reference after creating an inner **does not change the old inner's owner**.
7. Creating an inner through a null qualifier throws NPE according to the contract.
8. Private member classes are not accessible from external code.
9. Generic `Box<String>.Inner` has the appropriate type parameter T.
10. Static nested `Box.Nested<Integer>` does not require a Box instance.
11. A member record is created with `new Outer.RecordName(...)` if accessible.
12. Code in a static context gets a compiler error when attempting `new Inner()` directly.

### 34.1. Self-Testing Program, No JUnit Required

Save **`NestedCreationContractTest.java`**:

~~~java
public class NestedCreationContractTest {
    static class Outer {
        private final String id;

        Outer(String id) {
            this.id = id;
        }

        static class Nested {
            int value() {
                return 7;
            }
        }

        class Inner {
            String owner() {
                return Outer.this.id;
            }

            boolean belongsTo(Outer expected) {
                return Outer.this == expected;
            }
        }
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        Outer.Nested nested = new Outer.Nested();
        check(nested.value() == 7, "nested construction");

        Outer outer = new Outer("A");
        Outer.Inner first = outer.new Inner();
        Outer.Inner second = outer.new Inner();

        check(first != second, "inner identity");
        check(first.belongsTo(outer), "enclosing owner");
        check(second.belongsTo(outer), "second owner");
        check("A".equals(first.owner()), "owner data");

        Outer.Inner fresh = new Outer("B").new Inner();
        check("B".equals(fresh.owner()), "fresh owner");

        System.out.println("all nested creation checks passed");
    }
}
~~~

Run:

~~~bash
javac NestedCreationContractTest.java
java NestedCreationContractTest
~~~

Output:

~~~text
all nested creation checks passed
~~~

This uses the `check` method instead of Java `assert`, which by default can be disabled when not run with `-ea`. Here, all conditions are verified under a normal `java NestedCreationContractTest` command.

## 35. Review Questions and Answers

**Question 1.** Does a `static class Nested` declared inside Outer require creating an Outer object before creating Nested?  
**Answer:** No. Use `new Outer.Nested(...)` if the type/constructor is accessible.

**Question 2.** Does a non-static `class Inner` require an enclosing instance when created from outside code?  
**Answer:** Yes. Use `outer.new Inner(...)` with an appropriate outer.

**Question 3.** Can `Outer.Inner` be used as a variable's type name?  
**Answer:** Yes, if accessible; however, the creation syntax still differs from static nested.

**Question 4.** Why is `new Outer.Inner()` without an outer usually invalid?  
**Answer:** A non-static inner class requires an enclosing Outer instance.

**Question 5.** Does `new Outer().new Inner()` create an Outer object?  
**Answer:** Yes. The Inner is bound to the newly created temporary Outer.

**Question 6.** Does `outer.new Inner(7)` pass `outer` as a programmer-declared constructor parameter?  
**Answer:** No. The qualifier provides the enclosing instance, while `7` is the explicit argument.

**Question 7.** Is `new Inner()` inside an instance method of Outer valid?  
**Answer:** Yes. The implicit enclosing Outer instance is `this`.

**Question 8.** Is `new Inner()` from a static method of Outer, without a qualifier, valid?  
**Answer:** No, an enclosing instance is missing.

**Question 9.** Is `this.new Inner()` from an instance method of Outer valid?  
**Answer:** Yes, if Inner is accessible and the constructor matches.

**Question 10.** What happens with `outer.new Inner()` when `outer == null`?  
**Answer:** A `NullPointerException` when creating the inner.

**Question 11.** Which object does `Outer.this` inside Inner point to?  
**Answer:** The enclosing Outer instance bound to that Inner.

**Question 12.** Which object does `this` inside an Inner instance method point to?  
**Answer:** The Inner instance itself.

**Question 13.** Can Nested have its own instance fields?  
**Answer:** Yes. `static` on the nested declaration does not make Nested's instance fields static.

**Question 14.** Can a static Nested read an Outer instance field?  
**Answer:** Yes, when given an explicit Outer reference and access permission; there is no implicit Outer.this.

**Question 15.** Do two Inner objects created from two different Outer objects have the same type name?  
**Answer:** They can have the same type `Outer.Inner`, but different enclosing instances.

**Question 16.** Can one Outer create multiple Inner objects?  
**Answer:** Yes; normally each creation produces a distinct Inner instance.

**Question 17.** Does changing the `outer` variable's reference after creating an inner change the old inner's enclosing instance?  
**Answer:** No. The inner keeps its relationship with the object used at creation time.

**Question 18.** If Inner stays alive for a very long time, can Outer be kept reachable?  
**Answer:** Yes, the enclosing instance link can extend the lifetime of Outer.

**Question 19.** Is `Box<String>.Inner` with a generic outer valid?  
**Answer:** Yes, when Inner is non-static and the outer type/constructor is valid.

**Question 20.** Does `Box.Nested<Integer>` require a Box<Integer> object?  
**Answer:** No, if Nested is static and the type argument Integer belongs to Nested.

**Question 21.** Can a static nested class use the type parameter `T` of a generic enclosing Box<T> directly?  
**Answer:** No; a static nested class has no enclosing Box<T> instance/type parameter context like a non-static Inner does.

**Question 22.** Can `Outer.Middle.Leaf` be created using `middle.new Leaf()`?  
**Answer:** Yes, if Leaf is an inner member of Middle, middle has the right type, and it is accessible.

**Question 23.** Can `Outer.this` be used inside a static Nested?  
**Answer:** No, there is no implicit enclosing Outer instance.

**Question 24.** Can an inner class in Java 17 declare a static method?  
**Answer:** Yes, under Java 16+ rules; this does not remove the requirement of an enclosing Outer when creating an Inner instance.

**Question 25.** What syntax is used to create a member record declared inside Outer?  
**Answer:** `new Outer.RecordName(...)` if accessible; member records are implicitly static.

**Question 26.** Can a private Inner be created with `outer.new Inner()` from an outside class simply by having an outer reference?  
**Answer:** No, Java access control still applies.

**Question 27.** Can a local class declared inside a method be created from outside using `new Outer.Local()`?  
**Answer:** No, a local class is not a named member class accessible in that form.

**Question 28.** When should you choose a static nested helper instead of an Inner?  
**Answer:** When the helper does not need an automatic enclosing Outer instance and you want to reduce coupling/lifetime retention.

**Question 29.** If a method in Nested takes `Outer owner` to read state, does that turn Nested into an Inner?  
**Answer:** No. The explicit reference is just passed data, unlike an implicit enclosing instance.

**Question 30.** What is the shortest way to remember both syntaxes?  
**Answer:** **Static member: `new Outer.Nested(...)`. Non-static member: `outer.new Inner(...)`.**

## 36. Pre-Compilation Checklist for Code Creating Nested Objects

- [ ] Is the member class `static` or non-static?
- [ ] If non-static, do you already have an enclosing Outer instance?
- [ ] Is the type name in the right scope (`Outer.Inner`/`Outer.Nested`)?
- [ ] Does the constructor match the arguments being passed?
- [ ] Are Outer, the member type, and the constructor accessible from the caller?
- [ ] Did you accidentally write `new Inner()` inside a static context?
- [ ] Do you want a new outer via `new Outer().new Inner()` or to reuse an existing outer?
- [ ] Could the enclosing qualifier be null at runtime?
- [ ] Is there shadowing that requires `Outer.this`?
- [ ] Is a static nested class trying to access an instance field without a reference?
- [ ] If Outer is generic, are you using `Outer<T>.Inner` correctly?
- [ ] If the static nested class is generic, are you referencing it via `Outer.Nested<U>` correctly?
- [ ] Is an implicitly static member record/interface/enum being mistaken for an inner class?
- [ ] Does the enclosing instance relationship affect memory/lifetime/ownership?
- [ ] If stored in a collection, can the Inner instances have different owners?
- [ ] Have you tried compiling on Java 17 with the right file name/public class and testing stdout?

## 37. References

- Java Language Specification (Java SE 17), [`8.1.3 — Inner Classes and Enclosing Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.3): defines inner classes/enclosing instances.
- Java Language Specification, [`8.5 — Member Type Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.5): nested member types and static declarations.
- Java Language Specification, [`15.9 — Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9): qualified class instance creation.
- Java Language Specification, [`15.9.2 — Determining Enclosing Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9.2): enclosing instances when creating an inner.
- Java Language Specification, [`15.8.4 — Qualified `this`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.8.4): `Outer.this` syntax.
- Java Language Specification, [`8.8 — Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8): constructor parameters/creation.
- Java Language Specification, [`6.5 — Determining the Meaning of a Name](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.5): name resolution.
- Java Language Specification, [`6.6 — Access Control](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6): visibility and access modifiers.
- Java Language Specification, [`8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): member records and implicit static.
- Java Tutorials, [Nested Classes](https://docs.oracle.com/javase/tutorial/java/javaOO/nested.html): static nested/inner concepts. The tutorial documentation may reflect an older source level; when there are differences with Java 17 syntax (such as static members inside inner), prefer JLS 17.

## Summary

**`Outer.Nested`** and **`Outer.Inner`** are both type names of member classes inside Outer, yet they have **different instance creation rules**:

- For `static class Nested`: `Outer.Nested value = new Outer.Nested(...)`. No enclosing Outer object is needed.
- For non-static `class Inner`: `Outer outer = new Outer(...); Outer.Inner value = outer.new Inner(...)`. Inner is bound to the exact Outer instance used as the qualifier.
- Inside an instance context of Outer, you can write `new Inner(...)` or `this.new Inner(...)`.
- Inside a static context, an explicit Outer reference is required to create Inner.
- `Outer.this` inside Inner accesses the enclosing instance, whereas `this` refers to the Inner object.
- If the outer qualifier is null, qualified inner creation throws `NullPointerException`.
- Nested classes still obey access modifiers, constructor signatures, generic typing, and enclosing context rules.

Choose a **static nested class when an automatic Outer instance link is not needed**; choose a **member inner class when binding to a specific Outer object is part of the design**. Practicing checking type names, `new` syntax, reference identity, and lifetime will help avoid most errors when using nested classes in Java.
