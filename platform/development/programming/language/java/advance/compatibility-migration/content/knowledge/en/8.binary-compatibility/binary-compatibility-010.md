# Compile-Time Constants and Values Inlined into Consumer Code

## 1. A Very Small Change Can Cause Two Versions to See Two Different Values

Suppose a Java library publishes a shared value:

```java
package example.api;

public final class Limits {
    public static final int MAX_ATTEMPTS = 3;

    private Limits() {
    }
}
```

An application uses the library:

```java
if (attempts >= Limits.MAX_ATTEMPTS) {
    throw new IllegalStateException("Too many attempts");
}
```

The library developer changes `MAX_ATTEMPTS` from `3` to `5`, packages a new JAR, and deploys it. Some applications **compiled before the change** still compare against `3`, even though the `Limits` class at runtime holds the value `5`. The reason is that the Java compiler can embed the value of a **compile-time constant** into the consumer's bytecode, instead of emitting a runtime field read from the library.

This is an important issue in **binary compatibility**: a change can preserve the field's name, type, and access level so it triggers no binary linkage error, yet causes old compiled versions and new versions to observe different values. The bug is often hard to spot because the application can start normally without `NoSuchFieldError`, manifesting only as inconsistent business rules, protocols, or security checks.

Lesson objectives:

- Accurately identify which fields are *constant variables* under Java language rules.
- Understand how `javac` embeds values into bytecode and how `ConstantValue` is stored in class files.
- Distinguish binary compatibility from consistency of values and behavior.
- Predict the impact when changing the value, type, name, or initialization of a public constant.
- Inspect old artifacts with `javap`, build library/client tests across multiple versions, and select an appropriate migration strategy.

## 2. What Is a Compile-Time Constant in Java?

### 2.1. Definition of a *Constant Variable*

According to the Java Language Specification, a `final` variable of primitive type or `String` initialized with a *constant expression* is a **constant variable**. Both the type and the initializer expression matter; merely having `final` or `static final` is not enough.

In APIs, the cases that most often pose risk are `public static final` fields meeting the definition above:

```java
public final class Protocol {
    public static final int VERSION = 2;
    public static final long TIMEOUT_MILLIS = 5_000L;
    public static final boolean ENABLED = true;
    public static final char DELIMITER = '|';
    public static final String PREFIX = "APP-";
}
```

All of these fields are compile-time constants. When client code uses them in expressions, the compiler can directly substitute the values `2`, `5000L`, `true`, `'|'`, or `"APP-"` at compile time.

Not every `static final` is a compile-time constant:

```java
import java.time.Duration;
import java.util.List;

public final class Settings {
    // Constant variable: primitive + final + constant expression.
    public static final int DEFAULT_PORT = 8080;

    // Constant variable: String + final + constant expression.
    public static final String SERVICE = "catalog" + "-api";

    // Not a constant variable: method call.
    public static final int PORT_FROM_CONFIG =
            Integer.parseInt(System.getProperty("app.port", "8080"));

    // Not a constant variable: Duration type is not primitive/String.
    public static final Duration REQUEST_TIMEOUT = Duration.ofSeconds(5);

    // Not a constant variable: List type.
    public static final List<String> ROLES = List.of("reader", "writer");

    // Not a constant variable: array, even though the reference is final.
    public static final int[] CODES = {200, 201};
}
```

`static` is not a mandatory condition in the language definition of a constant variable; a `final` local variable can also satisfy the definition. However, for compatibility across JARs, **public `static final` fields** and constant fields in interfaces are the places to examine first because they form the contract between library and consumer.

### 2.2. Identification Table

| Declaration | Constant variable? | Reason |
| --- | --- | --- |
| `public static final int CODE = 200;` | Yes | Primitive, `final`, initializer is a constant expression |
| `public static final String NAME = "A" + "B";` | Yes | Concatenation of two string literals at compile time |
| `public static final boolean ACTIVE = 1 < 2;` | Yes | Constant expression returning boolean |
| `public static final Integer CODE = 200;` | No | Wrapper type `Integer`, not primitive |
| `public static final String NAME = new String("A");` | No | Object creation expression |
| `public static final int CODE = Integer.parseInt("200");` | No | Contains a method call |
| `public static final int[] CODES = {200};` | No | Array type |
| `public static int CODE = 200;` | No | Missing `final` |
| `public static final String NAME = System.getenv("NAME");` | No | Value known only at runtime |
| `public final int CODE = 200;` | Yes | Instance `final` field, primitive, initializer is a constant expression; also examine usage context |

For declarations that are not constant variables, client code usually must read the field at runtime via bytecode instructions such as `getstatic` or `getfield`. For compile-time constants used as values, the compiler typically embeds the value into the client's expression and does not need to read the field at runtime.

## 3. Constant Expressions and Compile-Time Expression Folding

A *constant expression* can consist of literals, references to other constant variables, and a set of operations permitted by Java: arithmetic operations, comparisons, logical operators, conditional operators, valid casts, string concatenation, and parentheses. Not every expression that stays constant at runtime is a constant expression under the language rules.

```java
public final class WireFormat {
    public static final int HEADER_SIZE = 8;
    public static final int CHECKSUM_SIZE = 4;

    public static final int MIN_PACKET_SIZE =
            HEADER_SIZE + CHECKSUM_SIZE; // 12 at compile time

    public static final String MAJOR = "2";
    public static final String MESSAGE_VERSION =
            "wire-v" + MAJOR;           // "wire-v2" at compile time

    public static final boolean STRICT =
            MIN_PACKET_SIZE >= 12;      // true at compile time

    private WireFormat() {
    }
}
```

An application using `WireFormat.MIN_PACKET_SIZE + 2` may be compiled to the value `14`. If the library later changes `HEADER_SIZE` to `16`, yielding `MIN_PACKET_SIZE = 20` in the new version, the old client can still hold the value `14` in bytecode. Changing a root constant can cascade across many constant expressions in other modules.

Distinguish two styles of writing:

```java
public static final int STATIC_LIMIT = 10;
public static final int COMPUTED_LIMIT = Math.max(8, 10);
```

Although `Math.max(8, 10)` always returns `10` in this example, it is still a method call and is not a constant expression under Java rules. `STATIC_LIMIT` can be embedded into client bytecode, whereas `COMPUTED_LIMIT` needs runtime initialization and is normally read via the field.

Key point: **intended immutability** is not the same as **compile-time evaluability under the JLS**. The compiler applies specific language rules rather than merely guessing that an expression “certainly will not change”.

## 4. How Are Values Embedded into Bytecode?

### 4.1. Field References Can Turn into Literals

Consider a library:

```java
package example;

public final class BuildInfo {
    public static final int FORMAT = 7;
    public static final String LABEL = "v7";

    private BuildInfo() {
    }
}
```

And a client:

```java
package example;

public final class Reader {
    public static int requiredFormat() {
        return BuildInfo.FORMAT;
    }

    public static String label() {
        return BuildInfo.LABEL;
    }
}
```

When compiled, `Reader.requiredFormat()` typically contains an instruction pushing the numeric value `7` onto the operand stack, while `Reader.label()` loads the literal `"v7"` from the constant pool. Instead of `getstatic example/BuildInfo.FORMAT`, the call simply uses the value already baked into the `Reader.class` artifact.

The compiler selects an instruction matching the type and magnitude of the value:

- `iconst_*` for small integers.
- `bipush` or `sipush` for corresponding value ranges.
- `ldc`, `ldc_w`, or `ldc2_w` for literals stored in the constant pool.

Do not rely on a specific instruction in API design; that is a code-generation detail. What needs checking is whether the client reads the field at runtime or already uses a literal.

### 4.2. The `ConstantValue` Attribute in Class Files

A class file can carry the `ConstantValue` attribute for fields represented by a constant. For example, when running:

```bash
javap -classpath library.jar -p -v example.BuildInfo
```

Detailed output may contain information like:

```text
public static final int FORMAT;
  descriptor: I
  flags: (0x0019) ACC_PUBLIC, ACC_STATIC, ACC_FINAL
  ConstantValue: int 7

public static final java.lang.String LABEL;
  descriptor: Ljava/lang/String;
  flags: (0x0019) ACC_PUBLIC, ACC_STATIC, ACC_FINAL
  ConstantValue: String v7
```

`ConstantValue` describes the value in the **class defining the field**. It does not automatically update literals already inserted by the compiler into **classes using the field**. Two artifacts can contain different values and still both be valid class files.

### 4.3. How to Inspect Client Bytecode

To see whether the client reads the field:

```bash
javap -classpath client-classes:library.jar -c -v example.Reader
```

Inspect the code of `requiredFormat()` and `label()`. If you see literal-loading instructions and no `getstatic` corresponding to `BuildInfo.FORMAT`/`BuildInfo.LABEL`, the values were embedded into bytecode. On Windows, the classpath separator is typically a semicolon (`;`), whereas on Linux/macOS it is a colon (`:`).

References that only use compile-time constants may **leave no class reference** to the constant-defining class in the corresponding bytecode. Therefore, looking only at the runtime dependency graph or `jdeps` output may miss **source-level** dependencies on constant APIs.

## 5. Complete Experiment: Library Changes Value While Client Keeps Old Value

### 5.1. Create the First Library Version

File `library-v1/example/RetryPolicy.java`:

```java
package example;

public final class RetryPolicy {
    public static final int MAX_RETRIES = 3;
    public static final String LEVEL = "standard";

    private RetryPolicy() {
    }

    public static int currentMaxRetries() {
        return MAX_RETRIES;
    }
}
```

The `currentMaxRetries()` method is compiled into the **library's** class. If the library is recompiled, this method's bytecode will reflect the new value in the new version.

### 5.2. Create a Client Based on Library v1

File `client/example/RetryClient.java`:

```java
package example;

public final class RetryClient {
    public static void main(String[] args) {
        System.out.println("constant = " + RetryPolicy.MAX_RETRIES);
        System.out.println("method   = " + RetryPolicy.currentMaxRetries());
        System.out.println("level    = " + RetryPolicy.LEVEL);
    }
}
```

Compile library v1 and client against library v1:

```bash
javac -d out/lib-v1 library-v1/example/RetryPolicy.java
javac -cp out/lib-v1 -d out/client client/example/RetryClient.java
java -cp out/client:out/lib-v1 example.RetryClient
```

Expected output when running all v1:

```text
constant = 3
method   = 3
level    = standard
```

### 5.3. Swap Library to v2 Without Recompiling Client

File `library-v2/example/RetryPolicy.java`:

```java
package example;

public final class RetryPolicy {
    public static final int MAX_RETRIES = 5;
    public static final String LEVEL = "strict";

    private RetryPolicy() {
    }

    public static int currentMaxRetries() {
        return MAX_RETRIES;
    }
}
```

Compile library v2 while keeping all of `out/client` unchanged:

```bash
javac -d out/lib-v2 library-v2/example/RetryPolicy.java
java -cp out/client:out/lib-v2 example.RetryClient
```

Illustrative output:

```text
constant = 3
method   = 5
level    = standard
```

Explanation:

- `RetryPolicy.MAX_RETRIES` in `RetryClient.class` is still the literal `3` from the v1 compilation.
- `RetryPolicy.currentMaxRetries()` is invoked from **library v2**, so it returns `5`.
- `RetryPolicy.LEVEL` in the client is still `"standard"` even though v2's field has the value `"strict"`.
- Neither `NoSuchFieldError` nor `NoSuchMethodError` necessarily occurs, because the method still exists and bytecode uses constant values for the remaining fields.

### 5.4. Recompile Client Against v2

```bash
javac -cp out/lib-v2 -d out/client-v2 client/example/RetryClient.java
java -cp out/client-v2:out/lib-v2 example.RetryClient
```

When both the library and the client are compiled against v2, the result will be:

```text
constant = 5
method   = 5
level    = strict
```

That is the core difference: **upgrading a dependency at runtime** is not the same as **recompiling code that depends on compile-time constants**.

If trying this on Windows, replace `:` in `-cp` examples with `;`. These commands are educational examples; when applying to real projects, use artifacts, toolchains, and build processes controlled by your organization.

## 6. Why Is This a Compatibility Risk Even When the JVM Reports No Error?

### 6.1. Linkage Compatibility Differs from Value Compatibility

When changing only the value:

```java
// Library v1
public static final int MAX_RETRIES = 3;

// Library v2
public static final int MAX_RETRIES = 5;
```

the field still has the same owner, name, type, descriptor `I`, and access privileges. Not every binary-level change produces a linkage error. However, an old application that already embedded `3` may never read v2's field, so the value deployed at runtime does not govern its behavior.

In migration reports, distinguish:

1. **Linkage compatibility:** Does the old client load and link against the new library?
2. **Value consistency:** Do the old client and the new library observe the same value?
3. **Behavioral compatibility:** Does the logic based on that value remain correct?

With public compile-time constants, testing only the first item is insufficient.

### 6.2. Changing the Field Type Adds Further Risk

Changing:

```java
public static final int MAX_RETRIES = 3;
```

to:

```java
public static final long MAX_RETRIES = 5L;
```

changes the field descriptor from `I` to `J`. Clients that **already embedded literals** may continue using the old value without resolving the field at runtime. However, clients using reflection, method handles, or field accesses compiled as `getstatic` with the old descriptor may fail or fail to find a matching field. Recompiled source code may also require edits because the type changed.

Do not conclude that all clients are safe or all clients fail merely because the field type changed. You must identify **how each client accesses the field**.

### 6.3. Removing a Constant Field Sometimes Does Not Break Old Clients Immediately

If a compiled client only retains literals, removing the field in a new JAR may not cause an error on that execution path. This is not a sign that removing the API is safe: recompiled clients will fail to find the field, and reflection or runtime access paths may fail.

In particular, a test that only runs old bytecode without recompiling consumers can miss source compatibility errors. Conversely, rebuilding all consumers can mask stale constant issues already affecting released products.

## 7. `static final` Does Not Always Mean Value Inlining

Compare:

```java
public final class Config {
    public static final int COMPILE_TIME = 10;
    public static final int RUNTIME_COMPUTED = Integer.parseInt("10");

    private Config() {
    }
}
```

`COMPILE_TIME` is a constant variable; `RUNTIME_COMPUTED` is not, because its initializer invokes `Integer.parseInt`. A client reference to `RUNTIME_COMPUTED` needs to read the field at runtime, usually via `getstatic`. When swapping in a new library that preserves the field's name, type, and availability, client code can read the value initialized by the new library.

However, intentionally calling a method just to avoid inlining is not always good API design. A runtime field can trigger class initialization and initialization exceptions. For values that may change across releases, an **accessor method** usually expresses the contract better:

```java
public final class RetryPolicy {
    private static final int DEFAULT_MAX_RETRIES = 5;

    private RetryPolicy() {
    }

    public static int maxRetries() {
        return DEFAULT_MAX_RETRIES;
    }
}
```

Client code calling `RetryPolicy.maxRetries()` will invoke the method of whichever library version is currently loaded. When only changing the value in the implementation while keeping the method descriptor intact, old clients can receive the new value at runtime. This is one way to decouple implementation details from the consumer's binary contract.

Not every value should be read through a method. Quantities that are genuinely immutable by definition, such as the number of bytes in a Java `short` or a permanently frozen protocol identifier, can reasonably be published as compile-time constants. The decision depends on the likelihood that **the value must change without rebuilding consumers**.

## 8. Accessing a Compile-Time Constant May Skip Class Initialization

Referencing a constant variable in some contexts does not cause the JVM to initialize the class containing the field. This creates an observable difference when initialization code has side effects:

```java
public final class RuntimeFlags {
    static {
        System.out.println("RuntimeFlags initialized");
    }

    public static final int STATIC_CODE = 42;
    public static final int DYNAMIC_CODE = Integer.parseInt("42");

    private RuntimeFlags() {
    }
}
```

Client:

```java
System.out.println(RuntimeFlags.STATIC_CODE);
System.out.println(RuntimeFlags.DYNAMIC_CODE);
```

In the first statement, the compiler can use literal `42` without reading the field and without needing to initialize `RuntimeFlags`. In the second statement, reading `DYNAMIC_CODE` via `getstatic` is a situation that triggers class initialization prior to reading, so the `static` block may print the message.

If the library changes `STATIC_CODE` into a runtime-computed field, **recompiled** clients may begin triggering class initialization on access. **Old compiled** clients may still use only the literal. Beyond values, this change can affect initialization order, startup cost, or initializer exceptions.

Do not design logic needing `static` initializer side effects based on consumers reading a compile-time constant. If a class must be initialized for a specific task, place that task in a clearly defined API/runtime flow.

## 9. Constants in Interfaces and Risks for Shared Code

Every field declared in a Java interface implicitly carries `public static final` modifiers. If the field is a primitive or `String` initialized by a constant expression, it is a compile-time constant.

```java
public interface MessageCodes {
    int OK = 200;
    int NOT_FOUND = 404;
    String TYPE = "application/vnd.example.v1+json";
}
```

Client code:

```java
int code = MessageCodes.OK;
String type = MessageCodes.TYPE;
```

can embed these values into bytecode. If the module defining the interface changes `TYPE` to `v2` without rebuilding consumer services, those services will still send or validate the old media type.

Avoid using interfaces solely to group constants (often called the *constant interface antipattern*), especially if classes implement the interface just to inherit constant names. For shared value sets, a clearly namespaced utility class may make more sense, though switching from an interface to a class **does not solve inlining by itself** if `public static final` compile-time constants are still used.

If a value is governed by protocol versions or can change independently, consider an API providing the value via methods, runtime configuration, or a dedicated type with a clear contract.

## 10. Special Cases: `switch`, Annotations, and Constant Folding

### 10.1. `case` Labels in `switch`

In many forms of `switch` over integers or strings, `case` labels use constant expressions. Example:

```java
public final class StatusCodes {
    public static final int ACCEPTED = 202;

    private StatusCodes() {
    }
}
```

```java
String describe(int code) {
    return switch (code) {
        case StatusCodes.ACCEPTED -> "accepted";
        default -> "other";
    };
}
```

A client that compiled `switch` code can use literal `202` directly in jump tables or comparison logic. If the library later changes `ACCEPTED` to `203` without rebuilding the client, the old `switch` logic does not automatically switch to recognizing `203`. This is an example of how stale constants can skew protocol handling.

Note: enum constants and pattern matching have their own rules and should not be equated with primitive/`String` constant variables. The example above focuses on `case` labels using constant expressions.

### 10.2. Values in Annotations

Annotations can require constant expressions for many kinds of elements. Example:

```java
public final class Routes {
    public static final String ROOT = "/v1/orders";

    private Routes() {
    }
}
```

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface Route {
    String value();
}

@Route(Routes.ROOT)
class OrderHandler {
}
```

The compiler writes the value of `Routes.ROOT` into annotation metadata inside `OrderHandler.class`. After upgrading the library to change `ROOT` to `"/v2/orders"`, the compiled `OrderHandler` class can still carry the annotation `"/v1/orders"`. Frameworks reading annotations via reflection will see the value stored inside the **consumer artifact**, with no mechanism to automatically re-read the constant field from the `Routes` class.

This is a major risk for routing, serializers, validation, message mapping, and frameworks that use annotations to configure behavior.

### 10.3. Expressions Folded Across Multiple Layers

```java
public final class Headers {
    public static final String PRODUCT = "service";
    public static final String X_PRODUCT_HEADER = "X-" + PRODUCT;
}
```

If consumer code declares:

```java
public static final String EXPECTED_HEADER = Headers.X_PRODUCT_HEADER;
```

then `EXPECTED_HEADER` can also become a constant variable containing the literal `"X-service"`. Changing `Headers.PRODUCT` in the library may require rebuilding multiple module layers because each layer can continue embedding the old value.

## 11. Consequences in Version Migrations and Multi-Service Deployments

Compile-time constant changes can propagate across the following boundaries:

| Usage site | Risk when library updates without consumer rebuild |
| --- | --- |
| Retry/timeout limits | Client logic still applies old threshold even though runtime methods report new threshold |
| Status codes or message codes | Producer and consumer interpret two different code sets |
| Routes, headers, media types | Compiled annotations or String literals still use old format |
| Default feature flags | Old modules decide by old value, new modules by new value |
| Security input limits | Checks in old applications may retain thresholds a patch intended to tighten |
| Cache parameters or TTLs | Rebuilt modules and non-rebuilt modules operate under different policies |
| Table names, data fields, or schema IDs | Consumers save/read old names even though library definitions changed |
| `case` labels or annotation elements | Values pre-recorded in bytecode/metadata require recompilation |

### 11.1. Changing Safety or Security Thresholds

Suppose library v1 has:

```java
public static final int MAX_PAYLOAD_BYTES = 1_000_000;
```

A patch lowers the limit to `100_000` to prevent oversized inputs:

```java
public static final int MAX_PAYLOAD_BYTES = 100_000;
```

If a web gateway or consumer application already compiled `payload.length > MAX_PAYLOAD_BYTES` into a comparison against `1_000_000`, merely replacing the library JAR may **fail to enforce the new limit on that validation path**. Every consumer depending on the constant must be found, rebuilt, and redeployed with new artifacts, or migrated to a runtime threshold-query API.

Do not consider a security patch fully deployed merely because a dependency scanner stops flagging the affected version. Verify whether the actual execution path uses the updated value/rule.

### 11.2. Rolling Deployments and Version Skew

During a rolling deployment, old service A, new service A, old consumer B, and new consumer B may run simultaneously. If services exchange values affected by compile-time constants, each artifact may carry a different value.

For example, a new producer begins sending message code `25`, while an old consumer compiled `case 20`. Upgrading the library containing `MESSAGE_CODE = 25` on the consumer host is not enough to change compiled logic. Protocol compatibility must be designed or consumers must be allowed to understand both codes during the transition period.

An important principle: values marking protocol, schema, or message versions should not change silently just because a constant in a shared JAR was edited. Clear versioning and producer–consumer compatibility plans are essential.

## 12. Impact Matrix When Changing Fields

| Change in library | Old client bytecode that inlined | Consumer accessing field at runtime | Recompiled consumer |
| --- | --- | --- | --- |
| Change constant value with same type | May continue holding old value | May read new value | Typically receives new value |
| Change `int` to `long` | May continue holding old literal | Risks field descriptor mismatch | May need type and logic edits |
| Rename field | May still run if no runtime field reference remains | May get access error/missing field | Error if still using old name |
| Delete field | May still run at inlined sites | May hit `NoSuchFieldError`/reflection error | Compile error when using deleted field |
| Change constant expression to runtime initializer of same type | Still holds old literal | Reads new runtime field; may trigger class initialization | Typically emits `getstatic` instead of literal |
| Change `static final` to mutable field of same type | Previously inlined old values do not auto-update | Need to check access, modifiers, and behavior | Can read values changed at runtime |
| Keep constant and add new accessor | Path using old constant stays stale | Accessor can return new library's runtime value | Can migrate to accessor |

This table shows analytical tendencies, not universal guarantees for every field or compiler. Actual outcomes depend on client bytecode, field types, access methods, reflection, module access, and class versions loaded by the JVM.

Specifically, **source code using a constant's name** does not guarantee bytecode retains a reference to that field. To evaluate accurately, inspect compiled artifacts.

## 13. Distinguishing Constant Risks from Normal Field Linkage Errors

Another situation is code compiled to read a field at runtime:

```java
public final class RuntimeSettings {
    public static final int MAX_RETRIES =
            Integer.parseInt("3");
}
```

Client:

```java
int retries = RuntimeSettings.MAX_RETRIES;
```

Because this is not a constant variable, the compiler must emit a `getstatic` access for the field. If the library renames or removes the field, the client may encounter `NoSuchFieldError` when the reference is resolved. If the library changes type `int` to `long`, descriptor `I` of the old access does not match the new `J` field, which can also trigger `NoSuchFieldError`.

Side by side:

- **Compile-time inlining:** value changes, old client still runs using old literal.
- **Runtime field linkage:** call retains symbolic field reference; changing or deleting the field can cause linkage errors.
- **Reflection/annotation:** observation path may differ from both above; reflection reads metadata of loaded classes, while annotation values may have been baked into consumer classes.

Risk cannot be inferred solely from a `public static final` declaration in source. Check the initializer, field type, and how consumers were compiled.

## 14. How to Investigate Using the Compiler and Bytecode

### 14.1. Identify APIs Providing Constants

Search for fields used in public/shared modules:

```java
public static final int ...
public static final long ...
public static final String ...
```

Do not search only for the exact string `public static final`: fields in interfaces have implicit modifiers, and code may use `static import`:

```java
import static example.api.Limits.MAX_ATTEMPTS;

if (attempts >= MAX_ATTEMPTS) {
    // ...
}
```

Determine whether the initializer is a constant expression, which modules use the field, and whether it appears in annotations, `case` labels, or other constant expressions.

### 14.2. Inspect Library Class Files

```bash
javap -classpath old-library.jar -p -v example.api.Limits
javap -classpath new-library.jar -p -v example.api.Limits
```

Record descriptors, flags, and `ConstantValue` before/after. Changing `ConstantValue` while keeping the descriptor is a signal to search for inlined clients, even if no binary linkage error necessarily occurs.

### 14.3. Inspect Client Bytecode

```bash
javap -classpath client.jar:old-library.jar -c -v example.app.Controller
```

Look for places using the constant value:

- Literals loaded via `iconst_*`, `bipush`, `sipush`, `ldc`, or `ldc2_w`.
- `getstatic` or `getfield` instructions pointing to the field owner and descriptor.
- Whether constant pools and annotation attributes contain old literal values.
- Whether expressions were constant-folded into a different value.

Inspect **consumer bytecode**, not just library bytecode. A library field having `ConstantValue: int 5` does not prove old consumers use `5`.

### 14.4. Verify Actual Artifacts and Dependencies

When an environment reports an old value, check:

1. Commit and artifact version against which the consumer was compiled.
2. Specific JAR placed in the consumer's runtime image.
3. Library version present when the consumer compiled.
4. Whether bytecode has old literals or field accesses.
5. Whether client/consumer builds were rebuilt and deployed in the rollout.

Classpaths can contain multiple versions of a library; build caches, shaded JARs, or stale images can mislead investigations. Verify the artifact actually running rather than only comparing dependency versions declared in build scripts.

## 15. Compatibility Testing Between Library and Consumers

When changing public constants, a single test is insufficient. Build a matrix:

| Client bytecode | Library runtime | Purpose |
| --- | --- | --- |
| Compiled with v1 | Run with v1 | Baseline, verify behavior before migration |
| Compiled with v1 | Run with v2 | Detect stale constants, linkage errors, and version skew |
| Recompiled with v2 | Run with v2 | Confirm new behavior and values |
| Compiled with v2 | Run with v1 (only when support is required) | Evaluate downgrade feasibility and compatibility support conditions |

Tests should check both **observed values** and **behavior using those values**. For example, a test calling only `Limits.maxRetries()` can pass when the library returns `5`, while compiled consumer logic still compares against `3`. A proper test must exercise the retry decision flow of the packaged consumer.

### 15.1. Contract-Level Testing

For constants with protocol meaning, test from both sides:

- Can old consumers still read/understand data sent by new producers?
- Must any data or requests support old/new versions concurrently?
- Do annotations/routes/schemas packaged in consumers contain the intended target values?
- Is a transition period, dual-read/dual-write, or protocol adapter needed?

### 15.2. Do Not Equate a Clean Build with Updating the Whole Ecosystem

A clean build of one module updates only that module's classes. If applications use previously built internal JARs, those JARs may still contain old values. Therefore, identify the consumer list and rebuild along the dependency graph, including published artifacts, internal modules, plugins, downstream applications, and services with independent deployment schedules.

When a constant change is for security, tracing all running consumers is part of patch verification, not just build work.

## 16. Designing APIs to Minimize Stale Constants

### 16.1. Reserve Compile-Time Constants for Truly Unchanging Values

`public static final` compile-time constants suit values that are genuinely part of a stable definition, such as a standardized delimiter not expected to change, or an identifier frozen to a specific version.

If a value must change across versions, consider naming that reflects the version:

```java
public static final String MEDIA_TYPE_V1 =
        "application/vnd.example.v1+json";
public static final String MEDIA_TYPE_V2 =
        "application/vnd.example.v2+json";
```

Adding a new constant instead of silently changing the value of an old constant lets consumers explicitly select the contract. However, consumers still need to update code when deciding to switch versions.

### 16.2. Use Accessors for Values That Need Runtime Upgrades

```java
public final class Policy {
    private static final int RETRY_LIMIT = 5;

    private Policy() {
    }

    public static int retryLimit() {
        return RETRY_LIMIT;
    }
}
```

On the consumer side:

```java
if (attempts >= Policy.retryLimit()) {
    stopRetrying();
}
```

The method call has a clear descriptor `()I`. If the library later changes only the returned value while preserving the method name and signature, old consumer code will call the new implementation. If the method is inlined by the JIT during runtime optimization, that is an optimization **within the running process**, distinct from `javac` baking literals into class files at compile time. The JIT does not cause released consumer JARs to carry fixed values from an old library version in the same manner.

### 16.3. Use Runtime Configuration for Operational Policies

Retry limits, timeouts, cache sizes, and operational flags generally fit runtime configuration with validation, defaults, and clear rollout mechanisms better than public constants. Example:

```java
public final class RetrySettings {
    private final int maxRetries;

    public RetrySettings(int maxRetries) {
        if (maxRetries < 0) {
            throw new IllegalArgumentException("maxRetries must be non-negative");
        }
        this.maxRetries = maxRetries;
    }

    public int maxRetries() {
        return maxRetries;
    }
}
```

Then changing the policy itself becomes a testable and observable configuration action, rather than depending on whether modules were recompiled.

### 16.4. Separate “Stable Values” from “Business Decisions”

Instead of letting every consumer compare directly:

```java
if (payload.length > Limits.MAX_PAYLOAD) {
    reject();
}
```

you can provide an API expressing the decision:

```java
if (!PayloadPolicy.isAllowed(payload.length)) {
    reject();
}
```

The implementation governs the rule inside the library. This helps avoid duplicating logic, though dependency availability, performance, testing, and policy enforcement location must be weighed. It does not replace clear protocol design between services.

## 17. Roadmap for Changing a Public Constant Used by Many Consumers

If a long-published constant must be changed, proceed in phases:

### Phase 1: Scope Survey

Identify the library owner, consumer artifacts, running versions, and constant usage sites. Search also for `static import`, annotations, `case` labels, code generation, test fixtures, and constant expressions in downstream modules. Determine whether the change can cause data corruption, protocol errors, or security issues.

### Phase 2: Choose the New Contract

Decide whether to keep the old field name, add a versioned constant, or switch to a method/runtime config. For consumers unable to upgrade simultaneously, plan support for multiple versions or adapters.

### Phase 3: Release Library with Transition API

Try to retain the old field if the old contract still requires support, while providing the new API:

```java
public final class Limits {
    /** @deprecated Consumers should use currentMaxAttempts(). */
    @Deprecated
    public static final int LEGACY_MAX_ATTEMPTS = 3;

    private Limits() {
    }

    public static int currentMaxAttempts() {
        return 5;
    }
}
```

In a real project, keeping the exact **old field name** may be necessary to preserve source compatibility for consumers using that name; the example above names it `LEGACY_...` to illustrate intent, not as a template for renaming an old field without assessing impact. If renaming, announce the breaking change and transition plan.

### Phase 4: Rebuild and Test Consumers

Rebuild artifacts that need to pick up the new value, then inspect bytecode and behavior. Run the old-client/new-client against old-library/new-library matrix when the product must support transition states.

### Phase 5: Deploy and Monitor

Observe metrics directly related to the change such as retry counts, request rejections, message parse failures, or route errors. For protocol changes, confirm old consumers were upgraded or still have compatibility mechanisms.

### Phase 6: Remove Old API per Support Policy

Delete the old constant only when consumers no longer use it and the release policy allows. Changing a value while ignoring compiled artifacts often leaves the system unable to agree on a single “correct” value everywhere.

## 18. Common Misconceptions

**“Anything with `final` is always inlined.”** False: a constant variable must have primitive or `String` type and be initialized with a constant expression. `final Duration`, `final List`, or values returned by methods do not meet this condition.

**“Changing a field from 3 to 5 is a binary breaking change.”** Not necessarily: changing the value may not break linkage, yet still causes stale constants and behavioral differences. Distinguish which kind of compatibility is being evaluated.

**“Deploying the new JAR is enough for clients to see the new constant.”** Untrue when clients already carry old literals. Clients must be rebuilt or the value-retrieval design changed.

**“`javap` on library v2 shows `ConstantValue: 5`, so every service uses 5.”** False. You must inspect consumer bytecode and the artifacts actually running.

**“No `NoSuchFieldError` means no consumer uses the field anymore.”** False. An inlined consumer may no longer access the field at runtime even though its source depended on that field.

**“Just changing `static final int` to a runtime initializer makes all old clients read the new value.”** False. Old bytecode was not recompiled, so old literals remain.

**“Using `enum` is the same kind of compile-time constant.”** An enum constant is an object with access and compatibility mechanisms different from primitive/`String` constant variables. Changing enums carries its own risks; do not directly apply `int`/`String` literal-inlining rules to enums.

**“Clean-building the library module means all consumers are updated.”** False when consumer JARs, downstream applications, or containers still carry bytecode built from the old version.

**“Values in annotations re-read the constant field at runtime.”** Typically annotation values are written into the annotated class file at compile time. Updating them requires rebuilding the artifact containing the annotation.

## 19. Checklist When Reviewing a Constant Change

Before merging or releasing a change to a `public static final` field:

- [ ] Determined whether the field is a constant variable under the JLS.
- [ ] Recorded name, owner, type, descriptor, and `ConstantValue` before/after.
- [ ] Identified consumers already compiled with the old value.
- [ ] Found all `static import`, `case`, annotation, and constant expression usages of the value.
- [ ] Distinguished consumers using literals from consumers using runtime fields/methods.
- [ ] Checked whether changing the value breaks behavior, data contracts, or security policies.
- [ ] Built an old/new client against old/new library matrix when multiple versions must be supported.
- [ ] Rebuilt all artifacts needing the new value, including internal JARs and container images.
- [ ] Inspected consumer bytecode with `javap -c -v` when exact verification is needed.
- [ ] Checked dependency graphs and libraries actually loaded at runtime.
- [ ] Determined whether an accessor method, new API version, or runtime config is needed.
- [ ] Planned deployment alongside consumers and monitored corresponding business metrics.
- [ ] Release notes clearly state value changes and impact on consumers needing recompilation.
- [ ] For security patches, confirmed actual validation paths enforce the new policy.

A checklist does not replace integration testing. It helps avoid overlooking a change that may look “small” in a library yet was replicated as hardcoded values across many downstream artifacts.

## 20. Technical References

The rules can be checked against the Java specifications:

- **JLS `4.12.4 — `final` Variables:** defines *constant variable*.
- **JLS `15.29 — Constant Expressions:** expressions permitted to be evaluated at compile time in the respective Java releases.
- **JLS `13.1 — The Form of a Binary:** how references to constant variables are represented when compiled.
- **JLS `13.4.9 — `final` Fields and Constant Variables:** impact of field changes on binary compatibility and compiler-embedded values.
- **JLS `12.4.1 — When Initialization Occurs:** difference between referencing a constant variable and accesses that trigger class initialization.
- **JVMS `4.7.2 — The `ConstantValue` Attribute:** how constant values are represented in class files.

When applying to a specific Java release, read the exact JLS/JVMS edition matching the toolchain in use. Running `javap` on real artifacts is the most direct way to compare the theoretical model against released bytecode.

## 21. Conclusion

Compile-time constants in Java sit at an important intersection of source code, the compiler, and binary compatibility. A `public static final` field of primitive or `String` type, initialized with a constant expression, can be embedded directly into consumer bytecode. When a library changes the value, already-compiled consumers may continue using the old literal even while starting up and running without linkage errors.

Therefore, during migrations, evaluate not only **what value a field currently has in the new library**, but also **what value consumer artifacts were compiled with** and **what logic depends on that value**. Use `javap` to verify, rebuild consumers when necessary, test multiple version combinations, and prefer accessors or versioned contracts for values that need to change independently. This discipline avoids a state where services run in the same system yet follow different constants.
