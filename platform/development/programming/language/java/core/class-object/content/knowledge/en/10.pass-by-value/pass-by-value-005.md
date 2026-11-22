# Why Reassigning a Parameter Does Not Replace the Caller's Variable in Java

In Java, **every method call argument is passed by value** (*pass-by-value*). This holds true for both primitive types such as `int`, `double`, `boolean` and reference types such as `String`, `Person`, `List<String>`, or arrays.

When a method is called, **the formal parameter is a separate variable** initialized from the value of the argument. Therefore:

- **Reassigning the parameter**, such as `number = 99` or `person = new Person("Bình")`, only changes **the parameter variable inside the call**. It does not reassign the variable at the call site.
- **Mutating the object's state** through a reference parameter, such as `person.setName("Bình")`, can make the change visible to the caller if both still reference **the same object**.
- **To make the caller's variable point to a new object**, **return the new reference and let the caller perform the assignment**, for example `person = replace(person);`.
- Java **does not have pass-by-reference for variables** like `ref`/`out` parameters in some other languages. "Passing a copy of a reference" is **different from** "passing the variable itself for the function to reassign".

Simply understanding **variables**, **values in variables**, and **referenced objects** explains most of this easily misunderstood behavior.

## 1. A Call Has Two Independent Sides

Consider the method:

```java
static void change(int value) {
    value = 100;
}
```

And the call:

```java
int original = 5;
change(original);
System.out.println(original); // 5
```

At **the call site**, `original` is a local variable of type `int`, currently holding the value `5`. In **the method declaration**, `value` is a **formal parameter**, also of type `int`. When calling `change(original)`:

1. The argument expression `original` is evaluated to the value `5`.
2. The parameter `value` in that call is initialized with **a copy of the value `5`**.
3. The statement `value = 100;` reassigns the variable **`value`**, not the variable **`original`**.
4. After the method finishes, `original` still holds `5`.

You can visualize it as:

```text
Before the call:

  original (caller) = 5

During the call:

  original (caller) = 5
  value    (callee) = 5  ← value is copied

After the statement value = 100:

  original (caller) = 5
  value    (callee) = 100
```

This is a **conceptual diagram of the two variables**, not intended to describe the exact stack/register layout used by the JVM/JIT. The compiler may optimize storage details without changing Java semantics.

### A Formal Parameter Is Not an Alias for the Passed-In Variable

A parameter name such as `value` cannot "become a second name" for the variable `original`. Java takes **the value of the argument expression** to initialize the parameter; it does not transfer the caller's assignment capability to the method.

This holds true even when the two variable names are identical in two different methods:

```java
static void reset(int count) {
    count = 0;
}

// In another method:
int count = 10;
reset(count);
```

The two `count` names are spelled identically, but they reside in **two different scopes**. `reset` does not change the `count` variable in the caller.

## 2. "Pass-by-Value" with Primitive Types

With primitives, the behavior is simplest: a value such as `10`, `true`, or `3.5` is used to initialize another parameter variable.

A complete Java 17 example, saved as **`PrimitiveParameterDemo.java`**:

```java
public class PrimitiveParameterDemo {
    static void changeNumber(int number) {
        number = 99;
        System.out.println("Trong changeNumber: " + number);
    }

    static void changeFlag(boolean flag) {
        flag = false;
        System.out.println("Trong changeFlag: " + flag);
    }

    public static void main(String[] args) {
        int score = 10;
        boolean enabled = true;

        changeNumber(score);
        changeFlag(enabled);

        System.out.println("score ở main: " + score);
        System.out.println("enabled ở main: " + enabled);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 PrimitiveParameterDemo.java
java PrimitiveParameterDemo
```

**Stdout:**

```text
Trong changeNumber: 99
Trong changeFlag: false
score ở main: 10
enabled ở main: true
```

Neither `score` nor `enabled` changed in `main`. It is not because Java "automatically restores" the two variables after the call, but because **no statement has assigned to those two variables themselves**.

## 3. With Objects: Copying the **Reference Value**, Not the Object

Reference types are more complex because a reference value can lead to **a mutable object**.

Suppose:

```java
class Box {
    int value;

    Box(int value) {
        this.value = value;
    }
}
```

When calling:

```java
static void process(Box parameter) {
    // ...
}
```

with the argument:

```java
Box callerVariable = new Box(10);
process(callerVariable);
```

then upon entering `process`, the variables `parameter` and `callerVariable` are **two separate variables**, yet both hold **the reference value to the same `Box` object**.

```text
callerVariable (in caller) ──┐
                             ├──> Box #1 { value: 10 }
parameter (in process) ──────┘
```

The number `#1` is a label illustrating object identity, not a memory address. Passing the argument **does not create a hidden `new Box(...)`**, nor does it clone the `value` field.

### Two Completely Different Operations

```java
parameter.value = 20;        // A: modify object Box #1
parameter = new Box(30);     // B: reassign the parameter variable
```

- **A — Mutation:** changes the `value` field of `Box #1` to `20`. Because the caller still references `Box #1`, reading `callerVariable.value` will see `20`.
- **B — Reassignment:** creates `Box #2` and assigns the new reference to **the `parameter` variable**. The `callerVariable` variable still points to `Box #1`. If `parameter.value = 40` afterward, only `Box #2` changes, not `Box #1`.

Diagram after B:

```text
callerVariable ──────> Box #1 { value: 20 }

parameter      ──────> Box #2 { value: 30 }
```

**Rule of thumb:** `parameter = ...` changes **the parameter variable**; `parameter.field = ...` changes **the field of the object** that the parameter points to.

## 4. Complete Program: Mutate Then Reassign a Parameter

Save as **`ReferenceParameterDemo.java`**:

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

public class ReferenceParameterDemo {
    static void mutate(Box box) {
        box.setValue(20);
    }

    static void reassign(Box box) {
        box = new Box(30);
        System.out.println("Trong reassign: " + box.value());
    }

    static void mutateThenReassign(Box box) {
        box.setValue(40);
        box = new Box(50);
        box.setValue(60);
        System.out.println("Trong mutateThenReassign: " + box.value());
    }

    public static void main(String[] args) {
        Box original = new Box(10);

        mutate(original);
        System.out.println("Sau mutate: " + original.value());

        reassign(original);
        System.out.println("Sau reassign: " + original.value());

        mutateThenReassign(original);
        System.out.println("Sau mutateThenReassign: " + original.value());
    }
}
```

Commands:

```bash
javac -encoding UTF-8 ReferenceParameterDemo.java
java ReferenceParameterDemo
```

**Exact stdout:**

```text
Sau mutate: 20
Trong reassign: 30
Sau reassign: 20
Trong mutateThenReassign: 60
Sau mutateThenReassign: 40
```

Breakdown of each method:

- `mutate(original)` receives a copy of the reference to the original object. `box.setValue(20)` modifies that object, so the caller reads `20`.
- `reassign(original)` initially receives the same original reference, but then executes `box = new Box(30)`. **Only the parameter variable `box` changes**; the caller still reads `20`.
- `mutateThenReassign(original)` first modifies the original object to `40`. Next, `box` is assigned to the new object `Box(50)`, and then the new object is modified to `60`. Therefore, **inside** it prints `60`, while `original`'s original object still has `40`.

**A rule with no exceptions here:** reassigning a parameter only affects that parameter directly. The fact that the caller sees changes in some examples comes from **mutation on a shared object**, not because Java secretly uses pass-by-reference.

## 5. Why Is `Box box = callerBox` Not the Same as `Box box = new Box(...)`?

Both statements can create a **reference variable**, but only one statement creates a new object:

```java
Box first = new Box(5);
Box alias = first;
Box independent = new Box(5);
```

- `first` and `alias` reference the same object.
- `independent` points to a different object, even though their initial state is equal.
- `alias = new Box(9)` switches `alias` to a new object without making `first` "follow along".
- `first.setValue(7)` modifies `first`'s object; it does not affect `alias` if `alias` has been assigned to another object.

If the `Box` class has not overridden `equals`, you can use `==` to tell whether two references share the same identity. When two objects have equal state, `==` can still be `false`.

A method call works like creating **a temporary alias in the form of a parameter variable**, rather than copying the object's contents.

## 6. Java Does Not Pass **Reference Variables** by Reference

This is the key point about the language:

> Java is **pass-by-value**, even with reference types. A parameter receives **a copied reference value**, not "permission to directly replace the caller's variable".

Sometimes people say "Java passes objects by reference". This phrasing easily causes misunderstanding:

- **True in the sense of sharing an object:** the callee and the caller can both access the same object through their reference values.
- **False if understood as pass-by-reference of a variable:** assigning `parameter = other` cannot automatically assign `callerVariable = other`.

If a language had true pass-by-reference parameters for variables, the callee could replace the storage location of the caller's variable itself. Java **has no method parameter syntax equivalent to `ref Box` or `out Box` to do that**.

In particular, ***regardless* of the reference type**, such as `String`, `Integer`, `List`, arrays, or objects you create yourself, the rule above still holds.

## 7. "Swapping Two Variables" by Reassigning Parameters Will Fail

This is a direct consequence of parameters being separate variables:

```java
static void swap(Box left, Box right) {
    Box temporary = left;
    left = right;
    right = temporary;
}
```

Suppose the caller creates `Box first = new Box(1); Box second = new Box(2);` with an appropriate constructor. After `swap(first, second)`, `first` still points to Box(1), and `second` still points to Box(2). Only `left` and `right` are swapped locally, and then go out of scope when the method returns.

This is a **snippet**, not a standalone file. The article "Analyzing an Unsuccessful Example of Swapping Two References" is the main lesson for this: it includes a program with stdout, diagrams after each assignment, and four correct approaches (array, list, holder, returning a pair of values). In this article on parameter reassignment, swap serves only as a concise counterexample showing that the callee **cannot change the caller's variables by assigning to parameters**.

## 8. If You Want to Change the Caller's Variable: Return a New Value and Reassign

A common Java design is **return a replacement**:

```java
static Box replace(Box oldBox) {
    return new Box(oldBox.id + 1);
}
```

The call site **must perform the assignment**:

```java
Box current = new Box(1);
current = replace(current);
```

The call `replace(current)` by itself **does not change the `current` variable**. The variable changes due to the left-hand side of `=` in the **caller**'s `current = ...` statement.

### 8.1. Distinguishing Three Ways of Writing the Call

Suppose:

```java
static Box next(Box value) {
    return new Box(value.id + 1);
}
```

With `Box current = new Box(10);`:

| Caller statement | Variable `current` after the statement | Explanation |
| --- | --- | --- |
| `next(current);` | Still points to `Box(10)` | The return value is ignored |
| `Box other = next(current);` | Still points to `Box(10)` | `other` receives the new object |
| `current = next(current);` | Points to `Box(11)` | The caller explicitly reassigns the `current` variable itself |

You neither need nor should invent a way to assign the caller's variable "on its behalf" when you can design an API that **returns the result explicitly**.

### 8.2. Example Program Replacing a Reference Properly

Save as **`ReturnAndAssignDemo.java`**:

```java
class Ticket {
    final int version;

    Ticket(int version) {
        this.version = version;
    }
}

public class ReturnAndAssignDemo {
    static Ticket upgraded(Ticket input) {
        return new Ticket(input.version + 1);
    }

    public static void main(String[] args) {
        Ticket current = new Ticket(1);
        Ticket alias = current;

        upgraded(current); // Ignore the return value
        System.out.println("Sau lời gọi bỏ qua: " + current.version);

        current = upgraded(current);
        System.out.println("current: " + current.version);
        System.out.println("alias: " + alias.version);
        System.out.println("Cùng object: " + (current == alias));
    }
}
```

```bash
javac -encoding UTF-8 ReturnAndAssignDemo.java
java ReturnAndAssignDemo
```

**Stdout:**

```text
Sau lời gọi bỏ qua: 1
current: 2
alias: 1
Cùng object: false
```

This is a clear example of **reassigning the variable at the exact place where the assignment belongs**. `alias` still holds the old object; `current` has received the reference to the new object. Nothing changes on the old object merely because the function returns a new object.

## 9. Mutable and Immutable Objects: Do Not Confuse Mutation with Reassignment

### 9.1. `String` Is Immutable

`String` has no operation to directly modify the contents of an already-created string object. Methods such as `concat`, `replace`, and `toUpperCase` normally produce a `String` result (which may reuse an existing object in some cases), rather than changing the contents of the current object.

```java
static void changeText(String text) {
    text = text + " Java";
}

String message = "Hello";
changeText(message);
System.out.println(message); // Hello
```

`text = text + " Java"` assigns the reference to the resulting string **to the parameter variable `text`**. It does not reassign the `message` variable in the caller.

If you want to receive the new string:

```java
static String appendJava(String text) {
    return text + " Java";
}

// Caller:
message = appendJava(message);
```

Now `message` receives the value `"Hello Java"` because **the caller performs an assignment**, not because Java passes `message` by reference.

### 9.2. `StringBuilder` Is Mutable

`StringBuilder.append` modifies the contents of **the builder object**:

```java
static void appendText(StringBuilder builder) {
    builder.append(" Java");
}
```

If `StringBuilder message = new StringBuilder("Hello");`, then after `appendText(message)`, `message.toString()` is `"Hello Java"`. This is **mutation on an object** with a shared reference.

However:

```java
static void replaceBuilder(StringBuilder builder) {
    builder = new StringBuilder("New");
}
```

does not change the `message` variable in the caller. The constructor `new StringBuilder("New")` creates another object and assigns **the parameter variable `builder`**.

### Java 17 Example: String and StringBuilder

Save to **`StringParameterDemo.java`**:

```java
public class StringParameterDemo {
    static void reassignString(String text) {
        text = text.concat(" World");
        System.out.println("Trong String: " + text);
    }

    static void mutateBuilder(StringBuilder builder) {
        builder.append(" World");
    }

    static void reassignBuilder(StringBuilder builder) {
        builder = new StringBuilder("Other");
        System.out.println("Trong Builder: " + builder);
    }

    public static void main(String[] args) {
        String text = "Hello";
        StringBuilder builder = new StringBuilder("Hello");

        reassignString(text);
        mutateBuilder(builder);
        reassignBuilder(builder);

        System.out.println("text ở main: " + text);
        System.out.println("builder ở main: " + builder);
    }
}
```

Commands:

```bash
javac -encoding UTF-8 StringParameterDemo.java
java StringParameterDemo
```

Stdout:

```text
Trong String: Hello World
Trong Builder: Other
text ở main: Hello
builder ở main: Hello World
```

The last two values differ because **`String` is immutable and the parameter variable is reassigned**, whereas `StringBuilder` has an operation that modifies the contents of the shared object.

## 10. Arrays: Modifying Array Contents vs. Replacing the Array Reference

Java arrays are **objects**. With:

```java
int[] data = {1, 2};
```

the variable `data` has reference type `int[]`, pointing to an array object. If `data` is passed to a method:

```java
static void process(int[] numbers) {
    numbers[0] = 9;
    numbers = new int[]{7, 8};
}
```

then:

- `numbers[0] = 9` changes the contents of the shared **array object**, so the caller sees `9`.
- `numbers = new int[]{7, 8}` only reassigns **the parameter variable `numbers`**. The `data` variable still points to the old array `[9, 2]`.

### Runnable Example

Save **`ArrayParameterDemo.java`**:

```java
import java.util.Arrays;

public class ArrayParameterDemo {
    static void alter(int[] numbers) {
        numbers[0] = 9;
        numbers = new int[]{7, 8};
        numbers[1] = 6;
        System.out.println("Trong alter: " + Arrays.toString(numbers));
    }

    public static void main(String[] args) {
        int[] data = {1, 2};
        int[] alias = data;

        alter(data);

        System.out.println("Ở main: " + Arrays.toString(data));
        System.out.println("alias: " + Arrays.toString(alias));
        System.out.println("Cùng mảng: " + (data == alias));
    }
}
```

```bash
javac -encoding UTF-8 ArrayParameterDemo.java
java ArrayParameterDemo
```

Stdout:

```text
Trong alter: [7, 6]
Ở main: [9, 2]
alias: [9, 2]
Cùng mảng: true
```

This is still **pass-by-value**. Initially, `data` and `numbers` are two separate variables referencing the same array, but reassigning `numbers` does not change `data`.

### An Array Wrapper Can Help Replace the *Elements* Read by the Caller

If you want to swap elements of the caller's array, you can modify the array directly:

```java
static void swapFirstTwo(Box[] values) {
    Box temp = values[0];
    values[0] = values[1];
    values[1] = temp;
}
```

`values[0] = ...` modifies **an array element**; it does not reassign the caller's array reference variable. Because the caller holds the same array, the changed element order is visible.

However, this is **not** a direct swap of the caller's two local variables `Box first` and `Box second`; only two slots inside **the array object** are swapped.

## 11. Using a Holder: Allowing the Caller to Observe a Replaced **Reference Field**

If an API needs a "current reference" that another method is allowed to replace, you can move what needs to be updated from a **local variable** to a **field of a shared mutable object**.

For example:

```java
class Holder<T> {
    T value;

    Holder(T value) {
        this.value = value;
    }
}
```

Instead of trying to write:

```java
static void replace(Box box) {
    box = new Box(99); // Does not change the caller's Box variable
}
```

you can write:

```java
static void replace(Holder<Box> holder) {
    holder.value = new Box(99); // Modifies the field of the shared Holder object
}
```

In that case, **the caller's `holder` variable is not reassigned**, while **the `holder.value` field** of the shared object is changed. When the caller reads `holder.value`, it sees the new object.

Diagram:

```text
caller.holder   ─────┐
                     ├──> Holder #1
parameter holder ────┘         └── value ───> Box #2

replace() replaces Holder #1.value, NOT caller.holder.
```

### Java 17 Example with a Holder

Save as **`HolderParameterDemo.java`**:

```java
class Box {
    final int number;

    Box(int number) {
        this.number = number;
    }
}

class Holder<T> {
    T value;

    Holder(T value) {
        this.value = value;
    }
}

public class HolderParameterDemo {
    static void replace(Holder<Box> holder) {
        holder.value = new Box(99);
        holder = new Holder<>(new Box(123));
        System.out.println("Holder cục bộ: " + holder.value.number);
    }

    public static void main(String[] args) {
        Holder<Box> outer = new Holder<>(new Box(10));
        replace(outer);

        System.out.println("Holder ở main: " + outer.value.number);
    }
}
```

```bash
javac -encoding UTF-8 HolderParameterDemo.java
java HolderParameterDemo
```

Stdout:

```text
Holder cục bộ: 123
Holder ở main: 99
```

Explanation:

1. Initially, the two holder variables reference the same `Holder<Box>` object.
2. `holder.value = new Box(99)` modifies the field of the shared `Holder` object, so `outer.value.number` changes to `99`.
3. `holder = new Holder<>(new Box(123))` only reassigns the holder parameter, so the local print outputs `123`, while the caller's `Holder` object still has its `value` field referencing `Box(99)`.

**Do not conclude that Java has become pass-by-reference.** The mechanism has not changed: the caller and callee both hold references to a **mutable holder**; both can observe **mutations to the holder**.

### When to Use a Holder vs. When to Return?

- If a method only needs to produce a replacement, **returning** is usually clearest: `current = replace(current);`.
- If **multiple values** need to be updated or an API requires taking a mutable structure, a holder or a result record may be appropriate.
- If you want to keep the API immutable and easy to test, prefer **returning the result** rather than hiding changes inside a holder.
- When working with multithreading, a custom holder with plain fields is **not thread-safe by itself**; you need to design synchronization or use appropriate concurrency abstractions.

## 12. Reassigning a *Field* Is Different from Reassigning a *Parameter Variable*

An object can contain a field referencing another object:

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

These two statements are not synonymous:

```java
customer.address = new Address("Huế");  // Reassign Customer's FIELD
customer = new Customer(new Address("Hà Nội")); // Reassign the customer VARIABLE
```

The first statement **mutates the `Customer` object** by replacing the value of its `address` field. If the caller and callee reference that same `Customer`, the caller can see the new `customer.address`.

The second statement, if inside a method where `customer` is a **parameter**, only replaces **the `customer` parameter variable**. The caller is not forced to switch to the new `Customer`.

### Direct Method Example

```java
static void update(Customer customer) {
    customer.address = new Address("Đà Nẵng");
}

static void replace(Customer customer) {
    customer = new Customer(new Address("Huế"));
}
```

With `Customer c = new Customer(new Address("Hà Nội"));`:

- `update(c);` makes `c.address.city` become `"Đà Nẵng"`.
- `replace(c);` does **not** make `c.address.city` become `"Huế"`.

A field is a **reference storage location belonging to an object**, distinct from a **local parameter variable**. Whether an assignment has an external effect depends on **the target of the assignment**.

## 13. `null` Does Not Change the Pass-by-Value Mechanism

With:

```java
Box value = null;
```

the argument `value` has **the reference value `null`**. The method receives a copy of `null`:

```java
static void initialize(Box box) {
    if (box == null) {
        box = new Box(10);
    }
}
```

Calling `initialize(value);` does not stop `value` from being `null`. Inside the method, `box` is assigned a reference to the new object, but **the caller's `value` variable remains `null`**.

### The Right Way When You Need to Initialize a Value for the Caller

```java
static Box initialize(Box box) {
    if (box == null) {
        return new Box(10);
    }
    return box;
}

// Caller:
value = initialize(value);
```

Because the assignment is in the caller, the `value` variable receives the resulting reference.

### Another Error: Dereferencing When a Parameter Is `null`

```java
static void mutate(Box box) {
    box.setValue(10);
}
```

If you call `mutate(null)` and execute `box.setValue(10)`, the method throws **`NullPointerException`**. There is no object to mutate. Assigning `box = new Box(10)` beforehand can help the parameter variable stop being null, **but it still does not reassign the caller's variable**.

Do not use phrasing like "passing null makes Java create an object and attach it back to the caller" if the code only changes the local parameter.

## 14. `final` on a Parameter Forbids Reassignment, but Does Not Lock the Object

A parameter can be declared `final`:

```java
static void modify(final Box box) {
    box.setValue(15);        // Valid if Box is mutable and the method allows it
    // box = new Box(20);     // INVALID: cannot reassign a final parameter
}
```

Here, `final` constrains **the parameter variable `box`**. It does not turn the `Box` object into an immutable object.

Similarly at the caller:

```java
final Box value = new Box(5);
modify(value);
```

`value` cannot be assigned a new reference, yet the state of the object that `value` points to can still change if the API allows it.

| Declaration / operation | Is it valid? | Reason |
| --- | --- | --- |
| `Box b = new Box(1); b = new Box(2);` | Yes | `b` is not final |
| `final Box b = new Box(1); b = new Box(2);` | No | Reassigns a final variable |
| `final Box b = new Box(1); b.setValue(2);` | Yes if the API is mutable | Modifies the object, does not reassign b |
| `void f(final Box b) { b = null; }` | No | Reassigns a final parameter |
| `void f(final Box b) { b.setValue(3); }` | Yes if the API is mutable | The final parameter only keeps the reference fixed |

Some frameworks/teams prefer declaring parameters final to prevent accidentally reassigning a variable inside the method body. This is a useful code-control style, but **it does not make Java use pass-by-reference** and does not by itself guarantee thread safety.

## 15. Parameters Have No Special "Two-Way" Effect Due to Sharing the Same Name

Some people name a parameter the same as a variable in the caller and expect it to be updated:

```java
static void change(int score) {
    score = 100;
}

public static void main(String[] args) {
    int score = 10;
    change(score);
}
```

Having the same name **creates no link** between the two `score` variables:

- `score` in `main` is a local variable of `main`.
- `score` in `change` is a formal parameter belonging to the `change` call.
- The two names reside in different scopes. They are **not** the same variable slot according to Java's rules.

In fact, an argument does not even need to be a variable name:

```java
change(1 + 2);
change(Math.max(3, 5));
```

Both calls are valid even though `1 + 2` and `Math.max(3, 5)` are **expressions**, not a "caller's variable" to reassign. This illustrates that a method's input is **an expression's value**, not an arbitrarily updatable variable address.

## 16. Constructors Also Receive Copies of Argument Values

**Constructor** parameters follow the same pass-by-value rules as methods.

```java
class Profile {
    private String name;

    Profile(String name) {
        name = "Inside"; // Only reassigns the name parameter
    }
}
```

The snippet above does not assign to the field `this.name`. Therefore, the `name` field receives the default value `null` (assuming no other initializer), while the `name` parameter variable is only changed inside the constructor.

The correct snippet when you need to store the data in the object:

```java
class Profile {
    private String name;

    Profile(String name) {
        this.name = name; // Assigns the FIELD from the PARAMETER value
    }
}
```

**`this.name = name` is different from `name = name`.** The left-hand side is the object's field, not the parameter variable. This is a very common mistake when the field name and constructor parameter name are identical.

Even inside a constructor, assigning to the parameter **assigns to the constructor's own variable**, without modifying the caller's variable used in `new Profile(inputName)`.

## 17. Varargs Cannot Reassign the Caller's Array Variable Either

A varargs declaration:

```java
static void process(int... numbers) {
    numbers = new int[]{8, 9};
}
```

Inside the method, `numbers` is an array parameter of type `int[]`. If you call:

```java
int[] data = {1, 2};
process(data);
```

then `numbers = new int[]{8, 9}` only reassigns **the array parameter**; `data` remains the array `[1, 2]`.

If the method modifies an element:

```java
static void process(int... numbers) {
    numbers[0] = 8;
}
```

then when the caller passes **an existing array** via `process(data)`, the array mutation can be observed through `data`. On the other hand, with `process(1, 2)`, the variable-arity call is prepared with an array for the values, and there is no caller array variable whose reference needs to be replaced.

**Note:** `process((int[]) null)` passes a null array reference value; `numbers[0]` then throws `NullPointerException` if executed. This is not a reason to treat varargs as pass-by-reference.

## 18. Passing `this` as an Argument Is Still Just Passing a Reference Value

In an instance method:

```java
class Task {
    void register(Registry registry) {
        registry.add(this);
    }
}
```

`this` is **the reference to the current `Task` object**. `registry.add(this)` passes **a copy of the reference value** to `Task` into `Registry.add`. The registry can retain the reference and act on the object if allowed, but it **cannot remotely reassign the `this` keyword** of the calling method.

If the callee executes `task = new Task();` with a `Task task` parameter, the callee only replaces **the task parameter variable**, just like in the previous examples.

A method can `return this;` to return the current object itself, but once again, whether the caller assigns the result to any variable is **the caller's decision**.

**Be careful about lifecycle:** passing `this` to a registry or callback directly inside a constructor can expose an incompletely initialized object (*this escape*). This issue concerns object design safety and does not alter the pass-by-value principle.

## 19. The Difference Between Replacing a Field and Replacing the Caller's Variable

Suppose:

```java
class Session {
    String status;

    Session(String status) {
        this.status = status;
    }
}
```

There are two methods:

```java
static void setStatus(Session session) {
    session.status = "ACTIVE";
}

static void replaceSession(Session session) {
    session = new Session("ACTIVE");
}
```

With:

```java
Session current = new Session("NEW");
setStatus(current);
System.out.println(current.status); // ACTIVE

replaceSession(current);
System.out.println(current.status); // ACTIVE, still the old object
```

After `setStatus`, the existing object has had its state modified. After `replaceSession`, the existing object **is not replaced by the new object**, so the print statement still reflects the old object whose status is `ACTIVE`.

To see the difference more clearly, if you start with a new `current` with `"NEW"` and **only** call `replaceSession(current)`, the value of `current.status` remains `"NEW"`.

### When Using a Mutable Reference Holder Field

If `class SessionStore { Session current; }` and the callee receives `SessionStore store` and writes `store.current = new Session("ACTIVE");`, the caller holding **the same `SessionStore` object** will be able to read the new `current` field.

**However, this is still not reassigning the `store` variable in the caller.** What gets mutated is **a field of a shared object**. Identify **the left-hand side of the assignment** precisely:

- `parameter = value;` → parameter variable.
- `parameter.field = value;` → field of the referenced object.
- `parameter.array[i] = value;` → element of the referenced array.
- `callerVariable = method(...);` → caller's variable, assigned by the statement in the caller itself.

## 20. Rules for Method Return Values

A return value **does not automatically assign itself to the argument**:

```java
static int doubleValue(int number) {
    number *= 2;
    return number;
}
```

With:

```java
int x = 5;
doubleValue(x);
System.out.println(x); // 5
```

`doubleValue(x)` computes the result `10`, but the caller **ignores** the return value. `x` does not change.

If you want `x` to change:

```java
x = doubleValue(x);
System.out.println(x); // 10
```

**Two actions must be separated:**

1. Inside the method, `return expression;` provides a **result value**.
2. At the caller, the assignment `x = ...` takes that result value to **change the variable x**.

`return` has no authority to "guess" which variable the caller wants to modify. A single result can be assigned to different variables, used in an expression, or ignored.

## 21. Changing Multiple Values: Use a Result Type, Do Not Simulate Pass-by-Reference

If a computation needs to return multiple values, Java offers several clear approaches:

- Return a **result object** containing the required fields.
- Use an immutable `record` in Java 17 to group the returned values.
- Return an appropriate collection or array when the elements share the same meaning and are controlled.
- Use a mutable holder when the API genuinely requires **an object carrying updatable state**.

Example of returning two new numbers with a `record`:

```java
record Pair(int left, int right) {
}
```

```java
static Pair swapValues(int left, int right) {
    return new Pair(right, left);
}
```

Caller:

```java
int a = 1;
int b = 2;

Pair swapped = swapValues(a, b);
a = swapped.left();
b = swapped.right();
```

This approach **does not directly modify the caller's arguments**. The caller receives the result object containing the needed values and **updates the two variables `a`/`b` itself**.

### Java 17 Program with a Result Record

Save **`ReturnPairDemo.java`**:

```java
record Pair(int left, int right) {
}

public class ReturnPairDemo {
    static Pair swapValues(int left, int right) {
        return new Pair(right, left);
    }

    public static void main(String[] args) {
        int first = 10;
        int second = 20;

        Pair result = swapValues(first, second);
        System.out.println("Trước gán: " + first + ", " + second);

        first = result.left();
        second = result.right();
        System.out.println("Sau gán: " + first + ", " + second);
    }
}
```

```bash
javac -encoding UTF-8 ReturnPairDemo.java
java ReturnPairDemo
```

**Stdout:**

```text
Trước gán: 10, 20
Sau gán: 20, 10
```

`record Pair` in Java 17 creates a type holding two components with the accessors `left()` and `right()`. Swapping **the caller's variables** still resides in `main` and is expressed by two explicit assignment statements.

## 22. Cases Commonly Misinterpreted

| Example | Actual effect | Does it change the caller's variable? |
| --- | --- | --- |
| `void f(int x) { x = 9; }` | Assigns the primitive parameter variable | **No** |
| `void f(Box x) { x = new Box(9); }` | Assigns the reference parameter variable | **No** |
| `void f(Box x) { x.setValue(9); }` | Mutates the object pointed to by the parameter | Does not reassign the caller's variable; the caller's object **can change** |
| `void f(int[] x) { x[0] = 9; }` | Modifies an element of the shared array | Does not reassign the caller's array variable; the element **can change** |
| `void f(int[] x) { x = new int[]{9}; }` | Assigns the parameter to a new array | **No** |
| `void f(String x) { x += "a"; }` | Assigns the parameter to the resulting string | **No** |
| `void f(StringBuilder x) { x.append("a"); }` | Modifies the shared builder | Does not reassign the caller's variable; the builder's contents **can change** |
| `void f(Holder<Box> x) { x.value = new Box(9); }` | Assigns a **field** of the shared holder | The caller's holder variable does not change; the field **can change** |
| `Box f(Box x) { return new Box(9); }` | Returns a new reference | **No**, if the caller ignores the result |
| `caller = f(caller);` | Caller assigns the returned value itself | **Yes**, due to the assignment in the caller |
| `void f(final Box x) { x.setValue(9); }` | Mutates the object through a final parameter | The caller's variable does not change; the object **can change** |
| `void f(final Box x) { x = new Box(9); }` | Invalid | **Compile-time error** |

**Be careful with how the question is asked:** "Does it make the caller see something different?" is different from "Does it reassign the caller's variable?". Mutation can make the caller see a new state **without ever reassigning the caller's variable**.

## 23. Identifying Bugs with Before/After Diagrams

For complex code snippets, use a four-step process:

1. **List the variables** in the caller and the parameters in the callee; mark them as **distinct variables**.
2. **Draw the initial references**: which variable points to which object; label objects A/B instead of guessing addresses.
3. **Read each assignment by its exact left-hand side**: if it is `parameter = ...`, modify the callee's variable; if it is `parameter.field = ...`, modify the object; if it is `caller = method(...)`, modify the caller's variable.
4. **When exiting the method**, discard the call's local variables; keep any mutations applied to shared objects and any values explicitly received by the caller.

Example:

```java
static void execute(Box item) {
    item.setValue(2);
    item = new Box(3);
    item.setValue(4);
}
```

Caller:

```java
Box box = new Box(1);
Box alias = box;
execute(box);
```

Diagram:

```text
1. Initially:
box  ─┐
alias ─┴──> Box A { value: 1 }

2. Entering execute:
box   ────┐
alias ────┼──> Box A { value: 1 }
item  ────┘

3. item.setValue(2):
box   ────┐
alias ────┼──> Box A { value: 2 }
item  ────┘

4. item = new Box(3):
box   ────┐
alias ────┴──> Box A { value: 2 }
item  ─────────> Box B { value: 3 }

5. item.setValue(4):
box   ────┐
alias ────┴──> Box A { value: 2 }
item  ─────────> Box B { value: 4 }

6. After execute finishes:
box   ────┐
alias ────┴──> Box A { value: 2 }
```

At step 6, both `box.value()` and `alias.value()` are `2`. `Box B` does not automatically "move into" the `box` variable because there has never been any assignment to the caller's `box`.

This is a more reliable explanation technique than vaguely saying "Java passes addresses" or "Java passes copies of objects".

## 24. Relation to Getters, Setters, and Encapsulation

An API may disallow modifying fields directly:

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
```

With:

```java
Account account = new Account(100);
addMoney(account);
```

and:

```java
static void addMoney(Account a) {
    a.deposit(50);
}
```

the caller will see `account.balance() == 150`. This **does not prove that `addMoney` has permission to reassign the `account` variable in the caller**. It merely calls a public/package-accessible instance method that alters the object's state.

Conversely, if:

```java
static void replaceAccount(Account a) {
    a = new Account(999);
}
```

then the caller still retains the original object.

**Encapsulation** controls which state changes are permitted through the API, yet the argument value-copying mechanism itself remains unchanged.

## 25. Concurrency and Shared Objects: Essential Scope of Understanding

When multiple threads share references to a mutable object, mutation operations can cause a **race condition** without synchronization. However, that is a **different issue from** pass-by-value.

For example:

- Two threads both hold references to the same `Counter`.
- One thread executes `counter.increment()`, while the other reads the state.
- One thread reassigning its **local parameter variable** `counter = new Counter()` does not change the other thread's variable.
- Having both modify **the same Counter object** may require `synchronized`, atomic types, or an immutability/snapshot strategy.

`AtomicReference<T>` is an object with an API that allows **replacing the reference value stored in it with appropriate concurrency semantics**, rather than changing how Java passes arguments:

```java
java.util.concurrent.atomic.AtomicReference<Box> holder =
        new java.util.concurrent.atomic.AtomicReference<>(new Box(1));
```

A method that receives an `AtomicReference<Box> holder` parameter and calls `holder.set(new Box(2))` has **changed the state of the shared AtomicReference object**. The caller's `holder` reference variable is not reassigned. At the same time, `AtomicReference` only provides guarantees about atomic operations on **the held reference value**; it does not automatically make all fields inside the `Box` object thread-safe.

**There is no need to use `AtomicReference` just to "make Java pass by reference"** in single-threaded code. Prefer a return value or an easy-to-understand result class.

## 26. Common Pitfalls and How to Fix Them

| Symptom | Cause | Fix |
| --- | --- | --- |
| `change(x)` leaves `x` unchanged | The method only assigns its own parameter | Return the new value and call `x = change(x)` |
| `replace(obj)` creates a new object, yet the caller's variable keeps the old object | `obj = new ...` inside the method only changes the parameter | Return the new object and assign it in the caller |
| `swap(a, b)` does not swap the two variables | Only swaps the parameter copies of references/values | Use a return value, a record, or swap elements inside a mutable structure |
| `list.add(...)` from a method affects the list in the caller | The same list object is shared via reference | This is mutation, not reassignment |
| `list = new ArrayList<>()` inside a method does not replace the caller's list | Reassigns the list parameter | Return a new list or update a holder object if the contract requires it |
| `String` does not change after `text += "!"` in a method | `String` is immutable; the parameter variable receives a different string | `return text + "!"` and assign it in the caller |
| `StringBuilder` changes after `append` | `append` mutates the shared builder | If independence is needed, copy the builder or design it to be immutable |
| `parameter = null`, yet the caller still keeps the object | Only the parameter variable is assigned `null` | If the caller should no longer hold a reference, the caller must assign `null` itself |
| `final Parameter` fails when reassigned | A final parameter cannot be reassigned | Avoid reassigning it or remove `final` if there is a valid reason |
| `final Box` still allows the object to be modified | Making the variable final does not make `Box` immutable | Design immutable fields/API or use defensive copies |
| Assigning `customer = new Customer(...)` instead of `customer.address = ...` | Mistaken assignment target | Determine whether the caller wants to replace the object or modify a field |
| Passing `this` and expecting the method to change `this` at the call site | Java copies the reference value of `this` | Return the result or call a valid mutating API |
| Creating a wrapper/holder and thinking this is pass-by-reference in Java | Only the wrapper's state is changed | Call it accurately a shared mutable holder |
| Calling `method(expr)` and expecting the method to modify a variable inside expr | The method receives **the expression's value** | Have the caller update the variable itself based on the result |

## 27. Self-Check Exercises with Answers

### Exercise 1: Does a Primitive Parameter Change the Caller's Variable?

```java
static void increase(int n) {
    n++;
}

int value = 5;
increase(value);
System.out.println(value);
```

**Answer:** prints `5`. `n++` updates the parameter variable, not `value` in the caller.

### Exercise 2: Two Variables Point to the Same Object—What Does the Method Do?

```java
static void process(Box b) {
    b.setValue(7);
    b = new Box(9);
}

Box first = new Box(1);
Box alias = first;
process(first);
System.out.println(first.value());
System.out.println(alias.value());
```

**Answer:** prints `7` and `7`. Both caller variables still reference the old Box that was set to `7`. The assignment `b = new Box(9)` only reassigns the parameter.

### Exercise 3: When Does the Caller Receive a New Object?

```java
static Box create(Box oldValue) {
    return new Box(oldValue.value() + 1);
}

Box box = new Box(10);
create(box);
System.out.println(box.value());
box = create(box);
System.out.println(box.value());
```

**Answer:** `10`, then `11`. The first call does not use the return value; the second call has an assignment in the caller.

### Exercise 4: Why Does Assigning `null` Not Clear the Caller's Object?

```java
static void clear(Box box) {
    box = null;
}

Box caller = new Box(3);
clear(caller);
System.out.println(caller.value());
```

**Answer:** prints `3`. The method only sets the parameter variable `box` to `null`; the `caller` reference does not change.

### Exercise 5: Reassigning a Field or a Parameter?

```java
class Item {
    String label;

    Item(String label) {
        this.label = label;
    }
}

class Holder {
    Item item;

    Holder(Item item) {
        this.item = item;
    }
}

static void change(Holder h) {
    h.item = new Item("New");
    h = new Holder(new Item("Other"));
}
```

With:

```java
Holder caller = new Holder(new Item("Old"));
change(caller);
System.out.println(caller.item.label);
```

**Answer:** prints `New`. The assignment `h.item = ...` replaces the field of the shared Holder; `h = new Holder(...)` only replaces the parameter.

### Exercise 6: Does Swapping with a Record Update Both Variables Automatically?

```java
record Pair(int x, int y) {
}

static Pair reverse(int x, int y) {
    return new Pair(y, x);
}
```

`reverse(a, b);` does **not** modify `a` or `b`. To update them:

```java
Pair result = reverse(a, b);
a = result.x();
b = result.y();
```

**Answer:** the variable updates occur at **the two assignment lines in the caller**, not because parameters `x`/`y` automatically link to `a`/`b`.

### Exercise 7: Can an Array Be Modified Without Changing the Array Variable?

```java
static void process(int[] values) {
    values[0] = 8;
    values = new int[]{9};
}

int[] data = {1, 2};
process(data);
System.out.println(java.util.Arrays.toString(data));
```

**Answer:** `[8, 2]`. The old array has its first element modified. The `data` variable does not point to the new array `{9}`.

### Exercise 8: Does `final` Prevent Mutation?

```java
static void update(final Box box) {
    box.setValue(2);
    // box = new Box(3);
}
```

**Answer:** `box.setValue(2)` can be valid and modifies the shared object. The reassignment line `box = new Box(3)` fails because the parameter is final.

## 28. Checklist When Analyzing Why the Caller Does Not Change

1. **Mark the caller variable name** that you expect to change (for example, `current`).
2. **Read the formal parameter** in the method (for example, `Box parameter`): this is a **different variable**.
3. **Identify the argument type:** primitives have their value copied; references copy **the reference value**.
4. **Draw the aliases at the start of the call**: which variables point to the same object?
5. **Look precisely at the left-hand side of `=`**: is it `parameter`, `parameter.field`, `array[i]`, or a variable in the caller?
6. **If `parameter = new ...`**, only the parameter switches objects; do not infer that the caller's variable also changes.
7. **If `parameter.method()`**, read the implementation/contract to know whether it is a mutation or returns a new object.
8. **If you want to change the caller's variable**, the method needs to return a result so the caller can write `caller = method(caller)` itself, or use a shared holder with a clear contract.
9. **If `final` is present**, remember it restricts reassigning the modified variable, and does not automatically lock the object.
10. **If the parameter is initially `null`**, a `parameter = new ...` statement inside the method does not automatically initialize the caller's null variable.
11. **If it is an array/collection**, distinguish modifying **elements/state** from reassigning **the array/list variable**.
12. **If using a static/shared field**, a field mutation can be seen from elsewhere, but that is not pass-by-reference of the caller's variable.
13. **If multiple threads are involved**, add separate synchronization and visibility analysis; do not use concurrency to misexplain parameter-passing rules.
14. **Verify with concrete results**: print the caller's variable, print the parameter variable in the method, print identities when needed, and cross-check with the reference diagram.

## Key Takeaways

- Java **only passes arguments by value**. A formal parameter is always a **separate variable** of the call, initialized from the value of the argument expression.
- With primitives, the method receives **a copy of the primitive value**. With objects, the method receives **a copy of the reference value**, not a copy of the entire object.
- **`parameter = ...` does not reassign `callerVariable`**; the two variables are independent even if they initially point to the same object.
- **`parameter.field = ...` or a mutator call** can modify **the shared object**, causing the caller to see the state change **while the caller's variable still keeps the same reference**.
- Assigning `null`, creating a new object, or swapping two parameters **does not automatically change the caller's variables**.
- Need to change the caller's variable? **Return the new value and assign it in the caller**: `current = transform(current);`. Need to modify shared state? Design an appropriate mutator API or holder and clearly state the side effect.
- **Distinguish three things** when reading code: *the parameter variable*, *the caller's variable*, and *the referenced object*. When these three are separated properly, the phenomenon that "reassigning a parameter does not change the caller's variable" will no longer be confusing.
