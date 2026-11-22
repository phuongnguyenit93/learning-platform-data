# Enum Constant Declarations and Individual Constant Identity in Java 17

In Java, **`enum`** is a special reference data type used to model a **finite set of named values**. Each value declared in the enum constant list is **a distinct object** of that enum type; that object has its own **identity** and is initialized by the JVM according to the rules of the enum type.

Example:

```java
enum TrafficLight {
    RED, YELLOW, GREEN
}
```

Here:
- `TrafficLight` is **an enum type**, not three variables of type `String`.
- `TrafficLight.RED`, `TrafficLight.YELLOW`, `TrafficLight.GREEN` are **three enum constants**, each representing a different enum instance.
- `TrafficLight.RED == TrafficLight.RED` is `true` because it is the same enum constant reference.
- `TrafficLight.RED == TrafficLight.GREEN` is `false` because they are two constants with different identities.
- `TrafficLight.RED.name()` is `"RED"`, the declared name of the constant; `name()` is not the enum object itself.
- `TrafficLight.RED.ordinal()` is `0` because RED is declared first; **ordinal is not a stable business identifier**.

A very important summary sentence:

> **An enum constant has identity via the constant's own object reference, whereas its name and declaration position are properties of the constant, not object identity.**

This lesson belongs to Java Core — Class/Object, for **Java 17+**. It covers constant declaration syntax, constructors and fields, identity/`==`/`equals`, `name()`/`ordinal()`/`toString()`, `values()`/`valueOf()`, initialization order, constant-specific class bodies, interfaces, `switch`, `EnumSet`/`EnumMap`, serialization/reflection, nested/local enums, concurrency, designing business identifiers, common pitfalls, runnable examples, and exercises with answers.

## 1. Why Use enum Instead of String or int?

Suppose an order status is stored as a String:

```java
String status = "PAID";
```

A method that accepts a String can mistakenly be passed `"PAYD"`, `"paid"`, or `"UNKNOWN"`. The compiler cannot prevent those naming mistakes.

With an enum:

```java
enum OrderStatus {
    NEW, PAID, SHIPPED, CANCELLED
}

OrderStatus status = OrderStatus.PAID;
```

The compiler knows `status` must be an `OrderStatus`, not an arbitrary String. To add a status, the developer updates the enum declaration itself.

Benefits:
- Type safety: constants belong strictly to the declared type.
- Clear names, with autocomplete and refactoring support.
- Comparing identity with `==` is safe in normal situations.
- `switch` can express behavior per constant.
- Can declare fields, methods, constructors, and implement interfaces.
- The JDK has enum-optimized collections such as `EnumSet` and `EnumMap`.

**Not every finite set of data should use an enum.** If values are user-configured, continuously added, or have a dynamic lifecycle from a database, a registry/domain entity may be more appropriate.

## 2. Minimal Syntax of an Enum

```java
enum Day {
    MONDAY,
    TUESDAY,
    WEDNESDAY,
    THURSDAY,
    FRIDAY,
    SATURDAY,
    SUNDAY
}
```

The identifiers between `{` and `}` are separated by commas. Each identifier is the name of an **enum constant**.

Writing a reference:

```java
Day today = Day.MONDAY;
```

Do not declare enum constants manually as static fields:

```java
// Not enum syntax:
enum Day {
    // public static final Day MONDAY = new Day();
}
```

In the enum constant list, the `MONDAY` syntax is already handled specially by Java. Constants are provided as **public static final fields** of the enum type according to the language semantics; developers do not write `new Day()` themselves to create a constant.

### The `;` Semicolon When Members Are Present

If there are only constants, the semicolon may be omitted:

```java
enum Color {
    RED, BLUE
}
```

If fields, constructors, or methods follow the constant list, end the constant list with `;`:

```java
enum Color {
    RED, BLUE;

    String describe() {
        return name().toLowerCase(java.util.Locale.ROOT);
    }
}
```

### The Constant List Must Appear Before Regular Members

Do not place a method declaration before `RED` and `BLUE`. Enum constant declarations are a special section at the beginning of the enum body.

## 3. Runnable: Declaring and Using the First Constants

Save **`BasicEnumDemo.java`**:

```java
enum Direction {
    NORTH, EAST, SOUTH, WEST
}

public class BasicEnumDemo {
    public static void main(String[] args) {
        Direction current = Direction.NORTH;

        System.out.println(current);
        System.out.println(current == Direction.NORTH);
        System.out.println(current == Direction.SOUTH);
        System.out.println(Direction.WEST.name());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 BasicEnumDemo.java
java BasicEnumDemo
```

**Exact stdout:**

```text
NORTH
true
false
WEST
```

`System.out.println(current)` calls `toString()`; if the enum does not override it, `Enum.toString()` returns the constant name just like `name()` by default. That does not mean an enum is a String.

## 4. An Enum Is a Reference Type, Not a Primitive

`Direction` is an enum type and belongs to Java's reference type system. A `Direction` variable holds a reference to one of the enum constants, or `null`.

Example:

```java
Direction a = Direction.NORTH;
Direction b = a;
```

`b = a` **does not clone or create a new NORTH**; the two references point to the exact same constant object.

`a == b` is true.

An enum variable can still be null:

```java
Direction unknown = null;
System.out.println(unknown == Direction.NORTH); // false
```

However:

```java
// unknown.name(); // NullPointerException at runtime.
```

**Enums do not automatically eliminate null from every API.** If you want a field to always be non-null, check the invariant in the constructor, setter, or data input boundary. `Objects.requireNonNull` can help express the contract.

## 5. Identity of an Enum Constant

Within the scope of an enum class loaded and initialized in a Java runtime, each constant is represented by a **canonical instance** provided by the enum mechanism.

Given a reference to `Direction.NORTH`, anywhere accessing the same constant of that same enum type receives the same reference identity.

```java
Direction first = Direction.NORTH;
Direction second = Direction.valueOf("NORTH");

System.out.println(first == second); // true
```

Do not misinterpret "each constant has only one instance" as "there is only one enum object in the entire world." There is **one object for each declared constant in the corresponding enum class**. Constants with different names have different objects. Details such as class-loader identity can also affect how a Java type is identified across different loaders/runtimes.

### Identity Differs from Ordinary Value Equality

With a `Person` class, two objects with equal fields can still have different references:

```java
new Person("A") != new Person("A")
```

With an enum, a developer cannot arbitrarily create a second `Direction.NORTH` object using a constructor. Therefore, comparison by reference identity aligns with the very **set of constant instances** declared by the enum.

## 6. Runnable: Three Variables but Only Two Constants

Save **`EnumIdentityDemo.java`**:

```java
enum AccessLevel {
    GUEST, ADMIN
}

public class EnumIdentityDemo {
    public static void main(String[] args) {
        AccessLevel one = AccessLevel.ADMIN;
        AccessLevel two = AccessLevel.ADMIN;
        AccessLevel three = AccessLevel.GUEST;

        System.out.println(one == two);
        System.out.println(one == three);
        System.out.println(two.equals(one));
        System.out.println(one.getClass() == AccessLevel.class);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumIdentityDemo.java
java EnumIdentityDemo
```

Stdout:

```text
true
false
true
true
```

In this example there is no constant-specific class body, so the runtime class of ADMIN is `AccessLevel.class` itself. Later on, when each constant has its own body, you need to use `getDeclaringClass()` if the goal is to determine the **enum type** of the constant.

## 7. Should You Use `==` or `equals()` for Enums?

**Recommendation:** compare two enum constants of the same type using `==` or `!=`:

```java
if (status == OrderStatus.PAID) {
    // ...
}
```

Reasons:
- Enum constants have canonical identity.
- `Enum.equals(Object)` is final and based on reference identity.
- `==` does not throw a `NullPointerException` when one operand is null.
- The compiler checks reference type compatibility in the comparison.

`status.equals(OrderStatus.PAID)` also produces the right result when status is non-null, but carries the added risk of an NPE if status is null.

**Do not use `==` to compare Strings**. Two String objects can have the same contents yet different references; enums differ because their set of constants is managed by the enum mechanism.

### Can You Override `equals` or `hashCode` on an Enum?

No. `java.lang.Enum` defines `equals` and `hashCode` as final. You are not allowed to replace an enum's identity semantics with a field-based equality policy.

If the problem requires two objects with the same business code to be considered equal regardless of when they were created, an immutable record/value object may be more suitable than an enum.

## 8. Runnable: `==`, `equals`, and null

Save **`EnumComparisonDemo.java`**:

```java
enum State {
    OPEN, CLOSED
}

public class EnumComparisonDemo {
    public static void main(String[] args) {
        State state = State.OPEN;
        State missing = null;

        System.out.println(state == State.OPEN);
        System.out.println(state.equals(State.OPEN));
        System.out.println(state == State.CLOSED);
        System.out.println(missing == State.OPEN);
        System.out.println(State.OPEN.equals(missing));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumComparisonDemo.java
java EnumComparisonDemo
```

Stdout:

```text
true
true
false
false
false
```

This source code does not call `missing.equals(...)`, because that behavior is a NullPointerException, not false.

## 9. Two Enum Types with Constants of the Same Name Are Still Different

```java
enum OrderState {
    OPEN, CLOSED
}

enum TicketState {
    OPEN, CLOSED
}
```

`OrderState.OPEN` and `TicketState.OPEN` both have the name `"OPEN"` but belong to **two independent enum types**.

This means:
- You cannot assign `TicketState.OPEN` to an `OrderState` variable.
- You cannot compare them directly with `==` when the two operand types cannot be validly converted to perform reference equality according to the type rules.
- `OrderState.OPEN.equals(TicketState.OPEN)` is valid because `equals(Object)` accepts Object, but it returns **false**.
- The same `name()` does not make two constants have the same identity.

### Runnable

Save **`SameNameDifferentEnumsDemo.java`**:

```java
enum OrderState {
    OPEN, CLOSED
}

enum TicketState {
    OPEN, CLOSED
}

public class SameNameDifferentEnumsDemo {
    public static void main(String[] args) {
        System.out.println(OrderState.OPEN.name());
        System.out.println(TicketState.OPEN.name());
        System.out.println(
                OrderState.OPEN.equals(TicketState.OPEN));
        System.out.println(
                OrderState.OPEN.getDeclaringClass()
                == TicketState.OPEN.getDeclaringClass());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 SameNameDifferentEnumsDemo.java
java SameNameDifferentEnumsDemo
```

Stdout:

```text
OPEN
OPEN
false
false
```

The enum type is also an indispensable part of a constant's identity, even when the display labels are the same.

## 10. `name()`: The Declared Name of the Constant

Each enum constant has its name exposed by the final method `name()`:

```java
Direction.NORTH.name() // "NORTH"
```

This name is the **exact identifier used in the source declaration**. It is how machines read the constant by name, but it also introduces risk if the name is stored as an external identifier and the developer later renames the source constant.

Characteristics:
- `name()` returns a String, not the enum object.
- `name()` cannot be overridden: it is final.
- If a constant is renamed from `PAID` to `SETTLED`, `name()` changes; old persisted data needs migration/mapping.
- `name()` is usually suitable for operations that want to identify constants by their current declaration.
- `name()` should not be used by default as a multilingual UI label.

### `name()` Differs from `toString()`

An enum's default `toString()` returns the constant name, but it can be **overridden** to produce a human-friendly label. `name()` cannot be overridden.

## 11. `ordinal()`: Declaration Position, Not an ID Code

`ordinal()` is a final method that returns the zero-based position of the constant in declaration order.

```java
enum Size {
    SMALL, MEDIUM, LARGE
}
```

Values:
- `SMALL.ordinal() == 0`.
- `MEDIUM.ordinal() == 1`.
- `LARGE.ordinal() == 2`.

Important warning:

> **Do not use ordinal as a database code, public API code, or stable protocol field.**

Inserting a new constant at the beginning of an enum changes the ordinals of all subsequent constants. Declaration order usually reflects the natural order of the enumeration, not a stable business key.

If a durable code is needed, define a separate, explicitly chosen field.

## 12. Runnable: `name` and `ordinal`

Save **`EnumNameOrdinalDemo.java`**:

```java
enum Priority {
    LOW, NORMAL, HIGH
}

public class EnumNameOrdinalDemo {
    public static void main(String[] args) {
        for (Priority priority : Priority.values()) {
            System.out.println(priority.name()
                    + ":" + priority.ordinal());
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumNameOrdinalDemo.java
java EnumNameOrdinalDemo
```

Stdout:

```text
LOW:0
NORMAL:1
HIGH:2
```

If the enum declaration order changes, the ordinal output changes accordingly. `ordinal()` has a specific purpose in order-based/optimization mechanisms such as `EnumSet`/`EnumMap`, but applications should not turn it into a business identity by default.

## 13. `toString()` Can Be a Display Name, Not the Source Name

You can write:

```java
enum PaymentStatus {
    PENDING, SUCCESS;

    @Override
    public String toString() {
        return switch (this) {
            case PENDING -> "Đang chờ";
            case SUCCESS -> "Thành công";
        };
    }
}
```

`PaymentStatus.SUCCESS.name()` is still `"SUCCESS"`; `toString()` returns `"Thành công"`.

**Do not rely on `toString()` as a serialization ID** if its purpose is a UI label; later changes to language, copywriting, or formatting will break compatibility.

### Runnable

Save **`EnumStringDemo.java`**:

```java
enum ResultStatus {
    OK, FAIL;

    @Override
    public String toString() {
        return this == OK ? "Thành công" : "Thất bại";
    }
}

public class EnumStringDemo {
    public static void main(String[] args) {
        ResultStatus value = ResultStatus.OK;

        System.out.println(value.name());
        System.out.println(value.toString());
        System.out.println(value == ResultStatus.OK);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumStringDemo.java
java EnumStringDemo
```

Stdout:

```text
OK
Thành công
true
```

Identity does not depend on the contents of `toString()`. Changing the label `"Thành công"` to `"Hoàn tất"` still does not create a new constant object.

## 14. `values()`: Retrieving All Constants in Declaration Order

For an enum `Color`, the compiler provides the `Color.values()` method, which returns an array containing the enum constants in declaration order.

```java
Color[] all = Color.values();
```

Key points to remember:
- It is a **new array** on each call per the API contract.
- The elements in the array are **references to the canonical enum constant objects**, not deep copies.
- The order of elements is the declaration order.
- Modifying elements of the array you receive **does not modify the list of enum constants** of the type.
- The array can contain all constants even though there is no logic creating each constant anew when `values()` is called.

### Distinguishing Two Kinds of Identity

```java
Color[] a = Color.values();
Color[] b = Color.values();
```

`a == b` is false because the two array objects are different. However, `a[0] == b[0]` is true when both hold the first constant.

**A new array does not mean new enum constants.**

## 15. Runnable: New Array, Old Constants

Save **`EnumValuesIdentityDemo.java`**:

```java
enum Color {
    RED, GREEN, BLUE
}

public class EnumValuesIdentityDemo {
    public static void main(String[] args) {
        Color[] one = Color.values();
        Color[] two = Color.values();

        System.out.println(one == two);
        System.out.println(one[0] == two[0]);

        one[0] = Color.BLUE;

        System.out.println(two[0]);
        System.out.println(Color.values()[0]);
        System.out.println(Color.values().length);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumValuesIdentityDemo.java
java EnumValuesIdentityDemo
```

Stdout:

```text
false
true
RED
RED
3
```

Assigning `one[0] = Color.BLUE` only changes the reference inside array `one`. The constant `Color.RED` still exists, and other calls to `values()` still return the original list.

## 16. `valueOf(String)`: Mapping Constant Name to Object Identity

For enum `Color`:

```java
Color red = Color.valueOf("RED");
```

The compiler generates the `Color.valueOf(String)` method to look up the constant with the **exact declared name**. The returned value is **the canonical constant itself**, not a copy.

`Color.valueOf("RED") == Color.RED` is true.

Errors to be aware of:
- Name does not match, for example `"red"`: `IllegalArgumentException`.
- A `null` string: `NullPointerException`.
- Constant names are case-sensitive.
- `valueOf` does not look up by `toString()`; a UI label is not synonymous with the enum name.
- If external data is untrusted, you need to validate/handle errors.

You also have the generic overload `Enum.valueOf(Color.class, "RED")`, which is useful when the enum type is a `Class<T>` passed into a generic API.

## 17. Runnable: `valueOf` Preserves Identity and Handles Errors

Save **`EnumValueOfDemo.java`**:

```java
enum Channel {
    EMAIL, SMS
}

public class EnumValueOfDemo {
    public static void main(String[] args) {
        Channel fromName = Channel.valueOf("EMAIL");
        Channel generic = Enum.valueOf(
                Channel.class, "SMS");

        System.out.println(fromName == Channel.EMAIL);
        System.out.println(generic == Channel.SMS);

        try {
            Channel.valueOf("email");
        } catch (IllegalArgumentException error) {
            System.out.println("invalid-name");
        }

        try {
            Channel.valueOf(null);
        } catch (NullPointerException error) {
            System.out.println("null-name");
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumValueOfDemo.java
java EnumValueOfDemo
```

Stdout:

```text
true
true
invalid-name
null-name
```

We do not print the exception message directly because the message text is not a suitable contract for fixed stdout in this lesson; we only verify the exception types.

## 18. Constructors and Data Specific to Each Enum Constant

Enums are not limited to parameterless constants. You can pass arguments to the enum constructor directly in the constant declaration:

```java
enum HttpStatus {
    OK(200),
    NOT_FOUND(404);

    private final int code;

    HttpStatus(int code) {
        this.code = code;
    }

    int code() {
        return code;
    }
}
```

Each constant is **a separate enum object** whose `code` is initialized differently. The names `OK` and `NOT_FOUND` remain the enum identities; the `code` field is **associated data**.

### What Is Special About an Enum Constructor?

- You cannot arbitrarily create an instance with `new HttpStatus(200)` from application source.
- Enum constructors have restricted access: you can write `private` or omit the modifier; they cannot be public/protected.
- Only enum constants at the top of the enum declaration use these constructors during constant creation.
- If no constructor is declared, Java provides an appropriate constructor according to the enum rules.
- Constructors can be overloaded.
- If an enum constant carries an argument list `(…)`, the compiler selects the matching constructor.
- An enum constructor cannot be used to create an unbounded set of "new instances" like a regular class constructor.

**Boundary:** outside the source declaration, users work with the existing constant objects.

## 19. Runnable: Enum Constants Carrying Properties and Stable Codes

Save **`EnumConstructorDemo.java`**:

```java
enum HttpStatus {
    OK(200, "Thành công"),
    BAD_REQUEST(400, "Yêu cầu không hợp lệ"),
    NOT_FOUND(404, "Không tìm thấy");

    private final int code;
    private final String message;

    HttpStatus(int code, String message) {
        this.code = code;
        this.message = message;
    }

    int code() {
        return code;
    }

    String message() {
        return message;
    }
}

public class EnumConstructorDemo {
    public static void main(String[] args) {
        HttpStatus status = HttpStatus.NOT_FOUND;

        System.out.println(status.name());
        System.out.println(status.code());
        System.out.println(status.message());
        System.out.println(status == HttpStatus.NOT_FOUND);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumConstructorDemo.java
java EnumConstructorDemo
```

Stdout:

```text
NOT_FOUND
404
Không tìm thấy
true
```

`code=404` is the domain/HTTP code of the NOT_FOUND constant; `ordinal()` of NOT_FOUND is 2 in the current source. **404 and 2 must not be mixed up.**

### Should You Use final Fields?

If a field is state describing the constant, `private final` ensures every constant object has its attributes assigned in the constructor and cannot be arbitrarily reassigned by other code. However, a final reference to a mutable object can still point to a mutable referent; make a defensive copy when necessary.

## 20. Constants with the Same Field Value Still Have Different Identities

Two constants with different names are still two different instances, even when constructor arguments match:

```java
enum AliasCode {
    PRIMARY(1),
    SECONDARY(1);

    final int code;

    AliasCode(int code) {
        this.code = code;
    }
}
```

`AliasCode.PRIMARY.code == AliasCode.SECONDARY.code` is true.

But `AliasCode.PRIMARY == AliasCode.SECONDARY` is false.

This shows that **identity is not the result of comparing field values**. The enum constant name/declaration defines two independent members.

If the domain requires a code to map uniquely to one constant, **you must perform validation yourself** in your design/mapping code; Java does not automatically prohibit two enum constants from having the same field value.

## 21. Runnable: Two Constants with the Same Code

Save **`EnumSameFieldDifferentIdentityDemo.java`**:

```java
enum Code {
    FIRST(10),
    SECOND(10),
    THIRD(20);

    private final int numeric;

    Code(int numeric) {
        this.numeric = numeric;
    }

    int numeric() {
        return numeric;
    }
}

public class EnumSameFieldDifferentIdentityDemo {
    public static void main(String[] args) {
        System.out.println(Code.FIRST.numeric()
                == Code.SECOND.numeric());
        System.out.println(Code.FIRST == Code.SECOND);
        System.out.println(Code.FIRST.equals(Code.SECOND));
        System.out.println(Code.FIRST.ordinal());
        System.out.println(Code.SECOND.ordinal());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumSameFieldDifferentIdentityDemo.java
java EnumSameFieldDifferentIdentityDemo
```

Stdout:

```text
true
false
false
0
1
```

If you want to use the `numeric` field as a lookup key, you must decide how to handle duplicate codes when they occur; do not assume the compiler has proven uniqueness.

## 22. No public/protected Enum Constructors

The following snippet **intentionally does not compile**:

```java
enum Invalid {
    ONE(1);

    public Invalid(int code) {
    }
}
```

An enum constructor cannot be public. Likewise, `protected Invalid(...)` is not allowed.

Write:

```java
enum Valid {
    ONE(1);

    private final int code;

    Valid(int code) {
        this.code = code;
    }
}
```

or add `private` to the constructor as needed.

**Do not fix it by using `new Valid(1)` elsewhere.** The enum type deliberately restricts construction to keep the set of constants fixed according to the declaration.

### Additionally: An Enum Cannot Declare an Arbitrary Constructor Calling `super(...)`

An enum extends `java.lang.Enum<E>` by language rules, with a special mechanism for the name/ordinal. The programmer does not directly call the Enum constructor or manually pass the name/ordinal.

## 23. Initialization Order of Enum Constants

Enum constants are static fields initialized during **class initialization**, in the order they appear in the declaration before regular static initializers/fields in the enum body are processed according to the applicable rules.

Example:

```java
enum Stage {
    FIRST(1),
    SECOND(2);

    Stage(int id) {
        System.out.println("construct:" + name() + ":" + id);
    }

    static {
        System.out.println("static-block");
    }
}
```

In a program that triggers initialization of `Stage`, you can predict the printed lines from FIRST's constructor, SECOND's constructor, and then the static initializer.

Important points:
- **Each enum constant object is initialized once when the enum class is initialized** (within the specific class initialization context).
- Accessing `Stage.FIRST` multiple times does not re-run the constructor.
- Calling `Stage.values()` multiple times does not recreate enum constants either.
- There is no need to create the first enum instance via a manual `new` call.
- Static initialization of the enum is a separate step from using the objects later.

## 24. Runnable: Observing Construction Order

Save **`EnumInitializationDemo.java`**:

```java
enum Stage {
    FIRST(1),
    SECOND(2),
    THIRD(3);

    private final int id;

    Stage(int id) {
        this.id = id;
        System.out.println("construct:" + name() + ":" + id);
    }

    static {
        System.out.println("static-block");
    }

    int id() {
        return id;
    }
}

public class EnumInitializationDemo {
    public static void main(String[] args) {
        System.out.println("before");
        System.out.println(Stage.SECOND.id());
        System.out.println(Stage.FIRST.id());
        System.out.println(Stage.SECOND.id());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumInitializationDemo.java
java EnumInitializationDemo
```

Stdout:

```text
before
construct:FIRST:1
construct:SECOND:2
construct:THIRD:3
static-block
2
1
2
```

Even though the caller first accesses `Stage.SECOND`, Java initializes **all enum constants in declaration order**: FIRST, SECOND, THIRD. Subsequent accesses do not run the constructors again.

### A Pitfall in Enum Constructors

Avoid directly referencing **a non-constant static field of the enum itself** inside a constructor/instance initializer. Java has compile-time restrictions to prevent cases where partially initialized enum state is read. If a lookup map of enum values is needed, it is usually built after the constants have been created, for example in a static initializer.

## 25. Overloaded Constructors in an Enum

An enum can have overloaded constructors:

```java
enum Severity {
    LOW,
    HIGH(10);

    private final int weight;

    Severity() {
        this(1);
    }

    Severity(int weight) {
        this.weight = weight;
    }

    int weight() {
        return weight;
    }
}
```

- `LOW` uses the no-arg constructor, then performs constructor chaining to `Severity(int)`.
- `HIGH(10)` uses the constructor taking `int`.
- `LOW` and `HIGH` are still two constants with distinct identities.
- Constructor chaining with `this(...)` happens inside the enum's constructors; there is no `new Severity()` outside the declaration.

### Runnable

Save **`EnumConstructorOverloadDemo.java`**:

```java
enum Severity {
    LOW,
    HIGH(10);

    private final int weight;

    Severity() {
        this(1);
    }

    Severity(int weight) {
        this.weight = weight;
    }

    int weight() {
        return weight;
    }
}

public class EnumConstructorOverloadDemo {
    public static void main(String[] args) {
        System.out.println(Severity.LOW.weight());
        System.out.println(Severity.HIGH.weight());
        System.out.println(Severity.LOW == Severity.HIGH);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumConstructorOverloadDemo.java
java EnumConstructorOverloadDemo
```

Stdout:

```text
1
10
false
```

If you want clear defaults in the API, overloading can help; however, do not create too many ambiguous constructor signatures that make constant declarations hard to read.

## 26. Constant-Specific Class Bodies Do Not Change Identity

A constant can have a *constant-specific class body* to override behavior, yet it is still **that exact named constant**, not a way to create new enum instances on demand. Example:

~~~java
enum Operation {
    ADD { @Override int apply(int a, int b) { return a + b; } },
    MULTIPLY { @Override int apply(int a, int b) { return a * b; } };

    abstract int apply(int a, int b);
}
~~~

This is a valid enum declaration, without `main` yet. `ADD != MULTIPLY`, and each constant still keeps its `name()` and `ordinal()` as declared. **An easily overlooked identity detail:** with a constant-specific body, `Operation.ADD.getClass()` can differ from `Operation.class`, whereas `Operation.ADD.getDeclaringClass() == Operation.class` is always true. This belongs to the compiler-managed anonymous subclass mechanism and does not make the enum an open set.

The next runnable example tests behavior and identity; a dedicated lesson on **constant-specific bodies** covers abstract methods, shared implementation, visibility, and choosing between them and `switch`.

## 27. Runnable: Per-Constant Behavior and Identity

Save **`EnumConstantBodyDemo.java`**:

```java
enum Operation {
    ADD("+") {
        @Override
        int apply(int a, int b) {
            return a + b;
        }
    },
    MULTIPLY("*") {
        @Override
        int apply(int a, int b) {
            return a * b;
        }
    };

    private final String symbol;

    Operation(String symbol) {
        this.symbol = symbol;
    }

    String symbol() {
        return symbol;
    }

    abstract int apply(int a, int b);
}

public class EnumConstantBodyDemo {
    public static void main(String[] args) {
        Operation add = Operation.ADD;
        Operation multiply = Operation.MULTIPLY;

        System.out.println(add.apply(3, 4));
        System.out.println(multiply.apply(3, 4));
        System.out.println(add.symbol());
        System.out.println(add.name());
        System.out.println(add == Operation.ADD);
        System.out.println(add.getClass() == Operation.class);
        System.out.println(
                add.getDeclaringClass() == Operation.class);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumConstantBodyDemo.java
java EnumConstantBodyDemo
```

Stdout:

```text
7
12
+
ADD
true
false
true
```

Each constant passes `symbol` to the enum constructor and overrides `apply` with its own behavior. `Operation.ADD` remains a fixed constant, even though a runtime subclass is used to implement its specific behavior.

## 28. Constant-Specific Bodies and the `toString()` Method

A constant can override `toString()` individually:

```java
enum Format {
    JSON {
        @Override
        public String toString() {
            return "application/json";
        }
    },
    TEXT {
        @Override
        public String toString() {
            return "text/plain";
        }
    }
}
```

`Format.JSON.name()` is still `"JSON"`; `Format.JSON.toString()` returns `"application/json"`.

However, **you cannot override `name()`**, `ordinal()`, `equals`, or `hashCode` because the corresponding methods in `Enum` are final.

### An Easy Design Mistake to Make

If a serializer uses `toString()` as an identifier, a UI change can break data. Use an explicit stable code if that is the contract, and use `name()` when you truly accept coupling to the source identifier.

## 29. Interfaces Do Not Erase Enum Constant Identity

An enum can `implements` an interface even though it cannot explicitly `extends` any class. A reference of the interface type still preserves **the original constant object**:

~~~java
interface Labelled {
    String label();
}

enum Status implements Labelled {
    ACTIVE, SUSPENDED;
    @Override
    public String label() {
        return name().toLowerCase(java.util.Locale.ROOT);
    }
}
~~~

These are valid declarations. `Labelled label = Status.ACTIVE;` invokes the method through the interface API, yet the referenced object is still `Status.ACTIVE`. Enum constant-specific methods can implement different behaviors under the same contract.

The focus here is **canonical identity remaining invariant across upcasting**. The lesson `Enums Implementing Interfaces` goes deep into default methods, multiple/generic interfaces, `Predicate`, `Function`, `Comparator`, and contract testing.

## 30. Runnable: Enums and Interfaces

Save **`EnumInterfaceDemo.java`**:

```java
interface Command {
    String execute(String input);
}

enum CommandType implements Command {
    UPPER {
        @Override
        public String execute(String input) {
            return input.toUpperCase(
                    java.util.Locale.ROOT);
        }
    },
    WRAP {
        @Override
        public String execute(String input) {
            return "[" + input + "]";
        }
    }
}

public class EnumInterfaceDemo {
    public static void main(String[] args) {
        Command first = CommandType.UPPER;
        Command second = CommandType.WRAP;

        System.out.println(first.execute("java"));
        System.out.println(second.execute("java"));
        System.out.println(first == CommandType.UPPER);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumInterfaceDemo.java
java EnumInterfaceDemo
```

Stdout:

```text
JAVA
[java]
true
```

An enum constant can be passed through the `Command` interface, while its identity with `CommandType.UPPER` is still preserved when the reference is assigned to an interface variable.

## 31. `switch` Branches Based on Declared Constants

If `status` has enum type `OrderStatus` with constants `NEW`, `PAID`, `SHIPPED`, `CANCELLED`, you can branch directly on **constant identity**, rather than manually comparing String names:

~~~java
String label = switch (status) {
    case NEW -> "New";
    case PAID -> "Paid";
    case SHIPPED -> "Shipped";
    case CANCELLED -> "Cancelled";
};
~~~

This is a Java 17 snippet requiring `status` to be declared. The compiler checks case labels and branch exhaustiveness of the switch expression; for a null selector, an enum switch in standard Java 17 throws an NPE. In this code, `case NEW` uses the constant name **without a qualifier** per Java 17 syntax.

The lesson on `==` and `switch` will thoroughly practice colon/arrow forms, fall-through, `yield`, null, exhaustiveness, and trade-offs with polymorphism. The current section only shows that enums are used directly according to their typed identity.

## 32. Runnable: switch Expression Over an Enum

Save **`EnumSwitchDemo.java`**:

```java
enum OrderStatus {
    NEW, PAID, SHIPPED, CANCELLED
}

public class EnumSwitchDemo {
    static String label(OrderStatus status) {
        return switch (status) {
            case NEW -> "new";
            case PAID -> "paid";
            case SHIPPED -> "shipped";
            case CANCELLED -> "cancelled";
        };
    }

    public static void main(String[] args) {
        System.out.println(label(OrderStatus.NEW));
        System.out.println(label(OrderStatus.SHIPPED));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumSwitchDemo.java
java EnumSwitchDemo
```

Stdout:

```text
new
shipped
```

An enum constant has a unique identity; switch selects the branch according to the enum value. There is no need to manually build a `String→int ordinal` table for branching.

## 33. `EnumSet` Works with Sets of Canonical Constants

`EnumSet<Role>` is a `Set` specialized for an enum type; its elements remain **the enum constants themselves**, not clones:

~~~java
java.util.EnumSet<Role> roles =
        java.util.EnumSet.of(Role.READER, Role.WRITER);
~~~

This is a snippet requiring an enum `Role` containing `READER`, `WRITER`. `EnumSet` does not allow nulls/duplicates and iterates in enum declaration order rather than insertion order. When creating an empty set, `EnumSet.noneOf(Role.class)` explicitly states the type; `copyOf` from an empty collection that is not an `EnumSet` may lack type information to infer it.

This lesson only observes the **canonical** nature of the members. The next runnable example demonstrates collection behavior; avoid equating a set of references with creating new constant objects.

## 34. Runnable: EnumSet Preserves Constants and Declaration Order

Save **`EnumSetDemo.java`**:

```java
import java.util.EnumSet;

enum Permission {
    READ, WRITE, EXECUTE
}

public class EnumSetDemo {
    public static void main(String[] args) {
        EnumSet<Permission> set =
                EnumSet.of(Permission.EXECUTE, Permission.READ);

        System.out.println(set);
        System.out.println(set.contains(Permission.READ));

        set.add(Permission.WRITE);

        for (Permission permission : set) {
            System.out.println(permission.name());
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumSetDemo.java
java EnumSetDemo
```

Stdout:

```text
[READ, EXECUTE]
true
READ
WRITE
EXECUTE
```

Even though `of(EXECUTE, READ)` was called, `EnumSet` iteration follows declaration order, not insertion order. This is a useful characteristic, but **do not use it to encode a changeable business ordering** if an independent explicit ordering is needed.

## 35. `EnumMap` Uses Enum Constants as Typed Keys

`EnumMap<Role, String>` associates values with keys that are **the canonical enum constants**; it does not create additional constants or equate two constants merely because they share a similar field/label.

~~~java
java.util.EnumMap<Role, String> labels =
        new java.util.EnumMap<>(Role.class);
labels.put(Role.READER, "Read");
~~~

This is a snippet requiring `Role` to be declared. `EnumMap` does not permit null keys, can allow null values, and iterates over keys in declaration order. Use it when a data-driven lookup table is needed; use switch if a small branching construct is clearer; use an enum method if the behavior truly belongs to the constant.

The next program proves that the keys are still **the constants themselves**; there is no need to view `EnumMap` as a factory or an identity-changing mechanism.

## 36. Runnable: EnumMap

Save **`EnumMapDemo.java`**:

```java
import java.util.EnumMap;

enum Phase {
    START, RUNNING, DONE
}

public class EnumMapDemo {
    public static void main(String[] args) {
        EnumMap<Phase, String> messages =
                new EnumMap<>(Phase.class);

        messages.put(Phase.DONE, "complete");
        messages.put(Phase.START, "begin");
        messages.put(Phase.RUNNING, "work");

        for (var entry : messages.entrySet()) {
            System.out.println(entry.getKey().name()
                    + "=" + entry.getValue());
        }

        System.out.println(
                messages.get(Phase.DONE));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumMapDemo.java
java EnumMapDemo
```

Stdout:

```text
START=begin
RUNNING=work
DONE=complete
complete
```

Iteration order does not depend on insertion order; it follows the declaration order of `Phase`.

## 37. `ordinal` and Ordering Constants

`Enum` implements `Comparable` with the natural order being the **declaration order** of constants of the same enum type. Therefore, `compareTo` uses ordinal-based ordering.

`Priority.LOW.compareTo(Priority.HIGH)` is negative if LOW is declared before HIGH.

Things to distinguish:
- Using declaration order as the natural order when **it is truly the domain order** can be reasonable.
- Using ordinal as a **stored/persisted ID** is unsafe when the declaration may change.
- If you want a priority score different from declaration order, add a separate `rank` field.
- `EnumSet`/`EnumMap` iterate in declaration order even if the caller adds keys in a different order.

### If Business Ordering Differs from ordinal

Use `Comparator.comparingInt(Priority::rank)` or an explicit rule. Do not reorder enum constants just to change a UI rank if doing so affects ordering elsewhere.

## 38. Business Codes Are Properties, Not Constant Identity

When an enum constant needs a stable **external code**, declare a separate field:

~~~java
enum InvoiceState {
    DRAFT("D"), APPROVED("A"), REJECTED("R");

    private final String code;
    InvoiceState(String code) { this.code = code; }
    String code() { return code; }
}
~~~

This is a valid declaration. Changing a constant's position does not automatically change the code `"A"`; however, two constants can still accidentally carry the same code, because the compiler does not check the uniqueness of that field.

**Distinguish the two contracts:** `InvoiceState.APPROVED` is the canonical enum object; `"A"` is a value that can be sent to a DB/API under a contract defined by the application. The next example proves that `fromCode` returns the canonical constant. A dedicated lesson on the risks of `ordinal()` analyzes schema, migration, versioning, and unknown external data.

## 39. Runnable: Stable Codes and Parsing from External Data

Save **`EnumStableCodeDemo.java`**:

```java
enum PaymentState {
    PENDING("P"),
    PAID("S"),
    FAILED("F");

    private final String code;

    PaymentState(String code) {
        this.code = code;
    }

    String code() {
        return code;
    }

    static PaymentState fromCode(String code) {
        for (PaymentState candidate : values()) {
            if (candidate.code.equals(code)) {
                return candidate;
            }
        }
        throw new IllegalArgumentException(
                "unknown code");
    }
}

public class EnumStableCodeDemo {
    public static void main(String[] args) {
        PaymentState paid = PaymentState.fromCode("S");

        System.out.println(paid.name());
        System.out.println(paid.code());
        System.out.println(paid == PaymentState.PAID);

        try {
            PaymentState.fromCode("X");
        } catch (IllegalArgumentException error) {
            System.out.println("unknown");
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 EnumStableCodeDemo.java
java EnumStableCodeDemo
```

Stdout:

```text
PAID
S
true
unknown
```

`fromCode` returns the canonical constant. Changing the declaration order of PENDING/PAID/FAILED does not automatically change the code `"S"`.

**Note:** `candidate.code.equals(code)` does not throw an NPE when the input code is null because `candidate.code` is assigned a non-null String. In production, you need to validate uniqueness and the null contract more carefully.

## 40. `name()` as an External Identifier: An Intentional Decision

Persisting `name()` can be reasonable if **the constant name is part of a stable contract**, the team controls renames/removals, and migrations exist. However, `name()` reflects **the name in Java source**, so changing `PAID` to `SETTLED` can cause `valueOf("PAID")` to no longer find the old constant.

Do not use `toString()` as an identifier if that method only serves display labels/localization. For protocols that need to remain stable across multiple releases, explicit `code()` and `fromCode(...)` are usually clearer. ORM/JPA mappings and choices among code/string/ordinal have their own contracts outside Java Core; **no default annotation replaces a migration/versioning strategy**.

This is the distinction between **declared name** and **persistent data identity**. The final lesson of the chapter goes into depth on the impact of ordinal ordering, rolling deployments, and migrating legacy records.

## 41. Enum Serialization and Identity

Java serialization has a **special mechanism for enum constants**: the serialized form relies on the enum type and constant name, and when deserialized under compatible conditions it resolves to the **canonical constant** of the existing enum type, without creating a parallel enum instance by invoking a normal constructor.

Points to remember:
- Enum objects still keep their own stable identity after a valid serialization round-trip.
- Enum deserialization is not like constructor-based cloning of a POJO.
- Individual instance fields are not used as serializable payload under the default enum serialization mechanism.
- If an enum constant name is renamed/removed, data serialized under the old name may fail to resolve.
- JSON technologies/custom serializers may have their own representations; you need to read the library's contract rather than inferring from Java native serialization.

### Why Is an Enum Singleton Often "Safer" During Serialization?

An enum singleton pattern `INSTANCE` uses the enum's serialization semantics rather than relying on manually writing `readResolve` for an ordinary serializable singleton class. Even so, do not assert that every external serialization library preserves identity if the library maps it to a DTO/string in its own way.

## 42. Can `clone()` and Reflection Create a Second Enum Constant?

Java's mechanism intentionally restricts the creation of enum objects:
- You cannot call `new EnumType(...)` in source code.
- `Enum.clone()` is final and prevents cloning in the usual way.
- Reflection `Constructor.newInstance` does not allow arbitrarily creating a new enum object through normal mechanisms.
- Java serialization specially resolves the canonical constant by name/type.

This supports enum identity semantics along standard object-creation paths.

**Do not turn this into a statement that every hack with JVM internals/Unsafe/native code is physically impossible.** This lesson refers to **commonly supported Java language/runtime APIs**, not exploiting internal implementations.

### Enum Singleton

`enum Singleton { INSTANCE; }` is a pattern representing a global instance **within the scope of the corresponding enum type/class loader**. It is concise and has advantages for serialization/identity, but if `INSTANCE` holds mutable state, thread safety is still required.

## 43. Mutable Fields in Enums: A Shared Instance Can Still Be Mutable

Be careful with:

```java
enum Counter {
    INSTANCE;

    private int value;

    void increment() {
        value++;
    }

    int value() {
        return value;
    }
}
```

`Counter.INSTANCE` has canonical identity, but the `value` field **can change**.

Consequences:
- All code using Counter.INSTANCE can interact with **the same mutable state**.
- The `final` of the constant reference does not make all instance fields final.
- `value++` is not atomic under concurrency.
- Enums do not automatically provide thread safety for mutable state.
- Tests sharing a JVM/class loader can affect one another if not properly reset/designed.

### Better in Many Cases

If constants only carry metadata:
- Use `private final` fields.
- Assign immutable values in enum constructors.
- If mutable global state is needed, use an explicit service/atomic abstraction with a clear owner/lifecycle.
- Avoid stateful enum constants when that makes correctness hard to reason about.

## 44. Runnable: Fixed Identity, Mutable State

Save **`MutableEnumDemo.java`**:

```java
enum Counter {
    INSTANCE;

    private int value = 0;

    void increment() {
        value++;
    }

    int value() {
        return value;
    }
}

public class MutableEnumDemo {
    public static void main(String[] args) {
        Counter first = Counter.INSTANCE;
        Counter second = Counter.INSTANCE;

        first.increment();
        second.increment();

        System.out.println(first == second);
        System.out.println(first.value());
        System.out.println(second.value());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 MutableEnumDemo.java
java MutableEnumDemo
```

Stdout:

```text
true
2
2
```

The example runs sequentially, so stdout is deterministic. If the same Counter.INSTANCE is incremented from multiple threads, `value++` can cause lost updates; appropriate synchronization/atomic mechanisms are needed.

## 45. Enums, Immutable Metadata, and Safe Publication

Each enum constant can serve as a place to hold immutable configuration:

```java
enum Timeout {
    SHORT(java.time.Duration.ofSeconds(5)),
    LONG(java.time.Duration.ofSeconds(30));

    private final java.time.Duration duration;

    Timeout(java.time.Duration duration) {
        this.duration = duration;
    }

    java.time.Duration duration() {
        return duration;
    }
}
```

`Duration` is an immutable value type; the final field keeps each constant's configuration stable and easy to share.

Java class initialization has guarantees related to visibility/happens-before for properly initializing static state, but if you **subsequently mutate** a field/mutable object held by an enum, you must still perform separate synchronization.

**Constructing each constant once does not mean every operation on it is thread-safe forever afterward.**

## 46. Be Careful Using Enum Constants in switch/Collections When Adding New Constants

Adding an enum constant can require places that use the enum to be updated:
- A `switch` expression that already listed all previous constants.
- `EnumSet.allOf(Type.class)` will include the new constant.
- `values()` has an additional element and ordinals may change.
- A UI that auto-builds a menu from `values()` displays the new item.
- `EnumMap` code creating entries for the old list may be missing the new key.
- Validators/serialized data/cross-service protocols need to support the new value.

Not every constant addition is a compatible change for every consumer. Distinguish among **source compatibility**, **binary compatibility**, **runtime data compatibility**, and **business semantics**.

### Reordering Constants

Changing the order does not alter the Java reference identity of constant names within a build, but it changes the ordinal, natural ordering, and iteration order of `values`/`EnumSet`/`EnumMap`. If a consumer relies on the old order, this is an impactful change.

## 47. Nested Enums and Local Enums in Java 17

An enum can be a member nested type:

```java
class Order {
    enum Status {
        NEW, PAID
    }
}
```

A member enum has static semantics and does not require an enclosing `Order` instance. Use `Order.Status.NEW` from a context with appropriate access.

Java 17 also allows a **local enum** to be declared inside a block:

```java
void run() {
    enum Mode {
        FAST, SAFE
    }

    Mode selected = Mode.FAST;
}
```

A local enum is implicitly static, and its name is only visible within the lexical scope of the block. It does not capture local variables via the mechanism of a normal local inner class.

**Whether an enum is nested or local, each declared constant still has enum identity semantics.** Declaration location affects scope/visibility, not the nature of the constant.

## 48. Runnable: A Nested Enum Requires No Enclosing Object

Save **`NestedEnumDemo.java`**:

```java
public class NestedEnumDemo {
    enum Mode {
        FAST, SAFE
    }

    public static void main(String[] args) {
        NestedEnumDemo.Mode a = NestedEnumDemo.Mode.FAST;
        Mode b = Mode.FAST;

        System.out.println(a == b);
        System.out.println(a.name());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 NestedEnumDemo.java
java NestedEnumDemo
```

Stdout:

```text
true
FAST
```

There is not a single `new NestedEnumDemo()`. A nested member enum is implicitly static, and both references point to the same `FAST` constant.

## 49. Reflection: Determining the Enum Type of a Constant

If there is no constant-specific body:

```java
MyEnum.VALUE.getClass() == MyEnum.class
```

is normally true because the object's runtime class is the enum class.

However, if the constant has a constant-specific body:

```java
enum Action {
    RUN {
        @Override
        void perform() {
        }
    };

    abstract void perform();
}
```

`Action.RUN.getClass()` is an anonymous subclass runtime class; comparing it with `Action.class` is no longer guaranteed to be true.

To obtain the **declaring enum class** of the constant, use:

```java
Action.RUN.getDeclaringClass() == Action.class
```

which is true.

### Do Not Use Compiler-Generated Class Names as Identifiers

Names such as `Action$1` in bytecode are not a public business contract. Do not store them in a database to model enum identity. Use the enum type and an appropriate constant name/code.

## 50. Is a Set of Enum Constants a Set?

An enum type is **the declared set of possibilities**, but the enum declaration itself is not a `java.util.Set` object.

`values()` creates an array snapshot of the constants; `EnumSet.allOf(MyEnum.class)` creates a Set containing all enum constants; they differ in kind and API.

Examples:
- `MyEnum.values().length`: number of constants in the declaration.
- `EnumSet.allOf(MyEnum.class).size()`: number of enum constants in the set.
- `EnumSet.noneOf(MyEnum.class)`: an empty set for a known enum type.

You cannot create new enum constants with `mySet.add(new MyEnum())`; a Set only adds references to the already declared constants.

## 51. Enum Type vs Sealed Hierarchy vs Record

An enum is suitable when:
- The set of values is **closed and finite** and known at compile time.
- Each value has a canonical name and identity.
- Each constant can carry metadata/behavior.
- Clients do not need to create additional new instances at runtime.

If variants must carry different payloads supplied by callers at runtime, for example:
- `Success(value)`;
- `Failure(reason)`;
- `Pending(retryAt)`;

then a **sealed interface + records** may be more natural than a single enum, because there will be **multiple instances** of each variant.

Do not turn `enum Error { ONE; mutable Object payload; }` into a "variable holding the result for every request" because a single constant would share the mutable payload across calls.

### Identity Decisions

- Enum: identity by constant object `State.SUCCESS`.
- Record/value object: equality by components (by default for records, with caveats for arrays).
- Entity: identity by domain ID/lifecycle, not an enum constant.
- Sealed variant instances: there can be multiple objects of the same subtype.

Understanding identity helps avoid choosing an enum for a dynamic data problem.

## 52. Issues When Using an Enum as a Set of Workflow States

A status enum is very convenient:

```java
enum OrderStatus {
    NEW, PAID, SHIPPED, CANCELLED
}
```

However, an enum declaration **does not automatically define transition rules**:
- Is NEW → SHIPPED allowed, skipping PAID?
- Is CANCELLED → PAID allowed?
- Who is authorized to change the state?
- Does the transition have side effects or a transaction requiring atomicity?
- Where is the history audited?

You can use an enum as a **state label**, and let a workflow/service validate transitions or add behavior onto the enum if the domain is small enough.

**Do not store the mutable current order state inside the `OrderStatus.PAID` object**. The current state must reside in each Order instance/entity, while `OrderStatus.PAID` is a shared constant describing a state.

## 53. Runnable: An Enum Constant Used as a Field Across Multiple Objects

Save **`OrderWithEnumDemo.java`**:

```java
enum OrderStatus {
    NEW, PAID
}

final class Order {
    private OrderStatus status = OrderStatus.NEW;

    void pay() {
        status = OrderStatus.PAID;
    }

    OrderStatus status() {
        return status;
    }
}

public class OrderWithEnumDemo {
    public static void main(String[] args) {
        Order a = new Order();
        Order b = new Order();

        a.pay();

        System.out.println(a.status());
        System.out.println(b.status());
        System.out.println(a.status() == OrderStatus.PAID);
        System.out.println(b.status() == OrderStatus.NEW);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 OrderWithEnumDemo.java
java OrderWithEnumDemo
```

Stdout:

```text
PAID
NEW
true
true
```

The two Orders have **independent state fields**, yet each field points to a canonical enum constant. Changing the `a.status` reference to PAID does not mutate `OrderStatus.NEW` or cause b to change state.

## 54. Mistaking a Constant Name for a String

Common code with mistaken intent:

```java
if (status.name() == "PAID") {
    // ...
}
```

The `==` operator on Strings compares references, not content. Although Java has String interning and enum names can involve literal internals, the code above **should not rely on an accidental reference match**.

Replace with:

```java
if (status == OrderStatus.PAID) {
    // ...
}
```

Or if you genuinely receive a String from external input and need to parse it:

```java
OrderStatus parsed = OrderStatus.valueOf(input);
```

along with validating/catching errors.

**Direct enum identity comparison** is clearer than converting a constant to a String and comparing back.

## 55. Equality with Enums: There Is No "Same-Name but New" Object

In an ordinary class, `new Item("A")` creates a new instance, so two Items can have the same field value yet different references.

In an enum:
- Enum constants are determined in the declaration.
- Ordinary Java code cannot instantiate an additional constant with the same name using `new`.
- `valueOf` returns an existing constant.
- `values` returns references to existing constants.
- Java native serialization resolves an existing constant.

Therefore, comparing `status == OrderStatus.PAID` is an expression based on **identity**, yet at the same time the standard way to check an enum's **state value**.

That is the difference from object value types, which normally require `equals`.

## 56. Exercise 1 — Identifying Type and Constants

Given:

```java
enum Direction {
    NORTH, SOUTH
}
```

How many enum types and how many declared constants are there?

**Answer:** One type `Direction`; two constants `NORTH` and `SOUTH`, corresponding to two enum instances with different identities.

## 57. Exercise 2 — Two References to the Same Constant

```java
Direction a = Direction.NORTH;
Direction b = Direction.NORTH;
```

`a == b`?

**Answer:** `true`. Both variables point to the same canonical constant NORTH.

## 58. Exercise 3 — Two Different Constants

`Direction.NORTH == Direction.SOUTH`?

**Answer:** `false` because they are different enum objects.

## 59. Exercise 4 — Does `values` Clone Constants?

```java
Direction[] x = Direction.values();
Direction[] y = Direction.values();
```

`x == y` and `x[0] == y[0]`?

**Answer:** `false` and `true` (for an enum with at least one constant), because each call to values creates a new array, while the elements are the same canonical constants.

## 60. Exercise 5 — Does `valueOf` Create a New Instance?

```java
Direction a = Direction.valueOf("NORTH");
```

`a == Direction.NORTH`?

**Answer:** `true`. valueOf returns the existing constant.

## 61. Exercise 6 — Is `name` an Object?

What type does `Direction.NORTH.name()` return?

**Answer:** `String`, with content `"NORTH"`. It is not an enum constant.

## 62. Exercise 7 — What Number Does `ordinal` Start At?

Given `enum Rank { BRONZE, SILVER, GOLD }`, `Rank.GOLD.ordinal()`?

**Answer:** `2` (zero-based declaration order).

## 63. Exercise 8 — Using ordinal for a Database

You store `GOLD.ordinal() = 2` in the database. Later you insert `PLATINUM` before GOLD.

**Answer:** The ordinal value of GOLD changes; the old mapping is no longer valid. Use an explicit stable code or a managed/migrated storage representation.

## 64. Exercise 9 — Overriding `name()`?

Can you declare in an enum:

```java
// @Override
// public String name() { return "custom"; }
```

**Answer:** No, `name()` is a final method in `Enum`. If you want a custom label, declare a separate method or override `toString()` if appropriate.

## 65. Exercise 10 — Overriding `toString()`?

Can an enum override `toString()`?

**Answer:** Yes. However, `name()` remains the declared name. Do not use a UI label from toString as a stable external key if it can change.

## 66. Exercise 11 — Two Constants with the Same Code

```java
enum Code {
    A(7), B(7);

    private final int id;

    Code(int id) {
        this.id = id;
    }
}
```

Do A and B have the same identity?

**Answer:** No. `A == B` is false; matching constructor arguments only make the field values match.

## 67. Exercise 12 — Public Constructor?

Is `public Color(int code) { ... }` valid in an enum?

**Answer:** No. Enum constructors cannot be public/protected; use private or omit the access modifier.

## 68. Exercise 13 — `new EnumType()`?

Can a client call `new Direction()` to create another constant?

**Answer:** No. Enum construction is a special mechanism tied to constant declarations and does not expose constructors to clients.

## 69. Exercise 14 — Static Initialization When One Constant Is Accessed First

Given `enum E { A, B, C; ... }` with a constructor that prints the name, main accesses E.C for the first time.

**Answer:** Enum class initialization creates the constants in declaration order A, B, C. It does not construct only C; constant constructors do not run again on subsequent accesses.

## 70. Exercise 15 — Constructor Using `name()`

An enum constructor prints `name()`. What value does it have?

**Answer:** The corresponding enum constant name has already been set up by the enum instance construction mechanism, so the constructor can print the constant name. You do not manually assign name/ordinal in a Java source constructor.

## 71. Exercise 16 — Constant-Specific Behavior

An enum `Operation` has ADD and MULTIPLY with bodies overriding `apply`.

**Answer:** Both constants still have distinct identities. The runtime class of a constant with a class body can be an anonymous subtype; use `getDeclaringClass()` to determine `Operation.class`.

## 72. Exercise 17 — `getClass()` of a Constant

`Action.RUN` has a constant-specific class body. Is `Action.RUN.getClass() == Action.class` always true?

**Answer:** No. It can be false because the runtime class is a constant-specific anonymous subclass. `Action.RUN.getDeclaringClass() == Action.class` is true.

## 73. Exercise 18 — Enums of Different Types with the Same Name

`OrderState.OPEN.equals(TicketState.OPEN)`?

**Answer:** `false`, even though both have `name() == "OPEN"` in terms of String content. Each type has its own set of constants.

## 74. Exercise 19 — Null and `==`

`OrderStatus status = null;`. `status == OrderStatus.PAID`?

**Answer:** `false`, with no NPE. However, `status.name()` throws an NPE.

## 75. Exercise 20 — EnumSet Order

In what order does `EnumSet.of(Permission.EXECUTE, Permission.READ)` iterate, given declaration `READ, WRITE, EXECUTE`?

**Answer:** READ before EXECUTE. EnumSet iteration follows natural declaration order, not insertion order.

## 76. Exercise 21 — EnumMap Order

Insert keys in the order DONE, START, RUNNING into an EnumMap; declaration is START, RUNNING, DONE.

**Answer:** Iterates in the order START, RUNNING, DONE.

## 77. Exercise 22 — Is a Mutable Enum Thread-Safe?

`enum Counter { INSTANCE; int value; void inc(){ value++; } }`.

**Answer:** Not automatically thread-safe. Canonical identity does not make `value++` atomic; synchronization/atomic APIs are needed for concurrent use.

## 78. Exercise 23 — Enum as Current State?

Should you put a mutable `int currentOrderId` field on `OrderStatus.PAID` to store the ID of the order currently being paid?

**Answer:** Usually no. PAID is a shared constant across all orders; the current state/ID belongs to each Order entity. Mutable data on a constant easily causes global shared-state bugs.

## 79. Exercise 24 — Constant Names and UI Labels

`PaymentStatus.SUCCESS` needs to display "Thanh toán thành công" in Vietnamese and "Payment successful" in English.

**Answer:** Do not rename the enum constant per language. Keep the identifier stable, and use localization/mapping labels by locale. You can have a displayName method, but do not turn toString into an external business identity.

## 80. Exercise 25 — Inserting a New Constant in the Middle

What does adding `PAUSED` between RUNNING and DONE affect?

**Answer:** The order of `values`, the ordinals of subsequent constants, EnumSet/EnumMap natural order, and related switch/exhaustiveness logic. External mappings storing ordinals may break.

## 81. Exercise 26 — Enum Serialization

An enum constant is serialized/deserialized using Java native enum serialization.

**Answer:** Deserialization resolves the canonical constant by enum type/name; it does not allocate a parallel instance via an ordinary constructor. Renaming/removing a constant can prevent old serialized data from resolving.

## 82. Exercise 27 — Enum Singleton

Does `enum Singleton { INSTANCE; }` always have exactly one instance across every JVM/class loader in the world?

**Answer:** You should not make a claim to that extent. Within a runtime enum class loaded in a single class loader context, INSTANCE is the canonical constant; different class loaders/processes do not share the same object reference.

## 83. Exercise 28 — Custom Stable Code

`enum Status { PENDING("P"), PAID("S") }`, and then constants are reordered.

**Answer:** `code()` still returns the code attached in the declarations, provided data is not modified. Ordinals change, but explicit business codes do not change automatically.

## 84. Exercise 29 — `valueOf` with Custom toString

`enum State { OK; @Override public String toString(){return "Success";} }`. `State.valueOf("Success")`?

**Answer:** `IllegalArgumentException` because valueOf looks up by `name()=="OK"`, not by the toString label.

## 85. Exercise 30 — A Better-Suited Type Than Enum?

A response has variants `Success(result)` and `Failure(reason)`, each invocation carrying a different payload.

**Answer:** Typically consider a sealed interface + records or a suitable hierarchy, since each call needs its own value object. Do not use a shared mutable singleton enum constant to store per-request payloads.

## 86. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| An enum constant is just a String | It is an object of the enum type, with reference identity |
| Every read of `Status.PAID` creates a new object | It reads the same canonical constant |
| `values()` creates new constants | Returns a new array, while elements are still the existing constants |
| `valueOf("PAID")` clones PAID | Returns the constant PAID itself |
| Enums are always completely immutable | They can have mutable instance fields/referents |
| Enums are automatically thread-safe for all mutations | Identity/initialization does not automatically synchronize operations |
| `ordinal()` is a stable code | Ordinals change if declaration order changes |
| `toString()` always equals `name()` | toString can be overridden |
| You can override `equals` based on a code field | Enum.equals is final and identity-based |
| Constants with the same field value are the same constant | Two different names are two constant instances |
| An enum constructor can be public | No; construction is restricted |
| You can call `new SomeEnum()` like an ordinary class | No |
| A constant with a class body definitely has `getClass()==Enum.class` | The runtime class may be an anonymous subtype |
| EnumSet preserves insertion order | Iterates in declaration order |
| EnumMap uses arbitrary object keys | Keys must be enum constants of the same key enum type |
| Renaming an enum constant does not affect serialized data | Data relying on the name may require migration |
| Enum state fields can safely store per-user data | Constants are shared across users/calls |
| Both enum and record have field-based equality | Enum is identity-based; record is component-based by default |
| An enum switch automatically accepts null in Java 17 | A null selector normally causes an NPE |
| Every type that is finite at runtime should be an enum | Enum is best when the set of values is closed and known at compile time |

## 87. Proper Enum Design Checklist

1. Is this a **closed, finite set of values** known at compile time?
2. Are the constants clearly named with business meaning?
3. Have you avoided arbitrary String/int in APIs when an enum fits?
4. Do you distinguish between the **enum type** and **each individual constant object**?
5. Do you understand that each declared constant has canonical reference identity?
6. Have you compared enums with `==` where appropriate?
7. Is there null input to handle before calling methods/switches?
8. Are you confusing enum `==` with String `==`?
9. Are you using `name()` as a persisted key without a migration strategy?
10. Are you using `ordinal()` as a stable external ID? If so, fix it.
11. Is an explicit stable business code field needed?
12. Are code fields unique and valid?
13. Are unmatched external codes handled explicitly?
14. Is `toString()` a label/diagnostic or an identifier? Have you distinguished them?
15. Are you using `values()` properly when all constants are needed?
16. Do you understand that `values()` returns a new array while elements are canonical?
17. Do you understand that `valueOf` looks up by exact name and throws an exception when wrong?
18. Does the enum constructor have appropriate private/package-private access?
19. Have you avoided manually calling `new EnumType()`?
20. Do constructor arguments match the signature/types?
21. Are there circular static initialization dependencies prone to bugs?
22. Have you avoided referencing uninitialized static enum fields in constructors?
23. Should constant state be `final` and immutable?
24. Are there mutable referents requiring defensive copies?
25. Is there mutable enum state requiring thread safety?
26. Is a constant-specific class body truly needed, or is a switch clearer?
27. If using a constant-specific body, does the code use `getDeclaringClass()` when the enum type is needed?
28. Do `switch` constructs properly handle constants and future changes?
29. Are `EnumSet`/`EnumMap` leveraged when appropriate?
30. Are you relying on iteration order/ordinal without intentionally defining a domain order?
31. Can data serialization/ORM mappings withstand renaming/adding/removing/reordering constants?
32. Do you distinguish class-loader identity from a global "every JVM" singleton?
33. Have you avoided attaching per-request/per-user mutable data to enum constants?
34. Is a sealed hierarchy/records needed for dynamic payloads instead of an enum?
35. Do the test programs compile cleanly under `--release 17` and produce deterministic stdout?

## 88. Core Summary

- **Declare enum constants** using a list of names at the top of the enum body, for example `enum Direction { NORTH, SOUTH }`.
- **Each constant name represents a distinct enum object**, with a stable identity within its corresponding runtime enum type; references to the same constant compare as true with `==`.
- **`name()` is the declared name**, **`ordinal()` is the zero-based position**, and **`toString()` is a customizable string**. They are not interchangeable.
- **`values()` creates a new array but does not create new constants**. **`valueOf(name)` returns the canonical constant itself**.
- Enum constants can carry data through **private constructors**, fields, and methods; two constants with the same code field are still two objects with different identities.
- A constant with a **constant-specific body** has a runtime anonymous subclass; `getDeclaringClass()` is the explicit way to obtain the original enum type.
- **EnumSet** and **EnumMap** leverage enum keys/elements and iterate in declaration order.
- **Do not store ordinal as a stable business ID**; use an explicit code when needed. Do not equate enum identity with mutable field values or UI labels.
- Enums support special identity/serialization/initialization semantics, but **mutable fields are not automatically immutable or thread-safe**.
- When values carry customizable per-request payloads, consider an immutable record/sealed hierarchy instead of forcing per-request state into a shared enum constant.

**Conclusion:** The strength of enums does not lie in replacing Strings with uppercase words, but in Java guaranteeing a **set of constant objects with clear type and identity**. Properly understanding each constant's identity helps you choose comparisons, design constructors, persist data, handle switches, and synchronize state safely.

## Java SE 17 Standard References

- **Java Language Specification `8.9 — Enum Classes`**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.9
- **JLS `8.9.1 — Enum Constants`**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.9.1
- **JLS `8.9.2 — Enum Body Declarations`**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.9.2
- **`java.lang.Enum` API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Enum.html
- **`java.util.EnumSet` API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/EnumSet.html
- **`java.util.EnumMap` API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/EnumMap.html
