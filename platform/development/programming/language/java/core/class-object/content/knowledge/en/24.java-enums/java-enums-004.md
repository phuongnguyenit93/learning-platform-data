# Enum Object Creation and Inheritance Restrictions in Java

> **Topic:** Java Core → Class/Object → Enum  
> **Focus:** Enum instance creation, constructor, and inheritance restrictions  
> **Version used in examples:** Java 17+

## 1. An enum is a special kind of class, but not an ordinary class

In Java, an `enum` (*enumeration class*) represents a **finite set of named values**, exposed by the **enum constants** in the enum declaration itself.

For example:

~~~java
enum TrafficLight {
    RED, YELLOW, GREEN
}
~~~

`RED`, `YELLOW`, and `GREEN` are the three constants of `TrafficLight`. Each constant is an object of an enum type, initialized via Java's special mechanism when the class is initialized. The program can use those objects, but **cannot create an additional TrafficLight using the `new` operator**.

An enum:

- **Cannot be arbitrarily instantiated** outside the declared constants.
- **Does not have a public/protected constructor** for external code to call.
- **Cannot declare `extends SomeClass`**, because an enum already has the special superclass `java.lang.Enum<E>`.
- **Cannot serve as the superclass of a user-named class** via `class Extra extends TrafficLight`.
- **Can implement interfaces** with `implements`, which is usually the right way to integrate polymorphism.
- Can have **fields, methods, constructors, static members**, and separate logic for each constant.
- In some cases, a constant can have its **own class body**; the compiler generates a dedicated anonymous subclass for that constant. This is a **language-controlled** exception, not permission to extend the enum with arbitrary subclasses.

The most important point: **an enum restricts the set of instances it is allowed to expose**, and Java enforces that property across constructors, the type hierarchy, and several runtime mechanisms.

This article presents those restrictions, their rationale, edge cases, equivalent designs when extensibility is needed, along with standalone runnable Java 17+ programs.

## 2. The set of enum constants is determined in the source

With:

~~~java
enum Size {
    SMALL, MEDIUM, LARGE
}
~~~

the set of named values of Size is `SMALL`, `MEDIUM`, `LARGE`. You cannot call any built-in Java public factory to add `EXTRA_LARGE` to the same enum at runtime.

### 2.1. Each constant is an object

~~~java
Size first = Size.SMALL;
Size second = Size.SMALL;
System.out.println(first == second); // true
~~~

`first` and `second` hold references to **the same enum constant instance**. Assigning an enum reference does not clone the object.

When declaring:

~~~java
Size selected = Size.MEDIUM;
selected = Size.LARGE;
~~~

you only **reassign the variable selected from one existing constant to another existing constant**. You do not create an additional enum object.

### 2.2. An enum constant is not a primitive value

An enum is a reference type. Therefore:

~~~java
Size selected = null;
~~~

can be valid at compile time; `null` **is not a new enum constant**. Calling `selected.name()` when selected is null will result in a `NullPointerException`.

This matters when writing validators, database mappings, JSON parsers, and APIs that accept optional enum values.

### 2.3. Why is fixing the number of instances useful?

A controlled set of values can help:

- Use `==` to compare the identity of named constants.
- Write an exhaustive `switch` based on the named constants.
- Build optimized `EnumSet` and `EnumMap` for an enum type.
- Prevent input from producing “unexpected” cases not in the business rules.
- Define centralized logic/metadata for each constant.
- Make clear that a variable of type `TrafficLight` only represents RED/YELLOW/GREEN or null, rather than an arbitrary subclass added by plugins.

**Instance restriction** is a design feature, not just a compiler limitation.

## 3. Syntax for creating enum constants and constructors

An enum can contain fields and constructors:

~~~java
enum HttpGroup {
    SUCCESS(200, "OK"),
    NOT_FOUND(404, "Missing");

    private final int code;
    private final String label;

    HttpGroup(int code, String label) {
        this.code = code;
        this.label = label;
    }

    int code() {
        return code;
    }

    String label() {
        return label;
    }
}
~~~

This is an **enum declaration fragment** (without `main`). The arguments after the constant name, such as `SUCCESS(200, "OK")`, are used to initialize the corresponding constant via the enum constructor.

### 3.1. Where is the constructor used?

`SUCCESS(200, "OK")` and `NOT_FOUND(404, "Missing")` are enum constant declarations. Java handles creating those instances when enum class initialization occurs. You do **not** write `new HttpGroup(200, "OK")`.

### 3.2. Enum constructors cannot be public/protected

Valid:

~~~java
enum State {
    STARTED;

    State() {             // Package-access syntax, enum-specific restriction.
    }
}
~~~

and:

~~~java
enum State {
    STARTED;

    private State() {     // Explicitly private.
    }
}
~~~

The two declarations above are **separate alternatives**, not placed simultaneously in the same source file with the same name `State`.

In Java, an enum constructor can only be **private or package-access in terms of declaration**; if there is no access modifier, it is treated as a private constructor according to the special rules of enums. An enum constructor must not be declared `public` or `protected`.

Intentionally **does not compile**:

~~~java
enum InvalidState {
    STARTED;

    public InvalidState() {  // ERROR.
    }
}
~~~

and:

~~~java
enum InvalidState {
    STARTED;

    protected InvalidState() { // ERROR.
    }
}
~~~

Reason: if external code could arbitrarily call the constructor, the enum would no longer guarantee a restricted set of values.

### 3.3. An enum does not automatically inherit constructors from its superclass

An enum constructor is declared as `State()`, `State(int code)`, etc. The compiler supplies the internal parameters required by the `Enum<E>` mechanism, such as name/ordinal. You do not directly call `super(name, ordinal)` from an enum constructor to turn it into ordinary class instance creation.

### 3.4. Constructor parameters still work normally

An enum can overload constructors with different signatures:

~~~java
enum Severity {
    LOW(1),
    MEDIUM(2, "Check"),
    HIGH(3, "Urgent");

    private final int weight;
    private final String note;

    Severity(int weight) {
        this(weight, "Normal");
    }

    Severity(int weight, String note) {
        this.weight = weight;
        this.note = note;
    }
}
~~~

This is a declaration fragment. The constant arguments determine which constructor overload is selected according to Java overload resolution. However, **only enum constant declarations** have the authority to create instances through the enum mechanism.

## 4. Restricting the number of instances: `new` cannot be used

Consider:

~~~java
enum Level {
    LOW, HIGH
}
~~~

The following lines **intentionally do not compile**:

~~~java
Level a = new Level();
Level b = new Level("CUSTOM");
Level c = new Level() { };
~~~

There is no syntax allowing a client to write `new Level()` to create an enum instance; attaching an anonymous class body in `new Level() { ... }` does not open a loophole either. The compiler rejects enum instantiation according to the language rules.

### 4.1. Cannot be worked around by adding a no-arg constructor

Adding:

~~~java
enum Level {
    LOW, HIGH;

    Level() {
    }
}
~~~

does not make `new Level()` valid externally. This constructor only participates in creating the enum constants.

### 4.2. Cannot declare an ordinary method that returns a new enum object

Inside the enum:

~~~java
static Level makeLow() {
    return LOW;
}
~~~

Valid because **it returns an existing constant**. However:

~~~java
static Level makeCustom() {
    return new Level(); // ERROR: cannot create more.
}
~~~

is invalid.

### 4.3. A factory can select a constant, not add a constant

~~~java
static Level fromWeight(int weight) {
    return weight > 5 ? HIGH : LOW;
}
~~~

This is a method fragment inside the `Level` enum. The factory only chooses among the available constants. If the business domain requires values with an arbitrary numeric weight, another class/record should be used instead of trying to create extra enum instances.

## 5. Complete program 1: identity, `values()`, and `valueOf()`

Create the file **`EnumIdentityDemo.java`**:

~~~java
import java.util.Arrays;

public class EnumIdentityDemo {
    enum Color {
        RED, GREEN, BLUE
    }

    public static void main(String[] args) {
        Color one = Color.RED;
        Color two = Color.RED;

        System.out.println("Same constant = " + (one == two));
        System.out.println("All = "
                + Arrays.toString(Color.values()));
        System.out.println("From name = " + Color.valueOf("GREEN"));
        System.out.println("Canonical = "
                + (Color.valueOf("RED") == Color.RED));

        Color[] array = Color.values();
        array[0] = Color.BLUE;

        System.out.println("Enum unchanged = "
                + (Color.values()[0] == Color.RED));
        System.out.println("Different arrays = "
                + (Color.values() != Color.values()));
        System.out.println("RED ordinal = " + Color.RED.ordinal());
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac -encoding UTF-8 EnumIdentityDemo.java
java EnumIdentityDemo
~~~

**Exact stdout:**

~~~text
Same constant = true
All = [RED, GREEN, BLUE]
From name = GREEN
Canonical = true
Enum unchanged = true
Different arrays = true
RED ordinal = 0
~~~

### 5.1. `==` is the appropriate choice for enum constants

For references to the same enum constant, `==` compares identity. A controlled set of constants makes comparing enums by identity clear. `Enum.equals` is also identity-based and is final.

### 5.2. `values()` does not allow modifying the set of constants

The compiler provides `Color.values()` to return the constants in **declaration order**. The returned array can be modified by the caller, but it is **not an API for modifying the set of enum constants**. The demo assigns `array[0] = Color.BLUE` and then calls a new `values()`; the first element is still RED.

### 5.3. `valueOf()` does not allocate arbitrary instances

`Color.valueOf("GREEN")` looks up the constant with the exact name GREEN. It does not parse a new enum from a string and does not allow arbitrary names. If a nonexistent name is passed, `valueOf` throws `IllegalArgumentException`; for a null name, related lookup APIs can throw `NullPointerException`.

### 5.4. What is `ordinal()` used for?

`ordinal()` reflects the constant's position in the declaration order, starting from 0. `RED.ordinal() == 0` in the example. This is a declaration-order detail and **should not be used as an ID stored in a database or external protocol**, because reordering or inserting constants can change the ordinal.

## 6. An enum implicitly extends `java.lang.Enum<E>`

Each enum `E` has the special supertype `java.lang.Enum<E>` according to Java language rules. This is a generic abstract base class providing a common API:

- `name()` — the declared name of the constant.
- `ordinal()` — the declaration order.
- `compareTo(E other)` — compares enum natural order.
- `getDeclaringClass()` — the enum class that declared the constant.
- `toString()` — defaults to the name, but can be overridden.
- `equals(Object)`, `hashCode()` — identity-based, final.
- Supports the serialization mechanism specifically defined for enums.

An enum cannot choose another superclass.

### 6.1. `extends` cannot be written in an enum declaration

Intentionally **does not compile**:

~~~java
class Base {
}

enum Status extends Base {  // ERROR: an enum declaration does not have an extends clause.
    READY
}
~~~

Also invalid:

~~~java
enum Status extends java.lang.Enum<Status> {
    READY
}
~~~

`Status` already has the special superclass specified by the language. It is neither necessary nor allowed to explicitly write `extends Enum<Status>`.

### 6.2. Why does Java not support multiple class inheritance here?

Java classes have a single superclass in the class hierarchy. An enum class already has `Enum<E>` as its superclass, so it cannot simultaneously extend a custom class such as `BaseEntity` or `AbstractStatus`.

If you need to share a **contract** between an enum and an ordinary class, use an interface. If you need to reuse behavior, use a static utility, composition, an appropriate default interface method, or a business service.

### 6.3. An ordinary class cannot directly extend `Enum<E>`

Intentionally **does not compile**:

~~~java
class FakeStatus extends Enum<FakeStatus> {
    FakeStatus(String name, int ordinal) {
        super(name, ordinal);
    }
}
~~~

Even though `Enum` has a protected constructor as part of the API for the compiler mechanism, Java forbids user-defined classes from directly extending `java.lang.Enum`. An ordinary subclass cannot be used to create an enum value “manually”.

### 6.4. An enum cannot extend another enum

Intentionally **does not compile**:

~~~java
enum Weekday {
    MONDAY, TUESDAY
}

enum Holiday extends Weekday {
    CHRISTMAS
}
~~~

There is no inheritance hierarchy like `Weekday <- Holiday` for two enum declarations.

If two enums need to share semantics, both can implement the same interface; clients use the interface type when polymorphism is desired.

## 7. Users cannot subclass an enum class

Suppose:

~~~java
enum State {
    ACTIVE, INACTIVE
}
~~~

You cannot write:

~~~java
class SpecialState extends State { // ERROR.
}
~~~

There cannot be an ordinary named subclass of State. This eliminates the possibility of an arbitrary subtype appearing at runtime that the enum declaration does not control.

### 7.1. An anonymous subclass cannot be used from outside

Also invalid:

~~~java
State extra = new State() {
};
~~~

An enum instance cannot be created with `new`, so it cannot be “bypassed” through an anonymous class body in normal class instance creation syntax.

### 7.2. Is an `enum` always final in the technical sense?

There is an important exception that needs to be understood accurately from Java language rules.

- If **no** enum constant declares its own class body, the enum class is **implicitly final**.
- If **there is at least one constant-specific class body**, the enum class is **implicitly sealed** according to the enum rules in Java 17. The only permitted direct subclasses are **anonymous classes generated by the compiler for the enum constants that have class bodies**.

This is **not** a mechanism for developers to declare `class Extra extends State` themselves; the set of permitted direct subclasses is restricted to the enum declarations.

### 7.3. Arbitrary modifiers cannot be attached to extend an enum

There is no source-level API such as `non-sealed enum E` allowing plugins to add constants. Enum-specific final/sealed semantics are defined by Java. `permits` cannot be used to expand the list of arbitrary descendants of an enum.

### 7.4. The runtime class may differ from the declaring enum class

When a constant has a class body, `constant.getClass()` can be an anonymous subtype, whereas `constant.getDeclaringClass()` still returns the enum class that declared the constant. This is an important nuance if code uses reflection/introspection.

## 8. Constant-specific class body: a compiler-controlled exception

Java allows each enum constant to have a class body:

~~~java
enum Operation {
    ADD {
        @Override
        int apply(int a, int b) {
            return a + b;
        }
    },
    MULTIPLY {
        @Override
        int apply(int a, int b) {
            return a * b;
        }
    };

    abstract int apply(int a, int b);
}
~~~

This is a declaration fragment. `ADD` and `MULTIPLY` have their own anonymous class bodies; they override `apply` to provide different behavior. The Java compiler generates the constant-specific subclasses according to language rules.

### 8.1. Why can arbitrary subclasses still not be created?

Only **enum constants within the enum declaration** can use this kind of constant-specific class body. You cannot introduce external code using a statement like `new Operation() { ... }` or `class Custom extends Operation`.

That means an enum supports **variation of behavior across a fixed set of constants**, rather than **open-ended inheritance by clients**.

### 8.2. Abstract instance methods in an enum

An enum can declare an abstract instance method like `abstract int apply(...)`, but must ensure every constant provides a concrete implementation via a class body according to Java requirements.

Intentionally does not compile:

~~~java
enum BrokenOperation {
    PLUS {
        @Override
        int apply(int a, int b) {
            return a + b;
        }
    },
    MISSING;

    abstract int apply(int a, int b);
}
~~~

`MISSING` has no implementation for the abstract method. The compiler rejects it.

### 8.3. Non-abstract methods can be overridden

Not every constant needs to have a class body. An enum can provide a default instance method and a constant can override it:

~~~java
enum Priority {
    LOW,
    HIGH {
        @Override
        String label() {
            return "urgent";
        }
    };

    String label() {
        return "normal";
    }
}
~~~

`LOW` uses the default behavior; `HIGH` uses the overridden behavior. Because HIGH has a class body, the enum has a constant-specific anonymous subclass, yet no named external subclass is allowed.

### 8.4. `getClass()` and `getDeclaringClass()`

`Priority.LOW.getClass() == Priority.class` is usually true because LOW has no constant body. `Priority.HIGH.getClass() == Priority.class` is false because HIGH has a body; however, `Priority.HIGH.getDeclaringClass() == Priority.class` is still true.

When you want to know **the enum type that declared the constant**, prefer `getDeclaringClass()` instead of assuming `getClass()` is always the enum class.

## 9. Complete program 2: constant-specific subclasses and interfaces

Create the file **`EnumConstantBodyDemo.java`**:

~~~java
public class EnumConstantBodyDemo {
    interface BinaryRule {
        int apply(int a, int b);
    }

    enum Operation implements BinaryRule {
        ADD {
            @Override
            public int apply(int a, int b) {
                return a + b;
            }
        },
        MULTIPLY {
            @Override
            public int apply(int a, int b) {
                return a * b;
            }
        };

        public abstract int apply(int a, int b);
    }

    static int calculate(BinaryRule rule, int a, int b) {
        return rule.apply(a, b);
    }

    public static void main(String[] args) {
        System.out.println("ADD = "
                + Operation.ADD.apply(3, 4));
        System.out.println("MULTIPLY = "
                + calculate(Operation.MULTIPLY, 3, 4));

        System.out.println("Constant body class equals enum = "
                + (Operation.ADD.getClass() == Operation.class));
        System.out.println("Declaring enum = "
                + Operation.ADD.getDeclaringClass().getSimpleName());
        System.out.println("Both are enum constants = "
                + (Operation.values().length == 2));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 EnumConstantBodyDemo.java
java EnumConstantBodyDemo
~~~

**Exact stdout:**

~~~text
ADD = 7
MULTIPLY = 12
Constant body class equals enum = false
Declaring enum = Operation
Both are enum constants = true
~~~

### 9.1. What kind of inheritance is this?

The runtime class of `Operation.ADD` is a compiler-generated constant-specific anonymous subclass, **not** a named class that a developer can extend. Both constants still belong to the fixed set of enum constants.

### 9.2. Why does an interface provide polymorphism?

`BinaryRule` is an interface. `Operation` implements BinaryRule, so `calculate(BinaryRule rule, ...)` accepts an enum constant via the interface type. The `apply` behavior differs by constant.

When you want the system to have another computation approach that is not an enum constant, you can create an **ordinary class that implements BinaryRule**, without needing or being able to extend Operation.

### 9.3. Do not treat an enum constant body as a public constructor

Nothing in the demo creates a new ADD2 or MULTIPLY2 operation. `values().length` remains 2. A constant-specific body only defines the behavior of one of the already declared constants.

## 10. Interfaces are the valid way to extend behavior

A Java enum **can implement interfaces**:

~~~java
interface HasCode {
    int code();
}

enum Result implements HasCode {
    OK(200),
    ERROR(500);

    private final int code;

    Result(int code) {
        this.code = code;
    }

    @Override
    public int code() {
        return code;
    }
}
~~~

This is a declaration fragment.

### 10.1. An enum can implement multiple interfaces

~~~java
enum Action implements Runnable, java.io.Serializable {
    EXECUTE;

    @Override
    public void run() {
        System.out.println("execute");
    }
}
~~~

The example above is valid in terms of interface declarations; adding `Serializable` is usually redundant because enums already have specialized serialization semantics, but it illustrates `implements`. Usually you should only implement interfaces that are meaningful in the domain.

### 10.2. Interfaces do not add enum constants

`Result implements HasCode` means Result satisfies the `HasCode.code()` contract. It does not allow another class to extend Result or add `OTHER` to Result.

An ordinary class can also implement HasCode:

~~~java
record CustomResult(int code) implements HasCode {
}
~~~

As a result, an API accepting `HasCode` can accept both enum constants and custom implementations.

### 10.3. Choose an interface to keep code extensible

If the requirement is “the system has multiple providers/plugins that add new status implementations”, an enum is not suitable as the root extensibility type. An interface or abstract class may be more appropriate; an enum can still serve as an implementation holding the set of built-in values.

**Distinguish extending behavior through an interface from expanding the set of instances of the enum itself.**

## 11. Complete program 3: an enum and an ordinary class implementing an interface

Create the file **`EnumInterfaceExtensionDemo.java`**:

~~~java
import java.util.List;

public class EnumInterfaceExtensionDemo {
    interface HasCode {
        int code();
    }

    enum BuiltinStatus implements HasCode {
        READY(1),
        FAILED(2);

        private final int code;

        BuiltinStatus(int code) {
            this.code = code;
        }

        @Override
        public int code() {
            return code;
        }
    }

    record CustomStatus(int code) implements HasCode {
    }

    static String format(HasCode value) {
        return "code=" + value.code();
    }

    public static void main(String[] args) {
        List<HasCode> statuses = List.of(
                BuiltinStatus.READY,
                new CustomStatus(9),
                BuiltinStatus.FAILED);

        for (HasCode status : statuses) {
            System.out.println(format(status));
        }

        System.out.println("Built-in count = "
                + BuiltinStatus.values().length);
        System.out.println("Custom is built-in enum = "
                + (statuses.get(1) instanceof BuiltinStatus));
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 EnumInterfaceExtensionDemo.java
java EnumInterfaceExtensionDemo
~~~

**Exact stdout:**

~~~text
code=1
code=9
code=2
Built-in count = 2
Custom is built-in enum = false
~~~

### 11.1. How to keep the API extensible

`CustomStatus` is a record that implements HasCode, not a subclass of BuiltinStatus. The `format(HasCode)` method handles both the enum and the record through the interface.

### 11.2. The set of enum constants remains unchanged

Even though the List has three HasCode objects, `BuiltinStatus.values().length` is still 2. The CustomStatus(9) value does not become a new enum constant.

### 11.3. A sealed interface can be used to control the set of implementations

Java 17 supports sealed classes/interfaces. When you need a hierarchy that both has multiple implementations and clearly restricts the permitted types, you can declare a `sealed interface` with a list of valid permitted types. An enum can be an implementation of a sealed interface, but **this is still not an enum extending another enum**.

Conceptual example:

~~~java
sealed interface Message permits OkMessage, ErrorMessage {
}

record OkMessage() implements Message {
}

record ErrorMessage() implements Message {
}
~~~

This is a valid Java 17 fragment when the top-level types in the same source context are declared appropriately. A sealed interface allows multiple implementation types according to permits; an enum keeps its own set of constants.

## 12. Complete program 4: constructor parameters and a lookup table

Create the file **`EnumConstructorLookupDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;

public class EnumConstructorLookupDemo {
    enum Phase {
        NEW(10, "New"),
        RUNNING(20, "Running"),
        DONE(30, "Done");

        private final int code;
        private final String label;

        private static final Map<Integer, Phase> BY_CODE;

        static {
            Map<Integer, Phase> map = new HashMap<>();
            for (Phase phase : values()) {
                map.put(phase.code, phase);
            }
            BY_CODE = Map.copyOf(map);
        }

        Phase(int code, String label) {
            this.code = code;
            this.label = label;
        }

        int code() {
            return code;
        }

        String label() {
            return label;
        }

        static Phase fromCode(int code) {
            Phase value = BY_CODE.get(code);
            if (value == null) {
                throw new IllegalArgumentException("Unknown code");
            }
            return value;
        }
    }

    public static void main(String[] args) {
        System.out.println("By code 20 = " + Phase.fromCode(20));
        System.out.println("NEW label = " + Phase.NEW.label());
        System.out.println("Count = " + Phase.values().length);
        System.out.println("Code DONE = " + Phase.DONE.code());

        try {
            Phase.fromCode(99);
        } catch (IllegalArgumentException ex) {
            System.out.println("Unknown rejected");
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 EnumConstructorLookupDemo.java
java EnumConstructorLookupDemo
~~~

**Exact stdout:**

~~~text
By code 20 = RUNNING
NEW label = New
Count = 3
Code DONE = 30
Unknown rejected
~~~

### 12.1. The constructor runs only for declared constants

`Phase.NEW`, `RUNNING`, `DONE` receive their corresponding code/label values. Calling `fromCode(20)` finds the existing RUNNING constant; it does not call the constructor to create a new Phase.

### 12.2. Why create the Map after the constants have been initialized?

Enum constant declarations are processed before ordinary static fields/blocks in the enum class initialization order. The static block in the demo iterates over `values()` to build the lookup map after the constants are ready.

Java has a **special restriction**: an enum constructor, instance initializer, or instance variable initializer cannot directly reference a static field of the enum itself, unless that field is a constant variable. This rule prevents a class of initialization-order bugs.

Intentionally **does not compile**:

~~~java
enum Broken {
    A;

    static int count;

    Broken() {
        count++; // Illegal reference to static field from enum initializer.
    }
}
~~~

Instead of doing that, build the computed static lookup after the constants are initialized, or manage mutable state in a well-designed external holder/service.

### 12.3. Do not use `ordinal` as a business code

The demo stores `code=10/20/30` independently of positions 0/1/2. An external code/DB ID should remain stable according to the contract; ordinal can change when constants are reordered. Use an explicit field and a parser/lookup like in the example when persistence is needed.

### 12.4. Checking for duplicate codes

A production lookup needs to define a policy if two constants share the same code. A simple `Map.put` will overwrite the previous mapping. You can detect duplicates using `putIfAbsent` and throw an exception during static initialization, or use other validation; this belongs to the enum's business invariant and is unrelated to the ability to create enum objects.

## 13. Can reflection create new enum instances?

**Not through the public reflection API using `Constructor.newInstance`.** Java reflection checks and rejects creating an enum object via this mechanism, even if code attempts to obtain the enum's constructor.

Some people see that an enum has a constructor in bytecode and assume they can use reflection to call it like an ordinary private constructor. That reasoning is wrong: **enums have specialized runtime-level restrictions**.

### 13.1. Why not use reflection to add constants?

- `getEnumConstants()` and `values()` provide the **declared constants**.
- `Constructor.newInstance` does not allow creating a new enum instance.
- The enum's set of constants is managed by the compiler/runtime.
- Using unsafe internal/unsupported hacks can break assumptions of the JDK/frameworks and is neither a Java language feature nor a stable API.

**It is unnecessary and inadvisable to use tricks that break enum invariants** to implement custom statuses. If runtime extensibility is needed, use an interface/registry or another value class.

### 13.2. Do not infer from the legacy `Class.newInstance()` API

Some legacy reflection APIs are deprecated or have accessibility limitations. They do not turn an enum into an ordinary class with a public no-args constructor. The existence of reflection does not change the type rules for enums.

### 13.3. Reflection is still useful for *reading* metadata

~~~java
System.out.println(Color.class.isEnum());
System.out.println(java.util.Arrays.toString(
        Color.class.getEnumConstants()));
~~~

This is a fragment when the enum Color is already available. Reflection can inspect the enum type and its constants, but does not grant the ability to add new constants.

## 14. Cloning and serialization: enum identity is protected

An enum constant differs from an ordinary mutable class object in several Java runtime behaviors.

### 14.1. `clone()` does not create a new enum constant

`java.lang.Enum` provides behavior that prevents cloning enum objects as a way to create arbitrary instances. `someEnum.clone()` cannot be used from user code to duplicate a constant; the corresponding cloning method of Enum has restricted/final semantics.

### 14.2. Java serialization has special handling for enums

With **Java native serialization**, enums are serialized/deserialized by a special mechanism based on the enum type and constant name, rather than by reconstructing arbitrary object state through an ordinary constructor. When reading back a valid serialized enum constant, the runtime returns the corresponding canonical constant instead of creating a separate new enum instance.

This ensures identity `==` continues to remain meaningful for enums within the same runtime class-loading context.

### 14.3. Serialization does not automatically guarantee compatibility across versions

If a constant name is changed or removed, deserialization of old data can fail. You should not treat the enum serialized form or ordinal as an independently versioned external protocol. When persisting data long-term, manage stable codes/migration.

### 14.4. An enum does not automatically make all state immutable

Although **the set of constants is fixed**, an enum class can still contain **mutable fields**. The enum serialization mechanism does not turn those mutable fields into immutable data. Those fields also carry their own concurrency and lifecycle considerations.

## 15. Complete program 5: serialization preserves the canonical enum constant

Create the file **`EnumSerializationDemo.java`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;

public class EnumSerializationDemo {
    enum Priority {
        LOW, HIGH
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes;

        try (ByteArrayOutputStream buffer =
                     new ByteArrayOutputStream();
             ObjectOutputStream output =
                     new ObjectOutputStream(buffer)) {
            output.writeObject(Priority.HIGH);
            output.flush();
            bytes = buffer.toByteArray();
        }

        Priority restored;
        try (ObjectInputStream input =
                     new ObjectInputStream(
                             new ByteArrayInputStream(bytes))) {
            restored = (Priority) input.readObject();
        }

        System.out.println("Restored = " + restored);
        System.out.println("Same constant = "
                + (restored == Priority.HIGH));
        System.out.println("Values count = "
                + Priority.values().length);
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 EnumSerializationDemo.java
java EnumSerializationDemo
~~~

**Exact stdout:**

~~~text
Restored = HIGH
Same constant = true
Values count = 2
~~~

Reading via `ObjectInputStream` does not create a third constant. `restored` references the exact canonical Priority.HIGH constant when deserialization occurs within a compatible class-loading context.

## 16. A final/sealed enum does not imply immutable fields

A misconception: “since an enum does not allow new and does not allow subclassing, every field of an enum must be immutable”.

This is **not true**. Enum constants have a fixed identity, yet they can have mutable fields:

~~~java
enum SessionCounter {
    INSTANCE;

    private int total;

    synchronized int next() {
        return ++total;
    }
}
~~~

`SessionCounter.INSTANCE` is an enum constant, but `total` changes when `next()` runs.

### 16.1. Complete program 6: an enum object with a mutable field

Create the file **`EnumMutableStateDemo.java`**:

~~~java
public class EnumMutableStateDemo {
    enum TicketCounter {
        SINGLE;

        private int issued;

        synchronized int issue() {
            return ++issued;
        }

        synchronized int issued() {
            return issued;
        }
    }

    public static void main(String[] args) {
        TicketCounter a = TicketCounter.SINGLE;
        TicketCounter b = TicketCounter.SINGLE;

        System.out.println("Same object = " + (a == b));
        System.out.println("First = " + a.issue());
        System.out.println("Second = " + b.issue());
        System.out.println("Total = " + a.issued());
        System.out.println("Constant count = "
                + TicketCounter.values().length);
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 EnumMutableStateDemo.java
java EnumMutableStateDemo
~~~

**Exact stdout:**

~~~text
Same object = true
First = 1
Second = 2
Total = 2
Constant count = 1
~~~

### 16.2. Why does it remain an enum even with mutable state?

`a` and `b` point to the same TicketCounter.SINGLE constant. `issued` changes from 0→1→2, yet there is still only **one enum constant instance**. No additional TicketCounter object is created.

### 16.3. Be careful with mutable enum singletons

Mutable fields in an enum are usually **shared state**, so they require thread safety and test isolation. If an enum represents fixed labels/states in business logic, keeping it immutable (final fields, immutable nested data) is usually simpler. If using an enum singleton for a service, you still need to design synchronization, lifecycle, and dependency management.

## 17. `values()`, `valueOf()`, and `name()` are not factories that create new instances

The compiler typically provides the following APIs for an enum:

| API | Role | Does it create a new enum instance? |
| --- | --- | --- |
| `E.values()` | Returns an array containing references to the declared constants in declaration order | No |
| `E.valueOf(String)` | Looks up a constant by exact declared name | No |
| `Enum.valueOf(E.class, name)` | Looks up a constant by enum class and name | No |
| `constant.name()` | Returns the declared identifier name | No |
| `constant.ordinal()` | Returns the position of the constant | No |
| `constant.getDeclaringClass()` | Returns the enum class that declared the constant | No |
| `constant.toString()` | Returns the string representation, which can be overridden | No |

### 17.1. `values()` may create a new array, not a new enum object

The statement “`values()` does not create new ones” needs to be stated precisely: the method typically creates/returns a **new array object** containing references to the **same enum constant instances**. The array is a mutable container, whereas enum constants are not added or removed through that array.

### 17.2. `name()` and `toString()` are different

By default, `toString()` returns the name. However, an enum can override toString to display a friendly label; `name()` remains the declared constant name. When storing a stable identifier, consider an explicit code field, because renaming an enum constant affects persisted strings.

### 17.3. `valueOf()` is case-sensitive

`Mode.valueOf("READ")` looks up the constant named READ; `"read"` is not automatically canonicalized. If input is case-insensitive, it must be intentionally normalized and invalid values caught according to the domain policy.

### 17.4. Do not use ordinal as an external key

Adding a constant at the beginning of an enum shifts the ordinals of subsequent constants. You should use the name or a stable code field suited to data versioning requirements, rather than writing database records based on ordinal as an immutable ID.

## 18. Switch expressions and the usefulness of a fixed enum set

Java 17 allows `switch` expressions with enum constants:

~~~java
static String nextAction(TrafficLight light) {
    return switch (light) {
        case RED -> "stop";
        case YELLOW -> "slow";
        case GREEN -> "go";
    };
}
~~~

This is a method fragment using an existing TrafficLight enum. Because the cases cover all constants, the compiler can evaluate the switch expression as exhaustive.

### 18.1. When adding a new constant in the source

If `BLINKING` is later added to TrafficLight without updating a switch expression that has no default, recompilation may require adding a case to remain exhaustive. This is a benefit of an explicit set of values: the developer is prompted to handle the new case.

### 18.2. Null is not an enum constant

With a switch expression in Java 17, passing null does not automatically match any ordinary enum case and can cause a NullPointerException. If the API allows null, validate for null beforehand or handle it according to an appropriate contract.

### 18.3. Switch does not allow runtime enum extension

You cannot “inject” a new enum constant to trigger a case outside the declared set under normal Java source/runtime rules. However, **upgrading the enum library version** can add a new named constant; source compatibility and exhaustive switches need to be considered at build/deploy time.

## 19. EnumSet and EnumMap rely on a fixed enum type

Java provides:

- `EnumSet<E extends Enum<E>>` — A specialized Set for enum constants of an enum type.
- `EnumMap<K extends Enum<K>, V>` — A specialized Map that uses enum constants as keys.

They are designed around the defined set of constants. You cannot add a “dynamic enum key” outside the enum declaration to the same enum type.

### 19.1. Complete program 7: switch, EnumSet, EnumMap

Create the file **`EnumCollectionsDemo.java`**:

~~~java
import java.util.EnumMap;
import java.util.EnumSet;

public class EnumCollectionsDemo {
    enum Permission {
        READ, WRITE, EXECUTE
    }

    static String action(Permission permission) {
        return switch (permission) {
            case READ -> "inspect";
            case WRITE -> "edit";
            case EXECUTE -> "run";
        };
    }

    public static void main(String[] args) {
        EnumSet<Permission> allowed =
                EnumSet.of(Permission.WRITE, Permission.READ);

        EnumMap<Permission, Integer> weight =
                new EnumMap<>(Permission.class);
        weight.put(Permission.EXECUTE, 3);
        weight.put(Permission.READ, 1);
        weight.put(Permission.WRITE, 2);

        System.out.println("Allowed = " + allowed);
        System.out.println("Weights = " + weight);
        System.out.println("READ action = "
                + action(Permission.READ));
        System.out.println("Contains EXECUTE = "
                + allowed.contains(Permission.EXECUTE));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 EnumCollectionsDemo.java
java EnumCollectionsDemo
~~~

**Exact stdout:**

~~~text
Allowed = [READ, WRITE]
Weights = {READ=1, WRITE=2, EXECUTE=3}
READ action = inspect
Contains EXECUTE = false
~~~

### 19.2. Why do EnumSet/EnumMap print in the right order?

`EnumSet` and `EnumMap` have an iteration order following **natural enum order**, which is declaration order. Since Permission declares READ, WRITE, EXECUTE, the output follows this order even though the insertion order differs. This is not arbitrary as with HashMap.

### 19.3. Do not mix enum types

An `EnumSet<Permission>` does not accept an arbitrary enum constant from another enum class as a valid typed element. `EnumMap` keys are also restricted to the single enum type provided when creating the map. If you need a collection combining multiple domains, you can use another interface/record key abstraction.

### 19.4. Enum collections do not make enum constants immutable

If a constant holds mutable fields, the collection still holds a reference to that very constant. EnumSet/EnumMap optimize membership and mapping; they do not protect thread safety or state inside enum constants.

## 20. Enum constant class bodies and `getClass()`

Without a class body:

~~~java
enum Simple {
    A, B
}
~~~

The constants usually have the exact runtime class of the enum class Simple. With a class body:

~~~java
enum Complex {
    A {
        @Override
        String text() {
            return "A!";
        }
    },
    B;

    String text() {
        return name();
    }
}
~~~

`Complex.A` has a constant-specific anonymous subclass runtime class, whereas `Complex.B` has no subclass body. It is neither necessary nor allowed to write a named class extending Complex.

### 20.1. How to check the type safely

If you need to know which enum a constant belongs to, call `value.getDeclaringClass()` instead of relying on `value.getClass()`. For `Complex.A`, the two Class objects can differ, even though value is still a Complex constant.

### 20.2. Do not infer new subclasses from names like `Complex$1`

The compiler may generate class files with names like `Complex$1` for constant-specific bodies, but those naming/details are a compiler implementation artifact. Do not hard-code the names of synthetic subclasses in business logic or reflection tests.

### 20.3. When using `getClass()` in equals/type checks

Enum.equals is final and uses identity, so it does not run into issues with custom equals based on getClass. However, custom helper/reflection code can make a mistake if it requires `constant.getClass() == SomeEnum.class` for every constant. Use `getDeclaringClass()` when the intended meaning is “declared enum class”.

## 21. Restrictions on constructors, superclasses, and inherited methods

An enum can declare regular instance methods and override permitted methods, but cannot override the `final` methods of `java.lang.Enum`:

- `name()`: final.
- `ordinal()`: final.
- `equals(Object)`: final.
- `hashCode()`: final.
- `compareTo(E)`: final.
- `getDeclaringClass()`: final.

Example that intentionally **does not compile**:

~~~java
enum Invalid {
    A;

    @Override
    public String name() {
        return "custom";
    }
}
~~~

`name()` cannot be overridden. If a display name is needed, create a `displayName()` method or override `toString()` if desired, keeping serialization/logging conventions in mind.

### 21.1. `toString()` can be overridden

~~~java
enum Priority {
    LOW, HIGH;

    @Override
    public String toString() {
        return "Priority:" + name();
    }
}
~~~

This is a valid declaration fragment. However, `Priority.LOW.name()` is still `"LOW"`; name() cannot be overridden.

### 21.2. Constructors are not inherited instance methods either

Enum constructors create constants internally; clients cannot choose a constructor overload to instantiate an arbitrary value. Having a parameterized constructor in an enum **does not turn the enum into an open factory**.

### 21.3. Other inherited methods still have contracts

An enum is an object, so it also has APIs from Object and Enum. However, an enum's identity/equality/ordering semantics are constrained to work reliably with its set of constants. If you want an object with value-based equals/hash that varies with mutable content, an enum is usually not the right abstraction.

## 22. Enum types can be nested members

When an enum is declared as a **member of a class/interface**, it is **implicitly static** according to Java rules.

~~~java
class Application {
    enum Mode {
        DEV, PROD
    }
}
~~~

If accessibility permits, you can use `Application.Mode.PROD` without creating an Application instance. This is a **nested enum type**, not an inner-class instance type requiring `outer.new Inner()`.

### 22.1. A nested enum still cannot have additional instances created

Being a nested enum does not change the constraints: no `new Application.Mode()` and no `class Custom extends Application.Mode`.

### 22.2. A member enum has no implicit enclosing instance

Because a member enum is implicitly static, enum constructors/instance methods cannot implicitly use `Application.this` like a non-static member inner class. If context data is needed, pass the data into a service method, or use a context holder outside the enum.

### 22.3. Do not tie an enum to each owner instance when per-owner state is desired

If each Application instance needs a customizable list of Modes, an enum cannot satisfy runtime dynamic values. You can store a List/Set of supported enum constants on each Application, or use a domain class with configurable values.

## 23. When should you not use an enum?

Do not try to force an enum if the requirement is:

1. Users create new values at runtime.
2. Plugins add implementations or action types unknown at compile time.
3. Values from a database can grow independently of source code deployments.
4. Each instance needs arbitrary state and a custom identity.
5. Multiple subclasses need to inherit from a custom base class.
6. An object requires multiple lifecycle/resource dependencies.
7. You want to deserialize an arbitrary ID into a new object of the same enum type.

In those situations, consider:

- **Record/value class** for data values that can be created flexibly.
- **Interface** for polymorphism/open implementations.
- **Abstract class** for behavior sharing when Java class inheritance fits.
- **Sealed interface/class** to restrict variants while using representation types you define yourself.
- **Registry/Map<String,Handler>** when dynamic extensions are needed.
- **Enum + metadata/business configuration** if the set of enum types is fixed while per-user configuration varies.

### 23.1. Distinguish between a closed enum and an open registry

An enum fits when the set of values is fixed per code version. An open registry fits when extensions are registered at runtime.

Do not create a dummy enum constant like `CUSTOM` and stuff every runtime custom value into a mutable field of the CUSTOM singleton if each custom value needs an independent identity. A record `CustomType(String id)` and an interface contract can be much clearer.

### 23.2. When dynamic type-safe values are needed

A record:

~~~java
record StatusCode(String value) {
    StatusCode {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Invalid code");
        }
    }
}
~~~

can let clients create `new StatusCode("SCHEDULED")`, `new StatusCode("PAUSED")`. This is a data-extensible value type, distinct from an enum's fixed constants. Validation/invariants must be handled by this class itself.

### 23.3. When mixed built-in and custom cases are needed

An interface `StatusLike` can be implemented by an enum BuiltinStatus and a record CustomStatus. An API accepting StatusLike will not be restricted to only named enum constants; however, it also gives up some guarantees/exhaustive switches of an enum-only type. Choose the trade-off based on the domain.

## 24. Common compiler and runtime errors

### 24.1. Error: `new MyEnum()`

**Cause:** enum instantiation is forbidden.  
**Fix:** use `MyEnum.EXISTING_CONSTANT`, `valueOf`, or a factory that selects a constant; if a new instance is needed, use a class/record.

### 24.2. Error: public/protected enum constructor

**Cause:** enum constructor accessibility is restricted.  
**Fix:** use private or omit the modifier, and pass arguments in the constant declarations.

### 24.3. Error: `enum X extends Base`

**Cause:** an enum cannot have a custom extends clause because it implicitly extends Enum<X>.  
**Fix:** implement an interface or use an ordinary class hierarchy if extending Base is required.

### 24.4. Error: `class Y extends X` where X is an enum

**Cause:** you cannot manually create a named subclass of an enum.  
**Fix:** define constant-specific behavior **inside the enum** or use an interface/ordinary class.

### 24.5. Error: `class Y extends Enum<Y>`

**Cause:** only compiler-generated enum types are valid under the special language rules.  
**Fix:** do not directly subclass java.lang.Enum.

### 24.6. Error: an enum abstract method is not implemented by all constants

**Cause:** a constant has no concrete implementation.  
**Fix:** give each constant body an implementation of the method or provide a default concrete method in the enum.

### 24.7. Error: accessing a nonconstant static field from an enum constructor

**Cause:** enum initialization order rule.  
**Fix:** build the static lookup after constants in a static initializer, use explicit immutable constant variables when appropriate, or move the state to an appropriate owner.

### 24.8. Runtime: `valueOf("UNKNOWN")`

**Cause:** there is no declared constant named UNKNOWN.  
**Fix:** validate input, map stable codes, and handle unknown values according to the contract; do not attempt to “create UNKNOWN”.

### 24.9. Runtime: race condition on a mutable enum field

**Cause:** a shared singleton-like constant with unsynchronized mutable fields.  
**Fix:** use immutable fields or synchronization/atomic types.

### 24.10. Design error: using ordinal for DB persistence

**Cause:** reordering enum constants changes the ordinal value.  
**Fix:** an explicit stable code/name with a migration policy.

### 24.11. Reflection error: assuming an enum object can be created via Constructor.newInstance

**Cause:** the reflection API rejects enum instantiation.  
**Fix:** use declared constants or a different abstraction.

### 24.12. Introspection error: `constant.getClass() == E.class` for every constant

**Cause:** constant-specific class bodies have anonymous subclasses.  
**Fix:** use `getDeclaringClass()` when the enum type is wanted.

## 25. Deep-comprehension check questions

**Question 1.** In `enum Color {RED, GREEN}`, can you create `new Color()`?

**Answer:** No. Only declared enum constants are created via the enum initialization mechanism.

**Question 2.** What does `Color.RED == Color.RED` return?

**Answer:** True, because they are the same enum constant instance.

**Question 3.** Does `Color.valueOf("RED")` create a new object?

**Answer:** No; it returns a reference to the existing Color.RED.

**Question 4.** Does `Color.values()` create new enum constants?

**Answer:** No. It returns an array containing references to the constants; the array itself may be a new object.

**Question 5.** Why cannot an enum constructor be public?

**Answer:** So clients have no way to create arbitrary additional enum instances, keeping the set of constants fixed.

**Question 6.** Does an enum constructor without a modifier allow clients in the same package to call it?

**Answer:** No. Enum constructors are treated under special restrictions; you cannot instantiate an enum with new even within the same package.

**Question 7.** Can you write `enum E extends CustomBase`?

**Answer:** No. Every enum has the special superclass `Enum<E>`.

**Question 8.** Can you write `class E2 extends E` when E is an enum?

**Answer:** No, there cannot be a named client subclass of an enum.

**Question 9.** Can you write `class Fake extends java.lang.Enum<Fake>`?

**Answer:** No; Java forbids ordinary classes from directly extending Enum.

**Question 10.** Can an enum implement an interface?

**Answer:** Yes, even multiple interfaces when valid.

**Question 11.** Can an interface be implemented by both an enum and a record?

**Answer:** Yes; that is how an API supports both built-in enum values and custom implementations.

**Question 12.** Is an enum always implicitly final in Java 17?

**Answer:** Not unconditionally: an enum without constant class bodies is implicitly final; one with a constant-specific class body is implicitly sealed, with permitted subclasses generated by the compiler for those constants.

**Question 13.** Can a user declare a custom subclass when an enum is implicitly sealed?

**Answer:** No. The permitted subclasses are constant-specific anonymous classes generated according to the enum declaration.

**Question 14.** Are `constant.getClass()` and `getDeclaringClass()` always the same?

**Answer:** Not if the constant has a class body. getDeclaringClass returns the enum type, while getClass can be an anonymous subclass.

**Question 15.** Can an abstract enum method be left unimplemented by one constant?

**Answer:** No, every constant must have a concrete implementation according to enum rules.

**Question 16.** Can `name()` of Enum be overridden?

**Answer:** No, the method is final. Use a separate label or override toString when appropriate.

**Question 17.** Can an enum override `toString()`?

**Answer:** Yes. However, name() remains the declared identifier.

**Question 18.** When needing a stable database ID, should ordinal() be used?

**Answer:** Avoid it. Use an explicit stable code according to the persistence contract.

**Question 19.** Can `EnumSet` hold an undeclared runtime custom constant?

**Answer:** No, because there is no valid additional enum constant.

**Question 20.** In what order does `EnumMap` iterate?

**Answer:** The natural order of the enum keys, corresponding to declaration order.

**Question 21.** Can enum constructors take parameters?

**Answer:** Yes, arguments are placed after constant names such as `OK(200)`.

**Question 22.** Is creating a Map lookup in an enum's static block useful?

**Answer:** Yes, it can map stable codes to declared constants after they are initialized.

**Question 23.** Can an enum constructor directly perform `count++` on a nonconstant static field of the enum itself?

**Answer:** No, due to the special enum initialization restriction.

**Question 24.** Does reflection `Constructor.newInstance` allow creating a new enum constant?

**Answer:** No. Reflection has a special restriction against enum instantiation.

**Question 25.** Does deserializing the same enum constant via Java serialization create a new enum instance?

**Answer:** No; special enum serialization returns the canonical declared constant by type/name when valid.

**Question 26.** Can an enum constant object have a mutable field?

**Answer:** Yes. An enum restricts creating/extending instances, but does not automatically guarantee deep immutability.

**Question 27.** Is a mutable counter in an enum automatically thread-safe?

**Answer:** No. Proper synchronization or atomic fields/APIs are needed.

**Question 28.** Is a member `enum` of a class implicitly static?

**Answer:** Yes. No enclosing class instance is needed just to use a member enum constant.

**Question 29.** When users add new statuses at runtime, is an enum or a record more suitable?

**Answer:** Usually a record/value class or registry/interface; an enum is suited for a set of named constants fixed per code version.

**Question 30.** What is the most important consideration when designing an enum?

**Answer:** An enum has a language-controlled set of named instances; it cannot be arbitrarily instantiated with new or subclassed. Extensibility should use interfaces/other abstractions instead of breaking enum invariants.

## 26. Checklist when choosing an enum for a design

1. Does the domain have a **finite, code-stable** set of values?
2. Are the constants truly named cases, or are arbitrary runtime instances needed?
3. Is there a need for subclassing/custom extends logic that an enum does not allow?
4. Can extensibility be separated into an interface?
5. Are constructors private/package-access with clear constant arguments?
6. Is there any `new EnumType(...)` or named extends enum in the code that needs to be fixed?
7. Is the enum's implicit superclass Enum<E> understood?
8. If using a constant-specific class body, are the runtime anonymous subclass/implicit sealed semantics understood?
9. Are abstract methods implemented by all constants?
10. Is getDeclaringClass used instead of getClass when the declared enum type is needed?
11. Do enum fields have appropriate immutable values and invariants?
12. If the enum has mutable fields, are concurrency and test isolation handled?
13. Is an explicit stable code used instead of ordinal for databases/protocols?
14. Are unknown valueOf inputs handled intentionally?
15. Is overriding final Enum methods avoided?
16. Are EnumSet/EnumMap used when collection keys/values are enums and appropriate?
17. Is the iteration order of EnumSet/EnumMap understood correctly?
18. Is trying to create additional enum constants via reflection/unsupported hacks avoided?
19. Is there a clear distinction between enum constants and values() array references?
20. Is there validation for lookup code collisions or unknown codes?
21. Is source/version compatibility considered when adding/changing constants?
22. Is persisting serialized ordinals or internal synthetic class names avoided?
23. Is the business display label distinguished from name()?
24. If it is a member enum, is it remembered that it is implicitly static with no outer instance?
25. If plugin-extensible values are needed, is an interface/registry/value class chosen instead of an enum?

## 27. Conclusion

**An enum in Java is a class whose set of named instances is determined by the enum declaration itself.** A program can reference, compare, and use those constants, but cannot create additional instances with `new`, cannot call the enum constructor from client code, cannot explicitly extend `java.lang.Enum`, and cannot make an enum the superclass of ordinary named classes.

Although an enum's constructors can accept parameters, they only serve the initialization of the declared constants. An enum implicitly has `Enum<E>` as its superclass and therefore cannot have `extends CustomBase`; **`implements Interface`** is the path to integrating with polymorphism. An enum constant can have a **constant-specific anonymous class body** to provide its own behavior; this exception is under the compiler's control and **does not turn an enum into an open hierarchy**.

Java also preserves identity through `valueOf`, `values`, reflection restrictions, and specialized serialization. At the same time, **fixed instance identity does not mean mutable fields are automatically immutable or thread-safe**. When the requirement is a fixed set of values, an enum is a strong design choice. When new values need to be created or third parties need to add implementations, use an appropriate interface, record/value class, sealed abstraction, or registry instead of trying to bypass the restrictions of enums.
