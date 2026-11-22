# `this` Is a Reference to the Current Object in Java

In Java, the **`this`** keyword is an expression that references the **current object** in an appropriate **instance** context. When an instance method is running on an object, `this` represents the very object receiving that call; when a constructor is initializing an object, `this` represents the object being constructed, but must comply with the restrictions of the initialization phase.

Understanding `this` properly helps you read object-oriented code: **which object is being operated on**, when `name` is a local variable or an object field, why `this` can be returned to chain method calls, and why passing `this` to external code can unintentionally expose state.

This lesson is for **Java 17+** and focuses on `this` as an **object reference**. The `this(...)` syntax for calling another constructor in the same class is also distinguished to avoid confusion.

## 1. Which object is the current object?

Consider the class:

~~~java
class Counter {
    private int value;

    void increment() {
        this.value++;
    }

    int current() {
        return this.value;
    }
}
~~~

This is a **class declaration snippet**, without a `main` to run on its own.

Suppose the program creates two objects:

~~~java
Counter first = new Counter();
Counter second = new Counter();

first.increment();
first.increment();
second.increment();
~~~

In the `first.increment()` call, `this` inside `increment()` points to **the object referenced by `first`**. In `second.increment()`, it is the same code, yet `this` points to **the object referenced by `second`**.

The results of calling `first.current()` and `second.current()` are `2` and `1`, respectively. The variable names `first` and `second` are at the call site, not inside the `increment()` method; the method uses `this` to represent the instance currently being processed.

Conceptual diagram:

~~~text
Variable first  ─────► Counter object A { value = 2 }
                         this in first.increment()

Variable second ─────► Counter object B { value = 1 }
                         this in second.increment()
~~~

The diagram only illustrates **reference relationships**, not physical memory addresses or how the JVM is required to lay out objects.

**Key takeaway:** `this` does not mean “the most recently created object”, “the object called on the nearest line of code”, or “the name of the class”. It is an expression that references the **current instance according to the execution context**.

## 2. What type does `this` have, and what value does it hold?

Inside an instance method of class `Person`, the `this` expression has the appropriate type corresponding to the class where the code is declared, and its value is a reference to **the exact instance receiving the call**.

~~~java
class Person {
    boolean sameInstance(Person other) {
        return this == other;
    }
}
~~~

The `sameInstance` method checks whether `other` and `this` point to **the same object**. `==` on two object references compares **identity**, and does not automatically compare the data inside the objects.

Example:

~~~java
Person a = new Person();
Person alias = a;
Person b = new Person();

System.out.println(a.sameInstance(alias)); // true
System.out.println(a.sameInstance(b));     // false
~~~

This is a **fragment inside a method**. `alias` and `a` both reference the same object; `b` is a different, new object. Different variable names do not force references to point to different objects; conversely, two different objects can have equal state without sharing the same identity.

### 2.1. `this` is not a variable name declared by the programmer

You do not need to, and cannot, declare a parameter named `this` and then reassign it yourself like a regular variable. Java determines the meaning of `this` according to the class/instance context; it is a special keyword/expression.

Mistake to avoid:

~~~java
class Example {
    void change() {
        // this = new Example(); // Invalid: cannot reassign 'this'
    }
}
~~~

You can **modify the fields of the object** referenced by `this`, or return/pass that reference, but you cannot assign a new object to `this` to “replace the current object”.

### 2.2. `this` can point to a subclass object at runtime

Suppose a method in a superclass is called on a subclass instance:

~~~java
class Animal {
    String typeName() {
        return this.getClass().getSimpleName();
    }
}

class Dog extends Animal {
}
~~~

If you call `new Dog().typeName()`, the method body of `Animal` runs, but `this` is still the **actual Dog object**. Therefore, `this.getClass().getSimpleName()` returns `"Dog"` in this example.

Just because a method is **declared in a superclass** does not mean `this` turns into a “superclass part” separated from the object. Java does not create a separate `Animal` object just to run this inherited method.

## 3. Using `this.field` to distinguish a field from a same-named parameter

This is the most common situation where you encounter `this` when learning classes and objects:

~~~java
class Student {
    private final String name;
    private int age;

    Student(String name, int age) {
        this.name = name;
        this.age = age;
    }

    void setAge(int age) {
        this.age = age;
    }
}
~~~

Analyzing the statement `this.age = age;`:

- **`this.age` on the left:** the `age` field of the current object.
- **`age` on the right:** the `age` parameter belonging to the currently running method/constructor.
- The `=` operator assigns the value from the parameter to the instance field.

If you mistakenly write:

~~~java
class BadStudent {
    private int age;

    BadStudent(int age) {
        age = age; // Only assigns the parameter to itself; does not modify the field
    }
}
~~~

this snippet **can compile**, but the `age` field keeps its default value `0`. Both occurrences of `age` resolve to the nearest parameter due to **shadowing**. Use `this.age = age;` to explicitly target the field to be assigned.

If the parameter does not share the same name as the field, `this` is sometimes not required:

~~~java
class Price {
    private long amount;

    Price(long initialAmount) {
        amount = initialAmount; // Valid: no local name 'amount' shadows the field
    }
}
~~~

However, many development teams still choose `this.amount` consistently to emphasize operating on instance state. This is a **style convention**, not a compiler requirement.

### 3.1. Lookup order for unqualified names

Inside an instance method, when you write `name` without `this.`, the compiler checks scope resolution rules and may choose a parameter or local variable instead of a field with the same name. For example:

~~~java
class Profile {
    private String label = "field";

    void show() {
        String label = "local";

        System.out.println(label);       // local
        System.out.println(this.label);  // field
    }
}
~~~

`label` and `this.label` are **two different expressions**. `this.label` selects the field of the current object; `label` in the nearest scope selects the local variable. Giving a local variable or parameter the same name as a field is not wrong, but you need to know exactly what each assignment and read refers to.

### 3.2. `this.field` does not bypass Java's access rules

`this` only specifies the **receiver**; it does not eliminate type checking, visibility, `final`, or other constraints. For example, if a field `id` has already been assigned under `final` rules, a method cannot arbitrarily write `this.id = ...`. If a method does not have permission to access a member, adding `this.` does not grant permission either.

## 4. Calling instance methods via `this`

Inside an instance method, you can use `this.method(...)` to call a method on the current object itself:

~~~java
class Temperature {
    private double celsius;

    Temperature(double celsius) {
        this.celsius = celsius;
    }

    double fahrenheit() {
        return this.celsius * 9.0 / 5.0 + 32.0;
    }

    String description() {
        return "F = " + this.fahrenheit();
    }
}
~~~

`this.fahrenheit()` calls the instance method on the same `Temperature` object that is executing `description()`. When there is no conflicting name and the call is valid, writing `fahrenheit()` usually produces the equivalent result.

Some important points:

- **`this.method()` is still an instance method call.** If that method can be overridden, Java applies dynamic dispatch as usual.
- `this.method()` **is not synonymous** with “forcing a call to the implementation declared in the current class itself”; for an overridable instance method, the implementation is selected according to the object's runtime type.
- An instance method can call multiple other methods of the same object via `this` to separate logic.
- Do not call an overridable method from a constructor if a subclass implementation could observe uninitialized subclass fields; this is an object lifecycle design issue.

## 5. Runnable program: `this`, fields, chaining, identity, and passing references

Create the file **`ThisReferenceDemo.java`**:

~~~java
public class ThisReferenceDemo {
    static final class Person {
        private final String name;
        private int visits;

        Person(String name) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("Tên không hợp lệ");
            }
            this.name = name;
        }

        Person visit() {
            this.visits++;
            return this;
        }

        Person visitTwice() {
            this.visit();
            return this.visit();
        }

        String summary() {
            return this.name + ": " + this.visits;
        }

        boolean sameInstance(Person other) {
            return this == other;
        }

        void register(Registry registry) {
            registry.accept(this);
        }
    }

    static final class Registry {
        private Person last;

        void accept(Person person) {
            this.last = person;
        }

        Person last() {
            return this.last;
        }
    }

    public static void main(String[] args) {
        Person lan = new Person("Lan");
        Person mai = new Person("Mai");

        lan.visit().visit();
        lan.visitTwice();

        System.out.println("Lan = " + lan.summary());
        System.out.println("Mai = " + mai.summary());

        Person alias = lan;
        System.out.println("Same alias = " + lan.sameInstance(alias));
        System.out.println("Same Mai = " + lan.sameInstance(mai));

        Registry registry = new Registry();
        lan.register(registry);
        System.out.println("Registered Lan = "
                + (registry.last() == lan));

        alias.visit();
        System.out.println("After alias = " + lan.summary());
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac -encoding UTF-8 ThisReferenceDemo.java
java ThisReferenceDemo
~~~

**Exact stdout:**

~~~text
Lan = Lan: 4
Mai = Mai: 0
Same alias = true
Same Mai = false
Registered Lan = true
After alias = Lan: 5
~~~

Explanation:

1. The `Person("Lan")` constructor validates the name and then assigns `this.name = name`. `this` inside the constructor points to the `Person` object **currently being created**.
2. `lan.visit().visit()` calls `visit()` twice on **the same object**: the method increments `this.visits` and then executes `return this;`. Because the return value is `lan` itself, the second call continues on that same object.
3. `lan.visitTwice()` calls `this.visit()` twice, so `lan` has four visits. `mai` remains at 0 because `mai` references a different object.
4. `alias = lan` copies the reference value; `alias` and `lan` both point to the same instance. `sameInstance(alias)` returns `true`, while `sameInstance(mai)` returns `false`.
5. `register(registry)` passes `this` to `Registry.accept(...)`. The registry holds a reference to the `lan` object itself; therefore, `registry.last() == lan` is `true`.
6. `alias.visit()` increments the visit count on the shared object; `lan.summary()` then sees 5.

**Note:** The `register` method is called **after the constructor completes**, so the example does not attempt to publish an object that has not finished initializing. Passing `this` externally can be valid, but object ownership, lifecycle, and concurrency must be considered.

## 6. What is the purpose of returning `this`?

An instance method can return **the current receiver itself** if the return type is compatible. `return this;` does not allocate a new object, making it possible to build a fluent API:

~~~java
class TextBuilder {
    private final StringBuilder value = new StringBuilder();

    TextBuilder append(String part) {
        value.append(part);
        return this;
    }

    String build() {
        return value.toString();
    }
}
~~~

`new TextBuilder().append("Java").append(" 17").build()` produces `"Java 17"`; the two `append` calls mutate the same builder. Do not default every method to returning `this`: queries need to return data, and operations that do not need chaining can use `void`. Distinguish this from immutable `withX(...)` methods that typically return a **new object**, and learn about return type conditions under inheritance in the lesson **Passing this as an argument and returning this**.

## 7. Passing `this` as an argument

Inside an instance method, `this` can serve as an **argument expression** when the parameter type can accept a reference to the current object:

~~~java
class Node {
    void visit(Inspector inspector) {
        inspector.inspect(this);
    }
}

class Inspector {
    void inspect(Node node) {
        System.out.println(node != null);
    }
}
~~~

Java copies the **reference value** into the `node` parameter variable; it neither clones the `Node` nor allows the inspector to reassign the receiver variable at the call site. When a collaborator holds the reference, it can observe or modify state if the API permits.

**Lifecycle warning:** passing or registering `this` from a constructor to a registry/listener/task can cause the object to be used **before initialization is complete**. For example, a callback could read a field that is still null even though the constructor intends to assign it right after. Publish only when state is ready; the lesson **Risks of letting this escape when initialization is incomplete** analyzes synchronous callbacks, threads, and safe publication.

## 8. `this` and `this(...)` are two different syntactic forms

This is a very easy point to confuse:

| Syntax | Meaning |
| --- | --- |
| `this` | Expression referencing the current object |
| `this.field` | Accessing a field of the current object |
| `this.method()` | Calling an instance method on the current object |
| `return this;` | Returning a reference to the current object itself |
| `otherMethod(this);` | Passing the current object reference as an argument |
| `this(...)` in a constructor | **Explicit constructor invocation**: delegating to another constructor of the same class |

Example of **`this(...)`**:

~~~java
class Rectangle {
    private final int width;
    private final int height;

    Rectangle() {
        this(1, 1);
    }

    Rectangle(int width, int height) {
        if (width <= 0 || height <= 0) {
            throw new IllegalArgumentException("Cạnh phải dương");
        }
        this.width = width;
        this.height = height;
    }
}
~~~

The no-argument constructor calls `this(1, 1)` to delegate to the two-argument constructor. Meanwhile, `this.width = width` accesses a field via the current object; the two syntaxes use the same keyword, but **do not have the same role**.

For Java 17:

- `this(...)` is only used as an explicit constructor invocation inside a constructor, following the mandatory rule that it **is the first statement** of the constructor body.
- A constructor can only begin with either `this(...)` **or** `super(...)` as its respective explicit invocation; you cannot use both.
- `this(...)` calls must not form a recursive constructor invocation cycle.
- Arguments to an explicit constructor invocation are subject to the restriction that they **must not use `this` or instance members in a way that violates context rules before the superclass/instance is initialized**. For example, you cannot use `this.width` as an argument to call `this(...)` in a Java 17 constructor.

Do not interpret `this(...)` as “calling a method named `this`” or “calling the same method again”: it is dedicated syntax for **constructor chaining**.

## 9. `this` and `super` are different

`this` denotes **the current object**. `super` is syntax used when you need to access a superclass implementation/member according to language rules; it is not a reference to an independent superclass object.

~~~java
class Base {
    String label() {
        return "Base";
    }

    String describe() {
        return this.label();
    }
}

class Derived extends Base {
    @Override
    String label() {
        return "Derived";
    }

    String both() {
        return this.label() + "/" + super.label();
    }
}
~~~

In the example:

- `new Derived().both()` returns `"Derived/Base"`.
- `this.label()` uses dynamic dispatch, so it calls `Derived.label()`.
- `super.label()` requests the implementation from superclass `Base` in that context.
- `new Derived().describe()` returns `"Derived"`, even though the body of `describe()` is declared in `Base`. `this` inside the inherited instance method still points to the `Derived` object receiving the call.

That explains why you should not think “`this` always points to the exact class containing the method's source code”. **The reference value is the runtime object**, while the compiler's checking of names/members depends on the declared type and context.

When a subclass constructor calls `super(...)`, that is a **constructor invocation** to the superclass to initialize **the same object** according to inheritance rules, not creating a separate superclass object and attaching it to the subclass.

## 10. When can `this` not be used?

`this` is only valid when there is a **current instance in the appropriate lexical context**. Static methods and static initializers have no receiver object:

~~~java
class Device {
    private int id;

    void show() {
        System.out.println(this.id); // Valid
    }

    static void report(Device device) {
        // System.out.println(this.id); // Invalid: static context
        System.out.println(device.id); // Valid: explicit receiver
    }
}
~~~

An instance method can read static members by class name, but that does not turn a static method into a place where `this` exists. Conversely, **an instance method of a static nested class** has the `this` of the **nested object**, even though it has no implicit `Outer.this`. In a lambda, `this` inherits the enclosing context; in an anonymous class, `this` denotes the anonymous instance itself. The lesson **Restrictions on using this in a static context** examines these boundaries in depth; `this(...)` is syntax for calling another constructor and **is not** a receiver expression.

## 11. `Outer.this` in inner classes

A **non-static inner class** has its own instance and is associated with an enclosing instance of the outer class. Therefore, inside an instance method of an inner class, `this` is the inner object; `Outer.this` is the corresponding **outer object**:

~~~java
class Outer {
    private String label = "outer";

    class Inner {
        private String label = "inner";

        String both() {
            return this.label + "/" + Outer.this.label;
        }
    }
}
~~~

If `Outer outer = new Outer();` and `Outer.Inner inner = outer.new Inner();`, `inner.both()` returns `"inner/outer"`. `Outer.this` does not create a new object and does not exist in a static nested class that lacks an enclosing instance. The lesson **Accessing the enclosing object with Outer.this** delves into multiple nesting levels, shadowing, lambdas/anonymous classes, and object lifecycle.

## 12. `this` in lambdas and anonymous classes: easy to confuse

Two forms of code can both execute via the `Runnable` interface yet have different `this` semantics:

~~~java
class JobOwner {
    String name = "owner";

    Runnable lambdaJob() {
        return () -> System.out.println(this.name);
    }

    Runnable anonymousJob() {
        return new Runnable() {
            String name = "anonymous";

            @Override
            public void run() {
                System.out.println(this.name);
            }
        };
    }
}
~~~

This is a declaration snippet. `lambdaJob()` uses a **lambda**, so `this` in the lambda body has the same meaning as `this` in the context of the `lambdaJob()` instance method: it points to `JobOwner`. `anonymousJob()` creates an object of an **anonymous class**; `this` inside `run()` is that anonymous object.

You should not assume that a lambda is “100% equivalent to an anonymous class” in every case: the difference in lexical scope and `this` is a very concrete example.

## 13. Method calls and virtual dispatch: `this.method()` does not lock the implementation

See the example:

~~~java
class Parent {
    void invoke() {
        this.describe();
    }

    void describe() {
        System.out.println("Parent");
    }
}

class Child extends Parent {
    @Override
    void describe() {
        System.out.println("Child");
    }
}
~~~

If executed:

~~~java
Parent object = new Child();
object.invoke();
~~~

Stdout is:

~~~text
Child
~~~

This part is a **fragment inside a method**, which can be combined with the two classes above. `Parent.invoke()` calls `this.describe()`; `this` is the actual `Child` object, so dynamic dispatch selects `Child.describe()`. This is a normal characteristic of instance method overriding.

**Consequence for constructor design:** a superclass constructor calling `this.overridableMethod()` can transfer control to the subclass's override **before the subclass's field initializers and constructor body have finished**. You should not call overridable methods in a constructor if they might require already-initialized subclass state.

## 14. Comparing `this == other` and `this.equals(other)`

These two checks are not necessarily the same.

### 14.1. Identity with `==`

~~~java
class Node {
    boolean sameObject(Node other) {
        return this == other;
    }
}
~~~

The result is `true` when both references point to the exact same object, even if they are two variables with different names. `null` is a valid reference value for the `other` parameter; `this == null` cannot be `true` inside an instance method normally invoked on an object.

### 14.2. Content-based equality with `equals`

~~~java
class Tag {
    private final String code;

    Tag(String code) {
        this.code = java.util.Objects.requireNonNull(code);
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true; // Same object: safe optimization
        }
        if (!(other instanceof Tag tag)) {
            return false;
        }
        return this.code.equals(tag.code);
    }

    @Override
    public int hashCode() {
        return code.hashCode();
    }
}
~~~

This is a declaration snippet using **pattern matching for instanceof**, available in Java 17. `equals` uses `this == other` as a fast check for the same object, then compares the `code` content when `other` is a `Tag`.

With two different `new Tag("A")` objects, `==` on the two references is `false`, while `equals` can be `true` because the codes are equal. When overriding `equals`, you must also override `hashCode` appropriately so as not to break the contract of hash-based collections.

**Do not use `this.equals(other)` unconditionally without understanding the contract.** Inside `equals`, calling `this.equals(other)` recursively does not replace comparison logic and can lead to infinite recursion.

## 15. Common misconceptions about `this`

| Misconception | Reality |
| --- | --- |
| “`this` is the class name.” | `this` is a reference to the current object, not the class name |
| “`this` points to the most recently created object.” | It points to the current receiver of the instance context |
| “If there are two reference variables, there are two `this` for different objects.” | Two variables can alias the same object; when called on the same object, `this` has the same identity |
| “`this.age = age` and `age = age` are always the same.” | Not if a parameter/local `age` shadows the field |
| “In an instance method, writing `this.` is always mandatory.” | It can usually be omitted when the name is not shadowed; the compiler uses an implicit receiver |
| “`return this` copies the object.” | No; it returns the same reference |
| “You can reassign `this = new X()`.” | No; `this` is not an assignable variable |
| “`this` exists inside a static method.” | There is no implicit current instance in a static context |
| “`super` is a separate object.” | No; it is syntax for selecting superclass member behavior on the same object |
| “`this(...)` and `this.method()` are both method calls.” | `this(...)` is an explicit constructor invocation; `this.method()` is an instance method call |
| “`this` inside a lambda is always the lambda object.” | No; `this` inside a lambda retains its lexical enclosing meaning |
| “`this` inside an anonymous class is always the outer object.” | No; `this` is the anonymous class instance; use `Outer.this` if there is an appropriate enclosing instance |
| “`this.field` protects against races across multiple threads.” | No; `this` does not provide synchronization or atomicity |
| “Passing `this` out of a constructor is always safe.” | It can lead to this escape before the object is complete |

### 15.1. `this` does not make an operation thread-safe

~~~java
class Counter {
    private int count;

    void increment() {
        this.count++; // Still not atomic across multiple threads
    }
}
~~~

In an environment where two threads call the same instance, `this.count++` can suffer lost updates just like `count++` without proper synchronization. `this` specifies the receiver; it is **not** a lock, memory barrier, `volatile`, or atomic variable.

Similarly, if two reference variables `a` and `b` alias the same object, calling `a.increment()` and `b.increment()` on two threads still contends over **the same field** of the object.

## 16. Self-check exercises

**Question 1.** In the constructor `User(String name)` with a field `String name`, why can `name = name;` be a bug?

**Answer:** The `name` parameter shadows the field of the same name; both sides of the assignment resolve to the parameter. Use `this.name = name;` to assign the parameter's value to the field.

**Question 2.** If `A a1 = new A(); A a2 = a1;`, when calling `a1.method()` and `a2.method()`, does `this` point to two different objects?

**Answer:** No. Both variables point to the same object; `this` in each instance method call represents that object.

**Question 3.** Does the method `A returnSelf() { return this; }` create a new A?

**Answer:** No. It returns a reference to the current object. Only a call to `new A()` creates an object through the normal instantiation path.

**Question 4.** Can you write `System.out.println(this);` inside a `static void main(String[] args)`?

**Answer:** No. `main` is a static method, so there is no current instance of the class. You can create an object and then print its reference or call its instance method.

**Question 5.** Does `this(10)` inside a constructor call a method named `this`?

**Answer:** No. It is a call to another constructor in the same class. In Java 17, the explicit invocation must be the first statement in the constructor.

**Question 6.** In `Outer.Inner` (a non-static inner class), how are `this` and `Outer.this` distinguished?

**Answer:** `this` is the current inner object; `Outer.this` is the corresponding enclosing outer object.

**Question 7.** Does `this` inside a lambda created by an instance method point to a separate lambda object?

**Answer:** No. It retains the meaning of `this` in the lexical enclosing context. In a normal instance method, that is the enclosing instance.

**Question 8.** Why should you avoid writing `registry.add(this)` at the very beginning of a constructor when the object has required fields that are not yet initialized?

**Answer:** Because other code could observe an incomplete object. This can violate invariants and safe publication principles. You should finish constructing the object before registering it.

**Question 9.** A superclass method calls `this.describe()` on a subclass object, and the subclass overrides `describe()`. Which implementation is chosen?

**Answer:** Dynamic dispatch for instance methods normally selects the override from the subclass's runtime class. `this` does not force calling the superclass implementation; `super.describe()` is the syntax with a different purpose.

**Question 10.** Do `this == other` and `this.equals(other)` always yield the same result?

**Answer:** No. `==` compares identity, whereas `equals` can be overridden by a class to compare values/content.

## 17. Checklist for applying `this` when writing classes

1. **Identify the instance:** which object is this method/constructor operating on?
2. **Check for shadowing:** does a field share a name with a parameter/local variable? Use `this.field` when you need to target the field.
3. **Understand internal calls:** `this.method()` is a method call on the current object, which may undergo dynamic dispatch.
4. **Understand returning `this`:** `return this;` returns the current object; it does not copy the object.
5. **When passing it out:** can the collaborator store, modify, or share that reference?
6. **Inside constructors:** avoid publishing `this` before the object is finished building, and avoid calling risky overridable methods.
7. **Distinguish syntaxes:** `this` is a reference expression; `this(...)` is constructor delegation.
8. **In a static context:** there is no `this`; a receiver instance or parameter is required.
9. **In inner classes/lambdas/anonymous classes:** accurately determine the lexical/running receiver, and use `Outer.this` when appropriate.
10. **Do not assume thread-safety:** `this` does not protect fields from races; if multiple threads share an object, a synchronization strategy is needed.

**Quick takeaway:** `this` answers the question **“which object is receiving the current instance call?”**. When you write `this.name`, `this.method()`, `return this;`, or pass `this` as an argument, you are still working with **the same object**, only performing a different operation on it. Understanding this accurately is the foundation for mastering constructors, encapsulation, chaining, inheritance, and nested classes in Java.
