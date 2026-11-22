# Enum Fields, Methods, and Constructors in Java

## Learning Objectives

After this lesson, you can:

- Explain that `enum` is a special kind of class in which the names at the top of the body are **enum constants**, each of which is an instance created by a mechanism managed by Java.
- Distinguish between **per-constant fields**, **shared static fields**, and the constants themselves, which are implicitly declared by Java as `public static final`.
- Declare enums with instance fields, instance methods, static methods, constructors, and initializer blocks; understand when a `;` is required after the constant list.
- Pass arguments to enum constructors directly at constant declarations, and use constructor overloads and `this(...)` chaining to specify different state for each constant.
- Understand that enum constructors are explicitly or implicitly `private`; they cannot be declared `public`/`protected`, cannot invoke `super(...)` explicitly, and cannot be called from external code using `new`.
- Grasp the **initialization order**: constant objects are constructed in declaration order during enum class initialization; instance fields/instance initializers run before the constructor body; explicit static fields/blocks of the enum run after the constant declarations.
- Explain and fix violations of the specific JLS rule: an enum constructor, instance field initializer, or instance initializer **cannot reference a static field of the enum itself**, unless it is a **constant variable**.
- Use constant-specific class bodies to override/implement per-constant methods, and understand why constructors cannot be declared inside a constant-specific body.
- Use `values()`, `valueOf(String)`, `name()`, `ordinal()`, `toString()`, `equals()`, `==`, and `switch` for their proper purposes.
- Build enums with private fields, validation, defensive copying, and immutable behavior; recognize the risks when an enum holds mutable state since constants are shared.
- Know how to use `EnumSet`/`EnumMap`, interfaces, `static` lookup tables, and design alternatives when an enum starts taking on too many responsibilities.
- Read/compile self-contained runnable Java 17+ programs, verify stdout, and answer exercises independently.

> **Version:** All standalone runnable examples in the README target JDK 17 or later. Snippets that are intentionally invalid to explain compilation errors are explicitly marked as **not complete compilable programs**. Specification details are referenced from the Java Language Specification (JLS) Java SE 17, especially `8.9`, `8.9.2`, and `8.9.3`.

## 1. An Enum Is a Class; Constants Are Named Instances

Basic syntax:

~~~java
enum Direction {
    NORTH, SOUTH, EAST, WEST
}
~~~

`Direction` is not just a list of integers. It is a special **enum class** managed by Java. The names `NORTH`, `SOUTH`, `EAST`, `WEST` are **enum constants** of type `Direction`, created during enum class initialization. At the language level, each constant name corresponds to a `public static final Direction` field implicitly declared by the compiler.

Key properties:

1. You cannot write `new Direction()` from application code.
2. You cannot add a new constant instance after the class has been defined.
3. `Direction.NORTH == Direction.NORTH` is `true` because they have the same enum constant identity.
4. The enum constants belonging to the same class declaration are created once following the class initialization lifecycle; calling `values()` does not reconstruct the objects.
5. You can still define instance fields and methods inside the enum body, similar to many capabilities of a regular class.
6. An enum directly extends `java.lang.Enum<Direction>` via the language mechanism; an enum source declaration does not have an arbitrary `extends` clause.
7. An enum can `implements` interfaces, but cannot declare its own type parameters in the form `enum E<T>`.

### 1.1. A Constant Name Is Not a Local Variable

Example:

~~~java
Direction selected = Direction.NORTH;
~~~

`selected` is a reference variable belonging to the caller, whereas `Direction.NORTH` is a constant object with a stable identity. Assigning `selected = Direction.SOUTH` only changes the reference held in the variable; it **does not create a new enum instance**.

Do not confuse the `final` keyword of the implicit constant field with **every field inside the enum object being immutable**. An enum can still contain mutable instance fields — although many designs should avoid doing so.

## 2. Enums with Per-Constant Fields

An enum can declare a constructor and a private instance field:

~~~java
enum Coin {
    PENNY(1), NICKEL(5), DIME(10), QUARTER(25);

    private final int cents;

    private Coin(int cents) {
        this.cents = cents;
    }

    public int cents() {
        return cents;
    }
}
~~~

Analysis:

- `PENNY(1)` is a constant declaration with constructor argument `1`.
- `Coin(int cents)` receives a separate argument for each constant.
- `this.cents = cents` sets the instance field `cents` **on the constant object currently being created**.
- `private final` indicates that the field cannot be reassigned after being initialized; for an `int` primitive, this keeps the value stable.
- `cents()` is an **instance method**. Calling `Coin.DIME.cents()` returns 10.
- The `;` after the constant `QUARTER(25)` is required when declarations of fields/methods/constructors/blocks follow the constant list.

### 2.1. First Standalone Program

Save **`EnumFieldsDemo.java`**:

~~~java
public class EnumFieldsDemo {
    enum Coin {
        PENNY(1), NICKEL(5), DIME(10), QUARTER(25);

        private final int cents;

        Coin(int cents) {
            if (cents <= 0) {
                throw new IllegalArgumentException("cents");
            }
            this.cents = cents;
        }

        int cents() {
            return cents;
        }

        String label() {
            return name() + "=" + cents + "c";
        }
    }

    public static void main(String[] args) {
        System.out.println(Coin.PENNY.label());
        System.out.println(Coin.QUARTER.label());

        int total = 0;
        for (Coin coin : Coin.values()) {
            total += coin.cents();
        }
        System.out.println("all cents=" + total);
    }
}
~~~

Run:

~~~bash
javac EnumFieldsDemo.java
java EnumFieldsDemo
~~~

Stdout:

~~~text
PENNY=1c
QUARTER=25c
all cents=41
~~~

Each Coin constant has its own `cents`, but they all execute the same `label()` implementation. The field is `final int`, so there is no method to change the number of cents after the constants are created.

### 2.2. Why Use a Field Instead of `ordinal()` to Store Business Data?

`ordinal()` reflects the **declaration position** of the constant, starting from 0. It can change when reordering or adding constants. A coin does not get its monetary value from its declaration order. Use `private final int cents`, `code`, or `id` with clear business meaning rather than deriving it from the ordinal.

## 3. Semicolon After the Constant List

In an enum body, constant declarations come before other body declarations.

~~~java
enum State {
    NEW, ACTIVE, DONE;  // A ; is required if more declarations follow.

    private final long createdAt = 0L;

    boolean terminal() {
        return this == DONE;
    }
}
~~~

If the enum body **only has constants**, the `;` can be omitted:

~~~java
enum SimpleState {
    NEW, ACTIVE, DONE
}
~~~

If you need a static method, private constructor, field, or instance initializer after the constants, write a `;` to separate them.

### 3.1. Commas and Constructor Arguments

~~~java
enum Priority {
    LOW(1),
    MEDIUM(5),
    HIGH(10);

    private final int score;

    Priority(int score) {
        this.score = score;
    }
}
~~~

The arguments after each constant are selected by overload resolution of the enum constructor; they **do not** turn enum constants into integer variables. `LOW` is still a `Priority` object in which `score` is 1.

## 4. Enum Constructors: Special Access

According to JLS `8.9.2`:

- A constructor can be written as `private EnumName(...)`.
- If the access modifier is omitted from the constructor declaration, that constructor is also treated as **private**.
- An enum constructor **must not** be `public` or `protected`.
- You cannot declare an explicit superclass constructor invocation such as `super(...)` inside an enum constructor.
- If you do not declare any constructor, the compiler automatically declares a **default private no-arg constructor** for the enum.
- Regular code cannot invoke `new EnumName(...)`. Constant creation is handled by the compiler/JVM during enum type initialization.

### 4.1. Invalid Declarations (Illustrative, Commented Out)

~~~java
enum Invalid {
    A(1);

    // public Invalid(int n) { }      // Invalid: public enum constructor.
    // protected Invalid(int n) { }   // Invalid: protected enum constructor.
    // Invalid(int n) { super(); }    // Invalid: explicit superclass call.
}

// Invalid another = new Invalid(1); // Invalid: enum cannot be instantiated with new.
~~~

**Do not use the commented-out lines as runnable code.** Compiler errors may be phrased differently depending on the JDK/IDE, but the cause lies in the enum-specific rules, not the private field `n` or the `;`.

### 4.2. How Does `java.lang.Enum` Receive name/ordinal?

The compiler provides a mechanism to pass the constant name and ordinal information to the superclass `java.lang.Enum`; you **do not** write `super("A", 0)` manually. Do not rely on the synthetic bytecode constructor signature as an API that an application can call.

An enum constructor is used to assign **state that you declare yourself**, validate arguments, and perform work appropriate at class initialization time. It is not a way to open a gateway for creating arbitrary enum instances.

## 5. Constructor Overloading for Different Constants

Enum constructors can be overloaded just like constructors of a regular class. Each constant invokes the overload that matches the arguments it declares.

### 5.1. Runnable Program

Save **`EnumConstructorOverloadDemo.java`**:

~~~java
public class EnumConstructorOverloadDemo {
    enum Priority {
        LOW,
        MEDIUM(5),
        HIGH(9, "urgent");

        private final int score;
        private final String description;

        Priority() {
            this(1, "normal");
        }

        Priority(int score) {
            this(score, "custom");
        }

        private Priority(int score, String description) {
            this.score = score;
            this.description = description;
        }

        String describe() {
            return name() + ":" + score + ":" + description;
        }
    }

    public static void main(String[] args) {
        for (Priority priority : Priority.values()) {
            System.out.println(priority.describe());
        }
    }
}
~~~

Run:

~~~bash
javac EnumConstructorOverloadDemo.java
java EnumConstructorOverloadDemo
~~~

Output:

~~~text
LOW:1:normal
MEDIUM:5:custom
HIGH:9:urgent
~~~

Note:

- `LOW` has no parentheses → empty constructor argument list → `Priority()`.
- `MEDIUM(5)` → `Priority(int)`.
- `HIGH(9,"urgent")` → `Priority(int,String)`.
- `this(...)` **is used to chain constructors within the same enum class** (chaining), unlike calling `super(...)`, which is prohibited.
- Each constant has its own final state, even though the constructors share the final implementation.
- You do not need to declare the constructor `public` for the constants to call it: the constant declarations reside within the enum class itself.

### 5.2. Default Constructor vs No-Arg Overloaded Constructor

If an enum is simply:

~~~java
enum SimpleMode {
    FAST, SAFE
}
~~~

Java automatically provides a default private no-arg constructor. However, if you explicitly declare **only** a parameterized constructor:

~~~java
enum Size {
    SMALL(1), LARGE(3);

    private Size(int value) {
    }
}
~~~

then the constants must have an argument list matching an invocable constructor. Adding `MEDIUM` (without arguments) here will not automatically produce a new no-arg overload. For that constant to be valid, declare a separate no-arg constructor or pass arguments to the constant.

## 6. Enum Instance Methods Using the Constant's Own State

An enum should generally express its meaning through **clearly named methods**, rather than forcing callers to extract a raw field and write a chain of `if` statements.

Example:

~~~java
enum Role {
    READER(false), EDITOR(true);

    private final boolean canWrite;

    Role(boolean canWrite) {
        this.canWrite = canWrite;
    }

    boolean permitsWrite() {
        return canWrite;
    }
}
~~~

`permitsWrite()` encapsulates the `canWrite` field. If the rule becomes more complex later, callers still use the API method instead of depending on the internal representation.

### 6.1. Complete Program

Save **`EnumInstanceMethodDemo.java`**:

~~~java
public class EnumInstanceMethodDemo {
    enum Role {
        VIEWER(false),
        EDITOR(true),
        ADMIN(true);

        private final boolean mayEdit;

        Role(boolean mayEdit) {
            this.mayEdit = mayEdit;
        }

        boolean mayEdit() {
            return mayEdit;
        }

        String action() {
            return mayEdit ? "WRITE" : "READ";
        }
    }

    public static void main(String[] args) {
        for (Role role : Role.values()) {
            System.out.println(role.name() + ":" +
                    role.action() + ":" + role.mayEdit());
        }
    }
}
~~~

Run:

~~~bash
javac EnumInstanceMethodDemo.java
java EnumInstanceMethodDemo
~~~

Output:

~~~text
VIEWER:READ:false
EDITOR:WRITE:true
ADMIN:WRITE:true
~~~

The getter/method is called **on the enum constant**, not on a new object created by the caller. The methods can be `public` if an API module needs external access, whereas for a nested enum inside the same demo class, package-private methods are sufficient.

## 7. When Does Enum Constant Initialization Occur?

Enum constants are static fields of the enum class, and each constant's constructor is invoked when the enum class **is initialized** (*class initialization*), not every time you read `SomeEnum.VALUE`.

According to the JLS, class initialization has specific rules regarding *active use*. For instance, the first evaluation of an enum constant field can trigger initialization of the enum class if it has not yet been initialized.

**Distinctions:**

- `new EnumClass(...)` in source code is invalid.
- `EnumClass.ONE` can be the first active use that triggers class initialization to run.
- When class initialization runs, enum constant declarations are processed **in textual order**.
- The enum constructor runs for **each constant** when the constant object is created.
- Subsequently calling an instance method on a constant does not invoke the constructor again.
- The classloader/class lifecycle and JVM class initialization synchronization ensure orderly initialization; do not use an enum constructor to write arbitrary multi-threaded side effects.

### 7.1. Program to Observe the Order

Save **`EnumClassInitializationDemo.java`**:

~~~java
public class EnumClassInitializationDemo {
    enum Stage {
        START(1),
        FINISH(2);

        private final int code;

        Stage(int code) {
            this.code = code;
            System.out.println("constructor " + name() +
                    " code=" + code);
        }

        int code() {
            return code;
        }

        static {
            System.out.println("static block constants=" +
                    Stage.values().length);
        }
    }

    public static void main(String[] args) {
        System.out.println("before first use");
        System.out.println("start code=" + Stage.START.code());
        System.out.println("finish code=" + Stage.FINISH.code());
    }
}
~~~

Run:

~~~bash
javac EnumClassInitializationDemo.java
java EnumClassInitializationDemo
~~~

Output:

~~~text
before first use
constructor START code=1
constructor FINISH code=2
static block constants=2
start code=1
finish code=2
~~~

This is the output in a standalone program, where the first active use occurs after `println("before first use")`. The constructors for START and FINISH run before the static block declared after the constants. The subsequent use of FINISH **does not re-execute the constructor**.

**Do not infer from this single example that every JVM class is initialized immediately when the class file is loaded**; class loading/linking and class initialization are distinct concepts.

## 8. Order of Instance Field Initializers, Instance Blocks, and Constructor Body

Enum constants are instances of the enum class; the instance initialization mechanism shares many similarities with a regular class:

1. The object is allocated, and instance fields initially receive their default values.
2. The superclass constructor chain is processed according to the rules; here Java handles the `Enum` superclass.
3. The enum's instance field initializers and instance initializer blocks execute interleaved **in source order**.
4. The body of the enum constructor continues processing the constant's state.
5. The constant object is completely constructed and assigned to the corresponding constant field.
6. After the constants finish, explicit enum static field initializers and static initializer blocks execute in textual order.

Therefore, an instance block can read a field assigned earlier; whereas reading a field assigned by an initializer placed after the block may observe the default value.

### 8.1. Verification Program

Save **`EnumInstanceInitializationOrderDemo.java`**:

~~~java
public class EnumInstanceInitializationOrderDemo {
    enum Phase {
        PREPARE(3),
        EXECUTE(7);

        private int score = log("field", 1);

        {
            System.out.println("block sees=" + score);
            score += 2;
        }

        Phase(int extra) {
            System.out.println("ctor extra=" + extra +
                    " score=" + score);
            score += extra;
        }

        int score() {
            return score;
        }
    }

    static int log(String phase, int value) {
        System.out.println(phase + "=" + value);
        return value;
    }

    public static void main(String[] args) {
        System.out.println("prepare=" + Phase.PREPARE.score());
        System.out.println("execute=" + Phase.EXECUTE.score());
    }
}
~~~

Run:

~~~bash
javac EnumInstanceInitializationOrderDemo.java
java EnumInstanceInitializationOrderDemo
~~~

Output:

~~~text
field=1
block sees=1
ctor extra=3 score=3
field=1
block sees=1
ctor extra=7 score=3
prepare=6
execute=10
~~~

Analysis:

- When constructing PREPARE, `score` defaults to 0, the field initializer assigns 1, and the instance block reads 1 and then increments it to 3.
- The PREPARE constructor receives extra=3, prints score=3, and increments it to 6.
- When constructing EXECUTE, its **separate instance field score** goes through 0→1→3 again, and then the constructor adds 7 to make 10.
- Both constants are constructed from the same field/initializer declarations, yet hold different instance values.

**Unlike a static initializer:** a `static { ... }` block runs **once for the enum class**, not separately for each constant; a `{ ... }` block in the enum body runs for each constant object.

## 9. Tricky JLS Rule: Do Not Read Static Fields That Are Not Constant Variables When Creating Enum Constants

Because enum constants are constructed **before the static fields you declare below them**, initialization cycles can easily occur. JLS `8.9.2` specifies:

> In a constructor, instance initializer, or instance variable initializer of an enum declaration, referencing a static field of **the enum class itself** is a compile-time error, **unless that field is a constant variable**.

Do not mistakenly assume that every `static final` field is a *constant variable*. According to `4.12.4`, a constant variable must be `final`, of primitive type or String, and initialized with a **constant expression**.

### 9.1. Valid Case: Constant Variable

~~~java
enum Mode {
    A(1), B(2);

    private static final int FACTOR = 10;
    private final int scaled;

    Mode(int n) {
        scaled = n * FACTOR;  // Valid: FACTOR is a constant variable.
    }
}
~~~

`FACTOR` is a `static final int` with the constant expression `10`. The compiler can use the constant expression value directly inside the enum constructor when the constants are created.

### 9.2. Invalid Case: `static final Map`

~~~java
enum BadLookup {
    A, B;

    private static final java.util.Map<String, BadLookup> INDEX =
            new java.util.HashMap<>();

    BadLookup() {
        // INDEX.put(name(), this);
        // Compile-time error if uncommented:
        // referencing a non-constant static field of the enum itself
        // inside the enum constructor.
    }
}
~~~

Even a `static final Map` is **not a constant variable**: Map is a reference type other than String and its value is created at runtime. If the constructor were allowed to use INDEX, INDEX would not yet be initialized while the constructors for A and B are running.

### 9.3. Case Where `static final Integer` Is Also Not a Constant Variable

~~~java
enum BadBoxed {
    A;

    private static final Integer BASE = Integer.valueOf(10);

    BadBoxed() {
        // int x = BASE; // Invalid if uncommented:
        // BASE is not a constant variable.
    }
}
~~~

`Integer` is neither a primitive type nor String, even though the reference is declared `final`. `static final` does not automatically create a constant-variable exception.

### 9.4. Appropriate Fixes

- For per-constant state, pass values via **constructor arguments**.
- For compile-time primitive/String values, use a **constant variable**.
- For a shared runtime map/list cache, initialize it via a **static initializer after the constants have been created**.
- For lookup logic called by users after class initialization, place it in a **static method** that reads the initialized map.
- Do not call a helper method from the constructor to hide an initialization cycle; the compiler cannot detect all circular dependencies through method indirection, yet runtime can still observe null/partial state.

## 10. Program: Valid Constant-Variable Exception

Save **`EnumConstantVariableDemo.java`**:

~~~java
public class EnumConstantVariableDemo {
    enum Multiplier {
        SMALL(2), LARGE(5);

        private static final int FACTOR = 10;
        private final int product;

        Multiplier(int input) {
            product = input * FACTOR;
        }

        int product() {
            return product;
        }
    }

    public static void main(String[] args) {
        System.out.println("small=" + Multiplier.SMALL.product());
        System.out.println("large=" + Multiplier.LARGE.product());
    }
}
~~~

Run:

~~~bash
javac EnumConstantVariableDemo.java
java EnumConstantVariableDemo
~~~

Output:

~~~text
small=20
large=50
~~~

`FACTOR` is declared after the constants in the body, yet it is a constant variable and is allowed to be used when the constructor runs. This is an exception **grounded in the JLS**; do not generalize it to `static final Map` or `static final Integer`.

## 11. Building a Static Lookup Table After All Constants Are Created

A practical requirement: looking up an enum constant from a business code, HTTP code, short label, or ID. Do not use the constructor to insert `this` into a static map of **the enum class itself**. Instead:

1. The constructor only assigns the **instance fields** of each constant.
2. After the constants, declare the static map.
3. In a static block that runs after the constants are constructed, iterate over `values()` to populate the map.
4. Provide a static method such as `fromCode(int)` for lookups after class initialization.

### 11.1. Complete Program

Save **`EnumLookupDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;

public class EnumLookupDemo {
    enum HttpStatus {
        OK(200), NOT_FOUND(404);

        private final int code;
        private static final Map<Integer, HttpStatus> BY_CODE;

        HttpStatus(int code) {
            this.code = code;
        }

        int code() {
            return code;
        }

        static {
            Map<Integer, HttpStatus> mapping = new HashMap<>();
            for (HttpStatus status : values()) {
                HttpStatus previous = mapping.put(status.code(), status);
                if (previous != null) {
                    throw new IllegalStateException("duplicate code");
                }
            }
            BY_CODE = Map.copyOf(mapping);
        }

        static HttpStatus fromCode(int code) {
            return BY_CODE.get(code);
        }
    }

    public static void main(String[] args) {
        System.out.println("200=" + HttpStatus.fromCode(200));
        System.out.println("404=" + HttpStatus.fromCode(404));
        System.out.println("500=" + HttpStatus.fromCode(500));
    }
}
~~~

Run:

~~~bash
javac EnumLookupDemo.java
java EnumLookupDemo
~~~

Output:

~~~text
200=OK
404=NOT_FOUND
500=null
~~~

Because the static block comes after the enum constant declarations, `values()` there retrieves all constants. `Map.copyOf` creates an unmodifiable map snapshot from the mapping, preventing callers from mutating the internal map. In this example, `fromCode` returns null when a key is not found; a production API might be better suited with `Optional<HttpStatus>` or an exception depending on the domain.

**Do not call `HttpStatus.fromCode(...)` from the enum constructor assuming that the static map is already ready**; you will encounter initialization cycles, missing state, or runtime errors in designs that are not directly forbidden by the JLS.

## 12. How Do Static Methods and Instance Methods of an Enum Differ?

An enum can have both:

~~~java
enum Mode {
    FAST, SAFE;

    boolean fast() {
        return this == FAST; // Instance method: requires a receiver.
    }

    static Mode parse(String text) {
        return valueOf(text); // Static method: called on the enum class.
    }
}
~~~

Usage:

~~~java
boolean x = Mode.FAST.fast();
Mode y = Mode.parse("SAFE");
~~~

- `FAST.fast()` has the constant FAST as its receiver.
- `Mode.parse(...)` belongs to the class; it does not require a caller-supplied enum object receiver.
- `valueOf(String)` is a special static method implicitly declared for each enum type.
- If `text` does not match a constant name, `valueOf` throws `IllegalArgumentException` (null also has its own exception semantics).

The snippets above are valid within an appropriate class/scope, not standalone files with a main method.

### 12.1. `values()` Returns a New Array

`Mode.values()` returns a `Mode[]` containing the constants in declaration order. The elements' references in the returned array can be modified by the caller, but this does not alter the enum constant fields `Mode.FAST`/`Mode.SAFE` or create new constants.

You should not store or allow callers to modify an internal array that you manage yourself without a defensive contract. With enum `values()`, the API provides a way to obtain the set of constants; enum identity is still preserved.

## 13. Program: Clear Static and Instance API

Save **`EnumStaticAndInstanceMethodsDemo.java`**:

~~~java
public class EnumStaticAndInstanceMethodsDemo {
    enum Mode {
        FAST, SAFE;

        boolean isFast() {
            return this == FAST;
        }

        static Mode parse(String name) {
            return valueOf(name.trim().toUpperCase(
                    java.util.Locale.ROOT));
        }
    }

    public static void main(String[] args) {
        Mode parsed = Mode.parse(" safe ");

        System.out.println("parsed=" + parsed);
        System.out.println("fast?=" + parsed.isFast());
        System.out.println("same constant=" +
                (Mode.valueOf("SAFE") == parsed));

        Mode[] copy = Mode.values();
        copy[0] = Mode.SAFE;

        System.out.println("copy first=" + copy[0]);
        System.out.println("original first=" + Mode.values()[0]);
    }
}
~~~

Run:

~~~bash
javac EnumStaticAndInstanceMethodsDemo.java
java EnumStaticAndInstanceMethodsDemo
~~~

Output:

~~~text
parsed=SAFE
fast?=false
same constant=true
copy first=SAFE
original first=FAST
~~~

`parse` intentionally performs normalization, whereas the built-in `valueOf` requires the exact constant name verbatim. Even if the `copy` array is modified, the enum constants and the order of `values()` on the class remain unchanged.

## 14. Constant-Specific Class Bodies: Per-Constant Behavior

Instead of writing `switch(this)` in every method, an enum can declare a **class body directly after a constant** to override a method:

~~~java
enum Operation {
    ADD {
        @Override
        int calculate(int x, int y) {
            return x + y;
        }
    },
    MULTIPLY {
        @Override
        int calculate(int x, int y) {
            return x * y;
        }
    };

    abstract int calculate(int x, int y);
}
~~~

This is the *constant-specific method implementation* idiom. According to JLS `8.9.1`, a constant's body creates a separate **anonymous subclass** of the enum class for that constant, though a constructor cannot be declared inside the constant body.

### 14.1. Complete Program

Save **`EnumConstantSpecificMethodDemo.java`**:

~~~java
public class EnumConstantSpecificMethodDemo {
    enum Operation {
        ADD {
            @Override
            int calculate(int x, int y) {
                return x + y;
            }
        },
        MULTIPLY {
            @Override
            int calculate(int x, int y) {
                return x * y;
            }
        };

        abstract int calculate(int x, int y);
    }

    public static void main(String[] args) {
        System.out.println("add=" + Operation.ADD.calculate(2, 3));
        System.out.println("multiply=" +
                Operation.MULTIPLY.calculate(2, 3));
        System.out.println("declaring type=" +
                (Operation.ADD.getDeclaringClass() == Operation.class));
        System.out.println("constant subclass=" +
                (Operation.ADD.getClass() != Operation.class));
    }
}
~~~

Run:

~~~bash
javac EnumConstantSpecificMethodDemo.java
java EnumConstantSpecificMethodDemo
~~~

Output:

~~~text
add=5
multiply=6
declaring type=true
constant subclass=true
~~~

Points to understand:

- `Operation` is the enum class; `ADD` and `MULTIPLY` have constant-specific bodies.
- `calculate` is declared abstract in the enum class; **every constant** must provide an implementation.
- `getDeclaringClass()` on an enum constant returns the enum class that declares it, even when the constant's runtime class is an anonymous subclass.
- `getClass()` on ADD in the example is not equal to `Operation.class` because it has a constant-specific class body.
- Do not use `getClass() == Operation.class` to check the enum declaring type when constant-specific subclasses exist.

### 14.2. Constructors Still Belong to the Enum Class

If the enum constructor takes parameters, each constant with a class body still passes arguments to the **enum constructor** as usual:

~~~java
enum Calculator {
    ADD(1) {
        @Override
        int apply(int a, int b) {
            return a + b;
        }
    },
    MULTIPLY(2) {
        @Override
        int apply(int a, int b) {
            return a * b;
        }
    };

    private final int id;

    Calculator(int id) {
        this.id = id;
    }

    int id() {
        return id;
    }

    abstract int apply(int a, int b);
}
~~~

This is a standalone **enum snippet** placed in a valid file/scope; it has no separate `main`. `ADD(1)` and `MULTIPLY(2)` select the `Calculator(int)` constructor, while the class bodies after the constants do not declare new constructors. They only provide behavior overrides.

## 15. What If a Constant Does Not Implement an Abstract Method?

If an enum class has an abstract method, the JLS requires the enum to have at least one constant and **every constant to have a constant-specific body with a concrete implementation** of that abstract method.

~~~java
enum InvalidOperation {
    ADD {
        @Override
        int apply(int x, int y) {
            return x + y;
        }
    },
    // SUBTRACT; // Invalid if abstract apply() is not implemented.

    MULTIPLY {
        @Override
        int apply(int x, int y) {
            return x * y;
        }
    };

    abstract int apply(int x, int y);
}
~~~

The commented-out lines illustrate the error. If a constant has default behavior, do not declare the method abstract; instead, provide a **concrete implementation in the enum class** and override it only in special constants.

### 15.1. When Is Constant-Specific Behavior Valuable?

- A finite set of strategies where each constant defines its own calculation.
- Avoiding duplicated switch blocks when the logic belongs to the constant itself.
- Compile-time enforcement guarantees all implementations are provided for an abstract method.
- Callers invoke `operation.calculate(x,y)` through a common API.

If each constant body becomes very long, has many dependencies/side effects, and starts resembling a service, you can use the enum as an **ID/selector** and delegate to other classes/services with clearer lifetimes.

## 16. `name()`, `toString()`, and Display Fields

`Enum.name()` returns the **original declared name** of the constant, such as `PENDING`. `name()` is final and cannot be overridden. `toString()` returns the same name by default, but can be overridden to return a display label.

~~~java
enum Status {
    PENDING("Waiting"), DONE("Finished");

    private final String label;

    Status(String label) {
        this.label = label;
    }

    @Override
    public String toString() {
        return label;
    }
}
~~~

If `Status.PENDING.toString()` returns `Waiting`, that does not change `Status.PENDING.name()`, which remains `PENDING`. `valueOf("PENDING")` is still valid; `valueOf("Waiting")` **does not** automatically look up by toString.

### 16.1. Runnable Program

Save **`EnumNameVsToStringDemo.java`**:

~~~java
public class EnumNameVsToStringDemo {
    enum Status {
        PENDING("Waiting"),
        DONE("Finished");

        private final String label;

        Status(String label) {
            this.label = label;
        }

        @Override
        public String toString() {
            return label;
        }

        String label() {
            return label;
        }
    }

    public static void main(String[] args) {
        Status value = Status.PENDING;

        System.out.println("name=" + value.name());
        System.out.println("toString=" + value);
        System.out.println("label=" + value.label());
        System.out.println("parse=" + Status.valueOf("PENDING"));

        try {
            Status.valueOf("Waiting");
        } catch (IllegalArgumentException expected) {
            System.out.println("display label is not enum name");
        }
    }
}
~~~

Run:

~~~bash
javac EnumNameVsToStringDemo.java
java EnumNameVsToStringDemo
~~~

Output:

~~~text
name=PENDING
toString=Waiting
label=Waiting
parse=Waiting
display label is not enum name
~~~

`parse` in the example prints `Waiting` because `System.out.println(Status.valueOf(...))` calls `toString()` on the Status object. If you want to display the original name, print `Status.valueOf("PENDING").name()`.

**Design tip:** if enum data is stored as a stable code in a database/API, consider a private final business code field rather than treating `ordinal()` or a translated label as an ID. If you rename a constant in source code, `name()` changes as well; versioning needs to be handled according to the domain.

## 17. `ordinal()`, `equals()`, `hashCode()`, and Identity

Enum constants are finite instances with unique identity within the scope of the enum class/classloader. This leads to:

- Comparing two constants of the same enum with `==` is a readable idiom that checks identity.
- The final `Enum.equals` uses identity semantics, not value-based comparison of private fields.
- `Enum.hashCode` cannot be overridden like an arbitrary value object.
- `name()` and `ordinal()` are final methods of Enum.
- `ordinal()` is mainly used for certain specialized data structures and should not be stored as a stable business ID.
- `getDeclaringClass()` reflects the original enum class, even for a constant-specific subclass.
- Enum `compareTo` reflects declaration order, but you cannot arbitrarily compare constants of two incompatible enum types.

### 17.1. Identity and Ordinal Program

Save **`EnumIdentityDemo.java`**:

~~~java
public class EnumIdentityDemo {
    enum State {
        CREATED, RUNNING, STOPPED;

        boolean terminal() {
            return this == STOPPED;
        }
    }

    public static void main(String[] args) {
        State a = State.RUNNING;
        State b = State.valueOf("RUNNING");

        System.out.println("same reference=" + (a == b));
        System.out.println("equals=" + a.equals(b));
        System.out.println("running ordinal=" + a.ordinal());
        System.out.println("stopped terminal=" +
                State.STOPPED.terminal());
        System.out.println("ordered=" +
                (State.CREATED.compareTo(State.RUNNING) < 0));
    }
}
~~~

Run:

~~~bash
javac EnumIdentityDemo.java
java EnumIdentityDemo
~~~

Output:

~~~text
same reference=true
equals=true
running ordinal=1
stopped terminal=true
ordered=true
~~~

If constants are reordered, `ordinal()` and ordering can change. That is one reason not to use ordinal as a persistent database code. Both `equals` and `==` evaluate to true for the same enum constant because they refer to the same object.

## 18. Enum Methods Can Implement an Interface

An enum class cannot `extends` an arbitrary superclass, but it can `implements` one or more interfaces. Instance methods of an enum can fulfill an interface contract, including an appropriate generic interface.

### 18.1. Complete Program

Save **`EnumInterfaceMethodDemo.java`**:

~~~java
public class EnumInterfaceMethodDemo {
    interface Transformer {
        int apply(int input);
    }

    enum Scale implements Transformer {
        DOUBLE(2),
        TRIPLE(3);

        private final int multiplier;

        Scale(int multiplier) {
            this.multiplier = multiplier;
        }

        @Override
        public int apply(int input) {
            return input * multiplier;
        }
    }

    static void execute(Transformer transformer, int value) {
        System.out.println("result=" + transformer.apply(value));
    }

    public static void main(String[] args) {
        execute(Scale.DOUBLE, 5);
        execute(Scale.TRIPLE, 5);

        System.out.println("same enum=" +
                (Scale.valueOf("DOUBLE") == Scale.DOUBLE));
    }
}
~~~

Run:

~~~bash
javac EnumInterfaceMethodDemo.java
java EnumInterfaceMethodDemo
~~~

Output:

~~~text
result=10
result=15
same enum=true
~~~

The interface lets callers depend on the **behavior contract** without needing to know about the `multiplier` field. The enum constructor initializes multiplier only once for each Scale constant.

### 18.2. Do Not Write a Generic Enum Declaration

An enum cannot be declared as `enum Scale<T>`. However, an enum can implement a **generic interface with concrete type arguments**, for example `enum Color implements Converter<String>` when Converter is declared appropriately.

## 19. Enums with `switch` and Fields/Methods

Sometimes using a `switch` expression inside an enum method is easier to understand than constant-specific class bodies, especially when the behavior is small:

~~~java
enum TrafficLight {
    RED(30), YELLOW(4), GREEN(25);

    private final int seconds;

    TrafficLight(int seconds) {
        this.seconds = seconds;
    }

    String instruction() {
        return switch (this) {
            case RED -> "STOP";
            case YELLOW -> "CAUTION";
            case GREEN -> "GO";
        };
    }
}
~~~

All of the small logic resides in one method; each constant still has its own private final `seconds` field.

### 19.1. Runnable Program

Save **`EnumSwitchAndFieldsDemo.java`**:

~~~java
public class EnumSwitchAndFieldsDemo {
    enum TrafficLight {
        RED(30), YELLOW(4), GREEN(25);

        private final int seconds;

        TrafficLight(int seconds) {
            this.seconds = seconds;
        }

        String instruction() {
            return switch (this) {
                case RED -> "STOP";
                case YELLOW -> "CAUTION";
                case GREEN -> "GO";
            };
        }

        int seconds() {
            return seconds;
        }
    }

    public static void main(String[] args) {
        for (TrafficLight light : TrafficLight.values()) {
            System.out.println(light.name() + ":" +
                    light.instruction() + ":" + light.seconds());
        }
    }
}
~~~

Run:

~~~bash
javac EnumSwitchAndFieldsDemo.java
java EnumSwitchAndFieldsDemo
~~~

Output:

~~~text
RED:STOP:30
YELLOW:CAUTION:4
GREEN:GO:25
~~~

A change to the enum that adds a new constant requires updating the `switch` expression to ensure exhaustiveness of all cases as required by compilation. Choosing between switch and constant-specific polymorphism depends on complexity and how the behavior needs to be extended.

## 20. Mutable Fields in Enums: Valid but Error-Prone

Important principle: enum constants are **shared** objects, not fresh instances created every time a method is called. If a constant has a mutable instance field, every alias to that constant sees the state being modified.

~~~java
enum Feature {
    CACHE;

    private int hits;

    void hit() {
        hits++;
    }

    int hits() {
        return hits;
    }
}
~~~

This is syntactically valid code, yet at the same time it contains **shared mutable state**. Across multiple threads, `hits++` is not atomic and can lead to lost updates/data races.

### 20.1. Program Demonstrating Reference Aliasing

Save **`EnumMutableStateDemo.java`**:

~~~java
public class EnumMutableStateDemo {
    enum Feature {
        CACHE;

        private int hits;

        void hit() {
            hits++;
        }

        int hits() {
            return hits;
        }
    }

    public static void main(String[] args) {
        Feature first = Feature.CACHE;
        Feature second = Feature.valueOf("CACHE");

        System.out.println("same object=" + (first == second));

        first.hit();
        second.hit();

        System.out.println("first hits=" + first.hits());
        System.out.println("second hits=" + second.hits());
    }
}
~~~

Run:

~~~bash
javac EnumMutableStateDemo.java
java EnumMutableStateDemo
~~~

Output:

~~~text
same object=true
first hits=2
second hits=2
~~~

Just because the instance field `hits` is **non-static** does not mean each variable `first`/`second` receives its own `Feature` object. Both aliases point to `Feature.CACHE` and modify the same field.

### 20.2. When Is Shared Mutable State Actually Needed?

An enum singleton can hold a thread-safe shared service/counter if that is an intentional design. Use appropriate synchronization, atomic classes, lifecycle, and testing. However, for enums representing **domain values**, prefer **private final immutable fields**, while mutable business state should reside in a separately managed service/aggregate.

## 21. Defensive Copying with Mutable Fields in Enums

`final` only locks the **reference field**; it does not make the referenced object immutable. If an enum constant receives an array and stores the raw reference, the array can be mutated through an accessor or another alias.

### 21.1. Defensive Copy for an Array Field

Save **`EnumDefensiveCopyDemo.java`**:

~~~java
import java.util.Arrays;

public class EnumDefensiveCopyDemo {
    enum Palette {
        BASIC(new int[] {1, 2, 3}),
        EXTENDED(new int[] {4, 5});

        private final int[] colors;

        Palette(int[] colors) {
            this.colors = colors.clone();
        }

        int[] copyColors() {
            return colors.clone();
        }

        int checksumForDemo() {
            return Arrays.stream(colors).sum();
        }
    }

    public static void main(String[] args) {
        int[] received = Palette.BASIC.copyColors();
        received[0] = 99;

        System.out.println("received=" +
                Arrays.toString(received));
        System.out.println("stored sum=" +
                Palette.BASIC.checksumForDemo());
        System.out.println("extended sum=" +
                Palette.EXTENDED.checksumForDemo());
    }
}
~~~

Run:

~~~bash
javac EnumDefensiveCopyDemo.java
java EnumDefensiveCopyDemo
~~~

Output:

~~~text
received=[99, 2, 3]
stored sum=6
extended sum=9
~~~

The enum constructor copies the input array, and the accessor returns a copy rather than the raw internal representation. `Arrays.stream` is only used to demonstrate the sum, not a cryptographic checksum. With `List<MutableItem>`, copying the list structure may not be enough: mutable elements may need to be converted to immutable values or copied appropriately.

**Specifically:** the arrays are created directly as arguments for the enum constants and are not exposed outside in this snippet, yet defensive copying remains a useful API discipline when a constructor signature accepts mutable references.

## 22. EnumSet and EnumMap Leverage the Finite Set of Constants

Java provides `EnumSet<E extends Enum<E>>` and `EnumMap<K extends Enum<K>,V>` to work with enum keys/sets in a specialized manner.

`EnumSet` represents a set of constants from the same enum class. `EnumMap` uses enum constants as keys and manages values. Both rely on enum identity/domain; if mutable values are used in an EnumMap, those values **do not automatically become immutable**.

### 22.1. Runnable Program

Save **`EnumCollectionsDemo.java`**:

~~~java
import java.util.EnumMap;
import java.util.EnumSet;

public class EnumCollectionsDemo {
    enum Permission {
        READ(1),
        WRITE(2),
        EXECUTE(4);

        private final int mask;

        Permission(int mask) {
            this.mask = mask;
        }

        int mask() {
            return mask;
        }
    }

    public static void main(String[] args) {
        EnumSet<Permission> granted =
                EnumSet.of(Permission.READ, Permission.WRITE);

        int combined = 0;
        for (Permission permission : granted) {
            combined |= permission.mask();
        }

        EnumMap<Permission, Integer> limits =
                new EnumMap<>(Permission.class);
        limits.put(Permission.READ, 2);
        limits.put(Permission.WRITE, 1);
        limits.put(Permission.EXECUTE, 0);

        System.out.println("mask=" + combined);
        System.out.println("can write=" +
                granted.contains(Permission.WRITE));
        System.out.println("execute limit=" +
                limits.get(Permission.EXECUTE));
    }
}
~~~

Run:

~~~bash
javac EnumCollectionsDemo.java
java EnumCollectionsDemo
~~~

Output:

~~~text
mask=3
can write=true
execute limit=0
~~~

This is a permission domain example with a private final `mask`, so the bit mask is not derived from `ordinal()`. The constants remain objects of type Permission, used in EnumSet/EnumMap without recreating instances.

## 23. Methods Can Use `name()`, but Business Labels Should Be Kept Separate

If an enum named `HTTP_404` is renamed in code, `name()` changes too. If an external protocol requires a durable code, the constructor can accept an explicit code:

~~~java
enum ResultCode {
    SUCCESS("ok"),
    NOT_FOUND("not_found");

    private final String wireCode;

    ResultCode(String wireCode) {
        this.wireCode = wireCode;
    }

    String wireCode() {
        return wireCode;
    }
}
~~~

Callers can serialize `wireCode()` to JSON/database instead of using `ordinal()`, and create a static lookup if parsing by wire code is desired. Avoid using `toString()` if it serves localization/display text that may change.

### 23.1. Constructor Validation

An enum constructor can reject invalid input via an unchecked exception. Keep in mind, however, that this occurs **during enum class initialization**; an error can cause initialization to fail, causing the first code path accessing the enum to encounter `ExceptionInInitializerError` or a subsequent related `NoClassDefFoundError` depending on the path.

Because constants are fixed declarations in source code, catching constant configuration errors early during test/build is generally better than letting production trigger class initialization first.

### 23.2. Do Not Assume `toString()` = `name()` When Overridden

By default, Enum's `toString()` returns the name, but an enum can override it. When parsing via `valueOf(String)`, the input must be the constant's **name**, not an arbitrary display label. When parsing external codes, write your own `fromWireCode(String)` method with explicit semantics and clear null/unknown handling.

## 24. Inherited Enum Methods That Cannot Be Arbitrarily Overridden

Every enum extends `java.lang.Enum`. Several methods are defined by the platform as `final`:

- `name()`
- `ordinal()`
- `equals(Object)`
- `hashCode()`
- `compareTo(...)`
- `getDeclaringClass()`
- `clone()` is designed to prevent cloning enum constants.

Conversely, `toString()` can be overridden. You can also write custom domain methods such as `isTerminal()`, `price()`, `apply()`, and `description()`.

The `values()` and `valueOf(String)` methods are implicitly declared by the compiler for an enum; do not declare fields/methods with signatures matching these implicitly generated members. This keeps the enum API consistent.

### 24.1. Do Not Clone Enums to Create a Second Constant

Enum instances are finite objects fixed by declaration. If you need **multiple instances with different runtime data**, you should not force an enum into becoming a mutable per-request object. Use the enum as a **type/strategy** and a record/class to hold the data of each request:

~~~java
enum Channel {
    EMAIL, SMS
}

record Message(Channel channel, String text) {
}
~~~

The snippet above is valid in Java 17 within an appropriate file/scope. Each Message record instance holds its own data, while Channel constants are safely shared when they carry no mutable state.

## 25. Calling an Enum Static Method During Enum Initialization: Beware Dependency Cycles

Even when a helper method is valid with respect to name resolution, it can read **partial state** before the class has finished initializing. Do not use a constructor to call a static lookup method when that lookup relies on a map that has not yet been built.

Example of what not to do:

~~~java
enum BadDesign {
    A, B;

    private static final java.util.Map<String, BadDesign> TABLE =
            new java.util.HashMap<>();

    BadDesign() {
        // register(this); // Avoid calling a helper that reads TABLE here.
    }

    private static void register(BadDesign value) {
        TABLE.put(value.name(), value);
    }
}
~~~

The commented-out lines illustrate an anti-pattern. If uncommented, calling the helper from the constructor can lead to a `NullPointerException` because `TABLE` has not yet been initialized while the A/B constructors are running. **Do not claim that the compiler will definitely catch every dependency cycle through helper methods**: the JLS rule on direct static field references prevents one class of errors, yet complex runtime initialization cycles can still occur.

**Correct approach:** a static block populates TABLE after the constants as in Section 11. A global mutable map is not needed if there are only a few constants and a `for(values())` loop inside a static method provides sufficient performance.

## 26. Should You Use Enum Constructors to Perform Side Effects?

Enum constructors run during class initialization, typically only once in the lifecycle of the enum class/classloader. Having a constructor:

- Write I/O,
- Open network resources,
- Initialize a shared service,
- Register a callback in a long-lived registry,
- Create a thread,
- Trigger the loading of classes with circular dependencies,

can make initialization behavior unpredictable, hard to test, and hard to clean up. An enum is generally best suited for **immutable metadata** such as code, label, priority, and strategy.

If a constant needs a mutable service, the service is normally kept in a dependency container/application lifecycle, with the enum representing a key or passing a strategy via an interface. This is not a Java syntax limitation, but a design choice to reduce coupling and side effects.

### 26.1. Constructor Validation Option

Good:

~~~java
enum Size {
    SMALL(1), LARGE(3);

    private final int factor;

    Size(int factor) {
        if (factor <= 0) {
            throw new IllegalArgumentException("factor");
        }
        this.factor = factor;
    }
}
~~~

Not good: a constructor running code that depends on network availability, database connections, or the file system to populate a final field when any constant is accessed for the first time.

## 27. Enums Are Singletons per Constant — but Understand the Scope Properly

Each constant has a single instance managed by the JVM for the enum class within the appropriate classloader context. Therefore:

- `Mode.FAST` is shared across callers.
- `Mode.FAST.getClass()` can be a constant-specific anonymous subclass if it has a class body; `getDeclaringClass()` is the original enum class.
- Code reading/writing a mutable field on `FAST` has no per-request isolation.
- Do not use raw Java reflection or serialization hacks to try to create additional enum constants: this is not a publicly supported construction model.
- If a new object is required for each business operation, use a record/class combined with an enum field rather than adding per-request mutable state onto the constant.

### 27.1. Example Combining an Enum Constant with a Request Record

Save **`EnumWithRecordDemo.java`**:

~~~java
public class EnumWithRecordDemo {
    enum Kind {
        BASIC(1), PREMIUM(2);

        private final int multiplier;

        Kind(int multiplier) {
            this.multiplier = multiplier;
        }

        int multiplier() {
            return multiplier;
        }
    }

    record Order(Kind kind, int amount) {
        int total() {
            return amount * kind.multiplier();
        }
    }

    public static void main(String[] args) {
        Order a = new Order(Kind.BASIC, 10);
        Order b = new Order(Kind.PREMIUM, 10);

        System.out.println("basic=" + a.total());
        System.out.println("premium=" + b.total());
        System.out.println("same kind object=" +
                (a.kind() == Kind.BASIC));
        System.out.println("different order objects=" + (a != b));
    }
}
~~~

Run:

~~~bash
javac EnumWithRecordDemo.java
java EnumWithRecordDemo
~~~

Output:

~~~text
basic=10
premium=20
same kind object=true
different order objects=true
~~~

Kind constants are immutable configuration/strategy values; each Order record instance holds a different amount without mutating a global enum constant.

**Arithmetic note:** this is only an illustration with small integers; production monetary calculations require appropriate numeric types and rounding/overflow rules.

## 28. Debugging Enum Initialization and Constructors

When code involving an enum constructor fails, ask in sequence:

1. Does the constant declaration have arguments matching an overloaded constructor?
2. Is there a `;` to begin the enum body declarations?
3. Is the constructor access properly private or package-default (treated as private)?
4. Is there a prohibited explicit `super(...)` call?
5. Is there a direct static field reference to the enum itself inside a constructor/instance initializer that is not a constant variable?
6. Is there a helper method indirectly reading an uninitialized static map?
7. Is the static map/list built **after** the constants while avoiding an initialization cycle?
8. Is the constructor throwing an exception due to an invalid constant source value?
9. Do a field initializer and an instance block have an incorrect ordering dependency?
10. Is there a mutable field on a constant leading to different results across tests/threads?
11. Is an overridden `toString()` causing logs to differ from `name()`?
12. Is there a constant-specific class body causing `getClass()` to differ from the enum declaring class?
13. Is ordinal being used for an ID or logic where reordering constants alters the result?
14. Are there method signatures colliding with `values()`/`valueOf(String)` or attempts to override final methods of Enum?
15. Is an enum being used for multi-instance runtime data that should instead be a class/record?

### 28.1. Avoid Testing Results via Global Static Initialization Side Effects

A unit test that initializes an enum in test method A may cause constructor logs to appear only in A and not in test B, because the enum was already initialized earlier. Do not write tests assuming enum constructors run again on every constant access. Verify the **state/method contract** instead of counting class-initialization logs if you do not control the classloader.

## 29. Self-Testing Contract Program (Without JUnit)

Save **`EnumMembersContractTest.java`**:

~~~java
public class EnumMembersContractTest {
    enum Level {
        LOW(1), HIGH(5);

        private final int weight;

        Level(int weight) {
            if (weight <= 0) {
                throw new IllegalArgumentException("weight");
            }
            this.weight = weight;
        }

        int score(int base) {
            return base * weight;
        }
    }

    static void check(boolean ok, String description) {
        if (!ok) {
            throw new AssertionError(description);
        }
    }

    public static void main(String[] args) {
        check(Level.values().length == 2, "size");
        check(Level.valueOf("LOW") == Level.LOW, "identity");
        check(Level.LOW.score(3) == 3, "low score");
        check(Level.HIGH.score(3) == 15, "high score");
        check(Level.LOW.ordinal() == 0, "declaration order");
        check(Level.LOW.getDeclaringClass() == Level.class,
                "declaring class");

        System.out.println("all enum member checks passed");
    }
}
~~~

Run:

~~~bash
javac EnumMembersContractTest.java
java EnumMembersContractTest
~~~

Output:

~~~text
all enum member checks passed
~~~

The `check` method actually executes even when Java `assert` statements are disabled by default without `-ea`. These checks verify fields/constructors/methods/identity according to a specific source declaration; it does not attempt to measure internal constructor bytecode or classloader behavior.

## 30. Comparison Table: Which Fields and Methods Belong to the Enum Class, Constant, or Caller?

| Component | Scope / Meaning | Example |
| --- | --- | --- |
| Enum constant | A named instance initialized when the enum class is initialized | `Priority.HIGH` |
| Implicit constant field | `public static final EnumType`, implicitly declared by the compiler | `Priority.HIGH` field |
| Instance field | A field residing on each constant object | `private final int weight` |
| Instance method | Runs with a constant as receiver; uses `this` | `HIGH.score(10)` |
| Static field | Data belonging to the enum class, shared | `private static final Map BY_CODE` |
| Constant variable | `final` primitive/String initialized with a constant expression | `static final int FACTOR=10` |
| Static method | Called on the enum class, requiring no constant receiver | `HttpStatus.fromCode(404)` |
| Enum constructor | Initializes each constant; private/implicitly private | `Priority(int weight)` |
| Instance initializer | Runs when each constant object is created | `{ count++; }` |
| Static initializer | Runs when the enum class is initialized, after constant declarations | `static { fillLookup(); }` |
| Constant-specific body | Anonymous subclass of the enum for a single constant | `ADD { int calculate(...) {...} }` |
| Caller reference | A variable assigned a constant, without creating a new constant | `Priority p = Priority.HIGH` |

**Distinguishing "per constant instance" from "per caller variable":** because `HIGH` is a shared object, the instance field `weight` resides on the HIGH object and is **not** duplicated for every variable referencing HIGH.

## 31. Common Mistakes and How to Fix Them

| Misconception / Incorrect Practice | Correct According to Java 17 |
| --- | --- |
| "Enums only hold constants, with no fields/methods." | Enums can have fields, constructors, instance/static methods, and initializer blocks. |
| "`HIGH(9)` means creating a new object every time HIGH is used." | The constant object is created during enum class initialization, not on each field read. |
| "Enum constructors should be `public` so callers can create more values." | Public/protected enum constructors are prohibited; you cannot use `new` on an enum from callers. |
| "If no constructor is declared, the enum has no constructor." | The compiler provides a default private no-arg constructor. |
| "An enum constructor can call `super(...)` itself." | Explicit superclass constructor invocation is prohibited. |
| "The `;` after enum constants is always optional." | Required when body declarations follow. |
| "`static final Map` is a constant variable." | No; Map is not a primitive/String constant expression. |
| "The constructor can insert `this` into the enum's static map." | Direct reference to its own non-constant static field is prohibited; build the map after the constants. |
| "Using a helper method to read the map from the constructor is safe." | It can hide an initialization cycle, causing null/partial state. |
| "Static blocks and instance blocks both run for each constant." | Instance blocks run per constant; static blocks run per enum class. |
| "All static fields are ready before enum constants." | Explicit static initializers run after the constant declarations. |
| "A parameterized constructor overload automatically creates a no-arg overload." | No; you must declare a separate no-arg constructor if constants use empty args. |
| "`this(...)` constructor chaining is prohibited just like `super(...)`." | `this(...)` is valid under constructor chaining rules. |
| "Every enum constant must have a class body." | No; a body is only needed for custom behavior or implementing abstract methods. |
| "A constant-specific body has its own constructor." | No; the body is an anonymous class and cannot declare constructors. |
| "An abstract enum method can be skipped on one constant." | Every constant must implement a concrete method according to the JLS. |
| "A constant's `getClass()` always equals enum.class." | It can differ with a constant-specific body; use `getDeclaringClass()`. |
| "`toString()` always equals `name()`." | toString can be overridden; name is final. |
| "`valueOf` accepts a translated display label." | It accepts the declared constant name, case-sensitively. |
| "`ordinal()` is a stable business ID." | It depends on declaration order; do not use it to persist IDs. |
| "Enum instance fields are duplicated per caller reference." | Each constant only has its own object/shared instance field; aliases see the same state. |
| "`private final List/array` is automatically deeply immutable." | The reference is final, while mutable elements can still change; defensively copy when needed. |
| "Enums cannot implement interfaces." | An enum can implement interfaces. |
| "An enum declares its own generic type parameter `enum E<T>`." | An enum declaration cannot have a type parameter list. |
| "Tests invoke the enum constructor again every time." | The constructor runs when the constant is initialized and is not re-invoked by callers. |

## 32. Short Exercises with Answers

**Question 1.** Does `enum Size { SMALL, LARGE }` have a constructor?  
**Answer:** Yes, it has a default private no-arg constructor implicitly declared by the compiler.

**Question 2.** How does `enum Coin { A(1); private Coin(int n) {...} }` create A?  
**Answer:** The compiler creates the enum constant A when the enum class is initialized and passes 1 to the constructor.

**Question 3.** Is writing `public Coin(int n)` valid?  
**Answer:** No, an enum constructor cannot be public/protected.

**Question 4.** What is an enum constructor without a written access modifier treated as?  
**Answer:** `private` according to the JLS.

**Question 5.** Can you call `super("A",0)` inside an enum constructor?  
**Answer:** No, explicit superclass constructor calls are prohibited.

**Question 6.** Can you overload enum constructors and use `this(...)`?  
**Answer:** Yes, following constructor chaining rules.

**Question 7.** When an enum has fields/methods after its constants, what punctuation is required?  
**Answer:** A `;` immediately after the constants.

**Question 8.** What does `private final int weight` inside an enum belong to?  
**Answer:** Each constant object has its own instance field.

**Question 9.** Can `static final int FACTOR=10` be used from an enum constructor?  
**Answer:** Yes, if it is a constant variable initialized from a constant expression.

**Question 10.** Is `static final Integer BOXED=Integer.valueOf(10)` a constant variable?  
**Answer:** No, Integer is not a primitive/String constant-variable type.

**Question 11.** Can a `static final Map` be used directly from an enum constructor?  
**Answer:** No, a direct reference to its own non-constant static field is prohibited by the JLS in constructors/instance initializers.

**Question 12.** Then when should a static lookup map be built?  
**Answer:** In a static initializer after the enum constants have been created.

**Question 13.** In what order are constant objects created?  
**Answer:** In the declaration order of the constants when the enum class is initialized.

**Question 14.** Does a static initializer run for each constant?  
**Answer:** No, it runs once during class initialization.

**Question 15.** When do instance initializers and instance field initializers run relative to the constructor body?  
**Answer:** In source order before the constant's constructor body, after the superclass chain.

**Question 16.** Is `new EnumType()` allowed from application code?  
**Answer:** No.

**Question 17.** Does `values()` recreate enum constants?  
**Answer:** No; it returns a new array containing references to the existing constants.

**Question 18.** Does `valueOf("PENDING")` use `toString()` or `name()`?  
**Answer:** It looks up by constant name, not by a translated/custom toString.

**Question 19.** Can `name()` be overridden?  
**Answer:** No, name is final in Enum.

**Question 20.** Can `toString()` be overridden?  
**Answer:** Yes, to display a label different from the constant name if needed.

**Question 21.** Can you override `equals` or `hashCode` to compare field values?  
**Answer:** No, Enum defines final identity semantics for those methods.

**Question 22.** Is `ordinal()` safe to use as a database code?  
**Answer:** You should not; reordering or adding constants changes the ordinal.

**Question 23.** If an enum has an abstract method, is a constant without a class body valid?  
**Answer:** No, every constant must provide an implementation.

**Question 24.** Can a constant-specific class body declare its own constructor?  
**Answer:** No, it is an anonymous class body.

**Question 25.** Why might `getClass()` of ADD with a class body not equal `Operation.class`?  
**Answer:** ADD has an anonymous subclass runtime class, though its declaring enum is still Operation.

**Question 26.** If two variables reference `Feature.CACHE`, is a change to a mutable field through the first variable visible through the second variable?  
**Answer:** Yes, they refer to the same enum constant object.

**Question 27.** Can an enum implement a `Transformer` interface?  
**Answer:** Yes, and then the enum constant can be used through an interface reference.

**Question 28.** Can an enum have generic type parameters such as `enum Box<T>`?  
**Answer:** No, but it can implement a generic interface with concrete type arguments.

**Question 29.** What are `EnumSet` and `EnumMap` useful for?  
**Answer:** Specialized collection structures for sets of enum constants and enum keys.

**Question 30.** If an enum constant needs separate runtime data per request, what should you do?  
**Answer:** Use a separate record/class holding the enum key and per-request fields, rather than mutating a global constant.

**Question 31.** Is `final int[] colors` enough to make an enum deeply immutable?  
**Answer:** No; clone input/output if you need to isolate the mutable array representation.

**Question 32.** Should an enum constructor open a network/database connection by default?  
**Answer:** Usually not; keep the constructor lightweight, assign metadata/validate, and manage services in a separate lifecycle.

**Question 33.** If class initialization fails because an enum constructor throws, can you just access another constant to fix it?  
**Answer:** No; enum class initialization can fail, and subsequent uses in the classloader will suffer the consequences; fix the configuration/code.

**Question 34.** What is the core takeaway about enum fields, methods, and constructors?  
**Answer:** Constants are finite instances, private constructors assign state to each constant, methods provide behavior, and shared static state is only initialized after constants in accordance with JLS restrictions.

## 33. Design Checklist for Stateful Enums

- [ ] Do the enum constants represent a finite and relatively stable set of values?
- [ ] Do each constant's arguments match the constructors (including overloads)?
- [ ] If the body has fields/methods, is there a `;` after the constants?
- [ ] Does the constructor avoid writing `public`/`protected` or an explicit `super(...)`?
- [ ] Do instance fields hold appropriate immutable values, or are there mutable aliases?
- [ ] Is the validation of constant arguments simple, deterministic, and free of external resource dependencies?
- [ ] Do fields that must remain stable use `private final` and appropriate defensive copying?
- [ ] Do instance field initializers/blocks and the constructor body have the proper dependency order?
- [ ] Do the constructor/instance initializers avoid directly reading a non-constant static field of the enum itself?
- [ ] Is there any helper method indirectly causing circular static initialization?
- [ ] Is the static lookup table built after the constants and does it detect duplicate codes?
- [ ] Are static methods and instance methods assigned their proper responsibilities?
- [ ] Are constant-specific behaviors actually cleaner than a switch?
- [ ] If there is an abstract method, have all constants implemented it properly?
- [ ] Does a method need `toString()` for display, or should there be a separate `label()`?
- [ ] Is persistence/API using a stable business code instead of `ordinal()`?
- [ ] Is `valueOf` used properly with the exact constant name, with unknown input handled?
- [ ] Are there shared mutable state risks when the enums are used across multiple threads?
- [ ] Are `EnumSet`/`EnumMap` applied where appropriate?
- [ ] Are there tests for identity, constructor state, methods, and initialization order (if needed)?
- [ ] If the type needs per-request state or unbounded instances, have you considered a record/class instead of an enum?

## 34. References

- Java Language Specification Java SE 17, [`8.9 — Enum Classes`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.9): nature of enums and the set of constants.
- JLS Java SE 17, [`8.9.1 — Enum Constants`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.9.1): constructor arguments and constant-specific class bodies.
- JLS Java SE 17, [`8.9.2 — Enum Body Declarations`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.9.2): constructor visibility, explicit superclass call prohibition, own static field reference restriction.
- JLS Java SE 17, [`8.9.3 — Enum Members`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.9.3): implicit constant fields, `values()`, `valueOf(String)`.
- JLS Java SE 17, [`4.12.4 — final Variables`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): concept of a *constant variable*.
- JLS Java SE 17, [`12.4 — Initialization of Classes and Interfaces`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4): active use/class initialization rules.
- JLS Java SE 17, [`12.5 — Creation of New Class Instances`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.5): instance initialization order.
- Java API SE 17, [`java.lang.Enum`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Enum.html): `name`, `ordinal`, `compareTo`, `getDeclaringClass`, and identity semantics.
- Java API SE 17, [`java.util.EnumSet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/EnumSet.html): specialized constant set.
- Java API SE 17, [`java.util.EnumMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/EnumMap.html): specialized map for enum keys.
- Java API SE 17, [`java.util.Map.copyOf`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map)): unmodifiable lookup map snapshots.

## Conclusion

**An enum is more than just a list of constants**: it is a special class in which **each constant is an instance created by Java during enum class initialization**. A `private` or implicitly private constructor receives the arguments declared on each constant, initializes instance fields, and performs validation. Enums can have instance/static methods, initializer blocks, interfaces, constant-specific anonymous subclasses, and static lookup tables.

Three key takeaways to remember:

1. **Enum constructors are not for callers:** no `new` from outside, no public/protected constructors, and no explicit `super(...)`. Constructor overloading with `this(...)` is valid.
2. **Initialization happens in proper order:** constants are created in declaration order; instance fields/blocks run before the constructor body for each constant, and explicit static initializers run after the constants. Do not read a non-constant own static field directly in an enum constructor/instance initializer; build static lookup maps after the constants.
3. **Fields should represent stable state and methods should represent behavior:** prefer `private final` immutable data, guard against mutable aliases when needed, use business codes instead of ordinal for persistence, and avoid turning enum constants into global mutable objects.

When designed according to these principles, an enum becomes a *type-safe set of named instances with behavior* — cleaner than integer/string constants, harder to put into an invalid state, and easy to test in Java 17+.
