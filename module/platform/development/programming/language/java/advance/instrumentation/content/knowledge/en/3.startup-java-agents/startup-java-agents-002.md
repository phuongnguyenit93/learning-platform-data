# `Premain-Class` and the Two Valid `premain` Signatures

When starting a Java application with the `-javaagent` option, the JVM needs to know **which class is the agent's entry point** and **which method in that class must be invoked before the application's `main`**. These two things have a clear contract:

- The `Premain-Class` attribute in the **main section of the manifest** of the agent JAR specifies the *binary name* of the agent class.
- The agent class provides one of **two valid `public static void premain` signatures**. The JVM prioritizes the signature accepting `Instrumentation`; only when this signature is absent does the JVM try the signature accepting `String`.

This is the agent startup mechanism (*startup agent*) in Java instrumentation. `Premain-Class` does not contain a path to `.java`, nor does it turn a regular `main` into `premain`.

## 1. The Big Picture When the JVM Starts with `-javaagent`

Syntax:

```bash
java -javaagent:<path-to-agent.jar>[=<agent-options>] -cp <classpath> <MainClassName>
```

The `<...>` placeholders above are symbols to be replaced with actual values, not commands to be run literally. The runnable examples in the following sections use concrete JAR names and class names.

Main flow:

```text
java -javaagent:agent-two.jar=mode=demo -cp out demo.App
             |
             v
JVM opens agent-two.jar
             |
             v
Reads META-INF/MANIFEST.MF
             |
             v
Finds Premain-Class: demo.AgentTwo
             |
             v
Loads demo.AgentTwo, searches for premain in priority order
             |
             +-- premain(String, Instrumentation) exists? --> invoke this signature
             |
             +-- not found? --> search for premain(String) --> invoke if valid
             |
             v
premain performs initialization and returns
             |
             v
Application runs demo.App.main(String[])
```

The JVM has already gone through the necessary initialization phase before invoking `premain`, so you should not assume that *no Java classes have been loaded yet* at the time the agent starts. The key guarantee is that the startup agent's `premain` runs **before the application's `main`**; if it needs to monitor classes, the agent typically registers a transformer right inside `premain`.

> **Separation of responsibilities:** the manifest selects the **agent class**; the `premain` signature selects **how the JVM invokes the entry point**; `Instrumentation` provides **the API for the agent to register and manage instrumentation**. Concrete bytecode modification, if any, belongs to the transformer and the agent's logic.

## 2. What Is `Premain-Class`?

In a standard JAR, the manifest is located at:

```text
META-INF/MANIFEST.MF
```

A minimal manifest for an agent named `demo.AgentTwo`:

```text
Manifest-Version: 1.0
Premain-Class: demo.AgentTwo

```

Details to understand accurately:

1. The attribute name is **`Premain-Class`**; the value `demo.AgentTwo` is the *binary name* of the class, including the package, using dots (`.`).
2. Do not write `demo/AgentTwo.class`, `src/demo/AgentTwo.java`, `AgentTwo.java`, or `demo.AgentTwo.class` for this value.
3. The attribute must be in the **main section** at the top of the manifest. A header placed after a `Name: ...` entry of a separate section has no effect in identifying a startup agent.
4. The manifest file uses `Name: value` syntax with newline characters; to avoid errors when writing the file manually, end the main section with a blank line as shown in the example.
5. The corresponding class must actually be present in the agent JAR or be loadable through an appropriate class loading mechanism. In the learning examples, we package `demo/AgentTwo.class` directly into the JAR.
6. Merely placing the JAR on `-cp` does **not** make the JVM automatically invoke `premain`; the `-javaagent` option is what activates the corresponding startup-agent mechanism.

An application JAR's manifest can use `Main-Class`, but that answers the question *which application to run*. `Premain-Class` answers the question *which agent to start*. The two attributes serve two different entry points.

## 3. The Two `premain` Signatures Supported by the Specification

### 3.1. The Two-Parameter Signature: Preferred Choice

```java
public static void premain(String agentArgs, Instrumentation inst)
```

To use the signature above in a Java class, import:

```java
import java.lang.instrument.Instrumentation;
```

- `public`: the JVM can invoke the method as an entry point according to the contract.
- `static`: the JVM does not need to create an agent instance to invoke it.
- `void`: the method does not return a value.
- `premain`: **exact name, exact case**.
- `String agentArgs`: the options string passed after the `=` sign of `-javaagent`.
- `Instrumentation inst`: the object provided by the JVM to the agent to interact with the instrumentation API.

Example of using `Instrumentation`:

```java
public static void premain(String agentArgs, Instrumentation inst) {
    System.out.println("Agent started: " + agentArgs);
    System.out.println("Can retransform: "
            + inst.isRetransformClassesSupported());
}
```

This is an **illustrative method snippet**, not a standalone class file. The value of `isRetransformClassesSupported()` depends on the JVM capabilities and agent configuration; you must not assume it is always `true`. When you want to call `inst.addTransformer(...)` or other APIs, the two-parameter form is the most direct and clear choice.

### 3.2. The One-Parameter Signature: Valid Fallback Option

```java
public static void premain(String agentArgs)
```

This form is still officially supported by the JVM. It can perform initialization work such as reading configuration, preparing logging, or connecting to auxiliary services; however, it **does not receive the `Instrumentation` object directly via a parameter**.

Illustrative method example:

```java
public static void premain(String agentArgs) {
    System.out.println("Starting agent with: " + agentArgs);
}
```

Not receiving `Instrumentation` in the one-parameter signature does **not** mean the JVM does not support instrumentation. It only means that method is not passed an `Instrumentation` reference through this entry point.

### 3.3. What If the Agent Declares Both?

The method lookup rule in order:

1. The JVM tries `public static void premain(String, Instrumentation)` first.
2. **Only when there is no matching method in step 1** does the JVM try `public static void premain(String)`.
3. No valid signature: the agent fails to start; for a startup agent, the JVM aborts application startup.
4. Both signatures are present: **only the two-parameter signature is invoked** for that startup; the JVM does not invoke both sequentially.

This is the overload selection rule of the agent mechanism, not a behavior where "Java automatically calls every overload with the same name". The signature list does not allow swapping parameter order or replacing parameter types with similar types.

| Declaration in agent class | Valid for `-javaagent`? | Result |
|---|---|---|
| `public static void premain(String, Instrumentation)` | Yes | Prioritized for invocation |
| `public static void premain(String)` | Yes | Invoked if the two-parameter form is absent |
| Both forms above | Yes | Only the two-parameter form is invoked |
| `public void premain(String, Instrumentation)` | No | Missing `static` |
| `private static void premain(String, Instrumentation)` | No | Missing `public` |
| `public static int premain(String, Instrumentation)` | No | Wrong return type |
| `public static void premain(Instrumentation, String)` | No | Wrong parameter order |
| `public static void premain(String[] args)` | No | `String[]` is different from `String` |
| `public static void preMain(String, Instrumentation)` | No | Wrong method name |

This table evaluates **each signature individually**; if a class has both an invalid method and a valid method, the JVM can still select the valid method.

## 4. Complete Java 17+ Example: Running Both Signatures and Demonstrating Priority Order

We create an application `demo.App` and three agent classes:

- `demo.AgentTwo`: has only the two-parameter signature.
- `demo.AgentOne`: has only the one-parameter signature.
- `demo.AgentBoth`: has both, printing which signature is actually selected.

The example uses only the JDK, **requiring no Maven, Gradle, or external libraries**. Each agent JAR uses its own manifest, making it easy to see clearly which class `Premain-Class` points to.

Directory structure to create:

```text
premain-example/
├── src/
│   └── demo/
│       ├── App.java
│       ├── AgentTwo.java
│       ├── AgentOne.java
│       └── AgentBoth.java
└── manifests/
    ├── two.mf
    ├── one.mf
    └── both.mf
```

### 4.1. Main Application: `src/demo/App.java`

```java
package demo;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("[app] main started");
    }
}
```

This application does not reference the agent. We will activate the agent using a JVM option at runtime, so the startup agent mechanism is independent of the contents of `App.main`.

### 4.2. Two-Parameter Agent: `src/demo/AgentTwo.java`

```java
package demo;

import java.lang.instrument.Instrumentation;

public final class AgentTwo {
    private AgentTwo() {
    }

    public static void premain(String agentArgs, Instrumentation inst) {
        System.out.println("[two] args=" + agentArgs);
        System.out.println("[two] instrumentation=" + (inst != null));
    }
}
```

The two-parameter method shows that the JVM passes both the options string and the `Instrumentation` object. Printing `inst != null` avoids depending on optional JVM capabilities; this is an entry-point check and does not perform bytecode transformation yet.

### 4.3. One-Parameter Agent: `src/demo/AgentOne.java`

```java
package demo;

public final class AgentOne {
    private AgentOne() {
    }

    public static void premain(String agentArgs) {
        System.out.println("[one] args=" + agentArgs);
    }
}
```

When the manifest points to `demo.AgentOne`, the JVM cannot find the two-parameter signature and uses the one-parameter form. This is a **valid** fallback, not an error.

### 4.4. Agent Declaring Both: `src/demo/AgentBoth.java`

```java
package demo;

import java.lang.instrument.Instrumentation;

public final class AgentBoth {
    private AgentBoth() {
    }

    public static void premain(String agentArgs) {
        System.out.println("[both] selected one-argument premain");
    }

    public static void premain(String agentArgs, Instrumentation inst) {
        System.out.println("[both] selected two-argument premain");
    }
}
```

The one-parameter method is intentionally placed **above** in the source to test: declaration order in the `.java` file does not determine how the JVM selects the signature. The JVM still prioritizes the two-parameter method.

### 4.5. Creating the Three Manifest Files

**`manifests/two.mf`:**

```text
Manifest-Version: 1.0
Premain-Class: demo.AgentTwo

```

**`manifests/one.mf`:**

```text
Manifest-Version: 1.0
Premain-Class: demo.AgentOne

```

**`manifests/both.mf`:**

```text
Manifest-Version: 1.0
Premain-Class: demo.AgentBoth

```

Save the files as plain text, preserving the trailing newline at the end of each file. The blank line after `Premain-Class` in each example serves to terminate the main section. `jar --manifest` puts this content into `META-INF/MANIFEST.MF` of the corresponding JAR.

### 4.6. Compiling and Packaging the Three JARs

Open a terminal in the `premain-example` directory, using JDK 17+ (which includes `javac`, `jar`, `java`).

The commands below do not use wildcards, so they can be entered one by one in Bash, PowerShell, or cmd:

```bash
mkdir out

javac --release 17 -encoding UTF-8 -d out src/demo/App.java src/demo/AgentTwo.java src/demo/AgentOne.java src/demo/AgentBoth.java

jar --create --file agent-two.jar --manifest manifests/two.mf -C out demo/AgentTwo.class
jar --create --file agent-one.jar --manifest manifests/one.mf -C out demo/AgentOne.class
jar --create --file agent-both.jar --manifest manifests/both.mf -C out demo/AgentBoth.class
```

- `javac --release 17` produces class files compatible with Java 17.
- `-d out` places class files according to their package, for example `out/demo/AgentTwo.class`.
- `jar --create` packages the agent into a JAR; `--manifest` imports the `Premain-Class` header properly.
- `-C out demo/AgentTwo.class` stores the `demo/AgentTwo.class` entry **at the archive root**, without storing the `out/` directory prefix.
- `out` is a new output directory for the example; there is no need to modify the system classpath.

To inspect the entries of an agent JAR:

```bash
jar --list --file agent-two.jar
```

The list must contain `META-INF/MANIFEST.MF` and `demo/AgentTwo.class`. You can read the manifest with an archive extraction tool or a Java API to be sure the `Premain-Class` name is exact; merely seeing `.class` in the JAR is not enough to prove the header is correct.

### 4.7. Running and Comparing Stdout

**Case A: without an agent**

```bash
java -cp out demo.App
```

Stdout:

```text
[app] main started
```

**Case B: agent with two parameters**

```bash
java -javaagent:agent-two.jar=mode=demo -cp out demo.App
```

Stdout:

```text
[two] args=mode=demo
[two] instrumentation=true
[app] main started
```

Note that `mode=demo` is preserved as **a single `String`**; the JVM does not automatically convert it into a configuration `Map`.

**Case C: agent with only one parameter**

```bash
java -javaagent:agent-one.jar=hello -cp out demo.App
```

Stdout:

```text
[one] args=hello
[app] main started
```

**Case D: agent with both overloads**

```bash
java -javaagent:agent-both.jar=check -cp out demo.App
```

Stdout:

```text
[both] selected two-argument premain
[app] main started
```

There is no `selected one-argument premain` line: the JVM does **not** invoke both and does not select based on the order of appearance in the source.

**Case E: multiple startup agents on the same Java command**

```bash
java -javaagent:agent-one.jar=first -javaagent:agent-two.jar=second -cp out demo.App
```

Stdout:

```text
[one] args=first
[two] args=second
[two] instrumentation=true
[app] main started
```

When `-javaagent` appears multiple times, the `premain` methods are invoked in **the order of the agents on the command line**, before the application's `main`. Multiple agents performing instrumentation simultaneously can cause interactions in advanced topics; this example only illustrates initialization order.

## 5. Why Are These Signatures Similar to and Different from `main(String[] args)`?

| Point of comparison | Application `main` | Startup agent `premain` |
|---|---|---|
| Entry point selected via | Class name run in the `java` command, or `Main-Class` with `java -jar` | `Premain-Class` in the JAR passed via `-javaagent` |
| Standard signature | `public static void main(String[] args)` | One of the two `premain` signatures mentioned |
| Command arguments | Usually an array of application arguments | `agentArgs` is **a single string** of agent options |
| `Instrumentation` object | Not a parameter of `main` | Passed to the `premain(String, Instrumentation)` signature |
| Timing | After startup agent | Before application `main` |
| Responsibility | Application logic | Initializing observation/transformation of the program if configured |

For example:

```bash
java -javaagent:agent-one.jar=agent-mode=trace -cp out demo.App app-mode=prod
```

The agent receives a `String` with content `agent-mode=trace`; the application receives an element in `String[] args` with content `app-mode=prod`. The two argument sources are separate, and `main(String[])` should not be used to replace `premain(String)`.

If multiple options are needed for the agent, for example:

```bash
java -javaagent:agent-one.jar=mode=trace,level=debug -cp out demo.App
```

The agent receives the raw string `mode=trace,level=debug`. **The agent must design and handle its own parsing syntax**, value validation, defaults, and input errors; the JVM does not automatically interpret `level=debug`.

## 6. `Premain-Class`, `Agent-Class`, `Launcher-Agent-Class`: Do Not Confuse Them

Java has different agent startup mechanisms. Each manifest attribute routes to a different entry point:

| Manifest attribute | Activation mechanism | Method searched for |
|---|---|---|
| `Premain-Class` | `java -javaagent:agent.jar ...` at JVM startup | `premain(...)` |
| `Agent-Class` | Mechanism to attach/load an agent into an already running JVM (if supported by the runtime) | `agentmain(...)` |
| `Launcher-Agent-Class` | Mechanism for an agent packaged in an executable JAR supported by the launcher | `agentmain(...)` |
| `Main-Class` | Application entry point `java -jar app.jar` | `main(...)` |

In particular, `Launcher-Agent-Class`, even though it runs the agent before the application `main`, still uses `agentmain` according to the specification, **not** `premain`. This is a common source of confusion when relying only on the phrase "before `main`".

An agent JAR can declare both `Premain-Class` and `Agent-Class` if it supports both startup modes. When run with `-javaagent`, the JVM uses `Premain-Class` and ignores `Agent-Class` to select the startup entry point. Flags such as `Can-Retransform-Classes` / `Can-Redefine-Classes` relate to instrumentation capabilities; they **do not replace** `Premain-Class` and **do not create** a valid `premain` method.

## 7. What `premain` Needs to Do and Practical Limitations

A `premain` typically:

1. Receives and validates the agent's own options.
2. Initializes configuration and supporting components before the application runs.
3. If using the two-parameter signature, registers a `ClassFileTransformer` via `Instrumentation.addTransformer(...)` when needed.
4. Performs other necessary setup and then **returns** so the JVM can proceed to invoke `main`.

What **does not happen automatically** just because `Premain-Class` and `premain` exist:

- No guarantee that bytecode has been modified: the example above only prints logs; it does not register a transformer.
- No transformer is created automatically: registration code and actual `transform` logic are required.
- No guarantee that all application classes have not yet been loaded before `premain`.
- No mechanism to automatically invoke `premain` if the application merely imports the agent class.
- No guarantee that the agent is allowed to redefine/retransform every class: specific JVM capabilities and limitations must be checked.

`premain` is invoked by the JVM very early in the startup lifecycle and can create threads or call APIs like normal Java code. However, the agent must avoid hanging, waiting on conditions that depend on an unstarted application, or throwing unhandled exceptions: if the startup agent fails to initialize or `premain` throws an uncaught exception, the JVM will abort startup instead of continuing to run `main`.

An illustrative option-handling example, not standalone-runnable because it is only a single method:

```java
public static void premain(String agentArgs, Instrumentation inst) {
    if (agentArgs == null || agentArgs.isBlank()) {
        System.err.println("Agent requires mode=<value>");
        return;
    }

    // Perform initialization/transformer registration after validating options.
}
```

Here, `return` is a policy choice of the agent: skip further initialization and let the JVM continue. If the agent has a critical configuration error, it may need to signal failure instead of silently running the application; this must be decided according to the requirements of the system being instrumented.

## 8. Diagnosing When `premain` Is Not Invoked or Startup Fails

| Symptom | What to check |
|---|---|
| Application runs but no agent logs appear | Was `-javaagent:<jarpath>` actually used? Does it point to the right JAR? |
| JVM reports missing `Premain-Class` | Is the header in the **main section** of `META-INF/MANIFEST.MF`? Was only `Main-Class` or `Agent-Class` accidentally declared? |
| JVM cannot find the agent class | Does the binary name `demo.AgentTwo` have the right package? Does the JAR contain `demo/AgentTwo.class`? |
| JVM cannot find the `premain` method | Is it `public static void`, with the exact parameter types and order, and the exact lowercase name `premain`? |
| Both overloads exist but only one method's log appears | This is standard behavior: the two-parameter signature is prioritized |
| `NoClassDefFoundError` occurs at startup | Check dependencies and whether the agent's class loader can see them; package dependencies when needed |
| `premain` throws an exception, `main` does not run | Inspect the stack trace and handle the cause in the agent; startup agent failure can cause the JVM to abort |
| Agent log appears but application behavior is unchanged | Is it only initializing/logging, or has it registered a transformer and returned valid new bytes? |

You can inspect the compiled signatures in the example using:

```bash
javap -p -classpath out demo.AgentBoth
```

In the class declaration displayed by `javap`, there must be both a method accepting `String` and a method accepting `String, java.lang.instrument.Instrumentation`. `javap` is a step for inspecting bytecode/signatures in the class file; it does **not** prove which method the JVM selected at runtime. To prove the actual selection, use the stdout in section 4.7.

An additional note on packaging: if the agent JAR uses external libraries, the library classes must be findable by the agent class loader. Dependencies can be packaged into the agent JAR using an appropriate build tool. The example here uses no external libraries, so this requirement does not arise.

## 9. Self-Check Scenarios

**Question 1.** The manifest specifies `Premain-Class: demo.AgentBoth`, and the class has both signatures. Which method does the JVM invoke?

**Answer:** `premain(String, Instrumentation)`; the one-parameter signature is a fallback and is not invoked.

**Question 2.** A class has `public static void premain(String[] args)` and `public static void main(String[] args)`. Is this a valid startup agent?

**Answer:** No, because `String[]` is not `String` in either of the two required `premain` signatures; `main` cannot substitute for it.

**Question 3.** Why is `Premain-Class: demo/AgentTwo.class` not a valid declaration?

**Answer:** The value must be the binary class name `demo.AgentTwo`, not an archive path with `/` slashes and a `.class` extension.

**Question 4.** There is a valid `Premain-Class` and `premain` method, but it is run with `java -cp agent-two.jar demo.App`. Does the JVM automatically activate the agent?

**Answer:** No. A startup agent pathway must be used, for example `-javaagent:agent-two.jar`.

**Question 5.** An agent needs `Instrumentation.addTransformer(...)`; which signature should it choose?

**Answer:** The `premain(String agentArgs, Instrumentation inst)` form to receive `Instrumentation` directly from the JVM.

**Question 6.** Using two consecutive `-javaagent` options, after which agent does the JVM invoke `main`?

**Answer:** After the corresponding startup `premain` methods have been invoked in the order declared and completed successfully, the JVM then invokes the application `main`.

## 10. Key Takeaways

- `Premain-Class` is a header of the **agent JAR manifest**, carrying the **binary name** of the class containing `premain`, not a file name or method name.
- Only two startup agent entry-point signatures are specified: `public static void premain(String, Instrumentation)` and `public static void premain(String)`.
- The JVM **prioritizes the two-parameter signature** and falls back to the one-parameter signature; having both exist does not mean both run.
- `agentArgs` is **a single `String` of options specific to the agent**; `Instrumentation` is only passed to the two-parameter signature.
- `premain` is invoked before the application `main`; agent initialization errors or unhandled exceptions can prevent the application from starting.
- An agent being invoked successfully does not necessarily mean bytecode has been altered. Starting the agent and installing transformations are two separate steps.

## Reference Documentation

- Oracle Java 17 — [Package `java.lang.instrument`: Starting an Agent from the Command-Line Interface](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html)
- Oracle Java 17 — [Interface `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html)
- Oracle Java 21 — [JAR File Specification: manifest, main attributes](https://docs.oracle.com/en/java/javase/21/docs/specs/jar/jar.html)
