# Returning a New Object to Represent a Replacement Result in Java

Java **always passes arguments by value (*pass by value*)**. When passing a reference variable to a method, Java copies the **reference value**, without transferring the right to reassign the variable itself on the caller side. Therefore, if a method wants to propose an object to **replace** the object that a variable on the caller side is pointing to, the clear approach is to **return the resulting reference** so that the caller actively receives it and reassigns its own variable.

Core pattern:

~~~java
current = createReplacement(current);
~~~

Here, `createReplacement` computes or creates a result object and executes `return`; the assignment `current = ...` **takes place on the caller side**. This is completely different from a method writing `parameter = new Object()` inside its body and expecting the external `current` variable to change accordingly.

This lesson explains the mechanism, when to create a new object, how to design transformations that do not modify the input, handling mutable data, pitfalls regarding identity/`equals`, errors, and performance. Programs that have a file name can all be compiled/run standalone using **Java 17 or later**.

## 1. Problem: Why Does Reassigning a Parameter Not Change the Caller's Variable?

Before using an API that returns a new object, remember that **a parameter is the callee's own variable**, not a local variable of the caller. The snippet assumes `Box(int)` exists:

~~~java
static void replaceLocally(Box box) {
    box = new Box(99);
}
~~~

Calling `replaceLocally(current)` only makes `box` in the callee point to the new object; `current` still points to the old object. The callee has no right to assign to the caller's local variable through a parameter.

This lesson focuses on a solution with a clear contract: the callee **returns** the result object, while the caller **decides to assign, keep separately, or discard it**; if an immutable snapshot is desired, mutable child data must also be handled. The `current = transformed(current)` pattern expresses the assignment in the right place, without simulating pass-by-reference using an unnecessary holder.

## 2. Solution: Returning a New Object Reference

Define a method that **returns `Box`**:

~~~java
static Box createReplacement(Box current) {
    return new Box(99);
}
~~~

The caller receives the result:

~~~java
Box current = new Box(10);
current = createReplacement(current);
~~~

Execution flow:

~~~text
1. caller.current ----> Box #1 [value=10]
2. createReplacement(current) creates Box #2 [value=99].
3. return passes the reference value to Box #2 back to caller.
4. caller performs the assignment itself:
      current = <reference to Box #2>
5. caller.current ----> Box #2 [value=99]
~~~

The snippets above are only illustrative in a context where a `Box` class exists. The reference value **returned** from a method is the value of an expression; Java still does not pass a caller variable by reference.

The essence of this approach is a **clear protocol between the two sides**:

1. Callee: “I create/compute a result and return it.”
2. Caller: “I decide to keep the result, assign it to an existing variable or a new variable.”

The caller also has the right not to assign:

~~~java
Box before = new Box(10);
Box after = createReplacement(before);
~~~

At this point, `before` still points to the old object, while `after` points to the result object. Because of this, it is possible to keep history, compare before and after, or try out a change without “applying” it yet.

## 3. Complete Example: Parameter-Reassigning Method and Object-Returning Method

Create the file **`ReferenceReplacementDemo.java`**:

~~~java
final class Label {
    private final String text;

    Label(String text) {
        if (text == null || text.isBlank()) {
            throw new IllegalArgumentException("text không hợp lệ");
        }
        this.text = text;
    }

    String text() {
        return text;
    }
}

public class ReferenceReplacementDemo {
    static void ineffectiveReplace(Label label) {
        label = new Label("Mới");
        System.out.println("inside=" + label.text());
    }

    static Label replacement(Label old, String newText) {
        return new Label(newText);
    }

    public static void main(String[] args) {
        Label current = new Label("Cũ");
        Label oldAlias = current;

        ineffectiveReplace(current);
        System.out.println("caller before=" + current.text());

        current = replacement(current, "Mới");
        System.out.println("caller after=" + current.text());
        System.out.println("old alias=" + oldAlias.text());
        System.out.println("same reference=" + (current == oldAlias));
    }
}
~~~

Run in the directory containing the file:

~~~bash
javac -encoding UTF-8 ReferenceReplacementDemo.java
java ReferenceReplacementDemo
~~~

**Exact stdout:**

~~~text
inside=Mới
caller before=Cũ
caller after=Mới
old alias=Cũ
same reference=false
~~~

**Explanation:**

- `ineffectiveReplace` creates `Label("Mới")` and assigns to **its own parameter**, so inside it prints `Mới`, while `main`'s `current` still prints `Cũ`.
- `replacement` returns a new `Label`. It is the statement `current = replacement(...)` **in `main`** that actually assigns the `current` variable to the new object.
- `oldAlias` still references the old object. Reassigning `current` **does not automatically update** all variables holding the old object.
- `current == oldAlias` is `false` because the method uses `new Label(...)` to create a different instance.

This example intentionally keeps the `Label` class simple and immutable: the `text` field is `final`, and `String` is an immutable type. Therefore, we clearly see the effect of **reference replacement** without confusing it with modifying state inside the object.

**Note:** the `old` parameter in `replacement` is not read because the example only illustrates the operation of “replacing with another value”. In a real API, if the result does not depend on the old object at all, the name and signature `new Label(newText)` or a factory that does not accept `old` may be simpler. The following examples will use the old data to compute the new object.

## 4. Reference Copies, New Objects, and Return Values

Accurately distinguish the four expressions:

| Expression | Does it create a new object? | Does it reassign the caller's variable? |
| --- | --- | --- |
| `param = other;` in a method | Not necessarily | No |
| `param = new Box(5);` in a method | Yes, a new `Box` | No |
| `return new Box(5);` in a method | Yes, a new `Box` | Not yet; only returns the result |
| `current = makeBox();` in the caller | Depends on `makeBox` | Yes; the assignment is in the caller |

**Very important point:** `return` **does not automatically assign** the result to a variable with the same name as the parameter in the caller. It returns a reference value; the caller must **use that result itself**.

Example:

~~~java
current = transform(current); // Keep and apply the result.
Box candidate = transform(current); // Keep the result alongside.
transform(current); // Discard the result if there is no use for it.
~~~

The snippet above is illustrative, assuming `transform` returns `Box`. For a method designed to be pure without modifying the input object, the last call still executes the computation/creation of the result, but the result is discarded; the state of `current` does not change.

One should not conclude that “every method with `return Box` creates a new object”: it may return `this`, return a cached object, return the old parameter, or return an existing instance. If the contract requires **new identity**, the implementation must actually guarantee that; if it only requires the **result value**, reusing an immutable instance may be allowed.

## 5. Transformations That Do Not Modify the Input: Immutable Records

A common design is to create an immutable **value object**. Instead of updating the amount inside an existing object, we return **a new version representing the balance**.

In Java 17, `record` is a convenient choice for small data. Create the file **`ImmutableBalanceDemo.java`**:

~~~java
record Balance(String accountId, long cents) {
    Balance {
        if (accountId == null || accountId.isBlank()) {
            throw new IllegalArgumentException("Mã tài khoản không hợp lệ");
        }
        if (cents < 0) {
            throw new IllegalArgumentException("Số dư không được âm");
        }
    }

    Balance deposit(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Số nạp phải dương");
        }
        return new Balance(accountId, Math.addExact(cents, amount));
    }

    Balance withdraw(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Số rút phải dương");
        }
        if (amount > cents) {
            throw new IllegalArgumentException("Không đủ số dư");
        }
        return new Balance(accountId, cents - amount);
    }
}

public class ImmutableBalanceDemo {
    public static void main(String[] args) {
        Balance original = new Balance("A-01", 1000);
        Balance alias = original;

        Balance next = original.deposit(250);
        System.out.println("old=" + original);
        System.out.println("next=" + next);
        System.out.println("same instance=" + (original == next));
        System.out.println("alias still old=" + (alias == original));

        Balance current = original;
        current = current.deposit(500);
        System.out.println("current=" + current);
        System.out.println("old after assign=" + original);

        try {
            current = current.withdraw(2000);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected=" + ex.getMessage());
        }
        System.out.println("after failed=" + current);
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 ImmutableBalanceDemo.java
java ImmutableBalanceDemo
~~~

**Exact stdout:**

~~~text
old=Balance[accountId=A-01, cents=1000]
next=Balance[accountId=A-01, cents=1250]
same instance=false
alias still old=true
current=Balance[accountId=A-01, cents=1500]
old after assign=Balance[accountId=A-01, cents=1000]
rejected=Không đủ số dư
after failed=Balance[accountId=A-01, cents=1500]
~~~

### What Is Changed?

- `original.deposit(250)` **does not modify `original`**. It uses the `accountId` and `cents` data from the old record to create `new Balance(...)`, and then returns the result.
- `next` receives the new object with `cents = 1250`. `original` still has 1000.
- `current = current.deposit(500)` performs the **reassignment of the `current` variable in the caller** to the new object with 1500. It does not modify or “delete” `original`.
- `alias` still holds the old reference, so `alias == original` is `true`.
- With `withdraw(2000)`, the method throws an exception **before returning a value**. Because the right-hand side does not complete normally, the assignment `current = ...` does not occur, so `current` still references the balance of 1500.

### Contract of a Method Returning a Replacement

`deposit(amount)` has the contract:

~~~text
Input:
    amount > 0
    cents + amount is within the long range

Success result:
    result.accountId == old.accountId according to String.equals
    result.cents == old.cents + amount
    the object receiving the call is not modified

Error cases:
    amount <= 0 -> IllegalArgumentException
    long overflow -> ArithmeticException
~~~

This is an **illustrative specification**, not Java syntax. In the program, `Math.addExact` throws `ArithmeticException` if the `long` addition overflows. The constructor of the new instance proceeds to check the invariants.

A record automatically has `toString()`, `equals()`, and `hashCode()` matching its components; that is why stdout displays in the form `Balance[accountId=..., cents=...]`. With a record containing one `String` and one `long`, the example avoids the issue of mutable child elements.

**This is a balance value model for learning purposes, not a real banking transaction.** In a system with persistence/concurrency, returning a new value instance does not automatically deduct money from the persistent data source or resolve synchronization across multiple updaters.

## 6. Returning an Object Does Not Necessarily Modify Old State

Distinguish between two API styles:

~~~java
// Example A: mutable object
account.depositInPlace(100);

// Example B: immutable-style transformation
account = account.withDeposit(100);
~~~

These are **illustrative calls**; there is no corresponding `account` class defined in this snippet. Style A typically intentionally **modifies the object itself** that `account` points to; Style B typically **returns a result object** and requires the caller to reassign if it wants to apply the change.

Comparison table:

| Criterion | In-place modification (*in-place*) | Returning a replacement object |
| --- | --- | --- |
| Old object | May be updated | Should remain unchanged if the design is non-mutating |
| Caller variable | No need to reassign to observe field changes | Needs reassignment for that variable to point to the result |
| Aliases to the old object | Typically see the modifications | Continue to see the old value |
| Testing | Check before/after state | Compare the new result and input immutability |
| State history | Must capture a separate snapshot | Can retain the old version |
| Identity management | Keeps the same object | May produce a new identity |
| Cost | May reduce allocations | May create additional objects/structures |

Neither choice is always better. For entities with identity and external resources, **intentional in-place modification** is sometimes appropriate. For configurations, coordinates, value ranges, or data requiring predictable results, **returning a replacement** is often easier to reason about and test.

In particular, an API designed to return a new object **should not silently modify the input object before returning** if it has promised no side effects.

## 7. Coordinate Example: Transformations and Method Chaining

A simple coordinate object can have a `move(dx,dy)` method that returns a new point, instead of updating the coordinates of the initial point.

Create the file **`ImmutablePointDemo.java`**:

~~~java
record Point(int x, int y) {
    Point move(int dx, int dy) {
        return new Point(
                Math.addExact(x, dx),
                Math.addExact(y, dy));
    }
}

public class ImmutablePointDemo {
    public static void main(String[] args) {
        Point start = new Point(1, 2);
        Point moved = start.move(3, -1);
        Point finalPoint = moved.move(0, 5);

        System.out.println("start=" + start);
        System.out.println("moved=" + moved);
        System.out.println("final=" + finalPoint);
        System.out.println("equal start=" + start.equals(new Point(1, 2)));
        System.out.println("same ref=" + (start == moved));
    }
}
~~~

Run:

~~~bash
javac ImmutablePointDemo.java
java ImmutablePointDemo
~~~

Stdout:

~~~text
start=Point[x=1, y=2]
moved=Point[x=4, y=1]
final=Point[x=4, y=6]
equal start=true
same ref=false
~~~

`start.move(3,-1)` returns a new object `(4,1)`, `moved.move(0,5)` returns another new object `(4,6)`, while `start` remains `(1,2)`.

Calls can be chained:

~~~java
Point destination = start.move(3, -1).move(0, 5);
~~~

Because each call to `move` returns a `Point`, the next call runs on the previous result. The strength is that each step **has a clear output value** and does not unexpectedly affect the `start` object.

**Note:** `start.equals(new Point(1,2))` is `true` because the two records are equal by component values; `start == moved` is `false` because these are two different instances created with `new`. `equals` and `==` cannot be used interchangeably at will.

## 8. Keeping the Old Object as a “Previous Version” Instead of Losing History

When a method does not modify the input, the caller can retain multiple versions:

~~~java
Balance v1 = new Balance("A-01", 1000);
Balance v2 = v1.deposit(300);
Balance v3 = v2.withdraw(100);
~~~

After these three lines:

~~~text
v1 --> Balance(..., cents=1000)
v2 --> Balance(..., cents=1300)
v3 --> Balance(..., cents=1200)
~~~

This is an illustrative snippet using the record from Section 5. Each variable stores a **different observable value**. If instead you always write `current = current.deposit(...)`, the `current` variable only holds the latest version, though there may still be other references holding old versions.

The ability to retain old versions is useful for:

- Interfaces with **undo/redo** or before-and-after comparison.
- Reducer-style state handling: `nextState = reduce(previousState, action)`.
- Configuration rules with multiple variants.
- Business testing: computing results from a prior state without having to revert it manually.

However, creating a new immutable object does not automatically create a **persistent history**. If an application wants to save versions across restarts, it still needs appropriate storage; if child data is mutable and shared, an old “version” may not be as independent as expected.

## 9. Important Pitfall: A New Object Can Still Share Mutable Child Data

Suppose a class contains a `List<String>` field. A method that returns a new object but **reuses the same mutable list** can cause the two objects to share state.

Risky example:

~~~java
class UnsafeCart {
    private final java.util.List<String> items;

    UnsafeCart(java.util.List<String> items) {
        this.items = items;
    }

    UnsafeCart withSameItems() {
        return new UnsafeCart(items);
    }
}
~~~

This is an **illustrative class definition**, without `main`. Even though `withSameItems()` uses `new UnsafeCart(...)`, both instances still hold **the same list object**. If outside code still holds a reference to the list and calls `items.add(...)`, the observable state of both instances changes together.

**Creating a new wrapper object does not equate to a deep copy.** It is necessary to check which child structures are shared, whether elements are mutable, and who is permitted to update them.

### When the Input Is an Array

A constructor that receives `int[] numbers` and assigns `this.numbers = numbers` also only stores a copy of the **array reference value**. If the caller modifies `numbers[0]`, the new object still reads the same changed element.

One option is defensive copying:

~~~java
this.numbers = java.util.Arrays.copyOf(numbers, numbers.length);
~~~

This line is illustrative inside a constructor that has a matching `numbers` field. For arrays of primitive types, copying elements separates the data; for arrays of mutable objects, an array copy can still **share the element objects**.

## 10. Complete Example: Returning a New Cart and Copying the List

We use `record CartSnapshot` to hold a list of product names. Each `add` operation returns a new snapshot, while the old snapshot remains unchanged. Create the file **`CartSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

record CartSnapshot(List<String> items) {
    CartSnapshot {
        items = List.copyOf(items);
    }

    CartSnapshot add(String item) {
        Objects.requireNonNull(item, "item");
        List<String> updated = new ArrayList<>(items);
        updated.add(item);
        return new CartSnapshot(updated);
    }
}

public class CartSnapshotDemo {
    public static void main(String[] args) {
        List<String> input = new ArrayList<>(List.of("Bút"));
        CartSnapshot original = new CartSnapshot(input);
        CartSnapshot updated = original.add("Vở");

        input.add("Thước");

        System.out.println("original=" + original.items());
        System.out.println("updated=" + updated.items());
        System.out.println("input=" + input);
        System.out.println("same ref=" + (original == updated));

        try {
            original.items().add("Tẩy");
        } catch (UnsupportedOperationException ex) {
            System.out.println("cannot edit snapshot");
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 CartSnapshotDemo.java
java CartSnapshotDemo
~~~

**Stdout:**

~~~text
original=[Bút]
updated=[Bút, Vở]
input=[Bút, Thước]
same ref=false
cannot edit snapshot
~~~

### Why Does the Old Version Not Change?

- The record's compact constructor executes `items = List.copyOf(items)`: the snapshot holds a **list that does not support modification via its API**, created from the input contents according to the `List.copyOf` contract.
- `add("Vở")` creates a temporary mutable `ArrayList` containing the old elements, adds `"Vở"`, and then creates a **new `CartSnapshot`**. The new snapshot's constructor again uses `List.copyOf` to keep the observable list fixed.
- The caller modifies `input.add("Thước")` **after** creating the first snapshot. Because the snapshot has copied the elements into a structure unaffected by additions to `input`, `original.items()` is still `[Bút]`.
- `original.items().add("Tẩy")` throws `UnsupportedOperationException`, because the list inside the snapshot does not allow modification via its API.
- `original == updated` is `false` because these are two separate record instances.

**Important boundary:** `List.copyOf` performs a **shallow copy of element references**; it does not create a deep copy of each object in the list. The example uses immutable `String`s, so independence is sufficiently clear. If the list contains `MutableItem`, both snapshots can still hold references to the same `MutableItem`; achieving deep independence requires designing copying or immutability at the element level.

`List.copyOf` does not accept **null elements**. In the example, `new CartSnapshot(null)` is also invalid; `null` checking and more detailed error messages can be added according to the actual API contract.

## 11. `withX(...)`: Designing an API That Returns a Replacement Object

A common naming convention for immutable data types is `withName`, `withStatus`, `withEmail`, ...: returning a version carrying a new value for **one part of the state**, while keeping the other parts.

Illustrative example:

~~~java
record UserProfile(String name, String city) {
    UserProfile withCity(String newCity) {
        return new UserProfile(name, newCity);
    }
}
~~~

Caller:

~~~java
UserProfile oldProfile = new UserProfile("An", "Huế");
UserProfile newProfile = oldProfile.withCity("Đà Nẵng");
~~~

This snippet is a valid illustration in a project that declares the `UserProfile` record. Both variables can coexist and hold two different city values. However, the name `withCity` is only a **design convention**, not special syntax automatically enforced by Java.

Creating an additional object can be avoided when the value does not change:

~~~java
UserProfile withCity(String newCity) {
    if (java.util.Objects.equals(city, newCity)) {
        return this;
    }
    return new UserProfile(name, newCity);
}
~~~

This is an **alternative implementation**, which cannot coexist with the `withCity(String)` above in the same record. When returning `this`, it **does not create a new instance**; therefore, one must distinguish between a contract that “returns the **resulting version value**” and a contract that “**always** creates a new identity”. For immutable data types, allowing `this` to be returned when nothing changes is often reasonable, though not a mandatory rule.

If the record has business domain invariants, they should be checked in the constructor so that all `withX` paths maintain them.

## 12. A Return Value Is Not an “Output Passed by Reference”

Consider two approaches:

~~~java
// A: update inside a shared object
static void appendBang(StringBuilder target) {
    target.append("!");
}

// B: return a new value
static String appendBang(String source) {
    return source + "!";
}
~~~

These are two illustrative methods with the same name but different parameter types, so they can be overloaded if placed in a suitable class.

In A, Java still **passes the reference value** to `StringBuilder`. The method modifies **the referenced object itself** via `append`, so the caller observes the change without reassigning the variable.

In B, `String` is immutable; the method returns a resulting string. A caller that wants to use the new value must write:

~~~java
String message = "Java";
message = appendBang(message);
~~~

Neither approach uses a mechanism where “the callee receives the right to reassign the caller's variable”. The difference is **modifying a shared object** versus **returning a replacement value for the caller to keep itself**.

When naming APIs, you can use `appendInPlace` or `withSuffix` if you need to make the behavioral difference explicit, instead of leaving users to guess from overloads.

## 13. Not Assigning the Result: A Very Common Mistake

Suppose there is an immutable method:

~~~java
Balance deposit(long amount) {
    return new Balance(accountId, Math.addExact(cents, amount));
}
~~~

This snippet only extracts the idea from the `Balance` record; the constructor in Section 5 also checks the necessary conditions.

If the caller writes:

~~~java
Balance current = new Balance("A-01", 1000);
current.deposit(200); // The result is discarded.
System.out.println(current.cents()); // 1000
~~~

then `current` still points to the initial object; the method **does not update the state of the old object**. This mistake is similar to many immutable APIs such as:

~~~java
String name = "  An  ";
name.trim(); // Discarding the result leaves name still as "  An  ".
~~~

With `String`, `trim()` returns a string result rather than modifying the existing `String` object.

The correct approach when wanting to apply it:

~~~java
current = current.deposit(200);
name = name.trim();
~~~

**Review signal:** if a method is designed without side effects and **returns a new object**, a call that ignores the result is usually worth inspecting. However, not every method returning an object requires the caller to retain the result; you must rely on the specific contract.

## 14. Errors While Computing a New Version: Keeping the Old Version Intact

One advantage of a result-creating method that **does not modify the input** is that it can compute/validate before publishing the new version.

Example `Balance.withdraw`:

~~~java
Balance withdraw(long amount) {
    if (amount <= 0) {
        throw new IllegalArgumentException("Số rút phải dương");
    }
    if (amount > cents) {
        throw new IllegalArgumentException("Không đủ số dư");
    }
    return new Balance(accountId, cents - amount);
}
~~~

This is a method excerpt from the complete record. When calling:

~~~java
current = current.withdraw(2000);
~~~

If `current.cents() == 1500`, the method throws an exception before returning a result. The caller's assignment `current = ...` **does not complete**, because the right-hand side fails; `current` still retains the old reference.

However, its limitation must be stated clearly: this is **not an automatic Java transaction/rollback**. If the method body already modified the input, sent a notification, wrote to a file, or updated a database **before throwing an exception**, those side effects may still persist. The property of “failing without changing the old value” is only reliable if the implementation genuinely **does not touch shared state** or has an appropriate rollback mechanism.

A method with `return new ...` should not be described as “pure” if, during result creation, it also performs I/O or modifies global state.

## 15. `null` and the Contract of a Replacement Result

When a method returns an object, it is necessary to clearly specify whether it can return `null`. For example:

~~~java
static String normalize(String raw) {
    if (raw == null) {
        return null;
    }
    return raw.strip();
}
~~~

This is an illustrative method; it accepts null and returns null by convention. The caller can assign:

~~~java
String name = normalize(name);
~~~

However, if the result can be null, the caller must know before calling another method. Another option is to reject null with `Objects.requireNonNull(raw)` or return `Optional<String>` in APIs where “no value” is a valid situation. **There is no single null policy for all APIs.**

For operations replacing an object holding required state, it is usually best to guarantee that the result is **non-null and valid**. Otherwise, `current = replacement(current)` could turn the caller's variable into `null` and cause failures in subsequent steps.

A clear way to write this in Javadoc:

~~~java
/**
 * Returns a new Balance with the deposited amount.
 *
 * @param amount the deposit amount, must be positive
 * @return a new, non-null Balance; the object receiving the call is unchanged
 * @throws IllegalArgumentException if amount is not positive
 * @throws ArithmeticException if the long addition overflows
 */
~~~

This is an **illustrative Javadoc snippet**, not a standalone method. Documentation must accurately reflect the implementation.

## 16. Identity, `==`, `equals`, and Replacement Results

A method with `return new Point(...)` creates a **different object** according to instance creation expression semantics. Therefore:

~~~java
Point a = new Point(1, 2);
Point b = a.move(0, 0);

System.out.println(a == b);      // false, because move uses new Point.
System.out.println(a.equals(b));  // true, because the components are the same.
~~~

This is an illustrative snippet using the `Point` record from Section 7. The two objects have different references but are equal by value.

For APIs that may `return this` when the content does not change, you must not use `a != b` to assume by default that “data has changed”:

~~~text
a == b    : asks whether they are the same instance?
a.equals(b): asks whether they have the same value according to the class's contract?
~~~

A good value object type can focus on **value-based `equals`**. An entity with its own identity may need different rules. When designing `withX` methods, you should not rely on `==` to distinguish business state if the API does not guarantee a new identity on every call.

### Note on Collections and Wrappers

Some library APIs such as `List.copyOf` may **reuse** an already-unmodifiable list instead of creating a different object in every case. Wrappers or cached values also have unpredictable identity. **Only use `==` if you genuinely want to ask about identity and the contract permits relying on it.**

Program correctness should be based on **guaranteed behavior and state**, not on the assumption that every “copy” operation allocates a different object.

## 17. Returning Multiple Values or Multiple Replacement Objects

When a transformation needs to provide multiple pieces of information, it can return a **result object** instead of trying to modify the caller's parameter variables.

Example:

~~~java
record UpdatedUser(String name, String email) {
}

static UpdatedUser updateContact(String name, String email) {
    return new UpdatedUser(name.strip(), email.strip());
}
~~~

This is an illustrative snippet, assuming both arguments are non-null. The caller can do:

~~~java
UpdatedUser result = updateContact("  An  ", "  an@example.org ");
String updatedName = result.name();
String updatedEmail = result.email();
~~~

Instead of expecting a `void update(String name, String email)` method to cause **two String variables of the caller** to be reassigned, the API returns an object representing the **two result values**. Because `String` is immutable, this simple record is easy to understand, though a production API needs additional email address validation as required.

Similarly, for integer division producing a quotient and remainder, a `record DivisionResult(int quotient,int remainder)` is usually clearer than trying to create two “output parameters” using primitive variables.

## 18. Performance: Is Creating a New Object Expensive?

Possibly. Creating many new objects can lead to **memory allocation**, garbage collection pressure, and data copying. However, this needs to be evaluated in actual context:

- The JVM has optimizations such as *escape analysis* and techniques to eliminate intermediate allocations in certain cases; one should not assume every `new` always corresponds to a separate measurable physical allocation.
- For small and immutable objects, the benefits of clarity and reduced mutation bugs can outweigh a small allocation cost.
- For large data structures, **copying the entire collection after every update** can be expensive, especially in a loop with many iterations.
- Immutable data structures with *structural sharing* can reuse unchanged parts instead of copying every node.
- Data with identity, resources that need to be closed, or managed shared state may not be suited to a strategy of always replacing the object.

Example:

~~~java
CartSnapshot cart = new CartSnapshot(java.util.List.of());
for (String item : incomingItems) {
    cart = cart.add(item);
}
~~~

This is an illustrative snippet in a context with a suitable `incomingItems`. The `CartSnapshot.add` implementation in Section 10 creates a temporary list and copies elements on every addition; with large amounts of data, this approach may not be optimal. You can collect changes into a temporary builder/list and then freeze them into a snapshot **once** after finishing.

**Principle:** prioritize a correct design and clear contract, then measure with benchmarking/profiling if performance is a real issue. Do not alter an API based on guesses about memory without data.

## 19. Replacement Objects and Concurrent Programming

Immutable data types help reduce many bugs caused by **concurrently modifying the same object**, yet **reassigning a reference shared across multiple threads** still requires guarantees on visibility and atomic operations when there are concurrent updates.

Conceptual example:

~~~java
Balance next = current.deposit(100);
current = next;
~~~

In a single thread, assigning `current` is normal. However, if `current` is a shared field and **two threads simultaneously read–compute–write** without synchronization, one update can be overwritten by the other update.

One option is `AtomicReference<Balance>` with a side-effect-free update function:

~~~java
java.util.concurrent.atomic.AtomicReference<Balance> current =
        new java.util.concurrent.atomic.AtomicReference<>(
                new Balance("A-01", 1000));

Balance after = current.updateAndGet(old -> old.deposit(100));
~~~

This is an **illustrative snippet**, using the `Balance` record declared in Section 5. `updateAndGet` performs the reference update using an appropriate atomic mechanism and may **evaluate the lambda multiple times** under contention. Therefore, the transformation function should have no side effects and should not assume it runs only once.

**Important warning:** the `AtomicReference` example only illustrates in-memory state management. It **does not** replace database transactions or handle money safely in a real-world system.

Distinctions to remember:

1. **Immutable objects** ensure the old version is not modified.
2. **Proper publication** ensures other threads see the published state.
3. **Atomic updates** prevent two threads from accidentally overwriting each other's results when replacing the reference at the same time.
4. **Business/transaction management** addresses broader rules, which do not arise automatically from returning a new object.

## 20. Clear API Design: Method Names and Contracts

A method that returns a replacement object should make clear:

- **Which input data is read?** Is the entire old object used, or only a few components?
- **Is the input object modified?** If the API follows an immutable style, the promise “do not modify the input” must genuinely hold even for mutable child data.
- **Is the result always non-`null`?** If not, how should the caller handle it?
- **Is the result guaranteed to be a new instance?** Or can it return `this` when unchanged?
- **Which exceptions can be thrown?** If an error occurs, what happens to the old object and external side effects?
- **Are child objects shared?** Is a shallow copy, defensive copy, or deep copy needed?
- **What must the caller do with the result?** Does it need to reassign a variable, store it in a collection, or pass it on to the next step?
- **Are there concurrency/transaction constraints?** Especially with shared state.

Names like `withStatus`, `moved`, `updated`, `copyWith`, and `next` can help signal the result-returning style; whereas names like `setStatus`, `appendInPlace`, and `mutate` usually suggest in-place updates. These are only **conventions**, not mandatory standards. Always combine them with the return type and documentation.

### Javadoc Illustration for the Immutable Style

The following example declares a complete `record`. The constructor validates the email; `withEmail` creates and returns a new instance without modifying the old instance:

~~~java
record UserProfile(String email) {
    UserProfile {
        if (email == null || email.isBlank() || !email.contains("@")) {
            throw new IllegalArgumentException("Email không hợp lệ");
        }
    }

    /**
     * Creates a new version with an updated email address.
     *
     * Does not modify the state of the current object.
     *
     * @param newEmail the new email, must be non-null and valid
     * @return the resulting version, non-null
     * @throws IllegalArgumentException if newEmail is invalid
     */
    UserProfile withEmail(String newEmail) {
        return new UserProfile(newEmail);
    }
}
~~~

When calling `UserProfile updated = original.withEmail("new@example.com");`, `updated` holds the new email and `original` still keeps the initial email. Invalid email cases are detected by the constructor via `IllegalArgumentException`; the `withEmail` method inherits this exact validation rule.

## 21. Common Mistakes

| Mistake | Why it is wrong | How to handle it |
| --- | --- | --- |
| Assigning `param = new Type(...)` and expecting the caller's variable to change | Only the parameter variable is reassigned | `return` the result and assign in the caller |
| Calling `current.withX(...)` while discarding the result | The method does not modify the old object | Use `current = current.withX(...)` when wanting to apply it |
| Assuming `return obj` always creates a new object | It may return the same instance | Read the identity contract rather than inferring from the return type |
| Creating a new wrapper object and thinking everything was deep-copied | Reference fields may point to the same mutable data | Defensively copy the data that needs independence |
| Writing `new ArrayList<>(source)` and thinking all element objects are copied | Only element references are copied | Check shallow/deep copy |
| Using `==` to decide whether two result values are equal | `==` compares identity for references | Use `equals` according to value semantics |
| Using `List.copyOf` while wanting to mutate the resulting list directly | The list does not support mutation via its API | Create a temporary list and return a new snapshot |
| Being confident old data is unchanged even though the method already wrote to DB/file | `return new ...` does not automatically erase side effects | Design a pure transformation or transaction |
| Assuming a record is “deeply immutable” by default | Mutable components can still be shared | Choose immutable components/defensive copy |
| Thinking an immutable object guarantees whole-program thread safety | Shared references still require publication/atomic updates | Synchronize where the result is held and replaced |
| Copying an entire collection in a long loop without measuring performance | Can significantly increase time and allocations | Use batch/builder/structural sharing when needed |
| Treating `return this` as a bug in every case | May be valid for transformations that do not change the value | Clarify in the contract whether the result requires a new identity |

## 22. Testing Object-Returning Transformations

For the `Balance.deposit` API, tests should verify **both the result and the old object**:

| Test step | Expectation |
| --- | --- |
| Create `Balance("A-01",1000)` | Original has `cents = 1000` |
| `Balance next = original.deposit(250)` | `next.cents() == 1250` |
| Re-read `original.cents()` | Still equals `1000` |
| Check `next.accountId()` | Still equals `"A-01"` |
| Compare `original == next` | `false` in an implementation that always uses `new` |
| `current = original.deposit(500)` | Caller holds the new version with 1500 |
| `current.withdraw(2000)` | `IllegalArgumentException`, caller still holds the old object |
| `original.deposit(Long.MAX_VALUE)` | `ArithmeticException` because addition overflows |
| Store `original` via an alias | Alias still sees the value 1000 |

The checks above are **test requirements**, not ready-to-run JUnit code. If using JUnit, you can combine `assertEquals`, `assertNotSame` (only when the API promises a different instance), `assertThrows`, and before-and-after snapshot comparisons.

With `CartSnapshot`, in addition to list contents before/after, you need to test the caller modifying `input` after the constructor; if mutable elements are used, you also need to test ownership and deep-copying according to application requirements.

**For methods that may return `this`:** `assertNotSame` should not be used as a mandatory criterion if the contract only promises the result value. Tests should adhere to the actual guarantee.

## 23. Self-Practice Exercises

**Question 1 — Why does it not change?** Given:

~~~java
static void reset(Box p) {
    p = new Box(0);
}
~~~

The caller has `Box current = new Box(10);` and calls `reset(current)`. Which object does `current` point to after the call? How should the API and the call site be changed if you want it to point to the new object?

**Question 2 — Is return enough?** The method `Box reset(Box old) { return new Box(0); }` already returns a new object, yet the caller only calls `reset(current);`. Does the `current` variable change? Why?

**Question 3 — Two versions.** `Balance a = new Balance("A",100);` and `Balance b = a.deposit(20);`. What are the values of `a.cents()` and `b.cents()`? What is `a == b`?

**Question 4 — Aliasing.** A variable `oldAlias` points to the same object as `current`. After `current = current.deposit(50)`, does `oldAlias` automatically point to the new version?

**Question 5 — Records and lists.** If a record contains `List<MutableItem>`, does writing only `items = List.copyOf(items)` guarantee that no child object can be modified from outside?

**Question 6 — With `String`.** Why might `name.trim();` not change `name`, whereas `name = name.trim();` applies the result?

**Question 7 — Mid-operation error.** If `current = current.withdraw(1000)` throws an exception before `return`, does the assignment in the caller complete? What if the method body already wrote to a file before the error?

**Question 8 — Performance.** In `CartSnapshot`, what problem can arise when adding 10,000 products by creating/copying the list after every addition? Suggest a way to improve it while still producing an immutable final snapshot.

**Question 9 — Identity.** A `withCity` method may `return this` if the city does not change. Does that violate a contract to “return the **result value**”? What if the contract demands “a **new instance**”?

**Question 10 — Multiple threads.** If two threads concurrently execute `shared = shared.deposit(100)` on a shared field without synchronization, are all updates preserved merely because `Balance` is immutable?

**Question 11 — Design.** When should a method modify an object in place, and when should it return a replacement object? Name two criteria for choosing.

### Reference Answers

1. It still points to `Box(10)`; change the method to `static Box reset(Box old) { return new Box(0); }` and call `current = reset(current)`.
2. No; the result is discarded, and the caller does not perform reassignment.
3. `a.cents() = 100`, `b.cents() = 120`, and `a == b` is `false` with the `new Balance` implementation.
4. No; `oldAlias` continues to point to the old object. Reassigning one variable does not reassign aliases.
5. No; `List.copyOf` does not automatically deep-copy mutable elements.
6. `String` is immutable; `trim()` returns the result and the caller must keep the result if it wants to change the variable.
7. No; failure on the right-hand side prevents the assignment from occurring, but side effects executed before the error (such as writing to a file) do not automatically roll back.
8. It can consume significant time and memory due to repeated copying; you can collect elements using a temporary builder/`ArrayList` and then finalize one snapshot.
9. It does not violate the value contract if the content does not change; however, it does violate the contract if the API guarantees always returning a **different** instance.
10. No; read–compute–write operations on a shared field can lose updates. Synchronization or appropriate atomic compare-and-set/update is needed.
11. In-place modification suits objects with identity/lifecycle and APIs that intentionally update state; returning a new instance suits value objects, version history, and requirements not to mutate the input. Consider resources/performance and ownership.

## 24. Reference Documentation

- [Java Language Specification 17, §15.12.4 — Run-Time Evaluation of Method Invocation](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.4): evaluating argument expressions and processing the invocation.
- [Java Language Specification 17, §15.12.4.2 — Evaluate Arguments](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.4.2): argument evaluation order.
- [Java Language Specification 17, §15.9 — Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9): `new` expressions.
- [Java Language Specification 17, §14.17 — Return Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.17): `return` semantics and returning the result value.
- [Java Language Specification 17, §8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): records and components.
- [Java SE 17 API — List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): creating unmodifiable lists and copy semantics.
- [Java SE 17 API — AtomicReference](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html): managing atomically updated references.

**Key takeaway:** Java passes a **copy of the reference value** into a parameter, so the callee **cannot change the caller's reference variable** by reassigning the parameter. When you want to represent a replacement result, **create/compute the result object and execute `return`**, then let the caller **reassign the variable if it wants to apply it**. If the old object is required to remain unchanged, you must ensure that mutable child data cannot be modified unintentionally either; distinguish a **result-value** contract from a guarantee of **always-new identity**.
