# Classes, Types, and Instances: Foundational Concepts

When reading the Java statement `CounterView view = new ClickCounter("Nút A", 10);`, beginners may call all three elements “objects.” In fact, three separate questions need to be asked:

- **Class:** which definition describes the object's data, methods, constructor, and rules?
- **Type:** which operations can a variable or expression use at compile time?
- **Instance/object:** which concrete object was created and has its own state at runtime?

Another important concept is the **reference**: in Java, a variable of a reference type typically holds a value used to access an object; the variable itself is not the object. This lesson focuses on distinguishing these concepts in code and runtime results.

## 1. A Map of the Four Concepts

| Term | Question answered | Example |
| --- | --- | --- |
| Class | How is the object defined? | `class ClickCounter` has `clicks` state and `click()` behavior |
| Type | Which operations are valid through this variable? | `CounterView` declares `value()` |
| Instance | Which concrete object exists? | The result of `new ClickCounter("Nút A", 10)` |
| Reference | Which object does the variable access? | `view` holds a reference to a `ClickCounter` |

In Java, a **class also defines a type**, but “class” and “type” are not synonymous. Other types include interface types, array types, primitive types, and more. Also, the same object can be accessed through multiple **compatible declared types**.

For example:

~~~java
CounterView view = new ClickCounter("Nút A", 10);
~~~

On the left, `CounterView` is the declared type of variable `view`. On the right, `new ClickCounter(...)` creates an instance of `ClickCounter`. Variable `view` receives a reference to that instance. Only one object is created, not two merely because two type names appear.

## 2. A Class Describes Shared Structure and Behavior

A class declares the members and rules for its objects in Java:

| Component | Example | Role |
| --- | --- | --- |
| Instance field | `private int clicks;` | Stores the click count for **each** counter |
| Final field | `private final String label;` | Counter label, assigned during initialization and not reassigned afterward |
| Constructor | `ClickCounter(String label, int initial)` | Establishes a valid initial state |
| Instance method | `void click()` | Operates on the counter receiving the call |
| Query method | `int value()` | Returns the current click count |
| Access modifier | `private`, `public` | Controls where members can be accessed |

Writing `class ClickCounter { ... }` alone **does not create** a concrete counter. Every time `new ClickCounter(...)` is evaluated, Java creates a new object and executes the corresponding constructor. Objects share the methods defined by their class but may hold different field values.

**Do not take the “class is a blueprint” analogy too literally.** In Java, classes also participate in type rules, inheritance, access control, and method selection. A blueprint is a starting analogy, not the full meaning of a class.

## 3. Standalone Runnable Program: One Object, Multiple Type Perspectives

This example uses Java 11 or later. Save all of it in `Main.java`.

~~~java
interface CounterView {
    int value();
}

final class ClickCounter implements CounterView {
    private final String label;
    private int clicks;

    ClickCounter(String label, int initial) {
        if (label == null || label.isBlank()) {
            throw new IllegalArgumentException("Label must not be blank");
        }
        if (initial < 0) {
            throw new IllegalArgumentException("Initial count must not be negative");
        }
        this.label = label;
        this.clicks = initial;
    }

    @Override
    public int value() {
        return clicks;
    }

    public String label() {
        return label;
    }

    public void click() {
        clicks = Math.addExact(clicks, 1);
    }
}

public class Main {
    public static void main(String[] args) {
        ClickCounter first = new ClickCounter("Nút A", 10);
        CounterView view = first;
        Object general = first;
        ClickCounter second = new ClickCounter("Nút A", 10);

        first.click();

        System.out.println(first.value());                  // 11
        System.out.println(view.value());                   // 11
        System.out.println(second.value());                 // 10
        System.out.println(first == view);                  // true
        System.out.println(view == general);                // true
        System.out.println(first == second);                // false
        System.out.println(view.getClass().getSimpleName()); // ClickCounter
    }
}
~~~

Run with:

~~~bash
javac Main.java
java Main
~~~

Output:

~~~text
11
11
10
true
true
false
ClickCounter
~~~

### Tracing Each Call

1. `new ClickCounter("Nút A", 10)` creates **the first instance** with `clicks = 10`. Variable `first` contains a reference to it.
2. `CounterView view = first` **copies the reference**. It does not create a second `ClickCounter`.
3. `Object general = first` also refers to the first instance; that one instance now has three reference variables pointing to it.
4. `new ClickCounter("Nút A", 10)` creates **the second instance** and assigns it to `second`. Matching labels and initial counts do not make it the first object.
5. `first.click()` changes `clicks` on the first instance from 10 to 11. `view.value()` returns 11 because it accesses the same object; `second.value()` remains 10 because it accesses a different object.
6. Both `first == view` and `view == general` are `true` because their respective references point to the same object. `first == second` is `false`.
7. `view.getClass().getSimpleName()` returns `ClickCounter` because viewing an object through an interface type does not change its runtime class.

~~~mermaid
flowchart LR
    F["first: ClickCounter"] --> C1["ClickCounter #1<br/>label=Nút A; clicks=11"]
    V["view: CounterView"] --> C1
    G["general: Object"] --> C1
    S["second: ClickCounter"] --> C2["ClickCounter #2<br/>label=Nút A; clicks=10"]
~~~

The diagram shows **four reference variables** but only **two instances**. Variables and objects must be counted separately.

## 4. A Type Determines What You Can Call Through a Variable

In the example, `first`, `view`, and `general` all refer to the same object. At compile time, however, they have **different declared types**.

| Variable | Declared type | Methods callable directly |
| --- | --- | --- |
| `first` | `ClickCounter` | `click()`, `value()`, `label()`, and other applicable methods |
| `view` | `CounterView` | `value()` and `Object` methods Java permits through an interface |
| `general` | `Object` | Methods declared by `Object`, such as `getClass()` |

For example:

~~~java
first.click();      // Hợp lệ: ClickCounter khai báo click().
view.value();       // Hợp lệ: CounterView khai báo value().
general.getClass(); // Hợp lệ: Object khai báo getClass().

// view.click();        // Không biên dịch: CounterView không khai báo click().
// general.value();     // Không biên dịch: Object không khai báo value().
~~~

These illustrative statements belong **inside a method** with the three variables already available, as in `main`; they are not a standalone Java file. The runtime object still has `click()`; the error occurs because **the type visible to the compiler at the call site** does not declare that method. To call additional capabilities, you can retain a variable of the concrete type or check the type before casting deliberately. Avoid unconditional casts when the runtime class is unknown.

**Distinguish two ideas:** the declared type restricts which operations can legally be called; for **overridden instance methods**, the runtime class determines which implementation executes. This underlies polymorphism, but assigning a reference to an interface-typed variable does not create a new object.

### Java Types Go Beyond Classes

- **Class types:** `ClickCounter`, `String`, `Object`.
- **Interface types:** `CounterView`, `Runnable`. An interface defines a contract and cannot be instantiated directly using `new CounterView()`.
- **Primitive types:** `int`, `long`, `boolean`; primitive values are not instances created using `new`.
- **Array types:** `int[]`, `String[]`; arrays are objects and have their own array types.
- **Abstract types:** An `abstract class` is still a class/type, but you cannot instantiate it directly using `new AbstractType()`.

Two variables with the same declared type may refer to different objects; conversely, two variables with different types may refer to **the same object** if their types are compatible.

## 5. How Do Instances, Identity, and State Differ?

An instance is a concrete object at runtime. We must distinguish three aspects:

| Aspect | Question | Example |
| --- | --- | --- |
| **Identity** | Is this the very same object as before? | `first == view` is `true` |
| **State** | What information does the object hold? | The `clicks` value in `first` has increased to 11 |
| **Behavior** | Which operations can it perform? | `click()` updates; `value()` queries |

An object can change state while **remaining the same object**. Conversely, two distinct objects may contain identical data without becoming one object.

~~~java
ClickCounter a = new ClickCounter("Trùng tên", 5);
ClickCounter b = new ClickCounter("Trùng tên", 5);

System.out.println(a == b);      // false
System.out.println(a.equals(b)); // false với lớp mẫu hiện tại
~~~

`a.equals(b)` returns `false` for this class because `ClickCounter` has not overridden `equals`, so it inherits identity-based comparison from `Object`. If a class defines value-based equality, two different instances may be `equals` according to that rule. Therefore:

- `==` between references checks **whether they point to the same object**.
- `equals(...)` reflects **the equality rule provided by the class**.
- Matching business data (for example, the same order ID) does not automatically make references point to one object; uniqueness of a business identifier is a separate rule.

A class can describe **immutable** objects (whose observable state does not change after initialization). Whether an object is mutable or immutable is a design choice; it does not determine whether it is an instance of a class.

## 6. Three Commonly Confused Operations: new, Reference Assignment, and State Changes

~~~java
ClickCounter x = new ClickCounter("X", 3); // Tạo đối tượng thứ nhất.
ClickCounter y = x;                        // Không tạo đối tượng mới.
x = new ClickCounter("Z", 7);              // Tạo đối tượng thứ hai rồi gán lại x.

y.click();
System.out.println(y.value()); // 4
System.out.println(x.value()); // 7
~~~

This snippet also belongs inside a method and uses the `ClickCounter` definition from the main example.

The differences:

- `new ClickCounter(...)` creates a new object with initial state validated by its constructor.
- `ClickCounter y = x` copies **the reference value**, not the object; `x` and `y` both refer to object X until one variable is reassigned.
- `x = new ClickCounter("Z", 7)` changes only the object to which **variable x** refers; it does not modify the old object still referenced by `y`.
- `y.click()` changes **the contents of object X** through variable `y`; it does not affect object Z.

A reference variable can also hold `null`:

~~~java
CounterView missing = null;
// missing.value(); // Nếu bỏ chú thích sẽ ném NullPointerException.
~~~

`null` is not an “empty instance” of `CounterView` or `ClickCounter`. A declared but unassigned local variable (`CounterView c;`) likewise cannot be read or used for a call until it has a valid assignment, as enforced by Java's definite-assignment checks.

## 7. Instance Members and Static Members Are Different

An **instance field** without the `static` keyword is stored separately for each object. In the example, `first` and `second` have independent `clicks` values. If you add a `static int createdCount` field to the class and increment it in the constructor, it becomes one shared counter for the loaded class, rather than a separate `createdCount` for every instance.

~~~java
class Sample {
    static int createdCount;
    int value;

    Sample() {
        createdCount++;
    }
}

Sample a = new Sample();
Sample b = new Sample();
a.value = 9;

System.out.println(a.value);            // 9
System.out.println(b.value);            // 0
System.out.println(Sample.createdCount); // 2
~~~

The trial statements must be placed inside a method; do not put standalone statements directly after the class declaration. `static` data belongs to the class (within the scope of the loaded class), while `instance` data belongs to an object. Sharing a type does not make all object fields shared.

Conversely, two separate instance fields containing **references** can still refer to the same other mutable object. “Each instance has its own field” does not mean that its entire object graph is automatically deep-copied.

## 8. Avoiding Common Misconceptions

| Misconception | Correct understanding |
| --- | --- |
| “Declaring a class creates an object.” | A declaration creates the definition; an object must still be created or obtained at runtime. |
| “`CounterView c;` creates a counter.” | It only declares a variable; that line creates no instance. |
| “Two type names mean two objects.” | One object can be used through multiple types and reference variables. |
| “Because `view` is interface-typed, the object has no `click()`.” | The method still belongs to the runtime class; it simply cannot be called directly through an interface type that does not declare it. |
| “Assigning `b = a` copies every field.” | Only the reference is copied; state changes made through one variable are visible through the other if both reference the same object. |
| “Objects with identical fields have identical identity.” | Equal values do not imply the same object. |
| “`null` is a default object.” | `null` does not reference any object. |
| “Every Java type can be instantiated with new.” | Primitive types, interfaces, and abstract classes cannot be instantiated directly using `new`. |
| “Every class must hold mutable state.” | Objects can be immutable, have no instance fields, or provide behavior only. |
| “Every field in a class belongs to each instance.” | A `static` field belongs to the class, not separately to each object. |

Distinguishing class, type, and instance also helps explain why code that uses only a `CounterView` variable need not know all the implementation details of `ClickCounter`. This separation between **the visible contract** and **the actual object** is especially useful when studying interfaces and polymorphism.

## 9. Test Yourself Before Running the Code

**Question 1.** Given `ClickCounter a = new ClickCounter("A", 1); ClickCounter b = a;`, after `b.click()`, what does `a.value()` return?

**Answer:** `2`. Both variables refer to the same instance, so calling through `b` increases the state visible through `a` as well.

**Question 2.** Replace `ClickCounter b = a;` with `ClickCounter b = new ClickCounter("A", 1);`. After `b.click()`, what does `a.value()` return?

**Answer:** `1`. Two uses of `new` create two objects; identical labels do not make them share state.

**Question 3.** With `CounterView view = new ClickCounter("A", 1);`, does `view.click()` compile? Can you call `view.value()`?

**Answer:** `view.click()` does not compile because type `CounterView` does not declare `click()`. `view.value()` is valid. The runtime object is still an instance of `ClickCounter`.

**Question 4.** Does writing `CounterView view = null;` create an instance? What happens when `view.value()` is called?

**Answer:** No instance is created; invoking an instance method through a null reference throws `NullPointerException`.

**Question 5.** Can an instance whose runtime type is `ClickCounter` be referenced through `Object`? Does that assignment change its runtime class?

**Answer:** You can use `Object x = first;`. The assignment does not change the object's runtime class; `x.getClass()` remains `ClickCounter.class`.

**Question 6.** Why is `ClickCounter` both a class and a type, while `CounterView` is a type but not a class?

**Answer:** A class defines a class type and its implementation; an interface declares a type contract that classes can implement. Java has several kinds of types, so “type” cannot be equated with “class.”

When reading OOP code, identify **the class that creates the object, the variable's declared type, the number of instances actually created, and which references point to the same instance**. If you can also determine which methods the compiler permits you to call and which object executes each call, you have a solid foundation for studying encapsulation, inheritance, and polymorphism.
