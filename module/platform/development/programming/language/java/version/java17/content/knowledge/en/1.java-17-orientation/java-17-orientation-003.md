# Java 17: Distinguishing New Features from Inherited Features

**Topic:** Java 17 Orientation  
**Goal:** Look at any feature usable on Java 17 and accurately identify: **which release first introduced it**, **which release finalized it**, and **whether it should be used in Java 17 source code today**.

Java 17 is a Java release shipped on the platform's release cadence, as well as a Long-Term Support (LTS) milestone. When a project adopts Java 17, it receives **all the stable features accumulated from earlier releases**, plus the changes introduced in Java 17 itself. Therefore, “usable in Java 17” is **not synonymous with** “newly introduced in Java 17.”

## 1. Three Questions You Must Separate

For each feature, determine three facts:

1. **Introduction version:** Which Java/JDK release did it first appear in? Initially, it may have been only in *preview* state.
2. **Finalization version:** Starting from which release can the feature be used officially without enabling experimental flags?
3. **Status in Java 17:** Is it a language feature, a library API, a JVM/JDK behavior change, or an experimental mechanism?

For example:

- `record` was first introduced in preview in Java 14, but became **final in Java 16**. Java 17 **inherits** `record`.
- `sealed class` was in preview in Java 15 and 16, and became **final in Java 17**. Thus, it is a new stable feature of Java 17.
- Pattern matching in `switch` is present in Java 17, but **only as a preview feature in Java 17 itself**. It must not be called a stable language feature of Java 17.

> **Documentation reading rule:** The terms “introduced,” “previewed,” “finalized,” and “available” describe different milestones. Prioritize the **finalized/standard** milestone when choosing syntax for long-term use.

## 2. Map of Inherited Features

The following table focuses on features that are practical and useful when writing and maintaining modern Java applications. The “Milestone” column indicates the release in which the feature became **official/final**, not its first preview appearance.

| Feature | Final Milestone | Role When Running on Java 17 |
|---|---:|---|
| Lambda expressions, Stream API | Java 8 | Foundation for functional-style and collection processing; **inherited** |
| `Optional`, Date/Time API `java.time` | Java 8 | Common standard APIs; **inherited** |
| Java Platform Module System (`module-info.java`) | Java 9 | Modular organization and encapsulation; **inherited** |
| Factory methods `List.of`, `Set.of`, `Map.of` | Java 9 | Create unmodifiable collections; **inherited** |
| Local variable type inference `var` | Java 10 | Reduce redundant types in local variable declarations; **inherited** |
| Standard HTTP Client `java.net.http.HttpClient` | Java 11 | Synchronous/asynchronous HTTP calls; **inherited** |
| `String.isBlank`, `strip`, `lines` | Java 11 | String processing utilities; **inherited** |
| `switch` expressions, `case ... ->`, `yield` | Java 14 | Write `switch` constructs that return a value; **inherited** |
| Text blocks `"""..."""` | Java 15 | Declare readable multi-line strings; **inherited** |
| `record` | Java 16 | Declare concise, explicit data-carrier classes; **inherited** |
| Pattern matching for `instanceof` | Java 16 | Test a type and bind a variable in one step; **inherited** |
| `Stream.toList()` | Java 16 | Collect stream results into an unmodifiable list; **inherited** |
| `sealed` classes/interfaces | **Java 17** | Restrict which subtypes may inherit or implement; **newly finalized in 17** |
| `java.util.random.RandomGenerator` and expanded PRNG algorithms | **Java 17** | Pseudo-random number generation APIs/algorithms; **new in 17** |

### 2.1. `var` is from Java 10

`var` lets the compiler infer the static type from the initializer expression:

```java
var name = "Java";             // String
var numbers = List.of(1, 2, 3); // List<Integer>
```

`var` does **not** turn Java into a dynamically typed language. You cannot use `var` as the type of a field, method parameter, or return type. The example above requires `import java.util.List;`.

### 2.2. `switch` expressions are from Java 14

```java
enum OrderStatus { NEW, PAID, CANCELLED }

static String label(OrderStatus status) {
    return switch (status) {
        case NEW -> "Created";
        case PAID -> "Paid";
        case CANCELLED -> "Cancelled";
    };
}
```

This construct is a **finalized** `switch` expression from Java 14, distinct from *pattern matching for switch*, which is only in preview in Java 17. `switch` expressions make code shorter and prevent missing-`break` bugs from traditional `case` syntax.

### 2.3. Text blocks are from Java 15

```java
String json = """
        {
          "id": 17,
          "name": "Java"
        }
        """;
```

Text blocks are ordinary Java `String` values, not a new JSON data type. They are useful for sample JSON, SQL, or multi-line content; they do not replace parameterized SQL queries and do not automatically sanitize input.

### 2.4. `record` and pattern matching for `instanceof` are from Java 16

```java
record User(int id, String name) {}

static String display(Object value) {
    if (value instanceof User user) {
        return user.id() + ": " + user.name();
    }
    return "Not a User";
}
```

A `record` automatically generates standard members such as the canonical constructor, accessors, `equals`, `hashCode`, and `toString`. It fits data-carrying objects, though it **does not guarantee deep immutability**: if a component holds a mutable object, that object's contents can still change.

The `value instanceof User user` syntax eliminates a redundant cast after checking the type. Both features were **finalized prior to Java 17**.

## 3. Changes That Truly Belong to Java 17

These can be grouped into **language features**, **library APIs**, and **JDK behavior/infrastructure changes**. Do not lump everything together under “new syntax.”

| Category | Change in Java 17 | Practical Impact |
|---|---|---|
| Language | **Sealed Classes** (JEP 409) finalized | Models a finite set of subtypes, useful for domain modeling |
| Library | **Enhanced Pseudo-Random Number Generators** (JEP 356) | Uses `RandomGenerator` and multiple algorithm families |
| Library/Security | **Context-Specific Deserialization Filters** (JEP 415) | Controls filtering of deserialized objects by context |
| Compatibility/Encapsulation | **Strongly Encapsulate JDK Internals** (JEP 403) | Code relying on internal JDK APIs may need to be updated |
| JVM/Language Semantics | **Always-Strict Floating-Point Semantics** (JEP 306) | Restores consistently strict floating-point semantics |
| OS/Graphics | macOS/AArch64 support (JEP 391), Metal-based Java 2D pipeline (JEP 382) | Primarily affects deployment platforms |

Library and runtime changes are also “new in Java 17,” even when a learner does not see a new keyword.

### 3.1. Sealed classes: the headline language addition in Java 17

A `sealed` class or interface explicitly specifies which types are allowed to **directly inherit from or implement** it:

```java
sealed interface Payment permits CardPayment, BankTransfer {}

final class CardPayment implements Payment {}

non-sealed class BankTransfer implements Payment {}
```

In this example:

- `Payment` permits two direct implementations: `CardPayment` and `BankTransfer`.
- `final` means `CardPayment` cannot be subclassed further.
- `non-sealed` allows `BankTransfer` to have further subclasses unrestricted by the `permits` list.
- A direct subtype of a `sealed` type must be declared `final`, `sealed`, or `non-sealed`. A `record` implementing a `sealed` interface is implicitly `final`.

Types listed in `permits` must also satisfy Java's location rules: they must be in the same named module as the `sealed` type, or in the same package if in the unnamed module. `sealed` manages **compile-time inheritance relationships**, not user authorization or data security.

**When to use:** Domains with a controlled set of variants—such as processing result states, event types, or expression tree nodes. When you want an API that third parties can implement freely, a non-`sealed` interface is usually a better fit.

### 3.2. `RandomGenerator`: a new API in Java 17

```java
import java.util.random.RandomGenerator;

public class Dice {
    public static void main(String[] args) {
        RandomGenerator random = RandomGenerator.of("L64X128MixRandom");
        int roll = random.nextInt(1, 7); // 1 to 6
        System.out.println(roll);
    }
}
```

This is a new API in Java 17's `java.util.random` package. It expands the available algorithms and introduces unified interfaces for PRNGs. Long-standing APIs like `java.util.Random` still exist and are not new in Java 17.

**Security note:** PRNGs intended for simulation, testing, or statistical work are **not automatically safe for keys, tokens, or OTPs**. When cryptographically strong randomness is needed, use `java.security.SecureRandom`; `SecureRandom` existed previously and is not a new Java 17 feature.

### 3.3. Strong encapsulation of JDK internals: upgrade impact

Java 17 tightens access to many **internal** JDK packages, classes, and members via JEP 403. Legacy projects or libraries using reflection to reach into internal structures may encounter errors such as:

```text
java.lang.reflect.InaccessibleObjectException:
Unable to make ... accessible: module java.base does not "opens ..."
```

The long-term fix is to upgrade libraries and migrate to **public, supported APIs**. When diagnosing legacy applications, `jdeps --jdk-internals` can help detect internal API dependencies in bytecode:

```bash
jdeps --jdk-internals app.jar
```

Depending on the situation, JVM options like `--add-opens` can ease a temporary transition; they should not become a permanent API design choice. This is a **behavior change when moving to Java 17**, even if the code never uses `sealed` or `RandomGenerator`.

### 3.4. Other changes to understand in proper scope

- **JEP 415:** Expands the ability to configure `ObjectInputFilter` deserialization filters per context. Deserializing untrusted data still requires strict controls; adding filters does not make all data automatically safe.
- **JEP 306:** Restores always-strict floating-point semantics. This is an execution-rule change, not new syntax for writing typical application logic.
- **JEP 391 and 382:** Improve compatibility with Apple Silicon hardware and macOS graphics. These are JDK/platform changes, not object-oriented programming features.
- **Security Manager:** Java 17 marks `SecurityManager` as *deprecated for removal* (JEP 411). Do not choose it as the security foundation for new designs.

## 4. Features Present in Java 17 That Are Not Yet Stable Standards

**Pattern matching for `switch` (JEP 406)** is a *preview* feature in Java 17. Unlike `switch` expressions finalized in Java 14, pattern matching lets `case` labels test types or data patterns. On Java 17, code using preview syntax requires `--enable-preview` at both compile and run time; it is **not part of Java 17's default stable syntax**. Pattern matching for `switch` was finalized later in Java 21.

Java 17 also includes *incubator* APIs, such as the Foreign Function & Memory API (JEP 412) and the experimental Vector API (JEP 414). Incubator status means the API is under evaluation and subject to change. For projects requiring **long-term Java 17 standard compatibility**, prefer stable APIs; do not treat Java 17 incubator APIs as production templates.

**Quick way to distinguish:**

| Case | Accurate Conclusion for Java 17 |
|---|---|
| `record User(...)` | Stably supported, **inherited from Java 16** |
| `if (x instanceof String s)` | Stably supported, **inherited from Java 16** |
| `return switch (x) { ... };` | Stable `switch` expression, **inherited from Java 14** |
| `sealed interface X permits A, B` | **Standardized in Java 17** |
| `RandomGenerator` | **New API added in Java 17** |
| `switch` with `case String s ->` | **Preview in Java 17**, does not compile by default as stable syntax |
| Reflective access into `java.base` internals | May be blocked more strictly in Java 17 due to JEP 403 |

## 5. Combined Example: A Java 17 Program Using Both New and Inherited Features

Save the file below as `Java17FeatureMap.java`:

```java
import java.util.random.RandomGenerator;

public class Java17FeatureMap {

    // NEW IN JAVA 17: sealed interface is finalized.
    sealed interface Result permits Success, Failure {}

    // INHERITED FROM JAVA 16: record.
    record Success(String value) implements Result {}
    record Failure(String reason) implements Result {}

    static String describe(Result result) {
        // INHERITED FROM JAVA 16: pattern matching for instanceof.
        if (result instanceof Success success) {
            return "Success: " + success.value();
        }
        if (result instanceof Failure failure) {
            return "Failure: " + failure.reason();
        }
        throw new IllegalStateException("Unexpected result type");
    }

    public static void main(String[] args) {
        // INHERITED FROM JAVA 10: var.
        var result = new Success("Order created");

        // INHERITED FROM JAVA 15: text block.
        String payload = """
                {
                  "event": "order-created"
                }
                """;

        // NEW IN JAVA 17: RandomGenerator.
        RandomGenerator random = RandomGenerator.of("L64X128MixRandom");

        System.out.println(describe(result));
        System.out.println(payload);
        System.out.println("Number from 1 to 6: " + random.nextInt(1, 7));
    }
}
```

Compile and run using JDK 17 or a newer JDK that supports target 17:

```bash
javac --release 17 Java17FeatureMap.java
java Java17FeatureMap
```

This program uses only **stable features** in Java 17, so `--enable-preview` is not needed. The random number printed can vary across runs.

Notice that in this example, only `sealed` and `RandomGenerator` are **new in Java 17**. `record`, pattern matching for `instanceof`, `var`, and text blocks are still valid Java 17 idioms and should continue to be used where appropriate, even though they originated in earlier releases.

## 6. Distinguishing “Running on Java 17” from “Compiling for Java 17”

These three concepts are related yet distinct:

- **The JDK in use:** The toolkit executing `javac`, `java`, and development utilities.
- **Target language/API level:** Selected with `javac --release N`; determines which language features and platform APIs may be used at compile time.
- **Deployment runtime version:** The JVM actually running the application; it must understand the class file version and APIs required by the app.

For example, using a sufficiently recent JDK to run:

```bash
javac --release 17 Java17FeatureMap.java
```

means compiling for Java 17 (class-file major version **61**). This class file **will not run on Java 11**. Conversely, a typical Java 11 application can run on JDK 17 provided it does not hit behavior changes, removed APIs, or incompatible dependencies; actual compatibility testing is still required.

If a product must run on Java 11, developing with JDK 17 **does not allow** you to use `sealed` or `RandomGenerator` and expect the app to keep running on Java 11. You must set `--release 11` and choose APIs accordingly.

### Checklist when reading source code or upgrading a project

1. Inspect `build.gradle`, `pom.xml`, or compiler configuration to see the source/target/release level the project commits to.
2. For language features, check the **finalized version**, not the preview version.
3. For APIs, check whether the package/class/method exists in the target Java version.
4. For older applications, audit library dependencies and internal JDK API usage when moving the runtime to Java 17.
5. Do not use examples requiring preview or incubator features as standard Java 17 production code.

## 7. Common Misconceptions

**“Java 17 has `record`, so `record` is a new feature of Java 17.”**  
False. `record` became stable in Java 16; Java 17 simply inherits it.

**“`switch` with arrow syntax and pattern matching in `switch` are the same feature.”**  
False. `case VALUE ->` in `switch` expressions was finalized in Java 14; pattern matching `case Type variable ->` is only preview in Java 17.

**“A sealed class is just like a final class.”**  
Not quite. `final` prevents all subclassing; `sealed` permits an explicit list of direct subtypes.

**“Java 17 is an LTS release, so every feature present in Java 17 is stable.”**  
False. LTS describes the release support lifecycle; Java 17 still contains preview and incubator JEPs.

**“Switching the runtime to Java 17 automatically enables Java 17 syntax in every project.”**  
False. Build configuration may still specify `--release 8` or `--release 11`, and build tools/IDEs must also support the target language level.

**“Java 17 has `RandomGenerator`, so any PRNG can be used to generate security tokens.”**  
False. Use `SecureRandom` for cryptographic needs, not general-purpose PRNGs.

## 8. Self-Check Scenarios

**Scenario 1:** When upgrading from Java 11 to Java 17, a team starts writing DTOs with `record`. Should they say they “adopted a new Java 17 feature” or “adopted a feature inherited by Java 17”?

**Answer:** `record` became stable in **Java 16**, so it is a feature **inherited by Java 17**. The fact that moving from Java 11 to 17 unlocked it for the project does not change the release in which `record` shipped.

**Scenario 2:** A Java 11 library uses reflection to access internal implementation details inside `java.base` and fails after upgrading the runtime to 17. Is this caused by new syntax or a JDK mechanism change?

**Answer:** This is likely an effect of **strong encapsulation of JDK internals in Java 17**. Inspect the stack trace, upgrade the library, and migrate to supported public APIs.

**Scenario 3:** You want to represent a business result that can only be `Success`, `Failure`, or `Pending`, without letting outside code add a fourth type. What should you consider?

**Answer:** You can use a `sealed interface` with a `permits` list for those result types; each direct subtype must satisfy the `final`, `sealed`, or `non-sealed` rule. If your goal is truly to close the entire hierarchy, avoid leaving a `non-sealed` branch open unintentionally.

**Scenario 4:** An online article uses `case String s ->` inside a `switch` and calls it “standard Java 17.” Is that accurate?

**Answer:** No. Pattern matching for `switch` is **preview in Java 17**, even though `switch` expressions in general were finalized in Java 14.

## 9. Official References

- [Oracle Java SE 17 — Java Language Changes](https://docs.oracle.com/en/java/javase/17/language/java-language-changes-release.html): table of stabilization milestones for language features across releases.
- [Oracle JDK 17 — Significant Changes](https://docs.oracle.com/en/java/javase/17/migrate/significant-changes-jdk-release.html): API and runtime changes plus notes for migrating to Java 17.
- [OpenJDK JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): specification and design motivation for `sealed`.
- [OpenJDK JEP 395 — Records](https://openjdk.org/jeps/395) and [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394): two features finalized in Java 16.
- [OpenJDK JEP 356 — Enhanced Pseudo-Random Number Generators](https://openjdk.org/jeps/356): Java 17's PRNG API.
- [OpenJDK JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): key compatibility change.
- [OpenJDK JEP 406 — Pattern Matching for switch (Preview)](https://openjdk.org/jeps/406): confirms the preview status of this feature in Java 17.

**Key takeaway:** Identify feature versions by their **finalization milestone**. On Java 17, you can use many modern constructs introduced from Java 8–16; Java 17's own notable additions include finalized `sealed` types, the `RandomGenerator` API, and improvements in encapsulation, security, runtime, and platform support.
