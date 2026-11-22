# Returning a New Object Instead of Updating the Old Object in Java

An **immutable** object does not allow its own logical state to change after full construction. Therefore, when business requirements call for “increasing the quantity”, “changing the address”, “transitioning state”, “adding a product”, or “updating configuration”, the natural approach is to **return a new object containing the result**, rather than modifying the existing object.

For example, instead of writing `account.setBalance(newBalance)` or `point.translateInPlace(dx, dy)`, an API can expose `Account deposit(amount)` and `Point movedBy(dx, dy)`: the caller receives the new result; the original remains unchanged. Both versions can coexist for comparison, storing history, or safer sharing.

This is not merely replacing setters with different names. To be truly meaningful, a method that returns a new object must **preserve invariants**, **not leak mutable references**, clearly define the no-change case, handle failed computations without partial updates, and make the caller aware that it needs to **use the return value**.

This lesson belongs to **Java core – class-object**, in the **Immutable Classes** section. The examples are standalone compilable Java **17+** programs; incomplete illustrative code is explicitly noted.

## 1. Learning Objectives

After this lesson, you should be able to explain and practice on your own:

- Why modifying a shared object can create hard-to-detect side effects.
- How to design `withX`, `plus`, `minus`, `movedBy`, `withAddedItem`-style methods that return a new object.
- The differences between **object identity**, **value equality**, and **immutable logical state**.
- How to place validation in constructors/factories so that every new version is valid.
- Why mutable collections or child objects can break an immutable design even when the outer class returns a new object.
- How to update lists/maps using **API-level copy-on-write**, and distinguish it from the concurrency collection `CopyOnWriteArrayList`.
- How to combine multiple transformations, build history/undo, and test for non-mutation.
- Limitations regarding allocation, performance, entity lifecycle, atomicity, and multithreading.

## 2. Mutation and Immutable Update Are Two Different Contracts

A **mutable API** modifies the object receiving the call:

~~~java
class MutablePoint {
    int x;
    int y;

    void moveBy(int dx, int dy) {
        x += dx;
        y += dy;
    }
}
~~~

This is an illustrative class: when the caller invokes `point.moveBy(2,3)`, **the old point itself changes its coordinates**. If two variables point to the same point, both observe the change.

An **immutable-update API** creates another result:

~~~java
record Point(int x, int y) {
    Point movedBy(int dx, int dy) {
        return new Point(x + dx, y + dy);
    }
}
~~~

This is a valid Java 17 record. `Point newPoint = oldPoint.movedBy(2,3)` produces a new value; `oldPoint` is not modified. The primitive components of this record are immutable, and the method has no way to modify state.

Distinctions that must be stated in the API documentation:

| Property | Mutable update | Returning a new object |
| --- | --- | --- |
| Receiver after the call | State has changed | Retains old state |
| Return value | Usually `void` or an auxiliary result | Object containing the new state |
| Aliases to the same object | Observe the mutation | Continue to observe the old version |
| State history | Must manually capture snapshots | Can retain multiple versions |
| Failed validation | Risk of partial modification if ordered incorrectly | Can avoid publishing a new version |
| Memory | Usually reuses a single object | May allocate new objects/collections |
| Concurrency | Must protect mutable state | Value objects are easy to share; updating references still requires coordination |

**Immutable does not mean a method cannot perform computation.** A method can still compute values, allocate objects, return collections, or report errors. What matters is **not changing the logical state of the receiver**.

## 3. Experiment 1 — Aliases of a Mutable Variable and Immutable Versions

Create the file **`MutationVersusNewValueDemo.java`**:

~~~java
class MutableScore {
    private int points;

    MutableScore(int initial) {
        points = initial;
    }

    void award(int amount) {
        points += amount;
    }

    int points() {
        return points;
    }
}

record ImmutableScore(int points) {
    ImmutableScore award(int amount) {
        return new ImmutableScore(points + amount);
    }
}

public class MutationVersusNewValueDemo {
    public static void main(String[] args) {
        MutableScore mutable = new MutableScore(10);
        MutableScore alias = mutable;
        mutable.award(5);

        System.out.println("mutable=" + mutable.points());
        System.out.println("alias=" + alias.points());
        System.out.println("same reference=" + (mutable == alias));

        ImmutableScore before = new ImmutableScore(10);
        ImmutableScore after = before.award(5);

        System.out.println("before=" + before.points());
        System.out.println("after=" + after.points());
        System.out.println("same immutable reference="
                + (before == after));
        System.out.println("same value=" + before.equals(after));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 MutationVersusNewValueDemo.java
java MutationVersusNewValueDemo
~~~

**Exact stdout:**

~~~text
mutable=15
alias=15
same reference=true
before=10
after=15
same immutable reference=false
same value=false
~~~

`alias` and `mutable` refer to the same object, so both see 15. With `ImmutableScore`, `award(5)` returns a new record: `before` remains 10, `after` is 15. In this example, component-based equality also differs because 10 does not equal 15.

**What to observe:** `final` on a **reference variable** does not make the receiver immutable. If you write `final MutableScore score = new MutableScore(10);`, the statement `score.award(5)` can still modify the object. The class design is what determines mutability.

## 4. Do Not Ignore the Return Value

With an immutable API:

~~~java
ImmutableScore score = new ImmutableScore(10);
score.award(5);
~~~

This is an illustrative snippet based on the `ImmutableScore` record from the previous section. **The result 15 is discarded**; `score.points()` is still 10.

To advance the logical state for a local variable:

~~~java
score = score.award(5);
~~~

Now the `score` variable points to the result object 15; the previous object 10 **is not modified**. Reassigning a **variable** is not mutating an object.

If the local variable is declared `final`, you cannot write `score = ...`; in that case, use a different variable name:

~~~java
final ImmutableScore before = new ImmutableScore(10);
final ImmutableScore after = before.award(5);
~~~

An immutable value object can still be held by a **mutable variable**; the two kinds of “change” exist at two different levels.

## 5. Method Names Should Convey the Update Style

Common names:

| API Name | Intended Meaning |
| --- | --- |
| `withName(newName)` | A new value with a different name |
| `withStatus(status)` | A new value with the specified status |
| `movedBy(dx,dy)` | A new value with shifted coordinates |
| `plus(amount)` | A new value after addition |
| `minus(amount)` | A new value after subtraction |
| `withAdded(item)` | A new collection/aggregate containing the element |
| `without(id)` | A new aggregate with the association removed by ID |
| `normalized()` | A new value following normalization rules |
| `copyWith(...)` | A customized copy according to the contract |

There is no `with` keyword in Java that creates this mechanism. It is a **naming convention**, and developers must implement creating the proper result instance themselves.

A method named `withName` that executes `this.name = name;` on the receiver itself **violates expectations** when the API promises an immutable update. The name should come with a clear contract: whether it creates a new copy or may return `this` in the no-change case, how null is handled, and whether error cases throw an exception.

## 6. Designing Value Objects with Constructor Validation

A typical immutable class:

~~~java
final class Username {
    private final String text;

    Username(String text) {
        if (text == null || text.isBlank()) {
            throw new IllegalArgumentException("username rỗng");
        }
        this.text = text;
    }

    Username withText(String next) {
        return new Username(next);
    }

    String text() {
        return text;
    }
}
~~~

This is a valid class without a `main` method. Every object creation path, including `withText`, goes through constructor validation. There is no setter; `text` is an immutable `String`, the field is `private final`, and the class is `final`.

If you want to reject names containing leading/trailing whitespace or normalize letter casing, **define the rule** in the constructor/factory and apply it consistently. Do not let `withText` bypass the validation that the constructor enforces.

An important distinction: **immutability** does not automatically guarantee **valid** data. An object can be immutable yet hold an invalid value if the constructor does not check domain rules.

## 7. Experiment 2 — Creating New Versions and Rejecting Invalid States

Create the file **`ImmutableProfileDemo.java`**:

~~~java
import java.util.Objects;

final class Profile {
    private final String username;
    private final int level;

    Profile(String username, int level) {
        if (username == null || username.isBlank()) {
            throw new IllegalArgumentException("username rỗng");
        }
        if (level < 1 || level > 10) {
            throw new IllegalArgumentException("level ngoài 1..10");
        }
        this.username = username;
        this.level = level;
    }

    Profile withUsername(String next) {
        return new Profile(next, level);
    }

    Profile withLevel(int next) {
        return new Profile(username, next);
    }

    String description() {
        return username + "@" + level;
    }
}

public class ImmutableProfileDemo {
    public static void main(String[] args) {
        Profile initial = new Profile("An", 2);
        Profile renamed = initial.withUsername("Bình");
        Profile promoted = renamed.withLevel(3);

        System.out.println("initial=" + initial.description());
        System.out.println("renamed=" + renamed.description());
        System.out.println("promoted=" + promoted.description());

        try {
            promoted.withLevel(99);
        } catch (IllegalArgumentException ex) {
            System.out.println("reject=" + ex.getMessage());
        }
        System.out.println("still=" + promoted.description());
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 ImmutableProfileDemo.java
java ImmutableProfileDemo
~~~

**Stdout:**

~~~text
initial=An@2
renamed=Bình@2
promoted=Bình@3
reject=level ngoài 1..10
still=Bình@3
~~~

`withUsername` and `withLevel` call the same constructor and do not reassign fields themselves. If the level is invalid, the constructor throws `IllegalArgumentException` and no result object is returned; existing objects remain valid.

**Note:** calling `withLevel(3)` on an object that is already at level 3 can be designed to **always create a new instance** or **return `this`**. Both can be valid if the contract describes it clearly; immutability requires that the old state not be mutated, **not necessarily that every call return a new identity**.

## 8. Monetary Data Types: Avoiding Addition Overflow and Partial State

For currency or balances, immutable updates not only make control easier, but also make **validation before publishing the result** clearer.

Business questions:

- Are negative amounts allowed?
- Does each account have a single currency or multiple currencies?
- Can addition/subtraction overflow `long`?
- Is the requested amount greater than the balance or exceeding the limit?
- Is the unit dong, cents, or a fixed-point scale?

If using `long cents`, you can guard against overflow with `Math.addExact`/`Math.subtractExact`. Do not write `balance + amount` and only check for a negative result, because overflow can turn a large number into a negative number or vice versa under two's-complement arithmetic.

In the next example, the simple rules are that the balance is **non-negative**, the unit is **dong**, and all additions/subtractions must be exact within the `long` range.

## 9. Experiment 3 — Immutable Account with `Math.addExact`

Create the file **`ImmutableBalanceDemo.java`**:

~~~java
final class Balance {
    private final long dong;

    Balance(long dong) {
        if (dong < 0) {
            throw new IllegalArgumentException("balance âm");
        }
        this.dong = dong;
    }

    Balance deposit(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount phải dương");
        }
        return new Balance(Math.addExact(dong, amount));
    }

    Balance withdraw(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount phải dương");
        }
        if (amount > dong) {
            throw new IllegalArgumentException("không đủ tiền");
        }
        return new Balance(dong - amount);
    }

    long dong() {
        return dong;
    }
}

public class ImmutableBalanceDemo {
    public static void main(String[] args) {
        Balance opening = new Balance(100);
        Balance funded = opening.deposit(50);
        Balance spent = funded.withdraw(30);

        System.out.println("opening=" + opening.dong());
        System.out.println("funded=" + funded.dong());
        System.out.println("spent=" + spent.dong());

        try {
            spent.withdraw(500);
        } catch (IllegalArgumentException ex) {
            System.out.println("reject=" + ex.getMessage());
        }
        System.out.println("spent after reject=" + spent.dong());

        try {
            new Balance(Long.MAX_VALUE).deposit(1);
        } catch (ArithmeticException ex) {
            System.out.println("overflow="
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 ImmutableBalanceDemo.java
java ImmutableBalanceDemo
~~~

**Exact stdout:**

~~~text
opening=100
funded=150
spent=120
reject=không đủ tiền
spent after reject=120
overflow=ArithmeticException
~~~

Each successful operation creates a new `Balance`, without changing opening or funded. When withdrawing more than the balance, the program throws an exception **before creating a new result**; spent remains 120. `Math.addExact` throws `ArithmeticException` when addition overflows, instead of letting an incorrect balance be stored silently.

**Important limitation:** this is a **balance value object**, not a multi-user banking transaction solution. If multiple threads read the old balance concurrently and independently create two new Balance instances, saving/publishing the new state still requires synchronization, compare-and-set, transactions, and proper ownership management.

## 10. Returning a New Object Does Not Require Replacing All Original Data

A new object can safely reuse the **immutable components** of the old object. For example, if Profile has `String username`, a new instance with the same username does not need to create another String just to avoid mutation, because String is immutable.

However, if the object contains:

~~~text
Invoice
  - number: String (immutable)
  - lines: ArrayList<MutableLine> (mutable)
~~~

then `new Invoice(old.number, old.lines)` only creates a new root object without **isolating the mutable state**. An update method like `withNumber` may return a new Invoice while still sharing the lines list, causing mutating a line to affect both versions.

You must decide the **scope of immutability**: if lines are immutable values held in an immutable list, sharing them is safe; if lines are mutable elements, you must copy them or design an appropriate wrapper/ownership mechanism.

## 11. Records Do Not Automatically Make All Components Deeply Immutable

A Java 17 `record` is a convenient tool for value carriers:

~~~java
record Location(int x, int y) {
    Location movedBy(int dx, int dy) {
        return new Location(x + dx, y + dy);
    }
}
~~~

The primitive components of this record cannot be mutated through normal APIs, so each move operation can return a new record.

However:

~~~java
record MutableTagList(java.util.List<String> tags) {
}
~~~

automatically has a final field holding a **reference** to the list. If the caller passes an `ArrayList` and continues modifying it, the result of `MutableTagList.tags()` can still change. Therefore, a record does not by itself guarantee deep immutability of mutable components.

The solution for `List<String>` is a compact canonical constructor:

~~~java
record SafeTagList(java.util.List<String> tags) {
    SafeTagList {
        tags = java.util.List.copyOf(tags);
    }

    SafeTagList withAdded(String tag) {
        var updated = new java.util.ArrayList<>(tags);
        updated.add(java.util.Objects.requireNonNull(tag));
        return new SafeTagList(updated);
    }
}
~~~

The snippets in this section are **valid illustrative record definitions** without a `main` method. The compact constructor takes a snapshot; `withAdded` creates a candidate list, then creates a new object with consistent validation/copying.

## 12. Experiment 4 — Records and Unchanging Lists

Create the file **`ImmutableTagsDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

record Tags(List<String> values) {
    Tags {
        values = List.copyOf(values);
    }

    Tags withAdded(String tag) {
        Objects.requireNonNull(tag, "tag");
        List<String> next = new ArrayList<>(values);
        next.add(tag);
        return new Tags(next);
    }

    Tags without(String tag) {
        List<String> next = new ArrayList<>(values);
        next.remove(tag);
        return new Tags(next);
    }
}

public class ImmutableTagsDemo {
    public static void main(String[] args) {
        List<String> input = new ArrayList<>();
        input.add("java");

        Tags base = new Tags(input);
        Tags extended = base.withAdded("oop");
        Tags reduced = extended.without("java");

        input.add("external");

        System.out.println("base=" + base.values());
        System.out.println("extended=" + extended.values());
        System.out.println("reduced=" + reduced.values());
        System.out.println("same object=" + (base == extended));

        try {
            base.values().add("illegal");
        } catch (UnsupportedOperationException ex) {
            System.out.println("read-only result");
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 ImmutableTagsDemo.java
java ImmutableTagsDemo
~~~

**Stdout:**

~~~text
base=[java]
extended=[java, oop]
reduced=[oop]
same object=false
read-only result
~~~

Adding `external` to `input` **does not change base** because the constructor used `List.copyOf`. `withAdded` and `without` create different versions, while `base.values()` still returns a list containing the single element java.

In this snippet, `without` uses `List.remove(Object)` and removes **only the first occurrence**. If the domain treats Tags as a **duplicate-free set**, you should choose `Set` or uniqueness validation; you cannot assume `List` removes all duplicates.

## 13. `List.copyOf` and `Collections.unmodifiableList` Are Different

An immutable design should avoid keeping an **unmodifiable view** of a mutable collection still held externally.

- `Collections.unmodifiableList(backing)` returns a **view that disallows modification through the view**, but if `backing` changes, the view reflects those changes as well.
- `List.copyOf(backing)` creates an unmodifiable list representing the elements at the time of the call; it may return the same instance if the input is already a suitable unmodifiable list. For a mutable input list, it does not retain a live connection to the input per its copy contract.
- Neither **deep-copies elements**. If the elements are mutable, mutations to an element can still be observed.

For example, if a record contains a `List<StringBuilder>`, `List.copyOf` does not make each StringBuilder immutable. Instead of putting mutable elements into a value object, you can store immutable data types such as `String`, a `record Line(...)` containing only immutable components, or take a separate snapshot of each element.

## 14. Experiment 5 — Collection Snapshots and Version Updates

Create the file **`PlaylistVersionsDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

final class Playlist {
    private final String title;
    private final List<String> songs;

    Playlist(String title, List<String> songs) {
        this.title = Objects.requireNonNull(title, "title");
        this.songs = List.copyOf(songs);
    }

    Playlist withTitle(String nextTitle) {
        return new Playlist(nextTitle, songs);
    }

    Playlist withSong(String song) {
        Objects.requireNonNull(song, "song");
        List<String> next = new ArrayList<>(songs);
        next.add(song);
        return new Playlist(title, next);
    }

    Playlist withoutSong(String song) {
        List<String> next = new ArrayList<>(songs);
        next.remove(song);
        return new Playlist(title, next);
    }

    String description() {
        return title + "=" + songs;
    }

    List<String> songs() {
        return songs;
    }
}

public class PlaylistVersionsDemo {
    public static void main(String[] args) {
        List<String> input = new ArrayList<>();
        input.add("Song A");

        Playlist original = new Playlist("Morning", input);
        Playlist expanded = original.withSong("Song B");
        Playlist renamed = expanded.withTitle("Evening");
        Playlist shortened = renamed.withoutSong("Song A");

        input.add("Outside");

        System.out.println("original=" + original.description());
        System.out.println("expanded=" + expanded.description());
        System.out.println("renamed=" + renamed.description());
        System.out.println("shortened=" + shortened.description());
        System.out.println("same original/expanded="
                + (original == expanded));
        System.out.println("songs original=" + original.songs());
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 PlaylistVersionsDemo.java
java PlaylistVersionsDemo
~~~

**Exact stdout:**

~~~text
original=Morning=[Song A]
expanded=Morning=[Song A, Song B]
renamed=Evening=[Song A, Song B]
shortened=Evening=[Song B]
same original/expanded=false
songs original=[Song A]
~~~

Each `Playlist` holds an unmodifiable snapshot of immutable `String`s; subsequent modifications to input by the caller do not affect the created versions. `withSong` and `withoutSong` operate on a **new candidate list** before passing it into the constructor.

**Cost:** each song addition/removal in the example must copy a list of the corresponding length, which can take **O(n)** time/memory. For very large lists or extremely frequent updates, consider persistent data structures, batching, or a mutable builder model before publishing a snapshot.

## 15. Choice: Always Create a New Object or Return `this` When Unchanged?

For an immutable object, when the target value **equals** the current value, there are two possible contracts:

1. **Always-new:** `withName(sameName)` still creates a new object. Callers can rely on a new identity if the API promises so.
2. **Reuse-if-unchanged:** `withName(sameName)` returns `this`. This does not break immutability because the receiver is not mutated.

For example:

~~~java
Profile withUsername(String next) {
    if (username.equals(next)) {
        return this;
    }
    return new Profile(next, level);
}
~~~

This is an **illustrative method snippet**, assuming the class has fields `username`, `level`, and the corresponding constructor. If null is passed, `equals` returns false, and then the constructor rejects null.

You should decide based on the API contract: a `withX` name usually describes the **resulting value**, without promising a new identity on every call. Avoid having callers check `old != next` as the criterion for “data changed” unless an identity contract is documented.

## 16. Experiment 6 — No-op Update and `equals()`

Create the file **`NoOpUpdateDemo.java`**:

~~~java
import java.util.Objects;

record Settings(String theme, int fontSize) {
    Settings {
        Objects.requireNonNull(theme, "theme");
        if (fontSize < 8 || fontSize > 40) {
            throw new IllegalArgumentException("fontSize sai");
        }
    }

    Settings withTheme(String nextTheme) {
        Objects.requireNonNull(nextTheme, "nextTheme");
        return theme.equals(nextTheme)
                ? this : new Settings(nextTheme, fontSize);
    }

    Settings withFontSize(int nextSize) {
        return nextSize == fontSize
                ? this : new Settings(theme, nextSize);
    }
}

public class NoOpUpdateDemo {
    public static void main(String[] args) {
        Settings first = new Settings("light", 14);
        Settings same = first.withTheme("light");
        Settings changed = first.withFontSize(16);
        Settings equalValue = new Settings("light", 14);

        System.out.println("reused=" + (first == same));
        System.out.println("changed identity="
                + (first != changed));
        System.out.println("first=" + first);
        System.out.println("changed=" + changed);
        System.out.println("equal value="
                + first.equals(equalValue));
        System.out.println("same identity="
                + (first == equalValue));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 NoOpUpdateDemo.java
java NoOpUpdateDemo
~~~

**Stdout:**

~~~text
reused=true
changed identity=true
first=Settings[theme=light, fontSize=14]
changed=Settings[theme=light, fontSize=16]
equal value=true
same identity=false
~~~

The `Settings` record has `equals/hashCode/toString` generated from its components. Two objects with the same data are considered **equal by value** even though `==` is false. Conversely, `withTheme("light")` returns the receiver itself because there is no data change.

**An immutable API should describe value outcomes, not force callers to guess by object address.**

## 17. Chained Transformations: Creating Intermediate Versions

Immutable operations can be combined:

~~~java
Settings next = start
        .withTheme("dark")
        .withFontSize(18);
~~~

This is an **illustrative snippet** using the `Settings` record defined in section 16. Each method receives an immutable receiver and returns a new value, so method chaining is natural.

Keep in mind:

- `start` **does not change**.
- An intermediate value may be allocated and quickly become unreachable.
- If a later step throws an exception, the `next` variable in the declaration above **does not receive a completed result**. Existing versions remain unmutated.
- If updating multiple fields must satisfy an **interdependent** invariant, method chaining may be blocked by validation of an intermediate state. In that case, a **composite factory or update method** is needed instead of forcing execution through invalid temporary states.

This is an important point: immutable updates are safe step by step, but do not automatically turn **a chain of transactions** into a business-level atomic operation.

## 18. When Multiple Fields Constrain Each Other, Use a Composite Update

Suppose a `Range(start,end)` interval requires `start <= end`. Given the range `[1,5]`, to change it to `[10,20]`:

~~~text
withStart(10) on [1,5] -> [10,5] (invalid)
withEnd(20) on [1,5] -> [1,20] (valid)
withStart(10) next -> [10,20]
~~~

If this has to be written in many places, update ordering can easily surprise users. The clearer approach is to provide `withBounds(newStart,newEnd)` that directly creates a valid result in **a single constructor call**.

## 19. Experiment 7 — Relational Invariant Between Two Fields

Create the file **`RangeUpdateDemo.java`**:

~~~java
record Range(int start, int end) {
    Range {
        if (start > end) {
            throw new IllegalArgumentException("start > end");
        }
    }

    Range withStart(int newStart) {
        return new Range(newStart, end);
    }

    Range withEnd(int newEnd) {
        return new Range(start, newEnd);
    }

    Range withBounds(int newStart, int newEnd) {
        return new Range(newStart, newEnd);
    }
}

public class RangeUpdateDemo {
    public static void main(String[] args) {
        Range source = new Range(1, 5);

        try {
            source.withStart(10);
        } catch (IllegalArgumentException ex) {
            System.out.println("first failed=" + ex.getMessage());
        }

        Range expanded = source.withEnd(20);
        Range moved = expanded.withStart(10);
        Range direct = source.withBounds(10, 20);

        System.out.println("source=" + source);
        System.out.println("expanded=" + expanded);
        System.out.println("moved=" + moved);
        System.out.println("direct=" + direct);
        System.out.println("same value=" + moved.equals(direct));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 RangeUpdateDemo.java
java RangeUpdateDemo
~~~

**Stdout:**

~~~text
first failed=start > end
source=Range[start=1, end=5]
expanded=Range[start=1, end=20]
moved=Range[start=10, end=20]
direct=Range[start=10, end=20]
same value=true
~~~

A `withBounds` method is useful when multiple values must change simultaneously to reach a valid state. It does not mean Java automatically provides transactions or automatically coordinates when multiple threads update a variable holding Range; it is simply that **constructing a new value object** does not publish an invalid intermediate version.

## 20. Updating Collections in a “Copy-Then-Replace” Style

In a mutable model, one might write:

~~~java
items.add(newItem);
items.remove(oldItem);
~~~

If `items` is an internal field shared with callers, these statements change the observable state of the old object.

With an immutable aggregate, a common pattern is:

~~~text
1. Read the immutable collection from the original version.
2. Create a candidate collection that can be modified within the method scope.
3. Apply the changes to the candidate.
4. Validate the result against domain rules.
5. Create a new value object containing an unmodifiable snapshot.
6. Return the result; the old version remains unchanged.
~~~

This is **application-contract copy-on-update**, which is not synonymous with using the `java.util.concurrent.CopyOnWriteArrayList` class. `CopyOnWriteArrayList` is a concrete collection with concurrency characteristics that still provides collection-mutation operations; it does not automatically turn the entire containing object into an immutable value.

A mutable builder/private temporary collection is completely acceptable when constructing an immutable object, provided it **does not escape as a mutable alias** into the published result.

## 21. Experiment 8 — Immutable Cart, Accumulating, and Removing by Code

Create the file **`ImmutableCartDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

record Item(String sku, int quantity) {
    Item {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku rỗng");
        }
        if (quantity < 1) {
            throw new IllegalArgumentException("quantity < 1");
        }
    }

    Item withQuantity(int next) {
        return new Item(sku, next);
    }
}

final class Cart {
    private final List<Item> items;

    Cart(List<Item> source) {
        Objects.requireNonNull(source, "source");
        List<Item> checked = new ArrayList<>();
        for (Item item : source) {
            checked.add(Objects.requireNonNull(item, "item"));
        }
        items = List.copyOf(checked);
    }

    static Cart empty() {
        return new Cart(List.of());
    }

    Cart withAdded(String sku, int quantity) {
        Item added = new Item(sku, quantity);
        List<Item> next = new ArrayList<>(items);
        for (int i = 0; i < next.size(); i++) {
            Item current = next.get(i);
            if (current.sku().equals(sku)) {
                int merged = Math.addExact(
                        current.quantity(), quantity);
                next.set(i, current.withQuantity(merged));
                return new Cart(next);
            }
        }
        next.add(added);
        return new Cart(next);
    }

    Cart without(String sku) {
        Objects.requireNonNull(sku, "sku");
        List<Item> next = new ArrayList<>(items);
        boolean changed = next.removeIf(
                item -> item.sku().equals(sku));
        return changed ? new Cart(next) : this;
    }

    List<Item> items() {
        return items;
    }
}

public class ImmutableCartDemo {
    public static void main(String[] args) {
        Cart empty = Cart.empty();
        Cart one = empty.withAdded("P1", 2);
        Cart two = one.withAdded("P2", 1);
        Cart merged = two.withAdded("P1", 3);
        Cart removed = merged.without("P2");
        Cart unchanged = removed.without("missing");

        System.out.println("empty=" + empty.items());
        System.out.println("one=" + one.items());
        System.out.println("two=" + two.items());
        System.out.println("merged=" + merged.items());
        System.out.println("removed=" + removed.items());
        System.out.println("reused=" + (removed == unchanged));
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 ImmutableCartDemo.java
java ImmutableCartDemo
~~~

**Exact stdout:**

~~~text
empty=[]
one=[Item[sku=P1, quantity=2]]
two=[Item[sku=P1, quantity=2], Item[sku=P2, quantity=1]]
merged=[Item[sku=P1, quantity=5], Item[sku=P2, quantity=1]]
removed=[Item[sku=P1, quantity=5]]
reused=true
~~~

`Item` is a record with two immutable components (`String` and `int`). `Cart` stores `List.copyOf` and does not expose a mutable list. When adding quantity for an existing product, it creates a **new Item** and replaces the element in the **new candidate list**; previous versions retain their original quantities.

**Example contract:** removing a SKU not present in the cart returns `this` (unchanged). It also assumes the input list contains no duplicate SKUs; **the current constructor only rejects null and does not itself check for duplicate SKUs**. In a production API, you should enforce the uniqueness constraint in the constructor/factory or switch the representation to `Map<SKU,Item>` so that the invariant is protected on every object creation path. The example illustrates the immutability principle; it does not claim that the current constructor already guarantees uniqueness for arbitrary input.

## 22. Shallow Copying Is Insufficient If Inner Items Are Mutable

Change `record Item` to a `MutableItem` with a setter:

~~~java
final class MutableItem {
    private int quantity;

    MutableItem(int quantity) {
        this.quantity = quantity;
    }

    void setQuantity(int next) {
        quantity = next;
    }

    int quantity() {
        return quantity;
    }
}
~~~

This is a valid illustrative class. If Cart only does `items = List.copyOf(input)` for a `List<MutableItem>`, the caller can still:

~~~java
MutableItem item = new MutableItem(1);
List<MutableItem> input = List.of(item);
item.setQuantity(99);
~~~

and change the quantity of the exact item object being referenced by Cart. There is no true immutable aggregate if its logical value changes according to a mutable reference that the caller still holds.

Preferred solution: **use immutable elements** such as the `Item` record. If `MutableItem` must be used due to integration requirements, you must defensively copy elements on input and output, or only expose immutable projections instead of returning element references.

## 23. Updating Nested Objects Without Modifying the Old Version

A value object can contain another value object. For example, `User` contains `Address`; the user's address needs to change to a new `Address`, and then a new `User` containing that Address is created.

~~~java
record Address(String city, String street) {
    Address {
        java.util.Objects.requireNonNull(city);
        java.util.Objects.requireNonNull(street);
    }

    Address withCity(String nextCity) {
        return new Address(nextCity, street);
    }
}

record User(String id, Address address) {
    User {
        java.util.Objects.requireNonNull(id);
        java.util.Objects.requireNonNull(address);
    }

    User withAddress(Address next) {
        return new User(id,
                java.util.Objects.requireNonNull(next));
    }
}
~~~

These two records are valid Java code without a `main` method. Neither Address nor User contains mutable components, so it is safe to share unchanged child objects.

**Principle:** at each level along the path to the changed data, create **a new node**; **unchanged** immutable child branches can be reused without deep-copying the entire graph.

## 24. Experiment 9 — Immutable Nested Update

Create the file **`NestedUpdateDemo.java`**:

~~~java
import java.util.Objects;

record Address(String city, String street) {
    Address {
        Objects.requireNonNull(city, "city");
        Objects.requireNonNull(street, "street");
    }

    Address withCity(String next) {
        return new Address(next, street);
    }
}

record User(String id, Address address) {
    User {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(address, "address");
    }

    User withAddress(Address next) {
        return new User(id, next);
    }
}

public class NestedUpdateDemo {
    public static void main(String[] args) {
        Address firstAddress = new Address("Huế", "A");
        User initial = new User("U1", firstAddress);

        Address secondAddress = initial.address().withCity("Đà Nẵng");
        User updated = initial.withAddress(secondAddress);

        System.out.println("initial=" + initial);
        System.out.println("updated=" + updated);
        System.out.println("same user=" + (initial == updated));
        System.out.println("same address="
                + (initial.address() == updated.address()));
        System.out.println("initial city=" + initial.address().city());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 NestedUpdateDemo.java
java NestedUpdateDemo
~~~

**Stdout:**

~~~text
initial=User[id=U1, address=Address[city=Huế, street=A]]
updated=User[id=U1, address=Address[city=Đà Nẵng, street=A]]
same user=false
same address=false
initial city=Huế
~~~

Creating a new `Address` and then a new `User` avoids modifying the initial `User` version. If both addresses reference an immutable `String street`, sharing the `String` does not create a mutable alias.

**Not every nested update must deep-copy the entire tree**. Only the nodes that need to change create new objects; other immutable nodes can be reused. This is the foundation of many efficient immutable data designs.

## 25. Functions Taking the Old Value and Returning a New Value

A transformation can be expressed as:

~~~java
java.util.function.UnaryOperator<Settings> change =
        old -> old.withFontSize(18);
~~~

This is an illustrative snippet using the `Settings` type from section 16, not a standalone program. `UnaryOperator<T>` is a `Function<T,T>` with the same input and output type, fitting the shape of an immutable update.

A good transformation function:

- Does not modify the input object.
- Can be tested independently by input/output.
- Returns a new value with valid invariants.
- Does not rely on mutable global state to determine the result if predictability is needed.
- Avoids side effects during execution if it needs to be used safely with **retryable** mechanisms.

“A method that returns a new object” **does not automatically make it pure**: the method can still write logs, send emails, increment a static variable, or mutate another dependency. When calling something a “pure transformation”, you must consider **all side effects**, not just the receiver.

## 26. Experiment 10 — Transforming a List with `stream().map`

Create the file **`ImmutableStreamUpdateDemo.java`**:

~~~java
import java.util.List;

record Product(String sku, int price) {
    Product {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku rỗng");
        }
        if (price < 0) {
            throw new IllegalArgumentException("price âm");
        }
    }

    Product withPrice(int nextPrice) {
        return new Product(sku, nextPrice);
    }
}

public class ImmutableStreamUpdateDemo {
    public static void main(String[] args) {
        List<Product> original = List.of(
                new Product("A", 10),
                new Product("B", 20));

        List<Product> updated = original.stream()
                .map(p -> p.sku().equals("B")
                        ? p.withPrice(25) : p)
                .toList();

        System.out.println("original=" + original);
        System.out.println("updated=" + updated);
        System.out.println("same first="
                + (original.get(0) == updated.get(0)));
        System.out.println("same second="
                + (original.get(1) == updated.get(1)));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 ImmutableStreamUpdateDemo.java
java ImmutableStreamUpdateDemo
~~~

**Stdout:**

~~~text
original=[Product[sku=A, price=10], Product[sku=B, price=20]]
updated=[Product[sku=A, price=10], Product[sku=B, price=25]]
same first=true
same second=false
~~~

`stream().map` creates a new result list via `toList()`. Element A does not change, so the lambda returns the same old immutable object A; element B is replaced with a new Product. This is **simple structural sharing** at the element level.

**Note:** `Stream.toList()` in Java 17 returns a list that does not support modification through methods such as `add`. However, if Product were mutable, retaining the same element A would not be safe in the sense of an immutable deep structure. We use a record with primitive/String components so that sharing is sound.

## 27. Keeping History for Comparison, Undo, and Auditing

One advantage of immutable values is the ability to retain versions:

~~~text
state0 --update A--> state1 --update B--> state2

state0 still exists
state1 still exists
state2 is the latest version
~~~

With a mutable object, if you merely store the same reference in a history list, every entry may end up seeing the **latest state**, rather than a snapshot at the time it was saved. With immutable objects, each reference still describes the value at the time it was created.

However, multi-version history consumes memory. If each version copies an entire large list, the overhead can be significant; if a system needs long-term history storage, you need a retention policy, snapshots/diffs, or a persistent data structure.

**In-memory history is not a durable audit log**. If you need persistent event storage, recovery after restart, or compliance, you must have separate storage and transaction mechanisms.

## 28. Experiment 11 — Undo Across Immutable Versions

Create the file **`ImmutableHistoryDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

record Draft(String text) {
    Draft {
        if (text == null) {
            throw new IllegalArgumentException("text null");
        }
    }

    Draft append(String extra) {
        if (extra == null) {
            throw new IllegalArgumentException("extra null");
        }
        return new Draft(text + extra);
    }
}

public class ImmutableHistoryDemo {
    public static void main(String[] args) {
        List<Draft> history = new ArrayList<>();
        Draft current = new Draft("A");
        history.add(current);

        current = current.append("B");
        history.add(current);

        current = current.append("C");
        history.add(current);

        System.out.println("history="
                + history.stream().map(Draft::text).toList());
        System.out.println("current=" + current.text());

        current = history.get(1);
        System.out.println("undo=" + current.text());
        System.out.println("first=" + history.get(0).text());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 ImmutableHistoryDemo.java
java ImmutableHistoryDemo
~~~

**Stdout:**

~~~text
history=[A, AB, ABC]
current=ABC
undo=AB
first=A
~~~

The `Draft` objects in history do not change after each `append`; Undo here is simply setting the `current` variable back to an old reference.

**Limitation:** the example uses a mutable `ArrayList` to manage **the history of immutable values**. The history list itself is not immutable, whereas the stored Drafts are immutable. These are two different layers of responsibility.

## 29. Crucial Condition: Do Not Let Callers Modify Child Contents of a Version

A new root object does not mean an immutable graph.

Example that is wrong with respect to the contract:

~~~java
final class WrongDocument {
    private final java.util.List<StringBuilder> lines;

    WrongDocument(java.util.List<StringBuilder> input) {
        lines = java.util.List.copyOf(input);
    }

    WrongDocument withMore(StringBuilder line) {
        var next = new java.util.ArrayList<>(lines);
        next.add(line);
        return new WrongDocument(next);
    }

    java.util.List<StringBuilder> lines() {
        return lines;
    }
}
~~~

This is a **valid class that intentionally illustrates a design that is not deeply immutable**. The constructor copies the list container; the accessor returns an unmodifiable list, yet every `StringBuilder` inside remains mutable and callers can hold references to them.

When calling `old.lines().get(0).append("!")`, **the logical state of old still changes**. If the new version shares that builder, both versions even change together.

To fix this, store a `List<String>` after converting the builders via `toString()`, or store immutable line value objects. If mutable elements are mandatory, defensively copy the elements upon receipt, and do not expose internal mutable elements.

## 30. Experiment 12 — Separating Mutable Data When Creating a New Value

Create the file **`ImmutableNotesDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

final class Notes {
    private final List<String> lines;

    Notes(List<StringBuilder> input) {
        Objects.requireNonNull(input, "input");
        List<String> copied = new ArrayList<>();
        for (StringBuilder item : input) {
            copied.add(Objects.requireNonNull(item).toString());
        }
        lines = List.copyOf(copied);
    }

    private Notes(List<String> safeLines, boolean marker) {
        lines = List.copyOf(safeLines);
    }

    Notes withLine(String text) {
        Objects.requireNonNull(text, "text");
        List<String> next = new ArrayList<>(lines);
        next.add(text);
        return new Notes(next, true);
    }

    List<String> lines() {
        return lines;
    }
}

public class ImmutableNotesDemo {
    public static void main(String[] args) {
        StringBuilder external = new StringBuilder("A");
        List<StringBuilder> input = List.of(external);

        Notes original = new Notes(input);
        Notes updated = original.withLine("B");

        external.append("!");
        System.out.println("original=" + original.lines());
        System.out.println("updated=" + updated.lines());
        System.out.println("same root=" + (original == updated));
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 ImmutableNotesDemo.java
java ImmutableNotesDemo
~~~

**Stdout:**

~~~text
original=[A]
updated=[A, B]
same root=false
~~~

Here, the public constructor **snapshots the string value** from each StringBuilder, so modifying `external` afterward does not touch Notes. The elements stored in Notes are immutable Strings. `withLine` builds a candidate list and creates a new Notes instance containing the snapshot.

The private constructor adds a `boolean marker` parameter to distinguish the signature taking `List<String>` from `List<StringBuilder>` after **type erasure**; the marker carries no business meaning. In production code, you should define a **named static factory** or restructure the constructors for better readability, avoiding a “flag parameter” used solely to disambiguate a generic overload. This lesson intentionally shows that two constructors differing only in the List type argument cannot be directly overloaded in Java due to erasure.

## 31. Copy Constructors and `withX`: How Do They Differ from `clone()`?

An immutable API can use:

~~~java
final class Label {
    private final String text;

    Label(String text) {
        if (text == null || text.isBlank()) {
            throw new IllegalArgumentException("label rỗng");
        }
        this.text = text;
    }

    Label(Label source) {
        this(source.text);
    }

    Label withText(String next) {
        return new Label(next);
    }

    String text() {
        return text;
    }
}
~~~

This is a valid class. The **copy constructor** receives an existing object and runs the regular constructor with validation; `withText` creates a new value differing in only one field.

`Object.clone()`, by contrast, has its own mechanism, usually performs a shallow copy, and does not run the copy's regular constructor. For value objects with invariants, explicitly named `withX`/copy factories/constructors are usually **easier to control** than relying on a shallow clone being implemented properly for all nested references.

There is no need to implement `Cloneable` solely to build immutable updates. If a class already has a copy contract using clone from a specialized API, follow that API's contract.

## 32. How Do Immutability and Java `final` Differ in Updates?

The snippet:

~~~java
final class MutableInside {
    private final java.util.ArrayList<String> values =
            new java.util.ArrayList<>();

    void add(String value) {
        values.add(value);
    }
}
~~~

is a **mutable** class, even though the class is final and the field is final. `final` on the field prevents `values = new ArrayList<>()` in normal methods, **not `values.add`**.

In an immutable value object, the fields participating in state should:

- Not be reassigned after the object is constructed.
- Not hold mutable references that callers can modify through leaked paths.
- Not be indirectly altered by public methods.
- Not be mutated by background tasks in a way that changes the logical value.
- Be created through necessary validation/normalization.

`final class` helps prevent subclasses from breaking the contract; `private final` helps prevent field reassignment. **These two keywords are supporting tools**, not the sole proof of immutability.

## 33. Multi-Step Computation and Exception Policy

An immutable update typically has the structure:

~~~text
old value (unmodified)
      |
      v
validate request
      |
      v
compute new fields
      |
      v
validate new fields in constructor/factory
      |
      v
return new value
~~~

If a step fails, no result object is published to the caller. The old version is not mutated.

However:

- If an update method **calls an external service**, writes to a database, or modifies a dependency object, an exception may leave **other side effects**, even though the receiver remains immutable.
- If multiple updates must form an atomic business operation, you need to design a **composite update** or a transaction at the appropriate layer.
- If the transformation takes mutable input data that is changed concurrently, the computation may read an inconsistent state unless snapshotted/synchronized.

Therefore, an **immutable receiver** does not by itself create an ACID transaction. Separate the guarantee of “not mutating the old object” from the guarantee of “having no side effects anywhere in the entire system”.

## 34. Multithreading: Immutable Values Make Reads Safe, While the Current Variable Must Still Be Updated Safely

Suppose multiple threads share an immutable `Settings` record. Reading `settings.theme()` on a fully constructed object can be simpler than reading multiple mutable fields that are concurrently being updated.

However, if a variable holding the **current Settings value** needs to change from S0 to S1, multiple threads writing to the variable still require coordination.

A common example:

~~~java
java.util.concurrent.atomic.AtomicReference<Settings> state =
        new java.util.concurrent.atomic.AtomicReference<>(
                new Settings("light", 14));
state.updateAndGet(old -> old.withFontSize(16));
~~~

This is an illustrative snippet based on `Settings` in section 16. `AtomicReference` manages the **currently published reference**. `updateAndGet` may re-invoke the update function under contention, so the update function should **have no side effects**; it should only compute the new value from the old value.

An important point: using `AtomicReference` protects **replacing the reference** via an atomic API; it does not turn any mutable child objects inside Settings into immutable ones. The value object design must still protect its own state.

## 35. Experiment 13 — Publishing a New Version with `AtomicReference`

Create the file **`AtomicImmutableStateDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicReference;

record AppConfig(String mode, int threshold) {
    AppConfig {
        if (mode == null || mode.isBlank()) {
            throw new IllegalArgumentException("mode rỗng");
        }
        if (threshold < 0) {
            throw new IllegalArgumentException("threshold âm");
        }
    }

    AppConfig withThreshold(int next) {
        return new AppConfig(mode, next);
    }
}

public class AtomicImmutableStateDemo {
    public static void main(String[] args) {
        AtomicReference<AppConfig> ref =
                new AtomicReference<>(new AppConfig("normal", 10));

        AppConfig first = ref.get();
        AppConfig second = ref.updateAndGet(
                old -> old.withThreshold(
                        Math.addExact(old.threshold(), 5)));

        System.out.println("first=" + first);
        System.out.println("second=" + second);
        System.out.println("current=" + ref.get());
        System.out.println("first unchanged="
                + (first.threshold() == 10));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 AtomicImmutableStateDemo.java
java AtomicImmutableStateDemo
~~~

**Stdout (the program runs sequentially for a deterministic result):**

~~~text
first=AppConfig[mode=normal, threshold=10]
second=AppConfig[mode=normal, threshold=15]
current=AppConfig[mode=normal, threshold=15]
first unchanged=true
~~~

`AtomicReference` holds the active reference. `first` still points to the threshold-10 version after the update; `second` and `ref.get()` point to the threshold-15 version.

In a real system, if the update function both sends an email and computes the new config, a CAS retry could send **multiple emails**. Therefore, the update function should be a side-effect-free transformation, while external actions should be coordinated at the appropriate layer.

## 36. A Mutable Builder to Construct an Immutable Object

It is not necessary to avoid every mutable object across the entire program. A practical pattern:

1. Use a local **mutable builder** to assemble data.
2. Validate the final constraints.
3. Create an **immutable snapshot** when complete.
4. Do not leave the builder with any path to modify state inside the snapshot.

Create the file **`BuilderToImmutableDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

record ReadingPlan(List<String> chapters) {
    ReadingPlan {
        chapters = List.copyOf(chapters);
    }

    ReadingPlan withChapter(String chapter) {
        List<String> next = new ArrayList<>(chapters);
        next.add(Objects.requireNonNull(chapter));
        return new ReadingPlan(next);
    }
}

final class PlanBuilder {
    private final List<String> chapters = new ArrayList<>();

    PlanBuilder add(String chapter) {
        chapters.add(Objects.requireNonNull(chapter));
        return this;
    }

    ReadingPlan build() {
        return new ReadingPlan(chapters);
    }
}

public class BuilderToImmutableDemo {
    public static void main(String[] args) {
        PlanBuilder builder = new PlanBuilder();
        builder.add("Class");

        ReadingPlan first = builder.build();
        builder.add("Object");
        ReadingPlan second = builder.build();
        ReadingPlan third = first.withChapter("Immutable");

        System.out.println("first=" + first.chapters());
        System.out.println("second=" + second.chapters());
        System.out.println("third=" + third.chapters());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 BuilderToImmutableDemo.java
java BuilderToImmutableDemo
~~~

**Stdout:**

~~~text
first=[Class]
second=[Class, Object]
third=[Class, Immutable]
~~~

The builder is allowed to modify its own list, whereas `ReadingPlan` takes a snapshot with `List.copyOf`; therefore, continuing to add Object via the builder does not change first. `withChapter` also creates a new version without affecting the builder or first.

This is **immutable at boundary**: internal mutable assembly can still be simple/efficient, while the state published externally is immutable.

## 37. Performance: Allocation, O(n) Copy Cost, and Structural Sharing

Returning a new object can cost:

- **Allocation** of the root object, even if only one field changes.
- **Collection copying** on every update, especially for a large `ArrayList`.
- **GC pressure** if many versions are created very rapidly.
- **Memory retention** if history retains all versions.

However, there are also advantages:

- Immutable objects are often easier to **cache, memoize, and share** when the contract is properly designed.
- No need to defensively copy every **immutable component**.
- Only create changed nodes and **share immutable structure** across unchanged nodes.
- The JIT/JVM has its own optimizations; you should not conclude that immutable updates are always slower solely from the number of `new` calls in source code.
- For small operations and moderately sized data, the cost may matter less than clarity and reducing aliasing bugs.

If you need to update a million-element list continuously, “copying the entire ArrayList for each added element” is usually inefficient. You can use a mutable builder within a closed scope, batch updates, or a specialized **persistent data structure**.

Here, **persistent structure** means a data structure that preserves old versions by sharing immutable nodes; it does not mean automatically persisting data to disk or a database.

## 38. Is Returning a New Object Always Right for Entities?

No. An object can be:

- **Value object:** a value defined by its content, such as coordinates, numeric ranges, or Money. Immutable updates are a very natural choice.
- **Entity:** an entity with identity, lifecycle, and transaction boundaries, such as a long-lived persisted account or order. Immutable snapshots can be used for entities, but **identity and persistence** require separate policies.
- **Mutable aggregate/service:** objects with responsibilities such as managing caches, data streams, connections, or concurrent counters; it is not necessarily desirable to clone the entire object on every operation.

For example, an immutable balance does not by itself execute a successful money transfer in a database. Another layer must verify both accounts together, prevent version overwrites, and commit or roll back within a transaction.

**Right mindset:** prefer immutable values when they fit the domain semantics and API; do not force every service, session, file stream, or persistence entity into “every command returns another object”.

## 39. Testing Immutable Updates: Observe Both Before and After

A good test suite should verify:

| What to check | Example |
| --- | --- |
| Old version does not change | `source.level() == 2` after `withLevel(3)` |
| New result is correct | `result.level() == 3` |
| Other fields are preserved | Changing theme does not change fontSize |
| Validation still applies | Out-of-range level throws an error |
| No mutation after error | Old version remains unchanged after an exception |
| Mutable input references are isolated | Caller modifying input does not change the old version |
| Getters do not expose mutable state | Caller cannot modify the internal list |
| Immutable elements are truly independent | No alias retained to a MutableLine with a setter |
| Nested update preserves the old parent | Old User still has the old Address |
| No-op cases have a clear contract | May return `this` if data is unchanged |
| Equality and identity are not confused | `equals` differs from `==` |
| Collection updates do not break invariants | No duplicate SKUs if the contract forbids them |
| Concurrency publication has a mechanism | State reference updates atomically when needed |
| No repeated side effects on retry | CAS update function does not send emails |

If a test only asserts the **return value** without asserting that the old receiver remains intact, an implementation that accidentally mutates the object and returns `this` can slip through.

With mutable input, test **both directions**: mutate the input after constructing the object, and attempt to mutate the data returned from the getter. Protecting only one of the two paths is not enough.

## 40. Common Mistakes and How to Fix Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling `withX` and discarding the result | Variable continues pointing to the old version | Store or pass along the return value |
| `withX` mutates `this` | Breaks the immutable contract | Create a new value without assigning to the receiver |
| `new Root(old.list)` while keeping a mutable list | Versions still share mutations | Use a snapshot and immutable elements |
| Using `Collections.unmodifiableList` on input still modified externally | Live view, does not protect a snapshot | `List.copyOf`/defensive copy |
| `List.copyOf` of mutable elements | Only shallow-copies the container | Copy elements or use an immutable DTO |
| New method bypasses constructor validation | Can create invalid values | Route all updates through the factory/constructor |
| Updating two fields sequentially through an invalid state | Exception at intermediate step | Use a composite update method |
| Using `==` to determine value changes | Confuses identity with equality | Define contractual value equality |
| Forcing `withX` to always allocate new unnecessarily | Unnecessary allocations | Allow returning `this` when appropriate per contract |
| Copying an entire oversized list in a loop | O(n) cost per update | Batch/builder/persistent data structure |
| Using immutable Balance instead of transactions | Lost updates/state overwrites | Storage-layer synchronization/transactions |
| CAS update function has side effects | Side effects may repeat on retry | Pure update, separate side effects |
| Allowing callers to modify child objects via getter | Snapshot root still changes logically | Defensive copy or immutable elements |
| Assuming records are automatically deeply immutable | Mutable components can still change | Compact constructor + safe accessors |
| Requiring every object to be immutable even for sockets/services | Does not match resource lifecycle | Keep data immutable, manage resources separately |
| Retaining many versions without bounds | High memory consumption | Retention/snapshot/diff policy |

## 41. Self-Practice Exercises

**Question 1.** Why does `final MutablePoint p = ...` not prevent `p.moveBy(1,2)` if `moveBy` modifies fields?

**Question 2.** `Point next = point.movedBy(3,4)` returns a new object. Does the value of `point` change afterward? If the variable `point` is reassigned `point = next`, is the old object mutated?

**Question 3.** A record `Score(int points)` has `Score add(int n)`. Why does calling `score.add(5)` and discarding the result not change score?

**Question 4.** `withLevel(99)` on a valid object is rejected in the constructor. What happens to the old object?

**Question 5.** Why should `Math.addExact` be used in an immutable Balance stored as a long when addition can overflow?

**Question 6.** A new object keeps the same `ArrayList<MutableItem>` as the old object. Are the two versions guaranteed to be independent?

**Question 7.** A constructor uses `List.copyOf(input)` when `input` contains `StringBuilder`. Callers still hold each builder. Is deep immutability guaranteed?

**Question 8.** `Settings withTheme("light")` on Settings with theme=light returns `this`. Does this break immutability?

**Question 9.** Two records are created separately but have equal components. Do `==` and `equals` necessarily produce the same result?

**Question 10.** Range[1,5] needs to become Range[10,20]. Why can `withStart(10)` fail while `withBounds(10,20)` succeeds?

**Question 11.** How do `List.copyOf(backing)` and `Collections.unmodifiableList(backing)` differ when backing changes?

**Question 12.** An immutable cart accepts `List<Item>`, but its constructor does not check for duplicate SKUs. Does the API guarantee the invariant “each SKU appears once”?

**Question 13.** If Person contains an immutable Address, does changing city require deep-cloning every object in the application?

**Question 14.** `Stream.map` returns the same old element A and a new element B. Under what condition is sharing A safe?

**Question 15.** Why does storing different immutable Draft versions support undo more simply than adding the same MutableDraft to a List multiple times?

**Question 16.** If a `withUpdated` method writes a record to a database before throwing an exception, does having an immutable receiver make the overall operation side-effect-free?

**Question 17.** Two threads read the old config concurrently and create a new config. Does using an immutable Config alone prevent lost updates?

**Question 18.** `AtomicReference.updateAndGet` can invoke the update function multiple times. Why should the update lambda avoid sending emails or mutating an external list?

**Question 19.** Why is a mutable builder still appropriate in a workflow that returns immutable objects?

**Question 20.** When does “copying the entire ArrayList every time an element is added” cause performance problems? What alternative design approaches exist?

### Answers and Explanations

1. `final` on a variable only prevents reassigning the reference; it does not forbid mutating the target object.
2. The old `point` does not change; reassigning the variable to next only changes the held reference, without modifying the old object.
3. The method only creates and returns a new value and has no setter; the return value must be used.
4. Unchanged. The constructor does not return a new value, and the old object continues to exist validly.
5. To detect overflow with an exception rather than storing an incorrect long result.
6. No; an aliased mutable list or mutable elements can cause both versions to change together.
7. No; List.copyOf only prevents modifying the list and does not deep-copy StringBuilder elements.
8. No; the state does not change, and returning the same immutable object is a valid contract.
9. No; two different references have `== false`, whereas records with equal component values normally have `equals true`.
10. `[10,5]` violates start<=end; `withBounds` directly creates a valid `[10,20]`.
11. A snapshot does not continue to reflect a mutable backing list; an unmodifiable view does.
12. No; the constructor must validate uniqueness or use a representation that prevents duplicates on every entry path.
13. No. Create a new Address and a new Person along the update path; sharing other immutable objects is safe.
14. When A is truly immutable and cannot be mutated indirectly through other references.
15. Each Draft preserves the exact value at that point in time; the same MutableDraft in a List would observe the latest state across all entries.
16. No. Immutability only states that the receiver is not modified; other side effects can still occur.
17. No. Publishing or updating the reference requires appropriate CAS, synchronization, or transactions.
18. Because a CAS retry can repeat side effects; the lambda should only compute the new value from the old value.
19. The builder can mutate its own data while constructing; the snapshot must isolate aliases upon publication.
20. With large lists or frequent updates, copying at each step can cost O(n). You can batch updates, use a mutable builder in a closed scope, or use a persistent structure.

## 42. Checklist for Applying to a Java Project

- Are the **logical value** and invariants of the class clearly stated?
- Does the update API return a **new value** instead of mutating `this`?
- Do callers understand that they need to store or pass along the return value?
- Are the remaining fields preserved accurately when updating one field?
- Are constructors/factories reused to validate every new result?
- Are null, negative numbers, overflow, and domain bounds handled appropriately?
- Are there cases where multiple fields must be updated together rather than sequentially through an invalid state?
- Are mutable inputs protected from aliasing?
- Could getters and returned elements allow callers to modify internal state?
- Do records/collections contain only immutable elements or perform deep copying to the proper scope?
- Is it clearly defined whether the no-op case returns `this` or a new instance?
- Do tests assert that the **original receiver is unchanged** after both success and failure?
- Is `equals` (value) distinguished from `==` (identity)?
- Does a nested update copy the changed nodes properly and share the remaining immutable nodes?
- If history is retained, is there a memory management policy?
- If multiple threads are involved, is updating the current reference properly synchronized?
- Does the update lambda have dangerous side effects if re-executed due to a retry?
- If a database is involved, is there separate transaction/concurrency control?
- Is performance measured before switching to a mutable strategy or persistent structure?
- Are you forcing an immutable object onto a resource/service that requires a mutable lifecycle?

## 43. Official Java 17 Documentation

- [JLS 17 §8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): records, components, and compact constructors.
- [JLS 17 §4.12.4 — final Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): meaning of `final` for references/variables.
- [JLS 17 §17.5 — final Field Semantics](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.5): final fields and initialization safety under the Java Memory Model.
- [Java SE 17 — List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): unmodifiable snapshot and shallow-copy limitations.
- [Java SE 17 — Stream.toList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList()): list result that does not support direct modification.
- [Java SE 17 — Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)): unmodifiable view reflecting the backing list.
- [Java SE 17 — Math.addExact](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html#addExact(long,long)): overflow checking.
- [Java SE 17 — UnaryOperator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/UnaryOperator.html): represents a `T -> T` transformation.
- [Java SE 17 — AtomicReference.updateAndGet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html#updateAndGet(java.util.function.UnaryOperator)): publishing a new value and noting that the update function may be recomputed.
- [Java SE 17 — Objects.requireNonNull](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#requireNonNull(T)): null checking.
- [Java SE 17 — LocalDate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html): an example of a temporal immutable API; date-addition operations return result objects.
- [Java SE 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): immutable numeric type with operations returning new values.

**Remember:** to “change” an **immutable value**, **create a new value describing the desired state** and leave the original intact. This design reduces alias-driven side effects, clarifies validation, makes history easy to build, and pairs well with functional processing. However, you must protect **all observable mutable state**, not just the root object or final references; and when persistence or multithreading is involved, **publishing or committing the new value** still requires properly scoped concurrency/transaction mechanisms.
