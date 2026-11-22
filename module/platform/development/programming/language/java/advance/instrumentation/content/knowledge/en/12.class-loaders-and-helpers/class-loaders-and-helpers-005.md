# appendToSystemClassLoaderSearch and Requirements for a Custom System Class Loader

A Java instrumentation agent may need to invoke a helper class from bytecode that it injects into an application. If the JVM cannot find the helper through the **defining class loader of the class containing the call**, you may encounter a `NoClassDefFoundError` even though the agent JAR starts up normally. A key tool for placing helpers is `Instrumentation.appendToSystemClassLoaderSearch(JarFile)`: it adds **a JAR to the search path of the system class loader**, but it does not automatically make every class loader in the JVM see that JAR.

This article explains the exact contract of the API, how it works with the default system loader, and the requirements for a **custom system class loader** specified via `-Djava.system.class.loader=...`. An often-overlooked point is that the custom loader must support a method with a **special name and signature**: `appendToClassPathForInstrumentation(String)`. We will run the same agent under two class loader configurations, confirm that the helper is loaded from a JAR not on `-cp`, and then analyze failure cases and limitations regarding delegation, modules, and class resolution.

**Lab prerequisites:** examples use Java 17 APIs and the `javac`/`jar` tools from JDK 17 or later. The code was compiled with `javac --release 17` and run on OpenJDK Zulu 24.0.2, with both the default loader and a custom loader; some JVM messages on stderr may vary by vendor/version.

## 1. The Practical Problem: Which Class Loader Loads the Helper?

Suppose a transformer adds an instruction equivalent to the following into a business class:

~~~java
// Describes the meaning of the instrumented bytecode; not a standalone file.
demo.helper.Greeting.message();
~~~

The JVM must resolve the symbolic reference `demo/helper/Greeting` when executing the code containing the call. Resolution depends on the **defining class loader of the class containing the instruction**, delegation rules, and module/access rules. "The agent sees Greeting" **does not mean** "every class in the application sees Greeting".

Example loader hierarchy:

~~~text
                      Bootstrap loader
                            |
                      Platform loader
                            |
                      System/App loader  <--- helper.jar is appended here
                            |
                    Child / plugin loader
                            |
                  Some application classes
~~~

In this diagram, a child loader **can** find the helper through its parent if it performs proper delegation and there are no isolation/child-first rules blocking it. However, a class defined by a loader **higher up** cannot by default see classes that exist only in a **child** loader. If a plugin loader uses its own strategy, it is also not required to delegate as shown in the diagram.

Therefore, **two separate questions** must be answered:

1. Did `appendToSystemClassLoaderSearch` successfully add the JAR to the **system loader**?
2. Can **the class with instrumented bytecode** properly resolve the helper through its own loader/module?

The lab below intentionally uses `Class.forName(name, true, ClassLoader.getSystemClassLoader())` to prove the first question. It **does not infer** from this that a helper call in any webapp/bootstrap/custom loader will always work.

## 2. The Contract of `Instrumentation.appendToSystemClassLoaderSearch`

JDK 17 signature:

~~~java
void appendToSystemClassLoaderSearch(java.util.jar.JarFile jarfile);
~~~

`Instrumentation` is an object provided by the JVM to `premain(String, Instrumentation)` or `agentmain(String, Instrumentation)`; it is not created with `new Instrumentation()`. When an agent calls the API above, a JAR is added to the list where the **system class loader** searches for classes and resources if prior search attempts fail.

Key characteristics from the Javadoc:

- The method accepts a **`JarFile`**, not a directory, `URL`, `Path`, or `ClassLoader`.
- When the system loader cannot find a class via delegation/its existing search path, it can search additional entries in the appended JAR.
- It can be called multiple times to add multiple JARs; added JARs are searched in **the order they were appended**.
- The JAR should contain only the instrumentation classes/resources that need to be defined via the system loader. Adding a huge JAR with classes matching application library names can cause hard-to-diagnose conflicts.
- The **`java.class.path` property value does not change** as a result of this call. Reading `System.getProperty("java.class.path")` cannot substitute for checking the actual class loader.
- If the system loader **does not support appending**, the API may throw `UnsupportedOperationException`.
- Passing `null` instead of a `JarFile` causes a `NullPointerException`.
- The method does not reload **already-defined** classes, does not automatically redefine/retransform classes, and does not grant any module access permissions.

The last point is easy to confuse: **"append to search path" is not "hot swap"**. If the JVM has already defined `demo.helper.Greeting` from another JAR, adding a new JAR with the same class name does not replace the existing `Class<?>`. And if the JVM has already failed to resolve a symbolic reference, there is an additional restriction regarding **remembered resolution failure** (Section 7).

### 2.1. Differences from `-cp` and the Agent JAR

Comparison:

| Mechanism | Trigger | Primary Effect |
| --- | --- | --- |
| `-cp app-out` | JVM launcher | Sets the initial application class path |
| `-javaagent:agent.jar` | JVM launcher | Loads the agent class via manifest `Premain-Class` before `main` |
| `inst.appendToSystemClassLoaderSearch(helperJar)` | Agent code | Adds the helper JAR to the system loader's search path in the running JVM |
| `inst.appendToBootstrapClassLoaderSearch(helperJar)` | Agent code | Adds a JAR to the **bootstrap loader**'s search path, which is a different mechanism |
| `ClassLoader.getSystemClassLoader().loadClass(...)` | Runtime code | Requests the system loader to load a class according to its own rules |

`appendToSystemClassLoaderSearch` **is not equivalent** to opening a new class loader with `new URLClassLoader(...)`. It acts on the search path **of the existing system loader**, even when the system loader is a compatible custom implementation.

In the example below, `agent.jar` and `helper.jar` are **two separate artifacts**: the agent provides `premain`; `helper.jar` contains `demo.helper.Greeting`, which the system loader will find after appending.

## 3. Special Requirements for a Custom System Class Loader

Java allows replacing the default system class loader with a startup property:

~~~bash
java "-Djava.system.class.loader=CustomSystemLoader" -cp app-out Main
~~~

When `ClassLoader.getSystemClassLoader()` is initialized for the first time, the JVM uses the default system loader to load the `CustomSystemLoader` class. This class **must have a public constructor** accepting a single `ClassLoader` as its parent:

~~~java
public CustomSystemLoader(ClassLoader parent) {
    super(..., parent);
}
~~~

This is a constructor template, not standalone source code. The parent provided by the JVM is the **default system class loader**, which should not be obtained by calling `ClassLoader.getSystemClassLoader()` recursively from the constructor. The Javadoc warns that causing recursive system loader initialization can throw `IllegalStateException`. Ensure the class loader implementation can be found by the default system loader at startup, typically by placing `CustomSystemLoader.class` on the initial classpath.

**An additional contract specifically for instrumentation:** the custom system loader must define a method named:

~~~java
void appendToClassPathForInstrumentation(String jarPath);
~~~

- The name **must be exact**: `appendToClassPathForInstrumentation`.
- The single parameter is `java.lang.String`. In common JVM implementations, the method returns `void`, as in the example.
- **The method is not required to have the `public` modifier** according to the `Instrumentation` Javadoc; the example chooses `public` for visibility and ease of testing.
- The JVM invokes this method and passes **the value of `jarfile.getName()`** of the `JarFile` passed to `appendToSystemClassLoaderSearch`; **you must not assume it is always an absolute path**. The custom method should normalize the path according to the environment if needed.
- The custom method must actually **add the JAR to the search path that the loader itself uses** when looking up classes. Merely storing the string in a list that `findClass` never reads does not fulfill the goal.
- This method should not throw exceptions; it should handle paths/URLs and invalid cases according to a tested policy. If unsupported or implemented incorrectly, agent startup/loading or the append call may fail.

A custom loader is part of the **runtime infrastructure**, not just a decorative helper class. If `java.system.class.loader` is configured but lacks the instrumentation support method, **loading the agent at startup itself** may fail before the agent's `premain` even runs. The reason is that the agent loading mechanism must interact with the system-loader search path, not just with helper JARs appended later.

### 3.1. What Can Be Done Inside the Custom Method?

A simple approach is to build the custom loader on top of `URLClassLoader`, using the `protected` inherited `addURL(...)` method to add the JAR's URL. However, note:

- The default `ClassLoader.getSystemClassLoader()` on modern JDKs **is not necessarily a `URLClassLoader`**. Do not cast the default loader to `URLClassLoader` to call `addURL`.
- Simply **extending** `URLClassLoader` does not automatically create the special instrumentation method; you must **define** `appendToClassPathForInstrumentation(String)`.
- Once a JAR is appended, the system loader may still **delegate to its parent first**. If the parent already has a class with the same name, the result may be the parent's class; the new JAR cannot override a class already loaded by the parent.
- If the loader holds state requiring synchronization/locking, thread safety must be considered; class loading and appending can happen concurrently while the system is running.

In Section 5, we write a minimal loader with the exact constructor and special method; the helper class is loaded by **the new system loader itself** to verify the append.

## 4. Flow from Agent to Custom Loader

~~~text
java "-Djava.system.class.loader=CustomSystemLoader"
     -javaagent:agent.jar=helper.jar
     -cp app-out Main
          |
          v
JVM creates CustomSystemLoader(parent = default system loader)
          |
          v
JVM prepares to load agent (custom loader must support adding JAR)
          |
          v
Agent.premain("helper.jar", instrumentation)
          |
          v
new JarFile("helper.jar")
          |
          v
inst.appendToSystemClassLoaderSearch(jar)
          |
          v
JVM calls customLoader.appendToClassPathForInstrumentation(
                    jar.getName())
          |
          v
customLoader adds URL pointing to helper.jar
          |
          v
Main calls Class.forName("demo.helper.Greeting", true, system)
          |
          v
customLoader finds class from helper.jar; defines class
          |
          v
Greeting.message() -> "hello"
~~~

This model illustrates the path **in the demo**. The JVM may use different internal details depending on the implementation; the interface published by the Javadoc is the combination of `Instrumentation.appendToSystemClassLoaderSearch` and the system loader's support method.

It is also important to distinguish **the class loader of `Main`** from **the system loader**: with a custom system loader using parent-first delegation, the `Main` class may already be found by the parent from `-cp app-out`. Therefore, the demo **intentionally does not place a static symbolic reference to the helper in `Main`**. Instead, it calls `Class.forName(..., systemLoader)` and checks `helper.getClassLoader() == systemLoader`. If a class actually defined by the parent contains bytecode calling a helper that exists only in the child system loader, that static call **is not automatically rescued** by the helper appearing in the child. This is a particularly important visibility boundary when designing instrumentation.

## 5. Full Java 17+ Demo: Helper JAR and Two System Loaders

Create a `demo/` directory for the lab, with **five input files**:

~~~text
demo/
  Greeting.java
  Agent.java
  CustomSystemLoader.java
  Main.java
  MANIFEST.MF
~~~

After building, we will have three output directories `helper-out/`, `agent-out/`, `app-out/` along with two JARs `helper.jar`, `agent.jar`. Everything is strictly for the demo; do not modify the machine's system classpath/environment.

### 5.1. `Greeting.java` — Helper Residing Only in `helper.jar`

~~~java
package demo.helper;

public final class Greeting {
    public static String message() { return "hello"; }
}
~~~

The binary class name is `demo.helper.Greeting`, corresponding to the entry `demo/helper/Greeting.class` in the helper JAR. This file is **not** placed in the `app-out` directory and does **not** appear in `-cp app-out` at runtime. This is essential to prove the append works.

### 5.2. `Agent.java` — Adding the JAR to System-Loader Search

~~~java
import java.lang.instrument.Instrumentation;
import java.io.IOException;
import java.nio.file.Path;
import java.util.jar.JarFile;

public final class Agent {
    public static void premain(String options, Instrumentation inst) {
        try (JarFile helper = new JarFile(Path.of(options).toFile())) {
            inst.appendToSystemClassLoaderSearch(helper);
            System.out.println("APPENDED=true");
        } catch (IOException e) {
            throw new IllegalStateException(e);
        }
    }
}
~~~

The agent receives the `options` string from `-javaagent:agent.jar=helper.jar`. It opens a `JarFile` and calls `appendToSystemClassLoaderSearch` **exactly once**. After the call succeeds, it prints `APPENDED=true`. This is an operation to add a search entry, **not** directly calling `Class.forName("demo.helper.Greeting")` inside `premain`.

Notes:

- `options` in the demo must be a non-empty path to an existing JAR; missing the option can cause `Path.of(options)` to throw an exception. A production version needs to validate null/blank/path first.
- `IOException` is caught when opening/closing the JAR; `UnsupportedOperationException` if the system loader does not support appending is a different error and should not be coerced into "file not found".
- `JarFile.getName()` provides the path that the JVM passes to the custom loader. The demo uses the relative name `helper.jar` from the working directory, so the custom method converts it to an absolute URL.
- `try-with-resources` closes the `JarFile` handle on the agent side when done; on the tested OpenJDK, the JVM can still locate the helper class afterward. You should not hold file handles indefinitely or delete the JAR while the runtime still needs to look up entries from it.
- Console printing is for learning only; a real agent should avoid depending on heavy logging frameworks during the initialization phase.

### 5.3. `CustomSystemLoader.java` — The Required Method

~~~java
import java.net.MalformedURLException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class CustomSystemLoader extends URLClassLoader {
    public CustomSystemLoader(ClassLoader parent) {
        super(new URL[0], parent);
    }

    public void appendToClassPathForInstrumentation(String jarPath) {
        try {
            addURL(Path.of(jarPath).toAbsolutePath().toUri().toURL());
        } catch (MalformedURLException e) {
            throw new IllegalArgumentException(e);
        }
    }
}
~~~

Analysis:

1. The class has a **public constructor(ClassLoader)**; the JVM can instantiate it when reading `java.system.class.loader`.
2. `super(new URL[0], parent)` creates a `URLClassLoader` **with no URLs of its own yet**, but with a parent as the delegation source.
3. `appendToClassPathForInstrumentation(String)` has the exact name specified by the Javadoc. `Instrumentation.appendToSystemClassLoaderSearch` requires the loader to support this method.
4. `Path.of(jarPath).toAbsolutePath().toUri().toURL()` converts the received path into a valid JAR URL under the test conditions.
5. `addURL(...)` adds the JAR to the list searched by **this URLClassLoader itself**. It does not update the `java.class.path` property.
6. The example uses a `public` method even though the Javadoc does not require `public`. In other implementations, pay attention to appropriate return type/exceptions/thread-safety and avoid turning the method into a business API.
7. The class loader does not call `ClassLoader.getSystemClassLoader()` in its constructor, so it does not create a system initialization cycle.

The `addURL` method here is a **protected** method of `URLClassLoader`, callable from a subclass. Do not copy patterns like `((URLClassLoader)ClassLoader.getSystemClassLoader()).addURL(...)` into normal code: the default loader may not be a `URLClassLoader`, and `addURL` is not public.

In a real environment, the method should reject invalid paths per a clear policy, ensure the JAR has a trusted signature/source, and include concurrency checks. The demo only illustrates the minimal contract; it contains no artifact management, rollback, or protection against JARs with duplicate class names.

### 5.4. `Main.java` — Verifying the Class Is Actually Loaded by the System Loader

~~~java
public final class Main {
    public static void main(String[] args) throws Exception {
        ClassLoader system = ClassLoader.getSystemClassLoader();

        System.out.println("CUSTOM_LOADER="
                + system.getClass().getSimpleName().equals("CustomSystemLoader"));

        Class<?> helper =
                Class.forName("demo.helper.Greeting", true, system);

        System.out.println("CLASS_LOADER_IS_SYSTEM="
                + (helper.getClassLoader() == system));

        System.out.println("HELPER_MESSAGE="
                + helper.getMethod("message").invoke(null));

        System.out.println("CLASS_PATH_HAS_HELPER="
                + System.getProperty("java.class.path").contains("helper.jar"));
    }
}
~~~

`Main` **does not** import `demo.helper.Greeting` to avoid making the experiment depend on how the parent loader defines `Main`. Instead, `Class.forName(name, true, system)` actively queries the **active system loader**. Then:

- `CUSTOM_LOADER` distinguishes the loader type across the two runs.
- `CLASS_LOADER_IS_SYSTEM` checks whether the helper was **defined by the exact system loader object**, not merely "found somewhere".
- `HELPER_MESSAGE` is an actual invocation of the loaded class's method.
- `CLASS_PATH_HAS_HELPER` proves `java.class.path` does not automatically list the appended JAR, matching the Javadoc.

In a large program, comparing class loader names simply with `getSimpleName` is for demo purposes only; check loader/parent/module identity in a controlled way. There can be class loaders with the same name in different modules.

### 5.5. `MANIFEST.MF` — Specifying the Agent Startup Class

~~~text
Manifest-Version: 1.0
Premain-Class: Agent

~~~

Keep the newline and a trailing blank line at the end of the manifest's main section. `Premain-Class` is for `-javaagent` at JVM startup; the demo does not use `Agent-Class`/`agentmain` because it does not dynamically attach to an already-running JVM.

### 5.6. Compiling and Packaging

From the `demo/` directory containing the five files:

~~~bash
javac --release 17 -d helper-out Greeting.java
javac --release 17 -d agent-out Agent.java
javac --release 17 -d app-out Main.java CustomSystemLoader.java

jar --create --file helper.jar -C helper-out .
jar --create --file agent.jar --manifest MANIFEST.MF -C agent-out .
~~~

Key build points:

- `helper-out` contains `demo/helper/Greeting.class`; only `helper.jar` contains it at runtime.
- `agent-out` contains `Agent.class`; `agent.jar` must contain `META-INF/MANIFEST.MF` and `Premain-Class: Agent`.
- `app-out` contains `Main.class` and `CustomSystemLoader.class`; it does **not** contain `demo/helper/Greeting.class`.
- The helper JAR **must not be placed on `-cp`** in the two run commands below, so that appending is the sole source for the system loader to find it.

You can inspect them:

~~~bash
jar --list --file helper.jar
jar --list --file agent.jar
~~~

`helper.jar` must contain `demo/helper/Greeting.class`. `agent.jar` must contain `Agent.class` and `META-INF/MANIFEST.MF`. The JAR listing may also include auxiliary entries such as `META-INF/`; verbatim output of the list command is not required.

### 5.7. Running with the Default System Loader

~~~bash
java -javaagent:agent.jar=helper.jar -cp app-out Main
~~~

Exact standard output observed on OpenJDK Zulu 24:

~~~text
APPENDED=true
CUSTOM_LOADER=false
CLASS_LOADER_IS_SYSTEM=true
HELPER_MESSAGE=hello
CLASS_PATH_HAS_HELPER=false
~~~

Interpretation: the agent called append successfully, the default system loader loaded `Greeting` from `helper.jar`, and `java.class.path` still only reflects the launcher configuration `app-out` without `helper.jar`.

The specific system loader name/type may vary by JVM implementation. The code only compares `getSimpleName` against the string `CustomSystemLoader`, so on a typical default configuration the line is `CUSTOM_LOADER=false` as above.

### 5.8. Running with the Custom System Loader

~~~bash
java "-Djava.system.class.loader=CustomSystemLoader" -javaagent:agent.jar=helper.jar -cp app-out Main
~~~

Standard output **of the program** observed on OpenJDK Zulu 24:

~~~text
APPENDED=true
CUSTOM_LOADER=true
CLASS_LOADER_IS_SYSTEM=true
HELPER_MESSAGE=hello
CLASS_PATH_HAS_HELPER=false
~~~

**Shell note:** the argument `-Djava.system.class.loader=CustomSystemLoader` is **quoted as a whole** in the command above. Quoting it this way works across common shells while avoiding some differing argument-parsing behaviors in Windows PowerShell. Do not place the property after the `Main` class name: it would then be treated as an application argument instead of a JVM option.

On the tested HotSpot version, a CDS warning line may appear **on stderr** when `java.system.class.loader` is enabled, for example regarding not using certain archived non-system classes. This warning is not an output line printed by the demo code and does not mean `append` failed. Separate the demo's stdout from diagnostics printed by the JVM/vendor itself.

The results prove:

1. The custom loader was selected as the system loader.
2. The JVM invoked the append support path and the helper was defined by the custom loader.
3. The app obtained the `Greeting.message()` method from the helper JAR that was not on the launcher classpath.
4. `java.class.path` did not have `helper.jar` added to it.

**Proof limitation:** `Main` uses reflection via the system loader. Do not infer from this experiment that classes defined by the **default parent loader** or isolated plugin loaders can also link directly to `Greeting` after appending.

## 6. Why Is Missing `appendToClassPathForInstrumentation` a Critical Error?

Imagine a custom loader:

~~~java
// Design example INSUFFICIENT for a Java agent, not a standalone program.
public final class BrokenLoader extends ClassLoader {
    public BrokenLoader(ClassLoader parent) {
        super(parent);
    }
    // Missing appendToClassPathForInstrumentation(String)!
}
~~~

It may satisfy the constructor requirement of `java.system.class.loader`, but it **fails the instrumentation contract**. When the JVM/agent needs to append a JAR to the system-loader search path, there is no suitable method to perform it. `Instrumentation.appendToSystemClassLoaderSearch` may throw `UnsupportedOperationException` when the system loader does not support it.

**Especially with `-javaagent`:** a custom loader missing the method can cause agent startup to fail from the outset, before `premain` even has a chance to call the API. Detailed messages and failure timing depend on the JVM/vendor. Do not try to "fix" it by rewriting `Premain-Class` if the manifest is already correct; check the custom loader contract.

Another broken implementation:

~~~java
// Semantically wrong: remembers path but does not make findClass see the new JAR.
public void appendToClassPathForInstrumentation(String jarPath) {
    knownPaths.add(jarPath);
}
~~~

If `findClass`/delegation logic does not use `knownPaths` to look up classes, it is **not an effective append**. The snippet only illustrates the design flaw (assuming a `knownPaths` variable exists); it is not standalone source code. What needs to be verified is not just that "the method exists" but that **new classes can actually be found after appending**.

### 6.1. Why Doesn't the Method Need to Be Public?

The `Instrumentation` Javadoc explicitly states that `appendToClassPathForInstrumentation(String)` **is not required to be public**. The JVM uses internal class loader support mechanisms to invoke it according to the contract. This does not mean an arbitrary external Java class can invoke a private/package-private method of the custom loader via a normal call. The example uses `public void` so learners can directly understand, inspect, and write unit tests for it.

Do not use reflection to secretly call internal methods of the default system loader. The supported way for a Java agent is **`Instrumentation.appendToSystemClassLoaderSearch(JarFile)`**, while a custom loader must provide the hook the JVM expects.

## 7. Do Not Try a Failing Resolution and Expect Append to Fix It

The Javadoc mentions a rule of **symbolic reference resolution** in the JVM: if the JVM has already attempted to resolve a symbolic reference and failed, a subsequent resolution attempt of **that same reference** still fails with the corresponding error, even if a new JAR is later added to the search path.

Example of a flawed design scenario:

~~~text
1. Class A is running bytecode referencing Helper.missing()
2. Symbolic reference resolution fails (linkage error)
3. Agent appends helper.jar containing the expected class/method
4. Class A retries the same symbolic reference
5. JVM may repeat the old resolution error per the JVM Specification
~~~

Therefore, **append as early as possible before the first use of the helper**. A diagnostic approach like "intentionally call the helper to see it fail, then append and call the exact same thing again" can be misleading and also leaves the error state difficult to reverse.

Distinguish between:

- **A new class/resource search** via the appropriate API can find the newly appended entry.
- **A symbolic reference whose resolution already failed** may be bound by the remembered-failure rule.
- **An already-defined class** is not replaced by a class of the same name merely because a new JAR was appended.

Hence, the demo only calls `Class.forName` **after** `premain` has appended. It does not attempt to trigger a resolution error before appending and then re-test on the same reference.

## 8. Parent Delegation: Why a Custom Loader Does Not Solve Every Visibility Issue

In the demo, `CustomSystemLoader` is a **URLClassLoader with a parent**. Default `URLClassLoader` uses parent-first delegation: when it needs to load a class, it tries its parent first, and only then searches its own URLs. This has two consequences:

1. **Duplicate class names:** if the parent already has `demo.helper.Greeting`, the custom loader may return the parent's class instead of the class in `helper.jar`. Appending a JAR cannot be used to arbitrarily override an already-available class.
2. **Classes defined by the parent:** if `Main` or a service class defined by the parent contains a symbolic reference to a helper **that exists only in the child custom loader**, the parent does not automatically search downward into the child to resolve that reference.

Diagram of the second scenario:

~~~text
Default system loader (parent)
   |-- defines Main / SomeService
   |      |
   |      +-- SomeService bytecode calls demo.helper.Greeting
   |             -> resolves via SomeService's defining loader
   |             -> parent does not look into child's own URLs
   |
   +-- CustomSystemLoader (new system loader)
           |
           +-- URL helper.jar (appended)
                  |
                  +-- contains demo.helper.Greeting
~~~

This is why `Class.forName(name, true, ClassLoader.getSystemClassLoader())` in the demo is an **intentional and scoped** test: it queries the child custom loader directly. A direct call inside a class already defined by the parent must be verified separately.

Similarly, applications with child-first/plugin loaders may have exclusion policies or non-default class visibility. Do not design an agent based on the assumption that "once a JAR is inserted into the system loader, all classes in the JVM can access it." You must test in **the exact defining loader** of the class being instrumented.

## 9. Does `appendToBootstrapClassLoaderSearch` Solve It?

Some agents need helpers for classes defined by the **bootstrap loader**, for example when instrumenting core library classes. In that case, `appendToSystemClassLoaderSearch` **is not enough** because the bootstrap loader does not delegate down to the system loader to find classes.

The alternative API is:

~~~java
void appendToBootstrapClassLoaderSearch(java.util.jar.JarFile jarfile);
~~~

However, you should not automatically replace every case with bootstrap append:

- A helper loaded by bootstrap must have dependencies that the bootstrap loader can actually see; a helper requiring application libraries on the system loader can hit linkage errors.
- The Javadoc warns that the appended JAR should contain only the necessary instrumentation classes/resources. Duplicate class names, especially package-private helpers, can cause `IllegalAccessError` due to differing loader identities.
- Bootstrap search and system search have different scopes; choosing the wrong one can **increase risk** rather than solving visibility.
- Named modules still have access rules; bootstrap append does not automatically open all modules/packages.
- If only a set of application classes truly defined by the system loader is involved, system append is usually more appropriate.

Choose where to place the helper by identifying **which class contains the injected invocation** and **that class's defining loader**, then checking module readability/exports when modules are used.

## 10. Distinguishing Module Path and Classpath

`appendToSystemClassLoaderSearch` does not mean:

- Creating a new named module or automatically resolving it into the boot layer.
- Modifying `--module-path`, `ModuleLayer`, or any module resolution state.
- Automatically adding `requires`/reads/exports/opens for existing named modules.
- Granting special privileges to helper code merely because it is in an instrumentation JAR.

A class defined from `helper.jar` via the system loader typically belongs to that loader's **unnamed module** if it is not loaded as a named module by another mechanism. When a class in a **named module** references the helper, appropriate readability and accessibility must be considered. For deep runtime module needs, `Instrumentation.redefineModule(...)` can adjust **API-permitted module relationships**, but that is a separate operation, not a default effect of appending.

For applications using JPMS, test class loading on the exact module/loader topology, rather than just running an application on a plain classpath and considering it sufficient.

## 11. Common Errors and Diagnostic Directions

| Symptom | Possible Cause | Verification Action |
| --- | --- | --- |
| `UnsupportedOperationException` at `appendToSystemClassLoaderSearch` | System loader does not support append/the corresponding hook | Check system loader type and special method |
| Startup fails with custom loader | Missing `(ClassLoader)` constructor, missing append method, or broken loader logic | Check `-Djava.system.class.loader`, classpath containing the loader, and JVM messages |
| `IOException` when creating `JarFile` | Wrong path, missing file, permissions/ZIP error | Verify path from working directory, actual file, permissions |
| `NullPointerException` when `jarfile` is null | Agent logic bug | Validate config/do not pass null |
| `ClassNotFoundException` after append | Class not in JAR/path or wrong loader chosen | Check JAR entries, defining loader, parent delegation |
| `NoClassDefFoundError` when injected method runs | Runtime cannot resolve helper or a dependency | Check loader of class containing the hook, dependencies, root cause error |
| `IllegalAccessError` or module error | Differing loader/package/module access | Check module rules, duplicate packages, package-private access |
| `NoSuchMethodError` | Helper class has wrong version or descriptor | Check method name, visibility, signature, and the class actually loaded |
| Append reports success but `java.class.path` does not change | **Expected contract** behavior | Verify by loading class/resource, do not measure via the property |
| Same error persists after append | Symbolic reference already failed resolution; or duplicate class already loaded | Trace the first phase, do not blindly retry the same reference |
| Class has the right name but wrong version | Parent-first delegation or JARs with duplicate classes | Check `Class.getClassLoader()`, `ProtectionDomain`/code source in a controlled way |
| JVM prints CDS warning with custom loader | Archived classes mode behaves differently | Separate JVM stderr from demo stdout |
| Custom loader cannot find agent class | Loader does not support adding agent JAR at startup | Check append hook and path before analyzing `premain` |

When debugging, record **which specific class needs the helper** along with `someClass.getClassLoader()`, `ClassLoader.getSystemClassLoader()`, the actual loaded class name, and which JARs were appended. There is no need to serialize the entire loader object or call `toString` during sensitive class loading moments.

### 11.1. Missing File vs. Missing Loader Hook

The two errors must be fixed in two different places:

- **Helper file does not exist:** `new JarFile(...)` fails before calling append. Fix the path, permissions, and packaging.
- **Custom loader missing support method:** the JAR may be completely valid, but the JVM cannot add it to the custom system loader's search path. Fix **the loader implementation** and re-test startup; do not endlessly repackage the helper if it is already correct.

A production agent should report errors by stage: `open JAR`, `append JAR`, `resolve helper`, `execute helper`. A generic "agent failed" message for every case obscures the error that needs fixing.

## 12. Safe Design for Production

### 12.1. Normalizing and Validating the JAR Path

The demo uses a relative `helper.jar`. For multi-environment deployments:

- Obtain an explicit path from agent configuration, avoiding reliance on an unstable working directory.
- Convert to an absolute/normalized path and open `JarFile` from that path.
- Verify the JAR exists, matches the expected version, passes checksum/signature policies, and contains only necessary classes/resources.
- Do not let untrusted input arbitrarily choose a JAR of code that can be loaded into the JVM.
- Avoid class-name collisions by using a dedicated package name for helpers, e.g., `com.example.observation.internal`.
- If the helper has already been loaded from another version, appending a new file does not perform hot replacement.
- Do not delete/rename the JAR path right after appending while the runtime may still need to read entries from it.

Conceptual snippet for production `premain`, **not standalone source code**:

~~~java
Path normalized = Path.of(options).toAbsolutePath().normalize();
if (!java.nio.file.Files.isRegularFile(normalized)) {
    throw new IllegalArgumentException("Helper JAR missing: " + normalized);
}
try (JarFile helper = new JarFile(normalized.toFile())) {
    inst.appendToSystemClassLoaderSearch(helper);
} catch (IOException ex) {
    throw new IllegalStateException("Cannot read helper JAR", ex);
}
~~~

`options` and `inst` must be present in the enclosing method of the snippet. You must validate `options != null` and non-blank **before** this block. The loader's `UnsupportedOperationException` is **not** an `IOException`; handle it at a layer that can accurately report the capability issue.

### 12.2. Timing of Append vs. Transformer Registration

In an agent with a real transformer, it is generally best to prepare the helper search path **before** the transformer starts producing class files containing helper calls:

~~~text
premain/agentmain:
    validate JAR
    append helper JAR
    initialize agent state
    register transformer
    optionally retransform selected already-loaded classes
~~~

If the transformer is registered first and business classes run and get instrumented immediately, the helper might not yet be available when the JVM resolves the invocation. In multithreaded systems, races between class load/resolve and append are even harder to reproduce. Also avoid calling `Class.forName` on the class **currently being defined** from inside `ClassFileTransformer.transform` just to test the loader: this can cause reentrancy or class circularity errors. Verify helper availability during setup or controlled tests.

### 12.3. Choosing an Appropriate Helper Contract

A helper might simply consist of:

~~~java
public final class Probe {
    public static void onEnter(String operation) {
        // Write event to a bounded buffer, avoiding synchronous network calls.
    }
}
~~~

This is an **API template**, not a standalone runnable class since it only has an illustrative body. When injected bytecode has `invokestatic Probe.onEnter(String)V`, the JVM must see a method with the exact descriptor. Do not let the helper throw telemetry errors that alter business results if the contract is best-effort observation; maintain drop/failure counters and process reporters outside the callback.

### 12.4. Avoiding Class Loader Leaks and Conflicts

If an agent holds references to `ClassLoader`, `Class<?>`, or `JarFile` in an unbounded cache, hot reload/plugin unload may keep object graphs alive unintentionally. Diagnostic data should use small IDs/metadata and bounded structures; manage resource lifecycles explicitly.

Do not use `appendToSystemClassLoaderSearch` as a way to arbitrarily load all application dependencies. This mechanism is for necessary **instrumentation classes**, not a replacement for project dependency management. If a JAR contains multiple versions of `commons-*` or logging frameworks with overlapping packages with the application, class loading outcomes can change unpredictably.

## 13. Structured Testing

| Case | Setup | Expected Outcome |
| --- | --- | --- |
| Default loader | Without `-Djava.system.class.loader` | `APPENDED=true`; helper loads via system loader |
| Supported custom loader | With `CustomSystemLoader` and hook method | `CUSTOM_LOADER=true`, helper defined by the custom loader itself |
| Without `-javaagent` | Only `-cp app-out` | `Main` cannot find helper because `helper.jar` is not on the classpath |
| Wrong helper JAR path | Provide a non-existent file | Agent reports a clear JAR read error |
| Loader missing hook | Create a custom loader without `appendToClassPathForInstrumentation` in test env | Startup/append may fail; do not confuse with helper error |
| Class already loaded by parent | Parent has a class with the same name | Parent-first may select the parent's version |
| Call from parent class | Class containing symbolic reference defined by parent | Do not assume parent automatically sees helper in child |
| Bootstrap class needs helper | Instrument a class defined by bootstrap | System append is insufficient; evaluate bootstrap search |
| Class in named module | Helper in loader's unnamed module | Check readability/exports/access |
| Symbolic resolution fails before append | Test in an isolated JVM test | Do not assume append fixes a remembered failure |
| Appending multiple JARs | Call append in a deterministic order | Append order is observed, no class conflicts |
| Realistic load | Helper called on hot path | Measure CPU, GC, p99 latency, telemetry drops |

To test the final behavior of an **instrumented method**, do not only test `Class.forName`: use a class defined by the target loader, inject the helper call, and run it. Check both normal and exception paths, business results, and module/loader variations of the real application.

## 14. Common Misconceptions

1. **"appendToSystemClassLoaderSearch adds to `java.class.path`."** No; the property does not change.
2. **"Every loader sees the helper after appending."** No; it depends on the defining loader and delegation/module rules.
3. **"A custom system loader only needs a constructor to run an agent."** No; it needs `appendToClassPathForInstrumentation(String)`.
4. **"The special method must be public."** The Javadoc does not require public, though public is convenient for testing.
5. **"The JVM passes an absolute path to the hook."** The contract passes `JarFile.getName()`; normalize the path if needed.
6. **"The default class loader is always a URLClassLoader."** Not true on modern JDKs.
7. **"You can cast the default loader and call addURL."** Do not do this; type and access are not guaranteed.
8. **"A JAR with a duplicate class name overrides an already-loaded class."** No; append only extends search for valid subsequent lookups.
9. **"Appending after a NoClassDefFoundError always fixes the error."** No; symbolic reference resolution failure may be remembered.
10. **"System append and bootstrap append are the same."** No; loader scope and dependencies differ.
11. **"A custom system loader definitely defined Main."** No; with parent-first, the parent may define `Main`.
12. **"If `Class.forName` via system succeeds, any bytecode in the parent can also call the helper."** You cannot infer that.
13. **"Having the loader method exist without changing findClass is enough."** No; the method must actually extend the search.
14. **"Append is a way to create a new named module."** No; module path and readability must be handled separately.
15. **"Any number of libraries in the JAR is safe."** False; duplicate classes, helper dependencies, and package boundaries must be controlled.

## 15. Self-Check Questions

1. Does `appendToSystemClassLoaderSearch` accept a `Path`, `URL`, or `JarFile`?
2. **Which loader's** search path is the JAR added to? Does it automatically change `java.class.path`?
3. Why does a custom system loader need both a public `(ClassLoader)` constructor and the `appendToClassPathForInstrumentation(String)` method?
4. What value from `JarFile` does the JVM pass to the custom loader's hook method?
5. Why does the demo use `Class.forName(..., ClassLoader.getSystemClassLoader())` instead of a direct reference in `Main`?
6. What happens if `Main` is defined by the parent loader while the helper exists only in the child system loader?
7. Why should you not call `ClassLoader.getSystemClassLoader()` inside a custom loader's constructor?
8. Where can `URLClassLoader.addURL` be called, and why can't you unconditionally cast the default loader?
9. If a helper class already failed resolution before appending, why might the old call continue to fail?
10. If you want to instrument a bootstrap class, is system append a sufficient solution in all cases?
11. How do you verify a JAR contains the exact `demo.helper.Greeting` class without confusing it with the agent JAR?
12. If the tool prints `APPENDED=true`, what has **not** yet been proven about named modules and child class loaders?
13. Name two scenarios that can cause `NoClassDefFoundError` even though the agent JAR started successfully.
14. Why is it necessary to check `CLASS_LOADER_IS_SYSTEM` in addition to just being able to call `Greeting.message()`?
15. What test would you design to prove the helper is loaded from the right package/loader in a real application?

## 16. Implementation Checklist

1. Identify which class will have the invocation injected and that class's defining loader/module.
2. Choose where to define the helper: system loader, bootstrap loader, or another truly suitable mechanism.
3. Place the helper in a lean JAR, dedicated package, without carrying dependencies that cause class collisions.
4. If `java.system.class.loader` is configured, ensure the custom loader has the proper constructor and a genuinely working `appendToClassPathForInstrumentation(String)` hook.
5. Validate the JAR path, open `JarFile` safely, and call `appendToSystemClassLoaderSearch` before the hook is used.
6. Distinguish `JarFile`/I/O errors from `UnsupportedOperationException` capability errors.
7. Avoid triggering symbolic resolution failures before appending.
8. Verify the helper class is defined by the right loader and has the descriptor/visibility the bytecode needs.
9. Check parent delegation, custom isolation, named module access, and bootstrap classes.
10. Test class loading, behavior, exceptions, and p95/p99 latency in an environment with the right topology.
11. Manage JAR/dependency/loader lifecycles; do not arbitrarily append multiple versions with duplicate classes.
12. Have a rollback runbook and diagnostic logs that do not contain secrets or oversized references.

## 17. Conclusion

`Instrumentation.appendToSystemClassLoaderSearch(JarFile)` allows an agent to add a JAR so the **system class loader** can find additional instrumentation classes. It **does not** modify `java.class.path`, does not alter already-defined classes, does not guarantee every loader in the JVM sees the helper, and does not grant default module permissions.

With a **custom system loader**, two contracts must both hold: the class configured via `java.system.class.loader` must have a **public constructor(ClassLoader)** and must have an **`appendToClassPathForInstrumentation(String)`** method that actually adds the JAR to its search path. The JVM obtains this method's argument from `JarFile.getName()`. If missing, a Java agent may fail immediately at startup or during append.

The most important takeaway: **check the loader of the class containing the helper call itself**, not just the agent's loader. Writing an agent successfully, appending a JAR successfully, and resolving the helper successfully from the right defining loader are three different things.

### Official Documentation

- [Oracle JDK 17 — Instrumentation.appendToSystemClassLoaderSearch](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#appendToSystemClassLoaderSearch(java.util.jar.JarFile)): `JarFile` contract, special method name for custom loaders, `jarfile.getName()`, exceptions, and the `java.class.path` property.
- [Oracle JDK 17 — ClassLoader.getSystemClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html#getSystemClassLoader()): `java.system.class.loader` configuration, public constructor(ClassLoader), delegation, and recursion.
- [Oracle JDK 17 — java.lang.instrument package](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): startup/dynamic agents and custom system class loader requirements.
- [Oracle JDK 17 — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): `addURL`, parent delegation, and how URL search works.
- [Java Virtual Machine Specification, SE 17 — Linking](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4): resolution failure rules and class loader linkage.
