# Instance Methods and Receiver Objects in Java

## 1. What Are Instance Methods Used For?

In Java, an **instance method** describes behavior associated with a **specific object**. For example, two bank accounts both support the `deposit` behavior, but the balance of whichever account the method is called on is modified.

```java
Account first = new Account("Mai", 100);
Account second = new Account("Nam", 30);

first.deposit(20);  // Affects first: 100 -> 120.
second.deposit(5);  // Affects second: 30 -> 35.
```

The snippet above illustrates a call, assuming `Account` has a corresponding constructor and `deposit` method; **it is not yet a standalone program**. The key point is not the method name `deposit`, but **`first` or `second` before the dot**. The object chosen to receive this call is called the **receiver object** (*receiver*).

With the syntax `first.deposit(20)`:

- `first` is the **receiver expression**. It is evaluated to obtain a reference.
- The object that this reference points to is the **receiver object** of the method call.
- `deposit` is the **method name**.
- `20` is the **argument** passed to the method's parameter.
- The method executes based on **the state of the receiver** and the arguments passed.

**Important distinction:** a **reference variable** like `first` is not the object itself. Two different variables can refer to the same receiver object; a variable can also receive a new reference later.

## 2. Syntax for Declaring and Calling an Instance Method

The general form of a method declaration with a body:

```java
[modifiers] ReturnType methodName(ParameterType parameter, ...) {
    // Statements
}
```

This is **syntax notation**; it is not compiled literally with the square brackets and `...`.

A practical example:

```java
class Counter {
    private int value;

    void increment() {
        value++;
    }

    int getValue() {
        return value;
    }
}
```

In the `Counter` class:

- `value` is an **instance field**, meaning each `Counter` has its own separate value.
- `increment()` is an **instance method** with a `void` return type that modifies `value`.
- `getValue()` is an **instance method** returning `int` that observes `value`.
- Both methods **do not have the `static` keyword**, so they require an instance context when called.
- Inside an instance method body, the name `value` is understood as the field belonging to the object receiving the call; it can be written explicitly as `this.value`.

Common way to call them:

```java
Counter counter = new Counter();
counter.increment();
int current = counter.getValue();
```

This is a code fragment meant to be placed inside a method. `counter.increment()` uses `counter` to identify the receiver. `counter.getValue()` returns the value on **that same receiver**. If a second `Counter` is created, the `value` state of the two instances is independent.

Quick comparison table:

| Expression | Characteristics |
| --- | --- |
| `object.method(args)` | Instance method call via a receiver expression; the actual object is determined at runtime. |
| `this.method(args)` | Calls a method on the **current instance** in an appropriate instance context. |
| `method(args)` | A call without an explicit receiver; inside an instance method, this may be equivalent to calling on `this`, depending on which name is resolved. |
| `ClassName.staticMethod(args)` | Calls a **static method**, which is associated with the class and does not require a receiver object. |
| `super.method(args)` | Inside a subclass, requests the appropriate implementation from the superclass according to Java rules; still associated with the `this` object being constructed/executed. |

Not every method called with a dot is an instance method: Java allows writing a static method call through a reference expression, yet it is still a **static invocation**; the recommended style is `ClassName.staticMethod()` to avoid confusion about the receiver.

## 3. Complete Runnable Example: The Receiver Determines Which Object Is Modified

Create the file **`ReceiverDemo.java`** with the following full code (Java 17+):

```java
class Account {
    private final String owner;
    private int balance;

    Account(String owner, int openingBalance) {
        if (owner == null || owner.isBlank()) {
            throw new IllegalArgumentException("Owner is required");
        }
        if (openingBalance < 0) {
            throw new IllegalArgumentException("Opening balance cannot be negative");
        }
        this.owner = owner;
        this.balance = openingBalance;
    }

    void deposit(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Amount must be positive");
        }
        balance += amount;
    }

    boolean withdraw(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Amount must be positive");
        }
        if (amount > balance) {
            return false;
        }
        balance -= amount;
        return true;
    }

    void transferTo(Account target, int amount) {
        if (target == null) {
            throw new IllegalArgumentException("Target is required");
        }
        if (this.withdraw(amount)) {
            target.deposit(amount);
        }
    }

    String summary() {
        return owner + ": " + balance;
    }
}

public class ReceiverDemo {
    public static void main(String[] args) {
        Account mai = new Account("Mai", 100);
        Account nam = new Account("Nam", 30);
        Account alias = mai;

        mai.deposit(20);
        alias.withdraw(15);
        mai.transferTo(nam, 25);

        System.out.println(mai.summary());
        System.out.println(nam.summary());
        System.out.println(mai == alias);
        System.out.println(mai == nam);
    }
}
```

Compile and run in the directory containing the file:

```bash
javac ReceiverDemo.java
java ReceiverDemo
```

**Exact output:**

```text
Mai: 80
Nam: 55
true
false
```

Call-by-call explanation:

1. `new Account("Mai", 100)` and `new Account("Nam", 30)` create **two different objects**.
2. `mai.deposit(20)` sets the "Mai" account as the receiver, so Mai's balance becomes `120`; Nam's account remains `30`.
3. `alias = mai` only **copies the reference**. `alias.withdraw(15)` receives **the same Mai object** as the receiver, reducing Mai's balance to `105`. It does not create a third account.
4. `mai.transferTo(nam, 25)` calls the method with **Mai** as the receiver. Inside the method, `this.withdraw(25)` withdraws `25` from Mai, while `target.deposit(25)` deposits `25` into Nam. Therefore, the two final balances are `80` and `55`.
5. `mai == alias` is `true` because both variables point to the same object; `mai == nam` is `false` because they point to two different objects.

### Reference Diagram

```text
Variable mai ───────┐
                    ├──> Account {owner="Mai", balance=80}
Variable alias ─────┘

Variable nam ───────────> Account {owner="Nam", balance=55}
```

The methods `deposit`, `withdraw`, `transferTo`, and `summary` are the same **method definitions** in the `Account` class. Different calls use different receivers; Java does not create a separate copy of the method code for each object.

An important design implication: **a method modifies the state of the "object receiving the call", not of the "variable used to make the call"**. A variable is merely a path to the object, so calling through `alias` still affects `mai`.

> This example is meant to explain the receiver and state; it does not model a real-world banking transaction. If a transfer must guarantee atomicity, concurrency, durability, and intermediate failure handling, separate mechanisms are required. Those mechanisms do not come automatically simply because the logic is placed inside an instance method.

## 4. `this` Is a Reference to the Object Receiving the Call

Inside an **instance method body**, the `this` keyword represents the **current object** on which the call is executing. The same method body can receive different `this` values across different calls.

```java
class Greeter {
    private final String name;

    Greeter(String name) {
        this.name = name;
    }

    String greeting() {
        return "Xin chào " + this.name;
    }

    void printGreeting() {
        System.out.println(this.greeting());
    }
}
```

In `greeting()`, `this.name` is the receiver's `name` field. In `printGreeting()`, `this.greeting()` calls another instance method on **the same object**. If you write `greeting()` without `this.`, when the name resolves appropriately, Java also implicitly uses the current receiver.

### When Should `this` Be Written Explicitly?

The most obvious case is when a parameter has the same name as a field:

```java
class Book {
    private String title;

    Book(String title) {
        this.title = title;
    }

    void rename(String title) {
        this.title = title;
    }

    String title() {
        return this.title;
    }
}
```

`this.title` is the receiver's field, while `title` on the right-hand side in the constructor/method is the parameter. If you write `title = title;` here, both `title` names refer to the parameter, failing to update the field as intended.

Using `this.` throughout all code is a style choice; what is mandatory is distinguishing them when a local/parameter name shadows a field.

### `this` Only Exists in an Appropriate Instance Context

```java
class Settings {
    private int version = 1;

    int readVersion() {
        return this.version; // Valid: instance method.
    }

    static String category() {
        return "settings";   // Static methods do not have this.
    }

    // static int invalid() {
    //     return this.version; // Compilation ERROR if uncommented.
    // }
}
```

A static method is not passed a receiver object and cannot use `this` or directly access an instance field as if an object already existed. If a static method needs to read instance data, it must receive or create a specific reference:

```java
static int read(Settings settings) {
    return settings.readVersion();
}
```

This method snippet is placed **inside a class** that can reference `Settings`. `settings` is the receiver of `readVersion()`; the `read` method remains static.

**Do not confuse `this.method()` with `this(...)`:** the `this(...)` form is a call to another constructor of the same class inside a constructor, following its own placement rules; it is not a regular instance method call.

## 5. The Receiver Can Be an Expression, Not Just a Variable Name

The following calls can be valid if the corresponding classes, methods, and return types are declared:

```java
account.deposit(10);            // Reference variable as the receiver expression.
getAccount().deposit(10);       // Method result as the receiver expression.
accounts[0].deposit(10);        // Array element as the receiver expression.
new Account("An", 10).deposit(5); // Newly created object as the receiver.
this.account.deposit(10);       // Field of the current instance as the receiver.
```

These are **illustrative snippets**, not standalone runnable programs; they assume `getAccount()` returns an `Account` and the relevant variables exist. The receiver expression is **evaluated** to obtain a reference value, and then Java calls the method on the resulting object.

### Complete Example: Chained Calls and Receivers Changing by Expression

Create the file **`FluentReceiverDemo.java`**:

```java
class Lamp {
    private final String label;
    private boolean on;

    Lamp(String label) {
        this.label = label;
    }

    Lamp turnOn() {
        this.on = true;
        return this;
    }

    Lamp turnOff() {
        this.on = false;
        return this;
    }

    String status() {
        return label + ": " + (on ? "ON" : "OFF");
    }
}

public class FluentReceiverDemo {
    public static void main(String[] args) {
        Lamp desk = new Lamp("Desk");
        Lamp sameLamp = desk.turnOn().turnOff().turnOn();

        System.out.println(desk.status());
        System.out.println(sameLamp.status());
        System.out.println(desk == sameLamp);
        System.out.println(new Lamp("Hall").turnOn().status());
    }
}
```

Run:

```bash
javac FluentReceiverDemo.java
java FluentReceiverDemo
```

```text
Desk: ON
Desk: ON
true
Hall: ON
```

`desk.turnOn()` changes the state of `desk` and **returns `this`** (the same object), so the `turnOff()` call after the dot continues to receive the same object. The `status()` method at the end of the chain is still called on the reference result of the expression immediately before it. `sameLamp == desk` is `true` because the call chain does not create a new Lamp on its own. On the last line, `new Lamp("Hall")` actually creates **a different object** and continues calling methods on it.

This API style is commonly called a **fluent interface**; note that not every method returning the class type necessarily returns `this`. It can return a new instance, a child object, or `null`. To understand the receiver of the next link in the chain, you must look at the **actual return value** of the previous link.

## 6. Reference Variables, Receiver Objects, and State

Calling a method does not "permanently bind" the method to the variable name used in the syntax.

```java
Account first = new Account("A", 10);
Account second = new Account("B", 10);

Account selected = first;
selected.deposit(5);  // Receiver is object A.

selected = second;
selected.deposit(7);  // Receiver is now object B.
```

This is an illustrative code snippet using the `Account` class from the main example. `selected` still has the **static type `Account`**, but the reference value held in the variable has changed. Therefore, the object receiving the first call differs from the one receiving the second call. After these calls, A's balance is `15` and B's is `17`.

Between two reference variables, assignment does not copy the object; it copies the **reference value**. For immutable objects such as `String`, a method may create a new value instead of modifying the old object; this difference comes from **method behavior and class design**, not from how the receiver is determined.

### An Instance Method Can Call Methods on Another Object

In the `Account.transferTo` example:

```java
void transferTo(Account target, int amount) {
    if (target == null) {
        throw new IllegalArgumentException("Target is required");
    }
    if (this.withdraw(amount)) {
        target.deposit(amount);
    }
}
```

The same method body contains **two different receivers**:

- `this.withdraw(amount)`: the receiver is **the account currently executing `transferTo`**.
- `target.deposit(amount)`: the receiver is **the account referenced by the `target` parameter**.

Therefore, one should not say "every statement in an instance method operates on `this`." An instance method has access to `this`, but it can also create or hold references to other objects and call methods on them.

## 7. A `null` Receiver: Error Occurs at Instance Method Call Time

A variable with a valid class type can still hold the value `null`:

```java
Account account = null;
// account.deposit(10); // If executed: NullPointerException.
```

`null` **does not point to any object**. Therefore, there is no receiver object on which to execute the instance method `deposit`. When a program attempts to call an instance method through `null`, Java throws a `NullPointerException`, except in special forms that are not instance invocations.

### Runnable Example, Explicitly Catching the Exception

File **`NullReceiverDemo.java`**:

```java
class Clock {
    void ring() {
        System.out.println("ring");
    }
}

public class NullReceiverDemo {
    public static void main(String[] args) {
        Clock clock = null;

        try {
            clock.ring();
        } catch (NullPointerException ex) {
            System.out.println("receiver is null");
        }

        clock = new Clock();
        clock.ring();
    }
}
```

```bash
javac NullReceiverDemo.java
java NullReceiverDemo
```

```text
receiver is null
ring
```

The compiler accepts `clock.ring()` because the variable has type `Clock` and the class declares `ring()`, but at runtime the receiver is `null`, so an error occurs. After `clock` is assigned a `new Clock()` reference, the call has a valid receiver object.

How to prevent this depends on the API contract: reject `null` inputs using `Objects.requireNonNull` or explicit checks; ensure reference fields are initialized; return a fallback value when appropriate; or design the API so an absent state cannot occur unexpectedly. Java 17 **does not have a null-safe access operator `?.`** like some other languages.

### The Receiver Is Evaluated Before Arguments, but the `null` Check Must Be Understood Correctly

When calling `receiver.method(argumentExpression)`, Java evaluates **the expression identifying the receiver first**, then evaluates the argument expressions from left to right, and finally performs the invocation according to runtime rules. In the case of calling an instance method on `null`, **the argument expression can still be evaluated before `NullPointerException` is thrown at the invocation step**.

A separate runnable example to observe this:

```java
class Printer {
    void print(int n) {
        System.out.println("number=" + n);
    }
}

public class EvaluationOrderDemo {
    static Printer findPrinter() {
        System.out.println("receiver expression");
        return null;
    }

    static int calculateArgument() {
        System.out.println("argument expression");
        return 42;
    }

    public static void main(String[] args) {
        try {
            findPrinter().print(calculateArgument());
        } catch (NullPointerException ex) {
            System.out.println("call failed");
        }
    }
}
```

Save as **`EvaluationOrderDemo.java`**, then:

```bash
javac EvaluationOrderDemo.java
java EvaluationOrderDemo
```

```text
receiver expression
argument expression
call failed
```

The program evaluates `findPrinter()` and gets `null`, continues by evaluating `calculateArgument()`, and then fails when attempting to invoke the instance method. This order matters if an argument expression has side effects. Do not assume that just because the receiver is `null`, the arguments definitely have not been evaluated.

## 8. The Method's Declaring Class, Reference Type, and Actual Receiver Type

With inheritance, it is necessary to distinguish between the **static type of the variable/expression** and the **runtime class of the object**.

```java
Animal animal = new Dog();
```

The variable `animal` has the static type `Animal`, but the created object belongs to the `Dog` class. When calling an overridable instance method, Java selects the implementation matching the **actual class of the receiver** via **dynamic dispatch**.

Create the file **`DynamicReceiverDemo.java`**:

```java
class Animal {
    String speak() {
        return "some sound";
    }

    String kind() {
        return "animal";
    }
}

class Dog extends Animal {
    @Override
    String speak() {
        return "woof";
    }

    String fetch() {
        return "ball";
    }
}

public class DynamicReceiverDemo {
    static String describe(Animal animal) {
        return "Animal overload";
    }

    static String describe(Dog dog) {
        return "Dog overload";
    }

    public static void main(String[] args) {
        Animal general = new Dog();
        Dog specific = new Dog();

        System.out.println(general.speak());
        System.out.println(general.kind());
        System.out.println(specific.fetch());
        System.out.println(describe(general));
        System.out.println(describe(specific));
    }
}
```

Compile and run:

```bash
javac DynamicReceiverDemo.java
java DynamicReceiverDemo
```

```text
woof
animal
ball
Animal overload
Dog overload
```

Line-by-line analysis:

1. `general.speak()` invokes the `Dog.speak()` implementation and therefore returns `woof`, because **the actual object is a Dog** and this method has been overridden.
2. `general.kind()` runs the implementation inherited from `Animal` since `Dog` does not override `kind()`; the result is `animal`.
3. `specific.fetch()` is valid because the variable has the static type `Dog`, which declares the `fetch()` method.
4. `describe(general)` selects the overload taking `Animal` at **compile time**. Even though the referenced object is a `Dog`, the overload does not automatically switch to `describe(Dog)`.
5. `describe(specific)` selects the overload taking `Dog` because the static type of the argument is `Dog`.

Writing `general.fetch()` **will not compile**, because the static type `Animal` does not provide `fetch()`, even though the runtime object is a `Dog`.

### Overloading and Overriding Are Not the Same

| Mechanism | What Does It Depend On? | Implications for the Receiver |
| --- | --- | --- |
| **Overloading** | The method name, applicable signatures, and the **static type** of the expression/arguments at compile time | Selects the appropriate overload signature before runtime. |
| **Overriding** | The actual class of the receiver when calling an overridable instance method | A subclass implementation can run even when the variable has a superclass type. |
| **Static method hiding** | Static resolution rules for `static` methods | Not dynamic dispatch based on the receiver object. |
| **Private method** | Not overridden under normal inheritance mechanisms | A method with the same name in a subclass does not override a private method of the superclass. |

`final` methods cannot be overridden; static methods are also not overridden in the sense of runtime polymorphism. Therefore, the statement "every `object.method()` call selects the method using runtime polymorphism" is too broad: you have to check **which method is selected at compile time, whether it can be overridden, and the actual type of the object**.

### `super.method()` in a Subclass

If a subclass needs to call the superclass's implementation instead of the current override, it can use `super` in a valid context:

```java
class BaseMessage {
    String message() {
        return "base";
    }
}

class CustomMessage extends BaseMessage {
    @Override
    String message() {
        return "custom+" + super.message();
    }
}
```

`new CustomMessage().message()` produces the string `custom+base`. `super.message()` **does not create a new superclass instance**; it requests a call to the superclass implementation on the same current object according to language rules. This snippet consists of illustrative class declarations; to print the result, it needs to be placed inside `main`.

## 9. Passing an Object as a Parameter Is Still Pass-by-Value

In Java, all method arguments are passed by **value**. If an argument has a reference type, the value copied is the **reference to the object**, not a copy of the object.

This is a source of confusion because a method can modify the state of the object the caller is referencing, yet **cannot reassign the caller's reference variable** by reassigning the parameter.

File **`ReferenceParameterDemo.java`**:

```java
class Box {
    int value;

    Box(int value) {
        this.value = value;
    }
}

public class ReferenceParameterDemo {
    static void change(Box box) {
        box.value += 3;
        box = new Box(99);
        System.out.println("inside=" + box.value);
    }

    public static void main(String[] args) {
        Box current = new Box(2);

        change(current);

        System.out.println("outside=" + current.value);
    }
}
```

```bash
javac ReferenceParameterDemo.java
java ReferenceParameterDemo
```

```text
inside=99
outside=5
```

At the beginning of `change(current)`, the parameter `box` receives a **copy of the reference** currently in `current`; both references point to `Box(2)`. `box.value += 3` modifies the shared object to `5`. Then `box = new Box(99)` only changes the **parameter variable `box` inside the method** and does not reassign the caller's `current` variable. Therefore, after exiting the method, `current.value` is still `5`.

Distinguish between:

- **Modifying the object's contents through a reference**: anyone holding a reference to the same object can observe the change.
- **Reassigning a local reference variable**: does not change the value of the reference variable at the call site.
- **Creating a new object inside a method**: does not automatically return that object to the caller, unless the method returns the reference or stores it in a location accessible to the caller.

In the `Account.transferTo(nam, 25)` example, the `target` parameter receives a copy of the reference from `nam`; calling `target.deposit(...)` still modifies the same Nam account. This is Java's pass-by-value mechanism for references, not a pass-by-reference language mechanism in the sense of a parameter reassigning the caller's variable.

## 10. Instance Method Calls and Static Method Calls: Do Not Confuse the Receiver Object

A **static method** can be called using the class name without needing an instance:

```java
class Converter {
    static int toSeconds(int minutes) {
        return minutes * 60;
    }

    int triple(int number) {
        return number * 3;
    }
}
```

Natural way to call them:

```java
int seconds = Converter.toSeconds(2); // static, returns 120.
Converter converter = new Converter();
int result = converter.triple(4);     // instance, returns 12.
```

Although Java accepts the syntax of calling a static method through an object variable in certain cases (for example, `converter.toSeconds(2)`), this method is still resolved as static, **has no receiver object as `this`**, and does not use dynamic dispatch. Write it using the class name `Converter.toSeconds(2)` to make the intent clear.

An advanced detail: a variable holding `null` can sometimes still be used in the syntax of a statically resolved static method call; this does **not** prove that calling an instance method through `null` is safe. Good practice is still to call static methods using the class name to avoid confusion and avoid unnecessary side effects when the expression before the dot is evaluated.

| Criterion | Instance method | Static method |
| --- | --- | --- |
| Declaration | Without `static` | With `static` |
| Typical call | `object.run()` | `TypeName.run()` |
| Has receiver object/`this`? | Has an appropriate receiver at runtime; `this` is used in an instance context | Does not have `this` |
| Accessing instance fields | Directly via `this` or an appropriate name | Must have a specific object reference |
| Overriding/polymorphism | Can be overridden when rules permit | Not overridden via dynamic dispatch; can be hidden |
| When to use | Behavior depending on object state or identity | Utility functions, factories, general functionality not requiring an instance |

## 11. Common Mistakes When Identifying the Receiver

### Mistake 1: Thinking a Variable Name Permanently Determines Identity

`Account selected = mai;` followed by `selected = nam;` makes the receiver change according to the reference `selected` holds at each point in time. Look at the **reference value**, do not guess from how the variable is named.

### Mistake 2: Using `this` in a Static Method

`this` does not exist in a static context. A static method must receive an object through a parameter, access static members, or create an appropriate object and use its reference.

### Mistake 3: Misreading `account.deposit(10)` as "Copy the Account and Then Deposit"

Java does not create a copy of the object when calling an instance method. The call runs on the object referenced by the receiver. If behavior that does not modify state is needed, design an immutable object or a method that explicitly returns a new object.

### Mistake 4: Calling an Instance Method on `null`

`String text = null; text.length();` can compile, but throws a `NullPointerException` at runtime. A valid static type does not guarantee that a receiver object exists.

### Mistake 5: Assuming `Base ref = new Derived()` Makes Every Method of `Derived` Callable

The compiler checks whether the method exists in the **static type of the receiver expression**. If a method exists only on `Derived`, it cannot be called directly through a `Base` variable. You can use an interface or an appropriate API design; cast only after verifying runtime compatibility.

### Mistake 6: Confusing Overloading with Overriding

`handle(Animal)` and `handle(Dog)` are two overloads, selected by resolution at compile time. `Dog.speak()` overrides `Animal.speak()`, so its implementation is selected based on the runtime receiver. These are two different mechanisms even though both involve multiple methods with the same name.

### Mistake 7: Thinking Parameters Are "References Passed by Reference"

Java copies the **reference value**; a method can modify the shared object, but reassigning the parameter variable does not change the caller's variable. Try the `ReferenceParameterDemo` example to observe the difference.

### Mistake 8: Failing to Identify the Receiver in Nested Calls

In `service.getAccount().deposit(10)`, the receiver of `getAccount()` is `service`, while the receiver of `deposit()` is **the object returned by `getAccount()`**. If the method returns `null`, the `deposit` call will fail. Analyze one dot at a time.

### Mistake 9: Calling an Overridable Method from a Constructor Before Object Initialization Finishes

If a superclass constructor calls an **overridable instance method**, the runtime may dispatch to the subclass method before the subclass's field initializers/constructor finish executing. The receiver is **the same object being constructed**, but the subclass state may not be ready yet. Avoid calling overridable methods from a constructor unless you clearly understand the rules and accept the risk.

### Mistake 10: Treating `private` as If Only `this`'s Fields Were Accessible

Within the same class, Java can allow an instance method to access a private field of **another instance of the same class** via an appropriate reference variable:

```java
class Point {
    private int x;

    Point(int x) {
        this.x = x;
    }

    int distanceFrom(Point other) {
        return Math.abs(this.x - other.x);
    }
}
```

`this.x` is the field of the current receiver, and `other.x` is the field of **another** receiver held in the parameter. `private` protects members at class access scope; it does not restrict a member to being read only from the `this` object. This code snippet is a valid class declaration without `main`.

## 12. Self-Check with Specific Scenarios

**Question 1.** Given `Counter a = new Counter(); Counter b = a;`, followed by `a.increment(); b.increment();`, how many `Counter` objects are created? What is the value of `a.getValue()`?

**Answer:** Only **one object** because there is only one `new`. `a` and `b` are two variables referencing that same object; the final value is `2`.

**Question 2.** In `mai.transferTo(nam, 25)` from the first example, what are the receivers of `transferTo`, `this.withdraw`, and `target.deposit`, respectively?

**Answer:** `transferTo` and `this.withdraw` have Mai's account as their receiver; `target.deposit` has Nam's account as its receiver.

**Question 3.** Given `Animal a = new Dog();`, what does `a.speak()` return, and why does `a.fetch()` cause a compilation error?

**Answer:** `a.speak()` returns `woof` because the instance method is overridden and the runtime receiver is `Dog`. `a.fetch()` is rejected because the static type of `a` is `Animal`, which does not have `fetch()`.

**Question 4.** In `Lamp x = new Lamp("Desk"); Lamp y = x.turnOn();`, is `x == y` `true` or `false`?

**Answer:** `true` because `turnOn()` returns `this`. If the implementation were changed to return `new Lamp(...)`, the result could differ; you must read the method contract.

**Question 5.** Given `Box b = new Box(2); change(b);` following `ReferenceParameterDemo`, why is `b.value` equal to `5` instead of `99`?

**Answer:** `change` modifies the object pointed to by both references, and then only reassigns the **local parameter** to reference a new object. The caller's variable `b` still points to the original object whose value was changed from `2` to `5`.

**Question 6.** If `Account a = null;`, at which stage does the call `a.summary()` occur?

**Answer:** The method is accepted by the compiler based on its static type, but at runtime there is no receiver object to invoke it on, so it throws a `NullPointerException`.

**Question 7.** In `new Lamp("Hall").turnOn().status()`, how many receiver objects are there?

**Answer:** In this example, **one Lamp object** is created. `turnOn()` receives that object and returns `this`, so `status()` continues using the same object. Two **method calls** do not mean two objects.

**Question 8.** Does `super.method()` inside a subclass instance method create a separate superclass object?

**Answer:** No. It is a form of call requesting the appropriate implementation from the superclass in the context of the **same object**, not a `new` statement.

## 13. How to Trace a Method Call Yourself

When encountering an expression `someExpression.someMethod(arguments)` in real code, determine each of the following in order:

1. **Static type of the expression to the left of the dot**: which members does the compiler allow access to?
2. **Which reference that expression returns at runtime**: a specific object, another reference via an alias, or `null`?
3. **Whether this is an instance or static call**: is the resolved method signature an instance method or a static method?
4. **Whether there are multiple overloads**: which signature version is selected by the compiler according to method selection rules?
5. **Whether that instance method is overridden**: if so, which implementation does the runtime class of the receiver select to run?
6. **Which object the method body affects**: could statements using `this.field`, `other.field`, and method calls on parameters point to different objects?
7. **What the method returns**: a primitive, a reference to `this`, another reference, a new object, or `void`? The answer determines the receiver of the next link in the chain, if any.
8. **Whether runtime errors can occur**: a `null` receiver, invalid arguments, the method throwing an exception, or an invalid object state?

Practicing these steps on `mai.transferTo(nam, 25)`, `desk.turnOn().turnOff()`, and `general.speak()` will help clearly distinguish between the **reference variable**, the **receiver object**, the **selected method**, and the **object actually being modified**.

---

**Remember:** An **instance method** is behavior executed in the context of a **receiver object**. The expression before the dot typically supplies a reference to the receiver; `this` is the current receiver inside an instance method body. Two variables can point to the same object, a call can shift to another object via a parameter or method return value, and Java selects overridden method implementations based on the receiver's runtime class. Correctly identifying **the receiver, static type, state, and return value** is foundational for reading, designing, and debugging instance methods in Java.
