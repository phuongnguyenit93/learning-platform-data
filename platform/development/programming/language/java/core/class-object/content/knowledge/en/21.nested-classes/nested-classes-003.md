# Inner member class associated with an enclosing object in Java

An **inner member class** is a class declared as a member **without the `static` modifier** inside the body of an outer class. When creating an instance of an inner member class, Java associates it with **an enclosing instance** — that is, **a specific enclosing object**.

~~~java
class House {
    private final String address;

    House(String address) {
        this.address = address;
    }

    class Room {
        String where() {
            return House.this.address;
        }
    }
}
~~~

In this case, `House.Room` is the **type name**. A Room object is created via `house.new Room()`; it does not appear automatically when declaring the class or when creating House. Inside a Room method, `House.this` is a reference to the exact House instance used when creating Room. This is an **enclosing relationship**, not an inheritance relationship.

This lesson belongs to **Java Core — Class & Object / Nested Classes**, using **Java 17+**. Standalone Java programs include a filename, `javac`/`java` commands, and stdout; snippets without full context are explicitly marked as illustrative.

## 1. Learning objectives

- Distinguish between outer type, inner member type, outer object, and inner object.
- Know that a non-`static` member class requires an enclosing instance when created.
- Use `outer.new Inner()` from code outside the outer class.
- Use `new Inner()` from an instance context of Outer.
- Distinguish between `this` of the inner and `Outer.this` of the outer.
- Understand that an inner class can access the private instance state of the outer.
- Explain shadowing and how to explicitly specify local/inner/outer fields.
- Distinguish inner member classes from static nested, local, and anonymous classes.
- Understand that a static context does not automatically have an outer instance.
- Know that the enclosing instance association does not change when assigning an inner reference to another variable.
- Understand that multiple inner instances can share the same outer, or have the same type with different outers.
- Predict initialization/constructor order and a null enclosing qualifier.
- Use `Outer<T>.Inner<U>` with generics.
- Understand that Java 17 allows static declarations inside an inner class.
- Understand that runtime metadata does not store a specific enclosing outer object via the Class API.
- Know that storing an inner long-term can keep the outer reachable.
- Choose an inner class, a static nested helper, or composition based on ownership/lifecycle.
- Write tests that verify the correct association, state, and invariants.

## 2. Declaring a class and creating an object are two different operations

Consider:

~~~java
class Outer {
    class Inner {
    }
}
~~~

This declaration creates **two class types** with a lexical nesting relationship. It does not automatically create an Outer object or an Inner object. To obtain objects:

~~~java
Outer outer = new Outer();
Outer.Inner inner = outer.new Inner();
~~~

Conceptual diagram:

~~~text
 Outer instance #1
        ^
        |
 enclosing-instance association
        |
 Inner instance #1
~~~

There are **two ordinary objects**. Inner is **not** a subclass of Outer and **does not physically reside inside Outer's memory under a struct model** guaranteed by Java.

### An inner instance does not mean a field

Merely declaring `class Inner` inside Outer does not automatically create an `outer.inner` field. If Outer needs to store an inner instance, a field/method must be declared:

~~~java
class Outer {
    class Inner {
    }

    private final Inner stored = new Inner();

    Inner stored() {
        return stored;
    }
}
~~~

Here, the `stored` field is explicitly declared and initialized; that is the author's own decision, not an automatic mechanism for every inner member class.

## 3. Syntax for creating an inner instance

There are three important patterns.

**From an instance method of Outer:**

~~~java
class Outer {
    class Inner {
    }

    Inner create() {
        return new Inner();
    }
}
~~~

In `create()`, `new Inner()` is associated with Outer's `this`.

**From outside code:**

~~~java
Outer outer = new Outer();
Outer.Inner inner = outer.new Inner();
~~~

`Outer.Inner` specifies the type on the declaration side, whereas `outer.new Inner()` specifies the enclosing **instance** on the object-creation side.

**Creating Outer and Inner in a single expression:**

~~~java
Outer.Inner inner = new Outer().new Inner();
~~~

The new Outer is created first and used as the enclosing object of the new Inner.

### Invalid syntax

~~~java
// Outer.Inner inner = new Outer.Inner(); // Invalid for a non-static inner member class.
~~~

`new Outer.Inner()` is normally the syntax for a `static nested class`, not a non-static inner member class from outside.

## 4. First program: two inner instances with the same outer

Create the file **`InnerBasicsDemo.java`**:

~~~java
public class InnerBasicsDemo {
    static final class House {
        private final String address;

        House(String address) {
            this.address = address;
        }

        class Room {
            String where() {
                return address;
            }
        }

        Room createRoom() {
            return new Room();
        }
    }

    public static void main(String[] args) {
        House home = new House("Ha Noi");
        House.Room first = home.new Room();
        House.Room second = home.createRoom();

        System.out.println("first=" + first.where());
        System.out.println("second=" + second.where());
        System.out.println("different rooms=" + (first != second));
        System.out.println("same inner class=" +
                (first.getClass() == second.getClass()));
    }
}
~~~

~~~bash
javac -encoding UTF-8 InnerBasicsDemo.java
java InnerBasicsDemo
~~~

Stdout:

~~~text
first=Ha Noi
second=Ha Noi
different rooms=true
same inner class=true
~~~

`first` and `second` are **two Room objects**. Both were created associated with `home`, so they read the address of the same House. They also belong to the same runtime type `House.Room`.

## 5. `this` and `Outer.this`

Inside an instance method of Inner:

- `this` is the **current Inner object**.
- `Outer.this` is the **enclosing Outer object**.
- `Outer.this.field` explicitly specifies the outer's field.
- `Outer.this.method()` explicitly specifies calling the outer's method.

Example:

~~~java
class Account {
    private final String id;

    Account(String id) {
        this.id = id;
    }

    class Audit {
        String id() {
            return Account.this.id;
        }

        boolean belongsTo(Account candidate) {
            return Account.this == candidate;
        }
    }
}
~~~

`Account.this` does not refer to the most recent Account object, does not access a global Account, and does not automatically create an Account. It refers to the **exact enclosing instance** associated with Audit when Audit was created.

## 6. Runnable program: identity of the enclosing outer

Create **`OuterThisDemo.java`**:

~~~java
public class OuterThisDemo {
    static final class Account {
        private final String id;

        Account(String id) {
            this.id = id;
        }

        class Audit {
            boolean belongsTo(Account value) {
                return Account.this == value;
            }

            String description() {
                return "audit:" + Account.this.id;
            }
        }
    }

    public static void main(String[] args) {
        Account first = new Account("A");
        Account second = new Account("B");

        Account.Audit audit = first.new Audit();

        System.out.println(audit.description());
        System.out.println("first=" + audit.belongsTo(first));
        System.out.println("second=" + audit.belongsTo(second));
    }
}
~~~

~~~bash
javac -encoding UTF-8 OuterThisDemo.java
java OuterThisDemo
~~~

Stdout:

~~~text
audit:A
first=true
second=false
~~~

The inner Audit knows its enclosing Account via `Account.this`, so it distinguishes first and second even though they have the same runtime class.

## 7. Enclosing instance association does not change when assigning a reference

~~~java
Outer first = new Outer();
Outer second = new Outer();
Outer.Inner inner = first.new Inner();
Outer.Inner alias = inner;
~~~

`alias = inner` only creates another alias to the **same Inner object**. It does not change the enclosing instance from first to second.

If you want an inner associated with second, you must create **a new Inner object**:

~~~java
Outer.Inner another = second.new Inner();
~~~

Java has no built-in assignment to change the enclosing instance of an already constructed Inner. To change an association according to the domain, you usually have to design another explicit field/indirection; that will be a separate data relationship and does not replace `Outer.this`.

## 8. Runnable program: multiple outer instances

Create **`MultipleOuterDemo.java`**:

~~~java
public class MultipleOuterDemo {
    static final class Shelf {
        private final String label;

        Shelf(String label) {
            this.label = label;
        }

        class Slot {
            String shelfLabel() {
                return label;
            }

            boolean belongsTo(Shelf candidate) {
                return Shelf.this == candidate;
            }
        }
    }

    public static void main(String[] args) {
        Shelf left = new Shelf("LEFT");
        Shelf right = new Shelf("RIGHT");

        Shelf.Slot a = left.new Slot();
        Shelf.Slot b = left.new Slot();
        Shelf.Slot c = right.new Slot();

        System.out.println("a=" + a.shelfLabel());
        System.out.println("b=" + b.shelfLabel());
        System.out.println("c=" + c.shelfLabel());
        System.out.println("a==b=" + (a == b));
        System.out.println("a class==c class=" +
                (a.getClass() == c.getClass()));
        System.out.println("c belongs right=" + c.belongsTo(right));
        System.out.println("c belongs left=" + c.belongsTo(left));
    }
}
~~~

~~~bash
javac -encoding UTF-8 MultipleOuterDemo.java
java MultipleOuterDemo
~~~

Stdout:

~~~text
a=LEFT
b=LEFT
c=RIGHT
a==b=false
a class==c class=true
c belongs right=true
c belongs left=false
~~~

The two Slots from left have the same enclosing outer instance. The Slot from right has a different enclosing outer instance. **The Class object of all three Slots remains the same** within the same class-loader context, because enclosing **object identity** does not create a new Java **class type**.

## 9. Inner member class can access private outer members

A member inner class is allowed to access the outer's private fields/methods according to Java nesting access rules.

~~~java
class Vault {
    private String secret = "KEY";

    class Inspector {
        String inspect() {
            return secret;
        }
    }
}
~~~

`secret` here is a field of the **enclosing Vault**. That does not make the field public to arbitrary external classes.

### Outer can also access private members of inner

~~~java
class Outer {
    class Inner {
        private int code = 7;
    }

    int read(Inner object) {
        return object.code;
    }
}
~~~

Outer needs a reference to a specific Inner to read the instance field code. The compiler/JVM supports nested private access; since Java 11, the concept of **nestmates** has been used in the JVM to represent private access among types in the same nest.

## 10. Runnable program: bidirectional private access

Create **`PrivateAccessDemo.java`**:

~~~java
public class PrivateAccessDemo {
    static final class Vault {
        private final String secret;

        Vault(String secret) {
            this.secret = secret;
        }

        class Inspector {
            private final String tag;

            Inspector(String tag) {
                this.tag = tag;
            }

            String inspect() {
                return Vault.this.secret + ":" + tag;
            }
        }

        String tagOf(Inspector inspector) {
            return inspector.tag;
        }
    }

    public static void main(String[] args) {
        Vault vault = new Vault("KEY");
        Vault.Inspector inspector =
                vault.new Inspector("I1");

        System.out.println("inspection=" +
                inspector.inspect());
        System.out.println("tag=" + vault.tagOf(inspector));
    }
}
~~~

~~~bash
javac -encoding UTF-8 PrivateAccessDemo.java
java PrivateAccessDemo
~~~

Stdout:

~~~text
inspection=KEY:I1
tag=I1
~~~

Inner reads private outer state; an outer method reads private inner state. Both accesses are valid because of lexical nesting, not because the `private` modifier is ignored completely.

## 11. Shadowing and how to explicitly specify scope

If a parameter, an inner field, and an outer field have the same name:

~~~java
class Outer {
    int number = 10;

    class Inner {
        int number = 20;

        void show(int number) {
            System.out.println(number);
            System.out.println(this.number);
            System.out.println(Outer.this.number);
        }
    }
}
~~~

When calling `show(30)`:

- `number` is the method parameter 30.
- `this.number` is the Inner field 20.
- `Outer.this.number` is the Outer field 10.

### Runnable program

Create **`ShadowingDemo.java`**:

~~~java
public class ShadowingDemo {
    static final class Outer {
        private int number = 10;

        class Inner {
            private int number = 20;

            void print(int number) {
                System.out.println("parameter=" + number);
                System.out.println("inner=" + this.number);
                System.out.println("outer=" +
                        Outer.this.number);
            }
        }
    }

    public static void main(String[] args) {
        Outer outer = new Outer();
        Outer.Inner inner = outer.new Inner();
        inner.print(30);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ShadowingDemo.java
java ShadowingDemo
~~~

Stdout:

~~~text
parameter=30
inner=20
outer=10
~~~

This is why `Outer.this` is useful even when Java sometimes allows accessing an outer member by its simple name: it makes the target of the expression explicit.

## 12. Calling an outer method from an inner method

~~~java
class Machine {
    private int total;

    private void add(int delta) {
        total += delta;
    }

    class Control {
        void click() {
            Machine.this.add(1);
        }
    }
}
~~~

Inner can call a private method of the enclosing outer. If there is no same-named/shadowing method, sometimes writing `add(1)` also works; qualified `Machine.this.add(1)` is clearer.

**Do not confuse with `super`:** `super` inside Inner relates to **Inner's superclass**, not the enclosing Outer. Nesting and inheritance are two different relationships.

## 13. From a static method, an explicit outer instance is required

A static method has no `Outer.this` receiver. Therefore:

~~~java
class Outer {
    class Inner {
    }

    static void invalid() {
        // Inner inner = new Inner(); // Error: missing enclosing Outer instance.
    }

    static Inner valid(Outer outer) {
        return outer.new Inner();
    }
}
~~~

To create an inner inside a static context, pass in an Outer object or create a new Outer. If the helper does not need an outer context, consider a static nested class.

### Runnable program

Create **`StaticContextDemo.java`**:

~~~java
public class StaticContextDemo {
    static final class Outer {
        private final int id;

        Outer(int id) {
            this.id = id;
        }

        class Inner {
            int ownerId() {
                return id;
            }
        }

        static Inner create(Outer source) {
            return source.new Inner();
        }
    }

    public static void main(String[] args) {
        Outer outer = new Outer(7);
        Outer.Inner first = outer.new Inner();
        Outer.Inner second = Outer.create(outer);

        System.out.println("first=" + first.ownerId());
        System.out.println("second=" + second.ownerId());
        System.out.println("different=" + (first != second));
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticContextDemo.java
java StaticContextDemo
~~~

Stdout:

~~~text
first=7
second=7
different=true
~~~

## 14. What if the outer qualifier is null?

~~~java
Outer missing = null;
// Outer.Inner inner = missing.new Inner();
~~~

This can be a valid expression at compile time (if the type/constructor is accessible), but at runtime there is no enclosing instance to provide and it will throw a `NullPointerException`.

Create **`NullOuterDemo.java`**:

~~~java
public class NullOuterDemo {
    static final class Outer {
        class Inner {
        }
    }

    public static void main(String[] args) {
        Outer outer = null;

        try {
            Outer.Inner inner = outer.new Inner();
            System.out.println(inner);
        } catch (NullPointerException ex) {
            System.out.println("missing outer");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 NullOuterDemo.java
java NullOuterDemo
~~~

Stdout:

~~~text
missing outer
~~~

If an API has a nullable Outer parameter, validate it first. A non-static member inner class is designed to have an enclosing instance, not to arbitrarily lack an owner.

## 15. Creation order with `new Outer().new Inner()`

The Outer instance is created first, followed by the Inner instance. We can inspect the order of constructor calls:

Create **`ConstructionOrderDemo.java`**:

~~~java
public class ConstructionOrderDemo {
    static final class Outer {
        Outer() {
            System.out.println("outer constructed");
        }

        class Inner {
            Inner() {
                System.out.println("inner constructed");
            }
        }
    }

    public static void main(String[] args) {
        Outer.Inner inner = new Outer().new Inner();
        System.out.println("created=" + (inner != null));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ConstructionOrderDemo.java
java ConstructionOrderDemo
~~~

Stdout:

~~~text
outer constructed
inner constructed
created=true
~~~

An Outer is not just a “syntactic step” that gets discarded; it is an ordinary object that gets created. If the Outer constructor throws an exception, the Inner constructor does not complete.

## 16. Inner has its own constructor parameters and state

~~~java
class Department {
    private final String name;

    Department(String name) {
        this.name = name;
    }

    class Employee {
        private final int id;

        Employee(int id) {
            this.id = id;
        }

        String label() {
            return name + ":" + id;
        }
    }
}
~~~

Here, `Department.Employee` has Employee's own id. `name` is read from the enclosing Department. To create:

~~~java
Department sales = new Department("Sales");
Department.Employee e = sales.new Employee(42);
~~~

The number `42` is an explicit constructor argument for Employee; the enclosing Department instance is supplied via `sales.new`, not as a source-level constructor parameter declared by you.

### Runnable program

Create **`InnerConstructorDemo.java`**:

~~~java
public class InnerConstructorDemo {
    static final class Department {
        private final String name;

        Department(String name) {
            this.name = name;
        }

        class Employee {
            private final int id;

            Employee(int id) {
                this.id = id;
            }

            String label() {
                return name + ":" + id;
            }
        }
    }

    public static void main(String[] args) {
        Department dev = new Department("Engineering");
        Department biz = new Department("Sales");

        Department.Employee first = dev.new Employee(42);
        Department.Employee second = biz.new Employee(42);

        System.out.println(first.label());
        System.out.println(second.label());
        System.out.println("same class=" +
                (first.getClass() == second.getClass()));
    }
}
~~~

~~~bash
javac -encoding UTF-8 InnerConstructorDemo.java
java InnerConstructorDemo
~~~

Stdout:

~~~text
Engineering:42
Sales:42
same class=true
~~~

## 17. How an inner member differs from a static nested class

~~~java
class Outer {
    class MemberInner {
    }

    static class NestedStatic {
    }
}
~~~

| Property | Non-static member inner | Static nested |
| --- | --- | --- |
| Has enclosing Outer instance on creation | Yes | No |
| How to create from outside | `outer.new MemberInner()` | `new Outer.NestedStatic()` |
| Can use `Outer.this` | Yes, in the inner's instance context | No |
| Directly reads outer instance fields | Yes | No, without an explicit reference |
| Suitable for helpers independent of outer | Usually no | Usually yes |
| Both are nested types | Yes | Yes |

**Do not confuse them:** a static nested class is declared inside Outer, yet **is not associated with an Outer object** when creating an instance. The Outer name in `Outer.NestedStatic` is only the namespace/declaring type context.

### Runnable program

Create **`StaticNestedVsInnerDemo.java`**:

~~~java
public class StaticNestedVsInnerDemo {
    static final class Outer {
        private final String name;

        Outer(String name) {
            this.name = name;
        }

        class MemberInner {
            String show() {
                return "inner:" + name;
            }
        }

        static class Nested {
            String show() {
                return "nested";
            }
        }
    }

    public static void main(String[] args) {
        Outer outer = new Outer("A");

        Outer.MemberInner first = outer.new MemberInner();
        Outer.Nested second = new Outer.Nested();

        System.out.println(first.show());
        System.out.println(second.show());
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticNestedVsInnerDemo.java
java StaticNestedVsInnerDemo
~~~

Stdout:

~~~text
inner:A
nested
~~~

## 18. How a member inner differs from local and anonymous classes

A **member inner** is a non-static member declared directly inside a class body:

~~~java
class Outer {
    class Member {
    }
}
~~~

A **local class** is declared inside a block/method:

~~~java
void run() {
    class Local {
    }
    Local local = new Local();
}
~~~

An **anonymous class** does not declare an explicit class name and uses an expression:

~~~java
Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println("task");
    }
};
~~~

Local/anonymous classes follow rules for capturing **final or effectively final** local variables where applicable. A member inner class is declared at the class-body level and does not automatically capture local variables in every method of the outer.

A local class inside a static context does not have an enclosing outer instance like an instance method does. Therefore, you must not mechanically apply every member inner rule to all nested classes.

## 19. An inner member does not automatically extend Outer

This is an important distinction:

~~~java
class Outer {
    class Inner {
    }
}
~~~

Inner **does not extend Outer**. If Inner does not declare a superclass, its normal superclass is Object. Outer and Inner are **two different types** and two different ordinary objects.

Therefore, `Outer.this` differs from `super`:

- `this` → Inner instance.
- `Outer.this` → enclosing Outer instance.
- `super` → superclass context of Inner.

An Outer object is **not** an instance of Inner, and vice versa. Java nesting is not inheritance.

## 20. Generic outer and inner member

When Outer has a type parameter:

~~~java
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    class Viewer {
        T read() {
            return value;
        }
    }
}
~~~

The type declaration for the viewer uses the generic outer type:

~~~java
Box<String> box = new Box<>("Java");
Box<String>.Viewer viewer = box.new Viewer();
String result = viewer.read();
~~~

`Box<String>.Viewer` represents the member type within a parameterized Outer type; it **does not encode the identity of a particular Box object**.

### Runnable program

Create **`GenericInnerDemo.java`**:

~~~java
public class GenericInnerDemo {
    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        class Viewer {
            T read() {
                return value;
            }
        }
    }

    public static void main(String[] args) {
        Box<String> words = new Box<>("Java");
        Box<Integer> numbers = new Box<>(17);

        Box<String>.Viewer textViewer = words.new Viewer();
        Box<Integer>.Viewer numberViewer = numbers.new Viewer();

        System.out.println("text=" + textViewer.read());
        System.out.println("number=" + numberViewer.read());
        System.out.println("same runtime class=" +
                (textViewer.getClass() ==
                        numberViewer.getClass()));
    }
}
~~~

~~~bash
javac -encoding UTF-8 GenericInnerDemo.java
java GenericInnerDemo
~~~

Stdout:

~~~text
text=Java
number=17
same runtime class=true
~~~

The two viewers have different generic outer type arguments at compile time, yet use the same runtime member class metadata due to type erasure.

## 21. Inner also has its own generic parameters

~~~java
class Holder<T> {
    private final T base;

    Holder(T base) {
        this.base = base;
    }

    class Pair<U> {
        private final U extra;

        Pair(U extra) {
            this.extra = extra;
        }

        String label() {
            return base + ":" + extra;
        }
    }
}
~~~

When used:

~~~java
Holder<String> holder = new Holder<>("A");
Holder<String>.Pair<Integer> pair =
        holder.new Pair<>(7);
~~~

T comes from Holder, and U belongs to Pair. The outer instance is still holder itself; an inner type parameter U never causes the inner to associate with a new outer.

### Runnable program

Create **`GenericPairDemo.java`**:

~~~java
public class GenericPairDemo {
    static final class Holder<T> {
        private final T base;

        Holder(T base) {
            this.base = base;
        }

        class Pair<U> {
            private final U extra;

            Pair(U extra) {
                this.extra = extra;
            }

            String label() {
                return base + ":" + extra;
            }
        }
    }

    public static void main(String[] args) {
        Holder<String> holder = new Holder<>("A");
        Holder<String>.Pair<Integer> pair =
                holder.new Pair<>(7);

        System.out.println(pair.label());
    }
}
~~~

~~~bash
javac -encoding UTF-8 GenericPairDemo.java
java GenericPairDemo
~~~

Stdout:

~~~text
A:7
~~~

## 22. Java 17 allows static declarations inside inner classes

Older documentation might say “an inner class cannot have static methods/fields, except constant variables”. **This restrictive rule was changed starting in Java SE 16**. As of Java 17, static declarations inside inner classes are allowed.

Having a static method in Inner **does not turn Inner into a static nested class**. An Inner instance still requires an enclosing outer upon creation.

Create **`InnerStaticMemberDemo.java`**:

~~~java
public class InnerStaticMemberDemo {
    static final class Outer {
        private final int base;

        Outer(int base) {
            this.base = base;
        }

        class Inner {
            static final String KIND = "inner";

            static int doubleOf(int n) {
                return n * 2;
            }

            int plus(int n) {
                return base + n;
            }
        }
    }

    public static void main(String[] args) {
        Outer outer = new Outer(10);
        Outer.Inner inner = outer.new Inner();

        System.out.println("kind=" + Outer.Inner.KIND);
        System.out.println("double=" +
                Outer.Inner.doubleOf(4));
        System.out.println("plus=" + inner.plus(3));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 InnerStaticMemberDemo.java
java InnerStaticMemberDemo
~~~

Stdout:

~~~text
kind=inner
double=8
plus=13
~~~

**A static method has no inner/outer receiver** and cannot use `Outer.this`. The Java 17 rule on static declarations does not change the `outer.new Inner()` instance creation rule.

## 23. Class metadata differs from an enclosing instance

Class reflection reports the declaration relationship:

- `Outer.Inner.class.getDeclaringClass()` → Class object for Outer.
- `Outer.Inner.class.getEnclosingClass()` → Class object for Outer.
- `Outer.Inner.class.isMemberClass()` → true.

However, the Class API does not by default return **a specific outer object** for each Inner instance. Two Inner objects associated with two Outer instances still have the **same Class object** for Inner.

### Runnable program

Create **`InnerMetadataDemo.java`**:

~~~java
public class InnerMetadataDemo {
    static final class Outer {
        class Inner {
        }

        static class Nested {
        }
    }

    public static void main(String[] args) {
        Class<?> inner = Outer.Inner.class;
        Class<?> nested = Outer.Nested.class;

        System.out.println("inner member=" + inner.isMemberClass());
        System.out.println("inner declaring=" +
                (inner.getDeclaringClass() == Outer.class));
        System.out.println("inner enclosing=" +
                (inner.getEnclosingClass() == Outer.class));
        System.out.println("nested member=" + nested.isMemberClass());
        System.out.println("nested declaring=" +
                (nested.getDeclaringClass() == Outer.class));
    }
}
~~~

~~~bash
javac -encoding UTF-8 InnerMetadataDemo.java
java InnerMetadataDemo
~~~

Stdout:

~~~text
inner member=true
inner declaring=true
inner enclosing=true
nested member=true
nested declaring=true
~~~

Both Inner and Nested are member classes. However, **only an instance of the non-static Inner requires an enclosing outer instance**.

## 24. The reflection constructor has an extra enclosing-instance parameter

For an inner class declaring the source constructor `Inner(int code)`, reflection typically sees an outer instance parameter alongside `int`. The JVM needs to know the enclosing object when creating the inner.

Create **`ReflectiveInnerDemo.java`**:

~~~java
import java.lang.reflect.Constructor;

public class ReflectiveInnerDemo {
    static final class Outer {
        private final String id;

        Outer(String id) {
            this.id = id;
        }

        public class Inner {
            private final int code;

            public Inner(int code) {
                this.code = code;
            }

            String description() {
                return id + ":" + code;
            }
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Outer outer = new Outer("R");

        Constructor<Outer.Inner> ctor =
                Outer.Inner.class.getDeclaredConstructor(
                        Outer.class, int.class);

        Outer.Inner inner = ctor.newInstance(outer, 7);

        System.out.println("parameters=" +
                ctor.getParameterCount());
        System.out.println("description=" + inner.description());
    }
}
~~~

~~~bash
javac -encoding UTF-8 ReflectiveInnerDemo.java
java ReflectiveInnerDemo
~~~

Stdout:

~~~text
parameters=2
description=R:7
~~~

The source constructor takes `int code`, whereas the reflection signature has the enclosing Outer parameter. Details of synthetic field/parameter names (for example, names the compiler may generate) are an implementation detail; **do not rely on synthetic names as a public contract**. For normal Java code, the `outer.new Inner(7)` syntax is easier to read and safer.

## 25. An inner object can extend the lifetime of the outer object

An inner callback stored in a long-lived registry/listener manager can keep the enclosing outer reachable:

~~~text
application registry
        |
        v
 inner callback object
        |
        v
 enclosing screen object
~~~

If the screen is supposed to be freed when the window closes, yet the handler remains in the registry, the screen's memory or large resources may be retained for a long time.

In Java, enclosing-instance semantics exist at the language level, but the Java compiler may represent the association using different implementation details; do not treat a synthetic field name as a stable API. When an inner actually uses outer state, pay special attention to reachability.

### How to control it

- Unregister the handler according to the lifecycle.
- Do not store the inner longer than needed.
- Use a static nested helper when an outer instance is not needed.
- If only a small dependency is needed, pass an explicit dependency instead of capturing the entire owner.
- If you use a static nested class and still hold a strong Outer reference, retention **can still occur**. Merely changing the keyword does not automatically fix retention.

## 26. Callback inner class

An inner class is convenient because a callback can directly manipulate the private state of its enclosing owner.

Create **`InnerCallbackDemo.java`**:

~~~java
public class InnerCallbackDemo {
    static final class Screen {
        private int clicks;

        class ClickHandler implements Runnable {
            @Override
            public void run() {
                clicks++;
            }
        }

        Runnable handler() {
            return new ClickHandler();
        }

        int clicks() {
            return clicks;
        }
    }

    public static void main(String[] args) {
        Screen screen = new Screen();
        Runnable handler = screen.handler();

        handler.run();
        handler.run();

        System.out.println("clicks=" + screen.clicks());
    }
}
~~~

~~~bash
javac -encoding UTF-8 InnerCallbackDemo.java
java InnerCallbackDemo
~~~

Stdout:

~~~text
clicks=2
~~~

`ClickHandler` is an Inner object using Screen's state. If the handler is registered with a long-lived registry, the code needs to design cleanup/unregistering to avoid inadvertently extending Screen's lifetime.

## 27. Inner access to private outer state does not mean breaking invariants is allowed

Because Inner can modify private outer state, the designer must protect domain invariants.

Bad example:

~~~java
class Wallet {
    private long cents;

    class Operator {
        void change(long delta) {
            cents += delta; // Could break the non-negative invariant.
        }
    }
}
~~~

Better design: Inner calls a **validated** private outer method:

Create **`InnerInvariantDemo.java`**:

~~~java
public class InnerInvariantDemo {
    static final class Wallet {
        private long cents;

        private void add(long amount) {
            if (amount < 0) {
                throw new IllegalArgumentException("negative");
            }
            cents = Math.addExact(cents, amount);
        }

        long cents() {
            return cents;
        }

        class Operator {
            void deposit(long amount) {
                Wallet.this.add(amount);
            }
        }
    }

    public static void main(String[] args) {
        Wallet wallet = new Wallet();
        Wallet.Operator operator = wallet.new Operator();

        operator.deposit(100);
        System.out.println("balance=" + wallet.cents());

        try {
            operator.deposit(-5);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected=" + ex.getMessage());
        }

        System.out.println("after=" + wallet.cents());
    }
}
~~~

~~~bash
javac -encoding UTF-8 InnerInvariantDemo.java
java InnerInvariantDemo
~~~

Stdout:

~~~text
balance=100
rejected=negative
after=100
~~~

The inner method calls the outer's validated logic, avoiding unsafe direct manipulation on the field. Private access for an inner is a **capability**, not proof that state is automatically safe.

## 28. When should you use an inner member class?

Consider using one when:

- Inner behavior is **naturally bound to a specific outer instance**.
- The helper needs to access the owner's private state, and the owner manages the lifecycle.
- The inner exists as an implementation detail that is minimally exposed externally.
- One owner can create multiple inner helpers with their own state.
- There is no need for the inner to exist independently of the owner.
- The association and reachability are clearly understood, with cleanup if a callback is registered outside the owner.

Examples: an iterator associated with a collection instance, a view/editor associated with a document instance, a listener managed by a UI component.

### When should you choose an alternative?

Choose a **static nested class** or a top-level class when the helper does not use outer state. Choose composition/interfaces and an explicit constructor dependency when ownership needs to be clear. Choose an immutable DTO if you only want to provide a data snapshot without needing to keep the owner alive via the inner.

A public API exposing `Outer.Inner` can tightly couple clients to implementation nesting. Do not expose an inner type merely for syntactic convenience when a standalone interface would be more appropriate.

## 29. Comparison table of the four nested constructs

| Kind | Where declared | Enclosing instance |
| --- | --- | --- |
| Member inner class | Inside a class body, without `static` | Requires an outer instance |
| Static nested class | Inside a class body, with `static` | Does not require an outer instance |
| Local class | Inside a block/method/constructor | Depends on the enclosing context; captures eligible locals |
| Anonymous class | At a class instance creation expression | Depends on the enclosing context |

A class declared inside an interface is usually an **implicit static member type**, without an enclosing interface object like a non-static inner class of an ordinary outer class. Do not lump these cases together into a single rule that “every class written inside another class needs an outer object”.

## 30. Common misconceptions

| Misconception | Correct understanding |
| --- | --- |
| “Outer.Inner is an inner object.” | It is a type name; there is no object yet. |
| “Creating Outer always automatically creates Inner.” | Only when code explicitly creates Inner. |
| “Inner extends Outer.” | Nesting is different from inheritance. |
| “new Outer.Inner() is always valid.” | A non-static inner from outside requires outer.new Inner(). |
| “A static method can call new Inner() without a qualifier.” | An explicit outer instance is required. |
| “this inside Inner is Outer.” | this is the inner; Outer.this is the outer. |
| “Outer.this selects the most recently created Outer.” | It is the enclosing outer of the current inner itself. |
| “Two Inners from two Outers are two different Java classes.” | Same member runtime type, different enclosing instances. |
| “Assigning an inner to another variable changes the outer association.” | No; it only aliases the reference. |
| “Inner cannot read private Outer fields.” | Yes, it can, under nesting access rules. |
| “Private outer fields cannot have their invariants broken by an inner.” | Inner can modify them, so validation is needed. |
| “Member inner and static nested are identical.” | A static nested class has no enclosing outer instance. |
| “Java 17 inner classes are forbidden from having any static methods.” | The old restriction changed in Java SE 16. |
| “Reflection getDeclaringClass returns the outer object.” | It returns the Class metadata of the outer type. |
| “The synthetic field this$0 can be used as an API.” | No, it is an implementation detail. |
| “An inner listener cannot keep the owner reachable.” | It can extend the owner's lifetime. |
| “Switching to static nested always eliminates memory retention.” | Not if an explicit strong Outer reference is still held. |
| “Inner's name being tied to Outer means inner cannot be a parameter.” | An inner instance is still an ordinary reference value. |

## 31. Exercise 1 — Counting instances

~~~java
class Car {
    class Wheel {}
}

Car car = new Car();
Car.Wheel front = car.new Wheel();
Car.Wheel rear = car.new Wheel();
~~~

**Answer:** One Car instance and two Wheel instances, sharing the same enclosing Car. `front != rear` is true. The member class declaration does not automatically create Wheel objects.

## 32. Exercise 2 — Fixing syntax

~~~java
class Outer {
    class Inner {}
}
// Outer.Inner inner = new Outer.Inner();
~~~

**Answer:** For a non-static inner, you need:

~~~java
Outer outer = new Outer();
Outer.Inner inner = outer.new Inner();
~~~

If Inner truly does not need an Outer instance, declare `static class Inner` and then use `new Outer.Inner()`.

## 33. Exercise 3 — Scope and shadowing

Outer field `int number=10`, Inner field `int number=20`, method parameter `int number=30`.

**Answer:** `number` is 30; `this.number` is 20; `Outer.this.number` is 10. Use qualification to specify clearly which owner a field belongs to.

## 34. Exercise 4 — One class type, multiple owner objects

Two outer objects a and b; two inner objects `a.new Inner()` and `b.new Inner()`.

**Answer:** The inner objects are associated with different owners, even though they have the same runtime inner class type. `==` between the two inner references is false if they were created by two separate new expressions.

## 35. Exercise 5 — Static context and null

Inside a static method containing `Outer outer = null; Outer.Inner item = outer.new Inner();`, what is the result?

**Answer:** When the expression executes, a `NullPointerException`. If `new Inner()` is written without a qualifier inside a static method of Outer, it normally produces a compile error due to the missing enclosing instance. The two errors belong to two different stages.

## 36. Exercise 6 — Reflection

What does `Outer.Inner.class.getDeclaringClass()` return?

**Answer:** The Class object representing the Outer **type**; it does not return a specific outer instance. If a client needs the owner object, you can design a method on Inner using `Outer.this` to return the owner according to the access contract.

## 37. Exercise 7 — Memory retention

A Screen creates an inner ClickHandler, registers it in a global registry, and does not unregister it when Screen closes. Why is there a problem?

**Answer:** The registry holds the handler; the handler has an enclosing association using Screen's state, so it can keep Screen reachable. Lifecycle unregistering is needed, or an appropriate callback/dependency design. A static nested class with a strong Screen field can still retain the owner.

## 38. Exercise 8 — Java 17 static declarations

Is `class Inner { static int twice(int n) { return n*2; } }` declared inside a non-static class Outer valid in Java 17?

**Answer:** Yes, since Java SE 16, static declarations inside inner classes have been allowed. However, an Inner instance still requires an enclosing outer, and the static method has no `Outer.this` receiver.

## 39. End-of-lesson checklist

- [ ] I know that a member inner class is a non-static member nested class.
- [ ] I distinguish type declaration from object creation.
- [ ] I understand that an inner instance has an enclosing outer instance.
- [ ] I know that the Outer object and the Inner object are two separate ordinary objects.
- [ ] I know outer.new Inner() from outside code.
- [ ] I know new Inner() inside an Outer instance method.
- [ ] I understand that new Outer().new Inner() constructs outer before inner.
- [ ] I do not use new Outer.Inner() for a non-static inner from outside.
- [ ] I know that a static context needs an explicit outer object.
- [ ] I know that a null outer qualifier causes NullPointerException.
- [ ] I distinguish between this and Outer.this.
- [ ] I understand parameter/inner/outer field shadowing.
- [ ] I know that an inner can access private outer members.
- [ ] I know that an outer can access private inner members under nesting rules.
- [ ] I know that nesting is not inheritance.
- [ ] I know that one Outer can create multiple Inner instances.
- [ ] I know that multiple Outer objects can create Inners of the same runtime class type.
- [ ] I do not assume reassigning an inner reference changes the enclosing association.
- [ ] I distinguish static nested, local, and anonymous classes.
- [ ] I know generic Outer<T>.Inner<U> type usage.
- [ ] I know that a Java 17 inner can declare static members.
- [ ] I know that Class.getDeclaringClass() returns type metadata.
- [ ] I know that the reflection constructor has an enclosing outer parameter.
- [ ] I do not rely on synthetic field names as an API.
- [ ] I understand that an inner callback can extend outer reachability.
- [ ] I know to clean up/unregister within the appropriate lifecycle.
- [ ] I do not accidentally expose the outer owner through a public API.
- [ ] I protect outer invariants even though the inner has private access.
- [ ] I choose a static nested/independent helper if the outer is not needed.
- [ ] I can read and explain the stdout of the Java 17+ examples.

**Conclusion:** A non-static **inner member class** declared inside Outer **can create multiple inner objects**, and **each inner object is associated with exactly one enclosing Outer instance** at creation time. The core syntax is `outer.new Inner()`; inside Inner, `this` represents the inner while `Outer.this` represents the owner. This is a nesting/enclosing relationship, not inheritance; it does not automatically create an inner when the outer is created and does not encode the outer object's identity into the inner type. Use an inner class when the helper genuinely depends on the owner; choose a static nested class/composition when it does not, and always manage invariants alongside the callback lifecycle.
