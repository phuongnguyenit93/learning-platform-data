# Hiding Fields with `private` and Providing Meaningful Operations in Java

When learning **encapsulation**, we often start with the advice “make fields `private` and create getters/setters”. However, that is only the **first step**, not the real goal.

A well-encapsulated class must **control its own state**. Instead of letting external code arbitrarily modify individual fields, the class provides **meaningful operations in the problem domain**: an account has `deposit(...)` and `withdraw(...)`; an order has `confirm()` and `cancel()`; a shopping cart has `addItem(...)` and `removeItem(...)`; a thermostat has `increase()` and `decrease()`. Those operations check conditions and ensure the object does not transition into an invalid state.

Placed side by side:

~~~java
account.setBalanceCents(-500);  // API that sets the balance arbitrarily, easily breaking the invariant.
account.withdraw(500);         // API that expresses behavior and checks conditions.
~~~

The two lines above are **conceptual comparison code**, not a standalone runnable program. The second line is only valid if the class implements `withdraw` with full validation. `private` does not by itself prevent a public setter from allowing invalid values; **the public API design itself** determines whether state is protected.

This lesson belongs to the **Encapsulation** section of Java Core — Class & Object, uses Java 17+, and moves from principles and access control mechanisms to behavior design, defensive copying, invariants, exceptions, tests, and practical limitations.

## 1. Learning Objectives

After this lesson, you should be able to:

1. Explain how **`private` fields** differ from public fields and why hiding state is usually useful.
2. Distinguish **data hiding** from **rule encapsulation**: a private field is not enough if a public setter breaks the invariant.
3. Identify an object's **invariant**, for example a non-negative balance, valid quantities, and proper order state transitions.
4. Design **meaningful methods** instead of providing an arbitrary setter for every field.
5. Decide when you need a **getter, command method, factory, or validated setter**, or when not to expose a way to modify state.
6. Know how to preserve invariants in the constructor **and** every update method.
7. Know how to avoid exposing references to **arrays, lists, or mutable objects** in private fields.
8. Understand the meaning of `final`, immutable objects, records, and defensive copies.
9. Handle exceptions so that a failed operation does not leave behind an invalid state.
10. Test **public behavior** instead of depending on private field details.
11. Understand that `private` is not a mechanism for authentication, user authorization, encryption, or multithreaded synchronization.
12. Know how to recognize cases where setters are reasonable rather than taking the extreme stance of banning setters.

## 2. Three Layers to Distinguish: State, Behavior, and Invariant

An object can be visualized as follows:

~~~text
                  Public API
           +------------------------+
Caller --->| deposit(amount)        |
Caller --->| withdraw(amount)       |
Caller --->| balanceCents()         |
           +------------+-----------+
                        |
                        v
           +------------------------+
           | private balanceCents   |
           | invariant: balance>=0  |
           +------------------------+
~~~

**State** is the data the object currently holds, such as `balanceCents`.

**Behavior** is the operations the object provides, such as `deposit` and `withdraw`.

**Invariant** is the condition the class guarantees to hold true for an object in a valid state, such as `balanceCents >= 0`.

A public method should not break an invariant that the constructor has guaranteed. If a class allows:

~~~java
new BankAccount(1_000);  // Valid initialization.
account.setBalanceCents(-20_000); // Setter bypasses the invariant!
~~~

then the invariant is broken right after initialization. The goal of encapsulation is **not to allow external code to freely bypass those rules**.

### What is `private`?

`private` is a Java access modifier. A `private` member can only be accessed from contexts permitted by Java rules within the class/nest that declares it. Another top-level class, even in the same package, is **not automatically** granted permission to read the other class's private fields.

~~~java
public final class Profile {
    private String displayName;

    public Profile(String displayName) {
        this.displayName = displayName;
    }
}
~~~

A separate class outside `Profile` cannot simply write `profile.displayName = "A";` if the field is private. However, **methods inside Profile itself** can still modify `displayName`. Therefore, whether a private field maintains validity still depends on **the methods the class exposes publicly**.

## 3. Comparison: Public Fields and Private Fields

The easy-to-write but uncontrolled approach:

~~~java
public class PublicAccount {
    public long balanceCents;
}
~~~

A caller can do:

~~~java
PublicAccount account = new PublicAccount();
account.balanceCents = -999;
~~~

If the business rule requires a non-negative balance, this code has violated that condition without the class being able to intervene.

The state-protecting version:

~~~java
public class Account {
    private long balanceCents;

    public Account(long initialBalanceCents) {
        if (initialBalanceCents < 0) {
            throw new IllegalArgumentException("initial balance must be >= 0");
        }
        this.balanceCents = initialBalanceCents;
    }

    public long balanceCents() {
        return balanceCents;
    }

    public void deposit(long amountCents) {
        if (amountCents <= 0) {
            throw new IllegalArgumentException("deposit must be positive");
        }
        balanceCents = Math.addExact(balanceCents, amountCents);
    }
}
~~~

The two classes above are **alternative design illustrations**, not a complete program in a single file. In the second version, the caller can only change the balance through paths permitted by the class. `deposit` rejects non-positive amounts and uses `Math.addExact` so it does not silently produce an incorrect result when `long` overflows.

### A Field's Access Permissions Do Not Determine the Entire Design

Making a field private and then exposing:

~~~java
public void setBalanceCents(long newBalance) {
    this.balanceCents = newBalance;
}
~~~

still allows callers to change the balance arbitrarily. Even though the compiler forbids reading/writing the field directly, the method above is equivalent to an **overly broad state mutation path**. If you want the balance to only increase or decrease through business operations, provide `deposit`, `withdraw`, or `transfer` with appropriate contracts.

## 4. Complete Runnable Example: Seats Managed Through Behavior

To see that **`private` is not just about hiding a field name**, consider a class that manages the number of allocated seats in a class session. Invariant: `0 <= allocated <= capacity`. Callers do not have `setAllocated`; changes go through `allocate` and `release`.

Save **`SeatAllocationDemo.java`**:

~~~java
public class SeatAllocationDemo {
    static final class SeatAllocation {
        private final String course;
        private final int capacity;
        private int allocated;

        SeatAllocation(String course, int capacity) {
            if (course == null || course.isBlank()) {
                throw new IllegalArgumentException("course required");
            }
            if (capacity <= 0) {
                throw new IllegalArgumentException("capacity must be positive");
            }
            this.course = course.strip();
            this.capacity = capacity;
        }

        void allocate(int seats) {
            requirePositive(seats);
            if (seats > capacity - allocated) {
                throw new IllegalStateException("not enough seats");
            }
            allocated += seats;
        }

        void release(int seats) {
            requirePositive(seats);
            if (seats > allocated) {
                throw new IllegalStateException("more than allocated");
            }
            allocated -= seats;
        }

        String summary() {
            return course + ": " + allocated + "/" + capacity;
        }

        private static void requirePositive(int value) {
            if (value <= 0) {
                throw new IllegalArgumentException("seats must be positive");
            }
        }
    }

    public static void main(String[] args) {
        SeatAllocation seats = new SeatAllocation("  Java Core  ", 10);
        seats.allocate(3);
        seats.allocate(4);
        System.out.println(seats.summary());

        try {
            seats.allocate(5);
        } catch (IllegalStateException ex) {
            System.out.println("rejected: " + ex.getMessage());
        }

        seats.release(2);
        try {
            seats.release(0);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected: " + ex.getMessage());
        }

        System.out.println("after failures: " + seats.summary());
    }
}
~~~

~~~bash
javac -encoding UTF-8 SeatAllocationDemo.java
java SeatAllocationDemo
~~~

~~~text
Java Core: 7/10
rejected: not enough seats
rejected: seats must be positive
after failures: Java Core: 5/10
~~~

### Walkthrough and Design Rationale

1. The constructor validates the name and capacity, after which the instance starts with `allocated == 0`.
2. The two operations `allocate(3)` and `allocate(4)` bring the result to 7/10.
3. `allocate(5)` is rejected before incrementing because only three seats remain; there is no setter that bypasses checks.
4. `release(2)` brings the result down to 5/10; `release(0)` is rejected.
5. Comparing `seats > capacity - allocated` does not add quantities before checking, avoiding unnecessary overflow and preserving the invariant.

This is a **single-threaded** model without individual identification or specific seat cancellation contracts. Real-world systems must add concurrency, authorization, and transaction boundaries where appropriate. The lesson is that **public methods describe meaningful behavior and protect state across every call path**.

## 5. Why Don't Getters/Setters for Every Field Equal Good Encapsulation?

A class is often auto-generated like this:

~~~java
class Person {
    private String name;
    private int age;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public int getAge() {
        return age;
    }

    public void setAge(int age) {
        this.age = age;
    }
}
~~~

This is an illustrative class. The fields are private, yet `setName(null)` and `setAge(-500)` are still accepted. If the class has invariants requiring a non-empty name and a non-negative age, these setters break the invariants.

**The question to ask is not “which field does not have a setter yet?”, but “why does the caller need to change this data?”**

For example, for an order, it might make sense to have `changeDeliveryAddress(Address newAddress)` **only before shipping**, instead of `setAddress(...)` being callable in any state. For a finalized grade, you might only allow `recordGrade(...)` through a proper verification workflow, rather than allowing `setGrade(...)` arbitrarily.

### When Can Setters Be Reasonable?

Setters are not forbidden in Java:

- A configuration bean during its construction phase might need `setTimeout(...)` with validation.
- A user interface object might need to update display properties repeatedly.
- DTOs or serialization frameworks might require specific constructor/setter forms.
- Properties without complex business constraints can use setters with explicit validation.

When a setter is genuinely appropriate, make sure it **validates** and preserves all related constraints. Avoid writing public setters just because an IDE has a Generate Getters and Setters feature.

## 6. “Tell, Don't Ask”: Telling the Object to Perform Behavior

A design that relies too heavily on getters sometimes leads callers to pull data out, perform calculations themselves, and write it back:

~~~java
if (account.getBalanceCents() >= amount) {
    account.setBalanceCents(account.getBalanceCents() - amount);
}
~~~

This is an **anti-example**. The withdrawal rule is currently placed **outside the Account class**:

- Any caller could forget to check the balance.
- Multiple places will duplicate the same logic.
- A change to the business rule requires updating multiple callers.
- In a multithreaded environment, checking and then updating through separate calls also risks a race condition.

The object-oriented approach:

~~~java
account.withdraw(amount);
~~~

The caller sends **a meaningful request**; the object checks the conditions and performs the appropriate state transition. This is a practical application of the **Tell, Don't Ask** principle: prefer placing behavior alongside the data and invariants that the behavior manages.

Not every getter is bad. `balanceCents()` is very useful for displaying reports. The problem arises when callers use getters to **reimplement internal rules** and write back through uncontrolled setters.

## 7. Designing Methods Based on the Problem Domain

Comparison:

| Purpose | Less Meaningful API | Behavior-Describing API |
| --- | --- | --- |
| Deposit money | `setBalance(old + amount)` | `deposit(amount)` |
| Withdraw money | `setBalance(old - amount)` | `withdraw(amount)` |
| Confirm order | `setStatus(CONFIRMED)` | `confirm()` |
| Cancel order | `setStatus(CANCELED)` | `cancel(reason)` |
| Increase quantity | `setQuantity(old + n)` | `addQuantity(n)` |
| Turn on device | `setPower(true)` | `turnOn()` |
| Enroll in course | `setEnrolled(true)` | `enroll(student)` |
| Complete task | `setDone(true)` | `complete()` |

The names on the right are beneficial when the behavior **needs to check its own conditions**. If an API is purely data with no domain rules, creating too many verbose methods is not helpful either.

### What a Meaningful Operation Should Specify

- Conditions under which it is allowed to be called (preconditions).
- Successful effect on state (postconditions).
- Which invariants must be preserved.
- When errors are reported and via which exception or result type.
- Whether there are external side effects.
- Whether it can be called repeatedly (idempotency or an explicit policy).
- Which data the caller can read afterward.

For example, `cancel()` can be called multiple times and silently do nothing if already canceled, **or** throw an exception on the second call. Both policies can be valid; the class needs to choose a consistent contract.

## 8. Runnable Example: Encapsulating State Transitions

Save the file **`OrderLifecycleDemo.java`**:

~~~java
public class OrderLifecycleDemo {
    enum State {
        DRAFT, CONFIRMED, CANCELED
    }

    static final class Order {
        private final String code;
        private State state = State.DRAFT;

        Order(String code) {
            if (code == null || code.isBlank()) {
                throw new IllegalArgumentException("code required");
            }
            this.code = code.strip();
        }

        void confirm() {
            if (state != State.DRAFT) {
                throw new IllegalStateException("only draft can be confirmed");
            }
            state = State.CONFIRMED;
        }

        void cancel() {
            if (state == State.CANCELED) {
                throw new IllegalStateException("already canceled");
            }
            state = State.CANCELED;
        }

        String describe() {
            return code + " -> " + state;
        }
    }

    public static void main(String[] args) {
        Order order = new Order("  O-01  ");
        System.out.println(order.describe());

        order.confirm();
        System.out.println(order.describe());

        try {
            order.confirm();
        } catch (IllegalStateException ex) {
            System.out.println("rejected: " + ex.getMessage());
        }

        order.cancel();
        System.out.println(order.describe());
    }
}
~~~

~~~bash
javac -encoding UTF-8 OrderLifecycleDemo.java
java OrderLifecycleDemo
~~~

Stdout:

~~~text
O-01 -> DRAFT
O-01 -> CONFIRMED
rejected: only draft can be confirmed
O-01 -> CANCELED
~~~

If the class exposed an unrestricted `setState(State)`, callers could move an order from `CANCELED` back to `DRAFT` against intent. The `confirm()` and `cancel()` API expresses a **small state machine**:

~~~text
            confirm()
DRAFT ----------------> CONFIRMED
  |                         |
  | cancel()                | cancel()
  v                         v
CANCELED <--------------- CANCELED
~~~

In the example, `cancel()` allows cancellation from DRAFT or CONFIRMED; this is an **assumed rule**. In a real system, it may be necessary to block cancellation after shipping, store a cancellation reason, issue a refund, or check permissions.

**Encapsulation note:** Making the `state` field private is one part of the protection; more importantly, **there is no public setter that bypasses the state transition rules**.

## 9. Constructors Must Also Protect Invariants

If checks are only performed in methods while the constructor allows creating an invalid object, all subsequent conditions can easily break.

Example to avoid:

~~~java
class InventoryItem {
    private int stock;

    InventoryItem(int stock) {
        this.stock = stock; // Allows negative stock.
    }

    void take(int amount) {
        // The method might assume the initial stock is valid, when it is not.
    }
}
~~~

A better version must validate `stock >= 0` right at initialization, and every update method must preserve `stock >= 0`. The same invariant needs to be applied consistently across overloaded constructors and factory creation paths.

### Preventing Parameter Self-Assignment

In a constructor:

~~~java
class Item {
    private final String code;

    Item(String code) {
        this.code = code;
    }
}
~~~

`this.code` is the field, while `code` on the right-hand side is the parameter. Writing `code = code;` only assigns the parameter to itself and does not assign the field as intended. For a `final` field, the compiler can catch that the field has not been initialized; for a non-final field, the bug can silently leave the default value.

### Fail Fast and External Assignment

If a constructor throws an exception, the `new Item(...)` expression does not complete normally and does not provide a new reference to the caller. The statement:

~~~java
current = new Item(invalidCode);
~~~

does not assign a new reference to `current` if the right-hand side throws an exception. However, if the constructor has already logged, incremented a static counter, registered a callback, or performed other side effects before throwing, those side effects **do not automatically roll back**. Good encapsulation also requires avoiding leaking a partially initialized `this` reference outside.

## 10. Validation: Checking Arguments Before Mutating State

A meaningful operation method should report errors **before** leaving the state in an invalid form.

~~~java
void remove(int quantity) {
    if (quantity <= 0) {
        throw new IllegalArgumentException("quantity must be positive");
    }
    if (quantity > stock) {
        throw new IllegalStateException("not enough stock");
    }
    stock -= quantity;
}
~~~

This is an illustrative method in a class with a private field `stock` and the invariant `stock >= 0`. When `quantity <= 0` or the requested quantity exceeds available stock, the method throws an exception **before subtracting**.

Distinguish between:

- `IllegalArgumentException`: a parameter value violates the contract, such as a non-positive quantity.
- `IllegalStateException`: the operation cannot be performed due to the current state, such as insufficient stock.
- `NullPointerException`: can be an explicit policy when using `Objects.requireNonNull(...)` for an argument that must not be null.
- Checked exceptions: used when the operation has checked failure modes such as I/O that the API contract needs to represent.

There is no rigid formula forcing every domain model to use those exact exceptions. What matters is that the exception types and messages are meaningful and documented consistently in the API.

### The Risk of Partial Mutation

Example:

~~~java
void unsafeRemove(int quantity) {
    stock -= quantity;
    if (stock < 0) {
        throw new IllegalStateException("not enough stock");
    }
}
~~~

If an exception is thrown, `stock` **has already been reduced below zero**. Exceptions in Java do not automatically restore fields to their previous values. Good design generally **computes and validates first, then commits**, or implements genuine rollback when multiple steps must change.

## 11. Preventing Numeric Overflow Also Protects Invariants

An addition on `int` or `long` can **overflow** without throwing an error if the ordinary `+` operator is used.

Example:

~~~java
long balance = Long.MAX_VALUE;
balance = balance + 1; // Overflows to Long.MIN_VALUE.
~~~

If the invariant requires a non-negative balance, the overflowed result creates an invalid state. Using `Math.addExact` or `Math.subtractExact` can help detect overflow where appropriate.

~~~java
long updated = Math.addExact(balanceCents, amountCents);
balanceCents = updated;
~~~

If `Math.addExact` throws `ArithmeticException`, the field assignment **has not happened yet**. This is why you should **compute the new result into a local variable and assign the field only after the calculation succeeds** when reducing the risk of partial updates.

In real-world monetary problems, you also need to consider currency units, transaction limits, rounding policies, duplicate requests, and multithreaded consistency. `private` does not replace those safeguards.

## 12. Safe Getters and Getters That Expose State

A getter that reads a primitive value generally carries little risk:

~~~java
public int count() {
    return count;
}
~~~

However, a getter that returns a mutable reference can break encapsulation, even if the field is private:

~~~java
class Team {
    private final java.util.List<String> members =
            new java.util.ArrayList<>();

    public java.util.List<String> members() {
        return members; // Returns the internal mutable reference directly!
    }
}
~~~

Callers can do:

~~~java
team.members().clear();
~~~

and mutate the internal list **without going through a business method**. In this case, the private field **does not provide effective encapsulation**, because the API exposes an alias with permission to mutate state.

**Principle:** Do not inspect only the field's modifier. Inspect **the references that the public API returns** and the methods that can be called on the returned objects.

## 13. Defensive Copying: Accepting Mutable Data from Callers

When a constructor receives a mutable array or collection, assigning the reference directly to a private field can allow the caller to continue mutating the data inside the object.

~~~java
class Roster {
    private final java.util.List<String> names;

    Roster(java.util.List<String> names) {
        this.names = names; // Still shares the caller's ArrayList.
    }
}
~~~

If the caller performs `source.add("X")` after `new Roster(source)`, `Roster` also sees the new element. The field is `private final`, yet **the referenced List object is still mutable**.

An appropriate approach when the list contains immutable `String` elements is:

~~~java
this.names = java.util.List.copyOf(names);
~~~

`List.copyOf`:

- Disallows structural modification of the returned list via standard mutation methods.
- Rejects a null source and null elements.
- May reuse an already unmodifiable list; it does not always have to allocate a new container.
- **Does not deep copy** mutable element objects.

With `List<Person>` where `Person` is mutable, `List.copyOf` only protects the list structure; the Person objects inside can still be modified through other aliases.

## 14. Runnable Example: Protecting an Internal List

Save the file **`RosterEncapsulationDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class RosterEncapsulationDemo {
    static final class Roster {
        private final List<String> names;

        Roster(List<String> names) {
            Objects.requireNonNull(names, "names");

            List<String> copy = List.copyOf(names);
            if (copy.isEmpty()) {
                throw new IllegalArgumentException("roster must not be empty");
            }
            for (String name : copy) {
                if (name.isBlank()) {
                    throw new IllegalArgumentException("name must not be blank");
                }
            }

            this.names = copy;
        }

        List<String> members() {
            return names;
        }
    }

    public static void main(String[] args) {
        List<String> input = new ArrayList<>();
        input.add("Mai");
        input.add("An");

        Roster roster = new Roster(input);

        input.add("Binh");
        System.out.println("input=" + input);
        System.out.println("roster=" + roster.members());

        try {
            roster.members().add("Lan");
        } catch (UnsupportedOperationException ex) {
            System.out.println("cannot modify roster list");
        }

        System.out.println("roster size=" + roster.members().size());
    }
}
~~~

~~~bash
javac -encoding UTF-8 RosterEncapsulationDemo.java
java RosterEncapsulationDemo
~~~

Stdout:

~~~text
input=[Mai, An, Binh]
roster=[Mai, An]
cannot modify roster list
roster size=2
~~~

### Why Does This Example Preserve Encapsulation?

1. The constructor checks that the `names` reference is non-null.
2. `List.copyOf` creates/obtains a list that cannot be modified via normal mutation APIs, decoupling its structure from the mutable `ArrayList` passed in by the caller.
3. The class verifies that the list has elements and each name is non-blank.
4. After the caller adds `Binh` to `input`, the state of `Roster` remains `[Mai, An]`.
5. `roster.members().add("Lan")` is rejected with `UnsupportedOperationException`; the caller cannot arbitrarily mutate collection state through the accessor.
6. `String` is immutable, so in this example there is no issue with the caller modifying fields inside elements.

You could replace `members()` with `List.copyOf(names)` again, though that is unnecessary if `names` already references an unmodifiable list by contract and all elements are immutable. Avoid pointless repeated copying in frequently called APIs.

## 15. Arrays: `private` Does Not Prevent Reference Exposure

Arrays are mutable objects. If a constructor stores `input` directly or a getter returns `values` directly, callers can modify elements even though the field is `private final`. For `int[]`, one option is to **copy on input, validate on the copy, and copy on return**. For `Person[]`, `clone()` only copies the array references, not the mutable Person objects.

## 16. Runnable Example: Controlled Operations and Array Snapshots

Unlike a simple array-returning getter, this example both protects against two-way aliasing and provides **a validated update method** to maintain the invariant `0 <= score <= 100`.

Save **`ScorePolicyDemo.java`**:

~~~java
import java.util.Arrays;

public class ScorePolicyDemo {
    static final class ScoreSheet {
        private final int[] scores;

        ScoreSheet(int[] input) {
            if (input == null || input.length == 0) {
                throw new IllegalArgumentException("scores required");
            }
            int[] copy = input.clone();
            for (int score : copy) {
                validate(score);
            }
            scores = copy;
        }

        void replaceScore(int index, int next) {
            validate(next);
            scores[index] = next;
        }

        int[] snapshot() {
            return scores.clone();
        }

        private static void validate(int score) {
            if (score < 0 || score > 100) {
                throw new IllegalArgumentException("invalid score");
            }
        }
    }

    public static void main(String[] args) {
        int[] input = {70, 80};
        ScoreSheet sheet = new ScoreSheet(input);

        input[0] = -10;
        int[] outward = sheet.snapshot();
        outward[1] = -30;
        System.out.println(Arrays.toString(sheet.snapshot()));

        sheet.replaceScore(0, 95);
        try {
            sheet.replaceScore(1, 120);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected: " + ex.getMessage());
        }
        System.out.println(Arrays.toString(sheet.snapshot()));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ScorePolicyDemo.java
java ScorePolicyDemo
~~~

~~~text
[70, 80]
rejected: invalid score
[95, 80]
~~~

Input/output alias mutations do not touch the private array. `replaceScore(0,95)` succeeds; `replaceScore(1,120)` is rejected before mutating, so the second score remains 80. The example emphasizes **behavioral encapsulation**, while deep copying for object arrays, multidimensional arrays, lists/maps, mutable elements, and concurrency must be defined through a separate **ownership contract**, rather than relying solely on `clone()`.

## 17. Providing Behavior Instead of Exposing Mutable Collections

Sometimes users need to modify a list rather than merely view it. Instead of returning the internal mutable `List`, the class can provide:

~~~java
cart.addItem(sku, unitPriceCents, quantity);
cart.removeItem(sku);
cart.totalCents();
cart.itemsSnapshot();
~~~

Where:

- `addItem` validates the SKU, price, and quantity.
- `removeItem` decides what happens if the SKU does not exist.
- `totalCents` computes the total based on internal data.
- `itemsSnapshot` returns a snapshot that does not allow callers to modify collection state.

This design has the advantage of **centralizing update rules**. Callers do not need to know whether the class stores data in an `ArrayList`, `HashMap`, array, or another structure.

### Do Not Turn the API into a Disguised Collection of Setters

A nicely named method that still allows passing arbitrary state is not enough either:

~~~java
void updateEverything(int stock, long price, boolean sold) {
    this.stock = stock;
    this.price = price;
    this.sold = sold;
}
~~~

Without validating the relationship among the three values and without representing a clear domain operation, `updateEverything` still exposes overly broad control over state. **Method names do not substitute for contract design.**

## 18. Shopping Cart Example Exposing Only Valid Operations

Save the file **`ShoppingCartEncapsulationDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ShoppingCartEncapsulationDemo {
    record Line(String sku, long unitPriceCents, int quantity) {
        Line {
            if (sku == null || sku.isBlank()) {
                throw new IllegalArgumentException("sku required");
            }
            if (unitPriceCents < 0 || quantity <= 0) {
                throw new IllegalArgumentException("invalid price or quantity");
            }
        }

        long subtotalCents() {
            return Math.multiplyExact(unitPriceCents, quantity);
        }
    }

    static final class Cart {
        private final List<Line> lines = new ArrayList<>();

        void addItem(String sku, long unitPriceCents, int quantity) {
            Line candidate = new Line(sku, unitPriceCents, quantity);
            candidate.subtotalCents(); // Check for overflow before storing.
            lines.add(candidate);
        }

        long totalCents() {
            long total = 0;
            for (Line line : lines) {
                total = Math.addExact(total, line.subtotalCents());
            }
            return total;
        }

        List<Line> itemsSnapshot() {
            return List.copyOf(lines);
        }
    }

    public static void main(String[] args) {
        Cart cart = new Cart();
        cart.addItem("P01", 100, 2);
        cart.addItem("P02", 50, 1);

        List<Line> snapshot = cart.itemsSnapshot();
        System.out.println("lines=" + snapshot.size());
        System.out.println("total=" + cart.totalCents());

        try {
            snapshot.clear();
        } catch (UnsupportedOperationException ex) {
            System.out.println("snapshot cannot be cleared");
        }

        try {
            cart.addItem("BAD", 20, 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid item rejected");
        }

        System.out.println("total after errors=" + cart.totalCents());
    }
}
~~~

~~~bash
javac -encoding UTF-8 ShoppingCartEncapsulationDemo.java
java ShoppingCartEncapsulationDemo
~~~

Stdout:

~~~text
lines=2
total=250
snapshot cannot be cleared
invalid item rejected
total after errors=250
~~~

**Why does this design make sense for the scope of the example?**

- `lines` is private, and no method returns the raw mutable `ArrayList`.
- `addItem` validates a line item before adding it.
- `Line` is a record containing a `String` and primitives, so each line's data in this example has no mutable reference components.
- `List.copyOf(lines)` returns an unmodifiable list; callers cannot clear the cart by mutating the snapshot.
- When adding a line with an invalid quantity, `new Line(...)` throws an exception **before `lines.add`**, so the line count and total remain unchanged.
- `totalCents` contains the summation logic, reducing the need for callers to iterate, multiply, and sum externally.

**Limitations:** The example allows multiple lines with the same SKU and computes the total on demand. A real-world shopping cart might need to merge SKUs, check total payment capacity immediately upon adding, support conditional removal/updates, taxes, promotions, and concurrent updates. As business conditions expand, they should continue to be kept inside meaningful operations of Cart or an appropriate domain service.

## 19. How Does `private final` Differ from an Immutable Object?

~~~java
private final java.util.List<String> names;
~~~

The `final` keyword on a field prevents **reassigning the field reference** after initialization according to Java rules, but **does not automatically make the List object immutable**.

~~~java
final java.util.List<String> names = new java.util.ArrayList<>();
names.add("Mai"); // Valid: mutates the object.
 // names = new java.util.ArrayList<>(); // Invalid: reassigning a final variable.
~~~

Therefore:

- `private` restricts **where the field can be accessed directly**.
- `final` restricts **the ability to reassign the field/variable**.
- **Immutable object** is a property of state and public API design.
- **Defensive copying** is a technique to prevent external mutable aliases from breaking invariants.

A class can have every field marked `private final` and still be mutable through `List.add`, `StringBuilder.append`, or objects inside those fields. Do not treat private + final as a sufficient condition for deep immutability.

### Immutable Value Object

A value object can be designed with no state-mutating methods:

~~~java
public final class Quantity {
    private final int value;

    public Quantity(int value) {
        if (value < 0) {
            throw new IllegalArgumentException("negative quantity");
        }
        this.value = value;
    }

    public int value() {
        return value;
    }

    public Quantity plus(int amount) {
        if (amount < 0) {
            throw new IllegalArgumentException("negative addition");
        }
        return new Quantity(Math.addExact(value, amount));
    }
}
~~~

`plus(...)` creates a **new Quantity** instead of mutating the old object. This is also encapsulation: callers have a valid operation to produce a resulting value and have no way to break the invariant of the existing Quantity.

## 20. Record: Convenient for Value Objects, but Does Not Enforce Invariants on Its Own

In Java 17, `record` supports value-like data carriers. However, a record **does not automatically reject null or invalid values**.

~~~java
record Price(long cents) {
    Price {
        if (cents < 0) {
            throw new IllegalArgumentException("price must be nonnegative");
        }
    }

    Price plus(Price other) {
        java.util.Objects.requireNonNull(other, "other");
        return new Price(Math.addExact(cents, other.cents));
    }
}
~~~

This is an illustrative record. The compact constructor checks the invariant `cents >= 0`. `plus` describes the operation of adding a price with another Price and creates a valid new instance.

### A Record Is Not an Automatic Protection for Mutable Components

~~~java
record UnsafeRoster(java.util.List<String> names) {}
~~~

Callers can create `new UnsafeRoster(mutableList)` and then modify the list from outside; the record component accessor also returns a reference to that list. Final record fields do not prevent mutation of the list.

A record that wants deeper immutability can use a compact constructor:

~~~java
record SafeRoster(java.util.List<String> names) {
    SafeRoster {
        names = java.util.List.copyOf(names);
    }
}
~~~

With immutable `String` elements, the list structure cannot be modified in the example. With mutable elements, copying/ownership still needs to be considered at the element level. Do not use a record just for its concise syntax while ignoring invariants.

## 21. Does `private` Apply to Subclasses?

A subclass cannot directly use a superclass's private field as an inherited accessible member.

~~~java
class Parent {
    private int counter = 10;

    protected void incrementCounter() {
        counter++;
    }

    public int counter() {
        return counter;
    }
}

class Child extends Parent {
    void perform() {
        incrementCounter(); // Calls the protected operation.
        // counter++;        // Cannot access Parent's private field.
    }
}
~~~

This is an illustrative class. An object of type `Child` still has state managed by the `Parent` part, yet Child cannot freely modify Parent's private field. It must use the **operations permitted by Parent**.

### Why Not Make the Field `protected` for Convenience?

`protected int counter` gives subclasses much broader control to adjust state, which can cause a subclass to break the superclass's invariant. A **protected method with a contract** such as `incrementCounter()` is usually safer than a protected mutable field.

There is no absolute rule forbidding protected fields, but protected is an API extension decision for inheritance and easily creates future compatibility constraints.

### Nested Classes and Private Access

Nested classes in the same nest can access private members according to Java 17 rules. This does **not** turn private into package-private or public. The goal of private remains limiting the boundary of code trusted to manage implementation details, not isolating every line of code from all nested classes.

## 22. Should Every Field Be Kept `private`?

For mutable domain classes, private is usually a **good default**, though not a mandatory rule for every data type:

- Truly stable `public static final` constants can be made public.
- Java records have corresponding public component accessors by type contract.
- A data carrier with no significant business rules can use an appropriately simple structure.
- Frameworks may have access or mapping requirements; balance these with encapsulation and testability.
- In a library API, exposed mutable data can create commitments that are hard to change later.

The key point is **do not expose a mutable implementation detail if callers do not need permission to modify it**.

### Suggested API Design Guidelines

| Caller Need | Potentially Suitable API |
| --- | --- |
| View an integer/immutable value | Getter/query method |
| Request a state transition | Behavior-named methods: `confirm()`, `cancel()` |
| Adjust a quantity according to rules | `increase(...)`, `withdraw(...)` |
| View multiple elements | Unmodifiable snapshot or controlled iterator/query |
| Add/remove elements | `addItem(...)`, `removeItem(...)` |
| Create an object with invariants | Validating constructor/factory |
| Update multiple related properties | Method accepting a value object/command, validating atomically within the object's scope |
| Simply transfer data across layers | DTO/record with a clear contract, not necessarily many domain behaviors |

Do not turn encapsulation into hundreds of methods just to avoid having setters. Choose boundaries based on **who owns the invariant and who is responsible for upholding it**.

## 23. Separating Read APIs and Write APIs

An understandable design often distinguishes between:

**Query methods**: return information without modifying observable state, such as `balanceCents()`, `isConfirmed()`, `totalCents()`.

**Command methods**: instruct the object to change state in a controlled manner, such as `deposit(...)`, `confirm()`, `addItem(...)`.

This distinction is close to **Command–Query Separation (CQS)** at the method level and does not imply that a system-wide CQRS architecture is required.

### Query APIs Can Still Expose Mutable State

~~~java
List<Item> items() {
    return internalItems;
}
~~~

The method name suggests a query, yet if the result contains a mutable reference to internal state, callers can still modify the object. Therefore, you must evaluate **the return type and mutability permissions**, not just the method name.

### A Command Should Preserve Invariants Along Every Normal Path

If `complete()` can be called when the task is already canceled, the method should reject it or define a valid state transition. Arbitrary transitions of `status` to COMPLETE cannot be controlled if the class exposes an unchecked public setter.

## 24. Encapsulation and Atomicity: An Operation Can Consist of Multiple Steps

An operation such as transferring money between two Account objects needs to validate both sides, avoiding debiting the sender and then throwing an exception before crediting the recipient.

Anti-example:

~~~java
void transferUnsafe(Account from, Account to, long amount) {
    from.withdraw(amount);
    to.deposit(amount);
}
~~~

This is an **illustrative code snippet**. If `to.deposit(amount)` throws an exception after `from.withdraw(amount)` succeeds, the sender's money has already been deducted. Organizing code into two separate encapsulated methods does not automatically create an **atomic transaction across multiple objects**.

To be safe, you must determine:

- Is there permission to transfer, and is the balance sufficient?
- Is the recipient valid? Is there a balance limit?
- What happens if updating one side fails?
- Are there multiple concurrent threads or operations?
- Is there I/O, a database, or networking involved? Are transactions or idempotency needed?

In systems with a database, a **domain service/transaction boundary** can coordinate multiple objects to ensure consistency. For in-memory structures, synchronization and updating related elements must also be controlled. **Encapsulation protects local invariants; it does not automatically guarantee atomicity across multiple objects or processes.**

## 25. `private` Does Not Make a Class Thread-Safe

A private mutable field can still be updated from multiple threads through a public method:

~~~java
class Counter {
    private int value;

    public void increment() {
        value++;
    }

    public int value() {
        return value;
    }
}
~~~

`value++` is a read–compute–write operation, **not inherently atomic** across two threads. If both threads call `increment()` concurrently, updates can be lost. Private only restricts direct access; it **does not automatically solve race conditions, visibility, or happens-before guarantees**.

When an object is shared across multiple threads, consider:

- Immutability if the state does not need to change.
- Synchronization such as `synchronized` or locks used consistently.
- Appropriate atomic types when only simple operations are needed.
- Single-thread ownership or message passing when the architecture allows.

Do not protect only writes; queries reading the same state also need a consistent visibility strategy. You should not sprinkle `synchronized` arbitrarily on a few methods and assume all multi-field invariants are safe.

### Encapsulation Supports Concurrency, but Does Not Replace Concurrency Design

The advantage of a meaningful API is that there are **fewer paths that mutate state**, making it easier later to place synchronization or transactions around an entire operation. If public setters allow callers to perform read–compute–write themselves, the class has difficulty controlling a multi-step operation.

## 26. `private` Is Not Authentication, Authorization, or Data Security

Access modifiers primarily control **Java code access rules**. They are not a substitute for:

- Checking whether the caller is authorized to perform a transaction.
- User authentication.
- Role-based or resource-based authorization.
- Encryption of sensitive data.
- Preventing database overwrites outside the workflow.
- Validating data from networks, files, or reflection/frameworks.

A public method can be called by any caller code with access to invoke it in order to attempt an operation. If the business logic requires authorization, enforce permission checks at the proper boundary such as the service/API layer and design appropriate domain command permissions.

Reflection, serialization, and some runtime environments also have mechanisms to access data differently from reading fields directly using normal Java syntax, depending on access permissions/module policies. Therefore, **private fields aid encapsulation**, but should not be advertised as “secrets unreadable from any context”.

## 27. Choosing Where Business Logic Lives: Object or Service?

Not all rules have to live inside an entity:

- **Inside the object**: its intrinsic invariants, such as Quantity must be positive, Account must not allow withdrawing more than the balance in a simple model, and Order must not transition from CANCELED back to DRAFT.
- **Inside a value object**: validating and normalizing a single unit of data, such as `EmailAddress`, `Money`, or `DateRange`.
- **Inside a domain/application service**: rules involving multiple aggregates, repositories, authorization, transactions, or external services.
- **At the adapter/boundary**: parsing JSON, verifying input format, and mapping errors to HTTP/UI.

You should not “stuff” an email-sending service or database connection into a constructor just so an object can manage its entire lifecycle by itself. Conversely, you should not create entities with only getters/setters and push **all local invariants** out to services, allowing state to become invalid between calls.

### A Responsibility-Splitting Model

~~~text
HTTP/UI/CLI input
       |
       v
Validation/Mapping boundary
       |
       v
Application service --------> Authorization / transaction
       |
       v
Domain object --------------> confirm(), cancel(), withdraw()
       |
       v
Private fields + invariants
~~~

This diagram illustrates possible responsibilities; it is not a rule requiring every small Java program to use multiple architectural layers.

## 28. Testing the Public API Instead of Private Fields

A good test should ask: “Given this state and input data, does the **public operation** produce the right result/exception?” There is no need to use reflection to read private fields or change a field's modifier to public just for testing.

For example, for an Account with `deposit`, `withdraw`, and `balanceCents()`, tests should cover:

- The constructor allows a zero balance.
- The constructor rejects a negative balance.
- `deposit` with a positive amount increases the balance properly.
- `withdraw` within the available balance decreases it properly.
- `withdraw` exceeding the balance throws an error and **leaves the balance unchanged**.
- `deposit` with a non-positive amount throws an error.
- Overflowing addition throws an error and does not alter the balance.

### Standalone Test Program Without External Libraries

Save the file **`EncapsulationContractTestDemo.java`**:

~~~java
public class EncapsulationContractTestDemo {
    static final class Wallet {
        private long cents;

        Wallet(long cents) {
            if (cents < 0) {
                throw new IllegalArgumentException("negative balance");
            }
            this.cents = cents;
        }

        void deposit(long amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("invalid deposit");
            }
            cents = Math.addExact(cents, amount);
        }

        void withdraw(long amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("invalid withdrawal");
            }
            if (amount > cents) {
                throw new IllegalStateException("insufficient funds");
            }
            cents -= amount;
        }

        long balance() {
            return cents;
        }
    }

    static void assertEquals(long expected, long actual) {
        if (expected != actual) {
            throw new AssertionError(
                    "expected=" + expected + " actual=" + actual);
        }
    }

    static void expectInsufficient(Runnable operation) {
        try {
            operation.run();
        } catch (IllegalStateException expected) {
            System.out.println("insufficient funds rejected");
            return;
        }
        throw new AssertionError("Expected IllegalStateException");
    }

    public static void main(String[] args) {
        Wallet wallet = new Wallet(100);
        wallet.deposit(40);
        wallet.withdraw(15);
        assertEquals(125, wallet.balance());

        expectInsufficient(() -> wallet.withdraw(500));
        assertEquals(125, wallet.balance());

        System.out.println("Contract tests passed");
    }
}
~~~

~~~bash
javac -encoding UTF-8 EncapsulationContractTestDemo.java
java EncapsulationContractTestDemo
~~~

Stdout:

~~~text
insufficient funds rejected
Contract tests passed
~~~

This test uses only the constructor and methods, without accessing private fields. If you replace `Wallet`'s implementation from `long cents` to a `Money` value object while preserving equivalent public behavior, the test can continue verifying the contract. That is the benefit of **implementation hiding**.

In real-world projects, JUnit with `assertThrows`, `assertEquals`, property-based tests, and multithreaded testing can help cover many more cases. Inspecting private fields via reflection is not necessary.

## 29. Two-File Example: External Code Cannot Modify Private Fields

To observe the compiler enforcing access control directly, create a directory with two files:

~~~text
private-lab/
├── Counter.java
└── CounterClient.java
~~~

**`Counter.java`**:

~~~java
public final class Counter {
    private int count;

    public void increment() {
        count = Math.addExact(count, 1);
    }

    public int value() {
        return count;
    }
}
~~~

**`CounterClient.java`**:

~~~java
public class CounterClient {
    public static void main(String[] args) {
        Counter counter = new Counter();
        counter.increment();
        counter.increment();

        System.out.println("count=" + counter.value());

        // counter.count = -5; // Compile error: count is private.
    }
}
~~~

~~~bash
javac -encoding UTF-8 Counter.java CounterClient.java
java CounterClient
~~~

Stdout:

~~~text
count=2
~~~

Here `CounterClient` is **another top-level class** and is not in the same nest as `Counter`, so `counter.count` cannot be accessed directly, even when both files are in the same default package. Uncommenting the error line and compiling will be rejected.

**Java 17 nested class note:** If you place `Counter` as a nested class inside `CounterClient`, private nestmate rules can allow outer code to access private members. Therefore, the example uses **two top-level classes** to demonstrate the ordinary private boundary accurately.

## 30. Common Mistakes When Designing Private State

| Mistake | Consequence | How to Improve |
| --- | --- | --- |
| Making every field public | Callers modify directly, breaking invariants | Private fields and an intentional API |
| Private fields with unconditional public setters | Only hides access syntax, does not protect state | Validation or domain commands |
| Validating only in the constructor, ignoring mutators | Object is valid at creation but becomes invalid later | Check invariants on every update path |
| Assigning fields before validating | Exceptions can leave behind corrupted state | Validate/compute results before committing |
| Getters returning internal mutable Lists/arrays | Callers mutate fields via aliases | Snapshots/unmodifiable APIs/copies |
| Constructors holding mutable inputs directly | Callers mutate externally, silently changing the object | Defensive copying when needed |
| Using only `final` to protect a list | `final` does not prevent list mutation | Immutable elements / copying / ownership design |
| Records containing uncopied mutable components | Record still has deeply mutable state | Defensive copying or an explicit contract |
| Banning all getters | Callers cannot observe necessary data | Provide safe queries |
| Banning all setters | Unnecessarily complex API for DTOs/configs | Use validated setters when the domain allows |
| Putting all logic in services while entities have only getters/setters | Local invariants are easily bypassed | Move intrinsic rules back into the object |
| Doing all I/O and transactions in constructors | Hard to roll back, test, and reuse | Separate boundaries/services |
| Treating `private` as authorization | Fails to check real users/roles | Dedicated authorization |
| Treating `private` as thread-safety | Race conditions still occur | Synchronization, atomicity, immutability |
| Getters returning mutable objects also held by callers | Indirect aliasing causes state changes | Copy or expose operations only |
| Calling overridable methods inside constructors | Subclass fields may not be initialized yet | Avoid overridable dispatch during construction |
| Testing private fields with reflection everywhere | Tests depend on implementation details | Test public contracts and invariants |
| Widening access modifiers just to silence compiler errors | Over-exposes API and increases coupling | Define proper boundaries and operations |

## 31. A Process for Designing a Well-Encapsulated Class

**Step 1 — Write down the invariants.** For example, a shopping cart must not contain lines with negative quantity; a canceled order must not transition back to draft; an account must not have a negative balance.

**Step 2 — Place internal data in private fields.** Choose appropriate types; use `final` for fields that do not need reassignment, while evaluating the mutability of objects referenced by those fields.

**Step 3 — Protect object creation paths.** Constructors/factories validate inputs; normalize and copy data when needed. Avoid publishing `this` before initialization completes.

**Step 4 — List the behaviors callers truly need.** Do not generate setters for every field by default. Prefer commands whose names express domain operations.

**Step 5 — Separate queries and commands where valuable.** Queries return data safely; commands handle state changes and report errors clearly.

**Step 6 — Preserve invariants on every failure path.** Check before committing; watch out for overflow, side effects, concurrency, and multi-object operations.

**Step 7 — Control aliasing.** Do not return internal mutable arrays/lists, and do not retain callers' mutable inputs if independent ownership is desired.

**Step 8 — Design the exception contract.** Distinguish invalid input data, operations invalid in the current state, and system errors.

**Step 9 — Test through the API.** Happy paths, boundaries, invalid inputs, invalid call ordering, state preservation after exceptions, and external modification of inputs/snapshots.

**Step 10 — Revisit extensibility needs.** Use package-private/protected/public only when other components genuinely need them; consider API stability.

## 32. Exercise 1 — Fixing a Class with Only Getters and Setters

Problem statement:

~~~java
class BankAccount {
    private long balance;

    long getBalance() {
        return balance;
    }

    void setBalance(long balance) {
        this.balance = balance;
    }
}
~~~

Requirements:

- Build a constructor accepting a non-negative initial balance.
- Remove the setter that allows assigning an arbitrary balance.
- Add `deposit(long amount)` and `withdraw(long amount)`.
- All amounts must be positive; do not allow withdrawing beyond the balance.
- Do not allow addition to overflow silently; use `Math.addExact` where appropriate.
- A getter/query allows displaying the balance without modifying the field.
- Test that the balance remains unchanged after a rejected operation.

**Hint:** Refer to `BankAccountEncapsulationDemo`; the key point is **preserving invariants inside the class itself**, not just changing fields from public to private.

## 33. Exercise 2 — Order Status

Suppose `status` can take `DRAFT`, `CONFIRMED`, `SHIPPED`, `CANCELED`. Design:

- `confirm()` valid only when DRAFT.
- `ship()` valid only when CONFIRMED.
- `cancel()` valid in business-permitted states, disallowed after SHIPPED.
- No unconditional public `setStatus(State)`.
- Read-only `status()` query.
- Test all valid and invalid state transitions.

Designing a **state transition table** before writing code helps avoid missing an update path.

## 34. Exercise 3 — Protecting a Private Array

Given a class storing scores:

~~~java
class Report {
    private int[] scores;

    Report(int[] scores) {
        this.scores = scores;
    }

    int[] getScores() {
        return scores;
    }
}
~~~

Requirements:

- Reject null and empty arrays if the domain requires scores.
- Every score must be within `0..100`.
- Copy the array in the constructor and when returning it.
- Add a query method `average()` with a clearly stated rounding rule.
- Prove that mutating the input array or returned snapshot does not mutate Report's state.
- Explain why `private` and `final` **without copying** are still insufficient.

## 35. Exercise 4 — Operations Instead of Blanket Setters

An `InventoryItem` has private `stock` and private `reserved`. Invariants:

~~~text
stock >= 0
reserved >= 0
reserved <= stock
~~~

Design methods such as `restock(int quantity)`, `reserve(int quantity)`, `releaseReservation(int quantity)`, and `fulfillReservation(int quantity)` with concrete rules. Do not allow callers to set `stock` or `reserved` to arbitrary numbers.

**Hint:** `fulfillReservation` may need to decrease **both stock and reserved** in a single operation. Compute the new values and validate before assigning to avoid partial updates.

## 36. Exercise 5 — Public API of a Class Containing a List

A `Course` class has a private `List<Student> students` and returns the raw list from `students()`. Choose a design:

1. Read-only access to the list; return an appropriate unmodifiable snapshot.
2. Enrollment: add `enroll(Student)`, rejecting null or duplicates by defined identity or business ID.
3. Unenrollment: add `unenroll(Student)` with an explicit policy when not present.
4. If `Student` is mutable, analyze why `List.copyOf` does **not** protect the fields inside Student.

The goal is not “just use `List.copyOf` and call it done”, but to **define who has permission to mutate which part of the object graph**.

## 37. Frequently Asked Questions

### 37.1. If a field is private, can another object of the same class read it?

Yes, within the code of the declaring class itself—for example, `this.balance == other.balance` can read the private field on `other`. Private access rules are based on **class/nest context**, not just the `this` receiver.

### 37.2. Can a class in the same package read a private field?

Not merely by being in the same package. Only package-private fields are open to other classes in the same package under standard rules; `private` differs from package-private.

### 37.3. Must getters and setters be created for all private fields?

No. The API should reflect **which data needs to be observed** and **which operations are valid**. Not every field should have a setter. Getters returning mutable objects also require careful consideration.

### 37.4. Is a validating setter enough?

It can suffice for a single property; however, if there are invariants **involving multiple fields** or state dependencies, separate setters can allow invalid intermediate states. A meaningful method that updates multiple fields consistently is often more appropriate.

### 37.5. Is `private final List<T>` immutable?

Not automatically. `final` prevents the field reference from being reassigned; the List object can still be mutable, and elements of type T can be mutable. Ownership design, copying, and appropriate unmodifiable APIs are still required.

### 37.6. Is returning `Collections.unmodifiableList(list)` the same as copying?

Not entirely. An **unmodifiable view** can reflect changes to the backing list if the backing list is modified through another reference. `List.copyOf(list)` creates/returns an unmodifiable list whose structure is independent of edits to the source ArrayList as shown in the example, though it does not deep copy element objects. Choose based on whether you need a snapshot or a live view.

### 37.7. Does `private` protect against multiple threads modifying a field simultaneously?

No. Threads can still invoke public methods on the same object. Separate concurrency mechanisms are required.

### 37.8. Should business logic be placed in constructors?

A constructor should guarantee that the successfully created state is valid. Multi-step workflows, I/O, transactions, or external interactions are usually better suited to methods, factories, or services with clear contracts and proper resource lifecycle management.

### 37.9. Should immutable objects always be used?

Immutable objects are very useful for many value types (immutable Money, DateRange, Address), but not every domain object needs to be immutable. A shopping cart, order, or account may need to change state through controlled command methods.

### 37.10. Is using reflection to test private fields recommended?

There may be very specific situations, but regular behavior tests should verify the **public contract** and observable invariants. Overusing reflection couples tests to implementation details and reduces refactoring freedom.

## 38. End-of-Lesson Checklist

- [ ] I can distinguish **hiding fields** from **protecting invariants**.
- [ ] I understand that `private` restricts direct access but does not automatically make an object immutable.
- [ ] I know why arbitrary public setters can break encapsulation.
- [ ] I know how to name methods after behavior: `deposit`, `withdraw`, `confirm`, `cancel`.
- [ ] I can choose getters/queries when callers genuinely need to observe state.
- [ ] I know constructors must validate initial state.
- [ ] I preserve invariants across all normal and failure update paths.
- [ ] I use exceptions according to contract and do not assume exceptions roll back fields automatically.
- [ ] I know how to handle numeric overflow before assigning new values.
- [ ] I do not return internal mutable arrays/lists directly from getters when state needs protection.
- [ ] I know when defensive copying is needed on input and output.
- [ ] I distinguish shallow copy, deep copy, and unmodifiable view.
- [ ] I understand how a `final` reference differs from an immutable object.
- [ ] I know records may need validation/copying for mutable components.
- [ ] I understand subclasses cannot directly access a superclass's private fields.
- [ ] I know `private` does not automatically guarantee thread-safety or authorization.
- [ ] I know when a domain service/transaction coordinating multiple objects is necessary.
- [ ] I can write tests for public behavior, invalid state transitions, and failure paths.
- [ ] I can compile, run, and explain the Java 17+ programs in this lesson on my own.

**Conclusion:** Effective encapsulation is not “making every field private and generating all getters/setters”, but **making the object responsible for keeping its own state valid**. Use `private` to hide implementation details; place valid changes into behavior-describing methods; let callers read only necessary information without exposing mutable state. A small, clear, invariant-preserving API makes programs easier to test, easier to change internally, and less prone to bugs caused by external code mutating objects improperly.
