# `final` Fields and the Requirement to Assign Values on Every Initialization Branch in Java

In Java, a **field declared `final`** is only allowed to receive a value according to the **one-time initialization rule**. For a **blank final field** — a field with the `final` keyword but **no initializer at its declaration site** — the compiler applies **definite assignment**: every initialization execution path that can **complete normally** must set a value for that field, and no valid assignment path may assign it a second time.

This is an important Java Core topic covering **classes, objects, constructors, and the `final` keyword**. It explains why there are constructors that appear to “usually” assign a field yet still **do not compile**, why `if/else` must cover all valid branches, and why a constructor throwing an exception before completion is not the same as a path that creates an object successfully.

Minimal example:

~~~java
class User {
    private final String id;

    User(String id) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("ID không hợp lệ");
        }
        this.id = id;
    }

    String id() {
        return id;
    }
}
~~~

This is a **class declaration snippet**, without a standalone runnable `main`. The `id` field is a **blank final instance field**. The constructor has two branches:

1. Invalid input: throws `IllegalArgumentException`; the constructor **does not complete normally** and does not return a successfully created `User` to the caller.
2. Valid input: executes `this.id = id`, then completes normally; the field now has a single value.

**Keep in mind:** a blank final must be assigned **exactly once on every initialization path that completes normally**, not “exactly once on every path including paths that intentionally throw an exception”.

This lesson uses **Java 17+**. Examples illustrating compiler errors are commented out or placed in snippets explicitly noted as **does not compile**; programs with `main` are kept separate, with exact run commands and stdout.

## 1. Distinguishing the Forms of `final` Fields

A Java class can declare final fields in different forms:

~~~java
class Config {
    final int maxRetries = 3;             // Initialized instance final
    final String name;                     // Blank final instance field

    static final int DEFAULT_PORT = 8080; // Initialized static final
    static final String ENVIRONMENT;       // Blank static final field

    static {
        ENVIRONMENT = "development";
    }

    Config(String name) {
        this.name = name;
    }
}
~~~

The members:

| Declaration | Field kind | Where value assignment completes |
| --- | --- | --- |
| `final int maxRetries = 3;` | Instance final with initializer | Field initializer that runs when creating each object |
| `final String name;` | Blank final instance | Constructor or appropriate instance initializer of the class itself |
| `static final int DEFAULT_PORT = 8080;` | Static final with initializer | Field initializer during class initialization |
| `static final String ENVIRONMENT;` | Blank static final | Appropriate static initializer of the class itself |

An **instance field** belongs to each object: each `new Config("A")` has a `name` assigned in that object's constructor. A **static field** is associated with the corresponding runtime class; `ENVIRONMENT` is initialized along the class initialization path, not reassigned when creating each Config object.

### 1.1. `final` Does Not Mean “The Field Must Have Its Initializer Written Directly on the Declaration Line”

Both are valid:

~~~java
class IdA {
    final int id = 7;
}

class IdB {
    final int id;

    IdB(int id) {
        this.id = id;
    }
}
~~~

`IdA.id` is assigned from a field initializer. `IdB.id` is assigned in the constructor. There is no requirement to use a field initializer when the value must be chosen from a parameter, validation, or business branch at the time of object creation.

### 1.2. `final` Is Not the Same as `static` and Is Also Not the Same as `const`

- `final` on a field: restricts **reassignment** of the field according to Java rules.
- `static`: the field **belongs to the class** rather than to each object.
- `static final`: combines both properties.
- Java does not have a model of placing a `const` keyword before a field to replace `final` in ordinary Java programs.

Constants like `Math.PI` are static final, but **not every static final field is a compile-time constant**. There is a kind of final reference to an object created at runtime, and that object can still be mutable.

## 2. What Is “Definite Assignment”?

**Definite assignment (DA)** is a compile-time analysis that enables the compiler to verify that a variable must be assigned **before it is read** or before the end of an initialization path that can complete normally. For a blank final, there is also the rule of **definite unassignment (DU)** before an assignment: the compiler must ensure that the assignment does not reassign a final field that has already been assigned on the corresponding path.

**The compiler analyzes control flow**, rather than test-running the program with a few random inputs to guess which branch occurs. Therefore, the code must satisfy the rules for the branches that the compiler considers executable according to the analyzed semantics.

Valid example:

~~~java
class Message {
    final String text;

    Message(boolean english) {
        if (english) {
            text = "Hello";
        } else {
            text = "Xin chào";
        }
    }
}
~~~

Both branches assign `text` exactly once. After the `if/else` statement, the compiler can determine that `text` has been assigned on every path that completes normally.

In contrast:

~~~java
class BrokenMessage {
    final String text;

    BrokenMessage(boolean english) {
        if (english) {
            text = "Hello";
        }
        // Compile error: the english == false path does not assign text
    }
}
~~~

The `BrokenMessage` snippet **does not compile** because the constructor can complete normally when `english == false` while the blank final `text` has not been assigned.

### 2.1. DA Is Not Checking Whether the Value Differs from `null`

~~~java
class Box {
    final String label;

    Box() {
        label = null; // Valid under definite assignment
    }
}
~~~

The `label` field is assigned exactly once, even though **the assigned value is null**. `final` does not mean a non-null reference. If business logic does not accept null, separate validation is required:

~~~java
this.label = java.util.Objects.requireNonNull(
        input, "label");
~~~

**Definite assignment answers the question “has it been assigned?”**, not by itself “is the value valid for the business rules?”. Ecosystem-specific `@NonNull` annotations are also not a universal replacement for the standard Java compiler's DA rules.

## 3. Initializing Blank Final Instance Fields in a Constructor

A blank final instance field typically takes its value from constructor parameters:

~~~java
class Product {
    private final String sku;
    private final long price;

    Product(String sku, long price) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU rỗng");
        }
        if (price < 0) {
            throw new IllegalArgumentException("Giá âm");
        }

        this.sku = sku;
        this.price = price;
    }
}
~~~

When the constructor completes normally, both `sku` and `price` have been assigned. The checks may throw an exception; those paths **do not create a Product successfully**, and therefore are not required to complete the two assignments before throwing.

### 3.1. Good Ordering: Validate, Compute, Then Assign

A constructor should avoid letting the object escape while only some fields are initialized. You can proceed as follows:

1. Validate all required parameters.
2. Compute derived values and check operations that can throw an exception.
3. Assign the final fields so that the compiler proves the rules hold.
4. Do not call an overridable method/register a callback that exposes `this` before object initialization is complete.

Example:

~~~java
class Invoice {
    private final long subtotal;
    private final long total;

    Invoice(long subtotal, long tax) {
        if (subtotal < 0 || tax < 0) {
            throw new IllegalArgumentException("Số âm");
        }
        long calculated = Math.addExact(subtotal, tax);
        this.subtotal = subtotal;
        this.total = calculated;
    }
}
~~~

`Math.addExact` can throw `ArithmeticException` on `long` overflow. The calculation happens before the two final field assignments; if it fails, the constructor does not complete. If it succeeds, the two final fields are assigned.

This is a good design choice, but **Java does not automatically roll back other side effects** that occurred before the exception. For instance, writing data to an external system or adding `this` to a static collection inside a constructor can still create risks even when final assignments are valid.

## 4. If There Is an `if/else`: Every Path That Completes Normally Must Assign

Compare the two snippets:

**Correct:**

~~~java
class AccessToken {
    private final String prefix;

    AccessToken(boolean administrator) {
        if (administrator) {
            prefix = "ADM";
        } else {
            prefix = "USR";
        }
    }
}
~~~

**Incorrect:**

~~~java
class AccessToken {
    private final String prefix;

    AccessToken(boolean administrator) {
        if (administrator) {
            prefix = "ADM";
        }
        // No else and no fallback assignment.
    }
}
~~~

The second snippet **does not compile**. The user can run the constructor with `administrator == false`; the compiler does not accept a path that allows the constructor to complete normally with `prefix` unassigned.

### 4.1. You Can Use the Ternary Operator to Assign Once

If only choosing between two values:

~~~java
class AccessToken {
    private final String prefix;

    AccessToken(boolean administrator) {
        prefix = administrator ? "ADM" : "USR";
    }
}
~~~

This approach has **a single assignment** to the final field; the conditional operator selects the value. For complex logic, `if/else` can be more readable.

### 4.2. Do Not “Patch” with a Second Assignment After `if/else`

~~~java
class Wrong {
    final int code;

    Wrong(boolean flag) {
        if (flag) {
            code = 1;
        } else {
            code = 2;
        }

        // code = 3; // Compile error: final field already assigned
    }
}
~~~

`final` does not allow you to update the field after completing the selection. If you want flexible computation, compute using a **local variable** first and then assign the field once:

~~~java
class Correct {
    final int code;

    Correct(boolean flag) {
        int calculated = flag ? 1 : 2;
        calculated += 10;
        code = calculated;
    }
}
~~~

The local `calculated` is not declared final, so it can be updated. `code` receives only one final value.

## 5. Complete Example: Assigning final on Every Valid Branch

Create the file **`FinalBranchesDemo.java`**:

~~~java
public class FinalBranchesDemo {
    static final class Badge {
        private final String label;
        private final int level;

        Badge(String name, boolean premium) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("Tên rỗng");
            }

            if (premium) {
                label = "VIP-" + name;
                level = 2;
            } else {
                label = "STD-" + name;
                level = 1;
            }
        }

        String description() {
            return label + "/level=" + level;
        }
    }

    public static void main(String[] args) {
        Badge vip = new Badge("Lan", true);
        Badge normal = new Badge("Mai", false);

        System.out.println(vip.description());
        System.out.println(normal.description());

        try {
            new Badge(" ", true);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected = " + ex.getMessage());
        }

        System.out.println(vip.description());
    }
}
~~~

Run with JDK 17+:

~~~bash
javac -encoding UTF-8 FinalBranchesDemo.java
java FinalBranchesDemo
~~~

**Exact stdout:**

~~~text
VIP-Lan/level=2
STD-Mai/level=1
Rejected = Tên rỗng
VIP-Lan/level=2
~~~

**Analysis:**

1. `new Badge("Lan", true)` selects the `premium == true` branch. Both `label` and `level` are assigned once.
2. `new Badge("Mai", false)` selects the `else` branch. Both final fields are also assigned.
3. `new Badge(" ", true)` enters the invalid branch, throwing an exception before assigning fields. The constructor does not complete normally; therefore, this **does not violate the DA rule for blank finals**.
4. `vip` is a different object that was already initialized successfully, so `description()` can still be called after the third Badge creation fails.

This example demonstrates the exact compile-time rule, not just behavior based on a few test values. The compiler sees that both the `if` and `else` branches fully assign both final fields when they can end normally.

## 6. A Branch That Throws an Exception Differs from a Branch That Fails to Assign and Returns

The important condition is **can the constructor complete normally?**

**Valid:**

~~~java
class Port {
    final int number;

    Port(int number) {
        if (number < 1 || number > 65535) {
            throw new IllegalArgumentException("Port sai");
        }
        this.number = number;
    }
}
~~~

Inputs outside the allowed range cause the constructor to terminate abnormally with an exception. For valid inputs, the `number` field is assigned before the constructor completes.

**Invalid:**

~~~java
class Port {
    final int number;

    Port(int number) {
        if (number < 1 || number > 65535) {
            return; // Constructor ends normally without an assignment.
        }
        this.number = number;
    }
}
~~~

The second snippet **does not compile**. In a Java constructor, `return;` does not return an object via an expression like a regular method, yet it can still end the constructor **normally**. If this branch exits the constructor before the blank final is assigned, the compiler detects a violation.

### 6.1. No Need to Assign final Before Every `throw` Statement

An exception intentionally reporting invalid input can occur before the final assignment. Do not create a dummy value like `id = "UNKNOWN"` before `throw` just to “please the compiler”; that is usually redundant and can cause unnecessary side effects.

However, if you **catch the exception and continue** to the end of the constructor, you must ensure that the final fields are assigned along that continuing path. To avoid tangled logic, it is usually best to validate and compute using locals before assigning fields, or throw the exception outward when the state cannot be initialized.

## 7. Multiple Constructors: Every Path That Successfully Creates an Object Must Be Valid

A class can have multiple constructor overloads:

~~~java
class Task {
    private final String title;
    private final int priority;

    Task() {
        this("Untitled", 1);
    }

    Task(String title) {
        this(title, 1);
    }

    Task(String title, int priority) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("Tiêu đề rỗng");
        }
        if (priority < 1 || priority > 5) {
            throw new IllegalArgumentException("Ưu tiên sai");
        }
        this.title = title;
        this.priority = priority;
    }
}
~~~

Constructors are not required to **each contain a direct assignment** to the same field. `Task()` and `Task(String)` call **another constructor in the same class** via `this(...)` (*constructor chaining*). If the delegation chain ultimately initializes the blank final fields completely before completing, all the constructors are valid.

### 7.1. `this(...)` Is Not a Field Reassignment

~~~java
Task() {
    this("Untitled", 1);
}
~~~

`this(...)` is an **explicit constructor invocation**, not calling a method named “this”. In Java 17, such a call must be the **first statement** of the constructor body, and the same constructor cannot explicitly call both `this(...)` and `super(...)`. The constructor invoked through `this(...)` performs the field initialization work.

This makes it possible to consolidate validation and blank final assignments into a central constructor, avoiding duplicating logic across multiple overloads.

### 7.2. Constructor Chaining Must Not Create a Cycle

~~~java
class Wrong {
    Wrong() {
        this(1);
    }

    Wrong(int n) {
        this();
    }
}
~~~

This snippet **does not compile** due to a recursive constructor invocation. There is no valid initialization path that reaches the part performing field assignments. Chaining constructors must lead to a constructor that performs the actual initialization.

### 7.3. A Constructor Overload That Does Not Chain Must Ensure Final Fields Itself

~~~java
class Wrong {
    final String id;

    Wrong() {
        id = "AUTO";
    }

    Wrong(String id) {
        // Does not assign this.id => compile error
    }
}
~~~

The snippet above **does not compile**: another valid overload does not “rescue” the `Wrong(String)` constructor when it completes normally while omitting the blank final.

## 8. Complete Example: Constructor Chaining and `final` Fields

Save the file **`ConstructorChainDemo.java`**:

~~~java
public class ConstructorChainDemo {
    static final class ConnectionSettings {
        private final String host;
        private final int port;
        private final boolean secure;

        ConnectionSettings() {
            this("localhost", 8080, false);
        }

        ConnectionSettings(String host) {
            this(host, 443, true);
        }

        ConnectionSettings(String host, int port, boolean secure) {
            if (host == null || host.isBlank()) {
                throw new IllegalArgumentException("Host rỗng");
            }
            if (port < 1 || port > 65535) {
                throw new IllegalArgumentException("Port sai");
            }
            this.host = host;
            this.port = port;
            this.secure = secure;
        }

        String summary() {
            return host + ":" + port + "/secure=" + secure;
        }
    }

    public static void main(String[] args) {
        ConnectionSettings a = new ConnectionSettings();
        ConnectionSettings b = new ConnectionSettings("example.org");
        ConnectionSettings c =
                new ConnectionSettings("api.local", 8443, true);

        System.out.println("Default = " + a.summary());
        System.out.println("Host only = " + b.summary());
        System.out.println("Explicit = " + c.summary());

        try {
            new ConnectionSettings("example.org", 0, false);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected = " + ex.getMessage());
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 ConstructorChainDemo.java
java ConstructorChainDemo
~~~

**Exact stdout:**

~~~text
Default = localhost:8080/secure=false
Host only = example.org:443/secure=true
Explicit = api.local:8443/secure=true
Rejected = Port sai
~~~

Here:

- The zero-parameter and one-parameter constructors **do not assign the three final fields directly**; they call the three-parameter constructor.
- The three-parameter constructor validates and then assigns `host`, `port`, and `secure` once.
- Every path that completes normally goes through those three assignments.
- For an invalid port, the constructor throws an exception before completing and does not produce a usable `ConnectionSettings`.

**Design tip:** constructor chaining reduces duplication. However, if a constructor overload genuinely has different semantics, do not blindly chain to a constructor with conflicting preconditions; design a clear shared contract.

## 9. A Field Initializer and a Constructor Cannot Both Assign the Same final Field

If a final field already has an initializer at its declaration:

~~~java
class Settings {
    final int retries = 3;

    Settings() {
        // retries = 5; // Error: cannot assign a value to final variable
    }
}
~~~

The `retries` field has already been assigned by the instance field initializer. The constructor cannot reassign it. For an instance of the class created with `new Settings()`, the value remains 3.

**Common mistake:** writing a “temporary” initializer like `final int retries = 0;` and wanting the constructor to replace it with the real value. `final` does not work under a model of “you can replace a placeholder value once later”. The assignment in the field initializer has already used the field's assignment right.

To let the constructor choose the value, declare a **blank final**:

~~~java
class Settings {
    final int retries;

    Settings(int retries) {
        if (retries < 0) {
            throw new IllegalArgumentException("retries âm");
        }
        this.retries = retries;
    }
}
~~~

## 10. An Instance Initializer Block Can Also Assign a Blank final

Java allows instance initializer blocks:

~~~java
class Sequence {
    private final int base;

    {
        base = 100;
    }

    Sequence() {
    }

    Sequence(String ignored) {
    }
}
~~~

The instance initializer runs during the creation of **each object**; it assigns `base` once, so neither constructor has to reassign that field.

Conversely, the following snippet is incorrect:

~~~java
class Wrong {
    final int base;

    {
        base = 100;
    }

    Wrong() {
        // base = 200; // Error: final has already been assigned
    }
}
~~~

### 10.1. A Conditional Instance Initializer Must Still Satisfy DA

~~~java
class Feature {
    final String mode;

    {
        boolean debug = Boolean.getBoolean("feature.debug");
        mode = debug ? "DEBUG" : "NORMAL";
    }
}
~~~

The initializer always assigns `mode` once, even though the value depends on a system property. External code can observe one of the two string values when the object is initialized successfully.

If the initializer only assigns a field in the `if (debug)` branch without an `else`/fallback branch and the constructors do not handle the missing case, the class will violate definite assignment.

### 10.2. Design Choice

Instance initializer blocks are a valid feature, but they easily scatter initialization logic across field initializers, blocks, and constructors. For an ordinary class that needs input validation, **constructor chaining + controlled assignment in a single constructor** is usually more readable. Only use an initializer block when it genuinely helps apply shared initialization behavior across multiple constructors.

## 11. Blank `static final`: Must Be Initialized in Class Context, Not Wait for a Constructor

A blank static final differs from a blank instance final in that it **does not belong to each object** and must be assigned through the static initialization of the declaring class:

~~~java
class Environment {
    static final String NAME;

    static {
        NAME = "development";
    }
}
~~~

The compiler sees that the static initializer path that completes normally assigns `NAME` exactly once. In Java 17, static initialization follows the order of the class's static field initializers and static initializer blocks.

**Invalid:**

~~~java
class Wrong {
    static final String NAME;

    Wrong() {
        // NAME = "development"; // Cannot assign a blank static final from a constructor
    }
}
~~~

A static field has a class lifecycle, whereas a constructor runs per object; putting the assignment of a static final inside a constructor does not satisfy Java's mechanism. Even if you intend to “create only one object”, the compiler does not use that runtime assumption to validate an assignment in the wrong context.

### 11.1. Static Final Initialized Directly at Declaration

~~~java
class Limits {
    static final int MAX_ITEMS = 100;
    static final String DEFAULT_MODE = "safe";
}
~~~

There is no need for a static block just to assign simple expressions. For computed values that involve validation or require multi-step structuring, a static initializer or a valid static helper may be appropriate.

### 11.2. Static Final Computed in a Controlled Way via a Local

~~~java
class SystemMode {
    static final String MODE;

    static {
        String candidate = System.getProperty(
                "app.mode", "safe").trim();

        if (candidate.isEmpty()) {
            candidate = "safe";
        }

        MODE = candidate;
    }
}
~~~

The static block uses the local `candidate` (which can be reassigned) and then assigns `MODE` **once** at the end. This is useful when computation has multiple steps, yet the final field should only receive the final result.

If `getProperty` or `trim` throws an exception, class initialization may fail, and the field is not necessarily assigned on that abnormal path. **The definite assignment condition applies to static initialization paths that complete normally.**

## 12. A Branching Static Initializer Also Needs Full Coverage

**Valid:**

~~~java
class AppProfile {
    static final String REGION;

    static {
        boolean domestic = Boolean.getBoolean("app.domestic");

        if (domestic) {
            REGION = "VN";
        } else {
            REGION = "GLOBAL";
        }
    }
}
~~~

Both branches assign `REGION` once, so when class initialization completes normally, the final field has been assigned.

**Invalid:**

~~~java
class Wrong {
    static final String REGION;

    static {
        if (Boolean.getBoolean("app.domestic")) {
            REGION = "VN";
        }
        // If false, the static initializer still ends normally,
        // but REGION has not been assigned.
    }
}
~~~

The second snippet **does not compile** because it lacks an assignment branch when the condition is false. The check result does not depend on whether your system currently has the property `app.domestic=true` set. The compiler must prove the DA rule based on the code structure.

### 12.1. Do Not Initialize a Blank Static Final Inside a Regular Static Method

~~~java
class Wrong {
    static final String REGION;

    static void initialize() {
        // REGION = "VN"; // Invalid for a blank static final
    }

    static {
        initialize(); // The compiler does not treat this method as a final assignment
    }
}
~~~

A blank static final must be assigned in a location that Java permits and where definite assignment can be proven during class initialization. A static helper **can return a value** for the static initializer to assign:

~~~java
class Correct {
    static final String REGION;

    static {
        REGION = readRegion();
    }

    private static String readRegion() {
        return System.getProperty("app.region", "VN");
    }
}
~~~

`readRegion()` performs the computation; **the assignment to `REGION` resides in the static initializer**. This is a way to separate work without attempting to assign a blank final from an arbitrary method.

## 13. Complete Program: Initializing Blank Static Final and Instance Final

Create the file **`FinalInitializationDemo.java`**:

~~~java
public class FinalInitializationDemo {
    static final class Job {
        private static final String PREFIX;

        static {
            String proposed = "JOB";
            PREFIX = proposed + "-";
            System.out.println("Static prefix ready");
        }

        private final String id;
        private final int retries;

        Job(String id, boolean urgent) {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("ID rỗng");
            }

            this.id = PREFIX + id;
            this.retries = urgent ? 1 : 3;
        }

        String summary() {
            return id + "/retries=" + retries;
        }

        static String prefix() {
            return PREFIX;
        }
    }

    public static void main(String[] args) {
        System.out.println("Start");
        System.out.println("Prefix = " + Job.prefix());

        Job first = new Job("A", true);
        Job second = new Job("B", false);

        System.out.println(first.summary());
        System.out.println(second.summary());

        try {
            new Job("", true);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected = " + ex.getMessage());
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 FinalInitializationDemo.java
java FinalInitializationDemo
~~~

**Exact stdout:**

~~~text
Start
Static prefix ready
Prefix = JOB-
JOB-A/retries=1
JOB-B/retries=3
Rejected = ID rỗng
~~~

Explanation:

1. `Job.prefix()` is a static method and triggers initialization of the runtime class Job if it is not already initialized. The static initializer assigns the blank static final `PREFIX` once and prints `Static prefix ready`.
2. Creating a Job object does not re-run the static initializer; constructors read the shared `PREFIX`.
3. Each Job instance has blank final fields `id` and `retries`, which are assigned by the constructor exactly once when the input is valid.
4. `urgent ? 1 : 3` selects the value; the assignment to `retries` itself still happens only once per object.
5. An empty id input causes the constructor to throw an exception and does not create a Job successfully; it does not change the static final field.

## 14. You Can Use `switch` or a Switch Expression to Select a final Value

Traditional `switch` branches must be structured so that the compiler sees the final field is assigned exactly once and no completion path is missed.

An example using Java 17's **switch expression** helps produce one value and then assign the field once:

~~~java
enum Tier {
    BASIC, PRO, ENTERPRISE
}

class Subscription {
    private final int limit;

    Subscription(Tier tier) {
        if (tier == null) {
            throw new IllegalArgumentException("tier null");
        }

        this.limit = switch (tier) {
            case BASIC -> 10;
            case PRO -> 100;
            case ENTERPRISE -> 1_000;
        };
    }

    int limit() {
        return limit;
    }
}
~~~

This is a Java 17 declaration (without `main`). The switch expression is **exhaustive** over all listed enum constants, so it produces an `int` for the assignment. Despite three different choices, `limit` is assigned via only **one assignment statement** in the constructor.

If a new enum constant is added later, the missing case can cause the compiler to require you to update the switch expression under the exhaustiveness rule. This can be useful for catching unhandled cases.

### 14.1. Do Not Assign a final Field Inside a Loop Where DA/DU Cannot Be Proven

Incorrect example:

~~~java
class Wrong {
    final int result;

    Wrong(int[] numbers) {
        for (int n : numbers) {
            // result = n; // Could assign multiple times if there are multiple elements.
        }
    }
}
~~~

If you genuinely want to obtain a value from a collection, compute it using a local variable and then assign once:

~~~java
class Sum {
    final long result;

    Sum(int[] numbers) {
        long calculated = 0;
        for (int n : numbers) {
            calculated = Math.addExact(calculated, n);
        }
        result = calculated;
    }
}
~~~

`calculated` is a local variable that can be updated multiple times; `result` is a blank final field that receives exactly **one** result. This is a good pattern for accumulation logic, multi-step validation, or complex computations.

## 15. Differences Between a final Field and a final Local Variable

Consider:

~~~java
class Demo {
    private final int field;

    Demo(int input) {
        final int local = input + 1;
        field = local;
    }
}
~~~

`field` is a **blank final instance field** that must be validly assigned during object initialization. `local` is a **final local variable** scoped to the constructor. Both are subject to reassignment restrictions, but their initialization responsibilities differ.

For a local variable, the compiler does not allow reading before definite assignment:

~~~java
void example(boolean flag) {
    final int number;
    if (flag) {
        number = 1;
    } else {
        number = 2;
    }
    System.out.println(number);
}
~~~

This method body example is valid if placed inside a class: both branches assign number before it is read. A final local does not need to be initialized at its declaration line if every path before the read assigns it exactly once.

### 15.1. Fields Having Runtime Default Values Does Not Mean Code Can Read Them Arbitrarily Before Assignment

At the JVM level, fields have **default values** (0, false, null...) before the appropriate initialization steps execute. However, blank final fields must still obey the DA/DU rules of Java source code.

Do not infer that a `final int id;` can be left blank in the constructor and “the compiler automatically uses 0 for it”. This is a common misconception. The compiler requires the code to assign it properly along initialization paths, even though runtime object memory has a temporary default state beforehand.

In good design, do not expose `this` before initialization is finished. If the object is published early, other code can observe an incomplete state under abnormal circumstances; this is not a way to legitimize bypassing DA.

## 16. A Blank final Field Generally Cannot Be Assigned from a Helper Method

An error-prone way to write it:

~~~java
class Wrong {
    private final String id;

    Wrong(String id) {
        initialize(id);
    }

    private void initialize(String id) {
        // this.id = id; // Invalid for a blank final field
    }
}
~~~

Even though `initialize` is only called from the constructor in the programmer's intent, **the compiler does not prove that a final field is assigned by analyzing the side effects of an arbitrary method**, and Java also restricts where a blank final field assignment may occur.

The right way is to have the helper **return a value**, and then the constructor assigns the final field directly:

~~~java
class Correct {
    private final String id;

    Correct(String raw) {
        this.id = validate(raw);
    }

    private static String validate(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException("ID rỗng");
        }
        return raw.trim();
    }
}
~~~

This approach separates responsibilities:

- The helper computes and validates data **without assigning the blank final field**.
- The constructor is responsible for **assigning exactly once**.
- An exception can escape from the helper; if it occurs, the constructor does not complete normally.

**Do not use reflection/Unsafe or runtime tricks to mutate a final field** as a substitute for proper initialization logic. Aside from being error-prone and subject to module/runtime restrictions, they break expectations around immutability and the Java Memory Model.

## 17. The Value Assigned to a final Field Can Be null, a Mutable Object, or a Computed Result

`final` restricts reassignment of **the field**, and does not by itself guarantee other properties.

### 17.1. `final` Does Not Guarantee Non-Null by Itself

~~~java
class Holder {
    final String text;

    Holder() {
        text = null; // Valid under final rules; may not be valid for business logic.
    }
}
~~~

To require non-null, the constructor must check:

~~~java
this.text = java.util.Objects.requireNonNull(value, "value");
~~~

### 17.2. `final` on a Reference Does Not Make the Referenced Object Immutable

~~~java
import java.util.ArrayList;
import java.util.List;

class Cart {
    private final List<String> items;

    Cart() {
        this.items = new ArrayList<>();
    }

    void add(String name) {
        items.add(name);
    }

    List<String> snapshot() {
        return List.copyOf(items);
    }
}
~~~

`items` is assigned only once to point to the ArrayList. However, calls to `items.add(...)` change the **state of the ArrayList object**, not reassign `items`. This is valid behavior when the List is mutable.

### 17.3. A final Array Still Has Mutable Elements

~~~java
class Scores {
    final int[] values;

    Scores() {
        values = new int[]{1, 2};
    }

    void changeFirst() {
        values[0] = 9; // Valid
        // values = new int[]{9}; // Invalid: reassigning final field
    }
}
~~~

To achieve immutable value semantics, you need to guard against aliasing and mutable contents via copying or an immutable representation. `final` is not a deep-freeze.

## 18. `final` Fields and Correctness Under Multiple Threads

Final fields have **special rules in the Java Memory Model (JMM)** that provide a properly constructed object with guarantees regarding the visibility of its final field values after the constructor completes, under certain conditions.

However, **do not overinterpret this**:

- A final field does not by itself make the **mutable object referenced by the field** thread-safe.
- A final field does not protect any other mutable non-final fields of the object.
- You should not let `this` “escape” inside a constructor, because other code could see the object before initialization is finished; this can break initialization safety assumptions.
- Coordinated operations across multiple fields may still require synchronization, immutable snapshots, or another design.

Risky example:

~~~java
class UnsafePublication {
    static UnsafePublication current;

    final String id;

    UnsafePublication(String id) {
        current = this;  // Dangerous: publishing the object before initialization finishes
        this.id = id;
    }
}
~~~

This snippet illustrates a **design problem**, not an example to adopt. From the DA standpoint, the `id` assignment can still satisfy the path where the constructor ends normally; yet the object could be retrieved from `current` by another thread before the final field is assigned. **Definite assignment and safe publication are two different concerns**.

A more appropriate approach is to finish constructing the object and then publish it through a suitable safe mechanism (for example, an immutable holder, synchronized transfer, or concurrent structure), without passing `this` elsewhere in the middle of the constructor.

## 19. Superclass and Subclass Constructors: Each Class Is Responsible for Its Own Fields

Suppose:

~~~java
class Parent {
    final String baseId;

    Parent(String baseId) {
        this.baseId = baseId;
    }
}

class Child extends Parent {
    final int childId;

    Child(String baseId, int childId) {
        super(baseId);
        this.childId = childId;
    }
}
~~~

`Parent` assigns the blank final `baseId` in **Parent's** constructor. `Child` assigns the blank final `childId` in **Child's** constructor.

A subclass cannot arbitrarily change a superclass's blank final after the superclass has initialized. If the superclass wants to let the subclass determine the value, a parameter is typically passed via `super(...)` so the superclass validates and assigns its own field.

### 19.1. An Overridable Method in a Constructor Can Observe Incomplete State

~~~java
class Base {
    Base() {
        show(); // Can dispatch to an override in a subclass!
    }

    void show() {
        System.out.println("Base");
    }
}

class Derived extends Base {
    final String label;

    Derived() {
        this.label = "ready";
    }

    @Override
    void show() {
        System.out.println(label);
    }
}
~~~

If `new Derived()` executes, `Base()` can call the `Derived.show()` override **before** the Derived constructor assigns `label`. Even though `label` is final and the compiler accepts proper initialization in Derived, the early call can observe the default value null in this situation.

Therefore, avoid calling overridable methods from a constructor when they rely on subclass state. Satisfying definite assignment **does not replace** safe initialization-order design.

## 20. `final` Does Not Mean the Field Is Assigned the Same Value on Every Branch

Branches can select **different values**:

~~~java
class Shipping {
    final int fee;

    Shipping(boolean international) {
        if (international) {
            fee = 50;
        } else {
            fee = 10;
        }
    }
}
~~~

The compiler only cares about the assignment rule: every path that completes normally assigns fee exactly once. There is no requirement that both branches assign the same constant or the same expression.

However, branches should uphold the **business contract**. If fee must always be positive or below a limit, validation still needs to be designed. A final field can hold a business-invalid value forever if the constructor assigns the wrong value and completes.

### 20.1. Computing First and Assigning at the End Helps Reduce Errors with Multiple Complex Branches

~~~java
class Price {
    final long amount;

    Price(long base, boolean discount) {
        if (base < 0) {
            throw new IllegalArgumentException("Giá âm");
        }

        long calculated = base;
        if (discount) {
            calculated = Math.subtractExact(base, base / 10);
        }

        amount = calculated;
    }
}
~~~

Using the local `calculated` makes calculation branches easy to extend, while the final field `amount` still has only one assignment at the end of the constructor. For real pricing business logic, you also need to choose an appropriate representation (`BigDecimal`/monetary unit), rounding rules, and separate validation.

## 21. Common Misconceptions

| Misconception | Correct Explanation |
| --- | --- |
| “A final field must be written with `= ...` directly at declaration.” | A blank final can be assigned in an appropriate constructor/initializer |
| “Assigning the final field in just one `if` branch is enough.” | Every initialization path that can end normally must fully assign it |
| “A constructor throwing an exception must still assign all final fields before throwing.” | An abnormal completion path is not a path that creates an object successfully |
| “`return;` in a constructor is like `throw` regarding definite assignment.” | `return;` completes normally and cannot skip assigning a blank final |
| “If already assigned in `if/else`, add a fallback assignment afterward to be safe.” | A second assignment violates the final rule |
| “A constructor where a field initializer `final int x=0` already exists can change `x` to the real value.” | No, the field initializer has already assigned the final field |
| “Every constructor overload must write the field assignment statement itself.” | It can delegate via `this(...)` so the target constructor initializes it |
| “If one constructor is valid, all other overloads are automatically valid.” | Every overload path that completes normally must be valid |
| “A blank static final waits for the first object to be created and is assigned by a constructor.” | No; a static final is initialized in the class's static context |
| “A helper method can assign a blank final on behalf of the constructor and the compiler will infer it.” | Assignment location restrictions and DA do not allow that model |
| “A final String is always non-null.” | Final protects assignment; null is still a valid reference value |
| “A final List cannot be modified.” | A final reference can still point to a mutable List |
| “A final field creates an immutable object.” | You must consider all state, child objects, and aliasing |
| “Because the JVM initializes memory to 0/null, the compiler lets final be left blank.” | No; it must satisfy Java source definite assignment |
| “Final guarantees an object is always thread-safe.” | No; mutable state, publication, and concurrency issues still apply |
| “A superclass constructor can rely on a subclass's final field already being assigned.” | Subclass initialization has not finished when the superclass constructor runs |
| “A static initializer runs every time an object is created.” | Static initialization is a class activity, not per instance |
| “A final field cannot take the result of a complex computation.” | You can compute via locals/helpers and then assign the field once |

## 22. Self-Check Exercises with Answers

**Question 1.** Is the following constructor valid?

~~~java
class Sample {
    final int x;
    Sample(boolean flag) {
        if (flag) x = 1;
        else x = 2;
    }
}
~~~

**Answer:** Yes. Both branches that complete normally assign `x` exactly once.

**Question 2.** What happens if `else x = 2;` is removed?

**Answer:** It does not compile, because `flag == false` can complete the constructor normally while `x` has not been assigned.

**Question 3.** Is `final String name;` assigned `name = null;` in the constructor valid?

**Answer:** Valid with respect to final/definite assignment. However, if the name is not allowed to be null per business rules, the constructor needs separate validation.

**Question 4.** Why can the field `final int x = 10;` not be assigned `x = 20;` in the constructor?

**Answer:** The field initializer has already assigned the final field; the assignment in the constructor would be another assignment.

**Question 5.** Does a constructor with an `if (invalid) throw new IllegalArgumentException();` branch before assigning the final field violate DA?

**Answer:** No, provided every remaining path that completes normally assigns the field according to the rules. The exception-throwing branch does not create an object successfully.

**Question 6.** What happens if `throw` is replaced by `return;` in the invalid branch?

**Answer:** `return;` is a normal completion path of the constructor; if the field has not been assigned, the compiler rejects it.

**Question 7.** Is it necessary to assign `final String id` in every constructor overload even if they call `this(...)`?

**Answer:** Every path that creates an object successfully must have the field assigned exactly once; a constructor delegating via `this(...)` can rely on the target constructor performing a valid assignment.

**Question 8.** Can a blank `static final String ENV` be assigned in the first instance constructor?

**Answer:** No. A static final belongs to the class; assign it in a static initializer/valid initializer of the class itself, not in an instance constructor.

**Question 9.** Why does `final List<String> values` not prevent `values.add("A")`?

**Answer:** Final restricts reassigning the reference field. `add` modifies the state of the referenced List object, without reassigning the field.

**Question 10.** If a static block has `if (flag) ENV = "A";` without an else or fallback branch, is it valid?

**Answer:** No, if there is a static initialization path that completes normally while ENV has not been assigned.

**Question 11.** Can you compute multiple steps using a local variable and then assign the final field once at the end?

**Answer:** Yes; this is usually a clear way to separate computation/validation from the final assignment.

**Question 12.** Why can a superclass constructor calling an overridable method observe a subclass's blank final field as null?

**Answer:** Dynamic dispatch can invoke the subclass's override before the subclass constructor has executed the assignment to that field. Even though the program satisfies definite assignment when the constructor completes, code should not be allowed to observe an object before it is sufficiently initialized.

**Question 13.** Can record components in Java 17 be understood as final fields?

**Answer:** Yes, record components correspond to private final fields in a record; however, records have their own constructors/accessors and rules. A compact constructor lets you validate/normalize parameters, and the compiler assigns the component fields according to record rules after the compact constructor body, not a set of setters.

**Question 14.** Does a `final` field automatically make a class thread-safe?

**Answer:** No. Final fields have important initialization semantics in the Java Memory Model, but mutable child objects, non-final state, this escape, and multi-field operations still require safe synchronization design.

## 23. Java 17 Records: Component Fields Are final, but Constructor Syntax Differs from Ordinary Classes

Java 17 supports **records** to describe data values by components. Example:

~~~java
record UserId(String value) {
    UserId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("ID rỗng");
        }
        value = value.trim();
    }
}
~~~

This is a record's **compact constructor**. It can validate and reassign the **parameter** `value` to normalize it. After the compact constructor body, Java performs the final assignment of component fields from the parameters according to record rules, not a setter.

Therefore, do not take the source code rules of a class with a blank final field and infer that you must write `this.value = value;` in a compact constructor; the compact form has its own mechanism. For a **fully declared canonical constructor** (not using the compact form), setting components must follow the record's constructor rules.

### 23.1. Final Record Components Do Not Mean a Deeply Immutable Object

~~~java
import java.util.List;

record Tags(List<String> values) {
    Tags {
        values = List.copyOf(values);
    }
}
~~~

`values` is a component reference; the corresponding record field is final, yet without copying, a mutable List provided by the caller can be modified outside after the constructor. `List.copyOf` creates an unmodifiable structure, which is suitable here because String elements are immutable.

Similarly, a record containing a mutable object can still be affected through that object without a defensive-copy contract. Do not confuse final fields with deep immutability.

## 24. Checklist When Fixing Compiler Errors Related to Blank Final

When encountering the error “variable might not have been initialized” or “cannot assign a value to final variable”, check:

1. **Is the field instance or static?** A blank instance final belongs to each object; a blank static final belongs to the runtime class.
2. **Is there a field initializer?** If `= ...` is already present at declaration, do not reassign in the constructor/static block.
3. **How many constructor overloads are there?** Is every path that creates an object successfully initialized completely?
4. **Is there constructor chaining `this(...)`?** Does it lead to a constructor that performs valid assignment?
5. **Does any `if/else`, switch, or early return branch omit the field?** Check uncommon input cases as well.
6. **Does the branch stop with `throw` or complete normally?** The two situations have different DA semantics.
7. **Is a final field assigned a second time?** Check field initializer + constructor, and multiple branches followed by a fallback assignment.
8. **Are you trying to assign the blank final inside a helper method?** Have the helper return the data, and assign the field in a location Java allows.
9. **For static final, is it assigned from a constructor?** You must use a static initializer/initializer of the declaring class.
10. **Are you using a loop directly to assign a final field multiple times?** Switch to a local variable and then assign the field once.
11. **Does the field need to be non-null or have a valid value?** DA does not replace validation/invariants.
12. **Does the field reference a mutable object?** Final does not replace defensive copying or an immutable representation.
13. **Are you calling an overridable method or exposing `this` from a constructor?** Avoid observing the object while final state is incomplete.
14. **If the class is a record:** review component/canonical/compact constructor rules instead of mechanically applying ordinary class syntax.
15. **When fixing code:** uncomment error-illustrating examples one case at a time to see precisely where the compiler rejects them; do not guess from runtime and ignore compile-time analysis.

**Conclusion:** A Java **blank final field** must have **a value assigned exactly once on every initialization path that completes normally**. For an instance final field, constructors and instance initializers are responsible; for a static final field, class initialization is where initialization must happen. `if/else`, `switch`, overloaded constructors, and `throw` determine whether the compiler can prove the definite assignment/definite unassignment rules. After successful assignment, final prevents reassigning the field, yet **does not by itself guarantee non-null, business validity, deep immutability, or thread safety**. The clearest design approach is usually to **validate/compute into local variables, and then assign final fields once** at the appropriate initialization boundary.
