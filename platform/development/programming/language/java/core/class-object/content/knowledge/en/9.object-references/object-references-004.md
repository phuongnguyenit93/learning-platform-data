# Mutating State and Reassigning References in Java

In Java, when a variable has a **reference type**, the variable's value enables the program to refer to an object (or be `null`). Two operations that are often confused are:

1. **Mutating object state**: modifying a field or data inside **the object that the variable is referencing**.
2. **Reassigning a reference**: changing **the value of the reference variable** so that it points to another object or `null`.

The two operations affect different things. They can cause expressions in a program to produce very different results, especially when **multiple variables reference the same object**.

Example:

```java
class Box {
    int value;
}

Box first = new Box();
first.value = 10;

Box alias = first;
alias.value = 20;       // Mutate the state of the existing Box

first = new Box();      // Reassign the variable first to a new Box
first.value = 30;
```

The declarations/statements above illustrate a snippet inside a method. After running:

- `alias.value` is **20**: `alias` still references the first object.
- `first.value` is **30**: `first` has been reassigned to the second object.
- `first == alias` is **false**: the two variables no longer reference the same object.

**Key point:** the statement `alias.value = 20` modifies **the object**; the statement `first = new Box()` modifies **the reference variable**. You should not equate the two assignments just because both use the `=` sign.

## 1. Identify Exactly What Changes: Reference or Object State?

In the two operations `user = new User()` and `user.name = "Mai"`, the `=` sign is the same, but **the write target is different**.

| Statement | What changes? | What will existing aliases see? |
| --- | --- | --- |
| `user = new User();` | Reference of the variable `user` | Aliases do not automatically change their reference |
| `user.name = "Mai";` | Field of the object that user points to | Aliases to the same object see the new name |
| `holder.user = other;` | Reference field in the holder object | Aliases to holder see the new link |
| `array[0] = other;` | A slot in the array object | Aliases to array see the new slot |
| `user = null;` | Reference of the user variable | The old object may still be held by other aliases |
| `user.updateName("Mai");` | Depends on the method implementation | Must check API behavior, do not guess from the name |

These are snippets requiring appropriate classes and variables. In this lesson, learners will trace **reference arrows** and **each object's state** through method parameters, immutable String, arrays, collection mutation, and field reassignment; without repeating the entire basic reference concepts lesson.

## 2. Mutating State: Modifying the Referenced Object

In a class with an updatable field:

```java
class Counter {
    int value;
}
```

The following code snippet:

```java
Counter counter = new Counter();
Counter otherName = counter;

counter.value = 5;
otherName.value += 2;
System.out.println(counter.value);  // 7
```

Both `counter` and `otherName` reference the same `Counter` object. Therefore, an update through either variable modifies the same `value` field, and both variables observe the new value.

**State-mutating operations** can be written using:

- Direct field assignment, for example `counter.value = 5` if the field has appropriate access permissions.
- Field update operators, for example `counter.value++` or `counter.value += 2`.
- Calling an instance method that modifies state, for example `counter.increment()`.
- Modifying an element of an array object, for example `array[0] = 10`.
- Calling a collection-modifying method, for example `list.add("Java")` on a mutable list.

Not every method call mutates state: getters such as `counter.getValue()` are typically read-only, while immutable APIs may return a new object instead of modifying the old one.

### The Dot and the Left-Hand Side of an Assignment

Compare:

```java
counter = new Counter();   // Reassign the VARIABLE counter
counter.value = 10;        // Reassign the FIELD value of the OBJECT
```

In the first line, the assignment target is `counter`. In the second line, the assignment target is `counter.value`. The two expressions have **different left-hand sides**, and therefore what gets updated is different.

## 3. Reassigning a Reference: The Variable Points to Another Object

A regular reference variable not declared `final` can receive another reference:

```java
Counter first = new Counter();
first.value = 10;

Counter second = new Counter();
second.value = 20;

first = second;
```

After the line `first = second;`:

- `first` and `second` both reference **the second object**.
- `first.value` and `second.value` are both `20`.
- The first object that `first` previously referenced **is not turned into** the second object. It retains its own state if it still exists.
- If no references remain to the first object and it is no longer reachable through other paths, that object may be **eligible for garbage collection**; this does not guarantee the JVM collects it immediately.

Reassigning a variable **does not** automatically copy the object's state into a new object, nor does it update every alias that previously referenced the old object.

### Example with Multiple Reference Variables

```java
Counter first = new Counter();
first.value = 1;

Counter second = first;         // Both variables reference Counter #1
first = new Counter();          // Only first switches to Counter #2
first.value = 2;

System.out.println(first.value);  // 2
System.out.println(second.value); // 1
```

Diagram after the last line:

```text
first  ───────────> Counter #2 { value: 2 }

second ───────────> Counter #1 { value: 1 }
```

The difference is that **the value of the variable `first` changes**, while **the value of the variable `second` does not change**. The two variables have no “auto-update together” link after the assignment `Counter second = first;`.

## 4. Complete Java 17 Program: Observing Both Operations

Save all of the following content to **`ReferenceChangeDemo.java`**:

```java
class Box {
    private int value;

    Box(int value) {
        this.value = value;
    }

    int value() {
        return value;
    }

    void setValue(int value) {
        this.value = value;
    }
}

public class ReferenceChangeDemo {
    public static void main(String[] args) {
        Box first = new Box(10);
        Box alias = first;

        System.out.println("Cùng đối tượng: " + (first == alias));

        alias.setValue(20);
        System.out.println("first sau mutate: " + first.value());
        System.out.println("alias sau mutate: " + alias.value());

        first = new Box(30);
        System.out.println("Cùng đối tượng sau reassign: " + (first == alias));
        System.out.println("first mới: " + first.value());
        System.out.println("alias cũ: " + alias.value());

        first = alias;
        System.out.println("Cùng đối tượng sau gán lại: " + (first == alias));
        System.out.println("first cuối: " + first.value());
    }
}
```

Compile/run with JDK 17 or later:

```bash
javac -encoding UTF-8 ReferenceChangeDemo.java
java ReferenceChangeDemo
```

**Exact stdout:**

```text
Cùng đối tượng: true
first sau mutate: 20
alias sau mutate: 20
Cùng đối tượng sau reassign: false
first mới: 30
alias cũ: 20
Cùng đối tượng sau gán lại: true
first cuối: 20
```

Analysis:

1. `first` and `alias` initially hold the same reference value, so `first == alias` is `true`.
2. `alias.setValue(20)` modifies the `value` field of the shared object. Both `first.value()` and `alias.value()` return `20`.
3. `first = new Box(30)` creates another `Box` and assigns the new reference to **the variable `first`**.
4. `alias` still points to the old `Box` with `value = 20`, so `first == alias` becomes `false`.
5. `first = alias` only copies the reference from `alias` to `first`; the new object with value `30` is not “overwritten to `20`”, rather `first` stops referencing it. Afterward, the two variables point to the same old object again.

The example uses a `private` field and a `setValue` setter to further highlight that **calling a state-modifying method** is still mutation, even though the caller is not allowed to access the field directly.

## 5. Observing Mutation Through an Alias; Observing Reassignment Through the Variable Itself

Suppose `Box` has `setValue(int)` and `value()`:

~~~java
Box original = new Box(5);
Box alias = original;
alias.setValue(7);
System.out.println(original.value()); // 7
alias = new Box(9);
System.out.println(original.value()); // still 7
~~~

This is an illustrative snippet inside a method. Mutation affects the old object so original sees 7; reassigning alias only changes the reference inside alias, without undoing the mutation or changing the reference of original.

To predict the output, draw two columns after each statement: **which object each variable's reference currently points to** and **what the state of each object currently is**. Use reference `==` to check for the same instance; do not use `equals` when the question is solely about identity. This tracing approach differs from the in-depth aliasing lesson on sharing nested mutable objects and defensive copying.

## 6. Passing Arguments to a Method: Java Is Always Pass-by-Value

A serious misconception is thinking that Java “passes objects by reference,” meaning the receiving method can **reassign the caller's variable**. In reality, Java passes **a copy of each argument's value** into the formal parameter:

- If the argument is a primitive, the copy is the primitive value.
- If the argument is a reference, the copy is **the reference value**.
- Reassigning **the parameter variable** only modifies that parameter variable.
- Modifying **the object's state through the parameter** can make the caller see the change if the caller still references the same object.

### 6.1. Runnable Program: Mutating and Then Reassigning a Parameter

Save as **`ParameterReferenceDemo.java`**:

```java
class Counter {
    int value;

    Counter(int value) {
        this.value = value;
    }
}

public class ParameterReferenceDemo {
    static void mutate(Counter counter) {
        counter.value += 5;
    }

    static void reassign(Counter counter) {
        counter = new Counter(99);
        System.out.println("Trong reassign: " + counter.value);
    }

    static Counter replace(Counter counter) {
        counter = new Counter(counter.value * 2);
        return counter;
    }

    public static void main(String[] args) {
        Counter current = new Counter(10);

        mutate(current);
        System.out.println("Sau mutate: " + current.value);

        reassign(current);
        System.out.println("Sau reassign: " + current.value);

        Counter next = replace(current);
        System.out.println("current: " + current.value);
        System.out.println("next: " + next.value);
        System.out.println("Cùng tham chiếu: " + (current == next));
    }
}
```

Commands:

```bash
javac -encoding UTF-8 ParameterReferenceDemo.java
java ParameterReferenceDemo
```

**Stdout:**

```text
Sau mutate: 15
Trong reassign: 99
Sau reassign: 15
current: 15
next: 30
Cùng tham chiếu: false
```

Explanation:

- `mutate(current)` copies the reference of `current` into the parameter `counter`. Both point to the same object; `counter.value += 5` causes `current.value` to become `15`.
- `reassign(current)` receives the same initial reference, but `counter = new Counter(99)` only changes **the local parameter variable**. After the method finishes, `current` still points to the object with `15`.
- `replace(current)` creates a new object containing `30` and **returns the new object's reference**. The caller stores that value in `next`. If you want the variable `current` to switch to the new object, the caller must **explicitly assign** `current = replace(current);`.
- `current == next` is `false` because the two references refer to different objects.

**Correct operational rule:** for a method to create a new object and replace the object that the caller uses, it typically **returns the new reference**, and then the caller decides to **reassign the variable**.

### 6.2. Why Doesn't a `final` Parameter Make an Object Immutable?

`final Counter counter` in a parameter list forbids `counter = new Counter(...)`, but **does not forbid** `counter.value++` if the field is modifiable and access permissions allow it.

```java
static void increment(final Counter counter) {
    counter.value++;
    // counter = new Counter(0); // ERROR: reassigning a final parameter
}
```

`final` is attached to **the parameter variable**, and does not automatically lock the entire state of the object that the parameter variable points to.

## 7. `return this` and Mutating State: Same Object or New Object?

An instance method can mutate an object's state and then return **`this`**:

```java
class Score {
    private int points;

    Score(int points) {
        this.points = points;
    }

    Score add(int amount) {
        points += amount;
        return this;
    }

    int points() {
        return points;
    }
}
```

`Score next = score.add(10);` **does not automatically create a new object**: `next` and `score` both point to the current instance. This style is commonly used in a **mutable fluent API**.

Compare another design approach:

```java
final class ImmutableScore {
    private final int points;

    ImmutableScore(int points) {
        this.points = points;
    }

    ImmutableScore add(int amount) {
        return new ImmutableScore(points + amount);
    }

    int points() {
        return points;
    }
}
```

`ImmutableScore newer = older.add(10);` returns **a new object**. `older` still references the old object, and its content does not change.

**Both APIs share the name `add` but have different semantics.** To determine whether an operation **mutates** or **returns a new object**, you must read the contract/implementation rather than guessing from the return type or method name.

## 8. Reassigning a Reference and Reassigning a Reference-Type Field

An object can contain **a field referencing another object**:

```java
class Address {
    String city;

    Address(String city) {
        this.city = city;
    }
}

class Customer {
    Address address;

    Customer(Address address) {
        this.address = address;
    }
}
```

Given:

```java
Address address = new Address("Hà Nội");
Customer customer = new Customer(address);

customer.address.city = "Đà Nẵng"; // (A)
customer.address = new Address("Huế"); // (B)
```

The two lines have different effects:

- **(A) Mutating state**: the `city` field of the original `Address` object changes from `"Hà Nội"` to `"Đà Nẵng"`. The `address` variable still points to the same original object, so `address.city` reads `"Đà Nẵng"`.
- **(B) Reassigning a reference field**: the field `customer.address` is assigned a reference to a new `Address` with `city = "Huế"`. The local variable `address` **does not change**; it still points to the original object with `city = "Đà Nẵng"`.

Diagram after (B):

```text
address ──────────────────> Address #1 { city: "Đà Nẵng" }

customer ───> Customer
                 └── address ───> Address #2 { city: "Huế" }
```

**Reference reassignment does not happen only with local variables.** A reference field, a reference array element, or a static variable can also be assigned a new reference if type rules, access permissions, and `final` rules allow it.

### Complete Example of a Reference Field

Save as **`ReferenceFieldDemo.java`**:

```java
class Address {
    String city;

    Address(String city) {
        this.city = city;
    }
}

class Customer {
    Address address;

    Customer(Address address) {
        this.address = address;
    }
}

public class ReferenceFieldDemo {
    public static void main(String[] args) {
        Address firstAddress = new Address("Hà Nội");
        Customer customer = new Customer(firstAddress);

        customer.address.city = "Đà Nẵng";
        System.out.println(firstAddress.city);

        customer.address = new Address("Huế");
        System.out.println(customer.address.city);
        System.out.println(firstAddress.city);
        System.out.println(customer.address == firstAddress);
    }
}
```

```bash
javac -encoding UTF-8 ReferenceFieldDemo.java
java ReferenceFieldDemo
```

Stdout:

```text
Đà Nẵng
Huế
Đà Nẵng
false
```

The program confirms that **mutation of the old Address** is not the same as **changing the reference field to a new Address**.

## 9. Arrays: Modifying an Element Differs from Reassigning an Array Variable

**Arrays are objects** in Java. Therefore, with `int[]`:

```java
int[] numbers = {1, 2};
int[] alias = numbers;
```

`numbers` and `alias` are both reference variables pointing to the same array object.

- `numbers[0] = 9;` changes **the array's state**; `alias[0]` is also `9`.
- `numbers = new int[]{3, 4};` reassigns **the variable `numbers`** so that it points to a new array; `alias[0]` is still `9`.
- `alias = null;` only sets the variable `alias` to `null`; the old array does not automatically become `null`.

### Java 17 Example of Array Aliasing

Save as **`ArrayReferenceDemo.java`**:

```java
import java.util.Arrays;

public class ArrayReferenceDemo {
    public static void main(String[] args) {
        int[] first = {1, 2};
        int[] alias = first;

        first[0] = 9;
        System.out.println(Arrays.toString(alias));

        first = new int[]{3, 4};
        System.out.println(Arrays.toString(first));
        System.out.println(Arrays.toString(alias));
        System.out.println(first == alias);
    }
}
```

```bash
javac -encoding UTF-8 ArrayReferenceDemo.java
java ArrayReferenceDemo
```

Stdout:

```text
[9, 2]
[3, 4]
[9, 2]
false
```

Note that **arrays have a fixed number of elements**: you can modify elements, but you cannot directly increase the `length` of an array object. If a different number of elements is needed, you typically create a new array or use a collection such as `ArrayList`. When you write `numbers = Arrays.copyOf(numbers, 3)`, that reassigns the variable to a **new array object**.

## 10. Collections: `add`, `set`, and Reassigning a List Variable

`ArrayList` is a mutable object. Therefore, two variables pointing to the same list will see the updates:

```java
java.util.List<String> left = new java.util.ArrayList<>();
left.add("A");

java.util.List<String> right = left;
right.add("B");
```

Afterward, `left` and `right` both see `[A, B]`.

If you write `right = new java.util.ArrayList<>();`, only the variable `right` switches to the new list. `left` continues pointing to the old list with `[A, B]`.

### Combined Program Demonstrating Both Operations

Save as **`ListReferenceDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class ListReferenceDemo {
    public static void main(String[] args) {
        List<String> first = new ArrayList<>();
        first.add("Java");

        List<String> second = first;
        second.add("Core");

        System.out.println(first);
        System.out.println(first == second);

        second = new ArrayList<>(first);
        second.set(0, "Spring");

        System.out.println(first);
        System.out.println(second);
        System.out.println(first == second);
    }
}
```

```bash
javac -encoding UTF-8 ListReferenceDemo.java
java ListReferenceDemo
```

Stdout:

```text
[Java, Core]
true
[Java, Core]
[Spring, Core]
false
```

Explanation:

1. `second = first` creates an **alias**.
2. `second.add("Core")` modifies **the same list object**. `first` sees the new element.
3. `second = new ArrayList<>(first)` creates **a new list object**, with its elements copied according to the constructor's mechanism; this is a **shallow copy** of the list.
4. `second.set(0, "Spring")` only replaces the element in the new list and does not modify the `first` list.
5. `first == second` is `false` because since step (3) there have been two different lists.

**Important point about shallow copy:** `new ArrayList<>(first)` copies the structure holding the **element references**, without deep-cloning every member object. If an element is a mutable object and both lists point to that element, mutating that element's state can still be observed through both lists.

## 11. `String` and Immutable Types: Looks Like Mutation, Actually a New Reference

**`String` in Java is immutable**: once a string object is created, no regular API modifies the content of that object itself.

```java
String first = "Java";
String alias = first;

first = first + " 17";
```

The last line creates/obtains a `String` reference value representing the content `"Java 17"` and reassigns the variable `first`. It **does not modify the content** of the `"Java"` string object that `alias` still references.

Therefore:

```java
System.out.println(first); // Java 17
System.out.println(alias); // Java
```

In this case, `first = first + " 17"` is **reassigning a reference variable**, not mutating a `String` object.

### `StringBuilder` Differs from `String`

`StringBuilder` is a mutable object:

```java
StringBuilder builder = new StringBuilder("Java");
StringBuilder aliasBuilder = builder;

builder.append(" 17");
System.out.println(aliasBuilder); // Java 17
```

`append` changes **the state of the existing StringBuilder**, so the alias sees the change. If you write `builder = new StringBuilder("Khác");`, `aliasBuilder` still points to the old builder with `"Java 17"`.

### Runnable Example for Comparison

Save as **`StringReferenceDemo.java`**:

```java
public class StringReferenceDemo {
    public static void main(String[] args) {
        String text = "Java";
        String sameText = text;

        text = text.concat(" 17");
        System.out.println(text);
        System.out.println(sameText);

        StringBuilder builder = new StringBuilder("Core");
        StringBuilder sameBuilder = builder;

        builder.append(" API");
        System.out.println(builder);
        System.out.println(sameBuilder);

        builder = new StringBuilder("New");
        System.out.println(builder);
        System.out.println(sameBuilder);
    }
}
```

```bash
javac -encoding UTF-8 StringReferenceDemo.java
java StringReferenceDemo
```

Stdout:

```text
Java 17
Java
Core API
Core API
New
Core API
```

Checkpoint: seeing `text` differ from `sameText` after string concatenation **is not because Java performs copy-on-write on every object**. The specific reason is that `String` is immutable and the `concat` call returns a reference value; the `text` variable is reassigned.

## 12. `final`: Forbids Variable Reassignment, Not Necessarily Mutation

A reference variable declared `final` cannot be reassigned after valid initialization:

```java
final Box box = new Box(10);

// box = new Box(20); // ERROR: box is a final variable
box.setValue(20);      // VALID if the method allows it
```

The `final` keyword in the line `final Box box` **constrains the variable `box`**, and does not automatically make the `Box` object immutable. Mutable fields of the object can be modified through the `box` reference.

Several cases to distinguish:

| Declaration | Can the reference be reassigned? | Can the object be modified? |
| --- | --- | --- |
| `Box b = new Box(1);` | Yes | Yes, if the API allows |
| `final Box b = new Box(1);` | No | Yes, if the API allows |
| `final String s = "A";` | No | `String` is immutable, so content cannot be modified directly |
| `final List<String> list = new ArrayList<>();` | No | Can call `list.add(...)` because `ArrayList` is mutable |
| `final List<String> list = List.of("A");` | No | Cannot modify the list using the mutators rejected by `List.of` |

Similarly, a **final field** keeps its reference value constant after valid initialization, but **the object behind the reference can be mutable**.

```java
class Holder {
    final java.util.List<String> items = new java.util.ArrayList<>();

    void add(String item) {
        items.add(item);          // Valid
        // items = new ArrayList<>(); // ERROR: final field
    }
}
```

If **true immutability** is needed, you must consider both the mutability of the object's state and references to internal mutable objects, not just add the `final` keyword.

### `final` Variables and Reference Constants Are Not Synonymous

`static final List<String> VALUES = new ArrayList<>();` prevents reassigning the `VALUES` field, but the list can still be modified through mutable APIs. When you want immutable data, use an appropriate structure such as `List.of(...)`, `List.copyOf(...)`, or a class that protects its own state — while also considering the mutability of **the elements**.

## 13. `null`: Reassigning a Null Reference Differs from Deleting an Object

A reference variable can hold `null`:

```java
Box box = new Box(10);
Box other = box;

box = null;
```

Afterward:

- `box == null` is `true`.
- `other` still references the original `Box` object.
- `other.value()` can still return `10`.
- `box.value()` throws `NullPointerException` if the call is executed, because `box` does not reference an object.

**`box = null` does not destroy the object on command**, does not set the object's fields to `null`, and does not automatically affect `other`. It only changes **the value of one reference variable**.

When the object is no longer reachable, the JVM may collect it according to the garbage collector's strategy; setting `box = null` does not guarantee immediate collection or invoke any deterministic cleanup behavior.

### Example with a Guard

```java
if (box != null) {
    System.out.println(box.value());
} else {
    System.out.println("Không có Box");
}
```

Here, the `null` check only indicates **whether the variable holds a reference**; it does not prove that the object is immutable, will stay alive until a specific point in time, or how many aliases are using it.

## 14. Mutating Through Another Reference Does Not Require the Same Variable Name

Objects can be shared through **fields**, **parameters**, **array elements**, or **collections**, not only through two local variables.

Example:

```java
class Node {
    int value;
}

Node shared = new Node();
Node[] nodes = {shared};
java.util.List<Node> list = new java.util.ArrayList<>();
list.add(shared);

nodes[0].value = 7;
System.out.println(list.get(0).value); // 7
```

`shared`, `nodes[0]`, and `list.get(0)` all provide references to the same `Node`. Changing `value` through one access path is seen through the other paths.

However, if you assign:

```java
nodes[0] = new Node();
nodes[0].value = 3;
```

then **the array element `nodes[0]` is assigned a new reference**; the `shared` variable and the element in `list` still point to the old `Node` with `value = 7`.

Do not confuse **replacing a reference array element** with **modifying the state of the object referenced by that element**:

- `nodes[0].value = 3;`: modifies the `value` field of the current object.
- `nodes[0] = new Node();`: replaces the reference stored at position `nodes[0]`.

## 15. Shallow Copy and Deep Copy: Not Every “Copy” Isolates State

**Copying a reference**:

```java
Address second = first;
```

`second` and `first` point to the same object, so any mutation on the object can be shared.

A **shallow copy** creates a new container object but retains references to the nested objects inside. Example:

```java
class Person {
    String name;
    Address address;

    Person(String name, Address address) {
        this.name = name;
        this.address = address;
    }
}
```

Suppose:

```java
Address address = new Address("Hà Nội");
Person original = new Person("An", address);
Person shallow = new Person(original.name, original.address);
```

`original` and `shallow` are **two different `Person` instances**. However, `original.address` and `shallow.address` reference **the same `Address`**, because the constructor uses the same reference value.

Therefore:

```java
shallow.name = "Bình";           // Only modifies the shallow Person
shallow.address.city = "Huế";    // Modifies the shared Address
```

Afterward, `original.name` is still `"An"`, while `original.address.city` has become `"Huế"`.

**Deep copy** generally aims to create the necessary nested objects in a way that avoids sharing mutable state. For the simple `Person` above, you might consider:

```java
Person deep = new Person(
        original.name,
        new Address(original.address.city)
);
```

At this point, `deep.address` is a different object from `original.address`. However, **deep copy has no universal magic solution** for every object graph: if an object contains many links, cycles, external resources, or immutable objects, an appropriate copying policy is needed to avoid bugs or unnecessary copying.

### When an API Returns a Mutable Field

```java
class Library {
    private final java.util.List<String> names = new java.util.ArrayList<>();

    java.util.List<String> names() {
        return names; // Returns the same mutable reference
    }
}
```

The caller is permitted to use the returned list according to its access level and can call `library.names().add("X")`, thereby modifying the state **inside `Library`**.

If you do not want to expose mutable state, one option is to return `List.copyOf(names)` (a list that cannot be modified via standard mutators, copies elements by reference, and does not support `null` elements), or return another copy appropriate to the contract. Remember that a **shallow** copy can still hold references to mutable elements.

## 16. Reassigning References in Loops and Conditionals

A variable can change the object it references multiple times:

```java
Box chosen = new Box(1);

if (chosen.value() < 5) {
    chosen = new Box(10);
}
System.out.println(chosen.value()); // 10
```

The `if` branch changes **the variable `chosen`**, and does not update the Box with `value = 1`. Any other aliases (if present) to the old Box will not be affected.

In a loop, pay attention to the variable's scope:

```java
Box current = new Box(0);

for (int i = 0; i < 3; i++) {
    current = new Box(i);
}
System.out.println(current.value()); // 2
```

Each loop iteration creates a new Box and assigns its reference to `current`. Finally, `current` points to the Box with `value = 2`. If references to Boxes from earlier iterations are still kept outside, they remain independent; otherwise, they can become unreachable objects.

**Learning point:** seeing that the variable `current` has a single name does not mean the program creates only one object across all loop iterations.

## 17. Reassigning a `static` Reference Field and Program-Wide Sharing

A `static` reference field belongs to the class according to Java's rules. If code changes a `static field` from object A to object B, places accessing that same field can see the new reference once Java memory rules are satisfied.

```java
class Registry {
    static Box current = new Box(1);
}
```

Inside a method:

```java
Box saved = Registry.current;
Registry.current.setValue(2); // Mutate Box #1
Registry.current = new Box(3); // Reassign static field

System.out.println(saved.value());          // 2
System.out.println(Registry.current.value()); // 3
```

`saved` keeps the reference to the old Box; reassigning `Registry.current` does not change `saved`.

**Multithreading note:** if different threads concurrently read/write a static or instance reference field, *happens-before* rules, `volatile`, synchronization, and atomic types matter in practice. A single reference assignment has basic atomicity properties, but **does not** turn the entire sequence “read state → modify state → replace reference” into an atomic transaction. Use `AtomicReference`, locks, or an immutable snapshot design when concurrent coordination is needed; do not rely on something “looking like a single assignment”.

## 18. Reassigning References and Immutable Objects: Create a New Instance Instead of Mutating

With an **immutable object**, key state values cannot be changed after creation. When a different logical state is desired, you typically **create a new object and reassign the variable**.

Example using `record` in Java 17:

```java
record Point(int x, int y) {
    Point moveX(int delta) {
        return new Point(x + delta, y);
    }
}
```

Inside a method:

```java
Point original = new Point(1, 2);
Point updated = original.moveX(3);

System.out.println(original);  // Point[x=1, y=2]
System.out.println(updated);   // Point[x=4, y=2]
System.out.println(original == updated); // false
```

`Point.moveX` does not mutate the `original` object; instead, it creates a new `Point`. If the caller wants the variable `original` to reference the new state, it must write `original = original.moveX(3);` (if the variable is not `final`).

Note: record components have final fields, but this only provides **shallow immutability** for the components. If a record holds a mutable `List`, that list's state can still be modified unless the design performs appropriate copying/protection.

### Runnable Program with an Immutable Record

Save **`RecordReferenceDemo.java`**:

```java
record Point(int x, int y) {
    Point moveX(int delta) {
        return new Point(x + delta, y);
    }
}

public class RecordReferenceDemo {
    public static void main(String[] args) {
        Point original = new Point(1, 2);
        Point updated = original.moveX(3);

        System.out.println(original);
        System.out.println(updated);
        System.out.println(original == updated);

        original = updated;
        System.out.println(original);
    }
}
```

```bash
javac -encoding UTF-8 RecordReferenceDemo.java
java RecordReferenceDemo
```

Stdout:

```text
Point[x=1, y=2]
Point[x=4, y=2]
false
Point[x=4, y=2]
```

The last line shows that **the variable `original` was assigned a new reference**, not that the initial `Point` object was modified.

## 19. Access Control Affects Object Mutability, Not the Reference Mechanism

Not every object allows the caller to modify fields directly. Example:

```java
class BankAccount {
    private int balance;

    BankAccount(int initial) {
        if (initial < 0) {
            throw new IllegalArgumentException("negative initial balance");
        }
        balance = initial;
    }

    void deposit(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("nonpositive deposit");
        }
        balance += amount;
    }

    int balance() {
        return balance;
    }
}
```

Given:

```java
BankAccount first = new BankAccount(100);
BankAccount alias = first;

alias.deposit(50);
System.out.println(first.balance()); // 150

// first.balance = -20;  // Compile error: balance is private
```

**Key point:** a `private` field does not prevent **aliasing**. Both references still point to the same object and see the same state. However, the class controls **how state is allowed to change**, for example through `deposit` with business rules.

Encapsulation reduces the risk of external code arbitrarily modifying state, but it does not prevent a valid API on a mutable object from updating that object.

## 20. Common Mistakes

| Situation | Misconception | Correct understanding/fix |
| --- | --- | --- |
| `Box b = a;` | Thinking it clones `a` | Only copies the reference value; `a` and `b` are aliases of each other |
| `b.value = 5;` | Thinking it only “modifies variable b” | It modifies the field of the object that `b` points to |
| `b = new Box();` | Thinking it reset the old object | It assigns variable `b` to a new object |
| `void reassign(Box b) { b = new Box(); }` | Thinking the caller's variable is changed | Only the parameter variable `b` changes; the caller does not change |
| `String s = s + "x";` | Thinking the content of the old `String` object changed | `String` is immutable; variable `s` receives a reference to the resulting string |
| `final Box b = new Box();` | Thinking the object cannot be modified | `final` on the variable only forbids reassigning `b` |
| `list2 = new ArrayList<>(list1);` | Thinking it deep-clones every element | It only copies the list structure, usually a **shallow copy** |
| `a.equals(b)` returns `true` | Thinking the two variables point to the same instance | They may be two objects equal in content but with different identities |
| `a = null;` | Thinking the object is deleted immediately | Only variable `a` receives `null`; other aliases may still hold the object |
| `array[0] = new Box();` | Thinking the old object at that position is modified | The array element now references a new object |
| `holder.field = new Box();` | Thinking another local variable also changes | Only the reference field `holder.field` is reassigned |
| Calling mutations on shared state from multiple threads | Thinking having aliases is safe under concurrency | Appropriate synchronization/thread-safety contract is required |
| `record` or `final` | Thinking every object inside is immutable | Check components/fields referencing mutable data |
| `counter++` on a shared field | Thinking it is a multi-thread atomic operation | This is a read–modify–write operation; an appropriate concurrency solution is required |

When encountering a bug, ask **what is the left-hand side of the assignment?** If it is a reference variable, that variable changes. If it is a field or element of an object, the corresponding object's state changes. If it is a return value from a method, you need to read the method's contract to know whether it modified the object or created a new object.

## 21. Practice Exercises with Answers

### Exercise 1 — Aliasing and Reassignment

```java
class Item {
    int count;

    Item(int count) {
        this.count = count;
    }
}
```

Code snippet:

```java
Item x = new Item(1);
Item y = x;
x.count = 2;
x = new Item(3);
System.out.println(x.count);
System.out.println(y.count);
System.out.println(x == y);
```

**Answer:**

```text
3
2
false
```

`y` still references the old object updated to `2`. `x` switches to the new object with `3`.

### Exercise 2 — Parameters Passed by Value

```java
static void change(Item item) {
    item.count = 4;
    item = new Item(10);
}
```

Caller:

```java
Item original = new Item(1);
change(original);
System.out.println(original.count);
```

**Answer:** `4`. The field modification before reassigning the parameter affects the caller's object; the subsequent reassignment of the parameter variable does not change `original`.

### Exercise 3 — Changing a Reference Inside a Field

```java
Address shared = new Address("A");
Customer customer = new Customer(shared);
customer.address.city = "B";
customer.address = new Address("C");
System.out.println(shared.city);
System.out.println(customer.address.city);
```

**Answer:** `B` and `C`, respectively. The old `Address` object still holds `B`; the field `customer.address` points to the new object `C`.

### Exercise 4 — Does `final` Forbid Modifying a List?

```java
final java.util.List<String> names = new java.util.ArrayList<>();
names.add("Java");
```

**Answer:** `names.add("Java")` is valid because the list is mutable. `names = new ArrayList<>();` is invalid because `names` is a final variable. Those are two different restrictions.

### Exercise 5 — Arrays and Aliasing

```java
int[] a = {1, 2};
int[] b = a;
a[0] = 7;
a = new int[]{8, 9};

System.out.println(b[0]);
System.out.println(a[0]);
```

**Answer:** `7` then `8`. `b` holds the old array whose first element was modified; `a` points to the new array.

### Exercise 6 — Does Copying a List Separate Element Objects?

Suppose a `List<Item>` contains a mutable `Item`. Does creating `List<Item> copy = new ArrayList<>(original);` guarantee that modifying `copy.get(0).count` will not affect `original.get(0).count`?

**Answer:** **No.** The new `ArrayList` has an independent structure, but its elements are references to the old `Item` objects. An element-copying policy is required if independent state is desired.

### Exercise 7 — String and StringBuilder

```java
String s1 = "A";
String s2 = s1;
s1 += "B";

StringBuilder b1 = new StringBuilder("A");
StringBuilder b2 = b1;
b1.append("B");
```

**Answer:** `s1` is `"AB"` and `s2` is `"A"` because strings are immutable and the variable `s1` was reassigned; `b1` and `b2` both show the content `"AB"` because they reference the same mutable `StringBuilder`.

## 22. Checklist for Analyzing State Changes and References

1. **Identify the variable type:** primitive or reference type?
2. **Identify the number of objects created:** each `new` that completes normally can create a new instance; do not count the number of variable names as the number of objects.
3. **Draw an alias diagram:** which variables/fields/array elements are pointing to the same object?
4. **Check the assignment target:** `ref = ...` assigns a variable; `ref.field = ...` assigns a field; `array[i] = ...` assigns an array element.
5. **Distinguish field types:** a primitive field has a value written into it; a reference field can be reassigned to another object.
6. **Inspect the method being called:** a getter, setter, mutator, builder, or immutable “with” method can have different effects.
7. **Check `final`:** a constraint on a reference variable/field does not automatically lock a mutable object.
8. **Check `null`:** a `null` variable has no object to access instance fields/methods; assigning `null` does not destroy other aliases.
9. **Check method parameters:** Java is pass-by-value; mutating through a parameter can affect the shared object, whereas reassigning a parameter does not change the caller's variable.
10. **If creating a copy, determine whether it is shallow or deep:** copying a collection does not necessarily copy its elements.
11. **Examine state sharing:** objects referenced by multiple components/threads may require encapsulation, immutability protection, and synchronization.
12. **Verify results using identity when needed:** `a == b` for references tells you whether they point to the same object, but do not confuse it with `equals` comparing logical values.

## Key Takeaways

- **Mutating state (mutation)** affects data **inside the existing object**; any alias to the same object can observe that change.
- **Reassigning a reference (reassignment)** changes **the variable, field, or array element holding the reference**; it does not update every alias pointing to the previous object.
- **`Box other = box` only copies the reference**, it does not clone the object; `other.value = 3` is completely different from `other = new Box()`.
- Java **passes arguments by value**. For references, the receiver gets a copy of the reference value and cannot reassign the caller's variable.
- **`final` on a reference variable forbids reassigning the variable**, but may still allow modifying a mutable object; `String` and immutable objects typically represent changes through a new object and reference reassignment.
- When unsure, draw **variable → object** before and after each line; that is a simple, reliable way to avoid confusion.
