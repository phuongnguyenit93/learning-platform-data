# Compile-Time Constants, Constant Folding, and the Risk of Stale Values

In Java, not every value declared `final` is a **compile-time constant**. Some expressions can be fully determined by `javac` from source code, and the values of qualifying `static final` fields can be **written directly into the class file of calling code**. This makes using constants efficient but creates a trap: **the library changes the constant's value, yet classes compiled against an older version may continue using the old value until recompiled**.

This lesson clarifies three related yet non-identical concepts: **constant expression** per the Java Language Specification (JLS), **constant variable**, and **constant folding/inlining** during compilation. Then we reproduce the stale-value bug ourselves, inspect bytecode, and apply appropriate configuration, build, and dependency management practices.

## 1. Three Concepts to Distinguish

| Concept | Exact Meaning | Example |
| --- | --- | --- |
| Constant expression | An expression of primitive type or `String`, satisfying the set of expressions/operators/constant names permitted by JLS `15.29 and determinable at compile time | `2 * 3 + 1`, `"Ja" + "va"` |
| Constant variable | A variable of primitive type or `String`, declared `final` and initialized with a **constant expression** (JLS `4.12.4) | `static final int LIMIT = 3;` |
| Constant folding | Evaluating/simplifying expressions whose results are already determined, allowing constants to be written directly into bytecode instead of a sequence of operations | `2 + 3` can become the value `5` |
| Constant value inlining | Code using a constant field embeds the **value baked in at compile time**, rather than reading the declaring class's field at runtime | A client using `Config.LIMIT` compiled with `LIMIT = 3` may keep `3` |
| Runtime evaluation | Values computed when the program runs or when a class is initialized | `Integer.parseInt("3")`, `System.getenv(...)` |

**Constant folding** is a common term for the code transformation; **constant expression** and **constant variable** are concepts with specific rules in the JLS. You should not conclude that "the compiler can guess the value" is enough for an expression to be a constant expression in the Java language.

For example, `final int x = Integer.parseInt("3");` is a value that does not change after assignment, yet the call `Integer.parseInt` does not belong to the JLS forms of constant expressions. The value of `x` is only produced when the execution path runs the initializer expression.

## 2. What Is a Constant Expression According to the JLS?

JLS `15.29 defines a compile-time constant expression as an expression of primitive type or `String` that uses only permitted constructs. Common categories:

- Literals: integer, floating-point, character, boolean, string literals, and text blocks.
- Arithmetic operators `+`, `-`, `*`, `/`, `%`; unary `+`/`-`.
- Bit shifts `<<`, `>>`, `>>>` and bitwise operators `&`, `|`, `^`, `~`.
- Comparisons `<`, `<=`, `>`, `>=`, `==`, `!=`; logical `&&`, `||`, `!`.
- Conditional operator `? :`, parentheses, and casts to primitive/`String` permitted by the JLS.
- Names of `final` variables that qualify as **constant variables**, which can participate in other constant expressions.

Valid examples:

```java
static final int TWO = 2;
static final int RESULT = (TWO + 3) * 4;       // 20
static final boolean ENABLED = TWO < 5 && true; // true
static final String LABEL = "Java" + " " + 17;  // "Java 17"
static final long SHIFTED = 1L << 8;           // 256
```

These are illustrative declarations inside a class, **not a standalone program**. In all of these declarations, the field type is primitive or `String`, has `final`, and the initializer is a constant expression.

Cases that are not constant expressions:

```java
static final int PARSED = Integer.parseInt("20");
static final String ENV = System.getenv("APP_MODE");
static final String BUILT = new String("Java");
static final Integer BOXED = Integer.valueOf(20);
static final long TIME = System.nanoTime();
static final int[] TABLE = {1, 2, 3};
```

- Containing a method call (`parseInt`, `getenv`, `nanoTime`, `valueOf`), the `new` operator, or an array initializer: not eligible.
- `Integer` is neither primitive nor `String`, so `static final Integer BOXED` cannot be a constant variable by the definition above, even though the reference held in the field is `final`.
- `final int[] TABLE` only prevents **reassigning the reference variable** after initialization; it does not make the array elements immutable.

Also distinguish: **`final` does not by itself make an object immutable**. An object's immutability depends on its API, class design, and whether state can be mutated.

### A final Local Variable Can Be a Constant Variable

```java
final int base = 4;
final int squared = base * base;  // 16, constant expression
```

The variable `base` has a primitive type, `final`, and a constant expression initializer; therefore it is a constant variable even inside a method. Conversely:

```java
int argument = 4;
final int squared = argument * argument;
```

`squared` is still assigned only once, yet **is not a compile-time constant variable**, because `argument` is an ordinary variable and the initializer is not a constant expression.

**Note:** regarding the phenomenon of clients keeping stale constants when a JAR is swapped, what matters particularly are **`static` fields that are constant variables** compiled and referenced from another class (JLS `13.4.9); do not equate every local `final` variable with a public field in an API.

## 3. Runnable Example: Folding, String, and Addition Order

Create file `FoldingDemo.java`:

```java
public class FoldingDemo {
    static final int BASE = 2 + 3;
    static final int SQUARE = BASE * BASE;
    static final String GREETING = "Xin" + " chào";
    static final String WORD = "Ja" + "va";

    public static void main(String[] args) {
        System.out.println(BASE);
        System.out.println(SQUARE);
        System.out.println(GREETING);
        System.out.println("Java" == WORD);
        System.out.println(1 + 2 + "x");
        System.out.println("x" + 1 + 2);
        System.out.println(Integer.MAX_VALUE + 1);
    }
}
```

Compile and run with JDK 17+:

```bash
javac --release 17 -encoding UTF-8 -d out FoldingDemo.java
java -cp out FoldingDemo
```

Stdout:

```text
5
25
Xin chào
true
3x
x12
-2147483648
```

Part-by-part explanation:

1. `BASE = 2 + 3` is a constant expression and evaluates to `5`. Because `BASE` is a constant variable, `SQUARE = BASE * BASE` is also determined at compile time as `25`.
2. `GREETING` and `WORD` are both `String` constant variables; concatenating eligible constant parts yields `"Xin chào"` and `"Java"`.
3. The result `"Java" == WORD` is `true` per the **interning rule for String constant expressions** in JLS `15.29. This is a specified language behavior; in general application code, compare string **contents** with `equals`, not `==`.
4. `1 + 2 + "x"` is evaluated left-to-right: integer addition `1 + 2` produces `3` first, then concatenates to `"3x"`. `"x" + 1 + 2` starts as string concatenation and thus produces `"x12"`.
5. `Integer.MAX_VALUE + 1` uses 32-bit `int` arithmetic: it overflows per Java rules and produces `-2147483648`, **without automatically throwing an exception for int overflow**.

These are Java 17+ language results, not a claim that every compiler must emit the exact same sequence of bytecode. A compiler may represent constants using `iconst`, `bipush`, `ldc`, or equivalent instructions allowed by the JVM; the exact choice depends on the class file and toolchain.

### Constant Folding Must Not Alter Expression Order or Types

String concatenation `1 + 2 + "x"` and `"x" + 1 + 2` differ because addition and string concatenation have specific type rules, associativity, and operand ordering. You must not take an algebraic transformation valid for numbers and arbitrarily alter the result of a program that has already transitioned to type `String`.

Likewise, primitive arithmetic has overflow rules and floating-point characteristics; the compiler may not arbitrarily alter the observable behavior of an expression merely because it sees a potential "optimization".

## 4. Why Is public static final Sometimes Embedded into the Client?

Consider a library class:

```java
public class Config {
    public static final int LIMIT = 3;
    public static final String MODE = "safe";
}
```

These two fields are **static constant variables**. When another class compiles the calls:

```java
System.out.println(Config.LIMIT);
System.out.println(Config.MODE);
```

The compiler uses **the values at the time the client was compiled** according to the rules for constant variables. The client's class file may directly embed `3` and `"safe"`, without needing to read the `Config.LIMIT` or `Config.MODE` fields at runtime.

That leads to an important consequence:

> If you change `Config.LIMIT` from `3` to `7`, recompile only `Config.class`, and distribute the new JAR, **client code compiled against the old value may continue using `3`** until the client itself is recompiled.

JLS `13.4.9 describes this exact scenario: changing the value of a `static` field that is a constant variable **does not necessarily stop old binaries from running**, yet old binaries will not automatically see the new value. This is **binary compatibility regarding linking/execution**, not **value synchronization**.

Do not confuse this mechanism with data caching, thread-locals, a classloader "reading wrongly", or JIT holding code too long. In this simple example, **the old value was already embedded inside `Consumer.class`** when the compiler processed the client code.

## 5. Hands-On Reproduction of the Stale-Value Risk: Two Compilation Passes

This section is a complete experiment with **two independent source files** and two class output directories. The goal is to witness **the library changing values while the client is not rebuilt**, rather than only reading theoretical descriptions.

### 5.1. Initial Structure

Create a working directory containing:

```text
constant-lab/
  libsrc/
    Config.java
  clientsrc/
    Consumer.java
  out/
    lib/          (will be created by javac)
    client/       (will be created by javac)
```

In `libsrc/Config.java` (version V1):

```java
public class Config {
    public static final int LIMIT = 3;
    public static final String MODE = "safe";
    public static final Integer BOXED = Integer.valueOf(3);

    public static int currentLimit() {
        return LIMIT;
    }
}
```

In `clientsrc/Consumer.java`:

```java
public class Consumer {
    public static void main(String[] args) {
        System.out.println("direct-limit=" + Config.LIMIT);
        System.out.println("direct-mode=" + Config.MODE);
        System.out.println("method-limit=" + Config.currentLimit());
        System.out.println("boxed=" + Config.BOXED);
    }
}
```

Why use all four expressions?

| Expression | Compile-time constant? | How is it read at runtime? |
| --- | --- | --- |
| `Config.LIMIT` | Yes, `static final int` field initialized with literal `3` | Value may be embedded in the client |
| `Config.MODE` | Yes, `static final String` field initialized with literal `"safe"` | Value may be embedded in the client |
| `Config.currentLimit()` | **No**: method invocation | Runtime invokes the method on the loaded version of `Config.class` |
| `Config.BOXED` | **No**: `Integer` is not a constant variable type | Runtime reads the field from the loaded `Config` class |

**Attention:** `BOXED` is an `Integer` object, not a primitive `int`; the field is only `final` as a reference, and the initializer `Integer.valueOf(3)` is a method call. Whether the JIT optimizes access/boxing does not change the constant variable rules across separate binaries.

### 5.2. Compiling Library V1 and Client V1

Stand inside the `constant-lab` directory and run:

```bash
javac --release 17 -encoding UTF-8 -d out/lib libsrc/Config.java
javac --release 17 -encoding UTF-8 -cp out/lib -d out/client clientsrc/Consumer.java
java -cp "out/client:out/lib" Consumer
```

The `java` command above uses the **`:` separator for Linux/macOS**. On Windows PowerShell or cmd, run:

```powershell
java -cp "out/client;out/lib" Consumer
```

Stdout of V1:

```text
direct-limit=3
direct-mode=safe
method-limit=3
boxed=3
```

There are two key points in the second compile command:

1. `-cp out/lib` lets `javac` find the `Config` class declaration and constant values when **compiling Consumer**.
2. Once `Consumer.class` is created, compile-time constants have already been used to emit bytecode; at runtime, `Consumer` does not necessarily look up `Config`'s constant fields again.

### 5.3. Updating Only the Library to V2

Replace the contents of `libsrc/Config.java` with the **exact** code:

```java
public class Config {
    public static final int LIMIT = 7;
    public static final String MODE = "fast";
    public static final Integer BOXED = Integer.valueOf(7);

    public static int currentLimit() {
        return LIMIT;
    }
}
```

Recompile **only** the library:

```bash
javac --release 17 -encoding UTF-8 -d out/lib libsrc/Config.java
```

**Do not** re-run `javac ... clientsrc/Consumer.java` at this step. Keeping `out/client/Consumer.class` unchanged is essential to reproduce the issue.

Now run V2 of the library with the old client binary:

Linux/macOS:

```bash
java -cp "out/client:out/lib" Consumer
```

Windows:

```powershell
java -cp "out/client;out/lib" Consumer
```

Stdout **expected and verified using JDK 21 with `--release 17`**:

```text
direct-limit=3
direct-mode=safe
method-limit=7
boxed=7
```

Exact explanation:

- `direct-limit=3` and `direct-mode=safe`: the **old** `Consumer.class` binary carries V1's compile-time values. Replacing the class file on the library side does not modify the client binary.
- `method-limit=7`: the JVM invokes `Config.currentLimit()` **from the loaded V2**, and V2's method returns `7`.
- `boxed=7`: at runtime, accessing `Config.BOXED` reads the field from the V2 runtime class; because this field is not a static constant variable, the client did not embed literal `3` via the constant variable mechanism.

This is a practical example of a library change that **does not break binary linking** yet causes the values observed by each client to **differ** depending on when it was compiled.

### 5.4. Recompiling the Client to Receive V2 Values

After library V2 is compiled, re-run the client build command:

```bash
javac --release 17 -encoding UTF-8 -cp out/lib -d out/client clientsrc/Consumer.java
```

Then run `Consumer` using the OS-appropriate classpath as above. Stdout:

```text
direct-limit=7
direct-mode=fast
method-limit=7
boxed=7
```

At this point both the client's compiler inputs and the runtime see V2, so the values agree. In a multi-module build, simply replacing a library JAR **does not guarantee** all consumer modules are recompiled. Check the build graph, incremental builds, caches, and actual deployed artifacts.

## 6. Using javap to Prove the Values Are Already Inside the Class File

After generating `Consumer.class` with V1, **before rebuilding the client**, try:

```bash
javap -classpath out/client -c Consumer
```

On modern JDKs, the output typically shows meaningful lines such as the following (this is a **structural illustration**; exact bytecode offsets and constant-pool indices may vary):

```text
ldc           // String direct-limit=3
...
ldc           // String direct-mode=safe
...
invokestatic  // Method Config.currentLimit:()I
...
getstatic     // Field Config.BOXED:Ljava/lang/Integer;
```

Because of how string concatenation is compiled, the compiler may merge the literal `"direct-limit=" + Config.LIMIT` into a single constant `"direct-limit=3"`. Thus you do not necessarily see a separate instruction loading integer `3`; you may see **the entire post-folding string**.

What to look for when reading bytecode:

1. For the two `direct-...` lines, you can see a **literal** carrying the V1 value and **no `getstatic Config.LIMIT`/`getstatic Config.MODE`** for those usages.
2. For `Config.currentLimit()`, there will be a corresponding method invocation such as `invokestatic`.
3. For `Config.BOXED`, there will be a corresponding field access such as `getstatic`.
4. After updating only the library to V2, re-running `javap ... Consumer` still shows the V1 picture: the client's class file has not changed.
5. After recompiling the client, the values in the literals change to V2.

Running `javap -v Config` can show the `ConstantValue` attribute of certain constant fields in the class file. `ConstantValue` is an important class-file detail when the compiler emits constant fields, yet **does not by itself guarantee every consumer will read the field at runtime**. You must inspect **the consumer's bytecode** to know whether it uses a literal or a field access.

Exact bytecode may differ by `javac` version, especially for string concatenation (`invokedynamic` is a common implementation). Read instruction semantics rather than forcing every offset and index to match.

## 7. final Is Not Synonymous with Constant Variable

A field with `final` that **does not satisfy the type and initializer rules** will not be a compile-time constant variable.

Complete example `FinalKinds.java`:

```java
public class FinalKinds {
    static final int COMPILE_TIME = 2 * 3;
    static final int RUN_TIME = Integer.parseInt("7");
    static final Integer WRAPPER = Integer.valueOf(8);

    public static void main(String[] args) {
        System.out.println(COMPILE_TIME);
        System.out.println(RUN_TIME);
        System.out.println(WRAPPER);
    }
}
```

Compile and run:

```bash
javac --release 17 -encoding UTF-8 -d out FinalKinds.java
java -cp out FinalKinds
```

Stdout:

```text
6
7
8
```

All three values are never reassigned after initialization, yet:

- `COMPILE_TIME` is `static final int` with a constant expression initializer, qualifying as a constant variable.
- `RUN_TIME` is `static final int` yet has an `Integer.parseInt` call, so it is computed when the class initializes, not a constant variable.
- `WRAPPER` is `static final Integer`; `Integer` is a reference type and not `String`, so it is not a constant variable.

**Distinguish status:** `final` governs assignment rules; **constant variable** enforces a stricter language condition. `final` also does not guarantee that a configuration value is safe to change across distributed library versions.

## 8. Compile-Time Constants and Class Initialization

Reading a `static` field that is a constant variable does not force the JVM to initialize the declaring class solely because of that constant read (per the class initialization rules of JLS `12.4.1). Meanwhile, accessing a `static` field that is **not** a constant variable can be an action that triggers class initialization.

Create file `InitializationDemo.java`:

```java
class Settings {
    static {
        System.out.println("Settings initialized");
    }

    static final int CONSTANT = 2 * 3;
    static final int RUNTIME_VALUE = Integer.parseInt("7");
}

public class InitializationDemo {
    public static void main(String[] args) {
        System.out.println(Settings.CONSTANT);
        System.out.println(Settings.RUNTIME_VALUE);
    }
}
```

Compile and run:

```bash
javac --release 17 -encoding UTF-8 -d out InitializationDemo.java
java -cp out InitializationDemo
```

Stdout:

```text
6
Settings initialized
7
```

Why is this order correct?

1. The call `System.out.println(Settings.CONSTANT)` uses the value `6` already determined by the compiler; using that constant variable **does not trigger initialization of `Settings`**.
2. The next call accesses `Settings.RUNTIME_VALUE`, which is a static field that is not a constant variable, so the JVM must initialize class `Settings` before reading the value. The `static` block prints `Settings initialized`.
3. After initialization, `RUNTIME_VALUE` has value `7`, so the program prints the line `7`.

If other code has already explicitly initialized `Settings` beforehand, you may observe a different order. The example above is a standalone program that does not initialize that class before calling into `RUNTIME_VALUE`.

**Diagnostic trap:** a piece of code referencing only `Settings.CONSTANT` may not execute the static initializer, even though a reader might assume any access to `Settings.SOMETHING` always initializes the class.

## 9. Boundaries of Constant Folding: JVM, JIT, and Runtime Results

There are three levels easily conflated:

| Level | When Does It Happen? | Condition / Example | How to Observe |
| --- | --- | --- | --- |
| Constant expression per JLS | Type and value determined when compiler processes source | `2 + 3`, `"A" + "B"` | `javap -c` on the binary |
| `javac` transformation | During class file generation | Folding constant expressions, emitting literals in client code | Compare `.class` and constant pool |
| JVM/JIT optimization | At runtime, potentially based on profiling and observed state | Inlining method calls, dead-code elimination, runtime constant propagation | JVM profiling/JIT logging tools |

**Do not equate JIT inlining with compile-time constant inlining.** Although HotSpot can optimize a field read or method call at runtime, the result must obey program semantics and optimization guards, unlike the situation where literals are already placed in `Consumer.class` by `javac`.

Also do not infer that "any expression whose result is always the same gets folded by javac":

```java
static final int A = 2 + 3;                 // constant variable
static final int B = Math.abs(-5);          // not a constant variable
static final String C = "A" + "B";           // constant variable
static final String D = new String("AB");   // not a constant variable
```

A compiler or JIT may optimize some other code snippets according to specification and implementation, yet **does not turn `Math.abs(-5)` into a constant expression per JLS `15.29**. Client–library binary relationships must be analyzed using constant variable rules, not by guessing that an optimizer "must have been smart".

## 10. Compile-Time Constant Constraints in the Language

### Switch Case Labels

A traditional `case` uses a constant expression value compatible with the selector. Example (illustrated inside a class):

```java
static final int CODE_OK = 2 + 3;

static String describe(int code) {
    return switch (code) {
        case CODE_OK -> "ok";
        default -> "other";
    };
}
```

`CODE_OK` has value `5` determined at compile time, so it can serve as a `case` label. If replaced by:

```java
static final int CODE_OK = Integer.parseInt("5");
```

then `CODE_OK` is no longer a constant variable; using it as a `case CODE_OK` label in the manner above will not satisfy the constant expression requirement. These examples illustrate the difference in compilation rules, not a standalone program with `main`.

### Narrowing in Constant Assignment

Java permits certain assignments of integer constants to smaller types if the value is representable:

```java
byte small = 10 + 20;   // Valid because constant expression int = 30.
char letter = 65;       // Valid because 65 is within char range.
// byte fail = 200;     // ERROR: exceeds byte range.
```

However, do not apply this rule indiscriminately to every method call context. Given `static void f(byte x) {}`, calling `f(30)` (where the literal has type `int`) **does not automatically narrow** to `byte` for overload resolution; you need `f((byte) 30)` or a suitable `byte` variable.

### Integer Division by Zero in Constant Expressions

```java
// static final int BROKEN = 1 / 0; // COMPILE ERROR: division by zero in constant expression.
```

For integer division executed at runtime:

```java
int divisor = 0;
// int result = 1 / divisor; // Compiles validly, but if executed will throw ArithmeticException.
```

The claim "the compiler catches every division by zero" is false: it can only apply relevant checking rules from static information; arithmetic errors on runtime data can surface at runtime.

### Integer Overflow Does Not Raise a Runtime Error

As in the `FoldingDemo` example, `Integer.MAX_VALUE + 1` gives `-2147483648` in 32-bit `int`. Do not assume `javac` rejects every out-of-range expression or that Java throws an exception on ordinary integer overflow. If overflow control is needed during runtime computation, look at APIs such as `Math.addExact` (but calls to `Math.addExact` are not constant expressions per the JLS).

## 11. Risks in Library APIs, Caches, and Deployment Systems

Multi-module applications often have the relationship:

```text
module-shared
    |
    | public static final int TIMEOUT = 30;
    v
service-A (compiled when TIMEOUT=30)
service-B (compiled when TIMEOUT=30)
    |
    | shared JAR replaced with TIMEOUT=45
    v
service-A (not recompiled)   -> may continue using 30
service-B (recompiled)       -> uses 45
```

This is a **binary versioning issue**, not merely a matter of the classpath containing an old JAR. Even when `service-A` is using the new `shared.jar`, `service-A.class` may still carry literal `30` from an older compilation.

The impact can be severe if the value relates to protocols, event codes, limits, features, or policies: two clients built at different times may make different decisions even while seeing the exact same runtime library version.

### Especially Dangerous with Feature Toggles

```java
public static final boolean FEATURE_ENABLED = false;
```

If client code compiles with value `false` and later the library changes it to `true`, old clients may still keep `false`. The compiler may even eliminate or transform branches based on the constant expression. Therefore, **do not use public static final compile-time constants as configuration flags that need to change after deployment**.

For `if (Config.FEATURE_ENABLED)`, you should not assume the program will read the field on the library side at runtime. In compiled client bytecode, the condition may already be resolved with no field read remaining.

### Similar Risk with Constant Strings

```java
public static final String API_VERSION = "v1";
```

If a client compiles with `"v1"` and later the library changes it to `"v2"`, the old client may still use literal `"v1"`. `String` is among the types eligible to be a constant variable; integers are not the only ones affected.

## 12. Which API Design Fits Each Kind of Value?

| Need | Suggested Design | Reason |
| --- | --- | --- |
| Mathematical constant or value truly unchanged across versions | `public static final int/long/String` with constant expression | Convenient to use at compile time; a stable value is intentional |
| Value that may change across library versions | Method accessor such as `public static int limit()` | Clients call the implementation at runtime instead of embedding literals via constant variables |
| Environment/deployment configuration | Config from file, environment, property, or config service | Decouples configuration selection from compilation |
| Value immutable after initialization yet should not be inlined | `private static final` initialized at runtime, exposed via accessor | Controls access and API encapsulation |
| Status enum carrying stable semantics | `enum` when appropriate for the API contract | Avoids untyped hardcoded numbers/strings in consuming code |
| On/off toggle needing changes after deploy | Feature/config service or runtime configuration | Does not rely on client bytecode holding a fixed boolean |

Accessor example:

```java
public class RuntimeLimits {
    private static final int LIMIT = 7;

    public static int limit() {
        return LIMIT;
    }
}
```

At call sites, use `RuntimeLimits.limit()` instead of exposing `RuntimeLimits.LIMIT`. `LIMIT` in the class above is still a constant variable *inside the library*, yet **clients only call the method**, so after replacing the library class without changing the method signature, old clients can receive the new value.

**Limitation of this approach:** the JVM/classloader must actually load the new library version. An already-running application will not automatically replace a loaded class just because you copy a new JAR onto disk. Hot reload/redefinition, classloaders, and restarts are separate runtime concerns. The stale-constant example above always launches a fresh `java` process with the replaced library class file.

Another option is `public static final int VALUE = computeValue();` to avoid a constant variable, yet if exposing a field makes clients depend directly on ABI and semantics, an accessor is still usually easier to evolve.

## 13. How to Fix When a Stale Value Is Discovered

Follow this order to avoid misdiagnosis:

1. **Identify the changed field:** is the type primitive/`String`, with `final`, and is the initializer a constant expression? If so, suspect client inlining.
2. **Inspect the client's own bytecode:** run `javap -c` on the deployed class file and look for old literals vs. `getstatic`/`invokestatic`.
3. **Verify the exact artifacts:** check versions/checksums of the running library JAR and client class files; watch out for dependency copies, shaded/fat JARs, or images/containers.
4. **Recompile all dependent consumers:** when changing a compile-time constant value, rebuild the modules that used it. Re-run tests and repackage deployment artifacts.
5. **Deploy the genuinely new artifacts:** restart/roll out according to project operations so new processes load new binaries; distinguish deploying a new library from deploying a new client.
6. **Revise the API design** if the value is expected to change multiple times: stop exposing it as a compile-time constant to consumers that need to observe new values.
7. **Check CI/caches:** if the build system restores old class files, identify dependency inputs and invalidation conditions rather than deleting files randomly.

For multi-module Java applications, modifying a constant source file in `module-shared` and building only that module **is not sufficient proof** that dependent modules have recompiled. Check build outputs and the binaries present in the release.

### Do Not Confuse with Other Bugs

| Symptom | Possible Cause | Evidence to Look For |
| --- | --- | --- |
| Changed `LIMIT` yet client still prints `3` | Constant variable embedded V1 value | Old literal in client bytecode |
| Client reads runtime field yet still gets old value | New JAR not loaded, classloader, multiple library versions | `getstatic` in client, actual class path |
| Client sees old method | Implementation not replaced/restarted, wrong classpath | `invokestatic`/`invokevirtual` and runtime class |
| One thread sees a different value than another | Memory synchronization/visibility or runtime logic | Runtime accesses, volatile/synchronization |
| Running on another machine yields different output | Different artifact/JDK/config | JAR hash/version, build metadata, configuration |
| Build succeeded yet old class is still deployed | Cache/artifact pipeline | Timestamps, hashes, and output of the exact task |

Do not blame every "stale value" phenomenon on constant folding. **If the field is not a constant variable, check runtime classloading, configuration updates, and artifact distribution first**.

## 14. Re-Check with Three Commands and One Edit

The experiment in section 5 can be summarized in order for hands-on practice:

```text
(1) Compile Config V1 -> out/lib/Config.class
(2) Compile Consumer V1 with -cp out/lib -> out/client/Consumer.class
(3) Run Consumer -> 3 / safe / 3 / 3
(4) Replace Config contents with V2
(5) Recompile Config only -> out/lib/Config.class
(6) Run old Consumer -> 3 / safe / 7 / 7
(7) Recompile Consumer against Config V2
(8) Run new Consumer -> 7 / fast / 7 / 7
```

When results differ from the summary above, check:

- Did you accidentally recompile `Consumer` at step (5)?
- Did the client's `javac` command use the exact `-cp out/lib`?
- Did the `java` command use both `out/client` and `out/lib`, with the proper OS-specific separator?
- Did you run inside the exact `constant-lab` directory containing those relative paths?
- Are there multiple different versions of `Config.class` on the classpath?
- Does the JDK version support `--release 17`?

**Key observation:** simply swapping the library and re-running does not remove literals already present in the client binary; recompiling the client is what updates embedded constant values.

## 15. Self-Check Questions

**1. Why is `final int v = Integer.parseInt("3");` not a constant variable?**

Because the initializer uses a method invocation, which does not belong to the constant expression set of JLS `15.29, even though the variable is `final` and of type `int`.

**2. Can `static final String S = "A" + "B";` be inlined?**

Yes. The expression concatenating two string literals is a constant expression, and the field is of type `String` declared `final`. A consumer compiled with value `"AB"` may retain that value.

**3. Is `static final Integer N = 3;` a constant variable?**

No. `Integer` is neither primitive nor `String`. Autoboxing does not change the definition of a constant variable.

**4. If a client was compiled with `TIMEOUT=30` while the new library has `45`, is replacing only the library JAR enough?**

No. The client may have embedded `30` in its class file. You need to rebuild the client, verify artifacts, and deploy the right new binary or change how the value is accessed.

**5. Why does `Config.currentLimit()` return `7` while `Config.LIMIT` is still `3` in the same old client?**

The client stored the constant variable's value directly from compile time, whereas the method call executes code from the V2 `Config.class` loaded at runtime.

**6. Why might `Settings.CONSTANT` not run the static initializer?**

Because referencing a static field that is a constant variable can be resolved from its compile-time value and is not an active use requiring class initialization per JLS `12.4.1.

**7. Can `Math.abs(-5)` be treated as a constant expression because its result is obvious?**

No. The Java Language Specification restricts which constructs may appear in a compile-time constant expression. JIT optimization, if any, is a different mechanism.

**8. Why should you not use `public static final boolean ENABLED = false` as a feature flag that needs to change in production?**

Because a consumer compiled with `false` may keep the old value/logic branch rather than automatically reading `true` from a newer library version.

## 16. Authoritative References

- [Java Language Specification, Java SE 21 — `15.29 Constant Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.29): scope of constant expressions, accepted operations, and string interning rules.
- [Java Language Specification, Java SE 21 — `4.12.4 final Variables](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.12.4): definition of a constant variable.
- [Java Language Specification, Java SE 21 — `13.4.9 final Fields and static Constant Variables](https://docs.oracle.com/javase/specs/jls/se21/html/jls-13.html#jls-13.4.9): impact of changing constant values on pre-existing binaries.
- [Java Language Specification, Java SE 21 — `12.4.1 When Initialization Occurs](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.4.1): static field access and class initialization.
- [Java SE 21 — javap command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html): how to inspect bytecode, field/method references, and the constant pool.

**Remember:** `final` is only part of the requirement for a constant variable; **constant expressions** obey strict language rules; **folding/inlining** can place values directly into consumer binaries. When a `public static final` value needs to change across versions, check **both the client binary** and the API design, because **binary compatibility does not guarantee old clients see new values**.