# Compile-Time Constants and `static final` Constants in Java 17+

In Java, `final` means **the variable cannot be reassigned after a valid assignment**, but it does not mean every `final` value is determined at compile time.

Specifically, **`static final` does not automatically equal "compile-time constant"**. A `static final` field can receive its value from a fixed calculation or from a method that must run when the class is initialized. The two cases have different effects on syntax checking, class initialization, and compiled bytecode.

## 1. Three Concepts to Distinguish

| Concept | Practical definition | Example |
| --- | --- | --- |
| `final` variable | A variable assigned according to `final` rules, cannot be reassigned after initialization | `final int count = readCount();` |
| `static final` field | Belongs to the class and cannot be reassigned after initialization; value may be computed at runtime | `static final int LIMIT = Integer.parseInt("12");` |
| *Constant variable* (compile-time constant variable) | A `final` variable of primitive type or `String`, initialized with a **constant expression** | `static final int LIMIT = 3 * 4;` |

By language definition, a *constant variable* **does not have to be `static`**: `final int x = 2 + 3;` inside a method can also satisfy the definition. However, shared application constants are typically placed in `static final` fields.

**Mnemonic formula:**

~~~text
final + (primitive or String type) + constant expression
                      │
                      ▼
              constant variable

static final but missing one of the conditions above
                      │
                      ▼
           not a constant variable
~~~

A "constant expression" is an expression that Java's rules allow evaluating at compile time, such as literals, certain operators on constants, constant string concatenation, or references to other constant variables. **Calling a regular method is not a constant expression**, even if the method always returns the same number.

## 2. Valid Examples vs. Non-Compile-Time Constants

~~~java
static final int MAX_USERS = 2 * 3;              // Constant variable.
static final String TITLE = "Java " + 17;        // Constant variable.
static final double RATE = 0.05;                 // Constant variable.

static final int CONFIG = Integer.parseInt("12"); // Initialized at runtime.
static final Integer BOXED = 12;                  // Wrapper, not primitive/String.
static final int[] SCORES = {4, 5};               // Array is a reference type.
static final String BUILT = new String("Java");  // Calls new, not a constant expression.
~~~

All the fields above are `static final`. Yet **only the first three** meet the definition of a *constant variable*.

### `static final` Does Not Mean "Immutable Object"

~~~java
static final int[] NUMBERS = {1, 2};

// NUMBERS = new int[]{3, 4}; // Invalid: cannot reassign a final reference.
NUMBERS[0] = 99;              // Valid: modifies array element.
~~~

`final` prevents reassigning the **reference variable**, not freezing the data of the referenced object. Therefore, you should not expose a `public static final` array assuming external code cannot modify its elements.

Additionally, a `static final` field can be assigned inside a **static initializer** following the rules, rather than having an initializer at declaration. That case usually does not produce a *constant variable*; some `final` fields can also be determined from configuration when the class is initialized.

## 3. Runnable Java 17+ Program: Observing Class Initialization

Create the file **`CompileTimeConstantsDemo.java`**:

~~~java
public class CompileTimeConstantsDemo {
    static class Settings {
        static final int MAX_USERS = 2 * 3;
        static final String LABEL = "Java " + 17;

        static final int RUNTIME_LIMIT = Integer.parseInt("12");
        static final int[] SCORES = {4, 5};

        static {
            System.out.println("Settings initialized");
        }
    }

    public static void main(String[] args) {
        final int local = 3 * 4;

        System.out.println("maxUsers=" + Settings.MAX_USERS);
        System.out.println("label=" + Settings.LABEL);
        System.out.println("local=" + local);

        System.out.println("runtimeLimit=" + Settings.RUNTIME_LIMIT);

        Settings.SCORES[0] = 90;
        System.out.println("score0=" + Settings.SCORES[0]);
    }
}
~~~

In PowerShell on Windows or Bash on Linux, open the directory containing the file and run:

~~~bash
java -version
javac -version
javac -encoding UTF-8 CompileTimeConstantsDemo.java
java CompileTimeConstantsDemo
~~~

**Expected output:**

~~~text
maxUsers=6
label=Java 17
local=12
Settings initialized
runtimeLimit=12
score0=90
~~~

**Why does the class initialization line appear in the middle?**

1. `MAX_USERS` and `LABEL` are *constant variables*. When code accesses them via `Settings.MAX_USERS` and `Settings.LABEL`, the compiler can inline the constant values directly; **merely reading them does not force `Settings` to initialize**.
2. `local` is a `final int` variable with constant expression `3 * 4`; it is not a `static` field itself.
3. `RUNTIME_LIMIT` is not a constant variable because its initializer calls `Integer.parseInt(...)`. The first read of this field via `Settings.RUNTIME_LIMIT` triggers initialization of `Settings` (if not yet initialized). At that point, static initialization code runs in order, prints `Settings initialized`, and only then does `main` print `runtimeLimit=12`.
4. The `SCORES` array is created during class initialization. Even though the reference is `final`, `SCORES[0] = 90` is completely valid.

Note: "not initializing the class when reading a constant" is a rule specifically for **accessing a constant variable**, and does not apply to all ways of using a class (`new`, calling an appropriate `static` method, or reading a non-constant `static` field can trigger initialization).

## 4. Practical Consequence: Constants Can Be Inlined into Caller Code

The compiler can **directly embed** the value of a *constant variable* when compiling a class that uses it. For example, in a library:

~~~java
public class LibraryConfig {
    public static final int LIMIT = 10;
}
~~~

Another class:

~~~java
public class Client {
    public static void main(String[] args) {
        System.out.println(LibraryConfig.LIMIT);
    }
}
~~~

When compiling `Client` against `LIMIT = 10`, `Client`'s bytecode may contain the value `10` itself instead of reading the field at runtime. If the library later changes `LIMIT = 20` and **only recompiles `LibraryConfig`**, the old `Client.class` file may **still print 10**.

**How to handle:** when changing a public constant variable in a library, **recompile the dependent classes** and republish dependent artifacts. This is why you should not casually use `public static final` constant variables for values expected to change across deployment versions.

With `static final int LIMIT = loadFromConfiguration();` (initializer calls a method), the value is not a *compile-time constant* and field access happens at runtime. However, it is still typically initialized only **once per class initialization**, and does not automatically update when a config file changes.

## 5. When Does the Compiler Require a Constant Expression?

An easily verifiable case in Java 17 is a traditional `switch` `case` label:

~~~java
static final int OK = 2 * 3;                // Constant variable.
static final int DYNAMIC = Math.max(5, 6); // Not a constant variable.

// Inside a method:
int status = 6;
switch (status) {
    case OK:
        System.out.println("OK"); // Valid.
        break;
    // case DYNAMIC: // Invalid: not a constant expression.
    default:
        System.out.println("Khac");
}
~~~

`case OK:` is accepted because `OK` is a *constant variable*, whereas `DYNAMIC` is rejected in this kind of `case` label because calling `Math.max` is not a constant expression.

This is why declaring a value `final` is not enough to use it in every context requiring a **compile-time constant**.

## 6. Common Errors and Misconceptions

| Misconception / situation | Reality | What to do |
| --- | --- | --- |
| "Having `static final` makes it a constant variable" | False: the initializer and type must also meet conditions | Check primitive/`String` type and constant expression |
| "`Integer` is the same as `int`" | `Integer` is a reference wrapper type | Use `int` if a primitive constant variable is needed |
| "`new String("x")` is a constant because content is fixed" | `new` is not a constant expression | If a compile-time constant is needed, use `"x"` |
| "`final int[]` is an immutable array" | Only the `final` variable's reference cannot change | Restrict access, use an appropriate immutable structure |
| "Changing `LIMIT` in the library is enough" | Compiled callers may still hold the old value | Rebuild and republish dependent code |
| "Reading any `static` field initializes the class" | Reading a constant variable is a notable exception | Distinguish compile-time constant fields from runtime fields |
| "`final` always allows use as a `case` label" | Labels in the example require a constant expression | Use a valid literal/constant variable |

### Naming Convention

Shared constants are usually written in uppercase with underscores, such as `MAX_USERS`, `DEFAULT_TIMEOUT_SECONDS`, `APP_NAME`. This is a **convention**, not a compiler requirement: `static final int maxUsers = 6;` is still valid and can still be a constant variable.

## 7. Short Exercises

**Exercise 1 — Classification.** Which ones are *constant variables*?

~~~java
static final int A = 1 + 2;
static final int B = Integer.parseInt("3");
static final String C = "Hi" + " Java";
static final String D = new String("Hi");
static final Integer E = 3;
~~~

*Answer:* `A` and `C`. `B` calls a method; `D` uses `new`; `E` is a wrapper.

**Exercise 2 — Reading output.** Why did `Settings initialized` in the example only print right before `runtimeLimit=12`, and not before `maxUsers=6`?

*Answer:* The two constant variables were used without forcing the `Settings` class to initialize; reading the non-constant static field `RUNTIME_LIMIT` triggered initialization.

**Exercise 3 — Testing immutability.** Given `static final int[] VALUES = {1, 2};`, which statement is valid: `VALUES[0] = 5;` or `VALUES = new int[]{5, 6};`?

*Answer:* Only the first statement is valid: elements can be modified, while the `final` reference variable cannot be reassigned.

**Exercise 4 — Library change.** A compiled program uses `public static final int VERSION = 1;`. Why might changing it to `2` in the library without rebuilding the client still print `1`?

*Answer:* The constant variable's value may have been inlined into the client's bytecode at compile time.

## Retention Checklist

- [ ] Distinguish `final`, `static final`, and *constant variable*.
- [ ] State all three conditions: `final` + primitive/`String` + constant expression.
- [ ] Know that method calls / `new` usually prevent an initializer from being a constant expression.
- [ ] Understand why merely accessing a constant variable does not force the declaring class to initialize.
- [ ] Recognize that `final` on a reference does not mean an immutable object.
- [ ] Know to recompile dependent code when changing a public constant that may be inlined.
- [ ] Run `CompileTimeConstantsDemo.java` and explain all six lines of output.

**Conclusion:** `static final` expresses **a non-reassignable class-level variable**, while *constant variable* is a special case Java identifies from **type and constant expression**. Distinguish these two concepts to understand class initialization, immutability, `switch case`, and the impact on published `.class` files.
