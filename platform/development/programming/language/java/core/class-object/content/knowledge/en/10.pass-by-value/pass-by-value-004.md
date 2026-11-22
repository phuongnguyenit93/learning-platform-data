# Why Can a Method Modify External Object State in Java?

## 1. Short Answer: Pass-by-Value Can Still Share the Same Object

Java always uses **pass-by-value** when calling methods. This rule applies to both primitive types such as `int`, `double`, and `boolean` and **reference types** such as `Student`, `Account`, `StringBuilder`, `int[]`, and `List<String>`.

The common point of confusion lies in what **the value being passed** is:

- For primitive-type variables, Java copies the **primitive value** (for example, the number `10`).
- For reference-type variables, Java copies the **reference value pointing to an object**. The method receives that copy in its own parameter variable.
- Two reference variables — one at the call site and one as a parameter in the method — therefore **can both point to the exact same object**.
- If the method uses the parameter to **change the state of the shared object**, the call site can observe the new state.
- However, if the method only **reassigns the parameter variable** to another object, the reference variable at the call site **does not change on its own**.

Example:

```java
class Account {
    int balance;

    Account(int balance) {
        this.balance = balance;
    }
}

class Example {
    static void deposit(Account parameter) {
        parameter.balance += 50;
    }

    static void reassign(Account parameter) {
        parameter = new Account(999);
    }
}
```

These are **illustrative class declarations**, without a `main` method yet. If the caller has `Account mine = new Account(100);`, then `Example.deposit(mine)` makes `mine.balance` become `150`, whereas `Example.reassign(mine)` does **not** make `mine` switch to the account with a balance of `999`.

> **Core rule:** Java **copies the reference**; it does not automatically copy the object. Because references can point to the same mutable object, a method is still capable of causing an **externally observable effect** (*side effect*) — which does not contradict pass-by-value at all.

## 2. Distinguishing Four Things Often Mistakenly Called “Reference”

To explain this properly, let us distinguish:

| Concept | Role | During a method call |
| --- | --- | --- |
| **Object** | An entity with identity and state, for example `Account{balance=100}` | The object is not automatically copied merely by passing an argument |
| **Caller variable** | A variable slot such as `mine` of type `Account`, holding a reference value | Remains the caller's variable |
| **Reference value** | A value representing a specific object, or `null` | Java copies this value |
| **Parameter variable** | A local variable belonging to the method invocation, for example `parameter` | Receives the copy; can be reassigned independently |

Visualization:

```text
Caller                                  Method deposit

mine : Account ──────────┐
                         ├──────────> Object A
parameter : Account ─────┘             balance = 100

Two different variable slots. Two reference values both point to Object A.
```

After the statement `parameter.balance += 50`:

```text
mine ────────────────────┐
                         ├──────────> Object A
parameter ───────────────┘             balance = 150
```

No **caller variable is reassigned**; only **the field of Object A** changes from 100 to 150.

After the statement `parameter = new Account(999)` in another method:

```text
mine ─────────────────────────────> Object A: balance = 150

parameter ────────────────────────> Object B: balance = 999
```

At this point, **the parameter's arrow** changes, not the arrow of `mine`.

The diagrams above only describe **reference relationships according to Java semantics** and make no claims about the physical location of variables on the stack or object addresses on the heap; the actual layout is managed by the JVM.

## 3. The Most Important Standalone Example: Modifying an Object Differs from Reassigning a Parameter

Save the entire code into the file **`MutationVsReassignmentDemo.java`** (JDK 17+):

```java
class Account {
    private int balance;

    Account(int balance) {
        this.balance = balance;
    }

    void deposit(int amount) {
        balance += amount;
    }

    int balance() {
        return balance;
    }
}

public class MutationVsReassignmentDemo {
    static void edit(Account target) {
        target.deposit(20);
        target = new Account(999);
        target.deposit(1);
        System.out.println("inside=" + target.balance());
    }

    public static void main(String[] args) {
        Account account = new Account(100);
        Account alias = account;

        edit(account);

        System.out.println("outside=" + account.balance());
        System.out.println("alias=" + alias.balance());
        System.out.println("same=" + (account == alias));
    }
}
```

Compile/run:

```bash
javac MutationVsReassignmentDemo.java
java MutationVsReassignmentDemo
```

**Output:**

```text
inside=1000
outside=120
alias=120
same=true
```

Step-by-step explanation:

1. `new Account(100)` creates **Object A** with field `balance=100`. The variable `account` points to Object A.
2. `Account alias = account;` only copies the reference value. `alias` also points to Object A; **no new Account is created**.
3. When `edit(account)` starts, the parameter `target` receives a **copy of the reference** pointing to Object A.
4. `target.deposit(20)` invokes the instance method on Object A, changing `balance` from 100 to 120. The variables `account` and `alias` still point to Object A, so both will later read 120.
5. `target = new Account(999)` creates **Object B**, and then **only replaces the local reference** inside the `target` parameter. `account` and `alias` do not switch to B.
6. `target.deposit(1)` invokes the method on Object B, raising B's balance to 1000; therefore it prints `inside=1000`.
7. After `edit` finishes, the caller still holds Object A with balance 120; it prints `outside=120` and `alias=120`. `account == alias` is `true` because both hold references to A.

**Trace table:**

| Point in time | `account` in caller | `alias` in caller | `target` in method | State |
| --- | --- | --- | --- | --- |
| Before call | A | A | Does not exist yet | A.balance=100 |
| Upon entering `edit` | A | A | A | A.balance=100 |
| After `target.deposit(20)` | A | A | A | A.balance=120 |
| After `target = new Account(999)` | A | A | B | A=120, B=999 |
| After `target.deposit(1)` | A | A | B | A=120, B=1000 |
| After returning | A | A | Out of scope | A=120 |

**Conclusion:** “A method can modify the caller's object” and “a method can reassign the caller's variable” are **two completely different statements**. Java allows the former in many situations, but does not perform the latter merely by reassigning a parameter.

## 4. Compared to Primitive Types: No Shared Object to Modify

With the primitive `int`, the callee only receives a copy of the **numeric value**; there is no shared `int` object to modify:

```java
static void addTen(int number) {
    number += 10;
}

// In the caller:
int points = 5;
addTen(points);
// points is still 5.
```

Contrasted with an object having mutable state:

| Operation in method | Target of the change | Does caller variable change reference/value? | Is the shared object modified? |
| --- | --- | --- | --- |
| `number = 99;` | Primitive parameter variable | No | No |
| `target = new Account(99);` | Reference parameter variable | No | No |
| `target.deposit(10);` | State of the shared object | No | Yes |
| `array[0] = 10;` | Slot of the shared array | No | Yes |
| `array = new int[3];` | Array parameter variable | No | No |

The expressions above are **snippets**, assuming the corresponding variables/types and methods exist. The difference is the **target being assigned to**: a separate parameter variable or the state of an object with aliases. The separate article on primitives analyzes widening, boxing, overloading, and argument evaluation in depth; here, the comparison only serves to clarify the question “why can a method modify an external object?”.

## 5. Instance Methods Using `this`: The Caller Does Not Need to Pass an Explicit Parameter

There is a related mechanism easily confused with parameters: an **instance method** is always invoked in the context of a **receiver object**.

```java
class Counter {
    private int value;

    Counter(int value) {
        this.value = value;
    }

    void increment() {
        this.value++;
    }

    int value() {
        return this.value;
    }
}
```

If you have `Counter counter = new Counter(4);` and call `counter.increment();`, inside the body of `increment()`, `this` points to the exact object that `counter` is referencing. The statement `this.value++` modifies the field of that receiver. That is why when the caller subsequently reads `counter.value()`, it sees `5`.

**Distinction from pass-by-value:** With `counter.increment()`, there is no explicit object parameter; the object is selected as the **receiver** of the instance method. With `Utility.increment(counter)`, it is a static method call that can accept the `counter` reference as an **argument**, and the method's parameter receives a copy of the reference value. In both cases, a method can ultimately modify the **same object**.

### Runnable Example: Different Receivers Mean Different Objects Are Modified

File **`ReceiverMutationDemo.java`**:

```java
class Counter {
    private int value;

    Counter(int value) {
        this.value = value;
    }

    void add(int delta) {
        this.value += delta;
    }

    int value() {
        return value;
    }
}

public class ReceiverMutationDemo {
    static void addTo(Counter target, int delta) {
        target.add(delta);
    }

    public static void main(String[] args) {
        Counter left = new Counter(2);
        Counter right = new Counter(7);

        left.add(3);
        addTo(right, 4);

        System.out.println(left.value());
        System.out.println(right.value());
    }
}
```

```bash
javac ReceiverMutationDemo.java
java ReceiverMutationDemo
```

```text
5
11
```

`left.add(3)` modifies object `left` via `this`; `addTo(right,4)` modifies object `right` via the `target` parameter and then calls the instance method. There is no “propagation” from object left to right, because the two variables do not point to the same object.

## 6. The “External Object” Is Actually the Same Object Viewed Through Multiple Paths

A method does not have the privilege to modify every object outside its scope. It only works with objects to which its code **has a valid reference path to access** (via parameters, receiver, fields, static fields, method results, etc.).

Example:

```java
class Address {
    String city;

    Address(String city) {
        this.city = city;
    }
}

class Person {
    Address address;

    Person(Address address) {
        this.address = address;
    }
}
```

The classes are **illustrative declarations**, without `main`. Suppose:

```java
Address shared = new Address("Hue");
Person an = new Person(shared);
Person binh = new Person(shared);
```

Object graph:

```text
shared ────────────────────┐
                          |
an ──> Person A ─ address ┼──> Address X {city="Hue"}
                          |
binh -> Person B ─address─┘
```

If a method receives `an` and executes `an.address.city = "Da Nang";`, both `shared.city` and `binh.address.city` will see `"Da Nang"` because all of them lead to **Address X**. If the method only executes `an.address = new Address("Ha Noi");`, the `address` field of Person A is assigned to another object; Person B still points to Address X. These are **two levels of reference**:

1. Local variable `an` points to Person A.
2. Field `an.address` points to Address X.
3. The assignment `an.address = ...` **does not reassign the local variable `an`**, but **modifies the state of Person A** by replacing one of its reference fields.
4. Modifying `an.address.city` changes **the state of Address X**, so every alias of X can observe it.

**Therefore, you must ask:** “Which **variable** is the method reassigning?” and “Which **object** is the method changing?”. Merely knowing a line contains an `=` sign is not enough to conclude whether the caller is affected or not.

## 7. Multi-Object Example: Changing a Reference Field Also Modifies the Caller's Object

Create the file **`NestedReferenceMutationDemo.java`**:

```java
class Address {
    private String city;

    Address(String city) {
        this.city = city;
    }

    String city() {
        return city;
    }

    void moveTo(String city) {
        this.city = city;
    }
}

class Person {
    private Address address;

    Person(Address address) {
        this.address = address;
    }

    Address address() {
        return address;
    }

    void setAddress(Address address) {
        this.address = address;
    }
}

public class NestedReferenceMutationDemo {
    static void changeCity(Person person, String city) {
        person.address().moveTo(city);
    }

    static void replaceAddress(Person person, String city) {
        person.setAddress(new Address(city));
    }

    public static void main(String[] args) {
        Address shared = new Address("Hue");
        Person an = new Person(shared);
        Person binh = new Person(shared);

        changeCity(an, "Da Nang");
        System.out.println("A=" + an.address().city());
        System.out.println("B=" + binh.address().city());

        replaceAddress(an, "Ha Noi");
        System.out.println("A=" + an.address().city());
        System.out.println("B=" + binh.address().city());
        System.out.println("shared=" + shared.city());
    }
}
```

```bash
javac NestedReferenceMutationDemo.java
java NestedReferenceMutationDemo
```

**Output:**

```text
A=Da Nang
B=Da Nang
A=Ha Noi
B=Da Nang
shared=Da Nang
```

Explanation:

- `changeCity(an, "Da Nang")` receives a copy of the reference to **Person An**, calls `person.address()` to obtain the **shared Address**, and then invokes `moveTo` on the shared Address. Because An and Binh point to the same Address object, both read the new city.
- `replaceAddress(an, "Ha Noi")` also receives a copy of the reference to Person An, but calls `person.setAddress(new Address(...))`. This replaces **the reference field inside Person An**, not the `an` variable at the caller.
- Person Binh still points to the original Address, so B remains at `Da Nang`; the variable `shared` also still points to the original Address.

The main point of this article is not “every operation inside a method changes an external object,” but rather that **a method can modify objects reachable via passed-in or already available references**, depending on the method body and access permissions.

## 8. Reassigning a Parameter Cannot Change the Caller's Reference Variable

To isolate this point, consider:

```java
static void rebind(StringBuilder text) {
    text = new StringBuilder("new");
}
```

When the caller has:

```java
StringBuilder original = new StringBuilder("old");
rebind(original);
System.out.println(original.toString());
```

The result is still `old`. The statement `text = new StringBuilder("new")` only changes **the parameter variable `text`**, not the `original` variable.

In Java, there is no default mechanism that turns a method parameter into **an alias of the caller's variable slot itself** so that an assignment like `text = ...` updates the caller's variable. Therefore, the statement “Java passes references to methods” is only correct if understood as **passing the reference value by value**; calling Java *pass-by-reference* in the sense of languages that allow the callee to reassign the caller's variable will cause misconceptions.

### If the Caller Wants to Change the Reference, Receive a Return Value

A clearer design:

```java
static StringBuilder replacement() {
    return new StringBuilder("new");
}
```

Then the caller **assigns it itself**:

```java
StringBuilder original = new StringBuilder("old");
original = replacement();
System.out.println(original.toString()); // new
```

This is a code snippet inside a method. The fact that `original` switches to the new object is **the result of the assignment `original = ...` at the caller**, not the method secretly modifying the caller's variable slot.

Similarly, if you want a method to create a replacement `Account`, the API can return a new `Account` or a result type containing the necessary information. For an API that updates an existing object, this should be clearly expressed through the method name and contract, for example `updateAddress(...)` or `deposit(...)`.

## 9. Arrays Are Objects: A Method Can Modify Elements, But Not the Caller's Array Variable

Java arrays are objects, so a method can change the **slot values** of an array that the caller references:

Create the file **`ArrayArgumentMutationDemo.java`**:

```java
public class ArrayArgumentMutationDemo {
    static void modify(int[] numbers) {
        numbers[0] += 10;
        numbers[1] = 77;
        numbers = new int[] {999};
        System.out.println("inside length=" + numbers.length);
    }

    public static void main(String[] args) {
        int[] values = {1, 2};

        modify(values);

        System.out.println("outside length=" + values.length);
        System.out.println(values[0]);
        System.out.println(values[1]);
    }
}
```

```bash
javac ArrayArgumentMutationDemo.java
java ArrayArgumentMutationDemo
```

```text
inside length=1
outside length=2
11
77
```

Inside `modify`:

1. `numbers` is a copy of the reference to the original array object.
2. `numbers[0] += 10` and `numbers[1] = 77` **write into the two slots of the original array**, so the caller reads `11` and `77`.
3. `numbers = new int[]{999}` creates a new array and only changes the reference **inside the parameter variable**.
4. `values` at the caller still points to the original array of length 2; `numbers` inside is pointing to the new array of length 1, so the line `inside length=1` does not contradict `outside length=2`.

Diagram:

```text
Upon entering modify:
values  ─────┐
             ├──> Array A: [1, 2]
numbers ─────┘

After the two slot modifications:
values  ─────┐
             ├──> Array A: [11, 77]
numbers ─────┘

After numbers = new int[]{999}:
values  ───────> Array A: [11, 77]
numbers ───────> Array B: [999]
```

**Note:** In an `int[]` array, the elements are **primitive values**, yet the **array itself** is still an object. Therefore, changing `numbers[0]` modifies the state of the array object; it is not that Java automatically turns `int` into pass-by-reference.

## 10. Object Arrays: Modifying Element Objects and Replacing References in Slots

For `Student[]`, there can be **two different levels of mutation**:

- `students[0].rename("Lan");` modifies the **Student object** that slot 0 currently references.
- `students[0] = new Student("Lan");` modifies **slot 0 of the array object** to point to a new Student object.

Create the file **`ObjectArrayMutationDemo.java`**:

```java
class Student {
    private String name;

    Student(String name) {
        this.name = name;
    }

    void rename(String name) {
        this.name = name;
    }

    String name() {
        return name;
    }
}

public class ObjectArrayMutationDemo {
    static void mutate(Student[] people) {
        people[0].rename("First");
        people[1] = new Student("Second");
    }

    public static void main(String[] args) {
        Student shared = new Student("Original");
        Student[] students = {shared, shared};

        mutate(students);

        System.out.println(shared.name());
        System.out.println(students[0].name());
        System.out.println(students[1].name());
        System.out.println(students[0] == students[1]);
    }
}
```

```bash
javac ObjectArrayMutationDemo.java
java ObjectArrayMutationDemo
```

```text
First
First
Second
false
```

**Explanation:** Initially both slots point to the same Student `shared`. `people[0].rename("First")` modifies that Student itself; the caller observes `shared.name()` becoming `First`. `people[1] = new Student("Second")` only changes **the reference at slot 1**; slot 0 still holds the first object, so the two elements no longer point to the same Student object.

Do not confuse `Student[] people` with `Student people`. With an array parameter, in addition to the parameter variable, there are also **the shared array and the element objects** that the method can reach.

## 11. Collections: Adding, Removing, and Modifying Elements Is Also Mutation of a Shared Object

Classes such as `ArrayList`, `HashMap`, and `HashSet` are mutable objects. When passing a mutable `List` or `Map` into a method, both sides can use different references to **the same collection object**.

Standalone Java 17+ example, file **`ListMutationDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class ListMutationDemo {
    static void update(List<String> items) {
        items.add("Java");
        items.set(0, "Core");

        items = new ArrayList<>();
        items.add("Local");
        System.out.println("inside=" + items);
    }

    public static void main(String[] args) {
        List<String> topics = new ArrayList<>();
        topics.add("Basics");

        update(topics);

        System.out.println("outside=" + topics);
    }
}
```

```bash
javac ListMutationDemo.java
java ListMutationDemo
```

```text
inside=[Local]
outside=[Core, Java]
```

Before reassigning the parameter, `items` and `topics` point to the same `ArrayList`, so `add` and `set` modify the list held by the caller. After `items = new ArrayList<>()`, the parameter points to the new list and `add("Local")` only affects that new list. Therefore, the caller still sees `[Core, Java]`.

**Not every `List` is modifiable:** `List.of("A", "B")` returns an **unmodifiable** list; calling `add`/`set` can throw `UnsupportedOperationException`. The pass-by-value mechanism **does not determine whether an object is mutable or not** — that is determined by the object's implementation/contract.

### Collections Containing Mutable Elements: Two Layers of Sharing

If a `List<Person>` contains mutable Person objects, then:

- `list.add(person)` changes **the collection structure**.
- `list.get(0).rename(...)` changes **the Person object** pointed to by the collection.
- `list = new ArrayList<>()` inside the method only replaces **the local parameter**, not the caller's variable.
- `list.set(0, new Person(...))` replaces **the reference at position 0 of the collection**.

A shallow copy `new ArrayList<>(existing)` creates **another collection** but typically **keeps the same element references**. To isolate the mutable element objects as well, the elements must be copied according to an appropriate data policy.

## 12. Mutable and Immutable: Having a Shared Reference Does Not Guarantee Modifiable State

A **mutable** object allows its observable state to be changed through its API or valid access permissions, for example `StringBuilder`, `ArrayList`, an `Account` class with a setter/deposit method, or an array.

Conversely, an **immutable** object does not allow the state defined by its contract to be changed after initialization. For example, `String` is immutable. Thus there is a difference between:

```java
String text = "cat";
text = text + "!";
```

and:

```java
StringBuilder builder = new StringBuilder("cat");
builder.append("!");
```

With `String`, the concatenation expression semantically produces a **new String value**, and then the variable `text` is assigned to that value. It does not change the contents of the old `"cat"` String object. With `StringBuilder`, `append` modifies the contents of **the builder object itself**.

### Program Comparing Results Through Parameters

File **`ImmutableVsMutableDemo.java`**:

```java
public class ImmutableVsMutableDemo {
    static void appendToString(String text) {
        text = text + "!";
        System.out.println("string inside=" + text);
    }

    static void appendToBuilder(StringBuilder builder) {
        builder.append("!");
        System.out.println("builder inside=" + builder);
    }

    public static void main(String[] args) {
        String word = "cat";
        StringBuilder buffer = new StringBuilder("cat");

        appendToString(word);
        appendToBuilder(buffer);

        System.out.println("string outside=" + word);
        System.out.println("builder outside=" + buffer);
    }
}
```

```bash
javac ImmutableVsMutableDemo.java
java ImmutableVsMutableDemo
```

```text
string inside=cat!
builder inside=cat!
string outside=cat
builder outside=cat!
```

**Why is it different?**

- `appendToString` only reassigns **the `text` parameter** with a new resulting String; the caller's `word` still points to the old String.
- `appendToBuilder` calls a **mutating** method on the shared builder; the caller's `buffer` reads the new state of that very object.
- Both calls still apply **pass-by-value** in the same way. The difference lies in **the behavior of the object type and the method**.

### Wrapper Types and Records Also Need to Be Understood Properly

`Integer`, `Long`, `Boolean`, and the common wrapper types are immutable. When writing `Integer x = 10; x++;`, the increment involves unboxing/boxing and **reassigning the variable** `x`; it does not modify a field inside the old Integer object.

A `record` has `final` component fields according to record rules, yet if a component holds **a reference to a mutable object**, the record can still **expose indirect changes** without a defensive copy. For example, a record containing a `List<String>` can observe the list changing if that list itself is shared. Do not equate “a reference variable cannot be reassigned” with “the entire object graph is immutable”.

## 13. `final` Restricts Variable Reassignment; It Does Not Prevent Mutation

The `final` keyword has two situations to distinguish:

**A `final` reference variable at the caller:**

```java
final StringBuilder builder = new StringBuilder("A");

builder.append("B"); // Valid: modifies the object.
// builder = new StringBuilder("C"); // Invalid: reassigning a final variable.
```

**A `final` parameter in a method:**

```java
static void update(final StringBuilder target) {
    target.append("!");
    // target = new StringBuilder("other"); // Error: a final parameter cannot be reassigned.
}
```

`final` only forbids **reassigning the reference variable** (`builder` or `target`). It does not automatically freeze the `StringBuilder` object, so `append` still works.

If you want a method not to mutate its argument, `final` on the parameter is **not** a sufficient tool to guarantee it. You need a read-only API, immutable types, defensive copies, an explicit contract, or another appropriate control mechanism.

**Remember:** A method is completely capable of modifying the state of an object held by the caller through a **`final` parameter**; pass-by-value still holds.

## 14. Distinguishing Direct Mutation, Indirect Mutation, and Creating a New Result

Not every observable effect comes from a `field = value` statement directly inside the current method.

**Direct mutation:**

```java
static void increase(Box box) {
    box.count++;
}
```

**Mutation through another method:**

```java
static void increase(Counter counter) {
    counter.increment();
}
```

**Indirect mutation through a child object:**

```java
static void move(Person person) {
    person.address().moveTo("Hue");
}
```

**Not mutating the input, instead returning a new object:**

```java
static String appendMark(String text) {
    return text + "!";
}
```

The snippets above are **illustrative method fragments** and assume the classes `Box`, `Counter`, and `Person` have already been declared with appropriate members. You must inspect **the implementation invoked inside** to know which state changes.

A method might look like it “only calls a getter,” yet the getter has a side effect if its implementation is written that way; similarly, a method named `update` does not guarantee that it mutates its parameter — it might return a new object. **Read the contract and the implementation**, rather than inferring from the name.

### “Modifying Externally” Does Not Mean the Caller Observes It Immediately in Every Situation

In a single thread, if two references point to the same mutable object and the method updates it successfully, subsequent reads on that same object can observe the new value. However, the conditions also include:

- The method **actually performs the mutation** and does not roll it back or change it back before the caller observes it.
- The caller holds a reference path to the modified object, **not** a different object.
- The caller reads the relevant field/state, possibly through a getter or an API exposing that state.
- Across multiple threads, **seeing** changes made by another thread also requires proper synchronization/visibility relationships according to the Java Memory Model.

Pass-by-value alone does not address concurrency rules.

## 15. Return Values, API Contracts, and Two Design Styles

Two common API styles:

### A. Mutating API — Modifying the Passed-In Object

```java
class Score {
    private int value;

    Score(int value) {
        this.value = value;
    }

    void add(int amount) {
        value += amount;
    }

    int value() {
        return value;
    }
}
```

Usage:

```java
Score score = new Score(10);
score.add(5);
System.out.println(score.value()); // 15
```

The caller still holds **the same Score object** and reads the new state. This is suitable when an object represents an entity with a distinct identity and state lifecycle.

### B. Non-mutating API — Creating or Returning a New Value

```java
record ScoreValue(int value) {
    ScoreValue added(int amount) {
        return new ScoreValue(value + amount);
    }
}
```

Usage:

```java
ScoreValue original = new ScoreValue(10);
ScoreValue changed = original.added(5);

System.out.println(original.value()); // 10
System.out.println(changed.value());  // 15
```

`ScoreValue` is a Java record (supported in Java 17+). The `added` method returns a **new record instance**; it does not change the state of the old record. This approach makes data flow clearer and reduces the risk of side effects, though one must weigh the cost and suitability of creating new values.

Both A and B use **pass-by-value**. There is no connection whereby “if a method mutates, Java switches to pass-by-reference.” The difference lies in **design conventions and implementation**.

## 16. Encapsulation: Being Able to Modify an Object Does Not Mean Allowing Every Field to Be Modified

Passing a reference creates the ability to reach the object, yet **Java member access permissions** are still enforced by the compiler. A method in another class cannot directly write to a `private` field merely because it received an object reference.

```java
class BankAccount {
    private int balance;

    BankAccount(int balance) {
        this.balance = balance;
    }

    void deposit(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("positive amount required");
        }
        balance += amount;
    }

    int balance() {
        return balance;
    }
}
```

A method outside the class can call `account.deposit(10)` when that method is accessible, but cannot write `account.balance = -100;` from a class without field access permission. This is **encapsulation**: allowing state changes according to rules that preserve invariants.

Because an object can be held by multiple aliases, every mutation must preserve **the object's business invariants**. If an arbitrary method is allowed to assign fields without checks, multiple parts of the program may read an object in an invalid state.

A clear API design should specify:

- Whether the method mutates the receiver/arguments.
- Which state is modified and what validation applies.
- Whether the return value represents the old object, a new object, or a computed value.
- Whether it retains a reference to the input for later use.
- Whether there are concurrency/ownership restrictions.

## 17. Defensive Copies to Prevent Callers from Modifying Internal State

If a class receives a mutable object from a caller and stores the reference directly, the caller might still hold an alias to internal data. That creates the risk of **representation exposure**.

Error-prone example:

```java
import java.util.List;

class UnsafeTeam {
    private final List<String> members;

    UnsafeTeam(List<String> members) {
        this.members = members;
    }

    List<String> members() {
        return members;
    }
}
```

This is a valid declaration, yet it carries design risks. If the caller creates an `ArrayList`, passes it into `new UnsafeTeam(list)`, and then calls `list.add("New")`, the team's `members` field holds **the same list object** and therefore observes the change. The getter also returns the internal list reference directly, allowing the caller to modify it indirectly.

### Runnable Example with Defensive Copies

Create the file **`DefensiveCopyDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

class Team {
    private final List<String> members;

    Team(List<String> source) {
        this.members = new ArrayList<>(source);
    }

    List<String> members() {
        return List.copyOf(members);
    }

    void add(String member) {
        members.add(member);
    }
}

public class DefensiveCopyDemo {
    public static void main(String[] args) {
        List<String> input = new ArrayList<>();
        input.add("An");

        Team team = new Team(input);

        input.add("Binh");
        System.out.println("input=" + input);
        System.out.println("team=" + team.members());

        team.add("Chi");
        System.out.println("team=" + team.members());
        System.out.println("input=" + input);
    }
}
```

```bash
javac DefensiveCopyDemo.java
java DefensiveCopyDemo
```

```text
input=[An, Binh]
team=[An]
team=[An, Chi]
input=[An, Binh]
```

**Mechanism:**

1. The constructor `Team(List<String> source)` receives a **copy of the reference** to the input list, but creates a **new ArrayList** to store in the `members` field. Therefore, the caller modifying `input` does not automatically alter the internal list.
2. The getter `members()` returns `List.copyOf(members)`, a new unmodifiable list according to its contract, instead of handing the internal mutable list directly to the caller.
3. `team.add("Chi")` mutates **Team's internal** list, not the caller's input list. Thus, in the end, Team has `[An, Chi]`, and input has `[An, Binh]`.

**Limitation:** `new ArrayList<>(source)` and `List.copyOf(...)` are **shallow copies with respect to element references**. In the example, `String` is immutable, so this is sufficiently effective. If the list contains mutable `Person` objects, you must decide whether to copy each element; merely creating another list can still leave both lists pointing to the same Person objects.

## 18. Object Ownership and Aliasing in Large-Scale Design

Java does not provide a default “single owner” for every mutable object. A mutable object can have references held by multiple different methods, fields, or threads. Therefore, **ownership conventions** are needed at the design level.

Some practical options:

1. **Allow controlled mutation:** Objects have a clear identity, such as an account or an order; methods like `deposit` and `approve` check conditions before modifying state.
2. **Do not share mutable state:** Each component creates its own copy, or returns an immutable value when possible.
3. **Do not expose internal mutable collections:** Return an unmodifiable view/copy or query methods instead of returning the original object directly.
4. **Establish clear contracts regarding input mutation:** If an API states “sorts the supplied list in place”, the caller knows the list will be modified; if an API states “returns a sorted copy”, the caller should not see the input modified.
5. **Avoid unintentional aliasing:** When assigning `a = b` or using `Arrays.fill` with a mutable object, consider whether the variables/slots are sharing the object.

These conventions do not change Java's pass-by-value rule; they determine **who is permitted to mutate an object when holding a reference to it**.

### How Do `Collections.unmodifiableList` and a Copy Differ?

An **unmodifiable view** can prevent mutation through the view itself, yet still **reflects changes to the underlying collection** made elsewhere. Conversely, creating a **snapshot/copy** at a specific point in time decouples the collection structure from subsequent changes to the source; however, mutable element objects can still be shared.

Therefore, when you want “a method not to let the caller alter internal state,” you need to consider **a copy versus a view**, and whether the elements are immutable or not. Changing only the declared `List` type is not enough to protect state.

## 19. `null`, Exceptions, and Partial Mutations

A reference parameter can hold the value `null`. When a method executes `target.deposit(5)`, if `target == null`, invoking the instance method lacks a receiver object and typically throws `NullPointerException`. There is no object to mutate via that null parameter.

```java
static void deposit(Account account, int amount) {
    if (account == null) {
        throw new IllegalArgumentException("account is required");
    }
    account.deposit(amount);
}
```

This is a method snippet using an appropriate `Account` class. Checking for null makes errors easier to understand and gives the API a clear contract. In real code, `Objects.requireNonNull(account, "account")` can be used if appropriate.

### Exceptions Do Not Automatically Undo Mutations That Have Already Occurred

Consider a method:

```java
static void updateTwo(int[] data) {
    data[0] = 10;
    throw new IllegalStateException("failed later");
}
```

If the caller passes a valid array and catches the exception, `data[0]` of the shared array **is still 10**, unless there is explicit rollback logic. Java does not provide transactional atomicity across multiple mutations merely because they reside in the same method.

Therefore, if a method updates multiple related states, consider validating before modifying, failure handling, or an appropriate transaction/rollback mechanism. Pass-by-value **does not protect the caller from side effects** that the method already performed before failing.

## 20. Concurrency: Sharing Mutable Objects Requires Dedicated Synchronization Rules

The preceding examples assumed observations within **a single thread of execution**. When multiple threads hold references to the same mutable object and read/write its state, **data races**, lost updates, or visibility issues can occur without proper synchronization according to the Java Memory Model.

```java
class Counter {
    private int count;

    void increment() {
        count++;
    }
}
```

Two threads simultaneously calling `increment()` on **the same Counter object** do not guarantee that the total increases accurately without proper synchronization; `count++` is not an atomic update at the concurrency level required by the example.

Synchronized methods, appropriate locks, or atomic types can be used depending on the problem:

```java
class SafeCounter {
    private int count;

    synchronized void increment() {
        count++;
    }

    synchronized int get() {
        return count;
    }
}
```

Here, both `increment()` and `get()` lock **the monitor of the same receiver** when invoked on an object. Other read/write paths must also follow the same protocol; `synchronized` does not automatically protect state if other code accesses it without acquiring the appropriate lock.

**In summary:** a method can modify the caller's object because both sides reference the same object; whether that change **is seen in a timely manner across threads** additionally requires concurrency mechanisms. Pass-by-value must not be interpreted as a guarantee of thread safety.

## 21. Common Reasoning Pitfalls

| Misconception | Correct Understanding |
| --- | --- |
| “Java passes objects by reference, so a method can change the caller's variable” | Java copies the **reference value**; a method can mutate the object, but cannot reassign the caller's variable via a parameter |
| “`p = new Person(...)` inside a method makes the caller switch objects” | It only reassigns the parameter `p`; if the caller wants to switch, it must receive a return result and assign it itself |
| “Calling a setter on a parameter is the same as reassigning the parameter” | A setter typically modifies **the object's state**; reassigning the parameter changes **the parameter variable's value** |
| “If an object is outside the method, the method cannot modify it” | If the method has a reference and appropriate access permissions, it can mutate that object |
| “Pass-by-value means every object is copied” | Only the **reference value** is copied, not the object itself |
| “Two variables are aliases, so reassigning one makes the other change too” | Object aliasing is not a link between two variable slots; reassigning one variable only changes that variable |
| “`final Account account` makes Account immutable” | It forbids reassigning the variable `account`; the object itself can still be mutable |
| “`String` does not change because Java uses a different passing mechanism” | It is still pass-by-value; `String` is immutable, and concatenation produces a new value and reassigns the variable |
| “An `int[]` parameter is passed by a special kind of reference” | An array is an object; the parameter receives a copy of the reference; modifying slots affects the shared array |
| “Changing `items = new ArrayList<>()` in a method clears the caller's list” | It only reassigns the local parameter and does not clear the original list object |
| “`List.copyOf` makes all element objects immutable” | The list itself is unmodifiable; mutable element objects can still be shared |
| “If a method mutates and then throws an exception, all state automatically rolls back” | There is no default rollback; mutations that have already occurred can remain |
| “A static method has no `this`, so it cannot modify objects” | A static method can still modify objects via parameters, fields, or valid references |
| “If two objects are `equals`, modifying one will modify the other” | `equals` depends on content/contract; only aliases to **the same identity** share the state of that specific object |
| “Having the same object across two threads means the new value is always visible immediately” | Visibility/concurrency requires proper synchronization; pass-by-value does not solve data races |

### Special Pitfall: Misunderstanding the Word “Reference”

Saying “the method receives a reference” is not wrong if you mean the method receives **a reference value to an object**. However, in reasoning about parameter passing, avoid the phrase “Java passes **by reference**” if it causes listeners to think **the parameter is another name for the caller's variable**.

Distinguish using these verification questions:

- If the method writes `parameter.field = x` and access permissions are valid, can the caller see the object's state change? **Yes**, if it is the same object.
- If the method writes `parameter = new Type(...)`, does the caller's variable automatically change its reference? **No**.
- If the method uses `return` to produce a new object and the caller writes `caller = method(caller)`, does the caller's variable change? **Yes**, because **the caller reassigns it**.
- If the method receives a primitive `int x` and writes `x++`, does the caller's primitive variable change? **No**.

The four questions above are sufficient to distinguish the two mechanisms that most learners confuse.

## 22. Comprehensive Practice Exercise: Predict the Output and Draw Arrows Yourself

Create the file **`ReferenceMutationTraceDemo.java`**:

```java
class Box {
    int value;

    Box(int value) {
        this.value = value;
    }
}

public class ReferenceMutationTraceDemo {
    static void change(Box first, Box second) {
        first.value += 5;
        second = new Box(20);
        second.value += 2;

        System.out.println("inside first=" + first.value);
        System.out.println("inside second=" + second.value);
    }

    public static void main(String[] args) {
        Box left = new Box(1);
        Box right = left;

        change(left, right);

        System.out.println("left=" + left.value);
        System.out.println("right=" + right.value);
        System.out.println("same=" + (left == right));
    }
}
```

```bash
javac ReferenceMutationTraceDemo.java
java ReferenceMutationTraceDemo
```

**Answer:**

```text
inside first=6
inside second=22
left=6
right=6
same=true
```

**Trace:**

```text
Step 1: before calling change
left ───┐
        ├──> Box A {value=1}
right ──┘

Step 2: upon entering change
left ───┐
right ──┤
first ──┤──> Box A {value=1}
second ─┘

Step 3: first.value += 5
left ───┐
right ──┤
first ──┤──> Box A {value=6}
second ─┘

Step 4: second = new Box(20); second.value += 2
left ───┐
right ──┤──> Box A {value=6}
first ──┘

second ─────> Box B {value=22}

Step 5: return
left ───┐
        ├──> Box A {value=6}
right ──┘

Both parameter variables first and second go out of scope.
```

There are **two Box objects** created in the program: A at the caller and B inside the method. The code creates B only once and does not “duplicate A” when passing it to both `first` and `second`. After returning, the caller still holds object A through both variables `left` and `right`.

### Self-Variation Exercises

1. If you replace `second = new Box(20)` with `second.value = 20`, what does the caller print? **Both `left` and `right` will read object A having `value=20` and then `second.value+=2` making it 22**, so the two outer lines print 22.
2. If the caller creates `Box right = new Box(10)` instead of `right = left`, `first.value+=5` will modify Box A, while `second = new Box(20)` only changes the parameter inside the method. After returning, `left.value=6` and `right.value=10`.
3. If the method replaces `second = new Box(20)` and then does `return second;`, and the caller writes `right = change(left,right);` with the return type adjusted accordingly, the caller **actively assigns** the reference to object B into `right`; in that case `left` still points to A, and `right` points to B.
4. If `Box` is an immutable value type that provides no way to modify `value`, the method cannot directly execute `first.value+=5` through the normal API. It will need to create a new value/return a result, and the caller decides whether to reassign or not.

Variations 1–4 are **reasoning exercises**, not four verbatim standalone compilable programs matching the sample file.

## 23. Checklist When a Method “Unintentionally Modifies Data”

When reading or debugging Java code with object parameters, go through these steps in order:

1. **Identify the actual object** that the caller's variable points to before the call; distinguish between the static type of the variable and the runtime object.
2. **Draw the parameter** as a separate variable inside the method receiving a **copy of the reference**; do not equate the parameter with the caller's variable.
3. **Mark all aliases**: other variables, fields, array slots, or collection entries that hold references to the object.
4. **Classify each assignment:** `parameter = new ...` reassigns the parameter; `parameter.field = ...` modifies the object; `parameter.array[i] = ...` modifies the reachable array object.
5. **Trace indirect calls:** `parameter.deposit(...)` or `parameter.getAddress().moveTo(...)` can mutate objects across multiple levels.
6. **Check the mutable/immutable contract** of the object being called; `String` differs from `StringBuilder`, and `List.of` differs from `ArrayList`.
7. **Determine which object the caller still holds after returning**; the caller does not automatically switch references just because the method reassigned its parameter.
8. **Check the return value:** if the method returns a new object, does the caller assign the result to a variable or not?
9. **Check shallow copy versus deep copy:** copying a collection does not automatically copy all mutable elements.
10. **Examine access permissions and invariants:** is the method allowed to mutate the field, or should it go through a validating API?
11. **Examine exceptions:** did any mutations occur before throwing? Is there any rollback/transaction?
12. **If multiple threads are involved:** is there a data race or missing synchronization? Do not assume visibility merely because threads hold the same reference.

---

**Remember:** Java **always uses pass-by-value**. For reference-type arguments, the method receives a **copy of the reference value**, so the caller and the method can both point to **the same mutable object**. Modifying **the state of a shared object** via a method/field/array slot can be observed by the caller; however, **reassigning the parameter** to another object does **not** reassign the caller's variable. To control side effects, distinguish between **reference variables**, **objects**, **mutability**, **aliasing**, and **API contracts**.
