# Distinguishing `static` Members from Instance Members — Java 17+

## 1. `static` Belongs to the Class, Instance Belongs to Each Object

In a Java class, a **member** is typically a field or a method. The `static` keyword determines whether the member is bound to the **class** instead of being bound to each individual **object (instance)**.

~~~java
class Counter {
    static int createdCount; // Static field: belongs to the Counter class.
    int value;               // Instance field: belongs to each Counter.

    Counter(int value) {
        this.value = value;
        createdCount++;
    }

    void increase() {        // Instance method: works with the current object.
        value++;
    }

    static int count() {     // Static method: works without an instance receiver.
        return createdCount;
    }
}
~~~

~~~java
Counter a = new Counter(2);
Counter b = new Counter(10);
a.increase();
System.out.println(a.value);
System.out.println(b.value);
System.out.println(Counter.count());
~~~

**Exact stdout**, when the calls are placed in an appropriate `main` of a fresh run:

~~~text
3
10
2
~~~

Two `new Counter(...)` calls create **two objects** with separate `value` fields. In contrast, `createdCount` is **one static field of the `Counter` class** and increments in both constructor calls.

**Rule to remember:** `static` belongs to the **type/class**; **instance** belongs to a **specific object**. Do not think of `static` as "a separate copy per object", nor think of instance as "a shared variable across all objects".

## 2. Quick Comparison Table

| Criterion | `static` member | Instance member |
|---|---|---|
| Has the `static` keyword? | **Yes** | **No** |
| Bound to | Declaring class | Each object of the class |
| What does the field store? | Shared class-level state | Per-object individual state |
| Recommended read/call syntax | `Counter.count()` | `a.increase()` |
| Need `new Counter(...)` before calling? | No, if access permits | Requires an object/receiver |
| Is `this` available in the method? | No | Yes, pointing to the current receiver |
| Can it directly access an instance field? | No, unless given a specific receiver | Yes |
| Can it access a static field? | Yes | Yes, though using the class name is clearer |
| Example | `static int createdCount` | `int value` |

The word `static` is not synonymous with **constant**. A `static int` can still change. Only adding `final` enforces the constraint that the **field variable** cannot be reassigned after initialization according to Java rules.

## 3. Instance Fields: Separate State per Object

~~~java
class Box {
    private int size;

    Box(int size) {
        this.size = size;
    }

    void grow(int amount) {
        size += amount;
    }

    int getSize() {
        return size;
    }
}
~~~

~~~java
Box small = new Box(2);
Box large = new Box(10);
small.grow(3);
System.out.println(small.getSize());
System.out.println(large.getSize());
~~~

**Exact stdout:**

~~~text
5
10
~~~

`size` is an **instance field**. Two objects of the same `Box` type have **independent** `size` values. Calling `small.grow(3)` updates the object `small` points to, without updating `large`.

A reference variable assigned via `Box alias = small;` **does not create a new Box**: `alias` and `small` point to the same object. In that case, `alias.grow(1)` causes `small.getSize()` to change. This is **sharing an object across two references**, not a field becoming static.

## 4. Static Fields: Class-Level Shared Data

~~~java
class Ticket {
    private static int nextNumber = 1;
    private final int number;

    Ticket() {
        number = nextNumber++;
    }

    int getNumber() {
        return number;
    }

    static int nextAvailableNumber() {
        return nextNumber;
    }
}
~~~

~~~java
Ticket a = new Ticket();
Ticket b = new Ticket();
System.out.println(a.getNumber());
System.out.println(b.getNumber());
System.out.println(Ticket.nextAvailableNumber());
~~~

**Exact stdout**, in a fresh run:

~~~text
1
2
3
~~~

- `nextNumber` is a **static field**, allowing constructors to share the next counter value.
- `number` is an **instance field** of each ticket; ticket `a` receives `1`, ticket `b` receives `2`.
- `Ticket.nextAvailableNumber()` is a **static method** and should be called via the class name, without needing to create another `Ticket`.

A normal static field is allocated and initialized by Java when the class is initialized according to JVM rules; it is not "a field residing inside each object". In environments with multiple class loaders, distinguish class identity scopes; do not treat every static field as **one single global variable across all JVMs**.

## 5. Calling `static` vs. Instance Methods

~~~java
class MathBox {
    private int value;

    MathBox(int value) {
        this.value = value;
    }

    int doubleValue() {
        return this.value * 2;
    }

    static int square(int n) {
        return n * n;
    }
}
~~~

~~~java
MathBox box = new MathBox(5);
System.out.println(box.doubleValue());   // Instance method.
System.out.println(MathBox.square(5));   // Static method.
~~~

**Exact stdout:**

~~~text
10
25
~~~

An **instance method** has a receiver, i.e., a specific object. In `box.doubleValue()`, `this` is the object `box` references.

A **static method** has no implicit instance receiver. `MathBox.square(5)` works on the argument `5` and needs no reference to any `MathBox` object.

Java allows syntax that calls a static method via an instance variable, such as `box.square(5)`; however, this easily gives a misleading impression about the receiver. **Call using the class name: `MathBox.square(5)`.** If you know the class name and the static method is accessible, no `new` object is required to call it.

## 6. `this` Cannot Be Used in a `static` Context

~~~java
class User {
    private String name;
    private static int count;

    String describe() {
        return this.name;    // Valid: inside an instance method.
    }

    static int getCount() {
        return count;        // Valid: reading a static field.
    }

    // static String wrong() {
    //     return this.name; // ERROR: static context has no this.
    // }
}
~~~

A static method **cannot directly** read an instance field `name` without a concrete object. To read it, accept an object as an argument or create a valid object:

~~~java
static String describeUser(User user) {
    return user.name;  // Accessed through the user reference.
}
~~~

In this example, `describeUser` belongs to the **same `User` class**, so it can access the `private name` field of a `User` object. If placed in another class, appropriate access permissions are needed (e.g., calling a getter).

Conversely, an instance method can use static fields/methods of the same class; although you can write `count` without the class name, `User.count` usually makes it clear that this is shared data.

**Note:** `main(String[] args)` is also a static method, so it has no `this`. To call an instance method from `main`, create or obtain an object first.

## 7. Static Initializers and Initialization Timing

~~~java
class Settings {
    static int limit = 10;

    static {
        limit += 5;
    }

    static int getLimit() {
        return limit;
    }
}
~~~

When the `Settings` class is initialized, static fields and static initializer blocks are processed in textual declaration order. In the example above, after initialization, `Settings.getLimit()` returns **`15`**.

Instance initializers/constructors are a separate mechanism that runs when each object is created. **Importing a class** is not a command to "run constructors" or initialize all objects of that class.

Static initialization is managed by the JVM (typically before the first active use requiring class initialization). Do not assume every class is initialized at compile time or immediately when a source file is imported.

## 8. `static final`: Class-Level Constants and Immutability Limits

~~~java
class Limits {
    static final int MAX_ITEMS = 100;
    static final String UNIT = "items";
}
~~~

You can read `Limits.MAX_ITEMS` and `Limits.UNIT` without creating an object. Fields of primitive/`String` types using `static final` are typically suitable for unchanging constants such as limits, labels, or units.

However, `final` only prevents **reassigning the field**; it does not automatically "freeze" the contents of the object the field references:

~~~java
class Holder {
    static final int[] VALUES = {1, 2};
}
~~~

`Holder.VALUES = new int[]{3};` is invalid, yet `Holder.VALUES[0] = 9;` is **still valid** if the array remains accessible and there are no other controls. Therefore, avoid exposing mutable static arrays/collections directly when data protection is needed.

**Interface members** also have specific rules: fields declared in an interface are implicitly `public static final`; this lesson focuses on comparing static/instance in regular classes.

## 9. Static Mutable State: Use the Right Scope

Static fields can be useful to hold:

- Unchanging configuration constants: `static final`.
- Counters of objects created or how many times an operation occurred.
- Utility functions needing no instance state, e.g., `Math.max(...)`.
- Intentionally shared data with clear update rules.

Not all data should be static. If you make a bank account's `balance` static, **every account object shares one balance**, violating the requirement that "each account has its own balance".

A mutable static field also causes different parts of a program to **share state**. In multithreaded programs, `counter++` is not an atomic increment; synchronization or tools like `AtomicInteger` may be needed, depending on the problem. In tests, static mutable state can also persist across tests if not reset. These issues do not arise simply because the `static` keyword is "bad"; they are consequences of **shared state and lifecycle management**.

In the educational example below, the counter and total balance use `static` to represent shared statistics. This is a **single-threaded** illustration, not a production-safe financial transaction implementation.

## 10. Standalone Java 17+ Program

Save with the exact filename **`StaticInstanceMembersDemo.java`**:

~~~java
public final class StaticInstanceMembersDemo {
    private StaticInstanceMembersDemo() {}

    // Static nested class so the example runs from one file.
    static final class Account {
        static final String CURRENCY = "VND";   // Class-level constant.

        private static int createdCount;        // Shared field.
        private static int nextId = 1;          // Shared field.
        private static int totalBalance;        // Shared total balance.

        private final int id;                   // Instance field.
        private final String owner;             // Instance field.
        private int balance;                    // Instance field.

        Account(String owner, int openingBalance) {
            if (owner == null || owner.isBlank()) {
                throw new IllegalArgumentException("owner must not be blank");
            }
            if (openingBalance < 0) {
                throw new IllegalArgumentException("negative opening balance");
            }

            this.owner = owner.strip();
            this.balance = openingBalance;
            this.id = nextId++;
            createdCount++;
            totalBalance += openingBalance;
        }

        void deposit(int amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }
            this.balance += amount;
            totalBalance += amount;
        }

        boolean withdraw(int amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }
            if (amount > this.balance) {
                return false;
            }
            this.balance -= amount;
            totalBalance -= amount;
            return true;
        }

        String summary() {
            return id + ":" + owner + ":" + balance;
        }

        static int getCreatedCount() {
            return createdCount;
        }

        static int getTotalBalance() {
            return totalBalance;
        }
    }

    public static void main(String[] args) {
        System.out.println("currency=" + Account.CURRENCY);
        System.out.println("created initially=" + Account.getCreatedCount());
        System.out.println("total initially=" + Account.getTotalBalance());

        Account an = new Account(" An ", 100);
        Account binh = new Account("Binh", 50);
        System.out.println("created after new=" + Account.getCreatedCount());
        System.out.println("total after new=" + Account.getTotalBalance());
        System.out.println("an initial=" + an.summary());
        System.out.println("binh initial=" + binh.summary());

        an.deposit(20);
        System.out.println("withdraw Binh 10=" + binh.withdraw(10));
        System.out.println("withdraw Binh 100=" + binh.withdraw(100));
        System.out.println("an after operations=" + an.summary());
        System.out.println("binh after operations=" + binh.summary());
        System.out.println("shared total=" + Account.getTotalBalance());

        Account alias = an;
        alias.deposit(5);
        System.out.println("alias same An=" + (alias == an));
        System.out.println("an via alias=" + an.summary());
        System.out.println("created after alias=" + Account.getCreatedCount());
        System.out.println("shared total after alias=" + Account.getTotalBalance());

        try {
            new Account(" ", 30);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid owner=" + ex.getMessage());
        }
        System.out.println("created final=" + Account.getCreatedCount());
        System.out.println("shared total final=" + Account.getTotalBalance());
    }
}
~~~

Requires **JDK 17 or later**; no Maven, Gradle, libraries outside the JDK, or preview features needed. The file has one public top-level class matching the filename. `Account` is a **static nested class** in order to keep the example in one file; the `static` keyword on the nested type means an instance of the enclosing class is not needed to create an `Account`, which differs from the static fields inside `Account`.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 StaticInstanceMembersDemo.java
java -cp . StaticInstanceMembersDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\StaticInstanceMembersDemo.java
java -cp . StaticInstanceMembersDemo
~~~

### Exact expected stdout

~~~text
currency=VND
created initially=0
total initially=0
created after new=2
total after new=150
an initial=1:An:100
binh initial=2:Binh:50
withdraw Binh 10=true
withdraw Binh 100=false
an after operations=1:An:120
binh after operations=2:Binh:40
shared total=160
alias same An=true
an via alias=1:An:125
created after alias=2
shared total after alias=165
invalid owner=owner must not be blank
created final=2
shared total final=165
~~~

**Analysis:**

1. `Account.CURRENCY` is a static final constant. `createdCount` and `totalBalance` are static fields, starting with the default value `0`; `nextId` starts at `1`.
2. Two successful constructor calls create `an` and `binh`: account count is `2`, initial total is `100 + 50 = 150`. Each object has its own `id`, `owner`, `balance`.
3. `an.deposit(20)` brings An's balance to `120`. `binh.withdraw(10)` brings Binh's balance to `40`. Withdrawing `100` is rejected, so data does not change. The static total at this point is `120+40=160`.
4. `Account alias = an;` **does not create a new account**, but shares one object. Depositing `5` via `alias` brings An to `125` and the shared total to `165`, while the number of created accounts remains `2`.
5. The constructor with `" "` throws an exception **before** the static update lines, so the count/total remain unchanged.

## 11. Common Mistakes

| Mistake | Why is it wrong? | How to fix |
|---|---|---|
| Thinking `static int count` has one copy per object | A static field belongs to the class | Use `static` only for genuinely shared data |
| Thinking `int balance` in a class is automatically static | Without `static`, it is an instance field | Distinguish each declaration |
| Calling `Account.summary()` as static | `summary()` is an instance method | Use `an.summary()` |
| Using `this.balance` in a static method | A static context has no `this` | Access through a specific object |
| Writing `new Account(...)` just to call a static method | Creates an unnecessary object | Use `Account.getCreatedCount()` |
| Calling `an.getCreatedCount()` making it look like `count` belongs to An | Static members are clearer when called via the class | `Account.getCreatedCount()` |
| Thinking `static final int[]` is an immutable array | `final` only fixes the field reference | Avoid exposing mutable arrays or return a copy |
| Making every field `static` for convenient access | Mixes object states, hard to test | Use instance fields when data belongs to each object |
| Believing static `counter++` is always thread-safe | Read-modify-write is not atomic | Needs thread-safety mechanisms if shared across threads |
| Confusing `alias = an` with copying an account | It is a reference copy | Create a new object if independent state is needed |

## 12. Exercises and Answers

**A — Classify the members:**

~~~java
class Sensor {
    static int sensorCount;
    int temperature;
    static int getSensorCount() { return sensorCount; }
    int read() { return temperature; }
}
~~~

**Answer:** `sensorCount` and `getSensorCount()` are **static**; `temperature` and `read()` are **instance**.

**B — What do two objects share?**

~~~java
class Marker {
    static int created;
    int color;

    Marker(int color) {
        this.color = color;
        created++;
    }
}
~~~

After `new Marker(1)` and `new Marker(2)`, there are **two separate instance `color` values**, whereas `Marker.created == 2` is shared static state.

**C — Can a static method read an instance field?**  
**Answer:** it cannot read **directly** without a receiver. It can accept an object as an argument and read through that reference if access permissions allow.

**D — Are two variables pointing to the same object the same as `static`?**  
**Answer:** no. `Account b = a;` makes two variables point to **one** object; that is aliasing. An instance field still belongs to that specific object rather than becoming static.

**E — Does `static final int[] VALUES` forbid `VALUES[0] = 5`?**  
**Answer:** no; `final` forbids reassigning the `VALUES` field, but does not automatically make array elements immutable.

**F — Why shouldn't `createdCount` be an instance field if the goal is to count all created accounts?**  
**Answer:** each object would have its own counter. A static field represents a single shared counter; it must be updated consistently, with attention to multithreading if applicable.

## 13. Checklist and Conclusion

- [ ] Identify which fields/methods carry the `static` keyword.
- [ ] Distinguish **class-level shared** fields from **per-object** fields.
- [ ] Know to call static methods via class name, and instance methods via a receiver.
- [ ] Do not use `this` in a static context.
- [ ] Understand that instance methods can access both instance and static members.
- [ ] Understand that constructors create individual objects while optionally updating a shared static counter.
- [ ] Distinguish `static` from `final`; know that `static final` does not make mutable objects immutable.
- [ ] Know that static initializers relate to class initialization, not creating individual objects.
- [ ] Understand that aliasing shares an object, not static members.
- [ ] Know the risks of static mutable state in tests/multithreading.
- [ ] Compile and run `StaticInstanceMembersDemo.java` with Java 17+, and verify exact stdout.

**Conclusion:** **Static members belong to the class**, used for shared data and behavior not tied to a specific instance. **Instance members belong to each instance**, used to represent individual state and behavior. Choosing the right member scope avoids mixing object data, clarifies where `this` is permitted, and keeps shared state under control.