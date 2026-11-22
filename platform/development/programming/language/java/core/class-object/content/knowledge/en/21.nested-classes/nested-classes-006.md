# Name Shadowing and Qualification with `Outer.this` in Java

## 1. The Problem: A Name Appearing in Multiple Scopes

In Java, a **non-static inner class (*inner class*)** can access the members of an **enclosing class object (*enclosing instance*)**. However, the inner class can also declare a field, parameter, or local variable **with the same name** as an outer member.

Example:

```java
class Outer {
    String name = "outer";

    class Inner {
        String name = "inner";

        void print(String name) {
            System.out.println(name);
            System.out.println(this.name);
            System.out.println(Outer.this.name);
        }
    }
}
```

The three expressions in the `print` method have three different meanings:

- `name`: the method **parameter**, because the parameter name shadows declarations with the same name in outer scopes.
- `this.name`: the `name` field of the **Inner object currently executing the method**.
- `Outer.this.name`: the `name` field of the **enclosing Outer object associated with that Inner object**.

The **`Outer.this`** syntax is a *qualified this expression*. It explicitly specifies a lexically enclosing object that has a matching **enclosing instance**. It does not create a new object, does not retrieve an arbitrary Outer object, and is not a mechanism for accessing static fields.

> **Quick rule of thumb:** `name` looks up the name by scope; `this.name` starts from the current receiver; `Outer.this.name` starts from the enclosing instance of type `Outer`.

This lesson belongs to the **Nested Classes** group, focusing on **name shadowing (*shadowing*)**, distinguishing receivers, and using `Outer.this` appropriately in Java 17+.

## 2. First Complete Example: Three Values for the Same Name

Create the file **`OuterThisBasicsDemo.java`**:

```java
class Outer {
    private final String name = "OUTER";

    class Inner {
        private final String name = "INNER";

        void show(String name) {
            System.out.println("parameter=" + name);
            System.out.println("inner=" + this.name);
            System.out.println("outer=" + Outer.this.name);
        }
    }
}

public class OuterThisBasicsDemo {
    public static void main(String[] args) {
        Outer outer = new Outer();
        Outer.Inner inner = outer.new Inner();

        inner.show("LOCAL");
    }
}
```

Compile and run:

```bash
javac OuterThisBasicsDemo.java
java OuterThisBasicsDemo
```

**Standard output:**

```text
parameter=LOCAL
inner=INNER
outer=OUTER
```

Explanation from top to bottom:

1. `new Outer()` creates an Outer object.
2. `outer.new Inner()` creates an Inner object **bound to outer**.
3. When `show("LOCAL")` runs, the `name` parameter has the value LOCAL.
4. `this` in `Inner.show` is the Inner receiver, so `this.name` is INNER.
5. `Outer.this` refers to the enclosing Outer instance, so `Outer.this.name` is OUTER.

**Important note:** The Outer field is declared `private`, yet Inner can still access it validly. In Java, nested classes and enclosing classes have access to each other's private members under the nested class access rules; `private` itself does not block `Outer.this.name` in the example.

## 3. What Does “Name Shadowing” Mean?

*Shadowing* occurs when a declaration in a closer scope causes an **unqualified simple name** usage to select that declaration instead of a declaration with the same name in a farther scope.

Example:

```java
int score = 10;
{
    // int score = 20; // Invalid if a local name is duplicated
    // in an overlapping local scope like this example.
}
```

This is a **code snippet** illustrating a local-variable rule that differs from field shadowing: Java **does not allow arbitrarily redeclaring a local variable in nested overlapping scope blocks**. However, a class field and a parameter/local variable **can share the same name** under different rules.

In a nested class:

```java
class Outer {
    int number = 1;

    class Inner {
        int number = 2;

        void show(int number) {
            System.out.println(number);
            System.out.println(this.number);
            System.out.println(Outer.this.number);
        }
    }
}
```

Here:

- `number` in the method refers to the parameter.
- `this.number` refers to the Inner field.
- `Outer.this.number` refers to the Outer field.

It is **not** that the compiler “forgets” the Outer field. It still exists, but when a short name is shadowed, you must use a **qualified receiver** to state precisely which field you want.

## 4. Distinguishing Field Shadowing from Reassignment

Name shadowing is a **compile-time name resolution** issue; it is not synonymous with changing an object reference or mutating a field.

Create **`ShadowingAssignmentsDemo.java`**:

```java
class Outer {
    private int count = 1;

    class Inner {
        private int count = 2;

        void modify(int count) {
            count += 10;                 // Modifies only the parameter.
            this.count += 20;            // Modifies the Inner field.
            Outer.this.count += 30;      // Modifies the Outer field.

            System.out.println("parameter=" + count);
            System.out.println("inner=" + this.count);
            System.out.println("outer=" + Outer.this.count);
        }
    }

    int count() {
        return count;
    }
}

public class ShadowingAssignmentsDemo {
    public static void main(String[] args) {
        Outer outer = new Outer();
        Outer.Inner inner = outer.new Inner();

        inner.modify(5);
        System.out.println("outside outer=" + outer.count());
    }
}
```

```bash
javac ShadowingAssignmentsDemo.java
java ShadowingAssignmentsDemo
```

```text
parameter=15
inner=22
outer=31
outside outer=31
```

These are three different state locations:

- Parameter `count` is a local value of the method call, initially 5.
- `this.count` is an instance field belonging to the Inner object, initially 2.
- `Outer.this.count` is an instance field belonging to the associated Outer object, initially 1.

When modifying the Outer field from Inner, the `outer.count()` method outside also sees 31 because this is the **same Outer instance**, not a data copy.

## 5. `Outer.this` Is an Expression Referring to an *Object*, Not Just a Field

You need to fully understand the syntax:

```java
Outer.this
```

This is an **expression whose value is a reference to the enclosing Outer instance**. You can:

- Read a field: `Outer.this.name`.
- Call an instance method: `Outer.this.describe()`.
- Pass it as an argument: `register(Outer.this)`.
- Compare identity: `Outer.this == expectedOuter`.
- Create a method reference: `Outer.this::describe` when a functional interface matches.

**You cannot reassign `Outer.this` itself** like a mutable field:

```java
// Outer.this = anotherOuter; // Invalid: qualified this is not an lvalue.
```

The enclosing instance link is established when the inner object is created; normally, you cannot “switch this Inner to another Outer” by assigning to `Outer.this`.

### Example Using Methods and Object Identity

Create **`OuterInstanceReferenceDemo.java`**:

```java
final class Outer {
    private final String id;

    Outer(String id) {
        this.id = id;
    }

    String describe() {
        return "Outer(" + id + ")";
    }

    class Inner {
        String summary() {
            return Outer.this.describe();
        }

        boolean belongsTo(Outer candidate) {
            return Outer.this == candidate;
        }
    }
}

public class OuterInstanceReferenceDemo {
    public static void main(String[] args) {
        Outer first = new Outer("A");
        Outer second = new Outer("B");

        Outer.Inner inner = first.new Inner();

        System.out.println(inner.summary());
        System.out.println(inner.belongsTo(first));
        System.out.println(inner.belongsTo(second));
    }
}
```

```bash
javac OuterInstanceReferenceDemo.java
java OuterInstanceReferenceDemo
```

```text
Outer(A)
true
false
```

`Outer.this` in `inner.summary` is **first**, not second, because Inner was created with `first.new Inner()`.

## 6. Why Does an Inner Object Know Its Enclosing Outer Instance?

A **non-static member inner class** is declared inside a class, and when created in a normal context, its instance is associated with an enclosing instance.

Example:

```java
Outer a = new Outer();
Outer b = new Outer();

Outer.Inner ia = a.new Inner();
Outer.Inner ib = b.new Inner();
```

This is an **illustrative code snippet**, assuming Outer has a no-argument constructor and Inner has a matching constructor. `ia` is associated with a, and `ib` is associated with b.

Diagram:

```text
a ──> Outer A <──── enclosing instance ── Inner ia

b ──> Outer B <──── enclosing instance ── Inner ib
```

When a method of `ia` uses `Outer.this`, it gets Outer A. When a method of `ib` uses `Outer.this`, it gets Outer B.

The JVM/compiler may use synthetic fields or an equivalent representation to implement this link. **You should not depend on compiler-generated field names** such as `this$0` or the runtime layout to write application code. Rely on the `Outer.this` semantics specified by Java.

## 7. Two Different Outers, Same Inner Type, No Shared State

Create **`TwoOuterInstancesDemo.java`**:

```java
class Outer {
    private final String label;
    private int counter;

    Outer(String label) {
        this.label = label;
    }

    class Inner {
        void incrementOuter() {
            Outer.this.counter++;
        }

        String snapshot() {
            return label + "=" + Outer.this.counter;
        }
    }
}

public class TwoOuterInstancesDemo {
    public static void main(String[] args) {
        Outer first = new Outer("first");
        Outer second = new Outer("second");

        Outer.Inner left = first.new Inner();
        Outer.Inner right = second.new Inner();

        left.incrementOuter();
        left.incrementOuter();
        right.incrementOuter();

        System.out.println(left.snapshot());
        System.out.println(right.snapshot());
    }
}
```

```bash
javac TwoOuterInstancesDemo.java
java TwoOuterInstancesDemo
```

```text
first=2
second=1
```

Each Inner instance uses **its own** enclosing object. `Outer.this` is not a static variable shared across all Inner instances.

This is important in event handlers, callbacks, UI components, or helpers held in an owner object: the inner instance can manipulate the exact state of its owner.

## 8. `this` and `Outer.this` When There Is No Name Collision

Even when there is no shadowing, you can still choose the qualified syntax:

```java
class Outer {
    private int capacity = 10;

    class Inner {
        int capacity() {
            return capacity;            // Can resolve to outer.
        }

        int explicitCapacity() {
            return Outer.this.capacity; // Explicit owner.
        }
    }
}
```

In the example, Inner **does not declare** a `capacity` field, so a simple name lookup can find the outer field. `Outer.this.capacity` explicitly states where the field belongs and reduces risk if Inner later adds a field with the same name.

**Balancing readability:** You do not necessarily have to write `Outer.this` for every use of an outer field. Use it when a name is shadowed, when code might be ambiguous, or when you want to clarify the receiver in multi-level logic.

## 9. Multiple Levels of Nested Classes: `Outer.this`, `Middle.this`, `this`

An inner class can be declared inside another inner class. In that case, there are **multiple lexically enclosing instances**.

Create **`ThreeLevelShadowingDemo.java`**:

```java
class Outer {
    private final String id = "OUTER";

    class Middle {
        private final String id = "MIDDLE";

        class Inner {
            private final String id = "INNER";

            void show(String id) {
                System.out.println("parameter=" + id);
                System.out.println("inner=" + this.id);
                System.out.println("middle=" + Middle.this.id);
                System.out.println("outer=" + Outer.this.id);
            }
        }
    }
}

public class ThreeLevelShadowingDemo {
    public static void main(String[] args) {
        Outer outer = new Outer();
        Outer.Middle middle = outer.new Middle();
        Outer.Middle.Inner inner = middle.new Inner();

        inner.show("LOCAL");
    }
}
```

```bash
javac ThreeLevelShadowingDemo.java
java ThreeLevelShadowingDemo
```

```text
parameter=LOCAL
inner=INNER
middle=MIDDLE
outer=OUTER
```

Lookup for each expression:

| Expression | Receiver / Scope |
| --- | --- |
| `id` | Parameter of method `show` |
| `this.id` | Inner object |
| `Middle.this.id` | Middle instance enclosing Inner |
| `Outer.this.id` | Outer instance enclosing Middle and Inner |

**Common mistake:** Thinking that with multiple levels, `Outer.this` points to the “most recently created Outer”. Not true: it points to the **Outer enclosing instance corresponding to the currently running inner object**.

## 10. Using Reference Identity to Prove the Enclosing Instance Chain

You can check with `==`:

Create **`EnclosingIdentityDemo.java`**:

```java
class Outer {
    class Middle {
        class Inner {
            boolean linkedTo(Outer expectedOuter,
                             Middle expectedMiddle) {
                return Outer.this == expectedOuter
                        && Middle.this == expectedMiddle;
            }
        }
    }
}

public class EnclosingIdentityDemo {
    public static void main(String[] args) {
        Outer first = new Outer();
        Outer other = new Outer();

        Outer.Middle middle = first.new Middle();
        Outer.Middle.Inner inner = middle.new Inner();

        System.out.println(inner.linkedTo(first, middle));
        System.out.println(inner.linkedTo(other, middle));
    }
}
```

```bash
javac EnclosingIdentityDemo.java
java EnclosingIdentityDemo
```

```text
true
false
```

This is an identity check and **does not call `equals()`**. If Outer overrides equals by value, two Outer objects can be equal to each other while still not being the same enclosing instance.

Using `==` in this test is intentional because the question is **is it that exact enclosing object?**

## 11. `Outer.this` Is Not the Same as `Outer.class`

These two expressions serve completely different goals:

- `Outer.this`: an **Outer instance reference** linked lexically/as an enclosing instance in an appropriate instance context.
- `Outer.class`: a `Class<Outer>` object describing the **Outer type**.
- `Outer.staticField`: a reference to a **static field** of the class, requiring no enclosing instance.

Illustrative example:

```java
class Outer {
    static int sharedCount = 1;
    int instanceCount = 2;

    class Inner {
        int total() {
            return Outer.sharedCount + Outer.this.instanceCount;
        }
    }
}
```

`Outer.class` does not mean “get the outer object containing the inner object”; class metadata cannot replace an instance reference.

**Syntax to avoid when reading code:** `Outer.this.instanceCount` is instance-qualified access; whereas `Outer.sharedCount` is static-qualified access. If the goal is to access a static field, write it explicitly via the class name.

## 12. A Static Nested Class Has No Implicit Enclosing Outer Instance

This is the most important limitation of `Outer.this`.

A **static nested class** is declared as:

```java
class Outer {
    private int value = 10;

    static class Nested {
        void show() {
            // System.out.println(Outer.this.value); // Invalid.
        }
    }
}
```

`Nested` in this example **does not have an automatic enclosing Outer instance**. Even though it is declared in Outer's source, lexical nesting does not attach a static nested object to a specific Outer object.

Therefore, `Outer.this` is **invalid** from a static nested class if there is no lexically enclosing Outer instance in that context.

### How to Fix: Pass the Outer Instance Explicitly

Create **`StaticNestedExplicitOwnerDemo.java`**:

```java
class Outer {
    private final int value;

    Outer(int value) {
        this.value = value;
    }

    static class Nested {
        private final Outer owner;

        Nested(Outer owner) {
            this.owner = owner;
        }

        int readValue() {
            return owner.value;
        }
    }
}

public class StaticNestedExplicitOwnerDemo {
    public static void main(String[] args) {
        Outer owner = new Outer(10);
        Outer.Nested nested = new Outer.Nested(owner);

        System.out.println(nested.readValue());
    }
}
```

```bash
javac StaticNestedExplicitOwnerDemo.java
java StaticNestedExplicitOwnerDemo
```

```text
10
```

`owner.value` is allowed inside nested class code because of the private-member access rules between nested/enclosing classes; however, **the owner reference is passed in**, not derived from `Outer.this`.

**Do not confuse them:** `Outer.Nested` is still a *nested class*, but it is not an *inner class* in the sense of a non-static member inner class.

## 13. `Outer.this` Also Cannot Be Used Inside a Static Method of Outer

A static method does not have an implicit `this` receiver.

```java
class Outer {
    private int value = 10;

    static void wrong() {
        // System.out.println(this.value);       // Invalid.
        // System.out.println(Outer.this.value); // Invalid.
    }
}
```

If a static method needs an Outer object, accept or create a reference explicitly:

```java
static int read(Outer candidate) {
    return candidate.value;
}
```

This is an illustrative method snippet placed inside Outer. A static method knows the Outer **type**, but it does not know **which instance** should be chosen as the enclosing instance.

### Quick Question Rule

“Is there a valid implicit/lexically enclosing **Outer instance** in the current code?” If **no**, `Outer.this` does not help create that instance.

In a static nested class, even if there is an `Outer owner` variable, `owner.value` is valid while `Outer.this.value` does not become valid just because the owner variable exists.

## 14. A Local Class Inside an Instance Method Can Use the Enclosing Instance

Nested classes do not consist only of member classes. A **local class** can also be declared inside a method block.

Create **`LocalClassOuterThisDemo.java`**:

```java
class Outer {
    private final String label;

    Outer(String label) {
        this.label = label;
    }

    void execute() {
        class LocalTask {
            private final String label = "LOCAL";

            void run(String label) {
                System.out.println("argument=" + label);
                System.out.println("local class=" + this.label);
                System.out.println("outer=" + Outer.this.label);
            }
        }

        new LocalTask().run("PARAM");
    }
}

public class LocalClassOuterThisDemo {
    public static void main(String[] args) {
        new Outer("OWNER").execute();
    }
}
```

```bash
javac LocalClassOuterThisDemo.java
java LocalClassOuterThisDemo
```

```text
argument=PARAM
local class=LOCAL
outer=OWNER
```

`LocalTask` is declared inside an **instance method** of Outer. When executing, it has an enclosing Outer context, so `Outer.this.label` is allowed.

**Conversely:** A local class declared inside a **static method** of Outer does not automatically have an enclosing Outer instance. When a specific Outer is needed, pass the reference via a constructor/parameter just as with a static nested class.

## 15. Local Variables and Captured Variables Are Not Outer Fields

Local classes and lambdas can reference local variables from the enclosing method if they are **final or effectively final** according to Java's rules.

Illustrative example:

```java
void perform() {
    String prefix = "HELLO";

    class Task {
        void run() {
            System.out.println(prefix);
        }
    }

    new Task().run();
}
```

This is an **instance method snippet** placed inside a valid class.

`prefix` is a **local variable captured from the method**, not the field `Outer.this.prefix`. If Outer has no prefix field, then `Outer.this.prefix` is completely unrelated.

Modifying the local variable `prefix` after creating Task (within code regions that still affect the capture condition) can break effectively-final status and prevent the program from compiling.

**Distinguishing scopes:**

- Local/parameter captured variable → direct variable name, obeying effectively-final.
- Inner field → `this.field`.
- Outer field → `Outer.this.field`.
- Static field → `Outer.field`.

`Outer.this` is not used to bypass the effectively-final rule for captured local variables.

## 16. Anonymous Class: `this` Is the Anonymous Object, `Outer.this` Is Outer

An anonymous class creates a class without its own source-level name and an object from that class. Inside the anonymous class body, `this` points to the anonymous object itself.

Create **`AnonymousClassOuterThisDemo.java`**:

```java
class Outer {
    private final String name;

    Outer(String name) {
        this.name = name;
    }

    Runnable task() {
        return new Runnable() {
            private final String name = "ANONYMOUS";

            @Override
            public void run() {
                System.out.println("this=" + this.name);
                System.out.println("outer=" + Outer.this.name);
                System.out.println("anonymous=" +
                        this.getClass().isAnonymousClass());
            }
        };
    }
}

public class AnonymousClassOuterThisDemo {
    public static void main(String[] args) {
        Runnable task = new Outer("OWNER").task();
        task.run();
    }
}
```

```bash
javac AnonymousClassOuterThisDemo.java
java AnonymousClassOuterThisDemo
```

```text
this=ANONYMOUS
outer=OWNER
anonymous=true
```

- `this` inside `run` is the anonymous Runnable object.
- `Outer.this` is the Outer instance where the anonymous class was created.
- `getClass().isAnonymousClass()` checks that the runtime class is anonymous.
- They are two distinct objects even though the code is nested at the source level.

**Note:** An anonymous class declared in a static context does not automatically bind to an Outer instance; this example runs inside the **Outer.task() instance method**.

## 17. Lambdas Differ from Anonymous Classes in `this` Semantics

A lambda **does not create a new `this` receiver that can be referenced using the `this` keyword** inside the lambda body. `this` inside a lambda has the same meaning as in its enclosing **lexical context**.

Create **`LambdaThisDemo.java`**:

```java
class Outer {
    private final String name = "OUTER";

    Runnable createTask() {
        return () -> {
            System.out.println("this=" + this.name);
            System.out.println("qualified=" + Outer.this.name);
        };
    }
}

public class LambdaThisDemo {
    public static void main(String[] args) {
        Outer outer = new Outer();
        Runnable task = outer.createTask();

        task.run();
    }
}
```

```bash
javac LambdaThisDemo.java
java LambdaThisDemo
```

```text
this=OUTER
qualified=OUTER
```

In `Outer.createTask()`, the enclosing lexical `this` is the Outer object. The lambda uses that same `this`, without switching to an anonymous implementation object's `this` as an anonymous class does.

### Lambdas Declared Inside Inner

If a lambda is written inside an **instance method of Inner**, `this` in the lambda is the Inner instance; `Outer.this` still refers to the Outer instance if a lexically enclosing Outer context is valid.

**Summary:** Do not infer from a lambda being assigned to a `Runnable` variable that `this` inside the lambda is a Runnable object. With an anonymous class, `this` refers to the anonymous object; with a lambda, it follows the lexical context.

## 18. Combined Example of a Lambda Inside Inner and Two Fields with the Same Name

Create **`InnerLambdaShadowDemo.java`**:

```java
class Outer {
    private final String value = "OUTER";

    class Inner {
        private final String value = "INNER";

        Runnable task() {
            return () -> {
                System.out.println("inner=" + this.value);
                System.out.println("outer=" +
                        Outer.this.value);
            };
        }
    }
}

public class InnerLambdaShadowDemo {
    public static void main(String[] args) {
        Outer outer = new Outer();
        Outer.Inner inner = outer.new Inner();

        inner.task().run();
    }
}
```

```bash
javac InnerLambdaShadowDemo.java
java InnerLambdaShadowDemo
```

```text
inner=INNER
outer=OUTER
```

`this` inside the lambda declared by `Inner.task()` is the Inner receiver; `Outer.this` is still the Outer receiver. Because both classes declare the `value` field, qualification clarifies the data source.

If you replace the lambda with an anonymous Runnable, `this` inside `run()` will be the anonymous object, so to refer to Inner you can use **`Inner.this.value`** from that anonymous class; `Outer.this.value` still points to Outer.

## 19. Anonymous Class Inside Inner: Three Separate Receivers

Create **`AnonymousInsideInnerDemo.java`**:

```java
class Outer {
    private final String label = "OUTER";

    class Inner {
        private final String label = "INNER";

        Runnable create() {
            return new Runnable() {
                private final String label = "ANONYMOUS";

                @Override
                public void run() {
                    System.out.println(this.label);
                    System.out.println(Inner.this.label);
                    System.out.println(Outer.this.label);
                }
            };
        }
    }
}

public class AnonymousInsideInnerDemo {
    public static void main(String[] args) {
        Outer outer = new Outer();
        Outer.Inner inner = outer.new Inner();
        inner.create().run();
    }
}
```

```bash
javac AnonymousInsideInnerDemo.java
java AnonymousInsideInnerDemo
```

```text
ANONYMOUS
INNER
OUTER
```

Receivers inside the `run()` method:

| Expression | Object |
| --- | --- |
| `this` | Anonymous Runnable instance |
| `Inner.this` | Enclosing Inner instance |
| `Outer.this` | Enclosing Outer instance |

This is a useful pattern when a callback needs to use the state of an enclosing component while also having its own state inside the callback.

## 20. Inherited Field, Inner Field, and Outer Field: Do Not Confuse `super` with `Outer.this`

`super.field` relates to **inheritance**, whereas `Outer.this.field` relates to the **enclosing instance**.

Create **`InheritanceVersusEnclosingDemo.java`**:

```java
class Base {
    protected String tag = "BASE";
}

class Outer {
    private final String tag = "OUTER";

    class Inner extends Base {
        private final String tag = "INNER";

        void show() {
            System.out.println("this=" + this.tag);
            System.out.println("super=" + super.tag);
            System.out.println("outer=" + Outer.this.tag);
        }
    }
}

public class InheritanceVersusEnclosingDemo {
    public static void main(String[] args) {
        Outer outer = new Outer();
        outer.new Inner().show();
    }
}
```

```bash
javac InheritanceVersusEnclosingDemo.java
java InheritanceVersusEnclosingDemo
```

```text
this=INNER
super=BASE
outer=OUTER
```

- `this.tag`: Inner field.
- `super.tag`: field belonging to superclass Base, referenced via inheritance.
- `Outer.this.tag`: field belonging to the **enclosing Outer instance**, not Inner's superclass.

**Syntactic nesting is not an inheritance hierarchy:** Declaring Inner inside Outer **does not mean Inner extends Outer**. In the example, Inner extends Base; Outer is the enclosing class.

## 21. `Outer.this.method()` When Inner Also Has a Method with the Same Name

Shadowing does not only occur with fields; when Inner and Outer have methods with the same name, you need to understand which receiver invokes the method.

Create **`MethodReceiverDemo.java`**:

```java
class Outer {
    String label() {
        return "OUTER";
    }

    class Inner {
        String label() {
            return "INNER";
        }

        void show() {
            System.out.println(label());
            System.out.println(this.label());
            System.out.println(Outer.this.label());
        }
    }
}

public class MethodReceiverDemo {
    public static void main(String[] args) {
        Outer outer = new Outer();
        outer.new Inner().show();
    }
}
```

```bash
javac MethodReceiverDemo.java
java MethodReceiverDemo
```

```text
INNER
INNER
OUTER
```

An unqualified `label()` inside an Inner method selects the matching method on Inner. `this.label()` explicitly specifies the Inner receiver. `Outer.this.label()` forces the instance method call on the enclosing Outer object.

**Be careful with terminology:** Field hiding/shadowing and **method lookup/overloading/overriding** have separate rules. This example illustrates how to **select a receiver explicitly**, without claiming that every method with the same name is “shadowed” like a field across all overloads/signatures.

## 22. Modifying the Wrong Receiver Can Cause Bugs That Are Very Hard to Spot

Suppose Inner is an editor controlling an Outer model:

```java
class Document {
    private String title = "Untitled";

    class Editor {
        private String title = "Editor panel";

        void renameDocument(String title) {
            OuterLogic:
            {
                // No label is needed in real code;
                // choosing the right receiver is the focus.
                Document.this.title = title;
            }
        }

        String panelTitle() {
            return this.title;
        }
    }
}
```

This is a **valid but illustrative-only declaration**, without `main`. The `OuterLogic` label has no effect on name lookup; the simpler and recommended way to write it is:

```java
void renameDocument(String title) {
    Document.this.title = title;
}
```

In the `renameDocument` method:

- `title`: parameter holding the new name.
- `this.title`: field of the Editor panel.
- `Document.this.title`: field of the Document model.

If you accidentally write `this.title = title`, the code may compile yet **change the panel's title instead of the document's**. Thus, qualified this both resolves compiler ambiguity and targets **the right domain object**.

## 23. Runnable Example Modifying Outer Correctly Without Modifying Inner

Create **`EditorOuterThisDemo.java`**:

```java
class Document {
    private String title = "Untitled";

    String title() {
        return title;
    }

    class Editor {
        private String title = "Editor panel";

        void renameDocument(String title) {
            Document.this.title = title;
        }

        String panelTitle() {
            return this.title;
        }
    }
}

public class EditorOuterThisDemo {
    public static void main(String[] args) {
        Document doc = new Document();
        Document.Editor editor = doc.new Editor();

        editor.renameDocument("Java Guide");

        System.out.println("document=" + doc.title());
        System.out.println("panel=" + editor.panelTitle());
    }
}
```

```bash
javac EditorOuterThisDemo.java
java EditorOuterThisDemo
```

```text
document=Java Guide
panel=Editor panel
```

Here the parameter, the Inner field, and the Outer field are all named `title`. `Document.this.title` is the expression required to ensure changing the Document owner's state.

**Do not confuse them:** `Document.title` is not valid syntax to access a (non-static) instance field from here; `Document.this.title` uses the enclosing Document instance itself.

## 24. `Outer.this` and Method References

`Outer.this` can serve as the receiver of a method reference when a functional interface matches.

Create **`OuterMethodReferenceDemo.java`**:

```java
class Outer {
    private final String label;

    Outer(String label) {
        this.label = label;
    }

    String getLabel() {
        return label;
    }

    class Inner {
        java.util.function.Supplier<String> supplier() {
            return Outer.this::getLabel;
        }
    }
}

public class OuterMethodReferenceDemo {
    public static void main(String[] args) {
        Outer outer = new Outer("OWNER");
        Outer.Inner inner = outer.new Inner();

        java.util.function.Supplier<String> supplier =
                inner.supplier();

        System.out.println(supplier.get());
    }
}
```

```bash
javac OuterMethodReferenceDemo.java
java OuterMethodReferenceDemo
```

```text
OWNER
```

`Outer.this::getLabel` binds the enclosing Outer receiver. When `supplier.get()` is called, it invokes `getLabel()` on that Outer.

If you change it to `this::getLabel` inside Inner when Inner has no matching method, the compiler will not find a corresponding instance method on Inner. Receiver selection in a method reference must be just as explicit as in a regular method invocation.

## 25. `Outer.this` Is Not the Syntax to Create an Inner Class

The syntax for creating a non-static member inner class from the outside:

```java
Outer outer = new Outer();
Outer.Inner inner = outer.new Inner();
```

Whereas:

```java
Outer.this
```

is an **expression referring to the enclosing instance in a valid lexical context**.

Inside an Outer instance method, we can use:

```java
Inner inner = new Inner();
```

because the current enclosing instance is the method's Outer receiver.

**Do not write this in the static main of a standalone class:**

```java
// Outer.Inner x = Outer.this.new Inner(); // There is no Outer.this here.
```

You need a specific Outer object, such as the `outer` variable, to call `outer.new Inner()`. Do not confuse the dot in `outer.new Inner()` with a qualified-this expression.

## 26. Can `Outer.this` Be Used Inside an Inner Constructor?

Yes: the constructor body of a member inner class runs in the context of an Inner instance that has an enclosing Outer instance.

Create **`InnerConstructorOuterThisDemo.java`**:

```java
class Outer {
    private final String id;

    Outer(String id) {
        this.id = id;
    }

    class Inner {
        private final String ownerId;

        Inner() {
            this.ownerId = Outer.this.id;
        }

        String ownerId() {
            return ownerId;
        }
    }
}

public class InnerConstructorOuterThisDemo {
    public static void main(String[] args) {
        Outer outer = new Outer("OUT-1");
        Outer.Inner inner = outer.new Inner();

        System.out.println(inner.ownerId());
    }
}
```

```bash
javac InnerConstructorOuterThisDemo.java
java InnerConstructorOuterThisDemo
```

```text
OUT-1
```

The Inner constructor reads the Outer field to assign its own final field. This is a **snapshot of the String reference/value**. If the Outer field later changes (when it is non-final), the previously assigned Inner.ownerId does not automatically change.

**Lifecycle warning:** Do not let `this`/the enclosing owner escape from a constructor or call overridable methods on the owner before the owner completes construction. This is especially dangerous if the Outer constructor itself creates Inner and then invokes callbacks that might observe incomplete Outer state.

## 27. Qualified this with a Generic Outer

The enclosing class can be a generic class:

```java
class Container<T> {
    private final T item;

    Container(T item) {
        this.item = item;
    }

    class View {
        T get() {
            return Container.this.item;
        }
    }
}
```

`Container.this` is qualified by the **class name**, not by a type argument expression such as `Container<String>.this`.

### Running Example

File **`GenericOuterThisDemo.java`**:

```java
class Container<T> {
    private final T value;

    Container(T value) {
        this.value = value;
    }

    class View {
        T get() {
            return Container.this.value;
        }
    }
}

public class GenericOuterThisDemo {
    public static void main(String[] args) {
        Container<String> container =
                new Container<>("Java");

        Container<String>.View view =
                container.new View();

        System.out.println(view.get());
    }
}
```

```bash
javac GenericOuterThisDemo.java
java GenericOuterThisDemo
```

```text
Java
```

`View.get()` returns `T` from the enclosing `Container<T>` instance. The type parameter `T` is a type-level generic relationship; `Container.this` is an object-reference-level relationship. Do not confuse the two mechanisms.

## 28. Only a Lexical Enclosing Instance of the Matching Type Allows `TypeName.this`

A variable of type Outer does **not** make the expression `Outer.this` valid if the scope has no enclosing instance.

Example:

```java
class Outer {
    int value = 10;

    static class Helper {
        private final Outer explicit;

        Helper(Outer explicit) {
            this.explicit = explicit;
        }

        int read() {
            return explicit.value;    // Valid.
            // return Outer.this.value; // Invalid.
        }
    }
}
```

Similarly, a `Foreign` object cannot write `Outer.this` just because it has an `Outer owner` field. It must use `owner` as the receiver.

**A rule for recognizing this:** Trace the path of **lexically enclosing classes and static/non-static contexts** at that code location. Do not just look at the whole file having the name Outer or having a reference to Outer.

### Distinguishing from Passing `this` as an Argument

An inner method can write `use(Outer.this)` when it wants to pass the enclosing Outer object to a collaborator. However, in a static nested class, you must have an `owner` variable and write `use(owner)`.

## 29. When Is `Outer.this` Not the Best Design Choice?

Inner classes can conveniently access the outer instance, yet they also create **coupling**:

- Inner can mutate Outer's private state through hidden paths.
- An Inner instance can keep the Outer instance alive longer than intended if stored long-term.
- A callback storing an inner class instance can extend the owner's lifetime.
- Multi-level `Outer.this / Middle.this` logic can be hard to maintain.
- Unit testing an Inner instance may require creating an Outer object with full state.

If a helper only needs a few values, consider a **static nested class that receives data explicitly**, or a top-level class with dependency injection.

**There is no rule to “avoid all inner classes”.** Choose a member inner class if the logic truly belongs to each Outer instance and access to Outer state is necessary and clear. Otherwise, use a class with explicit dependencies to reduce coupling.

## 30. Redesigning as a Static Nested Helper When an Enclosing Instance Is Not Needed

Create **`StaticHelperAlternativeDemo.java`**:

```java
class Report {
    private final String title;

    Report(String title) {
        this.title = title;
    }

    static class Formatter {
        private final String prefix;

        Formatter(String prefix) {
            this.prefix = prefix;
        }

        String format(Report report) {
            return prefix + report.title;
        }
    }
}

public class StaticHelperAlternativeDemo {
    public static void main(String[] args) {
        Report report = new Report("Java");
        Report.Formatter formatter =
                new Report.Formatter("Report:");

        System.out.println(formatter.format(report));
    }
}
```

```bash
javac StaticHelperAlternativeDemo.java
java StaticHelperAlternativeDemo
```

```text
Report:Java
```

`Formatter` does not automatically bind to a Report instance. `format(report)` receives the owner explicitly; the dependency relationship is expressed in the method signature. It can still access Report's private field under nested-class access rules, but it does not have `Report.this`.

**Comparison:**

| Design | Where does the owner instance come from? |
| --- | --- |
| Non-static `class Inner` | Enclosing instance when Inner is created |
| `static class Helper` | Explicit parameter, constructor field, or lookup |
| Local class in an instance method | Valid lexically enclosing instance |
| Anonymous class in an instance method | Valid enclosing instance |
| Lambda in an instance method | Lexical `this` of the current context |

## 31. Practice Exercise: Predict Exactly Which Name Is Selected

Create **`ShadowingTraceDemo.java`**:

```java
class Outer {
    private String value = "O";

    class Middle {
        private String value = "M";

        class Inner {
            private String value = "I";

            void update(String value) {
                value = value + "1";
                this.value = this.value + "2";
                Middle.this.value =
                        Middle.this.value + "3";
                Outer.this.value =
                        Outer.this.value + "4";

                System.out.println(value);
                System.out.println(this.value);
                System.out.println(Middle.this.value);
                System.out.println(Outer.this.value);
            }
        }
    }
}

public class ShadowingTraceDemo {
    public static void main(String[] args) {
        Outer outer = new Outer();
        Outer.Middle middle = outer.new Middle();
        Outer.Middle.Inner inner = middle.new Inner();

        inner.update("P");
    }
}
```

```bash
javac ShadowingTraceDemo.java
java ShadowingTraceDemo
```

```text
P1
I2
M3
O4
```

**Explanation for each assignment:**

1. `value = value + "1"` uses the method's `value` parameter, resulting in P1.
2. `this.value = this.value + "2"` modifies Inner's field, I2.
3. `Middle.this.value = ...` modifies Middle's field, M3.
4. `Outer.this.value = ...` modifies Outer's field, O4.

None of the assignments automatically modifies all four. These are four different storage locations.

## 32. A Design Bug Example and Its Fix

Suppose Outer stores the total number of orders; Inner stores the number of times the helper is used:

```java
class Store {
    private int orders;

    class Helper {
        private int orders;

        void registerOrder() {
            // orders++; // Modifies Helper.orders, NOT Store.orders.
            Store.this.orders++;
        }
    }
}
```

This snippet has no `main` but is valid. The name `orders` in Helper shadows the Outer field. If you write `orders++`, the compiler does not report an error because Helper also has a valid field, yet the state of the **wrong object** is updated.

**How to guard with a test:** Check both the Outer and Inner values after the call. If the business intent of `registerOrder` is to increment Store.orders, assert that Store changes while the Helper counter is not mistakenly incremented.

### Runnable Test

File **`ShadowingBugPreventionDemo.java`**:

```java
class Store {
    private int orders;

    int orders() {
        return orders;
    }

    class Helper {
        private int orders;

        void registerOrder() {
            Store.this.orders++;
        }

        int helperOrders() {
            return this.orders;
        }
    }
}

public class ShadowingBugPreventionDemo {
    public static void main(String[] args) {
        Store store = new Store();
        Store.Helper helper = store.new Helper();

        helper.registerOrder();
        helper.registerOrder();

        System.out.println("store=" + store.orders());
        System.out.println("helper=" + helper.helperOrders());
    }
}
```

```bash
javac ShadowingBugPreventionDemo.java
java ShadowingBugPreventionDemo
```

```text
store=2
helper=0
```

This code does not rely on compiler warnings. The test ensures that the **right owner state** is modified.

## 33. Compile-Time Errors to Recognize

| Code snippet / intent | Valid? | Reason |
| --- | --- | --- |
| `this.x` in an Inner instance method | Yes, if member lookup is valid | Accesses the Inner receiver |
| `Outer.this.x` in an Inner instance method | Yes, if an enclosing Outer instance exists and the member is valid | Accesses the Outer receiver |
| `Outer.x` where x is an instance field | Not the normal way to access an instance field | Requires an object reference |
| `Outer.staticX` with a static field | Yes, if access is valid | Does not use an Outer instance |
| `Outer.this = other` | No | Qualified this is not an assignable variable |
| `Outer.this` in a static nested class with no enclosing Outer instance | No | No implicit enclosing Outer instance |
| `Outer.this` in a static method of Outer | No | No receiver instance |
| `Outer.this` in a local class of an Outer instance method | Yes, in a matching lexical context | Bound to an enclosing Outer instance |
| `Outer.this` in a local class of a static method with no enclosing Outer instance | No | Source-level lexical nesting alone does not create an Outer instance |
| `Outer.this` in an anonymous class created in an Outer instance context | Yes | Anonymous object is bound to the lexical Outer context |
| `this` in a lambda inside an Outer instance method | Yes | Uses the lexical Outer receiver |
| `Inner.this` in an anonymous class created from an Inner instance context | Yes | Targets the enclosing Inner instance |
| `Outer.this.someMethod()` | Yes, if the method is valid | Invokes on the Outer receiver |
| `Outer.this::someMethod` | Yes, if the method reference is compatible | Bound instance method reference |
| `new Outer().new Inner()` | Yes, with valid constructors/access | Creates Inner bound to a new Outer object |

**Do not copy the “No” rows verbatim into runnable source files.** They are syntax/semantic error examples for learning.

## 34. Distinguishing `Outer.this` from Similar-Looking Syntax

- `this.field`: receiver of the current instance method/constructor.
- `Outer.this.field`: enclosing Outer instance receiver, when valid.
- `super.field`: field in the superclass of the current receiver, according to access rules.
- `Outer.super.method()`: a form of **qualified-super invocation** in an appropriate context, with the semantics of calling a method in the superclass of the enclosing instance; not synonymous with `Outer.this`. Use only when you properly understand inheritance/access rules.
- `Outer.class`: object describing the Outer type, not an Outer instance.
- `Outer.STATIC_FIELD`: static member access.
- `outer.field`: accesses a field on a reference variable named `outer`, which may point to a different object than `Outer.this`.
- `outer.new Inner()`: creates an inner instance bound to the specified outer object.
- `Outer.Inner`: nested class type name used in declarations/types.

**Key distinction:** `Outer.this` requires a **lexical enclosing instance** relationship at that code location; the variable `outer` is a regular reference that was passed or assigned and can point to any compatible Outer object.

## 35. Review Checklist When Encountering Name Shadowing

- [ ] Have I correctly identified the class/method/block containing the expression?
- [ ] Is the simple name shadowed by a parameter or local variable?
- [ ] Does Inner have a field with the same name as an Outer field?
- [ ] Do multiple levels of Outer/Middle/Inner declare members with the same name?
- [ ] Is `this.field` targeting Inner or an anonymous object?
- [ ] Is `Outer.this.field` needed to select the right Outer owner?
- [ ] If Middle exists, have I used `Middle.this` properly when needed?
- [ ] Do I distinguish `super.member` (inheritance) from `Outer.this.member` (enclosing instance)?
- [ ] Is the receiver of `method()` clear when multiple classes have a method with the same name?
- [ ] Is the current class a non-static inner class or a static nested class?
- [ ] If in a static method/static nested context, have I avoided `Outer.this` when there is no enclosing Outer instance?
- [ ] If Outer is needed from a static nested helper, have I passed the owner reference explicitly?
- [ ] If in a local/anonymous class, have I identified the enclosing instance and effectively-final local variables?
- [ ] If it is a lambda, do I recognize that `this` follows the lexical context rather than a lambda object?
- [ ] Have I avoided reassigning `Outer.this` because it is not an assignable variable?
- [ ] Have I avoided confusing `Outer.class` with an Outer object?
- [ ] Have I avoided confusing `outer.new Inner()` with `Outer.this`?
- [ ] If there are two Outer instances, is Inner guaranteed to be bound to the right owner?
- [ ] Do I use `==` when checking the **identity** of the enclosing object?
- [ ] Are there private fields? Do I understand the nested access rules?
- [ ] Could Inner keep Outer alive longer than expected in callbacks/collections?
- [ ] Should I switch to a static nested helper to reduce coupling if an automatic owner is not needed?
- [ ] Have I tested the exact state of both Inner and Outer after mutation?
- [ ] Do the Java 17+ examples have the right file/public class names, `javac`/`java` commands, and stdout?

## 36. Self-Check Questions and Answers

**Question 1.** Outer and Inner both have a `name` field; inside an Inner method there is a `name` parameter. How do `name`, `this.name`, and `Outer.this.name` differ?

*Answer:* Respectively, the parameter, the Inner field, and the Outer field of the enclosing instance.

**Question 2.** Is `Outer.this` type/class metadata or an object reference?

*Answer:* It is an expression referencing the enclosing Outer instance; metadata is `Outer.class`.

**Question 3.** Inside a static nested class, can `Outer.this` be used to automatically obtain an Outer object?

*Answer:* No. A static nested class has no implicit enclosing Outer instance. Pass the Owner reference explicitly.

**Question 4.** Inside a static method of Outer, is there a `this`?

*Answer:* There is no implicit instance receiver. Therefore, `Outer.this` is also invalid in that static context.

**Question 5.** What does `Outer.Inner inner = outer.new Inner();` make `Outer.this` inside inner point to?

*Answer:* It points to the exact object referenced by `outer` at the time inner is created.

**Question 6.** Do two Inner objects created from two different Outers share Outer state?

*Answer:* Not automatically. Each Inner is bound to its own enclosing Outer instance; static state may still be shared under static rules.

**Question 7.** With Outer→Middle→Inner, how do you read a Middle field that shares the same name as an Inner field?

*Answer:* `Middle.this.field`.

**Question 8.** Can you write `Outer.this = anotherOuter` to change the owner?

*Answer:* No. Qualified this is not an assignable variable.

**Question 9.** Are `super.name` and `Outer.this.name` the same field?

*Answer:* Not necessarily; `super` relates to the superclass of the current receiver, whereas `Outer.this` relates to the enclosing Outer object.

**Question 10.** Why can a private Outer field still be accessed by Inner?

*Answer:* Nested class access rules allow accessing private members among classes within the appropriate nest.

**Question 11.** Inside an anonymous class declared in an Outer instance method, what does `this` point to?

*Answer:* The anonymous instance. `Outer.this` points to the enclosing Outer instance.

**Question 12.** Inside a lambda in an Outer instance method, what does `this` point to?

*Answer:* The lexical Outer receiver; a lambda does not create a new `this` inside its body.

**Question 13.** Inside a lambda created in an Inner instance method, what does `this` point to?

*Answer:* The Inner instance of the lexical context; `Outer.this` is still the enclosing Outer instance.

**Question 14.** How does `Outer.this.method()` differ from `this.method()`?

*Answer:* The first invokes on the enclosing Outer receiver; the second invokes on the current receiver.

**Question 15.** If an Inner field and an Outer field have the same name, does modifying `this.count++` make Outer.count increase?

*Answer:* No, if these are two separate instance fields. You must use `Outer.this.count++` to modify Outer.

**Question 16.** Can a local class declared inside an Outer instance method use `Outer.this`?

*Answer:* Yes, within a lexical context that has a valid enclosing Outer instance.

**Question 17.** Does a local class declared inside a static method of Outer automatically have an Outer instance?

*Answer:* No. An existing Outer variable does not automatically turn it into an enclosing instance; use an explicit reference.

**Question 18.** If two Outer objects are equal by value, can `Outer.this == other` be false?

*Answer:* Yes. `==` checks identity; value equality does not make two objects a single instance.

**Question 19.** Is `Outer.this` suitable for calling a static method?

*Answer:* For static methods, you should call them via the class name `Outer.staticMethod()`; no enclosing instance is needed.

**Question 20.** What design impact does an Inner instance holding a long-lived link to Outer have?

*Answer:* It can increase coupling and extend Outer's lifetime while Inner is kept alive; consider a static nested helper/explicit dependencies if an implicit owner is not needed.

---

**Final takeaway:** When a name appears at multiple levels, do not guess which variable the compiler is selecting. **`name`** picks the closest declaration by scope, **`this.name`** uses the current receiver, and **`Outer.this.name`** uses the **exact enclosing Outer instance** in a valid inner class context. With multiple levels, `Middle.this` and `Outer.this` distinguish the owners; with an anonymous class, `this` points to the anonymous object; with a lambda, `this` follows the lexical context. **Static nested classes and static methods do not automatically have an Outer instance**, so do not use `Outer.this` to obtain an arbitrary owner. Writing the receiver explicitly when shadowing occurs avoids updating the wrong state, makes code easier to read, and tests the right behavior.
