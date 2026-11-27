# Distinguishing Final, Preview, and Incubator Features in Java 17

When reading Java 17 feature lists, you will come across labels such as **final/permanent**, **preview**, and **incubator**. These labels indicate **the maturity level and compatibility commitment of each feature in a specific JDK release**. Knowing how to tell them apart helps you choose appropriate APIs and syntax, configure compilation properly, and assess risks when upgrading Java.

> **Scope:** This lesson uses **JDK 17** for hands-on examples and compares with newer Java versions when needed. A feature's status must always be tied to a **Java version**: a feature that is preview in Java 17 may already be finalized in Java 21. Java 17 incubator examples are shown to explain the mechanism, not as instructions to adopt outdated experimental APIs in new Java projects.

## 1. Three Feature Maturity Levels

| Criterion | Final / Permanent | Preview | Incubator |
|---|---|---|---|
| Goal | Deliver a completed feature for standard everyday use | Put a nearly complete design in front of the community for testing and feedback | Experiment with a new API or module before deciding its long-term shape |
| Typical scope | Language syntax, JVM, standard APIs | Language/JVM features; may include preview APIs | Experimental libraries/APIs or modules distributed in the JDK |
| Status in JDK 17 | Usable directly under normal conditions | Disabled by default; must be enabled explicitly at compile and run time | Usually resides in a `jdk.incubator.*` module; module resolution must be declared when used |
| Typical flag | No `--enable-preview` needed | `--enable-preview` | `--add-modules <module-name>` for non-modular programs |
| Likelihood of change in later Java releases | Higher compatibility commitment; may still evolve or be deprecated through standard processes | Syntax/behavior may change, remain preview, be finalized, or be withdrawn | API/module may change, become a standard API elsewhere, or be removed from the JDK |
| Usage recommendation | Default choice for long-lived application code | Learning, experimentation, verification against the exact JDK version | Controlled experimentation; isolate dependencies for easier upgrades |

**Important:** “Available in the JDK” does not mean “finalized.” Conversely, **LTS** (Long-Term Support) describes the support policy of a Java release; it does not turn preview or incubator features in that release into stable features.

In Java documentation, `final` or `permanent` refers to a **feature's maturity status**. Do not confuse this with the Java `final` keyword used on variables, methods, or classes.

## 2. Final Features: Usable Without Experimental Flags

Final features have completed standardization for the corresponding Java release. On JDK 17, representative examples include:

- **Sealed classes/interfaces** — finalized in **Java 17**, per [JEP 409](https://openjdk.org/jeps/409).
- **Records** — finalized since **Java 16**, per [JEP 395](https://openjdk.org/jeps/395).
- **Pattern matching for `instanceof`** — finalized since **Java 16**, per [JEP 394](https://openjdk.org/jeps/394).
- **Text blocks** — finalized since **Java 15**, per [JEP 378](https://openjdk.org/jeps/378).
- **Switch expressions** — finalized since **Java 14**, per [JEP 361](https://openjdk.org/jeps/361).

Features finalized in earlier Java releases can still be used normally in Java 17. The fact that a feature appears in a Java 17 overview does not necessarily mean it was first finalized in Java 17.

### Example: `sealed`, `record`, and `instanceof` in Java 17

Create the file `StableDemo.java`:

~~~java
sealed interface Payment permits Card, Cash {}

record Card(String lastFourDigits) implements Payment {}

record Cash(long amount) implements Payment {}

public class StableDemo {
    static String describe(Payment payment) {
        if (payment instanceof Card card) {
            return "Paid by card ****" + card.lastFourDigits();
        }
        return "Paid in cash";
    }

    public static void main(String[] args) {
        Payment payment = new Card("1234");
        System.out.println(describe(payment));
    }
}
~~~

Here:

1. `sealed interface Payment` specifies that only the permitted types may directly implement this interface.
2. The two `record` types represent data concisely while satisfying the `sealed` subtype rules because records are implicitly `final` by design.
3. `payment instanceof Card card` both checks the type and binds the `card` variable for use in the matching branch.

Compile and run with **JDK 17**:

~~~bash
javac --release 17 StableDemo.java
java StableDemo
~~~

Output:

~~~text
Paid by card ****1234
~~~

**No `--enable-preview` is required.** If the compiler reports that it does not recognize `sealed` or `record`, check your JDK version and the project's `--source`/`--release` configuration.

### Understanding stability accurately

“Final feature” means it is the right choice for long-term code, though it does not mean every library detail stays unchanged forever. Java still has processes to add APIs, mark members `@Deprecated`, and evolve the platform deliberately. In particular, internal APIs like `sun.*` or `jdk.internal.*` do not become supported APIs just because they ship inside a finalized JDK.

## 3. Preview: Complete Enough to Try, Not Yet Permanently Committed

A **preview feature** is a feature whose design, specification, and implementation are complete enough for the community to try out, yet not locked in as a permanent part of the platform. The Java team can still adjust its syntax and semantics based on feedback. This mechanism is specified in [JEP 12](https://openjdk.org/jeps/12).

In **Java 17**, an important example is **Pattern Matching for `switch` (Preview)**, per [JEP 406](https://openjdk.org/jeps/406).

### Do not confuse `switch` expressions with pattern matching for `switch`

These two uses of `switch` have different statuses in Java 17:

~~~java
// Switch expression: finalized since Java 14, runs normally in Java 17.
String label = switch (day) {
    case 6, 7 -> "Weekend";
    default -> "Weekday";
};
~~~

~~~java
// Pattern matching in switch: PREVIEW in Java 17.
// Must enable --enable-preview at both compile and run time.
String label = switch (value) {
    case Integer n -> "Integer: " + n;
    case String s -> "String: " + s;
    default -> "Other type";
};
~~~

What makes the second example a preview feature in Java 17 is the **type patterns** such as `case Integer n` and `case String s`, not merely the use of the arrow `->`.

### Example runnable on JDK 17

Create the file `PreviewDemo.java`:

~~~java
public class PreviewDemo {
    static String describe(Object value) {
        return switch (value) {
            case Integer number -> "Integer: " + number;
            case String text -> "String: " + text;
            case null -> "null";
            default -> "Other";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(17));
        System.out.println(describe("Java"));
        System.out.println(describe(null));
    }
}
~~~

Compile:

~~~bash
javac --enable-preview --release 17 PreviewDemo.java
~~~

Run:

~~~bash
java --enable-preview PreviewDemo
~~~

Output:

~~~text
Integer: 17
String: Java
null
~~~

During compilation, `javac` may print a notice that preview features are in use; this is expected.

**Why must it be enabled in both steps?**

- `javac` needs `--enable-preview` to accept preview syntax and semantics. With JDK 17's `javac`, combine it with `--release 17` (or `--source 17`).
- `java` needs `--enable-preview` to run code compiled with preview features of that matching Java release. Enabling it only at compile time is not enough.
- You cannot use a newer JDK's `javac` to “re-enable Java 17 preview” solely via `--release 17`. Each release's preview features are tied to that exact release. To run Java 17 preview examples, use a **JDK 17 toolchain**.

Technically, `.class` files that depend on preview features in Java 17 carry class file version **61.65535**; the minor version `65535` marks a preview dependency. Such class files are bound to the Java version they were compiled with, unlike regular Java 17 class files (`61.0`). That is one reason upgrading the JDK requires recompiling preview-using sources.

### What happened after Java 17?

Pattern Matching for `switch` went through further previews in Java 18–20 before becoming **final in Java 21 (JEP 441)**. This illustrates how a feature progresses from preview to final. The syntax and rules of the finalized version may differ from earlier previews; when upgrading a project, read the documentation of the **target version** instead of copying Java 17 preview code verbatim.

## 4. Incubator: Testing New APIs and Modules in the JDK

**Incubator** modules are used for APIs or modules that developers want to put into users' hands early to gauge usefulness and collect design feedback. They are not part of the stable Java SE API.

In **JDK 17**, two examples are:

| Feature in JDK 17 | JEP | Module | Note |
|---|---|---|---|
| Vector API (Second Incubator) | [JEP 414](https://openjdk.org/jeps/414) | `jdk.incubator.vector` | Experiments with expressing SIMD operations in Java |
| Foreign Function & Memory API (Incubator) | [JEP 412](https://openjdk.org/jeps/412) | `jdk.incubator.foreign` | Experimental API **in JDK 17**; should not be learned as current syntax for new applications |

From a modern compatibility perspective, the history of the Foreign Function & Memory API is especially instructive: after multiple incubator and preview rounds, it became **final in Java 22** via [JEP 454](https://openjdk.org/jeps/454), residing in package `java.lang.foreign`. Study the official API docs of the Java version you actually use rather than copying old `jdk.incubator.foreign` code.

### Example: Vector API in the exact JDK 17 environment

Create the file `VectorDemo.java`:

~~~java
import java.util.Arrays;
import jdk.incubator.vector.IntVector;
import jdk.incubator.vector.VectorSpecies;

public class VectorDemo {
    public static void main(String[] args) {
        VectorSpecies<Integer> species = IntVector.SPECIES_PREFERRED;
        int lanes = species.length();

        int[] left = new int[lanes];
        int[] right = new int[lanes];

        for (int i = 0; i < lanes; i++) {
            left[i] = i;
            right[i] = 10;
        }

        IntVector a = IntVector.fromArray(species, left, 0);
        IntVector b = IntVector.fromArray(species, right, 0);

        int[] result = new int[lanes];
        a.add(b).intoArray(result, 0);

        System.out.println(Arrays.toString(result));
    }
}
~~~

Run with **JDK 17**:

~~~bash
javac --add-modules jdk.incubator.vector VectorDemo.java
java --add-modules jdk.incubator.vector VectorDemo
~~~

The output is an array of numbers `10, 11, 12, ...`, with length equal to `species.length()`. The vector size is chosen based on the platform, so do not assume there are always 4 or 8 lanes. You may see a warning such as `using incubating module(s): jdk.incubator.vector` during compilation/execution; that warning reminds you the API is incubating.

**Why use `--add-modules` instead of `--enable-preview`?**

- `--add-modules jdk.incubator.vector` instructs the module system to resolve the incubator module so code can reference its API.
- `--enable-preview` enables preview language/JVM/API features defined for that JDK release; it does **not replace** declaring incubator modules.
- If a project uses **named modules**, you typically need to declare the dependency in `module-info.java`, such as `requires jdk.incubator.vector;`. The exact setup depends on how you compile, package, and run the application.

For long-lived systems, evaluate the dependency risk and migration path to a stable API. Do not assume module names, package names, or method signatures from a JDK 17 incubator will stay unchanged in later Java releases.

## 5. Comparing Options for the Same Goal: Which Should You Choose?

Suppose you need to determine an object's type in order to display information.

**Option using a final Java 17 feature:** use pattern matching for `instanceof`.

~~~java
static String describe(Object value) {
    if (value instanceof Integer n) {
        return "Integer: " + n;
    }
    if (value instanceof String s) {
        return "String: " + s;
    }
    return value == null ? "null" : "Other";
}
~~~

This code requires no preview flags and is the right default choice if the application must stay compatible with **Java 17**.

**Option using preview in Java 17:** use pattern matching for `switch` as in Section 3. The code is concise, yet it brings compile/run flags and requires adjustments when switching JDKs. If the project can upgrade to Java 21 or newer, consult the **finalized** `switch` pattern matching syntax of that target version.

With **incubator** modules, the decision carries even more weight: you are opting into a dependency on an **experimental API**. Use incubator features to explore new capabilities or run controlled experiments while preparing a replacement plan for future JDK updates.

| Project Context | Recommended Approach |
|---|---|
| Production Java 17 project requiring stable deployment and updates | Prefer finalized syntax and APIs on Java 17 |
| Evaluating a proposed new language feature | Test preview in a separate branch/component, pin the JDK, and pass the flag at every step |
| Evaluating an experimental library shipped in the JDK | Use the incubator per the **exact JDK version's** documentation and isolate the dependency |
| Preparing to upgrade Java 17 to a newer version | Re-check the status of **each feature** in the target version; drop flags once finalized and adapt to any syntax/API changes |

## 6. How to Identify a Feature's Status

When you encounter unfamiliar syntax or APIs, proceed in order:

1. **Check your actual JDK** with `java -version` and `javac -version`. Both commands should point to the intended version.
2. **Consult version-specific documentation**, such as [Java 17 Language Changes Summary](https://docs.oracle.com/en/java/javase/17/language/java-language-changes-summary.html) and release notes. Do not infer behavior from tutorials written for another JDK.
3. **Check the corresponding JEP.** JEP titles or release histories typically explicitly state `Preview`, `Second Preview`, `Incubator`, or `Final`.
4. **Check the Java API Documentation for the exact version.** `jdk.incubator.*` packages carry incubator notices; experimental APIs should not be treated as durable standard APIs.
5. **Assess the impact across the entire application lifecycle**: compilation, runtime, tests, CI/CD, IDE, packaging, and JDK upgrades.

To inspect which modules your installed JDK provides:

~~~bash
java --list-modules
~~~

Seeing `jdk.incubator.vector` in that list means the JDK **ships the module**. It does not mean the module is finalized, nor does it guarantee API compatibility with another Java version.

### Common errors and warnings

| Symptom | Common Cause | Fix |
|---|---|---|
| `javac` reports preview features are disabled | Using preview syntax without enabling it at compile time | Use JDK 17's `javac` with `--enable-preview --release 17` |
| `java` refuses to run a preview-dependent class | Missing flag at runtime or running on the wrong Java version | Run with the exact JDK 17 using `java --enable-preview` |
| `package jdk.incubator.vector is not visible` or module not found | Incubator module is unresolved, or the current JDK lacks that module | Check `java --list-modules`; configure `--add-modules` and the right toolchain |
| Java 17 code compiles, then fails when using the example on a newer JDK | Preview syntax/status or incubator API changed | Open the newer JDK's docs and migrate to the finalized API/syntax if available |

**Build tool note:** If the project uses Maven or Gradle, options must be configured for every relevant task: compile, test, and runtime. Adding a flag to one step does not automatically apply it to the others.

## 7. How Can a Feature Change Status?

The lifecycle is often pictured as follows:

~~~text
Proposal / Research
       |
       +--> Preview (may repeat across releases)
       |          |
       |          +--> Final
       |          +--> Continue preview / revise
       |          +--> Withdrawn
       |
       +--> Incubator (may repeat across releases)
                  |
                  +--> Standard API (may change package/usage)
                  +--> Continue incubator / revise
                  +--> Withdrawn
~~~

This is a high-level overview, not a mandatory path for every JEP. Examples of real transitions that occurred:

- **Sealed classes:** preview in Java 15–16, **final in Java 17**.
- **Pattern matching for `switch`:** preview starting in Java 17, **final in Java 21**.
- **Foreign Function & Memory API:** progressed through incubator and preview stages, then **final in Java 22** as `java.lang.foreign`.

Because status can change, the right question is always **“What category does feature X belong to in Java version Y?”** rather than merely asking “Is feature X a preview feature?”.

## 8. Self-Check Exercises

**Exercise 1.** For a project using JDK 17, classify: `record`, `sealed interface`, `case Integer n ->` inside `switch`, and `jdk.incubator.vector.IntVector`.

**Exercise 2.** A Java 17 project uses `case String s ->` in a `switch`. The developer added `--enable-preview` when compiling but forgot it on the `java` command. Explain why running can still fail and give the correct commands.

**Exercise 3.** An older article presents `jdk.incubator.foreign` as the newest way to call native functions. You are developing on JDK 22 or newer. Which API should you check instead, and why?

**Suggested answers:**

1. `record` and `sealed interface` are both final in Java 17; type patterns in `switch` are preview; `IntVector` belongs to an incubator module.
2. Preview must be enabled at both compile time and runtime: `javac --enable-preview --release 17 ...`, then `java --enable-preview ...`, using the exact JDK 17.
3. Consult the documentation for the **Foreign Function & Memory API `java.lang.foreign`**, finalized in Java 22; the JDK 17 incubator API is an outdated form and should not be copied into new code.

## 9. References

- [Oracle — Java SE 17: Language Changes Summary](https://docs.oracle.com/en/java/javase/17/language/java-language-changes-summary.html)
- [Oracle — Java SE 17: Preview Features](https://docs.oracle.com/en/java/javase/17/language/preview-language-and-vm-features.html)
- [Oracle — Java SE 17: `javac` Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)
- [Oracle — Java SE 17: `IntVector` API](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.incubator.vector/jdk/incubator/vector/IntVector.html)
- [Oracle — Java SE 21: Language Changes](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html)
- [Oracle — Java SE 22: Foreign Function & Memory API](https://docs.oracle.com/en/java/javase/22/core/foreign-function-and-memory-api.html)
- [OpenJDK — JEP 12: Preview Features](https://openjdk.org/jeps/12)
- [OpenJDK — JEP 406: Pattern Matching for `switch` (Preview)](https://openjdk.org/jeps/406)
- [OpenJDK — JEP 409: Sealed Classes](https://openjdk.org/jeps/409)
- [OpenJDK — JEP 414: Vector API (Second Incubator)](https://openjdk.org/jeps/414)
- [OpenJDK — JEP 441: Pattern Matching for `switch`](https://openjdk.org/jeps/441)
- [OpenJDK — JEP 454: Foreign Function & Memory API](https://openjdk.org/jeps/454)
