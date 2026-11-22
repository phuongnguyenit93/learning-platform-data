# `-javaagent:jarpath[=options]` and How `agentArgs` Is Received

A **startup Java agent** is code loaded and invoked by the JVM before the application's `main` method. The entry point of a startup agent is the `premain` method. The standard way to declare an agent for a Java process is the `-javaagent` JVM option, where the path points to the **agent JAR** and the part after the `=` sign is the agent's own configuration.

This lesson focuses on how the JVM accepts the `-javaagent:jarpath=options` option, how `options` is passed as the `String agentArgs` parameter, how `Premain-Class` is declared in the manifest, and how to write, package, and test a standalone startup agent using Java 17+. The example only verifies the startup mechanism and argument passing; it does not transform bytecode yet.

## 1. Exact Syntax and Meaning of Each Component

The full syntax is:

~~~text
-javaagent:<jarpath>[=<options>]
~~~

Square brackets indicate an **optional part** in the documentation; do not type `[` and `]` when executing.

| Component | Meaning | Example |
| --- | --- | --- |
| `-javaagent:` | JVM option to load an agent at startup | `-javaagent:` |
| `<jarpath>` | Relative or absolute path to a properly packaged agent JAR | `agent-demo.jar` |
| `=` after the path | Separates the JAR path from the agent configuration string | `agent-demo.jar=` |
| `<options>` | **A single string** whose semantics and syntax are defined by the agent itself | `mode=trace,sample=25` |

Complete example when running an application named `Application`:

~~~bash
java -javaagent:agent-demo.jar=mode=trace,sample=25 -cp . Application red blue
~~~

The JVM interprets these as two separate groups of data:

- Agent JAR: `agent-demo.jar`.
- Agent string passed to `premain`: `mode=trace,sample=25`.
- Application main class: `Application`; `main(String[] args)` receives exactly two arguments, `red` and `blue`.

`-javaagent` is a **Java launcher option**, so it must be placed in the position reserved for JVM options, **before** the main class name or `-jar app.jar`. Everything after the main class name/`-jar app.jar` is an application argument: if you place `-javaagent:...` there, the application may simply receive it as a string in `main(args)` and the agent will not be activated as intended.

The `-javaagent` syntax is not synonymous with `-jar`:

- `-javaagent:agent.jar` points to a JAR with **`Premain-Class`** so the JVM invokes `premain`.
- `-jar app.jar` points to an executable JAR with **`Main-Class`** (or the corresponding launcher mechanism) to invoke the application.
- `-cp` or `--class-path` specifies the classpath for application classes; it does not replace `-javaagent` and does not automatically trigger `premain`.

Example of a startup agent running together with an executable application JAR:

~~~bash
java -javaagent:agent-demo.jar=mode=trace,sample=25 -jar application.jar
~~~

`application.jar` in the command above is for illustration only: it must be a runnable application JAR, and `agent-demo.jar` must be a validly packaged agent JAR.

## 2. At What Stage Does the JVM Invoke `premain`?

High-level flow:

~~~text
java command
    |
    +-- JVM launcher parses -javaagent:jarpath[=options]
    |
    +-- JVM locates agent JAR and reads main manifest
    |       |
    |       +-- Premain-Class: agent class name
    |
    +-- JVM loads agent class, invokes premain(agentArgs, instrumentation)
    |       |
    |       +-- Agent reads configuration and initializes hooks/transformers (if any)
    |
    +-- premain returns
    |
    +-- Application starts main(String[] args)
~~~

`premain` is invoked **before the application's `main`**, which does not mean it runs before all JVM initialization activities or before all JVM class loading. Classes needed for the launcher/agent may already have been loaded. Therefore, if you later want to attach a `ClassFileTransformer`, you must consider when target classes are loaded and the appropriate retransformation capability.

The class declared in `Premain-Class` must have one of two signatures:

~~~java
public static void premain(String agentArgs, Instrumentation inst)
~~~

or:

~~~java
public static void premain(String agentArgs)
~~~

Both must be `public static` methods returning `void`. The JVM **prefers** the two-parameter variant if present, and only then tries the one-parameter variant. The `Instrumentation` object is provided by the JVM so the agent can access instrumentation capabilities (such as registering a transformer); the person running the command does not pass this object via the CLI. You can use only the one-parameter variant if the agent does not need that API, but the two-parameter variant is usually more useful for practical instrumentation.

If the JAR cannot be found, there is no valid `Premain-Class`, the agent class/`premain` method cannot be loaded, or `premain` throws an unhandled exception, startup may be aborted **before `main` runs**. Do not design a startup agent assuming that all configuration errors will be caught by the application after entering `main`.

Note the distinction: `agentmain` is the entry point for an agent loaded into a **running** JVM (when that mechanism is supported). When activated via `-javaagent` at startup, the JVM invokes `premain`; it does not invoke `agentmain` as a substitute.

## 3. What Does `agentArgs` Actually Contain?

The `<options>` part is passed to `premain` as **a single `String`**. The JVM does not automatically turn commas into a list, does not decode `key=value` pairs, does not validate `mode` or `sample`, and does not build a `Map` for you. All string-splitting conventions, default values, type checks, and error handling are the agent's responsibility.

| Invocation | Value the agent needs to interpret |
| --- | --- |
| `-javaagent:agent-demo.jar=mode=trace,sample=25` | A single string `"mode=trace,sample=25"` |
| `-javaagent:agent-demo.jar=hello=world` | A single string `"hello=world"`; the `=` inside options belongs to the data |
| `-javaagent:agent-demo.jar` | No `=options` part; code must handle the case with no configuration |
| `-javaagent:agent-demo.jar=` | Has `=` but an empty options string |
| `-javaagent:agent-demo.jar=mode=trace` | A single string `"mode=trace"`, **not** an additional argument to `main` |

On OpenJDK/HotSpot 21, when `=options` is omitted, `agentArgs` is `null`; when `=` is written with nothing following it, it is the empty string `""`. The example in the next section was run and verified against this behavior. You should not force application logic to depend on distinguishing the two states if both mean "use defaults": handle **both `null` and the empty string**.

To visualize the exact data boundary:

~~~text
java -javaagent:agent-demo.jar=mode=trace,sample=25 Application red blue
               |--------------------|             |------|
                  agentArgs (1 String)            main(args) (2 Strings)
~~~

In the illustration above, `Application` must be on the classpath; the full standalone run command will include `-cp .` as in the main example.

Some common points of confusion:

- `System.getProperty("mode")` does not automatically read `mode=trace` from `agentArgs`. Only when `-Dmode=trace` is passed separately will there be a corresponding JVM system property.
- Environment variables and application arguments do not automatically become `agentArgs`.
- If running multiple startup agents, each `-javaagent` occurrence has its **own** options string sent to that agent's `premain`.
- Characters like `,`, `;`, `:`, and `=` inside options do not share the same meaning across all agents. A grammar exists only when the agent author explicitly defines it.

## 4. Runnable Example with Java 17+: Agent Receiving and Parsing `agentArgs`

We create three files placed in **the same directory**. The agent class prints the raw string received, then parses a simple convention `mode=<off|trace>,sample=<0..100>`. The application class only prints the `main` arguments to prove the two passing paths are separate.

### 4.1. File `StartupAgent.java`

~~~java
import java.lang.instrument.Instrumentation;
import java.util.LinkedHashMap;
import java.util.Map;

public final class StartupAgent {
    public static void premain(String agentArgs, Instrumentation instrumentation) {
        System.out.println("[agent] raw=" + agentArgs);

        Map<String, String> options = parse(agentArgs);
        String mode = options.getOrDefault("mode", "off");
        int sample = Integer.parseInt(options.getOrDefault("sample", "10"));

        if (!mode.equals("off") && !mode.equals("trace")) {
            throw new IllegalArgumentException("mode must be off or trace");
        }
        if (sample < 0 || sample > 100) {
            throw new IllegalArgumentException("sample must be 0..100");
        }

        System.out.println("[agent] mode=" + mode + ", sample=" + sample
                + ", instrumentation=" + (instrumentation != null));
    }

    private static Map<String, String> parse(String raw) {
        Map<String, String> parsed = new LinkedHashMap<>();
        if (raw == null || raw.isEmpty()) {
            return parsed;
        }

        for (String item : raw.split(",", -1)) {
            int equalsAt = item.indexOf('=');
            if (equalsAt < 1 || equalsAt == item.length() - 1) {
                throw new IllegalArgumentException("expected key=value: " + item);
            }

            String key = item.substring(0, equalsAt);
            String value = item.substring(equalsAt + 1);

            if (!key.equals("mode") && !key.equals("sample")) {
                throw new IllegalArgumentException("unknown option: " + key);
            }
            if (parsed.putIfAbsent(key, value) != null) {
                throw new IllegalArgumentException("duplicate option: " + key);
            }
        }
        return parsed;
    }
}
~~~

Points to read carefully:

1. The JVM passes `agentArgs` verbatim into `premain`; printing `[agent] raw=...` happens **before any manual string splitting**.
2. `parse` is logic **chosen by the example itself**: splitting on commas, then on the **first `=` sign** of each item. It is not a mandatory Java agent rule.
3. When `agentArgs` is `null` or an empty string, `parse` returns an empty map; `mode=off` and `sample=10` are defaults **set by the example**, not JVM defaults.
4. `Integer.parseInt` only accepts valid integer strings; invalid values will cause an error in `premain`. The `mode` setting is restricted to `off` or `trace`; `sample` is in the range 0 to 100.
5. The example intentionally rejects unknown keys, items missing `=`, empty values, and duplicate keys. It does **not** support commas in values, escaping, internal quoting, key names with spaces, or complex syntax. If those capabilities are required, a different parser and options specification are needed.
6. The `instrumentation` object is provided by the JVM and checked for presence. The example has **not** registered a transformer yet, so printing the configuration does not prove any class has been transformed.

### 4.2. File `Application.java`

~~~java
import java.util.Arrays;

public final class Application {
    public static void main(String[] args) {
        System.out.println("[app] main args=" + Arrays.toString(args));
    }
}
~~~

### 4.3. File `MANIFEST.MF`

~~~text
Manifest-Version: 1.0
Premain-Class: StartupAgent

~~~

`Premain-Class` must point to the exact **binary name** of the class containing `premain`. Because the example places the class in the default package, the name is `StartupAgent`. If `package com.example.agent;` is declared, the manifest value must be `com.example.agent.StartupAgent` and the JAR must contain the corresponding class path.

When creating a manifest manually, you need a trailing newline on each line and must end the main manifest section properly (usually leaving **one blank line** at the end as in the block above). Using `jar --manifest` packages the manifest contents into `META-INF/MANIFEST.MF` of the JAR.

`Main-Class` is not needed in the agent JAR when starting up this way; `Premain-Class` is the required key. `Agent-Class` serves the mechanism for loading an agent into a running JVM and does not replace `Premain-Class` for `-javaagent`.

### 4.4. Compile, Package, Run

Run the following commands in the directory containing those exact three files with **JDK 17 or later**:

~~~bash
javac StartupAgent.java Application.java
jar --create --file agent-demo.jar --manifest MANIFEST.MF StartupAgent.class
java -javaagent:agent-demo.jar=mode=trace,sample=25 -cp . Application red blue
~~~

The first two commands produce `StartupAgent.class`, `Application.class`, and `agent-demo.jar`. The `jar` command here only packages the agent class, while `Application.class` is found on `-cp .`. The `.` refers to the current directory. With PowerShell on Windows, `.` in the classpath is also valid; this example does not depend on directory-creation syntax of a specific shell.

**Exact standard output** of the final `java` command:

~~~text
[agent] raw=mode=trace,sample=25
[agent] mode=trace, sample=25, instrumentation=true
[app] main args=[red, blue]
~~~

You can see `[agent]` appears before `[app]`; the string `mode=trace,sample=25` goes into `premain`, while `red` and `blue` go into `main`. The example was run and verified on OpenJDK 21; the code and tools use APIs available since Java 17.

## 5. Variants You Should Run Yourself to Understand `agentArgs`

### 5.1. Passing No Options

~~~bash
java -javaagent:agent-demo.jar -cp . Application
~~~

When run with OpenJDK 21, `raw=null` and the parser uses the defaults `mode=off, sample=10`. `main` still runs with an empty argument array. The key takeaway is to handle `null` before calling `split` or other `String` methods.

### 5.2. Passing an Empty Options String

~~~bash
java -javaagent:agent-demo.jar= -cp . Application
~~~

On OpenJDK 21, the raw string in this situation is `""`: the command prints `[agent] raw=` with no characters after `=`. The parser still uses the same defaults. This differs in the raw value compared to Example 5.1, but does not differ in the effective configuration of the demo.

### 5.3. Passing Only One Key

~~~bash
java -javaagent:agent-demo.jar=mode=trace -cp . Application
~~~

The parser sets `mode=trace` and keeps `sample=10`. This behavior comes from `getOrDefault` in the agent, not from how the JVM infers missing configuration.

### 5.4. Invalid Values or Duplicate Keys

~~~bash
java -javaagent:agent-demo.jar=sample=abc -cp . Application
java -javaagent:agent-demo.jar=mode=trace,mode=off -cp . Application
java -javaagent:agent-demo.jar=unknown=1 -cp . Application
~~~

In the example, these trigger a number-parsing error, a duplicate-key error, and an unsupported-key error respectively when `premain` runs. These commands are for **testing error paths**, not successful runs. The JVM may print different stack traces and internal messages depending on the JDK; the point to verify is that the application does not start through `main` after an unhandled startup agent error.

When building a production agent, you must explicitly decide between **fail fast** and **degrade safely**: severely conflicting configuration may need to block startup, whereas an observability exporter failure should sometimes allow the application to continue depending on the system contract. This decision belongs to agent design and operational requirements, and cannot be inferred from `-javaagent` syntax alone.

### 5.5. Multiple Startup Agents

A JVM supporting the `-javaagent` option can accept multiple declarations:

~~~bash
java -javaagent:first-agent.jar=level=basic -javaagent:second-agent.jar=enabled=true -cp . Application
~~~

This is a syntax illustration; both JAR files must actually exist and be valid. The JVM invokes the `premain` methods in **declaration order** before calling `Application.main`. Each agent receives **the options portion accompanying its own JAR**. The same agent JAR path can also be used multiple times, but you must consider side effects if initialization is not idempotent.

## 6. Quoting, Whitespace, and Configuration with Special Characters

There are two distinct levels of processing:

1. **The shell/terminal** splits the command into arguments for `java` and handles quotes, environment variables, and control characters.
2. **The Java launcher** receives a single `-javaagent:...` argument, locates the agent JAR, and extracts the options to pass to `premain`.

If the JAR path contains spaces, enclose **the entire JVM argument** in quotes according to the rules of the shell in use. Illustrative example with a file actually located in the `my agents` directory:

~~~bash
java "-javaagent:my agents/agent-demo.jar=mode=trace,sample=25" -cp . Application
~~~

The quotes here make the shell pass a single argument to `java`; the quotes do not become part of `agentArgs`. How characters such as `&`, `;`, `|`, nested quotes, and environment variable symbols are handled depends on the shell (bash, PowerShell, cmd.exe). Do not write configuration instructions by arbitrarily copying one shell's escaping syntax to another shell.

Similarly, suppose options have a long value:

~~~text
mode=trace,endpoint=https://collector.example.test/v1/trace
~~~

The JVM only passes **that entire string**; the agent parser itself must know what `endpoint` is. The demo parser in Section 4 **intentionally does not support** `endpoint` and will therefore reject this example. When options contain commas inside values, you cannot use a simple `split(",")` and still preserve the data. You need to design a clear escaping/encoding mechanism (or pass the path to a separate configuration file), and then test values containing special characters.

A practical rule: **do not put secrets/tokens into options if avoidable**, because launch commands and process arguments can be recorded in scripts, deployment systems, monitoring tools, or operational logs. Prefer secure configuration appropriate for the environment, and avoid accidentally printing the entire `agentArgs` containing secrets. The demo intentionally prints raw for learning purposes; that logging approach should not be used as-is in production.

## 7. From `agentArgs` to Real-World Agent Configuration

An agent can use `agentArgs` to decide:

- **Enabling/disabling features:** `mode=off`, `mode=trace`, logging level, or the set of classes to instrument.
- **Collection level:** sampling rate, event count limit, buffer size.
- **Export destination:** endpoint name, service name, timeout, batch settings.
- **Application conditions:** package prefixes, class names, include/exclude rules, configuration version.

These keys are only **examples of choices made by an agent author**. Java does not standardize `mode`, `sample`, `endpoint`, or the `,` delimiter format. When using a third-party agent, you must read that specific agent's documentation; the valid options of one agent can be completely different from another's.

A good initialization flow typically follows this order:

1. Receive `agentArgs` verbatim, check for null/empty, and select documented defaults.
2. Parse according to **the agent's grammar** and report clear errors for invalid keys, types, or values.
3. Validate that the configuration is consistent, without including sensitive data in logs.
4. Initialize bounded resources, and register hooks/transformers only after the configuration is valid.
5. Return from `premain` so the application proceeds into `main`; if an unrecoverable error occurs, provide a helpful startup message.

Do not start a network exporter or begin a long-running task and wait indefinitely inside `premain`. Because the application waits for the agent to finish initializing, blocking there can prevent the service from ever reaching a ready state.

## 8. Common Errors and How to Verify

| Symptom | Cause to check | How to verify |
| --- | --- | --- |
| JVM reports it cannot open the agent JAR | Wrong `jarpath`, file not created yet, missing read permissions | Check the path relative to the current working directory, filename, and access permissions |
| `Premain-Class` not found | Missing manifest or improper packaging | Inspect `META-INF/MANIFEST.MF` inside the agent JAR and the class name value |
| Agent class cannot be loaded | Wrong binary name, class path, or missing dependencies | Inspect the JAR entries and the agent's classpath/dependencies |
| `premain` is not invoked | Wrong `public static void` signature, missing manifest, or `-javaagent` placed in the wrong position | Check startup errors and try a minimal demo first |
| `agentArgs` unexpectedly empty/null | Missing `=options` or accidentally passing only `=` | Print raw in a controlled test environment, inspect the CLI |
| `agentArgs` differs from intent | Shell splits on whitespace or processes special characters | Quote the entire argument properly and inspect the command the process actually receives |
| Parser fails on commas or `=` | Hand-written parser grammar is too simplistic | Add tests for escaping, delimiter characters, and empty values |
| `main(args)` receives `-javaagent` as text | Option was placed after the main class name or after `-jar app.jar` | Move `-javaagent` before the application class/JAR selection |
| App fails to start when options are invalid | `premain` throws an unhandled exception | Fix the configuration or the agent's startup error policy |
| Agent runs but telemetry/data is missing | Transformer not registered, class already loaded, or insufficient coverage | Check actual hooks, class loading, and instrumentation API usage |

Inspect packaging with the JDK tool:

~~~bash
jar --list --file agent-demo.jar
~~~

The listing must include `META-INF/MANIFEST.MF` and `StartupAgent.class`. To read the manifest contents, use your environment's JAR/ZIP viewer or extract into a **separate test directory**, then verify `Premain-Class` accurately. `Main-Class` is not needed in the example's agent JAR.

**Checklist before using in a real system:**

- `-javaagent` appears in the right position in the launch command of the **process to be instrumented**, not only in the build command.
- The agent JAR has a valid `Premain-Class` and all dependencies the agent needs.
- Configuration is parsed and validated; there is a clear policy for omitted options, empty strings, and configuration errors.
- Configuration logs avoid secrets, and do not hang the app or mask business errors.
- If multiple agents are present, verify execution order, hook conflicts, and initialization behavior.
- Tested with the actual JDK, shell, and packaging method; aware of class loading and coverage limitations.

## 9. Self-Check Questions

1. Given `java -javaagent:agent-demo.jar=mode=trace,sample=25 -cp . Application red blue`, what string goes into `premain`? What array goes into `main`?
2. Who decides the meaning of the comma and the two keys `mode` and `sample`: the JVM or the agent?
3. Why is `Premain-Class` different from `Main-Class`? When is `Agent-Class` needed?
4. Why must you handle both `null` and `""` before calling `split`?
5. If an agent declares both `premain` variants, which variant does the JVM prefer?
6. When a startup agent throws an exception in `premain`, has the application reached `main` yet?
7. Why does placing `-javaagent` after `Application` change its meaning?
8. How would you design a parser if values contain commas, spaces, or characters that need escaping?

## 10. Summary for Practical Application

`-javaagent:jarpath[=options]` is **the JVM launcher input for activating a startup agent**. The `Premain-Class` manifest attribute identifies the startup class; the JVM invokes `premain` before `main`; `options` arrives verbatim in a single `String agentArgs` parameter. Java does **not** parse custom key/value pairs on the agent's behalf. Therefore, proper usage consists of three things: placing the launch option in the right position, packaging the manifest correctly, and building sufficiently clear parsing/validation for the `agentArgs` string.

### Official References

- [Oracle Java 17 — Package java.lang.instrument](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): startup agents, `-javaagent` syntax, `premain` signatures, manifest, agent options, and multiple-agent ordering.
- [Oracle Java 21 — Package java.lang.instrument](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): corresponding specification on JDK 21, agent capabilities and limitations.
- [Oracle Java 17 — Class Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): role of the `Instrumentation` object passed by the JVM into `premain`.
