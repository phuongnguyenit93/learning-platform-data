# Using `this` to Distinguish Fields and Parameters with the Same Name in Java

In Java, **`this`** is an expression that refers to the **current object** in an appropriate instance context. One of the most common uses is writing **`this.field`** to distinguish an **object's field** from a **parameter or local variable with the same name**. This allows constructors and methods to assign state properly to the object instead of accidentally assigning a variable to itself.

This lesson belongs to Java Core — *class-object*, focusing on name resolution and setting data on the **right instance**. The standalone examples require **Java 17 or higher**.

## 1. The problem: one name, two different variables

Consider a class that has a field named `name` and a constructor that also takes a parameter named `name`:

~~~java
class Student {
    private String name;

    Student(String name) {
        name = name;
    }
}
~~~

This code **compiles**, but **does not assign a value to the `name` field**. Inside the constructor body, the `name` parameter is in scope and **shadows** the field of the same name. Both occurrences of `name` in `name = name;` are resolved as the **parameter**. In effect, the statement assigns the parameter to itself; the object's field retains its default value `null`.

The correct way to write it:

~~~java
class Student {
    private String name;

    Student(String name) {
        this.name = name;
    }
}
~~~

In `this.name = name;`:

- **`this`** is the reference to the `Student` object being initialized.
- **`this.name`** is **that object's `name` field**.
- **`name` on the right-hand side** is the **constructor parameter** receiving the value from the caller's argument.
- The `=` operator assigns **the parameter's value** to **the field**.

This is the difference between *assigning state to the object* and *assigning to a local variable of the call*.

## 2. Fields, parameters, and reference variables are three different concepts

Example call:

~~~java
Student an = new Student("An");
~~~

At runtime, this can be visualized as:

~~~text
Reference variable an
        |
        v
    Student object
  +------------------+
  | field name: "An" |
  +------------------+

Call Student("An")
  parameter name = "An"  (only within the constructor call)
            |
            +--- this.name = name
                      |
                      v
                  object's field
~~~

In this example, **`an`** is the reference variable at the call site, the **`name` parameter** is the constructor call's own variable, and **`this.name`** is the field belonging to the object that `an` references after successful initialization.

Parameters are used while the method/constructor is running. Instance fields continue to be part of the object's state after the call completes. Two different objects can have the same field named `name` yet **hold two separate values**.

| Syntax | Meaning when a parameter has the same name |
| --- | --- |
| `name` | The nearest parameter or local variable named `name` |
| `this.name` | The instance field `name` of the current object |
| `other.name` | The `name` field of the object referenced by `other`, if access rules permit |
| `Student student` | A reference variable holding a reference to the object, **not** the `name` field |
| `this` | The reference to the current object itself, **not** a “call constructor” keyword when standing alone |

**Note:** when there is no closer name shadowing it, Java allows using `name` instead of `this.name` in an instance method. `this` is especially necessary when names collide or when you want to make it clear that you are accessing the object's state.

## 3. Complete example: the `name = name` bug and how to fix it

Create the file **`ThisShadowingDemo.java`**:

~~~java
class BrokenProfile {
    private String name;

    BrokenProfile(String name) {
        name = name; // Logic error: the parameter assigns to itself.
    }

    String name() {
        return name;
    }
}

class StudentProfile {
    private String name;
    private int level;

    StudentProfile(String name, int level) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên không hợp lệ");
        }
        if (level < 1) {
            throw new IllegalArgumentException("Cấp độ phải dương");
        }
        this.name = name;
        this.level = level;
    }

    void rename(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên không hợp lệ");
        }
        this.name = name;
    }

    void promoteTo(int level) {
        if (level < this.level) {
            throw new IllegalArgumentException("Không được giảm cấp");
        }
        this.level = level;
    }

    String summary() {
        return name + " (level " + level + ")";
    }
}

public class ThisShadowingDemo {
    public static void main(String[] args) {
        BrokenProfile broken = new BrokenProfile("An");
        System.out.println("Broken: " + broken.name());

        StudentProfile an = new StudentProfile("An", 1);
        StudentProfile binh = new StudentProfile("Binh", 2);

        an.rename("Anh");
        an.promoteTo(3);

        System.out.println(an.summary());
        System.out.println(binh.summary());

        try {
            an.promoteTo(0);
        } catch (IllegalArgumentException ex) {
            System.out.println("Từ chối: " + ex.getMessage());
        }
        System.out.println(an.summary());
    }
}
~~~

In the directory containing the file, run:

~~~bash
javac -encoding UTF-8 ThisShadowingDemo.java
java ThisShadowingDemo
~~~

**Exact stdout:**

~~~text
Broken: null
Anh (level 3)
Binh (level 2)
Từ chối: Không được giảm cấp
Anh (level 3)
~~~

### Step-by-step explanation of the output

1. `new BrokenProfile("An")` passes `"An"` into the `name` parameter. The statement `name = name;` only reassigns the parameter; the `BrokenProfile.name` field is not set and defaults to `null`. When concatenated into a string for printing, Java represents this value as the text `null`.
2. `new StudentProfile("An", 1)` validates and assigns `this.name = name` and `this.level = level` properly to the first instance.
3. `new StudentProfile("Binh", 2)` creates a **second instance**, with two separate fields not shared with the An instance.
4. `an.rename("Anh")` assigns the new `name` parameter to **the field of the An instance**. This does not change Binh's name.
5. `an.promoteTo(3)` compares the **parameter** `level = 3` with the **current field** `this.level = 1`, then updates the field to 3.
6. `an.promoteTo(0)` throws an exception before the assignment, so the `this.level` field remains 3.

In this example, `this` both resolves the naming collision and makes the intent of the condition `level < this.level` clear to read: on the left is the **level to be set**, and on the right is the **existing level**.

## 4. Exact analysis of the expression `this.field = parameter`

A common pattern in a constructor or setter:

~~~java
class Rectangle {
    private final int width;
    private final int height;

    Rectangle(int width, int height) {
        this.width = width;
        this.height = height;
    }
}
~~~

This is an **illustrative class definition**, without `main`. For the line:

~~~java
this.width = width;
~~~

read it from left to right:

1. `this`: the `Rectangle` object being initialized.
2. The `.` symbol: accesses a member of the object.
3. `width` on the left: the `width` field of the object.
4. The `=` sign: assignment.
5. `width` on the right: the `int` constructor parameter passed in at `new Rectangle(...)`.

You should not say that `this` changes **the parameter's value**; it clarifies **the target of the assignment**. The type of the field and the value of the right-hand-side expression must still be compatible according to Java's assignment rules.

### Why is naming parameters the same as fields so common?

It establishes a consistent convention between the API and the state:

~~~java
Book(String title, String author) {
    this.title = title;
    this.author = author;
}
~~~

Just by looking at the header and the assignments, a reader immediately understands which argument initializes which field. Instead of renaming the parameter to `newTitle` or `inputTitle` to avoid a name collision, many Java projects choose to keep the natural name and use `this.title` on the field side.

**This is a design convention, not a mandatory syntax rule.** Parameter names and field names do not have to be identical.

## 5. Local variables can also shadow fields

It is not just parameters: a **local variable** declared within a scope can also shadow a field of the same name.

Create the complete file **`ThisLocalVariableDemo.java`**:

~~~java
class Counter {
    private int value;

    Counter(int value) {
        this.value = value;
    }

    void inspect() {
        int value = 100;
        System.out.println("local=" + value);
        System.out.println("field=" + this.value);
    }

    void add(int amount) {
        this.value = Math.addExact(this.value, amount);
    }

    int value() {
        return this.value;
    }
}

public class ThisLocalVariableDemo {
    public static void main(String[] args) {
        Counter first = new Counter(10);
        Counter second = new Counter(20);

        first.inspect();
        first.add(5);
        System.out.println("first=" + first.value());
        System.out.println("second=" + second.value());
    }
}
~~~

Run:

~~~bash
javac ThisLocalVariableDemo.java
java ThisLocalVariableDemo
~~~

Stdout:

~~~text
local=100
field=10
first=15
second=20
~~~

In `inspect()`, the local variable `int value = 100;` shadows the object's `value` field. Therefore:

- `System.out.println(value)` reads the **local variable** 100.
- `System.out.println(this.value)` reads the **field** of `first`, which is initially 10.
- After `first.add(5)`, only `first`'s field becomes 15; `second`'s field remains 20.

In `add(int amount)`, there is no parameter named `value`, so `this.value` is not required for name resolution; you could write `value = Math.addExact(value, amount)`. Writing `this.value` is still valid and helps make instance state explicit.

**Scope note:** a local variable cannot be declared with the same name as a parameter that is in scope within the same method in a way that causes a duplicate declaration; for example, `void f(int x) { int x = 1; }` is a compile error. That differs from an instance field sharing a name with a parameter, which **is allowed** and is the situation that `this` resolves.

## 6. When `this` is not used, which name does Java resolve?

Suppose we have:

~~~java
class Example {
    private int points;

    Example(int points) {
        this.points = points;
    }

    int points() {
        return points;
    }

    void setPoints(int points) {
        this.points = points;
    }
}
~~~

This is an illustrative class. The name contexts differ significantly:

| Location | Writing `points` means | Writing `this.points` means |
| --- | --- | --- |
| Inside constructor `Example(int points)` | The constructor parameter | The field of the instance being created |
| Inside `points()` with no matching local/parameter name | The field of the current instance | That same field |
| Inside `setPoints(int points)` | The method parameter | The field of the instance receiving the call |
| Inside a method containing `int points = 5;` | The local variable | The field of the instance |

Java has rules for **scope** and **shadowing**. A valid parameter or local variable can shadow the field name visible via a simple name. Adding `this.` turns the access into a **member selection expression** on the current object.

Do not oversimplify this as “Java always prioritizes parameters over everything else” for all kinds of names and scopes. Nested types, inheritance, static fields, and other identifier forms each have their own rules. For this lesson, the relationship to keep firmly in mind is that **a parameter or local variable with the same name shadows an instance field** when a bare name is used.

## 7. `this` in constructors and instance methods

In a constructor, `this` refers to the object **being initialized**:

~~~java
StudentProfile(String name, int level) {
    this.name = name;
    this.level = level;
}
~~~

In an instance method, `this` refers to the object **receiving the current call**:

~~~java
void rename(String name) {
    this.name = name;
}
~~~

Both variables `an` and `binh` can call `rename`, but each call has its own **receiver object**:

~~~java
an.rename("Anh");      // this points to the object referenced by an
binh.rename("Bình");   // this points to the object referenced by binh
~~~

That is why a single method defined in a class can operate on **multiple independent copies of state**.

You can write `this.name` multiple times across the constructors/methods of a class, but `this` **is not a fixed global variable**: its reference value depends on the object being used in each call.

## 8. `this` is not required on every field access

When **there is no closer variable with the same name**, the following code has the same meaning when reading the field:

~~~java
int getLevel() {
    return level;
}

int getLevelExplicitly() {
    return this.level;
}
~~~

Both are **illustrative method snippets** in a class with an instance field `level`. If a parameter or local variable named `level` appears in the method body, the bare-name form can change meaning; `this.level` still explicitly refers to the object's field.

Two common styles:

- Write `this.` only **when there is shadowing** or when it is needed to clarify the receiver.
- Consistently use `this.` for **every instance field** to make it easier to distinguish fields from local variables.

Java accepts both. A project should choose a readable and consistent convention rather than concluding that one style is mandatory for every application.

### Does renaming the parameter solve the problem?

Yes:

~~~java
void rename(String newName) {
    this.name = newName;
}
~~~

If there is no other local `name`, writing `name = newName;` can also assign to the right field. However, the `this.name = name` convention often makes it easier to match field names with parameter names, especially in constructors with many fields.

You should not misuse `this` as a variable name: `this` is a **special keyword**, not a valid identifier for declaring your own variable.

## 9. `this` and `static`: there is no receiver instance

A `static` method belongs to the class context and does not have a current object to use with `this`.

An **intentionally invalid** example:

~~~java
class Invalid {
    private int value;

    static void update(int value) {
        this.value = value; // Compile error: cannot use this in a static context.
    }
}
~~~

If the operation needs to update a field of an object, provide a specific object reference:

~~~java
class Valid {
    private int value;

    static void update(Valid target, int value) {
        if (target == null) {
            throw new IllegalArgumentException("target là null");
        }
        target.value = value;
    }

    void update(int value) {
        this.value = value;
    }
}
~~~

This is an **illustrative class definition**, without `main`. The two `update` methods have different signatures because one takes `(Valid, int)` and the other takes `(int)`. In the static method, `target.value` accesses the field of the passed-in object. In the instance method, `this.value` accesses the field of the receiver.

`static` fields should be accessed through the **class name** when appropriate; `this` is not the way to represent shared class state. For example, `Counter.total` is different from `this.value`.

## 10. `this.field` differs from `this(...)`

Two syntaxes that are easy to confuse:

| Syntax | Purpose | Example |
| --- | --- | --- |
| `this.field` | Selects a field of the current object | `this.name = name;` |
| `this.method(...)` | Calls an instance method on the current object | `this.rename("An");` |
| `this(...)` | Calls another constructor **in the same class** | `this(name, 0);` |
| `super(...)` | Calls a superclass constructor | `super(name);` |
| `super.field` | Selects a superclass field when access is permitted | `super.value` |

An example of a delegating constructor (illustrative, without `main`):

~~~java
class Product {
    private String name;
    private int quantity;

    Product(String name) {
        this(name, 0);
    }

    Product(String name, int quantity) {
        this.name = name;
        this.quantity = quantity;
    }
}
~~~

`new Product("Sách")` creates **one object**, invokes the one-parameter constructor, and delegates to the two-parameter constructor on the **same object**. The statement `this(name, 0)` does not assign the `name` field; it is the line `this.name = name` inside the two-parameter constructor that does so.

In **Java 17**, an explicit `this(...)` or `super(...)` call in a constructor must appear as the first statement in that constructor's body. Do not call `this(...)` recursively without end or write `this(...)` like a regular method call in the middle of `setName`.

## 11. `this` and shadowed fields in inheritance

In addition to a parameter shadowing a field, a subclass can also declare a field with the **same name** as a field in its superclass. In that case, `this.field` and `super.field` can differ, depending on which declaring class the expression sits in and the access rules.

Create the file **`ThisAndSuperDemo.java`**:

~~~java
class ParentBox {
    protected int size = 10;
}

class ChildBox extends ParentBox {
    private int size = 20;

    ChildBox(int size) {
        this.size = size;
    }

    void printSizes() {
        System.out.println("child=" + this.size);
        System.out.println("parent=" + super.size);
    }
}

public class ThisAndSuperDemo {
    public static void main(String[] args) {
        ChildBox box = new ChildBox(30);
        box.printSizes();
    }
}
~~~

~~~bash
javac ThisAndSuperDemo.java
java ThisAndSuperDemo
~~~

Stdout:

~~~text
child=30
parent=10
~~~

In `ChildBox(int size)`, the parameter `size` shadows the subclass's field name. `this.size = size;` sets the `ChildBox.size` field to 30. `ParentBox.size` had an initializer of 10 and still holds 10, so `super.size` reads 10.

**Do not intentionally shadow fields in inheritance without a clear reason**: it creates two physical/conceptual fields with the same name, which easily leads to confusion. This example is only meant to clearly distinguish `this` and `super`; in practical design, you should usually use non-conflicting field names.

## 12. Using `this` when a setter must validate the new value

If a getter or setter needs to operate on a field that shares the same name as a parameter, `this` helps clearly express the **old value** and the **requested value**.

~~~java
class InventoryItem {
    private int quantity;

    InventoryItem(int quantity) {
        setQuantity(quantity);
    }

    void setQuantity(int quantity) {
        if (quantity < 0) {
            throw new IllegalArgumentException("Số lượng không được âm");
        }
        this.quantity = quantity;
    }

    void increase(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Số cộng phải dương");
        }
        this.quantity = Math.addExact(this.quantity, quantity);
    }
}
~~~

This is an **illustrative class definition**, without `main`. In `setQuantity`, the condition checks the **new parameter** `quantity`, and then updates the `this.quantity` field. In `increase`, `this.quantity` on the right-hand side is the **current quantity**, while the `quantity` parameter is the **amount to add**.

Note that calling an overridable instance method from a constructor can be dangerous if that method is not controlled, because the object has not finished initializing yet. In the `InventoryItem` example, the class has no subclasses or overrides; in inheritance-oriented APIs, you should be cautious with this approach and prefer initializing data safely.

### Why is a correct assignment not enough to make a class correct?

Even when `this.quantity = quantity;` is written correctly, a constructor must still ensure a **valid value** according to the class's invariant. Validation should not be skipped just because the name-collision bug has been fixed. Two distinct errors must be kept separate:

1. **Wrong receiver or wrong assignment target:** `quantity = quantity;`.
2. **Invalid business data:** `this.quantity = -10;` when the class requires a non-negative quantity.

A good class needs to address both.

## 13. A few details to remember about the `this` expression

- In an instance method or constructor of a regular class, `this` refers to the current object. It **does not create a new object** and is not a synonym for the class name.
- You can pass `this` as an argument to another method or return `this` from an instance method when the type is compatible. However, **you should not expose `this` from a constructor** to other objects/threads before initialization is complete.
- Inside a **lambda**, `this` (when valid) still refers to the instance of the enclosing context, not a new “lambda object”.
- Inside an **anonymous inner class**, `this` can refer to the instance of the anonymous class itself; when you need to refer to the enclosing class's instance, Java provides the `OuterClass.this` syntax in a valid context.
- You cannot write `this` inside a **static method** or static initializer because there is no current receiver object there.

These details explain why `this` has **context-dependent** semantics. However, when it comes to distinguishing a field from a parameter in a regular class, the essential pattern remains **`this.field = parameter;`**.

## 14. Common mistakes and how to spot them

| Mistake | Symptom | How to fix |
| --- | --- | --- |
| `name = name;` when field and parameter share a name | Parameter assigns to itself; field keeps its old/default value | Write `this.name = name;` |
| `this.name = this.name;` | Field assigns to itself; parameter is ignored | Use the parameter's `name` on the right-hand side |
| Writing `age = age;` inside a setter | The object is not updated | `this.age = age;` |
| In a method with a local `int value`, using `value` thinking it is the field | Prints/reads the local variable by mistake | Use `this.value` when the field is needed |
| Using `this.field` in `static` | Compile error: no `this` available | Use a specific object reference or make it an instance method |
| Confusing `this(field)` with `this.field` | Completely different syntax/purpose | `this(...)` is only used for constructor delegation |
| Using `this.field` to refer to a superclass field with the same name | May instead access the shadowing field in the subclass | Use `super.field` when needed and access is permitted |
| Assuming `this.field = parameter` validates data automatically | Stores invalid values in the object as well | Validate invariants before assigning |
| Assuming `this` in two instances always points to the same object | Two objects are mistaken for one | The receiver changes according to the object receiving the call |
| Letting `this` escape from a constructor before completion | Other code may observe incomplete state | Do not publish the receiver prematurely |

In an IDE, warnings like “assignment to itself” can help detect `name = name;`. However, you should not rely solely on warnings: the Java compiler **does not necessarily reject** this self-assignment statement. Test the state after constructors and setters.

## 15. Checklist for reading and reviewing code

When you see a constructor or setter with matching field and parameter names:

1. List the **fields** that need to be set, such as `name`, `age`, `level`.
2. Identify the **parameters** that share the same name and their effective scope.
3. In each assignment, check whether the left-hand side is actually **`this.field`**.
4. Check that the right-hand side is the requested input data, not the field itself.
5. Check **preconditions** before writing to the field.
6. If you need to compare the new and old values, write the **parameter** and **`this.field`** explicitly.
7. Test at least one object with non-default values, and if possible, **two objects with different data**.
8. If it is a static method, identify the object reference that the method actually needs to operate on.
9. If there is inheritance/field hiding, distinguish between `this.field`, `super.field`, and the field of the class actually declaring the method.
10. When using constructor chaining, verify that `this(...)` only selects another constructor in the same class and does not replace assigning the fields.

For example, after `new StudentProfile("An", 1)`, a state test must read back **`"An"` and `1`**, not merely verify that the `new` statement does not throw an exception.

## 16. Practice exercises

**Exercise 1 — Spot the bug.** Predict the value of `id` after `new User(9)`:

~~~java
class User {
    private int id;

    User(int id) {
        id = id;
    }

    int id() {
        return id;
    }
}
~~~

Fix the constructor so that the field receives the value 9.

**Exercise 2 — Field or parameter?** In `void setAge(int age) { this.age = age; }`, what does each `age` on the left-hand side and right-hand side belong to?

**Exercise 3 — Local variables.** Suppose a class has a field `int total = 7;`. Inside an instance method, there is `int total = 100;`. Predict `System.out.println(total)` and `System.out.println(this.total)`.

**Exercise 4 — Multiple instances.** Given two `StudentProfile` objects with the names `"Lan"` and `"Minh"`. Call `rename("Linh")` on the first object. Does the second object's name change? Why?

**Exercise 5 — Static.** Explain why `static void update(int age) { this.age = age; }` is wrong. Propose replacing it with an instance method or using an object parameter.

**Exercise 6 — Constructor delegation.** Distinguish between `this(name, 0)` and `this.name = name` in a constructor. Which statement assigns a field, and which statement calls another constructor?

**Exercise 7 — Field hiding.** A subclass also declares `size` just like its superclass. Why can `this.size` and `super.size` produce different results?

**Exercise 8 — Safe design.** Write the constructor `Product(String name, int stock)` with two fields `private final String name;` and `private int stock;`; reject empty/`null` names and negative stock, then assign properly using `this`.

### Reference answers

1. The `id` field remains 0 because `id = id` assigns the parameter to itself; fix it to `this.id = id;`.
2. `this.age` is the instance field; `age` without `this` is the parameter.
3. Prints `100` and then `7`, because the local `total` shadows the `total` field name.
4. No. `this` in `rename` points to the object on which it is called; the second object keeps its own field.
5. A static method has no `this` receiver; write `void update(int age) { this.age = age; }` in the appropriate class, or `static void update(Person p, int age) { p.age = age; }` when field access is permitted.
6. `this(name, 0)` delegates to a constructor; `this.name = name` assigns the field of the current object.
7. `this.size` can select the field declared by the subclass, while `super.size` selects the field seen through the superclass according to access rules.
8. Example body: `if (name == null || name.isBlank() || stock < 0) throw new IllegalArgumentException(); this.name = name; this.stock = stock;` (with the constructor placed in a class that has both fields).

## 17. Reference documentation

- [Java Language Specification 17, §6.4.1 — Shadowing](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.4.1): rules for shadowing field names by parameters/local variables and other names.
- [Java Language Specification 17, §15.8.3 — `this`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.8.3): semantics of the `this` expression, and valid and invalid contexts.
- [Java Language Specification 17, §8.3 — Field Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3): class fields, instance fields, and static fields.
- [Java Language Specification 17, §8.8.7 — Constructor Body](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8.7): constructor bodies and explicit constructor invocations.

**Remember:** when a field and a parameter have the **same name**, write **`this.field = parameter;`** to assign state properly to the object. `this.field` refers to the field of the **instance receiving the call**, whereas a bare name is typically resolved to the parameter/local variable shadowing the field. Distinguishing both sides of the assignment avoids a Java bug that compiles easily yet leaves the object holding the wrong data.
