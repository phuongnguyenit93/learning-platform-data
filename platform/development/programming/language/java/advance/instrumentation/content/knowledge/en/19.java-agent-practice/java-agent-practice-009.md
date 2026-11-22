# Creating an Invisible Helper Scenario and Fixing It with Proper Class Loader Placement

## 1. The Experimental Problem and Core Conclusion

A Java agent can produce a **completely valid classfile**, the JVM defines the class, and the application instantiates the object, yet as soon as the instrumented method calls a **helper class**, a `NoClassDefFoundError` occurs. The root cause is usually not bytecode syntax, but the **class loader used to resolve the reference to the helper**.

Scenario of this lab:

- The agent runs via `-javaagent`, with a transformer replacing the bytes of `lab.target.Service` with a V2 version containing a call to `lab.helper.Probe.mark()`.
- `Probe.class` **exists** and is present on the JVM's **system classpath**.
- `Service` is defined by an **independent `URLClassLoader` with `parent=null`**, which only knows the directory containing `Service.class`.
- `Service` is defined, but its loader **cannot find `Probe`**, so when `work()` runs, the JVM throws **`NoClassDefFoundError`**.
- Fix via **two practical approaches**: (A) have the child loader **delegate** to the system class loader that sees `Probe`; or (B) keep the child loader isolated but **add the URL containing `Probe.class` to the child's own search path**.

**Key takeaway:** "The helper is on `-cp`", "the agent JAR is loaded", or "the thread context class loader is system" **does not guarantee** that a target class defined by another loader can see that helper.

This article belongs to the **Agent Practice** group, so it provides complete Java 17+ source code, manifest, directory structure, `javac`, `jar`, `java` commands, and **actual stdout**. The program was compiled with `javac 24.0.2 --release 17` and run with `-Xverify:all` on JDK 24.0.2. JVM/vendor-dependent points or module policies are explicitly noted rather than generalized from a single run.

### 1.1. Results to Prove

| Scenario | Loader of `Service` | Where is `Probe`? | Result |
|---|---|---|---|
| Control: no agent | Child `URLClassLoader(parent=null)` | System classpath | V1 `work()` returns `original`, because it does not call helper |
| Failure: agent installs V2 | Child `URLClassLoader(parent=null)` | System classpath, invisible to child | V2 is defined, but `work()` causes `NoClassDefFoundError` |
| Fix A: delegation | Child has **system loader** as parent | System classpath, visible via parent | Prints `probe:hit`, returns `instrumented` |
| Fix B: local search path | Child has null parent but contains **URL to helper directory** | Child finds `Probe` itself | Prints `probe:hit`, returns `instrumented` |

These are four **separate JVM runs**. Do not reuse the same `Class<?>` across runs to avoid confusing an already-defined class with the class to be loaded in the next test.

## 2. Why Can a Helper on the Classpath Still Be "Invisible"?

### 2.1. Class Identity Is Tied to the Defining Class Loader

In the JVM, a class's runtime identity is determined by its **binary name plus its defining class loader**. Two loaders can load the same name `lab.target.Service` and create **two different classes**. `Class.getClassLoader()` on the target tells you which loader defined it.

Model of the failure scenario:

~~~text
System / AppClassLoader
  Search path:
    out/app/                       -> lab.app.Main
    out/helper/                    -> lab.helper.Probe
  |
  +-- can find Probe: YES
  +-- Thread context loader: system (in lab)

Child URLClassLoader(parent=null)
  Search URLs:
    out/base/                      -> lab.target.Service
  |
  +-- parent delegation to system: NO
  +-- can find Probe: NO

Java Agent (startup -javaagent)
  |
  +-- transformer returns class bytes V2 for lab/target/Service
  +-- V2 work() has symbolic ref lab/helper/Probe.mark:()V
  +-- target is still defined by Child URLClassLoader
~~~

A child loader does not inherit visibility of all classes on the system classpath simply because the classes are in the same JVM. The **loader delegation graph** determines which classes can be found from a specific target class.

### 2.2. Rules of Symbolic References in Bytecode

When the JVM executes an instruction like:

~~~text
invokestatic lab/helper/Probe.mark:()V
~~~

it must resolve the symbolic reference in the constant pool of **`lab.target.Service`**. Resolution of the referenced class follows the **defining loader of the class containing the reference** and JVM/loader delegation rules; in the lab, that is the child `URLClassLoader`.

Therefore:

- The system loader finds `Probe` — **true**.
- The main thread's context loader is system — **true**.
- The child loader has a null parent and no helper URL — **true**.
- The child loader cannot resolve `Probe` when V2 calls the method — **also true**.
- The result is `NoClassDefFoundError`, not a malformed V2 classfile.

**Do not assume that TCCL is automatically used for every `invokestatic`.** The thread context class loader is used by certain frameworks, SPI/`ServiceLoader`, or custom code when they **explicitly** read the TCCL; it does not replace loader resolution for each symbolic reference in method bytecode.

### 2.3. What Does `parent=null` Mean?

With `new URLClassLoader(urls, null)`, the null parent argument selects delegation to the **bootstrap class loader**, not "no parent and still automatically find everything from system". `java.lang.*` classes can still be found via bootstrap, but `lab.helper.Probe` is on the system search path, so the child does not naturally see it.

According to the Java SE 17 `ClassLoader` documentation, when the parent is null **there is no guarantee that all platform classes are visible**; do not use a parent-null custom loader by default in production applications without a clear isolation design.

## 3. Distinguishing Three Failure Stages: Load Helper, Link Helper, Execute Helper

An invisible-helper failure can surface at different stages:

~~~text
Agent.premain returns normally
        |
        v
Child loader starts loading lab.target.Service
        |
        v
Transformer sees "lab/target/Service"
        |
        +--> returns valid V2 bytes, containing ref to Probe
        |
        v
JVM verifies/defines Service -> succeeds
        |
        v
Service instance is created -> succeeds
        |
        v
Service.work() is invoked via reflection
        |
        v
invokestatic Probe.mark() needs to resolve helper
        |
        +--> Service's loader cannot find Probe
                     |
                     v
               NoClassDefFoundError
~~~

Three independent questions to answer:

1. **Is the target's classfile valid?** — In the lab, yes: the JVM creates a `Service` instance and `-Xverify:all` reports no `VerifyError`.
2. **Has the target class been defined?** — Yes: the program prints `app:service-defined-by-child=true` and proceeds to `app:before-work`.
3. **Is the helper loaded/resolved when the method is called?** — No in isolated mode; yes in both fix modes.

The fact that a class has been defined does not guarantee that **every dependency in every method** will resolve. The JVM may defer some resolution until the first time the relevant instruction is used, depending on the JVMS contract and implementation.

### 3.1. `ClassNotFoundException` vs `NoClassDefFoundError`

In the lab code, we explicitly call:

~~~java
Class.forName("lab.helper.Probe", false, child);
~~~

If the child loader cannot find the helper, this explicit call throws **`ClassNotFoundException`** (a checked exception), which `visible(...)` catches to print `false`.

However, when `Service.work()` executes the symbolic reference `Probe.mark()`, the error can be **`NoClassDefFoundError`**, a `LinkageError`. In the sample code, the method is invoked via `java.lang.reflect.Method.invoke`, so the error inside the method is wrapped in **`InvocationTargetException.getCause()`**; the program unwraps it to print the exact root cause.

**Do not confuse them:** `ClassNotFoundException` comes from an explicit class lookup via API, whereas `NoClassDefFoundError` when the JVM tries to resolve a reference of a compiled class can reflect the exact same root cause of the loader failing to find the dependency.

### 3.2. When Do Other Errors Occur?

- `NoSuchMethodError`: the helper class is found, but at runtime it lacks the required method **descriptor**.
- `IllegalAccessError`: the helper/class/member is found, but the access check fails, e.g., package/module access.
- `ClassCastException`: two classes have the same binary name but are created by **two different defining loaders**, so they are not the same runtime type.
- `ExceptionInInitializerError`: the helper exists, but its static initializer throws; subsequent uses may lead to `NoClassDefFoundError`.
- `ClassFormatError` or `VerifyError`: the generated bytes are invalid before installation, completely different from this lab.
- `SecurityException`: the class loader or module/resource security policy denies the operation.

Therefore, you must combine the **first stack trace**, classloader identity, module context, and timing of the error.

## 4. Designing Four Independent Tests

### 4.1. V1 and V2 Sources of the Same Class

Create two `Service.java` files with the **same package and binary name `lab.target.Service`**, but in **two different source directories**:

- **V1** `src/base/lab/target/Service.java`: `work()` returns the string `"original"`, without calling any helper.
- **V2** `src/v2/lab/target/Service.java`: `work()` calls `lab.helper.Probe.mark()` and then returns `"instrumented"`.

Both versions are compiled into **two separate output folders**. `out/base` contains V1 for the child loader to load, while the agent reads V2 bytes from `out/v2/lab/target/Service.class` and replaces the bytes **before the JVM defines the class**.

### 4.2. Independent Helper

`lab.helper.Probe` resides in `out/helper`. We always place `out/helper` on the **system classpath**:

~~~text
out/app;out/helper          (Windows)
out/app:out/helper          (Linux/macOS)
~~~

This way, when the program prints `app:system-helper-visible=true`, we know the helper **actually exists and the system loader can find it**. If the child still cannot see it, the error clearly belongs to **loader visibility**, not forgetting to build the helper.

### 4.3. Three Child Loader Modes

The application code selects the mode:

~~~text
isolated:
  URLClassLoader(urls = [out/base], parent = null)

delegated:
  URLClassLoader(urls = [out/base], parent = system)

local:
  URLClassLoader(urls = [out/base, out/helper], parent = null)
~~~

**Two fundamentally different fixes:**

- `delegated`: the helper is still defined by the **system loader**; the child relies on parent delegation to use the helper.
- `local`: the child keeps a null parent but has the URL containing the helper itself; **the child can define `Probe` itself**. This fits a plugin that needs self-contained dependencies, but can create an **independent copy of the class** separate from the same-named class defined by the system loader. If the helper API shares object types with the application, identity/visibility must be designed carefully.

## 5. Complete Lab Directory Structure

~~~text
helper-loader-lab/
├── agent.mf
├── src/
│   ├── agent/
│   │   └── lab/agent/HelperVisibilityAgent.java
│   ├── app/
│   │   └── lab/app/Main.java
│   ├── base/
│   │   └── lab/target/Service.java
│   ├── v2/
│   │   └── lab/target/Service.java
│   └── helper/
│       └── lab/helper/Probe.java
└── out/                        (created after build)
    ├── agent/
    ├── app/
    ├── base/
    ├── v2/
    ├── helper/
    └── visibility-agent.jar
~~~

Do not arbitrarily rename packages when copying the code, because the transformer **matches the exact** internal class name `lab/target/Service` and V2 references `lab/helper/Probe`.

The code uses public APIs from `java.instrument`, reflection, and `java.net.URLClassLoader`. No ASM or Byte Buddy is needed: **the agent replaces the entire classfile at class definition time with a valid V2 classfile generated by `javac`**. This is a controlled way to focus on classloader topology without distracting into bytecode manipulation algorithms.

## 6. Writing the Agent That Reads V2 Classfile from a Path

File **`src/agent/lab/agent/HelperVisibilityAgent.java`**:

~~~java
package lab.agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.ProtectionDomain;

public final class HelperVisibilityAgent {
    public static void premain(String path, Instrumentation inst)
            throws Exception {

        byte[] replacement = Files.readAllBytes(Path.of(path));

        System.out.println("agent:ready");

        inst.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(
                    ClassLoader loader,
                    String name,
                    Class<?> redefined,
                    ProtectionDomain domain,
                    byte[] original) {

                if (!"lab/target/Service".equals(name)) {
                    return null;
                }

                System.out.println(
                        "agent:transform=lab/target/Service");

                return replacement.clone();
            }
        }, false);
    }
}
~~~

### 6.1. Why Choose `premain`?

With `-javaagent`, the JVM invokes `premain` **before `Main.main`**, so the transformer is registered before `Main` creates the custom `URLClassLoader` and loads `Service`. We want to replace the bytes **during the very first class definition** rather than changing the definition of an already-loaded class.

### 6.2. Meaning of the Callback

- `name` is the **internal name** `lab/target/Service`, not `lab.target.Service`.
- Strict filtering `if (!"lab/target/Service".equals(name)) return null;` avoids modifying JVM, agent, and other application classes.
- `replacement` is the precompiled bytes of `Service` V2; `replacement.clone()` returns a fresh array so the callback does not share a mutable array with other code.
- V2 still has the **same binary class name** as V1: `lab.target.Service`.
- The callback runs before the class is defined. `System.out.println("agent:transform...")` **does not by itself prove** the JVM has verified and installed the bytes; the `app:service-defined-by-child=true` milestone and invocation provide additional evidence.
- `addTransformer(..., false)` does not request retransformation capability; we do not call `retransformClasses`.
- The agent loads the replacement file **before registering the transformer**, so a missing file causes startup to fail cleanly instead of failing unexpectedly inside a class-loading callback.

### 6.3. Why Not "Automatically Add the Helper to the System Search Path"?

The agent only **generates/replaces bytes for `Service`**; it does not force the target loader to see the helper class. Java Instrumentation **does not automatically propagate all of an agent's dependencies** to the target's defining loader. Thus V2 can still call an invisible class even when the transformer works perfectly.

This is the experimental root cause we want to demonstrate.

### 6.4. Limitations of Using a Replacement Classfile

Replacing V1 classfile bytes with V2 is suitable **for a class that has not yet been defined**. If the target is already loaded and requires `redefineClasses`/`retransformClasses`, there are schema limits, VM capabilities, and active frame constraints. Do not extrapolate from this load-time example to assume you can arbitrarily change the superclass, fields, or methods of a running class.

## 7. Writing the Application That Creates the Loader and Checks Visibility

File **`src/app/lab/app/Main.java`**:

~~~java
package lab.app;

import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class Main {
    private static boolean visible(
            ClassLoader loader, String name) {
        try {
            Class.forName(name, false, loader);
            return true;
        } catch (ClassNotFoundException expected) {
            return false;
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                    "mode targetDir helperDir");
        }

        String mode = args[0];
        if (!mode.equals("isolated")
                && !mode.equals("delegated")
                && !mode.equals("local")) {
            throw new IllegalArgumentException("bad mode");
        }

        URL target = Path.of(args[1])
                .toAbsolutePath().toUri().toURL();
        URL helper = Path.of(args[2])
                .toAbsolutePath().toUri().toURL();

        ClassLoader system = ClassLoader.getSystemClassLoader();

        ClassLoader parent =
                mode.equals("delegated") ? system : null;

        URL[] urls = mode.equals("local")
                ? new URL[] {target, helper}
                : new URL[] {target};

        System.out.println("app:mode=" + mode);

        System.out.println(
                "app:system-helper-visible="
                + visible(system, "lab.helper.Probe"));

        System.out.println(
                "app:context-is-system="
                + (Thread.currentThread().getContextClassLoader()
                   == system));

        try (URLClassLoader child =
                     new URLClassLoader(urls, parent)) {

            System.out.println(
                    "app:child-parent="
                    + (child.getParent() == null
                       ? "bootstrap" : "system"));

            System.out.println(
                    "app:child-helper-visible="
                    + visible(child, "lab.helper.Probe"));

            Class<?> service = Class.forName(
                    "lab.target.Service", true, child);

            System.out.println(
                    "app:service-defined-by-child="
                    + (service.getClassLoader() == child));

            Object instance = service
                    .getDeclaredConstructor().newInstance();

            Method work = service.getMethod("work");

            System.out.println("app:before-work");

            try {
                Object value = work.invoke(instance);
                System.out.println("app:result=" + value);
            } catch (InvocationTargetException e) {
                System.out.println(
                        "app:invoke-cause="
                        + e.getCause().getClass().getSimpleName());
            }
        }

        System.out.println("app:end");
    }
}
~~~

This is a **complete standalone Java file**, requiring no compilation against the agent classes; the application only uses reflection, `URLClassLoader`, and JDK APIs.

### 7.1. Logic of the Variables

- `system`: the system/application class loader in the current JVM.
- `target`: URL of the directory containing `Service.class` V1.
- `helper`: URL of the directory containing `Probe.class`.
- `mode=isolated`: child has null parent, URLs contain only target.
- `mode=delegated`: child has system parent, URLs contain only target.
- `mode=local`: child has null parent, URLs contain target and helper.

The error branch in `visible(...)` only catches `ClassNotFoundException` when trying `Class.forName`. The goal is to compare **helper lookup capability across each loader**; do not run `Class.forName` on every JVM class or treat this function as a comprehensive module/member accessibility verifier.

### 7.2. Why Print `app:context-is-system`?

The line:

~~~text
app:context-is-system=true
~~~

appears in all three modes on the test JVM. It clearly illustrates: **TCCL = system does not automatically make `Service` defined by the child loader see `Probe`**. Some frameworks intentionally use TCCL to load plugins; however, `invokestatic` is linked via the symbolic reference of the class containing the instruction, not simply by "looking up the thread's TCCL".

### 7.3. Why Print `service-defined-by-child`?

`Class.forName("lab.target.Service", true, child)` loads and initializes `Service`. The code directly compares:

~~~java
service.getClassLoader() == child
~~~

If true, we know **`Service` is actually defined by the child**, not "claimed" by the parent loader. In the lab, the system classpath **does not contain `Service.class`**, so even `delegated` mode lets the child define `Service`. Only the helper is provided by the parent.

This is an important point in Fix A: **ownership of the target class does not change**, only dependency visibility is opened through delegation.

### 7.4. Reflection and Root Cause

`Method.invoke` wraps exceptions/errors thrown inside the method in `InvocationTargetException`. If you only log this wrapper, learners might see `InvocationTargetException` without seeing the actual `NoClassDefFoundError`. In the code, we use:

~~~java
Throwable cause = e.getCause();
System.out.println(
        "app:invoke-cause=" + cause.getClass().getSimpleName());
~~~

This is an **illustrative snippet** with the same behavior as the complete code (which calls `e.getCause()` directly). For production diagnostics, capture the full stack trace of the root cause, loader/module context, and nested exceptions; do not just print the short name.

**Do not catch `InvocationTargetException` and swallow the error in real applications.** Here the catch is for the test to display the cause and continue running, not a production recovery strategy.

## 8. Service V1, Service V2, and Probe Helper

### 8.1. V1: Method Without Helper Dependency

File **`src/base/lab/target/Service.java`**:

~~~java
package lab.target;

public final class Service {
    public String work() {
        return "original";
    }
}
~~~

This is the original classfile that the child loader will find at `out/base/lab/target/Service.class`. With **no agent**, even though the child does not see `Probe`, the method runs fine because V1 has no symbolic reference to the helper.

### 8.2. V2: Valid Bytecode with a Reference to `Probe`

File **`src/v2/lab/target/Service.java`**:

~~~java
package lab.target;

import lab.helper.Probe;

public final class Service {
    public String work() {
        Probe.mark();
        return "instrumented";
    }
}
~~~

V2 has the same package, class name, and public method signature as V1, but adds the `Probe.mark()` call. When compiling V2, the compiler must see `Probe` to emit valid bytecode; therefore, the V2 build command uses `-cp out/helper`.

**Being able to compile V2 does not guarantee `Probe` is on `Service`'s loader search path at runtime.** This is the distinction between compile-time classpath and runtime classloader topology.

### 8.3. Helper: No ASM/Byte Buddy Required

File **`src/helper/lab/helper/Probe.java`**:

~~~java
package lab.helper;

public final class Probe {
    public static void mark() {
        System.out.println("probe:hit");
    }
}
~~~

The helper only uses `System.out`, so it is simple enough to run via the system loader or a parent-null child loader in the two fix modes. When a helper depends on additional JARs, native libraries, logging facades, or other modules, loader placement must resolve the **entire dependency closure**, not just `Probe.class`.

## 9. Manifest and Compilation: Two Same-Named Classfiles in Separate Outputs

File **`agent.mf`** (keep trailing newline):

~~~text
Manifest-Version: 1.0
Premain-Class: lab.agent.HelperVisibilityAgent

~~~

`Premain-Class` is a **binary Java name** with dots, whereas the transformer callback compares `lab/target/Service` with slashes. Do not mix up the two formats.

### 9.1. Create Output Directories

Bash:

~~~bash
mkdir -p out/agent out/app out/base out/v2 out/helper
~~~

PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out/agent, out/app, out/base, out/v2, out/helper
~~~

### 9.2. Build on JDK 17+

From the root directory `helper-loader-lab`, run sequentially:

~~~bash
javac --release 17 -d out/agent src/agent/lab/agent/HelperVisibilityAgent.java

javac --release 17 -d out/app src/app/lab/app/Main.java

javac --release 17 -d out/base src/base/lab/target/Service.java

javac --release 17 -d out/helper src/helper/lab/helper/Probe.java

javac --release 17 -cp out/helper -d out/v2 src/v2/lab/target/Service.java

jar --create --file out/visibility-agent.jar --manifest agent.mf -C out/agent .
~~~

Explanation:

1. `out/agent`: agent bytecode.
2. `out/app`: `Main` application bytecode, does not import `Service`.
3. `out/base`: `Service` V1 for the child `URLClassLoader` to load.
4. `out/helper`: `Probe` separately, found by the system loader via the runtime classpath.
5. `out/v2`: `Service` V2 generated by `javac` with a reference to `Probe`; **do not put V2 on the runtime classpath**.
6. `visibility-agent.jar`: contains `HelperVisibilityAgent` and the `Premain-Class` manifest.

`--release 17` constrains source/API and produces classfile major version **61**, suitable for Java 17+. In the experiment, the toolchain was JDK 24.0.2 compiled with `--release 17`; tests ran on JDK 24.0.2. For production targets running on 17/21 runtimes, run additional integration tests directly on those JVMs.

### 9.3. Inspect Artifacts Before Running

~~~bash
jar --list --file out/visibility-agent.jar
javap -c -p -classpath out/v2 lab.target.Service
jdeps --jdk-internals out/visibility-agent.jar
~~~

Things to verify:

- The agent JAR contains `lab/agent/HelperVisibilityAgent.class` and the nested transformer class.
- `META-INF/MANIFEST.MF` of the **final JAR** contains the exact `Premain-Class`.
- `javap -c` on V2 shows the instruction calling `lab/helper/Probe.mark:()V` in `work()`.
- `jdeps --jdk-internals` reports no dependencies on JDK internal APIs.
- `out/base` and `out/v2` have the same binary name `lab.target.Service` but **different method bodies**.

Do not use `--add-exports` or `--add-opens` to run the example: all classes are in unnamed modules, using public APIs and a public helper.

## 10. Control Without Agent: Service V1 Works

This is the baseline to ensure the child loader can load `Service`. The system classpath **has `Probe`**, while the parent-null child **cannot see `Probe`**. Because V1 does not call the helper, there is no error.

**Windows PowerShell or Command Prompt** (classpath separator `;`):

~~~powershell
java -Xverify:all -cp "out/app;out/helper" lab.app.Main isolated out/base out/helper
~~~

**Linux/macOS Bash** (classpath separator `:`):

~~~bash
java -Xverify:all -cp "out/app:out/helper" lab.app.Main isolated out/base out/helper
~~~

**Exact stdout from JDK 24.0.2:**

~~~text
app:mode=isolated
app:system-helper-visible=true
app:context-is-system=true
app:child-parent=bootstrap
app:child-helper-visible=false
app:service-defined-by-child=true
app:before-work
app:result=original
app:end
~~~

Reading the output:

- The system loader finds `Probe`, proving the helper is not missing JVM-wide.
- TCCL is system, yet `child-helper-visible=false`.
- `Service` is indeed defined by the child.
- The original method returns `original` and the process completes.
- There is no `agent:ready` or `agent:transform` because no agent was run.

**Significance:** a parent-null class loader does not automatically cause an error; it fails **when bytecode requires a dependency that the loader cannot find**.

## 11. Reproducing the Failure: Agent Installs V2, Child Loader Cannot See `Probe`

### 11.1. Reproduction Command

**Windows:**

~~~powershell
java -Xverify:all -javaagent:out/visibility-agent.jar=out/v2/lab/target/Service.class -cp "out/app;out/helper" lab.app.Main isolated out/base out/helper
~~~

**Linux/macOS:**

~~~bash
java -Xverify:all -javaagent:out/visibility-agent.jar=out/v2/lab/target/Service.class -cp "out/app:out/helper" lab.app.Main isolated out/base out/helper
~~~

The argument after `=` in `-javaagent` is the path to the V2 class bytes. Do not confuse it with the application classpath. The JVM passes that argument to `premain(String path, Instrumentation inst)`, and the agent reads the bytes before registering the transformer.

### 11.2. Verified Stdout

~~~text
agent:ready
app:mode=isolated
app:system-helper-visible=true
app:context-is-system=true
app:child-parent=bootstrap
app:child-helper-visible=false
agent:transform=lab/target/Service
app:service-defined-by-child=true
app:before-work
app:invoke-cause=NoClassDefFoundError
app:end
~~~

This is the **actual output of the source code in this article**, not a hypothetical scenario. The program exits with code 0 because `Main` intentionally catches `InvocationTargetException` and prints the root cause for the lab. If a production method lacks this catch, the error can fail the request/thread.

### 11.3. Proving the Cause Step by Step

1. `agent:ready`: `premain` reads the V2 file and registers the transformer successfully.
2. `app:system-helper-visible=true`: the helper can be found by the system loader.
3. `app:context-is-system=true`: TCCL is also system, but that **does not help** the symbolic reference in `Service` V2.
4. `app:child-parent=bootstrap`: the parent-null child does not delegate to system.
5. `app:child-helper-visible=false`: `Probe` is not on the child's search path.
6. `agent:transform=lab/target/Service`: the transformer matched the right class and returned V2 bytes.
7. `app:service-defined-by-child=true`: the JVM actually defined `Service` with the child.
8. `app:before-work`: only method invocation remains.
9. `app:invoke-cause=NoClassDefFoundError`: the V2 method cannot resolve `Probe`.

**Exact conclusion:** **V2 bytecode was successfully installed/defined**, but the helper is not visible to **`Service`'s defining loader**. The error is **not** in `Premain-Class`, not a `ClassFormatError`, and not a helper missing from the entire system classpath.

## 12. Fix A: Delegate to the System Class Loader

Change child creation from:

~~~java
new URLClassLoader(
        new URL[] {target},
        null);
~~~

to:

~~~java
new URLClassLoader(
        new URL[] {target},
        ClassLoader.getSystemClassLoader());
~~~

This **does not automatically change `Service`'s defining loader to system**: because `Service.class` is only in `out/base` and not on the system classpath, the child still defines `Service` itself. However, when `Service` needs `Probe`, the child delegates to the **system** parent and finds the helper.

### 12.1. Fix A Command

**Windows:**

~~~powershell
java -Xverify:all -javaagent:out/visibility-agent.jar=out/v2/lab/target/Service.class -cp "out/app;out/helper" lab.app.Main delegated out/base out/helper
~~~

**Linux/macOS:**

~~~bash
java -Xverify:all -javaagent:out/visibility-agent.jar=out/v2/lab/target/Service.class -cp "out/app:out/helper" lab.app.Main delegated out/base out/helper
~~~

### 12.2. Verified Exact Stdout

~~~text
agent:ready
app:mode=delegated
app:system-helper-visible=true
app:context-is-system=true
app:child-parent=system
app:child-helper-visible=true
agent:transform=lab/target/Service
app:service-defined-by-child=true
app:before-work
probe:hit
app:result=instrumented
app:end
~~~

**Decisive difference:** `app:child-parent=system` and `app:child-helper-visible=true`. The `probe:hit` line proves the helper code actually executed; `app:result=instrumented` proves the V2 method completed.

### 12.3. When Should You Choose Delegation?

Suitable if:

- The helper is a **shared API** across multiple plugins/target classes.
- The helper can be **defined once** by the system or an ancestor loader.
- The target needs to exchange object types with the rest of the app.
- There is a clear class identity and versioning policy.

Things to check:

- If the system loader **also contains `Service`** of the same name, parent-first delegation may cause the child to **no longer define `Service` itself**; `service-defined-by-child` would become `false`, changing the experiment.
- If the helper is loaded by the system loader but needs dependencies that exist only in the child, the helper may fail to find those dependencies (reversing the visibility direction).
- Do not arbitrarily open parent delegation to the entire system classpath for untrusted plugins; this widens the scope of APIs the plugin can call.

Fix A adjusts the **loader hierarchy** appropriately, rather than upgrading the bytecode parser or adding launcher flags.

## 13. Fix B: Keep Isolation, Place the Helper in the Child's Search Path

Change child URLs from:

~~~java
new URLClassLoader(
        new URL[] {target},
        null);
~~~

to:

~~~java
new URLClassLoader(
        new URL[] {target, helper},
        null);
~~~

With a null parent, the child does not delegate to system, **but it has both the folder containing `Service` and the folder containing `Probe`**, so it finds the helper itself.

### 13.1. Fix B Command

**Windows:**

~~~powershell
java -Xverify:all -javaagent:out/visibility-agent.jar=out/v2/lab/target/Service.class -cp "out/app;out/helper" lab.app.Main local out/base out/helper
~~~

**Linux/macOS:**

~~~bash
java -Xverify:all -javaagent:out/visibility-agent.jar=out/v2/lab/target/Service.class -cp "out/app:out/helper" lab.app.Main local out/base out/helper
~~~

### 13.2. Verified Exact Stdout

~~~text
agent:ready
app:mode=local
app:system-helper-visible=true
app:context-is-system=true
app:child-parent=bootstrap
app:child-helper-visible=true
agent:transform=lab/target/Service
app:service-defined-by-child=true
app:before-work
probe:hit
app:result=instrumented
app:end
~~~

**Difference:** `app:child-parent=bootstrap` remains unchanged (delegation is not altered), but `app:child-helper-visible=true` because the local URLs added the helper. The V2 method runs successfully.

### 13.3. The Cost of Isolation

Even though the system loader has also loaded `lab.helper.Probe`, the parent-null child can **define another copy of `Probe`** from `out/helper`. Two classes with the same binary name but different defining loaders **are not the same runtime type**.

In the demo, `Probe.mark()` returns `void` and only uses public JDK `System.out`, so having a separate helper copy causes no issue. However, if the helper:

- returns an object of an interface defined by the system loader;
- uses singletons/static state shared across multiple plugins;
- holds global caches/registries;
- binds to type annotations or framework service APIs;
- calls dependencies that exist only in the system loader;

then a child-local helper can cause class identity mismatch, duplicated state, or `ClassCastException`. In that case, design **shared API classes in a common loader**, while implementations can be isolated, instead of copying the entire type graph.

## 14. Comparing the Two Fixes and Choosing an Architecture

| Criterion | Fix A: `parent=system` | Fix B: add helper URL to child |
|---|---|---|
| Is target still defined by child? | Yes in the lab, because system lacks `Service` | Yes |
| Helper is found by | System parent via delegation | Child search path |
| Does child retain isolation from system app classes? | Not completely; sees system delegation | More so, though still sees bootstrap |
| Can helper be defined twice with the same name? | Less likely if sharing an ancestor | Yes, if both system and child have the same helper |
| Sharing interfaces/DTOs with app | Easier if loader graph is consistent | Requires clear loader boundary design |
| Depends on system loader classpath | Yes | No for the URL-added helper |
| Package/version conflict risk | Parent-first may pick unexpected system version | Plugin-local version may conflict at interface boundary |
| Suitability for isolated plugins | Requires trust/security consideration | Suitable when helper has self-contained dependencies and controlled interfaces |

**Selection principle:** place the helper **in a loader usable by the class containing the referencing bytecode**, and ensure the helper in turn sees **its own dependencies**. Do not just ask "which JAR is the helper in", but draw the **loader graph** and determine **class identity**.

### 14.1. What Not to Do

- Do not add `out/helper` to the **system** classpath and assume a parent-null target will see the helper; the test proves that is false.
- Do not set `Thread.currentThread().setContextClassLoader(system)` and expect every `invokestatic` to use the system loader.
- Do not call `Class.forName("lab.helper.Probe", true, system)` beforehand and expect a parent-null child to automatically use the class loaded by system.
- Do not change `Premain-Class` or edit the agent manifest to "fix" a symbolic reference when the target is already installed.
- Do not just copy `Probe.class` into the agent JAR while ignoring the target's loader. The agent JAR is usually on the system search path, not the bootstrap or child-local search path.
- Do not hide `NoClassDefFoundError` with a blanket catch in business code; in the demo, the catch is only to print the cause.

## 15. Advanced Solutions: Bootstrap Helper and the Module System

The two tested approaches are the most direct. For an agent that actually instruments **bootstrap classes**, parent-null custom loaders, or multiple application loaders, you may need to organize the helper into a **bootstrap-visible helper JAR**.

### 15.1. `appendToBootstrapClassLoaderSearch`

Java SE provides:

~~~java
Instrumentation.appendToBootstrapClassLoaderSearch(
        java.util.jar.JarFile jarfile);
~~~

This is an **illustrative signature**, not a standalone runnable command. You must create a separate JAR containing the appropriate helper classes and pass the `JarFile` to the API in the agent.

Contract of the API: when the bootstrap loader does not find a class in its default search path, the JVM can search the appended JAR. Thus a child loader with a null parent **can delegate up to bootstrap** to find the helper if the helper with the right package/name has been added.

**However, this technique carries risks:**

1. A helper JAR for bootstrap should contain only **classes truly intended for bootstrap** and depend only on classes bootstrap can access.
2. Do not stuff the entire agent, ASM/Byte Buddy, JSON, or logging stack into bootstrap unnecessarily; this can cause class loading recursion or namespace collisions.
3. A class loaded by bootstrap may not see dependencies that exist only in the system loader.
4. Package-private helpers, nested classes, or non-public accessors can hit `IllegalAccessError` if they share the same name/package but have a different **runtime package** (package + defining loader).
5. Appending to the bootstrap class path does not automatically create JPMS module read/export relations that classes in named modules may need.
6. Test on the exact runtime/vendor; only append JARs with clear provenance and permissions.

**There is no bootstrap append test in the main lab suite**; the stdout results in sections 11–13 only prove **delegation** and **local URL search path**. Only deploy a bootstrap helper when the problem truly requires it, with dedicated integration tests.

### 15.2. `appendToSystemClassLoaderSearch` Has Limitations

Java SE also has:

~~~java
Instrumentation.appendToSystemClassLoaderSearch(
        java.util.jar.JarFile jarfile);
~~~

It adds a JAR to where the **system class loader** searches, and does not automatically make a parent-null child see the system loader. If a system has an `isolated` failure like the demo, simply calling `appendToSystemClassLoaderSearch` **is not a fix** unless you also change the delegation graph or loader search path.

### 15.3. Module Access Is Another Dimension

Since Java 9, named modules have reads/exports/opens rules:

- **Class not found**: usually a loader search path or module resolution/visibility issue.
- **Class found but not accessible**: can produce `IllegalAccessError` or reflection `InaccessibleObjectException`.
- `Instrumentation.redefineModule` can programmatically alter some module reads/exports/opens, but **does not supply a missing classfile** to a child loader.
- `--add-opens` is for deep reflection, not a cure-all for every `NoClassDefFoundError`.

In the lab, classes reside on the classpath and in unnamed modules, so the results focus on the **loader graph**, independent of `module-info.java` configuration.

## 16. Evidence-Based Production Diagnostics

When an agent logs a successful transform yet the method calling the helper fails, gather information in sequence:

### Step 1 — Confirm the Executing Bytecode Was Installed

- Was the agent/transformer called for the **exact class internal name**?
- Did the transformer return `null` or a replacement `byte[]`?
- Are there other transformers in the pipeline?
- Did the JVM emit `VerifyError`/`ClassFormatError` before definition?
- What milestone confirms successful definition/update?
- For an already-loaded class, did `retransformClasses`/`redefineClasses` return normally?

**Do not treat a callback log as proof of completed installation.** In the demo, the `service-defined-by-child=true` milestone preceding the `work()` failure confirms the target was defined.

### Step 2 — Find the Class Containing the Failing Symbolic Reference

Use `javap -c -p` or an appropriate bytecode inspector to see:

~~~text
invokestatic lab/helper/Probe.mark:()V
~~~

Check the binary name, method name, descriptor, and source artifact of the installed bytes. A helper relocated to another package while V2 still calls the old name produces a similar error.

### Step 3 — Identify the Exact Defining Loader

Record in diagnostic code:

~~~java
ClassLoader loader = service.getClassLoader();
System.out.println(loader);
~~~

This is an **excerpt**, requiring `service` to be an appropriate `Class<?>`. For custom loaders, log identity rather than just the class loader type name. Repeated `URLClassLoader` names across instances do not prove they are the same loader.

### Step 4 — Compare Visibility Across Loaders

In an environment with diagnostic permissions:

~~~java
Class.forName("lab.helper.Probe", false, system);
Class.forName("lab.helper.Probe", false, child);
~~~

These lines are **examples to run separately when debugging**, with exceptions handled appropriately. If system sees the helper while child does not, investigate the child's delegation parent and URL/JAR search path.

Note: explicit `Class.forName` can trigger additional class loading; do not use it as a sweeping profiler in production. And finding a class does not always prove method access is valid in named modules.

### Step 5 — Inspect the Context Loader Without Extrapolating

Record `Thread.currentThread().getContextClassLoader()` as supplementary data; do not assume it is the loader the JVM uses to resolve every symbolic reference in the target's bytes.

### Step 6 — Choose the Appropriate Fix

- Helper is a public shared API: place it in a consistent ancestor loader and have the target loader delegate to it.
- Helper is a plugin-local implementation: add the helper along with its dependency closure to the plugin's loader.
- Target is in bootstrap: you may need a minimal bootstrap-visible helper JAR, with careful testing.
- Named modules: additionally resolve proper module reads/exports, without confusing class lookup with access.
- Multiple agents: avoid shading/package conflicts and duplicate helpers across loaders.

### Step 7 — Retest Behavior, Not Just Absence of Exceptions

You must observe the **probe actually running**, the method returning the right result, and no classloader leaks, version conflicts, or errors on other exception paths. In the lab, both `probe:hit` and `app:result=instrumented` prove that both helper invocation and method return succeeded.

## 17. Common Errors and Actual Causes

| Symptom | What to Check |
|---|---|
| `app:system-helper-visible=true` but `child-helper-visible=false` | Target's loader has a null parent or does not delegate to system |
| `app:context-is-system=true` yet `NoClassDefFoundError` | TCCL does not automatically override bytecode loader resolution |
| `NoClassDefFoundError: lab/helper/Probe` on invoke | Child cannot see helper, binary name mismatch, or helper initialization failed |
| `ClassNotFoundException` in `Class.forName` probe | The loader being tested cannot find the class by name |
| `InvocationTargetException` on reflection call | Read `getCause()` to see the actual root cause |
| `ClassFormatError` when `Service` is defined | Replacement bytes are malformed, not a missing helper at invocation |
| `VerifyError` | Invalid stack maps/frames/instructions; inspect output bytecode |
| `IllegalAccessError` | Runtime package, module exports, or visibility/member access |
| `NoSuchMethodError` | Helper class exists, but version/descriptor differs |
| `ClassCastException` after local fix | Duplicate class identity across loaders when sharing interfaces/DTOs |
| `probe:hit` does not appear even with no error | Was V2 really installed? Is `Probe` on the execution path? |
| Delegated fix makes `service-defined-by-child=false` | System loader is defining a same-named `Service` before child |
| Helper has sub-libraries and still fails | Helper's dependency closure is not yet visible |
| Copied helper into agent JAR but target still fails | Agent JAR loader is not in target's delegation graph |
| App runs without agent but fails with agent | V2 bytecode introduces a new symbolic reference that needs resolution |
| Called `appendToSystemClassLoaderSearch` yet child still fails | Parent-null child does not delegate to system |
| Changed TCCL without resolving the issue | Symbolic reference uses `Service`'s defining loader, not TCCL |
| Reran test in same JVM and class did not re-transform | Class is already loaded; a load-time transformer does not automatically redefine it |
| Class loader fails to unload after experiment | Strong references to `Class`/loader, threads, caches, or helper state |

### 17.1. Do Not Arbitrarily Modify Class Loaders in Real Systems

Changing a plugin loader's parent can make many application types visible, altering **class identity**, version resolution, and security boundaries. You must integration-test plugin APIs, DTO classes, serialization, and service providers. If the loader hierarchy cannot be changed, a local helper or a shared bridge/interface may be more suitable.

### 17.2. Reflection Is Only a Demo Mechanism

The application uses reflection to load `lab.target.Service` without putting `Service` on the system classpath. That preserves the necessary condition for the experiment. In real applications, the target may be loaded via a plugin framework, servlet container, OSGi, or a module layer; you must inspect the target's **actual defining loader**. Do not copy test reflection into production if the system already has a clear lifecycle/plugin loading mechanism.

## 18. Exercises and Self-Assessment Questions

### Exercise A — Predict the Error Before Running

The system classpath has `Probe`, while the child loader has `parent=null` and only knows `Service.class`. V2 bytecode calls `Probe.mark()`. When the method runs, what happens?

**Answer:** the child cannot find `Probe` in its graph, and the method may throw `NoClassDefFoundError`. System/TCCL visibility of the helper is not enough.

### Exercise B — Distinguish Classfile Errors from Linkage Errors

In isolated mode with the agent, the program prints `app:service-defined-by-child=true` and then `app:invoke-cause=NoClassDefFoundError`. What does that say about V2 installation?

**Answer:** `Service` was successfully defined on the test JVM; the error occurred when executing the helper call. This is not a `ClassFormatError` during class definition.

### Exercise C — Fix via Delegation

Change the child's parent from `null` to `ClassLoader.getSystemClassLoader()`. Why is `Service` still defined by the child while `Probe` can be provided by the parent?

**Answer:** `Service` is only in the child's URL; `Probe` is in the parent's search path. Parent-first lookup fails for `Service` so the child defines it, but succeeds for `Probe`.

### Exercise D — Fix via Local URL

Keep the parent null and add the helper's URL to the child. Why does it run successfully? Is there a risk of creating two `lab.helper.Probe` classes with the same name in the JVM?

**Answer:** the child finds the helper itself in its URL search path; there can be one copy defined by system and one copy defined by child, with different class identities.

### Exercise E — TCCL Is Not a Default Solution

Set TCCL to system in isolated mode (which is already system in the lab). Why does it not fix the error?

**Answer:** `Service` V2's symbolic reference resolves via `Service`'s defining loader, not automatically via the thread context loader.

### Exercise F — Check Helper via Two `Class.forName` Calls

Why does `Class.forName("lab.helper.Probe", false, system)` return the class while the same call with `child` throws `ClassNotFoundException`?

**Answer:** the two loaders have different search paths/delegation graphs; the global JVM does not have a single unified class namespace.

### Exercise G — Change Helper Package

V2 is compiled calling `lab.helper.Probe`, but the helper is deployed with binary name `lab.runtime.Probe`. Does putting the JAR on system solve it?

**Answer:** no; the binary class name and method descriptor must match, or V2 bytes must be rebuilt/transformed accordingly.

### Exercise H — Helper Calls an API Only Available in System

You use the local fix, and the child's helper references a class in the application system loader. What is the risk?

**Answer:** the helper defined by the child may also fail to see that dependency; you must design the dependency closure and shared API boundary, not just copy a single file.

### Exercise I — Named Module Access

A loader sees the helper, yet the target still reports `IllegalAccessError` because the package is not exported. Will adding the helper to the URL definitely fix it?

**Answer:** no; you must properly resolve module reads/exports/access.

### Exercise J — Bootstrap Helper

When instrumenting a bootstrap class, why does copying the helper into a system JAR not guarantee the bootstrap class sees the helper? When should `appendToBootstrapClassLoaderSearch` be considered?

**Answer:** bootstrap does not delegate down to system; the helper may need to be in a minimal bootstrap-visible JAR. Dependencies/namespaces must be controlled and tested separately.

### Quick Questions

1. **How do you get the defining class loader of a class?** — `clazz.getClassLoader()`.
2. **Does `URLClassLoader` with `parent=null` automatically search the system classpath?** — No.
3. **Does having the helper on the system classpath mean the child will definitely find it?** — No.
4. **Does TCCL automatically resolve `invokestatic` in the target?** — No.
5. **Where do you read the root error inside a reflection wrapper?** — `InvocationTargetException.getCause()`.
6. **If V2 is defined but the helper is missing on invoke, what can happen?** — `NoClassDefFoundError`.
7. **What does Fix A change?** — Parent delegation to a loader that has the helper.
8. **What does Fix B change?** — The URLs/class search path of the child loader itself.
9. **Can the local fix create duplicate class identity?** — Yes.
10. **Does `appendToSystemClassLoaderSearch` automatically fix a parent-null child?** — No.
11. **Is `appendToBootstrapClassLoaderSearch` needed for the main lab?** — No.
12. **Is a logged transform callback enough to prove the class was defined?** — No.
13. **Does `-Xverify:all` guarantee all helpers will be visible?** — No, linkage/runtime still must be tested.
14. **Can you freely change the schema of a loaded class via a transformer?** — No; it requires capabilities and compliance with VM restrictions.
15. **What is the confirmation criterion for the fix in this lab?** — `probe:hit`, `app:result=instrumented`, and no linkage error.

## 19. Release Checklist and Official References

### Before Reproducing the Failure in a Sandbox

- [ ] Real agent is launched with `-javaagent` and the correct `Premain-Class`.
- [ ] `Service` V1 and V2 have the same binary name but are compiled separately.
- [ ] V2 only adds a public helper call, with the same method signature.
- [ ] `Probe` is built at `out/helper` and the system loader sees it.
- [ ] `Service.class` is not on the system classpath so the child actually defines the target.
- [ ] Code logs the `service-defined-by-child` milestone before `work()`.
- [ ] `InvocationTargetException` is caught in the lab to reveal the root cause.
- [ ] Run the **no-agent** baseline and save output.
- [ ] Run isolated failure with the agent to reproduce `NoClassDefFoundError`.
- [ ] Run the delegated fix and confirm `probe:hit`.
- [ ] Run the local fix and confirm `probe:hit`.
- [ ] Clearly compare **helper visibility paths** without changing Java business code between fixes.

### When Choosing a Solution in Production

- [ ] Draw the actual class loader graph, including the target defining loader and the loader owning the helper.
- [ ] Decide whether the helper is a shared API or a local implementation.
- [ ] Check the helper dependency closure, versions, and shading/relocation.
- [ ] Consider class identity if the same binary name is defined by multiple loaders.
- [ ] If the target is in a named module, verify reads/exports/opens and access.
- [ ] Avoid unnecessary bootstrap helpers; if needed, use a minimal JAR and test separately.
- [ ] Check rollback if a running class has already been instrumented.
- [ ] Test code paths, exception paths, and async threads.
- [ ] Do not swallow linkage errors in production without a fail-open/fail-fast policy.
- [ ] Measure startup/transform/lookup/GC overhead; do not assume instrumentation is free.
- [ ] Do not over-expand class loader/module permissions beyond what is necessary.

**Conclusion:** when a Java agent inserts a call to a helper, **the helper must be visible from the perspective of the class loader used to define the target**. Putting the helper on the system classpath is only half the story. The `URLClassLoader(parent=null)` scenario demonstrates a very real failure: the JVM defines `Service` V2 successfully but cannot resolve `Probe` when the method runs. Two fixes were tested: **delegate to system** if the helper is a shared dependency, or **add the helper to the child's search path** if isolation is required. Determine the loader graph, class identity, and module access before changing bytecode or adding launcher flags.

### Official Sources

- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): delegation model, parent-null, and system/platform/bootstrap loaders.
- [Java SE 17 — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): URL search path and parent constructor.
- [Java SE 17 — Class.getClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getClassLoader()): defining loader identity.
- [Java SE 17 — Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): transformer, bootstrap/system loader JAR search append, and retransform/redefine capability.
- [Java SE 17 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): transformer callback and classfile output rules.
- [Java SE 17 — java.lang.instrument](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): `premain`, `-javaagent`, helper bootstrap constraints.
- [Java SE 17 — Method.invoke](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#invoke(java.lang.Object,java.lang.Object...)): `InvocationTargetException` and cause.
- [JVMS 17 — Loading, Linking and Initialization](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): runtime class identity, loader constraints, resolution, and linkage.
