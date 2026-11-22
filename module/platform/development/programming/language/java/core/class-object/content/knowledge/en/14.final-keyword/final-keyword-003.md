# `final` Fields Without a Value and Where Assignment Is Allowed in Java

The `final` keyword has a special meaning when applied to a **field** of a class: once the field is validly assigned during initialization, an ordinary Java program **cannot reassign that field**. However, not every `final` field needs to receive a value right on its declaration line. Java allows declaring a `final` field **without an initializer expression**, commonly called a **blank final field**.

Example:

~~~java
final class Book {
    private final String isbn;

    Book(String isbn) {
        this.isbn = isbn;
    }

    String isbn() {
        return isbn;
    }
}
~~~

`isbn` does not have a value specified on the declaration line, but the constructor assigns it during the creation of each `Book` object. After the object is successfully created, no setter is allowed to reassign `isbn` under the assignment rules of `final`.

This lesson belongs to Java Core — **class-object**, the **final keyword** section, focusing on practical questions: what a *blank final* is; how instance fields differ from `static` fields; how assignment is allowed in initializers, constructors, and static initializers; how the compiler checks every branch; and what mistakes to avoid when designing immutable objects. Standalone examples use **Java 17+**.

## 1. What does `final` on a field guarantee?

A field can be declared as follows:

~~~java
private final int maxItems = 20;
private final String code;
private static final String APP_NAME = "Library";
private static final int DEFAULT_PORT;
~~~

These are **illustrative declarations** belonging to a class, not yet a standalone program. They fall into two groups:

| Declaration | Field type | Has initializer on declaration line? |
| --- | --- | --- |
| `final int maxItems = 20` | Instance field | Yes |
| `final String code;` | **Blank final instance field** | No |
| `static final String APP_NAME = "Library"` | Static field | Yes |
| `static final int DEFAULT_PORT;` | **Blank final static field** | No |

Once a `final` field is assigned in a way allowed by Java, ordinary Java code cannot subsequently assign another value to **the field itself**. This is a restriction on **field assignment**, not a guarantee that every object referenced by the field is immutable.

For example, `final List<String> names` keeps the **field reference** fixed after initialization, but an `ArrayList` referenced by the field can still have `add`, `remove`, or `clear` called on it if the API and ownership allow it.

**Do not equate `final` with `const` in every other language.** In Java, a `final` field can receive a value determined only at runtime, such as an order code validated and stored by a constructor. It is not necessarily a **compile-time constant**.

## 2. What is a blank final?

A **blank final field** is a field that has the `final` modifier but **no initializer directly in its declaration**.

~~~java
class Profile {
    private final String username; // Blank final instance field.

    Profile(String username) {
        this.username = username;
    }
}
~~~

Unlike:

~~~java
class FixedProfile {
    private final String username = "guest";
}
~~~

In `FixedProfile`, the field already has an initializer; this is **not** a blank final field. In `Profile`, each `new Profile(value)` call supplies a different value when constructing the object.

A very important point: **“blank” does not mean the field's memory has no value at all at every point in time.** Before initializers and constructors run, the storage for an instance field is default-initialized according to Java semantics (for example, `null` for references, `0` for `int`). However, **the compiler requires** blank final fields to be **definitely assigned** before the relevant initialization path completes normally. That default value must not be treated as a valid way to skip the required assignment.

A class with a blank final field is often appropriate when:

- Each object needs its own code or parameter, passed via the constructor.
- The object has an invariant that must be checked before accepting the final value.
- There are multiple overloaded constructors, and all of them must fully set the immutable field.
- A static value can only be computed when class initialization runs rather than being declared with a simple expression.

## 3. Where assignment is allowed: quick map

| Field | Where it can be assigned for the first time | Where is assignment not allowed? |
| --- | --- | --- |
| Blank final **instance** | Instance initializer block or constructor of **the class declaring the field** | Ordinary instance methods, setters, subclass constructors, lambdas executed later |
| Blank final **static** | Static initializer block of **the class declaring the field** | Constructors, instance initializers, ordinary static methods, instance methods |
| Final field **with an initializer** | Already assigned in the declaration expression | Cannot be assigned again in a constructor/static initializer |
| `final` local variable | According to definite assignment rules for local variables | Not the same location rules as a blank final **field** |

Distinguish between two layers of rules:

1. **Valid location:** where the rules of the language allow the assignment to take place.
2. **Definite assignment (DA) / definite unassignment (DU):** the compiler proves that the field **has been assigned before completion**, and **has never been assigned along the current path prior to the new assignment**.

Simply placing an assignment statement inside a constructor does not automatically make it valid. If another constructor fails to assign it, an `if` branch is missed, or the field has already been assigned in an earlier initializer, the program may still fail to compile.

## 4. Complete example: blank final instance field via constructor

Create the file **`BlankFinalInstanceDemo.java`**:

~~~java
import java.util.Objects;

final class Ticket {
    private final String code;
    private final int priority;

    Ticket(String code) {
        this(code, 1);
    }

    Ticket(String code, int priority) {
        Objects.requireNonNull(code, "code");
        if (code.isBlank()) {
            throw new IllegalArgumentException("code rỗng");
        }
        if (priority < 1 || priority > 5) {
            throw new IllegalArgumentException("priority ngoài 1..5");
        }

        this.code = code.strip();
        this.priority = priority;
    }

    String label() {
        return code + "/" + priority;
    }
}

public class BlankFinalInstanceDemo {
    public static void main(String[] args) {
        Ticket first = new Ticket("  AB-01  ");
        Ticket second = new Ticket("CD-02", 3);

        System.out.println("first=" + first.label());
        System.out.println("second=" + second.label());

        try {
            new Ticket(" ", 2);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected=" + ex.getMessage());
        }

        System.out.println("still=" + first.label());
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac -encoding UTF-8 BlankFinalInstanceDemo.java
java BlankFinalInstanceDemo
~~~

**Exact stdout:**

~~~text
first=AB-01/1
second=CD-02/3
rejected=code rỗng
still=AB-01/1
~~~

### Why is the program valid?

- `Ticket.code` and `Ticket.priority` are both **blank final instance fields**.
- The two-parameter constructor validates the data, then **assigns each field exactly once on the successful initialization path**.
- The one-parameter constructor calls `this(code, 1)` to delegate initialization. It **does not reassign** the two fields after the target constructor completes.
- When `code` consists only of whitespace, the constructor throws `IllegalArgumentException` before returning an object. No `Ticket` object is successfully created for the caller from that call.
- The objects `first` and `second` have their own `final` field values, because `final` does not mean every instance must have the same value.

**Different values across objects are completely valid.** `final` protects against reassigning a field **on an object itself**, not turning it into a static field shared across all objects.

## 5. Constructor chaining with `this(...)`

If there are multiple constructors, one way to centralize initialization is to use `this(...)` to delegate to **a single target constructor** that assigns the blank final fields:

~~~java
final class ConnectionConfig {
    private final String host;
    private final int port;

    ConnectionConfig() { this("localhost", 8080); }
    ConnectionConfig(String host) { this(host, 8080); }

    ConnectionConfig(String host, int port) {
        if (host == null || host.isBlank() || port < 1 || port > 65535)
            throw new IllegalArgumentException("config");
        this.host = host;
        this.port = port;
    }
}
~~~

`this(...)` must be in a valid Java 17 constructor invocation position, must not form a cycle, and the delegating constructor must not reassign the target constructor's fields. The focus of this lesson is **where assignment is allowed to occur**; proving definite assignment for each constructor path, return/throw branch, and control-flow table is explained in full in lesson B144.

## 6. Checking all paths: definite assignment

The Java compiler applies **definite assignment (DA)** and **definite unassignment (DU)**: simply seeing an assignment in the source code is not enough; the execution paths and the possible number of assignments must be valid.

~~~java
class Valid {
    private final int code;
    Valid(boolean flag) {
        code = flag ? 1 : 2; // Assigned exactly once.
    }
}
~~~

A constructor can `throw` before initialization finishes; however, it must not **complete normally** while a blank final field remains unassigned. B144 is where branch analysis is taught in detail; use this rule when determining whether a constructor/initializer is permitted to assign a field.

## 7. Runnable example: assigning across valid branches

Create the file **`BranchFinalDemo.java`**:

~~~java
final class TargetRoute {
    private final String destination;

    TargetRoute(boolean offline) {
        if (offline) {
            destination = "LOCAL";
        } else {
            destination = "REMOTE";
        }
    }

    String destination() {
        return destination;
    }
}

public class BranchFinalDemo {
    public static void main(String[] args) {
        TargetRoute local = new TargetRoute(true);
        TargetRoute remote = new TargetRoute(false);

        System.out.println("offline=" + local.destination());
        System.out.println("online=" + remote.destination());
        System.out.println("again=" + local.destination());
    }
}
~~~

Compile/run:

~~~bash
javac BranchFinalDemo.java
java BranchFinalDemo
~~~

**Stdout:**

~~~text
offline=LOCAL
online=REMOTE
again=LOCAL
~~~

There are two assignment statements `destination = ...` in the source, but **only one branch executes per object creation**. The compiler can prove that every normal initialization path assigns the field exactly once.

Conversely, if you write two assignment statements on the **same execution path**:

~~~java
class DoubleAssignment {
    private final int number;

    DoubleAssignment() {
        number = 1;
        number = 2; // COMPILE ERROR: final field has already been assigned.
    }
}
~~~

then the compiler rejects it. This is an **intentionally non-compiling** example, not a class meant to be run.

## 8. An instance initializer block can assign a blank final instance field

Not every blank final instance field has to be assigned directly inside the constructor body. An **instance initializer block** can also assign a final field that is still blank:

~~~java
final class RecordStamp {
    private final int formatVersion;
    private final String key;

    {
        formatVersion = 2;
    }

    RecordStamp(String key) {
        if (key == null || key.isBlank()) {
            throw new IllegalArgumentException("key không hợp lệ");
        }
        this.key = key;
    }

    String describe() {
        return key + "@v" + formatVersion;
    }
}
~~~

This is a **valid illustrative class**. The `formatVersion` field has no initializer on its declaration line, but the instance block assigns `2` when the object is initialized. The `key` field is assigned in the constructor.

**Relevant initialization order:** in the normal object initialization sequence, superclass initialization completes before the subclass's instance field initializers/instance initializers; the initializers belonging to a class run in the order they appear in the source, followed by the actual constructor body of that class (except that a constructor may delegate via `this(...)` under a special mechanism).

Therefore, if `formatVersion` has already been assigned in an instance initializer, you **must not additionally assign** `formatVersion = 3;` in the constructor. Meanwhile, `key` still needs to be assigned on every constructor path that completes normally.

A static nested class or inner class also obeys the final field assignment rules **of that class itself**. Being inside an enclosing class does not automatically allow the enclosing class's constructor to assign a blank final field declared in a different nested type.

## 9. `static final` without an initializer: assign only in an appropriate static initializer

For a class-level field:

~~~java
private static final int BUFFER_SIZE;
~~~

this is a **blank final static field**. It belongs to **the class**, not to each instance, so an instance constructor is not the place to assign it.

The common way is a **static initializer block**:

~~~java
private static final int BUFFER_SIZE;

static {
    int configured = 1024;
    if (configured <= 0) {
        throw new ExceptionInInitializerError("BUFFER_SIZE phải dương");
    }
    BUFFER_SIZE = configured;
}
~~~

This is an illustrative declaration snippet inside a class. The assignment `BUFFER_SIZE = configured` is located inside the static initializer of **the class declaring the field**. The compiler requires a blank final static field to be definitely assigned when the class's static initialization completes normally and not to be assigned a second time.

Distinguish:

- `static final int LIMIT = 100;`: has a field initializer, not a blank final.
- `static final int LIMIT; static { LIMIT = 100; }`: blank final, assigned in a static initializer.
- `static final int LIMIT; static void init() { LIMIT = 100; }`: **invalid** because of assigning a final field in an ordinary static method, even if the method is intended to be called only once.
- `static final int LIMIT; SomeClass() { LIMIT = 100; }`: also **invalid**; an instance-creating constructor cannot assign a blank final static field.

**Note:** `static` does not mean “can be assigned at any time through the class name.” `static final` still requires assignment within an allowed initialization region and compliance with DA/DU.

## 10. Runnable program: initializing blank final static fields

Create the file **`BlankFinalStaticDemo.java`**:

~~~java
import java.util.Locale;

final class RuntimeDefaults {
    private static final String PROFILE;
    private static final int RETRIES;

    static {
        String rawProfile = "production";
        String checkedProfile = rawProfile.strip()
                .toUpperCase(Locale.ROOT);

        if (checkedProfile.isEmpty()) {
            throw new ExceptionInInitializerError("profile rỗng");
        }

        PROFILE = checkedProfile;
        RETRIES = "PRODUCTION".equals(PROFILE) ? 3 : 1;
    }

    static String profile() {
        return PROFILE;
    }

    static int retries() {
        return RETRIES;
    }
}

public class BlankFinalStaticDemo {
    public static void main(String[] args) {
        System.out.println("profile=" + RuntimeDefaults.profile());
        System.out.println("retries=" + RuntimeDefaults.retries());
        System.out.println("again=" + RuntimeDefaults.profile());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 BlankFinalStaticDemo.java
java BlankFinalStaticDemo
~~~

**Stdout:**

~~~text
profile=PRODUCTION
retries=3
again=PRODUCTION
~~~

Mechanism:

1. When class `RuntimeDefaults` is initialized for the first time according to Java's rules, the static initializer runs.
2. The code normalizes and validates the profile, then assigns `PROFILE` and `RETRIES`.
3. Calls to the `profile()` and `retries()` methods read the two assigned fields.
4. `RuntimeDefaults` is initialized via the JVM's class initialization mechanism and **does not rerun the static initializer on every method call**.

This is an example with fixed input data so that stdout is deterministic. In a real application, `rawProfile` might come from runtime configuration, but reading configuration and handling errors must be clearly designed. An error during class initialization can leave the class unusable, so avoid placing complex logic, hard-to-control side effects, or cyclic dependencies inside a static initializer.

## 11. Static initializers must also cover every branch

A **non-compiling** example:

~~~java
class BrokenStatic {
    private static final String MODE;

    static {
        boolean valid = false;
        if (valid) {
            MODE = "ACTIVE";
        }
        // Path that does not assign MODE: definite assignment error.
    }
}
~~~

Similar to an instance constructor, the compiler must be able to establish that a blank final static field is **definitely assigned** before the class's static initializer completes normally.

A better approach:

~~~java
final class SafeStatic {
    private static final String MODE;

    static {
        boolean enabled = false;
        MODE = enabled ? "ACTIVE" : "INACTIVE";
    }

    static String mode() {
        return MODE;
    }
}
~~~

This is a valid illustrative class. The conditional expression produces a value, and `MODE` is assigned **once**.

Assignments can be split across multiple static initializer blocks within the same class as long as the compiler can still prove the DA/DU conditions; the blocks execute in textual declaration order. However, if the initialization logic is hard to follow, consolidating the computation into **a local variable inside a single static block** and assigning the field at the end is usually easier to maintain.

## 12. Field initializer and constructor: choose one place to assign

For a final instance field, both of these ways are valid **if you choose one appropriate approach**:

~~~java
class InlineLimit {
    private final int limit = 10;
}
~~~

and:

~~~java
class ConstructorLimit {
    private final int limit;

    ConstructorLimit() {
        limit = 10;
    }
}
~~~

However, the following snippet **does not compile**:

~~~java
class WrongLimit {
    private final int limit = 10;

    WrongLimit() {
        limit = 20; // Error: the final field already has an initializer.
    }
}
~~~

The examples in this section are **separate classes** intended to illustrate independent options. Reasons for choosing each:

- **Initializer at declaration:** fixed or easily expressed value that applies uniformly to every object; reduces duplication across constructors.
- **Constructor:** value depends on arguments, requires invariant validation, or is only known at object creation time.
- **Instance initializer:** shared logic for multiple constructors, though usually less clear than using a field initializer or a central constructor when a separate block is not genuinely needed.
- **Static initializer:** suitable for a blank final **class variable** that needs computation/validation during class initialization.

Do not create a blank final merely to move a simple initializer into a longer block: a short, readable form is preferred as long as it accurately expresses the requirement.

## 13. Ordinary methods cannot “fill in the blank” of a blank final field

A common misconception is defining an `initialize()` method and calling it from the constructor:

~~~java
class BrokenInitializer {
    private final String token;

    BrokenInitializer(String token) {
        initialize(token);
    }

    private void initialize(String value) {
        token = value; // Compile error: cannot assign a final field here.
    }
}
~~~

This is an **intentionally non-compiling** example. Even though `initialize` is `private` and only called by the constructor, Java **does not allow** a normal assignment to a blank final instance field from inside an instance method. The compiler does not rely on the assumption that “the method is only called once.”

Instead, you can **compute and validate the value in a helper**, and then assign the field itself from the constructor:

~~~java
final class SafeInitializer {
    private final String token;

    SafeInitializer(String value) {
        token = checkedToken(value);
    }

    private static String checkedToken(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("token không hợp lệ");
        }
        return value.strip();
    }

    String token() {
        return token;
    }
}
~~~

This is a valid illustrative class. The helper `checkedToken` **returns a value** and does not attempt to assign the final field; the constructor performs `token = checkedToken(value)` in an allowed location.

This pattern is useful when multiple constructors share the same validation rules: **separate the computation from the final assignment**, rather than moving the final field assignment into an ordinary method.

## 14. Constructors throwing exceptions and ensuring complete initialization

A constructor that throws an exception does not produce a complete instance for the caller, so it is not required to assign a final field on the **abrupt completion** path. However, if the error is caught and execution continues to the end of the constructor, all blank final fields must still satisfy DA.

An easy-to-verify flow: validate input → compute results into locals → assign fields exactly once in an allowed constructor/initializer. Avoid publishing `this` before invariants are ready; final-field visibility guarantees do not make a partially initialized object safe.

## 15. A `final` field is not necessarily a compile-time constant

Consider:

~~~java
class Limits {
    static final int FIXED = 16;
    static final int RUNTIME;

    static {
        RUNTIME = 16;
    }
}
~~~

This is a valid illustrative class. Both fields are `static final int`, yet there is an important difference:

- `FIXED` is initialized with a **constant expression** of primitive type `int`; it is a **constant variable** according to the JLS.
- `RUNTIME` is a **blank final static field**, receiving its value inside the static block. Even though after initialization it also equals 16, it is **not a constant variable** because it has no initializer at its declaration.

This distinction can affect the compiler's use of constants at call sites, places requiring a constant expression, and the *inlining* of certain `static final` constants.

Example:

~~~java
static final int PORT = 8080; // Constant variable.
static final int DYNAMIC_PORT;
static {
    DYNAMIC_PORT = Integer.parseInt("8080");
}
~~~

These are illustrative declarations inside a class. `DYNAMIC_PORT` is a value computed when class initialization runs; **it cannot be treated as a constant expression** merely because its final result is 8080.

**Do not conflate these concepts:** `final` restricts reassignment; `static` indicates class-level membership; a **constant variable** is a concept with stricter conditions, requiring an initializer that is a constant expression. A blank final field inherently does not satisfy that condition.

## 16. `final` on a reference differs from an immutable object

Create the standalone file **`FinalReferenceDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

final class Notes {
    private final List<String> items;

    Notes(List<String> items) {
        this.items = List.copyOf(items);
    }

    List<String> items() {
        return items;
    }
}

public class FinalReferenceDemo {
    public static void main(String[] args) {
        List<String> input = new ArrayList<>(List.of("Java"));
        Notes notes = new Notes(input);

        input.add("OOP");
        System.out.println("source=" + input);
        System.out.println("notes=" + notes.items());

        try {
            notes.items().add("unsafe");
        } catch (UnsupportedOperationException ex) {
            System.out.println("items cannot be changed");
        }

        System.out.println("again=" + notes.items());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 FinalReferenceDemo.java
java FinalReferenceDemo
~~~

**Stdout:**

~~~text
source=[Java, OOP]
notes=[Java]
items cannot be changed
again=[Java]
~~~

For `Notes`:

- `items` is a **blank final instance field**, assigned in the constructor.
- `List.copyOf(items)` produces a list that does not support modification through its API, preventing the caller from modifying the input list and causing this field to observe newly added elements.
- The getter returns a list that does not support modification, so `add` throws `UnsupportedOperationException`.
- If you replace the constructor assignment with `this.items = items;` and `items` is an `ArrayList`, the field is still `final`, but the caller can mutate the original list and change the elements observed through the field.

`List.copyOf` does not perform a **deep copy** of mutable element objects. The example uses immutable `String` elements, so it is appropriate. When a final field points to an array, `final int[] values` also **does not lock individual array elements**; if independence is needed, defensively copy on both input and output.

This is why `final` is a tool for **restricting field reassignment**, whereas **encapsulation and immutability** also require controlling the object graph, aliases, and all update paths.

## 17. Can a final field assigned in a superclass be assigned in a subclass?

If a blank final field is declared in a superclass, the constructor of **the superclass itself** must satisfy the initialization rule for that field. A subclass cannot reassign the superclass's final field on its own.

Example:

~~~java
class BaseDocument {
    private final String documentId;

    BaseDocument(String documentId) {
        if (documentId == null || documentId.isBlank()) {
            throw new IllegalArgumentException("documentId rỗng");
        }
        this.documentId = documentId;
    }

    String documentId() {
        return documentId;
    }
}

class Invoice extends BaseDocument {
    private final long cents;

    Invoice(String documentId, long cents) {
        super(documentId);
        if (cents < 0) {
            throw new IllegalArgumentException("cents âm");
        }
        this.cents = cents;
    }

    long cents() {
        return cents;
    }
}
~~~

The two classes above form a valid illustrative snippet. The `BaseDocument` class assigns `documentId`; the `Invoice` class calls `super(documentId)` so the superclass initializes its part, and then `Invoice` assigns the blank final field `cents` **declared by itself**.

For Java 17 constructors, if the superclass does not have a suitable no-argument constructor, the subclass must validly invoke an available superclass constructor. You must not expect to “assign BaseDocument's final field from Invoice later,” even if the field is `protected final`: assignment in a subclass still cannot replace the initialization responsibility of the declaring class.

**Access permissions and reassignment permissions are two different rules.** A subclass may be allowed to *read* a `protected final` field under the rules of `protected`, but that does not mean it has permission to reassign it.

## 18. Records and blank final fields: how are they related?

In Java 17, a `record` has **record components**, which are represented in the record's state via `private final` fields according to its own rules. The record's canonical constructor is responsible for setting the corresponding components.

Example:

~~~java
record Money(long cents) {
    Money {
        if (cents < 0) {
            throw new IllegalArgumentException("cents âm");
        }
    }

    Money add(long extra) {
        if (extra < 0) {
            throw new IllegalArgumentException("extra âm");
        }
        return new Money(Math.addExact(cents, extra));
    }
}
~~~

This is a valid illustrative record. The compact canonical constructor `Money { ... }` allows validating `cents`; Java applies the mechanism of assigning the record's component fields after the compact constructor body according to record rules, so you do not need to write `this.cents = cents;` yourself.

Do not mistakenly assume that **every record component must be initialized in the exact same way as a blank final field manually declared in an ordinary class**. A record has **specific constructor rules**, and users are not allowed to declare arbitrary additional instance fields in a record.

If you want a direct example of manually assigning a blank final field in a constructor, using a regular class such as `Ticket` or `UserKey` is clearer. Records are well suited for seeing how Java helps model immutable value objects.

## 19. Static blank finals and class initialization order

Static field initializers and static initializer blocks execute in **textual order** during the appropriate class initialization process. Therefore:

~~~java
final class StaticOrder {
    private static final int VALUE;

    static {
        int source = 10;
        VALUE = source * 2;
    }

    static int value() {
        return VALUE;
    }
}
~~~

is a valid class: `VALUE` is assigned inside the static initializer and has the value 20 after class initialization completes.

The risk does not lie in using a static block itself, but in **the complexity of dependency logic**:

- A static initializer that calls another class can trigger related class initialization.
- Circular dependencies between static classes/fields can create unpredictable situations or prematurely observed values.
- An exception during class initialization can cause subsequent uses to fail; do not assume the error affects only a single object as when a constructor throws an error.
- I/O or environment operations can fail; you must decide whether failing class initialization is acceptable or whether configuration setup should be deferred to a separate mechanism.

For a simple value that needs no branching or validation, an initializer right at the declaration is usually clearer than a static block. A static block is useful when you must validate, normalize, or process multiple values **before the final assignment**.

## 20. `final`, thread safety, and premature publication of `this`

The Java Memory Model provides specific guarantees for **final fields of properly constructed objects**, with the important condition that the object reference is not published prematurely during construction.

Example of good design:

~~~java
final class SessionKey {
    private final String key;

    SessionKey(String key) {
        if (key == null || key.isBlank()) {
            throw new IllegalArgumentException("key không hợp lệ");
        }
        this.key = key;
    }

    String key() {
        return key;
    }
}
~~~

The constructor sets the field before returning. The caller can use an appropriate **safe publication** mechanism when sharing the object with other threads.

Conversely, inside a constructor, you should not register `this` as a listener or start a thread that might read `key` **before the field is assigned**. This can expose a partially initialized state and break the conditions needed to rely on safe final-field initialization semantics.

**Distinguish carefully:**

- Blank final instance fields are checked by the compiler for **definite assignment**.
- `final` does not make mutable child objects immutable.
- `final` does not turn every method into an atomic or thread-safe operation.
- Using immutable objects and proper publication helps reduce concurrency risks, but mutable state shared across threads still requires its own protection mechanisms.

This problem is distinct from the field merely having a single assignment in source code: **a syntactically valid assignment does not by itself prove the entire object lifecycle is safe**.

## 21. Common compilation errors and misconceptions

| Case | Why is it wrong? | How to fix |
| --- | --- | --- |
| `final String id;` but constructor does not assign it | No definite assignment before normal completion | Assign on every constructor path |
| Assigning a final field twice in the same constructor | Violates definite unassignment | Choose one assignment |
| Final field already assigned at declaration, assigned again in constructor | Field is no longer blank and has already been assigned | Use a single initialization place |
| One `if` branch assigns, the other branch is left empty | There is a normal completion path where the field is unassigned | Assign in both branches or compute a common value |
| `final` field assigned for the first time in a setter | Assigning a final field outside a constructor/initializer is invalid | Compute the value beforehand and assign in the constructor |
| Calling `initialize()` so a method assigns a blank final field | Assignment occurs inside an ordinary method | Helper returns the value; constructor assigns the field |
| Blank `static final` assigned from a constructor | Static field does not belong to individual instances and cannot be assigned there | Static initializer block |
| Blank `static final` assigned from a static method | An ordinary static method is not a valid assignment location | Compute in a helper, then assign in a static block |
| Assigning a parent class's final field in a subclass constructor | The field belongs to the initialization scope of the declaring class | Have the superclass constructor assign it |
| Treating a blank final as always null/0 after successful creation | Compiler requires assignment before normal completion | Understand DA/DU; do not rely on defaults |
| Treating `final List` as an unmodifiable list | Final protects the field reference, does not lock the object | Use defensive copies/immutable collections |
| Treating `static final` as always a compile-time constant | A blank final assigned in a block is not a constant variable | Distinguish initializers using constant expressions |
| Using a public constructor that leaks `this` before assignment | Object may be observed partially initialized | Do not publish the object inside the constructor |
| Assigning a final field and expecting to change it later via a setter for configuration | Cannot be reassigned through normal code paths | Create a new object or use a controlled non-final field |
| Assuming `final` guarantees thread safety for the entire object | Mutable state/concurrency has its own requirements | Proper synchronization and ownership |

The **intentionally non-compiling** examples in this lesson are explicitly noted to explain the errors. When auditing a project, fix the **definite assignment/duality root cause**, rather than mechanically removing `final` just to get the program past the compiler.

## 22. Blank final field design checklist

When a field is declared `final` without an initializer, check:

1. Does this field **belong to an object** or **belong to the class**? Does it need `static`?
2. **When is the value known?** Right at declaration, or only when the constructor/static initializer runs?
3. If it is an instance field, does **every constructor** assign it before normal completion?
4. If `this(...)` is used, are assignments centralized in the target constructor to avoid duplication?
5. If there are `if`/`switch`/`try` statements, do all successful branches validly assign it?
6. Is the field being assigned from both an instance initializer and a constructor?
7. If it is `static final`, is the assignment in a **valid static initializer**, or mistakenly inside a static method?
8. Does the input need validation/normalization before storing the value?
9. Does a field referencing a mutable object need a defensive copy or clear ownership?
10. Could the constructor publish `this` prematurely to a callback/thread?
11. Is the field used for a **compile-time constant** or a final runtime value?
12. When business logic needs a new value, should you create a replacement instance or intentionally use a mutable field instead of fighting against `final`?

It is best to treat a `final` field as **a state design decision**, not a decorator to make code “look safe.” Compiler rules help restrict reassignment, while the business contract is still defined by the class author.

## 23. Practice exercises

**Exercise 1 — Assignment point.** Class `Employee` has `private final String id;`. Its constructor takes `String id`. Write a valid assignment and explain why `setId` cannot reassign it later.

**Exercise 2 — Two constructors.** A class has `final int level;`, a no-argument constructor, and a constructor taking `int`. What must both creation paths do for the compiler to accept them? Should `this(...)` be used?

**Exercise 3 — Missing branch.** Given `final String mode;` and a constructor that only assigns `mode` when `debug == true`, what does the compiler reject? Fix it in two ways.

**Exercise 4 — Duplicate assignment.** If `final int size = 10;` yet the constructor also has `size = 20;`, why is that wrong? Choose a design if the value must be decided by the constructor.

**Exercise 5 — Initializer block.** A blank final instance field has already been assigned in `{ field = 3; }`. Can the constructor also assign `field = 4;`?

**Exercise 6 — Static blank.** Write a class with `private static final String MODE;` assigned conditionally inside a static initializer. Why can that assignment not be moved into a static method `init()`?

**Exercise 7 — Helper.** A constructor calls `validateAndSet(token)`, and the helper assigns `this.token = ...` to the blank final field. Why does the compiler reject this? Design a helper that returns the result instead.

**Exercise 8 — Constant expression.** Compare `static final int A = 10;` and `static final int B; static { B = 10; }` with respect to whether they qualify as a constant variable.

**Exercise 9 — Inheritance.** A parent class declares a blank `protected final int code;`. Can a child class assign that value in its own constructor without the parent class assigning it? Why?

**Exercise 10 — Final reference.** `private final List<String> names;` is assigned an `ArrayList`. Can you write `names = anotherList` in a setter? Can you write `names.add("A")`?

**Exercise 11 — Exception.** A constructor throws `IllegalArgumentException` before assigning a blank final field. Does Java require that constructor to complete the assignment on the exception path? Should `this` be published before throwing the error?

**Exercise 12 — Record.** With `record Price(long cents)`, how does a compact canonical constructor validate `cents`, and why is `this.cents = cents;` not needed inside the compact constructor body?

### Reference answers

1. `this.id = id;` in the constructor; a `final` field cannot be reassigned from a setter method.
2. Every constructor path that completes normally must assign the field exactly once. Usually you should use `this(defaultLevel)` to centralize assignment in the constructor that takes `int`.
3. There is a normal completion path missing an assignment. Fix it with `else { mode = "RELEASE"; }` or by computing `String selected = debug ? "DEBUG" : "RELEASE"; mode = selected;`.
4. The final field already has an initializer. If the constructor must decide it, declare `final int size;` without an initializer, then assign it only in the constructor.
5. No; the field has already been assigned in the instance initializer before the corresponding constructor body.
6. You can use `static { MODE = condition ? "A" : "B"; }`; assigning a `static final` field cannot be moved into an ordinary static method.
7. An ordinary method is not an allowed place to assign a blank final field. Use `this.token = checkedToken(token);` in the constructor, with the helper only validating and returning the value.
8. `A` is a constant variable since `10` is a constant expression; `B` is not because a blank final receives its value in a static block.
9. No. The superclass must initialize the final field it declares before the superclass constructor completes normally.
10. A setter cannot reassign `names`, but if the list object is mutable and the API permits it, `names.add("A")` is valid. A defensive copy is needed if immutability is desired.
11. Assignment is not required on the exception-throwing path; you should not publish a partially initialized `this` to external code.
12. For example, `Price { if (cents < 0) throw new IllegalArgumentException("cents âm"); }`; the component field is automatically assigned by the record under the compact canonical constructor mechanism.

## 24. References

- [Java Language Specification 17, §4.12.4 — `final` Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): blank finals and assignment rules for final variables.
- [Java Language Specification 17, §8.3.1.2 — `final` Fields](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3.1.2): meaning of final for fields.
- [Java Language Specification 17, §8.3.2 — Field Initialization](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3.2): field initialization.
- [Java Language Specification 17, §8.7 — Static Initializers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.7): static initializer blocks.
- [Java Language Specification 17, §8.6 — Instance Initializers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.6): instance initializer blocks.
- [Java Language Specification 17, §8.8 — Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8): constructors and object initialization paths.
- [Java Language Specification 17, §16 — Definite Assignment](https://docs.oracle.com/javase/specs/jls/se17/html/jls-16.html): DA/DU across control-flow paths.
- [Java Language Specification 17, §12.4 — Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4): class initialization mechanism.
- [Java Language Specification 17, §17.5 — `final` Field Semantics](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.5): semantics of final fields in the Java Memory Model.
- [Java Language Specification 17, §8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): specific rules of records.

**Key takeaway:** A `final` field **is not required to have an initializer on its declaration line**. For a **blank final instance field**, assign it inside an **instance initializer or constructor of the declaring class**, ensuring it is assigned on every successful initialization path and not assigned a second time. For a **blank final static field**, use the class's **static initializer**. Do not move final assignment into an ordinary method or a subclass constructor; do not confuse a final reference with an immutable object or with a compile-time constant. The compiler checks *definite assignment*, while validation and safe object publication are your design responsibilities.
