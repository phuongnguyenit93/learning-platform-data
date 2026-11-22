# Record: Validation, Data Normalization, and Defensive Copying in Java 17+

In Java 17, `record` helps model **data-carrying objects** by declaring *components*. Java automatically generates private final fields, public accessors, a canonical constructor, `equals`, `hashCode`, and `toString` when you do not provide those members yourself.

~~~java
record User(String name, int age) {}
~~~

However, **records do not automatically validate data, normalize strings, or copy mutable objects**. If you only write `record User(String name, int age) {}`, the program can create `new User(null, -10)`. If a record holds a `List`, `Map`, array, or mutable object, the fact that the component fields are `final` **does not automatically make the inner data immutable**.

This lesson focuses on three key responsibilities of a *record constructor/accessor*:

1. **Validation:** reject inputs that violate business constraints with the right exception.
2. **Normalization:** convert multiple equivalent representations into a single consistent form before storing.
3. **Defensive copying:** prevent callers from modifying the record's state through aliases to mutable data.

This is a standalone self-study README for **Java Core — Class & Object / Record** with **Java 17+**. Complete programs include file names, `javac`/`java` commands, and expected stdout; illustrative-only snippets are explicitly noted.

## 1. Learning Outcomes

After this lesson, you will be able to:

- Write records with a **compact canonical constructor**.
- Distinguish between a compact constructor and an explicit canonical constructor.
- Validate null, blank, range, relationships between components, and business invariants.
- Normalize strings with `strip()`, casing with `Locale.ROOT`, and structured data.
- Understand that normalization differs from validation and must fit the domain.
- Know that you must not assign `this.component = ...` inside a compact constructor.
- Perform validation before valid state is published through the object.
- Intentionally choose between `IllegalArgumentException` and `NullPointerException`.
- Use `List.copyOf`, `Set.copyOf`, and `Map.copyOf` within their proper limits.
- Understand how a *snapshot* differs from an *unmodifiable live view*.
- Distinguish between shallow copy and deep copy with mutable elements.
- Protect array components using `clone()` in the constructor **and accessor**.
- Recognize when the default `equals/hashCode/toString` is unsuitable for arrays.
- Protect records used as `HashMap` keys from unexpected mutation.
- Choose immutable components from `java.time` instead of mutable legacy types when appropriate.
- Design records containing nested records, collections, and data payloads.
- Test valid/invalid/edge inputs, normalization, aliasing, and the equality contract.
- Distinguish common mistakes in constructors, accessors, and factories.
- Decide when a record is appropriate and when a regular class should be used.

## 2. What Does a Record Generate?

Given the declaration:

~~~java
record Point(int x, int y) {}
~~~

Java provides the usage equivalent of:

- private final fields `x` and `y`;
- accessor methods `int x()` and `int y()`;
- a public/package-appropriate canonical constructor `Point(int x, int y)` according to access rules;
- `equals(Object)` comparing the record components according to record rules;
- `hashCode()` computed from the components;
- `toString()` displaying the record name and component values.

A record implicitly extends `java.lang.Record` and cannot arbitrarily extend another class. It can implement interfaces.

**Important:** `final` on fields only prevents **reassigning the field's reference/value** after initialization. It does not automatically control the mutable object that a field points to.

~~~java
record Group(java.util.List<String> members) {}
~~~

If a caller passes an `ArrayList` into `new Group(list)`, the `members` component keeps a reference to the same List object unless the record makes a copy.

## 3. Starting with Validation in a Compact Constructor

A **compact constructor** has the form:

~~~java
record Person(String name, int age) {
    Person {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        if (age < 0 || age > 150) {
            throw new IllegalArgumentException("age out of range");
        }
    }
}
~~~

You do not declare a parameter list in `Person { ... }`, yet Java lets you use parameters named after the record components: `name`, `age`. When the compact constructor body completes normally, **the compiler automatically assigns the final fields from the final parameter values**.

The advantage: you only write the necessary validation/normalization without repeating `this.name = name` boilerplate.

### Key Rule

Inside a compact constructor, **do not assign directly to a component field**:

~~~java
record Invalid(String name) {
    Invalid {
        // this.name = name; // Compile error in a compact constructor.
    }
}
~~~

To change the value stored in the component, **reassign the parameter** `name = ...`.

## 4. Runnable Program: Constructor Rejecting Invalid Data

Create **`RecordValidationDemo.java`**:

~~~java
public class RecordValidationDemo {
    record Person(String name, int age) {
        Person {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("name");
            }
            if (age < 0 || age > 150) {
                throw new IllegalArgumentException("age");
            }
        }
    }

    public static void main(String[] args) {
        Person ok = new Person("Mai", 20);
        System.out.println(ok);

        try {
            new Person(" ", 20);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }

        try {
            new Person("An", -1);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RecordValidationDemo.java
java RecordValidationDemo
~~~

Stdout:

~~~text
Person[name=Mai, age=20]
invalid=name
invalid=age
~~~

Whenever `new Person(...)` violates an invariant, the constructor throws an exception; the record creation expression **does not return a valid instance** to the caller.

## 5. Validation and Normalization Are Different

**Validation** answers: "Is this input acceptable?"

**Normalization** answers: "If accepted, what canonical form should be stored?"

For example, with input `"  Mai  "`:

- Validation can reject null or whitespace-only values.
- Normalization can use `strip()` to store `"Mai"`.
- If the domain allows names with leading or trailing whitespace, stripping automatically may **unintentionally alter the data's meaning**; the policy must be clearly defined.

For an identifier like `"  AbC  "`, some domains want it normalized to `"abc"`, while other domains require preserving case. **Do not automatically lowercase every string** just because the API supports it.

A sensible order is usually:
1. determine the null policy;
2. normalize into a temporary form;
3. validate the canonical form;
4. store only the validated value.

## 6. Compact Constructor Normalizing by Reassigning Parameters

~~~java
record Account(String username) {
    Account {
        username = java.util.Objects.requireNonNull(
                username, "username").strip()
                .toLowerCase(java.util.Locale.ROOT);

        if (username.isEmpty()) {
            throw new IllegalArgumentException("blank username");
        }
    }
}
~~~

`username = ...` in a compact constructor is a **reassignment of the constructor parameter**, not a direct field assignment. After the constructor body, Java automatically assigns the record field from the normalized value.

### Why Use `Locale.ROOT`?

Case conversion operations can be locale-dependent. For **technical identifiers** that require consistent behavior, `Locale.ROOT` is generally more appropriate than the default system locale. For personal names, natural language, and locale-specific identifying information, the rules must follow the domain — do not apply a single generic conversion mechanically.

## 7. Runnable Program: Username Normalization

Create **`RecordNormalizationDemo.java`**:

~~~java
import java.util.Locale;
import java.util.Objects;

public class RecordNormalizationDemo {
    record Account(String username) {
        Account {
            username = Objects.requireNonNull(
                    username, "username")
                    .strip()
                    .toLowerCase(Locale.ROOT);

            if (username.isBlank()) {
                throw new IllegalArgumentException("username blank");
            }
        }
    }

    public static void main(String[] args) {
        Account first = new Account("  ADMIN  ");
        Account second = new Account("admin");

        System.out.println(first.username());
        System.out.println("equal=" + first.equals(second));

        try {
            new Account("   ");
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RecordNormalizationDemo.java
java RecordNormalizationDemo
~~~

Stdout:

~~~text
admin
equal=true
invalid=username blank
~~~

Two inputs with different textual representations become the same canonical username. Therefore, the default record `equals/hashCode` now behaves consistently with the **normalized field values**.

## 8. Normalize First or Validate First?

There is no single order that is right for every domain.

For example:

~~~java
String normalized = Objects.requireNonNull(raw, "raw").strip();
if (normalized.isEmpty()) {
    throw new IllegalArgumentException("blank");
}
~~~

If the business rule forbids whitespace at either end, you **should not automatically strip first and then accept**, but rather validate the raw input:

~~~java
if (!raw.equals(raw.strip())) {
    throw new IllegalArgumentException("leading/trailing spaces");
}
~~~

The rule should be specified:

| Policy | Input `" A "` | Result |
| --- | --- | --- |
| Normalize whitespace | Accepted | Stores `"A"` |
| Strict identifier | Rejected | Exception |
| Text verbatim | Accepted | Stores `" A "` |

Do not write an overly broad normalization policy that discards important data such as the email local-part, case-sensitive codes, or intentional whitespace.

## 9. Validating Multiple Components Together

Records can contain components with **interdependent constraints**.

~~~java
record DateRange(java.time.LocalDate start,
                 java.time.LocalDate end) {
    DateRange {
        java.util.Objects.requireNonNull(start, "start");
        java.util.Objects.requireNonNull(end, "end");

        if (end.isBefore(start)) {
            throw new IllegalArgumentException(
                    "end must not precede start");
        }
    }
}
~~~

This is an invariant over the **start/end pair** that cannot be fully validated on each field independently.

Because `LocalDate` is immutable, there is no need to defensively clone the dates. If mutable `java.util.Date` were used, the problem would be different.

## 10. Runnable Program: DateRange Record

Create **`RecordDateRangeDemo.java`**:

~~~java
import java.time.LocalDate;
import java.util.Objects;

public class RecordDateRangeDemo {
    record DateRange(LocalDate start, LocalDate end) {
        DateRange {
            Objects.requireNonNull(start, "start");
            Objects.requireNonNull(end, "end");

            if (end.isBefore(start)) {
                throw new IllegalArgumentException("range");
            }
        }

        long daysInclusive() {
            return java.time.temporal.ChronoUnit.DAYS
                    .between(start, end) + 1;
        }
    }

    public static void main(String[] args) {
        DateRange valid = new DateRange(
                LocalDate.of(2026, 10, 1),
                LocalDate.of(2026, 10, 3));

        System.out.println("days=" + valid.daysInclusive());

        try {
            new DateRange(
                    LocalDate.of(2026, 10, 3),
                    LocalDate.of(2026, 10, 1));
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RecordDateRangeDemo.java
java RecordDateRangeDemo
~~~

Stdout:

~~~text
days=3
invalid=range
~~~

`daysInclusive` is a valid instance method on a record. A record is suitable because a range is a simple value object with clear invariants.

## 11. Exception Policy for Invalid Input

Common choices:

- `Objects.requireNonNull(value, "field")` → `NullPointerException` with a message when the input is null; appropriate when null is forbidden by the contract.
- `IllegalArgumentException` → data has the right type but violates a domain rule (blank, negative, range).
- Custom unchecked exception → only when the API/domain has a consistent contract and callers need distinct classification.
- Checked exceptions → consider at boundaries involving IO/external operations, not for pure validation.

For example:

~~~java
record Quantity(int value) {
    Quantity {
        if (value <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }
    }
}
~~~

**Do not use `assert` to validate user input**: Java assertions can be disabled at runtime. Public invariants should be checked normally and throw an exception.

## 12. Runnable Program: Distinguishing Null and Blank

Create **`RecordExceptionPolicyDemo.java`**:

~~~java
import java.util.Objects;

public class RecordExceptionPolicyDemo {
    record Category(String code) {
        Category {
            code = Objects.requireNonNull(code, "code").strip();
            if (code.isEmpty()) {
                throw new IllegalArgumentException("blank code");
            }
        }
    }

    public static void main(String[] args) {
        try {
            new Category(null);
        } catch (NullPointerException ex) {
            System.out.println("null=" + ex.getMessage());
        }

        try {
            new Category("   ");
        } catch (IllegalArgumentException ex) {
            System.out.println("blank=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RecordExceptionPolicyDemo.java
java RecordExceptionPolicyDemo
~~~

Stdout:

~~~text
null=code
blank=blank code
~~~

The API distinguishes null from a blank value; consumers can handle errors according to a clear contract.

## 13. Compact vs. Explicit Canonical Constructor

There are two standard forms:

**Compact canonical constructor**:

~~~java
record Email(String address) {
    Email {
        address = address.strip();
    }
}
~~~

**Explicit canonical constructor**:

~~~java
record Email(String address) {
    Email(String address) {
        this.address = address.strip();
    }
}
~~~

In an explicit canonical constructor:
- the parameter list must match the record components according to canonical constructor rules;
- you must assign each component field properly and validly before the constructor finishes;
- you can explicitly determine the order of assignment logic, though Java's final-field/definite-assignment rules still apply.

In a compact constructor, the compiler handles field assignments after the body. **Do not write both canonical constructor forms at the same time** for the same signature.

## 14. Runnable Program: Two Equivalent Forms

Create **`CanonicalFormsDemo.java`**:

~~~java
public class CanonicalFormsDemo {
    record Compact(String code) {
        Compact {
            code = code.strip();
        }
    }

    record Explicit(String code) {
        Explicit(String code) {
            this.code = code.strip();
        }
    }

    public static void main(String[] args) {
        Compact a = new Compact(" A ");
        Explicit b = new Explicit(" A ");

        System.out.println("compact=" + a.code());
        System.out.println("explicit=" + b.code());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 CanonicalFormsDemo.java
java CanonicalFormsDemo
~~~

Stdout:

~~~text
compact=A
explicit=A
~~~

In short examples, a compact constructor avoids boilerplate. When an explicit canonical constructor is needed for a valid reason, assignments must be handled completely and consistently.

## 15. Record Does Not Mean Deeply Immutable

Consider:

~~~java
record Team(java.util.List<String> members) {}
~~~

Creating it with an ArrayList:

~~~java
java.util.List<String> original =
        new java.util.ArrayList<>(java.util.List.of("Mai"));

Team team = new Team(original);
original.add("An");
~~~

Because a record by default keeps **the same List reference** in `members`, `team.members()` can now contain Mai and An.

Immutability requires distinguishing:
- **Field immutability:** a final record component field cannot be reassigned.
- **Shallow structural immutability:** the collection object cannot be modified through an exposed reference.
- **Deep immutability:** elements and nested mutable objects also cannot be modified unintentionally.
- **Snapshot semantics:** the record holds data from a point in time rather than live-following an external collection.

You cannot infer deep immutability from the `record` keyword alone.

## 16. Runnable Program: Aliasing Bug Without Copying

Create **`BadRecordAliasingDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class BadRecordAliasingDemo {
    record Team(List<String> members) {}

    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("Mai");

        Team team = new Team(source);
        System.out.println("before=" + team.members());

        source.add("An");
        System.out.println("after=" + team.members());

        team.members().add("Binh");
        System.out.println("source=" + source);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 BadRecordAliasingDemo.java
java BadRecordAliasingDemo
~~~

Stdout:

~~~text
before=[Mai]
after=[Mai, An]
source=[Mai, An, Binh]
~~~

Mutations in both directions can affect the same object. This is an anti-pattern when a record is expected to represent a snapshot.

## 17. Defensive Copying of Collections with `List.copyOf`

~~~java
record Team(java.util.List<String> members) {
    Team {
        members = java.util.List.copyOf(
                java.util.Objects.requireNonNull(members, "members"));
    }
}
~~~

`List.copyOf`:
- creates an **unmodifiable list** containing the elements of the input at the time of the call, in list iteration order;
- does not reflect subsequent structural changes to the mutable source;
- rejects null elements with `NullPointerException`;
- may reuse an existing unmodifiable list instead of always allocating a new List;
- **does not deep-copy elements**.

If the elements are immutable Strings, a snapshot of the list structure is usually sufficient.

**Important:** `List.copyOf` does not merely create a live view of the original ArrayList. It has snapshot semantics for the collection structure.

## 18. Runnable Program: List.copyOf Protects Both Directions

Create **`RecordListCopyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class RecordListCopyDemo {
    record Team(List<String> members) {
        Team {
            members = List.copyOf(
                    Objects.requireNonNull(members, "members"));
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("Mai");

        Team team = new Team(source);
        source.add("An");

        System.out.println("source=" + source);
        System.out.println("record=" + team.members());

        try {
            team.members().add("Binh");
        } catch (UnsupportedOperationException ex) {
            System.out.println("record list unmodifiable");
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RecordListCopyDemo.java
java RecordListCopyDemo
~~~

Stdout:

~~~text
source=[Mai, An]
record=[Mai]
record list unmodifiable
~~~

Changes to the input do not change the record list; the accessor returns an unmodifiable list, so the caller cannot add an element through the accessor.

## 19. `List.copyOf` and the Null Elements Policy

~~~java
List<String> list = new ArrayList<>();
list.add(null);
List.copyOf(list); // Throws NullPointerException.
~~~

`List.copyOf` forbids **null elements**, unlike some conventional ways of creating a List. Therefore, the null policy must be defined:

- If elements must not be null: List.copyOf is an appropriate choice.
- If null has domain meaning: consider a different representation or use a snapshot wrapper that allows null.
- If null should simply be ignored: require that explicitly; do not silently filter invalid elements if doing so drops data.

Example of an unmodifiable snapshot that allows null:

~~~java
List<String> snapshot = java.util.Collections.unmodifiableList(
        new java.util.ArrayList<>(source));
~~~

This copies the structure and wraps it as unmodifiable, though it is still a **shallow copy**.

## 20. Is `Collections.unmodifiableList` a Defensive Snapshot?

Not if it directly wraps a mutable list:

~~~java
List<String> source = new ArrayList<>();
List<String> view = Collections.unmodifiableList(source);
source.add("A");
// view will reflect "A".
~~~

`unmodifiableList(source)` creates a **view that disallows mutation through the view reference**, while the underlying source remains mutable by anyone holding another reference.

To create a snapshot wrapper:

~~~java
List<String> stable = Collections.unmodifiableList(
        new ArrayList<>(source));
~~~

A subsequent structural change to source does not affect stable, because stable wraps a **copy**. However, if the elements are mutable, their references are still shared.

If null does not need to be allowed, `List.copyOf(source)` is usually shorter and clearer.

## 21. Runnable Program: Live View Differs from Snapshot

Create **`UnmodifiableViewDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class UnmodifiableViewDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("A");

        List<String> live = Collections.unmodifiableList(source);
        List<String> copied = List.copyOf(source);

        source.add("B");

        System.out.println("source=" + source);
        System.out.println("live=" + live);
        System.out.println("copied=" + copied);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 UnmodifiableViewDemo.java
java UnmodifiableViewDemo
~~~

Stdout:

~~~text
source=[A, B]
live=[A, B]
copied=[A]
~~~

`live` is an unmodifiable view yet still observes structural mutations of source. `copied` has snapshot behavior.

## 22. `Set.copyOf` and `Map.copyOf`

Records often have collections other than List:

~~~java
record Config(java.util.Set<String> flags,
              java.util.Map<String, String> settings) {
    Config {
        flags = java.util.Set.copyOf(flags);
        settings = java.util.Map.copyOf(settings);
    }
}
~~~

`Set.copyOf` creates an unmodifiable set snapshot and forbids null elements. `Map.copyOf` creates an unmodifiable map snapshot and forbids null keys/values.

**Caution on ordering:**
- `Set.copyOf` does not guarantee encounter/iteration order like a List.
- `Map.copyOf` does not promise insertion order.
- If ordering must be part of the contract/API, choose an appropriate collection and copying strategy.

Even though the set/map structure cannot be mutated, **objects stored as elements/keys/values can still be mutable**.

## 23. Runnable Program: Map.copyOf Preserves a Snapshot

Create **`RecordMapCopyDemo.java`**:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

public class RecordMapCopyDemo {
    record Settings(Map<String, String> entries) {
        Settings {
            entries = Map.copyOf(entries);
        }
    }

    public static void main(String[] args) {
        Map<String, String> source = new LinkedHashMap<>();
        source.put("theme", "dark");

        Settings snapshot = new Settings(source);
        source.put("language", "vi");

        System.out.println("snapshot size=" + snapshot.entries().size());
        System.out.println("source size=" + source.size());
        System.out.println("theme=" + snapshot.entries().get("theme"));

        try {
            snapshot.entries().put("x", "y");
        } catch (UnsupportedOperationException ex) {
            System.out.println("unmodifiable");
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RecordMapCopyDemo.java
java RecordMapCopyDemo
~~~

Stdout:

~~~text
snapshot size=1
source size=2
theme=dark
unmodifiable
~~~

The example does not print the entire Map because the iteration order of Map.copyOf is not something to assume.

## 24. Structural Copying Is Still Not a Deep Copy

A record containing `List<MutableItem>` can be built with `List.copyOf`, yet the elements are still the **same objects**:

~~~java
record Order(java.util.List<MutableItem> items) {
    Order {
        items = java.util.List.copyOf(items);
    }
}
~~~

If the caller keeps `MutableItem item` and modifies `item.value`, the record looking through `order.items().get(0)` can also see the change.

Therefore:
- `List.copyOf` **snapshots the List structure**; it does not clone elements.
- For deep immutability, each element must be immutable or snapshotted into an immutable value object.
- If there are nested collections, copying is needed at every level that requires protection.

You should not call `List.copyOf` a "deep copy"; it does not do that.

## 25. Runnable Program: Mutable Element Still Changes

Create **`ShallowCopyPitfallDemo.java`**:

~~~java
import java.util.List;

public class ShallowCopyPitfallDemo {
    static final class MutableScore {
        int points;

        MutableScore(int points) {
            this.points = points;
        }
    }

    record Report(List<MutableScore> scores) {
        Report {
            scores = List.copyOf(scores);
        }
    }

    public static void main(String[] args) {
        MutableScore item = new MutableScore(10);
        Report report = new Report(List.of(item));

        System.out.println("before=" + report.scores().get(0).points);

        item.points = 99;
        System.out.println("after=" + report.scores().get(0).points);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ShallowCopyPitfallDemo.java
java ShallowCopyPitfallDemo
~~~

Stdout:

~~~text
before=10
after=99
~~~

The List structure is immutable, but the element object changes. If the domain requires a true snapshot, you must change the representation or copy the elements.

## 26. Deep Snapshot Using a Nested Immutable Record

A safe approach is to convert each mutable DTO into an **immutable record**:

~~~java
record Score(String student, int points) {}

record GradeBook(java.util.List<Score> scores) {
    GradeBook {
        scores = java.util.List.copyOf(scores);
    }
}
~~~

If `Score` only contains a String and an int (and has been validated), Score objects are structurally immutable and contain no mutable references inside. Thus `List.copyOf` provides a strong list snapshot.

When the input consists of mutable objects, map them to new Score records:

~~~java
scores = source.stream()
        .map(item -> new Score(item.student(), item.points()))
        .toList();
~~~

`Stream.toList()` produces an unmodifiable list (Java 16+), but differs from `List.copyOf` in null policy: `toList()` does not have the same guarantee forbidding null elements. If a null-free policy is needed, validate/pass through List.copyOf.

## 27. Runnable Program: Deep-Copying Mutable Inputs into Immutable Values

Create **`DeepSnapshotRecordDemo.java`**:

~~~java
import java.util.List;

public class DeepSnapshotRecordDemo {
    static final class MutableScore {
        String student;
        int points;

        MutableScore(String student, int points) {
            this.student = student;
            this.points = points;
        }
    }

    record Score(String student, int points) {
        Score {
            if (student == null || student.isBlank()) {
                throw new IllegalArgumentException("student");
            }
            if (points < 0 || points > 100) {
                throw new IllegalArgumentException("points");
            }
        }
    }

    record GradeBook(List<Score> scores) {
        GradeBook {
            scores = List.copyOf(scores);
        }

        static GradeBook fromMutable(List<MutableScore> source) {
            List<Score> snapshots = source.stream()
                    .map(item -> new Score(item.student, item.points))
                    .toList();

            return new GradeBook(snapshots);
        }
    }

    public static void main(String[] args) {
        MutableScore source = new MutableScore("Mai", 10);
        GradeBook book = GradeBook.fromMutable(List.of(source));

        source.points = 99;

        System.out.println("source=" + source.points);
        System.out.println("snapshot=" + book.scores().get(0).points());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 DeepSnapshotRecordDemo.java
java DeepSnapshotRecordDemo
~~~

Stdout:

~~~text
source=99
snapshot=10
~~~

Because each new Score contains no mutable objects, changing MutableScore afterward does not affect GradeBook.

## 28. What If a Nested Record Contains Mutable Data?

A nested record **is not automatically deeply immutable** if it itself contains a mutable array/List.

~~~java
record Image(byte[] pixels) {}
record Album(java.util.List<Image> images) {}
~~~

Even if `Album.images` uses List.copyOf, `Image.pixels()` still exposes a mutable array if Image does not perform defensive copying.

**Recursive rule:** Achieving deep immutability requires checking **the entire reference path** to mutable objects. Nested record layers do not automatically "seal" objects.

You can use:
- immutable primitives, String, enum, and java.time classes;
- collections of immutable elements;
- records with their own defensive-copy rules;
- explicit deep copies for mutable substructures.

## 29. Arrays: Copying in the Constructor Is Not Enough

A record with an array:

~~~java
record Blob(byte[] bytes) {}
~~~

Arrays are mutable, so a caller can:
1. modify the original array after creating Blob;
2. retrieve `blob.bytes()` and modify the array through the default accessor.

Copying only on input **blocks path 1**, not path 2. If the record must protect the data:

~~~java
record Blob(byte[] bytes) {
    Blob {
        bytes = bytes.clone();
    }

    @Override
    public byte[] bytes() {
        return bytes.clone();
    }
}
~~~

`clone()` on a primitive array creates an independent array copy. It is good practice to call `Objects.requireNonNull(bytes,"bytes")` first for a clear message; `bytes.clone()` automatically throws an NPE if bytes is null, though the message may differ.

## 30. Runnable Program: Two-Way Copying for Arrays

Create **`RecordArrayCopyDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Objects;

public class RecordArrayCopyDemo {
    record Blob(byte[] bytes) {
        Blob {
            bytes = Objects.requireNonNull(bytes, "bytes").clone();
        }

        @Override
        public byte[] bytes() {
            return bytes.clone();
        }
    }

    public static void main(String[] args) {
        byte[] input = {1, 2, 3};
        Blob blob = new Blob(input);

        input[0] = 9;
        System.out.println("after source change=" +
                Arrays.toString(blob.bytes()));

        byte[] exposed = blob.bytes();
        exposed[1] = 8;
        System.out.println("after getter change=" +
                Arrays.toString(blob.bytes()));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RecordArrayCopyDemo.java
java RecordArrayCopyDemo
~~~

Stdout:

~~~text
after source change=[1, 2, 3]
after getter change=[1, 2, 3]
~~~

The record keeps its own array copy, and the accessor returns another copy. That is defensive copying of a mutable array component.

## 31. However, Array Components Still Have `equals` and `hashCode` Issues

Record-generated equality compares components according to the semantics of the component types. For an array component, the default is **not element-wise equality** like `Arrays.equals`; instead, array references are compared by identity.

Therefore:

~~~java
record Blob(byte[] bytes) {
    Blob {
        bytes = bytes.clone();
    }

    @Override
    public byte[] bytes() {
        return bytes.clone();
    }
}
~~~

Two Blobs have the same byte content yet hold **two different array objects**; the generated `equals` can return false. `toString` also does not automatically print arrays cleanly by element content.

If the domain requires **value equality by bytes**, override `equals`, `hashCode`, and optionally `toString` consistently.

## 32. A Record That Copies Arrays Still Does Not Automatically Have Value Equality

Suppose two instances are constructed from separate `new byte[]{1,2}` arrays. Each compact constructor clones the input and the accessor clones the output, so **ownership is safe**; however, the default generated `equals` still compares the two array component references, returning false even though the byte contents are equal.

~~~java
record Blob(byte[] bytes) {
    Blob {
        bytes = bytes.clone();
    }
    @Override public byte[] bytes() {
        return bytes.clone();
    }
}
~~~

This is a **record declaration** without `main`. Given `Blob a = new Blob(new byte[]{1,2}); Blob b = new Blob(new byte[]{1,2});`, `a.equals(b)` is false, whereas `Arrays.equals(a.bytes(), b.bytes())` is true.

In this **validation/defensive copying** lesson, the takeaway is that **copying to prevent aliasing does not mean changing equality**. Complete test programs, hash contracts, and identity behavior belong to the dedicated lesson **"equals(), hashCode(), toString() and the Impact of Array Components"**.

## 33. When the Domain Requires Comparing Array Contents

If `byte[]` represents a **value** (rather than buffer identity), you also need to define the contract for `equals` and `hashCode`. For example, inside the body of a `Blob(byte[] bytes)` record that is already defensively copied in both directions, you can write:

~~~java
@Override
public boolean equals(Object other) {
    return other instanceof Blob blob
            && java.util.Arrays.equals(bytes, blob.bytes);
}

@Override
public int hashCode() {
    return java.util.Arrays.hashCode(bytes);
}
~~~

This is only an **additional member-method snippet inside a record**, not a standalone runnable file. For a one-dimensional array, `Arrays.equals` and `Arrays.hashCode` keep the two methods consistent. If the data consists of nested arrays, you need to consider `deepEquals`/`deepHashCode` and corresponding deep copying. `toString` can be customized when you want to display the contents rather than the array identity string.

**Key point:** the constructor is responsible for **validating, normalizing, and protecting ownership**. Deep equality/hash policies belong to the value model and are covered and tested thoroughly in the dedicated lesson on generated methods with array components. Do not override only `equals` without `hashCode`.

## 34. Object Arrays and Multidimensional Arrays

For `String[]`, `clone()` creates a new array, but references to the elements are still shared. If the elements are immutable Strings, that is usually sufficient. For `MutableItem[]`, a shallow array clone does not copy the elements.

For `int[][]`, calling only `matrix.clone()` copies the **outer array**; each inner `int[]` is still shared. To make a deep snapshot of a 2D primitive array:

~~~java
static int[][] copyMatrix(int[][] input) {
    int[][] result = new int[input.length][];
    for (int i = 0; i < input.length; i++) {
        result[i] = input[i].clone();
    }
    return result;
}
~~~

This is an illustrative snippet only; production code requires an explicit null policy for input/rows as well as an equality/content display strategy.

If the nested data structure is too mutable/complex, consider a custom immutable class with a clear contract instead of defaulting to a record with arrays.

## 35. Runnable Program: Deep-Copying a 2D int Array

Create **`MatrixRecordDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Objects;

public class MatrixRecordDemo {
    record Matrix(int[][] rows) {
        Matrix {
            rows = deepCopy(rows);
        }

        @Override
        public int[][] rows() {
            return deepCopy(rows);
        }

        private static int[][] deepCopy(int[][] source) {
            Objects.requireNonNull(source, "rows");
            int[][] result = new int[source.length][];
            for (int i = 0; i < source.length; i++) {
                result[i] = Objects.requireNonNull(
                        source[i], "row " + i).clone();
            }
            return result;
        }

        int at(int row, int column) {
            return rows[row][column];
        }
    }

    public static void main(String[] args) {
        int[][] input = {{1, 2}, {3, 4}};
        Matrix matrix = new Matrix(input);

        input[0][0] = 99;
        int[][] output = matrix.rows();
        output[1][1] = 88;

        System.out.println("at00=" + matrix.at(0, 0));
        System.out.println("at11=" + matrix.at(1, 1));
        System.out.println("snapshot=" +
                Arrays.deepToString(matrix.rows()));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 MatrixRecordDemo.java
java MatrixRecordDemo
~~~

Stdout:

~~~text
at00=1
at11=4
snapshot=[[1, 2], [3, 4]]
~~~

You still need to override equals/hashCode if you want Matrix value equality based on the contents of 2D arrays. `Arrays.deepEquals/deepHashCode` provides the appropriate tools when the data consists of nested arrays.

## 36. The Problem of Mutable Keys in Map and Set

When a record computes `equals/hashCode` based on mutable component objects, changing an external object can cause the record's hash code to change after the record has already been used as a `HashMap` key.

For example:

~~~java
record Key(java.util.List<String> tags) {}
~~~

If tags is a mutable ArrayList, adding a tag after inserting Key into a HashMap causes the component list's hash code to change. Lookups using the same Key reference can fail because the bucket depends on the old hash.

**Final record fields do not prevent this automatically.**

### Solutions

- Normalize and defensively copy the collection in the canonical constructor.
- Store only immutable elements.
- For arrays, clone + implement content equality/hash when value semantics are desired.
- Do not mutate the key's components after creation.

## 37. Runnable Program: Record Key with a Copied List

Create **`RecordMapKeyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class RecordMapKeyDemo {
    record Key(List<String> tags) {
        Key {
            tags = List.copyOf(tags);
        }
    }

    public static void main(String[] args) {
        List<String> input = new ArrayList<>();
        input.add("java");

        Key key = new Key(input);
        Map<Key, String> lookup = new HashMap<>();
        lookup.put(key, "present");

        input.add("record");

        System.out.println("key tags=" + key.tags());
        System.out.println("found=" + lookup.get(key));
        System.out.println("same-value lookup=" +
                lookup.get(new Key(List.of("java"))));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RecordMapKeyDemo.java
java RecordMapKeyDemo
~~~

Stdout:

~~~text
key tags=[java]
found=present
same-value lookup=present
~~~

A List snapshot with immutable Strings keeps record equality/hash stable by value.

## 38. Unicode Normalization: Only Perform When Required by the Contract

Two strings can look identical yet have different Unicode code-point sequences. If the domain requires canonical Unicode text, Java provides:

~~~java
java.text.Normalizer.normalize(
        input, java.text.Normalizer.Form.NFC);
~~~

`NFC` is a Unicode normalization form. However, not every field should undergo Unicode normalization:
- File paths, credentials, cryptographic signatures, or binary-like identifiers may require exact bytes/code points.
- Search/display names may want a different normalization.
- Some domains require case folding or locale-specific logic beyond `toLowerCase(Locale.ROOT)`.

**Policy:** Only normalize according to a published specification; representative Unicode inputs must be tested.

## 39. Runnable Program: Unicode NFC Normalization

Create **`RecordUnicodeDemo.java`**:

~~~java
import java.text.Normalizer;
import java.util.Objects;

public class RecordUnicodeDemo {
    record Label(String value) {
        Label {
            value = Normalizer.normalize(
                    Objects.requireNonNull(value, "value"),
                    Normalizer.Form.NFC);
        }
    }

    public static void main(String[] args) {
        String composed = "\u00E9";
        String decomposed = "e\u0301";

        Label a = new Label(composed);
        Label b = new Label(decomposed);

        System.out.println("same=" + a.equals(b));
        System.out.println("length=" + a.value().length());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RecordUnicodeDemo.java
java RecordUnicodeDemo
~~~

Stdout:

~~~text
same=true
length=1
~~~

Unicode NFC converts both representations into a canonical form according to the chosen goal. `String.length()` is the UTF-16 code-unit count; for the normalized `é` in the example above, it is 1.

## 40. Number Normalization and BigDecimal Have Their Own Rules

`BigDecimal.equals` takes into account both value **and scale**, so:

~~~java
new java.math.BigDecimal("1.0")
    .equals(new java.math.BigDecimal("1.00"))
~~~

returns false, even though `compareTo` returns 0.

If the record treats both amounts as the same value, domain canonicalization is required. You can use `stripTrailingZeros()` where appropriate, or normalize with `setScale(n, roundingMode)` according to currency precision.

**Do not round monetary values without a contract**; rounding can affect transactions.

### Runnable Program

Create **`RecordBigDecimalDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.util.Objects;

public class RecordBigDecimalDemo {
    record Amount(BigDecimal value) {
        Amount {
            value = Objects.requireNonNull(value, "value")
                    .stripTrailingZeros();

            if (value.signum() < 0) {
                throw new IllegalArgumentException("negative");
            }
        }
    }

    public static void main(String[] args) {
        Amount a = new Amount(new BigDecimal("1.0"));
        Amount b = new Amount(new BigDecimal("1.00"));

        System.out.println("equal=" + a.equals(b));
        System.out.println("value=" + a.value().toPlainString());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RecordBigDecimalDemo.java
java RecordBigDecimalDemo
~~~

Stdout:

~~~text
equal=true
value=1
~~~

`BigDecimal` is immutable, so cloning is unnecessary. Normalization is determined by the business value-equivalence rule.

## 41. Legacy `java.util.Date` Is Mutable

If a record component is a Date, the input Date can be modified via setters such as `setTime`. The default accessor also returns the Date reference directly.

~~~java
record Event(java.util.Date when) {}
~~~

This is not an immutable snapshot.

There are two approaches:
1. **Prefer java.time**: use `Instant`, `LocalDate`, `LocalDateTime`, or `ZonedDateTime` depending on the domain; these types are immutable.
2. If you must keep Date for a legacy API, copy it in both the constructor and the accessor.

## 42. Runnable Program: Defensive Copying of Date

Create **`LegacyDateRecordDemo.java`**:

~~~java
import java.util.Date;
import java.util.Objects;

public class LegacyDateRecordDemo {
    record Event(Date when) {
        Event {
            when = new Date(
                    Objects.requireNonNull(when, "when").getTime());
        }

        @Override
        public Date when() {
            return new Date(when.getTime());
        }
    }

    public static void main(String[] args) {
        Date input = new Date(1000L);
        Event event = new Event(input);

        input.setTime(9000L);
        System.out.println("stored=" + event.when().getTime());

        Date output = event.when();
        output.setTime(5000L);
        System.out.println("after getter=" + event.when().getTime());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 LegacyDateRecordDemo.java
java LegacyDateRecordDemo
~~~

Stdout:

~~~text
stored=1000
after getter=1000
~~~

The example has control via the timestamp without depending on the default timezone when printing Date.toString. When possible, `record Event(Instant when)` is usually clearer and involves less copying.

## 43. Factory Methods Can Add Contracts but Do Not Replace the Canonical Constructor

A record can have static factories:

~~~java
record Tag(String value) {
    Tag {
        value = value.strip();
        if (value.isEmpty()) {
            throw new IllegalArgumentException("blank");
        }
    }

    static Tag fromUserInput(String raw) {
        return new Tag(raw);
    }
}
~~~

A factory helps name a use case, parse/convert inputs, or handle checked boundaries. However, if the canonical constructor remains public/package-accessible, callers can bypass **logic that resides only in the factory**.

**Principle:** Core invariants must be enforced in the canonical constructor, not only in an optional factory. Factories may add conversion steps, but they must not be the sole gate ensuring a valid object if the constructor is also exposed.

## 44. Runnable Program: Factory Normalizing Input Data

Create **`RecordFactoryDemo.java`**:

~~~java
import java.util.Locale;
import java.util.Objects;

public class RecordFactoryDemo {
    record CountryCode(String value) {
        CountryCode {
            value = Objects.requireNonNull(value, "value")
                    .strip()
                    .toUpperCase(Locale.ROOT);

            if (!value.matches("[A-Z]{2}")) {
                throw new IllegalArgumentException("country code");
            }
        }

        static CountryCode fromInput(String raw) {
            return new CountryCode(raw);
        }
    }

    public static void main(String[] args) {
        CountryCode code = CountryCode.fromInput(" vn ");
        System.out.println(code.value());

        try {
            new CountryCode("Vietnam");
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RecordFactoryDemo.java
java RecordFactoryDemo
~~~

Stdout:

~~~text
VN
invalid=country code
~~~

Whether callers use the factory or call the constructor directly, validation/normalization is still applied.

## 45. Secondary Constructors Must Delegate to the Canonical Constructor

A record can declare additional constructors with different signatures, but non-canonical constructors must begin with an **explicit constructor invocation** to the canonical constructor (usually via `this(...)`). Canonical validation cannot be bypassed.

~~~java
record Range(int start, int end) {
    Range {
        if (end < start) {
            throw new IllegalArgumentException("range");
        }
    }

    Range(int end) {
        this(0, end);
    }
}
~~~

Thanks to delegation, the invariants in the compact canonical constructor also remain in effect for the overload.

### Runnable Program

Create **`RecordConstructorDelegationDemo.java`**:

~~~java
public class RecordConstructorDelegationDemo {
    record Range(int start, int end) {
        Range {
            if (end < start) {
                throw new IllegalArgumentException("range");
            }
        }

        Range(int end) {
            this(0, end);
        }
    }

    public static void main(String[] args) {
        System.out.println(new Range(5));
        System.out.println(new Range(2, 7));

        try {
            new Range(-1);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RecordConstructorDelegationDemo.java
java RecordConstructorDelegationDemo
~~~

Stdout:

~~~text
Range[start=0, end=5]
Range[start=2, end=7]
invalid=range
~~~

`new Range(-1)` delegates `this(0,-1)`, and then the canonical invariant throws an exception.

## 46. Custom Accessors and the Record API Contract

A record auto-generates an accessor only if you do not define a method with the same signature yourself. You can override a component accessor:

~~~java
record Secret(byte[] payload) {
    Secret {
        payload = payload.clone();
    }

    @Override
    public byte[] payload() {
        return payload.clone();
    }
}
~~~

The accessor must have the **exact return type and signature** matching the record component contract and appropriate accessibility.

However, consider **semantic consistency**: the record data state used in equals/hashCode/toString is determined by the record components and the generation mechanism, and does not automatically apply transformations performed by a custom accessor.

An accessor returning a defensive copy should have *equivalent content value* each time; avoid accessors with unpredictable side effects or ones that produce a different logical value.

## 47. Records Do Not Allow Arbitrary Extra Instance Fields

A record only has instance fields from its declared components; you cannot add an instance field that is not a component to "keep a backup copy" while keeping the record declaration valid.

~~~java
record Person(String name) {
    // private final String normalizedName; // Error: extra instance field.
}
~~~

Records can have appropriate static fields, but static state does not replace per-instance immutable components.

If you need internal mutable caches, lazy state, locks, resource lifecycles, or a representation that does not match the components, an **ordinary class** may be more appropriate.

## 48. Record Invariants Must Hold with Component Accessors

A principle of record data-carrier design: reconstructing a record from its component accessors should yield a record that is equal under the contract to the original, for example:

~~~java
record Pair(int left, int right) {}

Pair p = new Pair(1, 2);
Pair copy = new Pair(p.left(), p.right());
System.out.println(p.equals(copy)); // true
~~~

When normalizing, the canonical constructor can put values into a canonical form, so this property still holds if the accessor returns the stored value.

With arrays and defensive copies, **default equality** by array identity can cause `new Blob(blob.bytes())` not to equal the original Blob. That is why you need to think carefully about content-based `equals/hashCode`.

### Avoid Accessors That Break the Contract

If an accessor increments a counter or returns varying data different from the component state, the record may no longer intuitively be a transparent carrier. If the logic requires stateful access, consider a regular class.

## 49. Runnable Program: Reconstruction Property After Normalization

Create **`RecordReconstructionDemo.java`**:

~~~java
import java.util.Locale;

public class RecordReconstructionDemo {
    record Code(String value) {
        Code {
            value = value.strip().toLowerCase(Locale.ROOT);
            if (value.isEmpty()) {
                throw new IllegalArgumentException("empty");
            }
        }
    }

    public static void main(String[] args) {
        Code first = new Code("  AbC ");
        Code rebuilt = new Code(first.value());

        System.out.println("first=" + first.value());
        System.out.println("rebuilt=" + rebuilt.value());
        System.out.println("equal=" + first.equals(rebuilt));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RecordReconstructionDemo.java
java RecordReconstructionDemo
~~~

Stdout:

~~~text
first=abc
rebuilt=abc
equal=true
~~~

Normalization should be **idempotent**: normalizing an already-normalized value does not change its logical state.

## 50. Mutable Objects with Custom `equals/hashCode` Can Also Be Dangerous

It is not only arrays: a component with custom mutable state and state-based equals/hashCode can cause the record's hash to change after construction.

~~~java
record Wrapper(MutablePrice price) {}
~~~

If MutablePrice's hashCode changes when amount changes, the Wrapper record's hashCode can also change. Even though the component field is final, the hash-based collection contract can be broken.

Options:
- replace the mutable component with an immutable value record;
- copy the state into an immutable domain representation;
- specify custom equals/hashCode only when genuinely needed, using stable values;
- avoid using a mutable-record wrapper as a Map key.

Defensive copying is a solution for **reference ownership**, whereas correct equality/hashing is a **value semantics** concern that is closely related yet not completely identical.

## 51. Correctness When the Input Collection Is Modified Concurrently

`List.copyOf(source)` reads the elements of source at the time of the call, but if another thread concurrently mutates a non-thread-safe mutable collection, the result may be inconsistent or throw an exception; `List.copyOf` is not an atomic transaction snapshot for arbitrary concurrent sources.

If you need a snapshot of shared concurrent state:
- establish synchronization/locking around the snapshot according to the ownership policy;
- or use data structures/publishing mechanisms with a clear consistency contract;
- or pass an immutable snapshot created by the producer;
- do not assume `copyOf` guarantees an atomic "instant" for every collection.

Which mechanism is appropriate depends on consistency requirements and concurrency design, not just record syntax.

## 52. Should Validation Check Content or Only Non-Null?

For example:

~~~java
record Catalog(java.util.List<String> codes) {
    Catalog {
        codes = java.util.List.copyOf(codes);
    }
}
~~~

`List.copyOf` checks for a null list and null elements, but does **not** check:
- blank strings;
- duplicate codes;
- maximum length;
- regex format;
- relationships between codes and other components.

If the domain requires them, add explicit checks, preferably validating once and then copying:

~~~java
for (String code : codes) {
    if (code.isBlank()) {
        throw new IllegalArgumentException("blank code");
    }
}
codes = List.copyOf(codes);
~~~

When concurrent modification is possible, it is better to copy the snapshot **first**, and then validate the stable snapshot if the input might be modified unexpectedly. The validation/copy order must ensure that checks apply to **the exact data being stored**.

## 53. Runnable Program: Validating a Snapshot Collection

Create **`RecordListValidationDemo.java`**:

~~~java
import java.util.List;
import java.util.Objects;

public class RecordListValidationDemo {
    record Catalog(List<String> codes) {
        Catalog {
            codes = List.copyOf(
                    Objects.requireNonNull(codes, "codes"));

            for (String code : codes) {
                if (code.isBlank()) {
                    throw new IllegalArgumentException("blank code");
                }
            }

            if (codes.isEmpty()) {
                throw new IllegalArgumentException("empty catalog");
            }
        }
    }

    public static void main(String[] args) {
        Catalog catalog = new Catalog(List.of("A", "B"));
        System.out.println("codes=" + catalog.codes());

        try {
            new Catalog(List.of("A", " "));
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RecordListValidationDemo.java
java RecordListValidationDemo
~~~

Stdout:

~~~text
codes=[A, B]
invalid=blank code
~~~

The code copies the structure first, then validates the exact snapshot that will be stored.

## 54. Duplicates and Canonicalization of Collections

If the domain treats the input collection as a *set of unique normalized tags*, a `List<String>` record can normalize by:
1. copying the source;
2. mapping strings to normalized tags;
3. rejecting blank/invalid values;
4. deduplicating according to the rule;
5. storing an unmodifiable List with a deterministic order.

However, deduplication can **silently lose information**; do not do it automatically without a domain requirement.

If preserving insertion order after removing duplicates, you can use a `LinkedHashSet` during normalization followed by `List.copyOf`; if you use `Set.copyOf`, there is no ordering guarantee.

## 55. Runnable Program: Normalized Unique Tags

Create **`RecordNormalizedTagsDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public class RecordNormalizedTagsDemo {
    record Tags(List<String> values) {
        Tags {
            Objects.requireNonNull(values, "values");
            LinkedHashSet<String> unique = new LinkedHashSet<>();

            for (String raw : values) {
                String tag = Objects.requireNonNull(raw, "tag")
                        .strip()
                        .toLowerCase(Locale.ROOT);

                if (tag.isEmpty()) {
                    throw new IllegalArgumentException("blank tag");
                }

                unique.add(tag);
            }

            values = List.copyOf(new ArrayList<>(unique));
        }
    }

    public static void main(String[] args) {
        Tags tags = new Tags(
                List.of(" Java ", "CORE", "java", "Core"));

        System.out.println(tags.values());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RecordNormalizedTagsDemo.java
java RecordNormalizedTagsDemo
~~~

Stdout:

~~~text
[java, core]
~~~

This domain policy treats tag names as case-insensitive and preserves first-seen order. For a case-sensitive domain, **do not** lowercase.

## 56. Records Receiving External Input: Parse at the Boundary, Validate in the Record

For example, a DTO from HTTP/CLI/config may arrive as Strings. It is good practice to separate:
- **Parsing**: `String` → `int`, `LocalDate`, `BigDecimal`;
- **Construction & invariant**: the record's canonical constructor protects the domain state;
- **Error reporting**: the boundary translates exceptions into user-appropriate messages.

~~~java
record Port(int number) {
    Port {
        if (number < 1 || number > 65535) {
            throw new IllegalArgumentException("port out of range");
        }
    }

    static Port parse(String raw) {
        return new Port(Integer.parseInt(raw.strip()));
    }
}
~~~

If raw is not a number, `NumberFormatException` comes from parsing; if it is a number out of range, IllegalArgumentException comes from the domain constructor. The two stages serve different purposes.

## 57. Runnable Program: Separating Parsing and Validation

Create **`RecordParsingDemo.java`**:

~~~java
public class RecordParsingDemo {
    record Port(int number) {
        Port {
            if (number < 1 || number > 65535) {
                throw new IllegalArgumentException("port out of range");
            }
        }

        static Port parse(String raw) {
            return new Port(Integer.parseInt(raw.strip()));
        }
    }

    public static void main(String[] args) {
        System.out.println("valid=" + Port.parse(" 8080 ").number());

        try {
            Port.parse("70000");
        } catch (IllegalArgumentException ex) {
            System.out.println("domain=" + ex.getMessage());
        }

        try {
            Port.parse("invalid");
        } catch (NumberFormatException ex) {
            System.out.println("parse rejected");
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RecordParsingDemo.java
java RecordParsingDemo
~~~

Stdout:

~~~text
valid=8080
domain=port out of range
parse rejected
~~~

`NumberFormatException` extends IllegalArgumentException, so place a separate catch for NumberFormatException in the appropriate scope if you need to distinguish it within the exception hierarchy.

## 58. Records and Validation Annotations

Java frameworks may support Jakarta Bean Validation annotations (`@NotNull`, `@Size`, etc.) on record components/constructor parameters/accessors, yet **an annotation by itself does not guarantee that the constructor is validated on every `new Record(...)`**. An appropriate framework/invocation mechanism is required.

If an invariant must hold for **every caller**, writing checks inside the canonical constructor is the clear, framework-independent approach.

Validation annotations can be useful at a DTO boundary for error aggregation, while a core domain record still needs a contract that the code actually enforces.

## 59. When Should You Not Use a Record?

A record is a great fit when the state consists solely of a set of components with value-oriented semantics. Consider a regular class when:

- The object has identity/lifecycle rather than value semantics.
- Complex mutable internal state or lazy caches are required.
- A resource handle (socket/thread/session) with a special ownership/close lifecycle needs to be held.
- An arbitrary superclass is required.
- Multiple constructors are needed whose representations do not fit canonical components.
- Encapsulation must completely hide the representation without exposing component accessors.
- Defensive-copy logic becomes overly complex or the performance contract differs too much from record semantics.

A record with an array component and a deep equality override is still valid; however, if too much custom logic is required, an immutable class with clear naming and API design may be easier to maintain.

## 60. Common Anti-Patterns

| Anti-pattern | Consequence | Correct Approach |
| --- | --- | --- |
| Assuming records auto-validate inputs | null/negative/blank values slip through | Canonical validation |
| Thinking a `final` field makes a List immutable | Caller mutates the List | `List.copyOf`/snapshot |
| Wrapping a mutable List directly with `unmodifiableList` | Source still mutates the underlying collection | Copy before wrapping |
| Using `List.copyOf` and claiming it is a deep copy | Mutable elements still change | Immutable elements/deep snapshot |
| Cloning an array only in the constructor | Getter exposes internal array | Override accessor to clone |
| Cloning in the getter but forgetting the constructor | Input alias mutates record | Clone in both directions |
| Cloning arrays while relying on default equals for content | Same bytes yet unequal | Override equals/hashCode for value semantics |
| Using `getClass()==Record.class` assuming nested subclassing | Wrong abstraction | Rely on record type/contract |
| Assigning `this.component=...` in a compact constructor | Compile error | Assign the parameter |
| Validating only in a static factory | Direct constructor bypass | Validate in the canonical constructor |
| Using `assert` for validation | Assertions can be disabled | Throw an exception normally |
| Lowercasing/stripping every string | Alters domain meaning | Explicit policy |
| Using default locale for identifiers | Environment-dependent behavior | Use Locale.ROOT for technical identifiers |
| Not distinguishing input normalization from validation | Wrong acceptance/rejection | Specify a clear contract |
| Using a mutable record key in a HashMap | Hash/equality shifts | Immutable snapshot |
| Using `Stream.toList` and assuming nulls are forbidden | Null may slip through | Validation/List.copyOf if required |
| Using `Set.copyOf` and expecting preserved order | No ordering guarantee | List/ordered snapshot contract |
| Using mutable Date directly | External mutation | Instant or copy in constructor+accessor |
| Snapshotting a concurrently modified source without locking | Inconsistent data | Synchronization/immutable snapshot |
| Complex parsing/IO in the canonical constructor | Coupling, side effects | Separate factory/boundary |

## 61. Exercise 1 — Can a Compact Constructor Be Written Like This?

~~~java
record Username(String text) {
    Username {
        // this.text = text.strip();
    }
}
~~~

**Answer:** No, if you uncomment the assignment to the component field `this.text` in the compact constructor. Write `text = text.strip();` and the compiler assigns the field automatically after the body.

## 62. Exercise 2 — Null Policy

~~~java
record Name(String value) {
    Name {
        value = java.util.Objects.requireNonNull(value, "value").strip();
        if (value.isEmpty()) {
            throw new IllegalArgumentException("empty");
        }
    }
}
~~~

**Answer:** Input null → NullPointerException("value"); input `"   "` → IllegalArgumentException("empty"); input `" A "` → stores `"A"`.

## 63. Exercise 3 — Is List.copyOf Deep?

Given input `List<MutableItem>`, the record constructor uses `List.copyOf`. Afterward, the caller modifies a field on a MutableItem referenced from the list.

**Answer:** The record can still observe the updated item because `List.copyOf` only copies a snapshot of the list structure, not a deep copy of its elements. Immutable elements or mapping each element to an immutable snapshot is needed.

## 64. Exercise 4 — Two-Way Array Protection

Record Blob copies the array in its constructor but leaves the default `bytes()` accessor.

**Answer:** A caller can call `blob.bytes()[0]=99` and modify the internal array. Override the accessor to return a clone.

## 65. Exercise 5 — Arrays and Equality

Two `Blob(byte[] bytes)` records each hold new byte[] {1,2}. Is the generated equals guaranteed to be true?

**Answer:** No, array components are compared by reference identity by default, not by content. To get content equality, override equals/hashCode using the appropriate Arrays methods.

## 66. Exercise 6 — List Live View

~~~java
List<String> source = new ArrayList<>();
List<String> view = Collections.unmodifiableList(source);
source.add("A");
~~~

**Answer:** `view` will see A because an unmodifiable wrapper does not snapshot the source. `List.copyOf(source)` or `unmodifiableList(new ArrayList<>(source))` snapshots the structure at the time of copying.

## 67. Exercise 7 — String Normalization

Two Username instances are created from `"  AbC  "` and `"abc"`. The compact constructor uses strip and toLowerCase(Locale.ROOT). How do the two records compare with equals?

**Answer:** True if all other components are equal. Both store canonical `"abc"`; the generated String component equality reflects the normalized value.

## 68. Exercise 8 — Map.copyOf

Can you store a `Map<String,MutableValue>` using Map.copyOf and call the object deeply immutable?

**Answer:** No. The Map entries structure is unmodifiable, but the MutableValue objects are still shared; the values must be snapshotted if deep immutability is required.

## 69. Exercise 9 — Record Key in a HashMap

Record Key contains an uncopied mutable List. After inserting the key, the caller adds an element to the List. What is the risk?

**Answer:** Key.hashCode can change, and HashMap lookups will no longer be reliable. Copy into an immutable list in the constructor and ensure the elements themselves are immutable.

## 70. Exercise 10 — Date or Instant?

An event timestamp does not need to be mutated and must store a snapshot.

**Answer:** Prefer the immutable java.time.Instant. If a legacy API mandates java.util.Date, copy the Date in the constructor and on every accessor call; do not rely solely on a final Date field.

## 71. Exercise 11 — Auxiliary Constructor

Record Range has a canonical constructor that validates start <= end. Is the overloaded constructor `Range(int end)` allowed to assign fields directly instead of delegating?

**Answer:** No; a non-canonical constructor must delegate using an appropriate `this(...)` call to a constructor of the record, ultimately going through canonical initialization. For example, `Range(int end) { this(0,end); }`.

## 72. Exercise 12 — Choosing Record or Class

An object needs a mutable internal cache, a close lifecycle, and resource ownership, with many invariants not represented by transparent components.

**Answer:** Consider an ordinary class with explicit private state, constructors, methods, and a close policy. A record should only be used if value-carrier semantics genuinely fit.

## 73. Workflow for Designing a Safe Record

**Step 1 — List components.** Classify each component as a primitive, immutable object, mutable collection/array, or nested object graph.

**Step 2 — Write invariants.** Null, blank, range, cross-field constraints, uniqueness, and length.

**Step 3 — Define normalization.** Trim/strip, case, Unicode, BigDecimal scale, ordering/dedup — only when required by the domain.

**Step 4 — Choose the canonical constructor.** Compact for validation/parameter reassignment; explicit if there is a clear reason.

**Step 5 — Store a snapshot.** List/Set/Map copyOf with null/order policy; clone arrays; deep-copy elements if mutable.

**Step 6 — Check accessors.** Array/Date require a defensive copy when returned; an unmodifiable List of immutable elements generally does not need re-copying in the getter.

**Step 7 — Check generated equals/hashCode/toString.** Array content equality requires custom methods if value semantics are desired. Avoid exposing credentials via toString.

**Step 8 — Check additional constructors/factories.** Do not allow bypassing invariants.

**Step 9 — Write negative tests.** Null, blank, out-of-range, duplicate, invalid formats.

**Step 10 — Write aliasing tests.** Mutate input after construction, mutate getter output, mutate nested element references.

**Step 11 — Write equality/hash tests.** Equivalent normalized inputs, HashMap lookup, reconstruction property.

**Step 12 — Review concurrency/ownership.** Is the input shared with other threads? Is there lifecycle/resource state?

## 74. End-of-Lesson Checklist

- [ ] I know that a record auto-generates components but does not auto-validate.
- [ ] I distinguish between validation and normalization.
- [ ] I know that a compact constructor uses parameter names and implicit assignments.
- [ ] I do not assign directly to `this.component` inside a compact constructor.
- [ ] I know that an explicit canonical constructor must assign component fields.
- [ ] I validate null/blank/range and cross-component invariants.
- [ ] I know that normalization must be based on domain rules.
- [ ] I use Locale.ROOT appropriately for technical identifiers.
- [ ] I distinguish between null exceptions and invalid-domain exceptions.
- [ ] I do not use assert in place of real validation.
- [ ] I use List.copyOf to snapshot a list structure.
- [ ] I know that List.copyOf forbids null elements.
- [ ] I know that List.copyOf can reuse an unmodifiable input list.
- [ ] I distinguish between an unmodifiable view and a copied snapshot.
- [ ] I know that Set.copyOf/Map.copyOf do not guarantee insertion order.
- [ ] I distinguish between shallow copy and deep copy.
- [ ] I snapshot mutable elements when deep immutability is needed.
- [ ] I know that a nested record can still contain mutable data.
- [ ] I clone arrays in both the constructor and the accessor.
- [ ] I know that the default equals for an array component is not element-wise.
- [ ] I override equals/hashCode consistently for byte[] value semantics.
- [ ] I do not use a mutable record key in a HashMap.
- [ ] I prefer immutable java.time types when appropriate.
- [ ] I defensively copy legacy Date if it must be used.
- [ ] I know that BigDecimal equals depends on scale.
- [ ] I understand that a factory does not replace canonical validation.
- [ ] I know that an auxiliary constructor must delegate.
- [ ] I verify the reconstruction property with normalized inputs.
- [ ] I know that concurrent mutation requires a synchronization policy.
- [ ] I test aliasing for both input and accessor output.
- [ ] I do not expose secrets in record toString when confidentiality is required.
- [ ] I know when an ordinary class is more suitable than a record.

**Conclusion:** Records in Java 17 only provide **a value-carrier structure and operations generated from components**; correctness and deep immutability remain a design responsibility. **Validate and normalize in the canonical constructor**, use **List.copyOf/Map.copyOf** for immutable structural snapshots, **deep-copy mutable elements when needed**, and **clone arrays in both the constructor and the accessor**. Then verify `equals/hashCode/toString`, especially with arrays and mutable components, so that the record truly satisfies value semantics and is safe when used as a key or shared across parts of the program.
