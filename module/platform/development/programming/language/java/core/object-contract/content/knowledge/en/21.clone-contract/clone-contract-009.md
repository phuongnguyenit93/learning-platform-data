# Overriding `clone()` as `public` and using a specific return type in Java

## 1. Context: `Object.clone()` is not a public copying API

Every Java class inherits from `java.lang.Object`. `Object` declares the method:

```java
protected native Object clone() throws CloneNotSupportedException;
```

This is an **illustrative API signature**, not a method learners need to define themselves. There are three important characteristics:

- **`protected`**: `Object`'s `clone()` method cannot be arbitrarily called from anywhere. External application code cannot write `someObject.clone()` merely because a variable has type `Object`.
- **Return type `Object`**: in the original signature, using the result as a concrete type requires a cast. Java allows overriding with a **covariant return type** to avoid casting on the caller side.
- **`throws CloneNotSupportedException`**: `Object.clone()`'s implementation checks whether the actual object implements the `Cloneable` marker interface; if not, the call may throw this checked exception.

This lesson focuses on how a class **explicitly exposes cloning capability**, typically via `implements Cloneable`, `public T clone()`, calling `super.clone()`, and handling mutable reference fields when necessary.

Note: `Cloneable` is only a **marker interface** and does not declare a `clone()` method. Writing `implements Cloneable` does not automatically make `clone()` `public`. This is a limitation of Java's traditional clone API design; for new code, a copy constructor or static factory is usually an easier-to-control option.

## 2. From `protected Object clone()` to `public T clone()`

A common pattern:

```java
public class Point implements Cloneable {
    private final int x;
    private final int y;

    public Point(int x, int y) {
        this.x = x;
        this.y = y;
    }

    @Override
    public Point clone() {
        try {
            return (Point) super.clone();
        } catch (CloneNotSupportedException e) {
            throw new AssertionError(e);
        }
    }
}
```

This is a compilable class in file `Point.java` on Java 17+. The decisions have clear meaning:

1. **`implements Cloneable`** marks the object as copyable by `Object.clone()` under the standard mechanism.
2. **`@Override`** checks the exact signature of the overridden method; helps catch wrong names/parameters.
3. **`public`** widens the access level of the inherited `protected` method. Java allows widening access permissions when overriding; it does **not** allow narrowing from `protected` to `private` or default package-private.
4. **`Point` as the return type** instead of `Object`. Since `Point` is a subtype of `Object`, this is a valid *covariant return type*. Callers can write `Point copy = original.clone();` without needing a cast.
5. **`super.clone()`** performs a shallow copy of the object. It returns `Object` per the original signature, so inside the method body casting `(Point)` is still required; it removes the cast **at the caller**, not necessarily **inside the implementation**.
6. **The `catch` block** turns an exception expected never to occur into `AssertionError`, because the class directly implements `Cloneable`. One can choose to declare `throws CloneNotSupportedException` instead of catching, though then API callers must handle the exception.

For `Point` containing only two `int`s, shallow copying is already enough: each copy holds its own copy of the primitive values.

### Why is changing the return type valid?

Java supports overriding a method returning a reference type with a method returning a subtype. `Object.clone()` returns `Object`, while `Point.clone()` returns `Point`, so it is valid. Similarly, if `Report extends Document`, `Report.clone()` can return `Report` when `Document.clone()` returns `Document`. This mechanism is called **covariant return type**.

You cannot arbitrarily replace the return type with an unrelated type, such as from `Object` to `int`. And covariant return only applies under proper override rules; it is not a way to create a separate overload.

### Where must `public` be used?

When the API needs external code to call `clone()`, put `public` on **the overriding method**. If a class only `implements Cloneable` without writing a public method, code outside the class cannot normally call `clone()` through a reference of that class's type, because only the `protected` version inherited from `Object` remains.

`Cloneable` is also **not** a type on which `clone()` can be called directly: a variable of type `Cloneable` has no `clone` method in the interface. The class itself must expose the method publicly; or the application should provide a copying API with a clearer name and contract.

## 3. `Cloneable` rules and exceptions

Default `Object.clone()` checks the `Cloneable` marker on the runtime type, then creates a new object with the same runtime type and copies fields. Without the marker, it throws `CloneNotSupportedException`.

Two exception handling options in an override:

**Option A — keep the checked exception in the API:**

```java
@Override
public Point clone() throws CloneNotSupportedException {
    return (Point) super.clone();
}
```

This is an **illustrative code snippet** placed inside a class `Point implements Cloneable`. Callers must catch or declare `CloneNotSupportedException`. An override may preserve the checked exception per `Object.clone()`'s contract.

**Option B — hide the checked exception because the class guarantees Cloneable:**

```java
@Override
public Point clone() {
    try {
        return (Point) super.clone();
    } catch (CloneNotSupportedException e) {
        throw new AssertionError("Unexpected clone failure", e);
    }
}
```

This is also a **code snippet inside a class**, not yet a standalone program. Because the class in question already implements `Cloneable`, the `catch` block is usually a way to reflect an abnormal programming error, rather than forcing callers to handle a checked exception not expected to occur under the standard `Object.clone()` mechanism.

Whichever option is chosen, **do not swallow the exception and return `null`**: otherwise subsequent calls may encounter `NullPointerException` far from the real cause, and callers cannot rely on the copy-returning contract.

## 4. Shallow copy: what does `super.clone()` copy?

Standard `Object.clone()` creates a **new object of the same runtime type** and copies field values:

- For `int`, `boolean`, `double`, and other primitives: the value is copied.
- For reference fields like `String`, `List`, arrays, or custom objects: **the reference is copied**, without automatically duplicating the object that reference points to.
- If the reference points to an **immutable** object like `String`, sharing the object is usually safe.
- If the reference points to a **mutable** object like `int[]` or `ArrayList`, the clone and the original can observe each other's changes through the shared reference.

`super.clone()` does not automatically call the public constructor of the cloned class like a normal `new T(...)` statement; therefore you cannot rely on constructor logic to recreate or re-copy mutable components automatically. All invariants and constraints on post-clone state must be examined in the override.

For example, if a class has an `int[] scores` field and only calls `super.clone()`, both the original and the copy initially hold references to **one array**. To allow both objects to edit the array independently, after cloning, an array copy must be created:

```java
@Override
public Report clone() {
    Report copy = (Report) super.clone();
    copy.scores = scores.clone();
    return copy;
}
```

This snippet assumes class `Report` has a non-final `int[] scores` field and `super.clone()` calls a valid override returning a runtime `Report` object. If `scores` can be null, the null case must be handled. For arrays of mutable objects, `scores.clone()` (when it is a reference array) **only duplicates the array**, still sharing elements; to deep copy, you must specify how to copy each element.

**Specifically:** a `final` reference field cannot be reassigned after `super.clone()` from inside a normal clone. If deep cloning is needed for objects with mutable `final` fields, a copy constructor or factory is usually more natural than `Object.clone()`.

## 5. Java 17: runnable program with superclass and subclass

The following example illustrates simultaneously: public clone, concrete return type, covariant return in a subclass, and duplicating a mutable array yourself. Create file `PublicCloneDemo.java`:

```java
import java.util.Arrays;

public class PublicCloneDemo {
    static class Document implements Cloneable {
        private final String title;

        Document(String title) {
            this.title = title;
        }

        @Override
        public Document clone() {
            try {
                return (Document) super.clone();
            } catch (CloneNotSupportedException e) {
                throw new AssertionError(e);
            }
        }

        public String title() {
            return title;
        }
    }

    static final class Report extends Document {
        private int[] scores;

        Report(String title, int[] scores) {
            super(title);
            this.scores = scores.clone();
        }

        @Override
        public Report clone() {
            Report copy = (Report) super.clone();
            copy.scores = scores.clone();
            return copy;
        }

        public void setFirstScore(int score) {
            scores[0] = score;
        }

        public int firstScore() {
            return scores[0];
        }

        public int[] scoresSnapshot() {
            return scores.clone();
        }
    }

    public static void main(String[] args) {
        Document source = new Document("Guide");
        Document clonedDocument = source.clone();

        System.out.println("document different reference: "
                + (source != clonedDocument));
        System.out.println("document title: " + clonedDocument.title());

        Report report = new Report("Metrics", new int[] {2, 4});
        Report clonedReport = report.clone();

        System.out.println("report different reference: "
                + (report != clonedReport));
        System.out.println("same runtime type: "
                + (report.getClass() == clonedReport.getClass()));
        System.out.println("before: "
                + report.firstScore() + "/" + clonedReport.firstScore());

        report.setFirstScore(9);
        System.out.println("after: "
                + report.firstScore() + "/" + clonedReport.firstScore());
        System.out.println("copy scores: "
                + Arrays.toString(clonedReport.scoresSnapshot()));
    }
}
```

Compile and run:

```bash
javac --release 17 PublicCloneDemo.java
java PublicCloneDemo
```

Expected output:

```text
document different reference: true
document title: Guide
report different reference: true
same runtime type: true
before: 2/2
after: 9/2
copy scores: [2, 4]
```

Explanation:

1. `Document implements Cloneable` and exposes `public Document clone()`. Callers directly assign `Document clonedDocument = source.clone();`, with no cast needed.
2. `Report` inherits `Document`'s clone policy. `Report.clone()` overrides and **narrows the return type** from `Document` to `Report`, so `Report clonedReport = report.clone();` is valid.
3. Inside `Document.clone()`, `Object.clone()` creates an object **of the same runtime type** as the receiver. When the receiver is `Report`, the created object is still `Report`. Therefore the cast `(Report) super.clone()` inside `Report.clone()` is valid under this structure.
4. The `title` data is an immutable `String` so sharing its reference is safe for the example. Conversely, `scores` is a mutable array; `Report.clone()` creates a separate array via `scores.clone()`.
5. After changing the original's first score to `9`, the copy still keeps `2`. This is proof that copying is independent at **the `int[]` array level**, not an assertion that `Object.clone()` always performs a deep copy.

If the line `copy.scores = scores.clone();` is removed, the first element of the array in both objects would change together because both point to the old array. If the array contains mutable objects, cloning the array still does not deep-copy each inner object.

## 6. Covariant return type and the role of inheritance

Consider the hierarchy:

```text
Object.clone(): Object
    ↓ override
Document.clone(): Document
    ↓ override
Report.clone(): Report
```

Each override level is permitted to return a subtype of the parent level's type. This is a Java language rule, not an ad-hoc runtime cast. All methods are named `clone`, take no parameters, and override one another; `@Override` helps the compiler check this.

This improves the API user experience:

```java
Report report = new Report("Metrics", new int[] {2, 4});
Report copied = report.clone(); // No (Report) cast needed
```

This code snippet assumes the classes from `PublicCloneDemo` above. If a variable is declared with static type `Document`:

```java
Document baseView = report;
Document copiedThroughBase = baseView.clone();
```

The expression `baseView.clone()` has a **compile-time return type** of `Document` due to the signature on `Document`; at runtime Java still dispatches to the `Report.clone()` override. To have a variable of type `Report` without casting, you must hold a reference with static type `Report` or design a factory/API with appropriate typing. Covariant return does not make the compiler infer a subtype from the runtime object when the static type is broader.

At the bytecode level, the compiler may generate a **bridge method** to preserve override behavior and compatibility for calls through the parent type. That is an implementation detail and does not change the Java code-writing rules above.

## 7. Protecting the clone contract with inheritable classes

For a **non-final** class, clone design must account for subclasses. An override calling `super.clone()` normally creates an object of the actual runtime class, even if the code resides in the superclass. A subclass with new mutable state should override `clone()` itself to finish copying; otherwise, copies of the subclass may share mutable objects with the original.

With a `final` class, you do not have to deal with future subclasses and can determine the exact set of fields needing copying. With an inheritable class, document the contract clearly: whether subclasses are permitted to override, what they must do with mutable fields, and whether special state must be preserved.

Do not claim `Cloneable` means every clone is a **deep copy**. `Cloneable` only signals capability to perform copying via `Object.clone()`; the class itself is responsible for the copying semantics of the data it manages.

Some principles for a public clone API:

- **Do not return `this`** if the contract expects a new instance; for ordinary mutable objects, two variables pointing to the same object is not a copy.
- **Constructor is not called automatically**: check invariants if normal state is established by constructors, validation, or cross-field relationships.
- **Keep related fields consistent**: a clone may need to re-initialize caches, locks, system handles, or resource IDs instead of sharing them directly.
- **State explicitly how shallow or deep the copy is**: "deep copy" must be defined per specific data structure, not merely by relying on calling `clone()` multiple times.
- **Avoid cloning objects owning external JVM resources** without an explicit copying policy; sockets, file descriptors, transactions, threads, and resource handles cannot by default be duplicated safely.

## 8. How `clone()` differs from copy constructors and factories

Java does not require every object to support clone. A simpler option is a copy constructor or a clearly named static method:

```java
public final class Settings {
    private final String name;
    private final java.util.List<String> tags;

    public Settings(String name, java.util.List<String> tags) {
        this.name = java.util.Objects.requireNonNull(name);
        this.tags = java.util.List.copyOf(tags);
    }

    public Settings(Settings original) {
        this(original.name, original.tags);
    }

    public static Settings copyOf(Settings original) {
        return new Settings(original);
    }
}
```

This is a valid `Settings.java` class in Java 17. A copy using a constructor can keep `final` fields, validate inputs, and copy an immutable list from the start. With `List<String>` (and immutable strings), the model is safer than using `Object.clone()` and then having to reassign `final` fields.

| Option | Characteristics | Best suited for |
| --- | --- | --- |
| `public T clone()` + `Cloneable` | Leverages `Object.clone()`; concrete return type; must manage shallow/deep copy and checked exception | Legacy APIs or types with an existing clear clone convention |
| Copy constructor `new T(original)` | Invokes constructor, allows invariant checks and copying under a defined policy | Value objects or objects managing `final` fields |
| Static factory `T.copyOf(source)` | API name expresses intent, can reuse immutable objects if contract permits | New application APIs, immutable types |

For records or immutable objects, sometimes **no new copy is needed**: the same instance can be shared safely if only holding values is required. If the API requires distinct object identity, that requirement must be stated explicitly.

## 9. Common mistakes

### Only writing `implements Cloneable` without overriding `clone()`

The marker does not add a `public clone()` to the class. Because `Object.clone()` is `protected`, external users still cannot call `obj.clone()` through a normal public API. To support the feature, expose the method with an appropriate access level.

### Overriding yet continuing to return `Object`

`public Object clone()` is a valid override by type, yet forces callers to cast to the target type. When a class returns its own subtype, declaring `public T clone()` is usually friendlier and offers better type checking.

### Forgetting `Cloneable`

Calling `super.clone()` in a class not implementing `Cloneable` normally leads to `CloneNotSupportedException` at runtime. Understand that clone is an opt-in contract; you cannot just raise access visibility and expect the copying mechanism to work automatically.

### Failing to handle `CloneNotSupportedException`

If calling `super.clone()` directly, developers must catch or declare the checked exception per Java rules. For classes implementing `Cloneable`, the pattern of catching and turning into `AssertionError` is commonly used when the exception is considered abnormal.

### Thinking `super.clone()` is a deep copy

A shallow copy shares field references with the original object. With lists, arrays, maps, or mutable-state objects, the two copies can affect each other. Copy further according to the goal, or use a constructor/factory.

### Ignoring subclasses

A superclass's public `clone()` may copy parent fields properly yet leave mutable fields added by subclasses shared. Therefore subclasses usually must override and return the subclass type, additionally copying state they own.

### Cloning classes with special invariants or resources

`Object.clone()` does not re-run the cloned class's constructor to re-establish all conditions. For objects with resources, handles, state-dependent caches, or multi-field relationships, a shallow clone may be invalid. Define a specific copy policy or avoid the clone mechanism for that type.

## 10. Checklist when implementing `public T clone()`

1. Determine **why** the object needs cloning: must it create an object with a different reference, keep the same values, or require two independent states?
2. If using `Object.clone()`, verify the class belongs to a branch implementing `Cloneable`.
3. Override with **`@Override public T clone()`** and ensure `T` is a valid covariant return type.
4. Call `super.clone()` and handle `CloneNotSupportedException`, or declare the checked exception in the API if appropriate.
5. Inspect primitive, immutable, and mutable fields: which mutable fields require separate allocation copying?
6. For arrays of mutable objects or nested collections, inspect **elements** too, without stopping at `array.clone()` or `new ArrayList<>(list)`.
7. For subclasses, consider `super.clone()` and additionally copy private fields; check the actual runtime type of the clone.
8. Test `original != clone`, compare initial data, and mutate mutable state on one side to verify independence.
9. If the class contains `final` fields, complex invariants, or external resources, evaluate a copy constructor/static factory first.
10. Document clone behavior clearly in API docs; do not infer from the `Cloneable` marker that clone is necessarily deep or safe.

**Conclusion:** To let callers of a class invoke `clone()` directly and receive the exact type, typically write `public T clone()` to override `Object.clone()` with **wider access** and a **covariant return type**. When using the `super.clone()` mechanism, `Cloneable` is needed, exceptions must be handled, and understand by default this is a **shallow copy**. Deep copying or preserving object invariants is a separate responsibility of class design, not an automatic outcome of `public` or covariant return.