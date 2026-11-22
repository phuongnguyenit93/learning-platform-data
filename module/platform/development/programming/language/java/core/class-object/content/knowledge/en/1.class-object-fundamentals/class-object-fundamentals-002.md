# State, Behavior, and Identity of an Object in Java

An **object** in Java is not merely a collection of data. When a program works with objects, we need to distinguish three aspects: **state**, **behavior**, and **identity**. These three aspects are closely related, yet they answer three different questions:

| Aspect | Question | Typically represented in Java by |
| --- | --- | --- |
| State | What data does the object currently hold? | Values of instance fields at the time of observation |
| Behavior | What can the object do and how does it react? | Instance methods, rules, and conditions during operations |
| Identity | Is this the exact same object? | Reference relationship pointing to the same object; checked with `==` on two references |

For example, a digital wallet has a wallet ID, an owner, and a balance. That is its state. The wallet allows depositing and withdrawing money after checking conditions. That is its behavior. Two variables pointing to the same wallet refer to the same object; two different wallets with the same ID and balance are still two distinct objects in runtime memory. That is identity.

## 1. State: Data of Each Object

A `class` declares fields; each object created from the class typically has **its own copy of the instance field values**. State can change when methods update those fields.

~~~java
final class TemperatureSensor {
    private final String sensorId;
    private double celsius;

    TemperatureSensor(String sensorId, double initialCelsius) {
        this.sensorId = sensorId;
        this.celsius = initialCelsius;
    }

    double readCelsius() {
        return celsius;
    }

    void updateReading(double nextCelsius) {
        celsius = nextCelsius;
    }
}
~~~

`sensorId` is assigned at initialization and cannot be reassigned by ordinary Java code afterward because the field is `final`. `celsius` can change. Two `TemperatureSensor` instances may have the same temperature yet still have independent states. State is not just mutable data: `final` fields also belong to an object's state.

**Distinguish between instance fields and static fields.** A `static` field belongs to the class and is shared among objects, so it does not represent data specific to an individual instance.

~~~java
final class Ticket {
    private static int nextNumber = 1; // Shared across the Ticket class
    private final int number;           // Specific to each Ticket object

    Ticket() {
        number = nextNumber++;
    }

    int number() {
        return number;
    }
}
~~~

The first `new Ticket()` receives `number = 1`, and the second receives `number = 2` if the code runs sequentially from the initial state. `nextNumber` is shared state, not a separate copy for each ticket. This counting example is not safe if multiple threads call the constructor concurrently.

### State at Initialization

- Instance fields receive default values before the corresponding initialization steps complete: integers are `0`, `boolean` is `false`, and references are `null`. Afterward, initializers and constructors can set meaningful values.
- A constructor must establish a valid initial state; otherwise, subsequent methods will have to deal with an inconsistent object.
- A local variable in a method does **not** become part of an object's state merely because it is declared in that method; it exists within the corresponding call.

You should not understand “state” as every variable accessible from a method. When referring to an object's own state, the focus is on its instance fields and the data they reference.

## 2. Behavior: An Object Performs Work and Enforces Rules

Behavior is typically represented by instance methods. A method can **read** state (`balance()`), **modify** state (`deposit()`), **compute** a result without changing state, or collaborate with other objects. The goal of object-oriented design is to keep data and valid operations on that data within the same boundary of responsibility.

A wallet object has rules: only positive amounts can be deposited or withdrawn, and withdrawals must not exceed the balance. Instead of letting code anywhere modify `balance` directly, we keep the field `private` and expose valid behaviors.

## 3. Java 17+ Example: All Three Aspects in One Program

Save the file as **`ObjectStateBehaviorIdentityDemo.java`**:

~~~java
public class ObjectStateBehaviorIdentityDemo {

    static final class Wallet {
        private final String id;
        private String owner;
        private long balance;

        Wallet(String id, String owner, long openingBalance) {
            this.id = requireText(id, "id");
            this.owner = requireText(owner, "owner");
            if (openingBalance < 0) {
                throw new IllegalArgumentException("openingBalance must be >= 0");
            }
            this.balance = openingBalance;
        }

        String id() {
            return id;
        }

        long balance() {
            return balance;
        }

        void renameOwner(String newOwner) {
            owner = requireText(newOwner, "owner");
        }

        void deposit(long amount) {
            requirePositive(amount);
            balance = Math.addExact(balance, amount);
        }

        void withdraw(long amount) {
            requirePositive(amount);
            if (amount > balance) {
                throw new IllegalArgumentException("Insufficient balance");
            }
            balance -= amount;
        }

        String describe() {
            return id + " | " + owner + " | " + balance;
        }

        private static String requireText(String value, String fieldName) {
            if (value == null || value.isBlank()) {
                throw new IllegalArgumentException(fieldName + " is required");
            }
            return value;
        }

        private static void requirePositive(long amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("amount must be > 0");
            }
        }
    }

    public static void main(String[] args) {
        Wallet a = new Wallet("W-01", "An", 1_000);
        Wallet alias = a;
        Wallet other = new Wallet("W-01", "An", 1_000);

        System.out.println("Ban đầu: " + a.describe());
        System.out.println("a == alias: " + (a == alias));
        System.out.println("a == other: " + (a == other));
        System.out.println("a.equals(other): " + a.equals(other));
        System.out.println("Cùng mã ví: " + a.id().equals(other.id()));

        alias.deposit(250);
        a.withdraw(100);

        System.out.println("Ví a sau cập nhật: " + a.describe());
        System.out.println("Ví other: " + other.describe());
    }
}
~~~

Compile and run from the directory containing the file:

~~~bash
javac ObjectStateBehaviorIdentityDemo.java
java ObjectStateBehaviorIdentityDemo
~~~

Expected output:

~~~text
Ban đầu: W-01 | An | 1000
a == alias: true
a == other: false
a.equals(other): false
Cùng mã ví: true
Ví a sau cập nhật: W-01 | An | 1150
Ví other: W-01 | An | 1000
~~~

**Analysis across the three aspects:**

1. **State:** object `a` initially has `id = "W-01"`, `owner = "An"`, and `balance = 1000`. After two operations, `balance = 1150`. `other` still keeps a balance of `1000`.
2. **Behavior:** `deposit(250)` increases the balance, while `withdraw(100)` decreases the balance and rejects withdrawals exceeding the balance. `describe()` reads the state to build a string without modifying any fields.
3. **Identity:** `a` and `alias` hold references to **the same Wallet**. `other` is a different instance created by a separate `new` expression, even though its initial data is identical. Therefore, `a == alias` is `true` while `a == other` is `false`.
4. `Wallet` does not override `equals`, so it inherits `Object.equals`: for these Wallet objects, it returns `true` when both references point to the same object. Consequently, `a.equals(other)` is `false`.
5. The wallet ID strings of `a` and `other` have equal contents, so `a.id().equals(other.id())` is `true`. This compares **business identifier values**; it does not prove that the two Wallets share the same object identity in the JVM.

`Math.addExact` is used to throw `ArithmeticException` if the `long` addition overflows; using only `balance += amount` could cause the balance to overflow and produce an incorrect result. This is an example of behavior protecting a state invariant. In a real-world monetary system, you would also need to define the smallest currency unit and handle transactions and concurrency; this example focuses solely on the object model.

## 4. Identity and References: Two Variables Can Point to the Same Object

In Java, a variable of a reference type (`Wallet`, `String`, arrays, etc.) holds a **reference value** pointing to an object or `null`. The reference variable itself and the object it points to are two distinct concepts.

~~~text
a ────────┐
          ├────> Wallet #1 { id: "W-01", balance: 1150 }
alias ────┘

other ─────────> Wallet #2 { id: "W-01", balance: 1000 }
~~~

The diagram only illustrates reference relationships; it does not represent actual memory addresses or heap layout.

- `Wallet alias = a;` copies the **reference value**. It does not invoke a constructor, does not clone, and does not create another Wallet.
- `alias.deposit(250)` invokes behavior on the object that both `alias` and `a` reference. Therefore, reading `a.balance()` reflects the update.
- `Wallet other = new Wallet(...);` creates a new instance. Matching field contents do not merge the new instance with the previous one.
- Reassigning a variable, such as `alias = other;`, only changes which object **the alias variable** references; it does not turn Wallet #1 into Wallet #2 and does not automatically modify the reference stored in `a`.
- If an object's state changes, **the identity of that object itself remains unchanged** for as long as the object exists.

### Comparing `==` and `equals()`

| Expression | Meaning for reference types | Key point to remember |
| --- | --- | --- |
| `x == y` | Do both references point to the same object, or are both `null`? | Checks the reference relationship, not field contents |
| `x.equals(y)` | Compares according to logic defined by the class | `Object.equals` compares like `==` by default; many classes override it for value comparison |
| `x.id().equals(y.id())` | Do both business IDs have the same content? | Not equivalent to `x == y`, nor necessarily equivalent to `x.equals(y)` |

When used with primitive types such as `int`, `char`, and `boolean`, `==` compares **primitive values**, because there are no objects whose references can be compared. Do not apply your intuition about `==` on integers to two objects.

`null` is a value indicating that no object is currently referenced. `x == null` is a valid check; calling `x.equals(...)` when `x` is `null` throws a `NullPointerException`. When you want to compare two potentially null values, use `java.util.Objects.equals(x, y)`: it returns `true` if both are null, `false` if only one is null, and otherwise delegates to `x.equals(y)`.

## 5. “Object Identity” and “Business Identifier” Are Two Different Concepts

In the Wallet example, the `id` field is a **business identifier**. A system may specify that no two wallets may have the same ID; however, the JVM does not automatically enforce that rule when executing two `new` expressions. To guarantee uniqueness by ID, the application must control object creation, manage storage, or apply data constraints.

Three relationships should be kept distinct:

- **Same instance:** `a == b`.
- **Equal according to the class contract:** `a.equals(b)`. The meaning depends on the implementation.
- **Same business key:** for example, `a.id().equals(b.id())`.

An entity may choose to define `equals/hashCode` based on a stable business key. A value object typically defines equality across all relevant value components. There is no rule stating that every class must override `equals`, or that having a field named `id` causes `==` to become an ID comparison.

### Illustrating a Value Object with `record` (Java 17+)

`record` is well suited for data-carrying structures, providing `equals`, `hashCode`, and `toString` by default based on the record components. Save the file **`CoordinateComparison.java`**:

~~~java
public class CoordinateComparison {
    record Coordinate(int x, int y) {}

    public static void main(String[] args) {
        Coordinate left = new Coordinate(2, 3);
        Coordinate right = new Coordinate(2, 3);

        System.out.println(left == right);
        System.out.println(left.equals(right));
        System.out.println(left);
    }
}
~~~

~~~bash
javac CoordinateComparison.java
java CoordinateComparison
~~~

Stdout:

~~~text
false
true
Coordinate[x=2, y=3]
~~~

`left` and `right` are two distinct instances, but the two `Coordinate` objects have the same `x` and `y` and are therefore equal according to `equals`. A record has no setters for record components, and `int` components cannot change on their own. However, if a record holds a reference to a mutable object, `record` **does not automatically make** that referenced object deeply immutable.

**The `equals/hashCode` contract:** when overriding `equals` to change the definition of equality, you must override `hashCode` consistently: if `x.equals(y)` is `true`, both objects must have the same `hashCode()`. The equality relation must also be reflexive, symmetric, transitive, and consistent as long as the relevant data does not change. This matters for `HashSet` and `HashMap` keys. A key based on a mutable field can cause incorrect lookups after the field changes.

Do not use `System.identityHashCode(object)` as a unique ID. This method returns an identity-based hash code independent of any overridden `hashCode`, yet **two different objects can still have the same hash code**; the value is not a guaranteed memory address, nor is it a durable key across application runs.

## 6. Passing References to Methods: Java Always Passes Arguments by Value

Java **passes arguments by value**. For object types, the value copied into the parameter is the **reference value**. As a result, a method can modify the state of the referenced object, but reassigning the parameter variable itself does not change the caller's variable.

Standalone runnable example, file **`ReferenceCopyDemo.java`**:

~~~java
public class ReferenceCopyDemo {
    static final class Counter {
        int value;

        Counter(int value) {
            this.value = value;
        }
    }

    static void touch(Counter parameter) {
        parameter.value += 3;         // Modifies the same object as the caller
        parameter = new Counter(99);  // Only reassigns the local parameter variable
        parameter.value++;            // Modifies the new object
    }

    public static void main(String[] args) {
        Counter original = new Counter(10);
        touch(original);
        System.out.println(original.value);
    }
}
~~~

~~~bash
javac ReferenceCopyDemo.java
java ReferenceCopyDemo
~~~

Stdout:

~~~text
13
~~~

The first operation increases `original`'s Counter from 10 to 13. The subsequent assignment `parameter = new Counter(99)` does not change `original`'s reference. The new object is manipulated separately; `original` continues pointing to the initial Counter. This is a source of confusion if Java is described as “pass by reference”.

## 7. State Encapsulation, Mutability, and Immutability

Good design restricts where state can be modified so that an object always preserves its valid conditions (**invariants**).

- Make sensitive fields `private` and provide necessary accessor methods or behaviors. There is no requirement to provide a setter for every field.
- Validate inputs in constructors and mutating methods. For instance, disallow negative opening balances or non-positive deposit amounts.
- Avoid directly returning internal mutable references if external code could modify them while bypassing the class's rules. Consider defensive copies or read-only interfaces.
- Distinguish between **`final` on a reference variable** and **immutability of an object**. `final Wallet w = ...` forbids reassigning `w` to another Wallet, yet **does not forbid** `w.deposit(10)`. Applying `final` to a reference field likewise does not automatically lock the state of the object that field points to.
- An immutable object is designed so that its observable state cannot change after creation. It still has identity when evaluated with `==`. Two immutable objects with equal contents are not necessarily the same instance.

Sometimes behavior simply returns a result without modifying state, such as `balance()` or a fee calculation method. “Having behavior” does not mean “always having side effects”. Conversely, methods that transfer funds, write files, or make network calls can produce side effects outside instance fields; when designing an API, those effects must be clearly documented.

### Mutable State in Multithreaded Environments

The Wallet example helps identify objects and business rules, yet by itself it is **not thread-safe**. Two threads updating `balance` simultaneously can cause a race condition or lost updates. If multiple threads share the same mutable object, you must design an appropriate synchronization mechanism or data/transaction model. This is an issue of **sharing state and coordinating behavior**, and it does not change the definition of an object's identity.

## 8. Common Misconceptions

| Misconception | Correct understanding |
| --- | --- |
| “Two objects with equal fields are the same object.” | Matching values do not imply that `==` is `true`. |
| “`Wallet alias = a` creates a copy of the Wallet.” | The assignment copies the reference; both variables point to the same instance. |
| “`equals` always checks for the same object.” | `Object.equals` does so by default, but `String`, records, and many other classes define equality by content. |
| “The `id` field is the JVM identity.” | `id` is merely application-defined data; JVM identity is independent of field names or values. |
| “`final` makes all properties immutable.” | `final` restricts reassignment of the corresponding variable or field; it does not automatically guarantee deep immutability. |
| “Passing an object to a method passes the caller's variable by reference.” | The parameter contains a copy of the reference value; the method cannot reassign the caller's variable. |
| “`identityHashCode` uniquely identifies every object.” | Hash codes can collide and are unsuitable as unique identifiers. |
| “Every instance method modifies fields.” | A method can simply read, compute, or coordinate tasks. |
| “Sharing the same object makes updates from two places always safe.” | Aliases see the same state, but multithreaded updates require concurrency safety handling. |

**Note on `String`:** Java has string interning and reuses certain objects. Therefore, do not infer that two variables refer to two distinct objects solely from seeing two string expressions. When the goal is to check string contents, use `equals` instead of `==`; in lessons on identity, look closely at the references and how objects are created.

## 9. Conceptual Self-Check

Suppose we have the following simple class, in which `Box` does not override `equals`:

~~~java
final class Box {
    int value;

    Box(int value) {
        this.value = value;
    }
}
~~~

Consider the following snippet placed inside a method:

~~~java
Box x = new Box(1);
Box y = x;
Box z = new Box(1);

y.value = 7;

System.out.println(x.value);
System.out.println(x == y);
System.out.println(x == z);
System.out.println(x.equals(z));
System.out.println(z.value);
~~~

Predict the output before looking at the answer:

~~~text
7
true
false
false
1
~~~

Explanation: `x` and `y` both reference the first Box, so modifications through `y` are visible when reading through `x`. `z` is created separately and retains the value `1`. The `Box` class does not override `equals`, so `x.equals(z)` is only true if both variables point to the same instance, which is not the case here.

Try answering these additional questions:

1. If you assign `y = z` **after** modifying `y.value`, does `x.value` revert to `1` automatically? **No.** Reassigning a reference does not undo already updated state.
2. If both Boxes have `value = 7`, does the expression `x == z` change to `true`? **No.** Modifying a field does not change identity.
3. If you modify `Box` to override `equals` based on `value`, does `x == z` change its result? **No.** Overriding `equals` only changes the logical method-based comparison; it does not change `==` for two references.

## 10. Applying This to Real Source Code

When reading or designing a class, identify the following in turn:

1. **State:** Which instance fields describe the object? What are the valid initial values? Which data is mutable and which data should remain stable?
2. **Behavior:** Which methods represent valid operations on the state? Which invariants must hold before and after each operation? Who has permission to make changes?
3. **Identity:** Does the application need to recognize the **same instance**, **value equality**, or the **same business ID**? Which definition of equality fits the requirement? Are there aliases or sharing across multiple threads?
4. **References:** Which objects are being shared? Does copying a variable copy a reference or create a copy of the object? Which methods can cause side effects?

These three perspectives help explain bugs such as “modifying one variable also changes another”, “two objects print identically yet fail comparison”, “invalid state even though setters still ran”, and “a key in a collection cannot be found again”. Understanding state, behavior, and identity clearly is the foundation for designing classes with well-defined responsibilities that are easy to test and safe to use in Java programs.
