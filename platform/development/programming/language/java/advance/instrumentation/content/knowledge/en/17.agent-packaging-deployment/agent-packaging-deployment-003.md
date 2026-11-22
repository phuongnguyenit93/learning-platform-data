# Agent Bytecode Version, Helper Bytecode Version, and Target Application Version

A Java instrumentation agent can run properly on a development machine yet fail to start in production, or the agent starts successfully while the helper call just injected into the application fails at execution time. A common cause is **three groups of class files built with three different Java levels**:

1. **Agent bytecode:** the classes of `Premain-Class`/`Agent-Class`, transformers, parsers, exporters, and dependencies loaded by the agent.
2. **Helper bytecode:** `Probe`, `Bridge`, `Advice`, or logging/metrics helper classes that the agent must load, sometimes placed on the classpath/bootstrap so application bytecode can call them.
3. **Target application bytecode:** class files provided by the application and libraries, **plus** class files that the transformer generates or replaces before the JVM defines/redefines/retransforms the class.

These three levels **do not have to be equal**, but **every class actually loaded by the JVM must have a bytecode format and API compatible with the running JVM itself**. A Java 17 agent can instrument a Java 21 application on a Java 21 JVM if the agent/toolkit can handle Java 21 classfiles; however, a helper compiled for Java 21 cannot be loaded by a Java 17 JVM merely because the main agent was compiled for Java 17. Nor can you turn a Java 21 application into a Java 17 application by changing a couple of bytes in the classfile header.

This lesson belongs to the **Packaging and Deployment** group of Java Advance – instrumentation. The goal is to design a clear compatibility matrix, know how to inspect `major_version`/`minor_version`, use `javac --release` properly, separate agent/helper/app artifacts, understand at which stage `UnsupportedClassVersionError` occurs, verify the bytecode returned by a transformer, and organize the CI/deployment pipeline so that wrong-version artifacts are not shipped to the target JVM.

**Hands-on lab executed:** a startup Java agent and a helper JAR compiled on Java 17, with the application built for Java 17 or 21; tested **successfully on JDK 17/JDK 21** and reproduced three types of incompatibility errors when attempting to run bytecode 65 (Java 21) on JDK 17. All required source code, commands, and outputs are included in this lesson. Results on other JVMs may have slightly different stack traces/startup logs, but the nature of version errors still follows the classfile specification.

## 1. Three Classfile Versions Are Three Independent Conditions

Let's distinguish **compilation toolchain**, **classfile major version**, and **actual Java runtime**:

~~~text
Agent source + agent dependencies
        |
        +-- javac --release 17 --> agent17.jar (class major 61)
        |
Helper source + helper dependencies
        |
        +-- javac --release 17 --> helper17.jar (class major 61)
        |
App source + app dependencies
        |
        +-- javac --release 21 --> app21/ (class major 65)
                                         |
                                         v
                                  Java 21 JVM
                                  loads agent 61
                                  loads helper 61
                                  loads app 65
                                  --> can run
~~~

A Java 21 JVM knows how to read major 61 and major 65 according to its classfile compatibility. The agent and the application do not need to share the same `major_version`. What is **mandatory** is that each loaded classfile conforms to a format supported by the JVM, and in addition, API references, class loader/module access, and other runtime conditions must resolve successfully.

Conversely:

~~~text
agent17.jar (major 61)   -> Java 17 JVM: OK
helper21.jar (major 65)  -> Java 17 JVM: CANNOT BE LOADED
app17/ (major 61)        -> Java 17 JVM: OK if helper does not cause an error

Result: agent can start premain, then helper linking fails.
~~~

Therefore, concluding that "the agent supports Java 17" cannot be based **solely** on `Agent.class`. You must check **all class files that could be loaded by a Java 17 JVM**: nested classes, bootstrap helpers, bytecode libraries, companion libraries, versions inside Multi-Release JARs, and any dynamically generated classes.

### 1.1. Do Not Confuse Four Types of "Version"

| Term | Meaning | Example |
| --- | --- | --- |
| **Build JDK** | Which JDK is running `javac`, `jar`, Gradle/Maven | Using JDK 24 to build |
| **`--release`** | Language rules, public platform API, and classfile target used during compilation | `javac --release 17` |
| **Classfile major/minor** | Version stored inside each `.class`; checked by the JVM when loading | Java 17: `61.0` |
| **Runtime JDK/JVM** | The virtual machine actually running the application/agent process | `java -version` = 17, 21, 24 |

A JDK 24 compiler using `--release 17` can produce class major 61. That does **not** mean the Java 24 runtime is replaced with Java 17. And building with JDK 24 does **not** automatically make classes major 68 if the project has properly configured `--release 17`.

## 2. Which Major Version Corresponds to Which Java Release?

According to the Java Virtual Machine Specification, a classfile header contains the magic number, minor version, and major version:

~~~text
Byte offset (0-based):
0..3 : magic         0xCAFEBABE
4..5 : minor_version (unsigned 16-bit, big-endian)
6..7 : major_version (unsigned 16-bit, big-endian)
8..  : constant_pool_count, constant pool, other components
~~~

Some commonly used milestones:

| Java release | Classfile major | Typical major/minor |
| --- | ---: | --- |
| Java 8 | 52 | 52.0 |
| Java 11 | 55 | 55.0 |
| Java 17 | 61 | 61.0 |
| Java 21 | 65 | 65.0 |
| Java 22 | 66 | 66.0 |
| Java 23 | 67 | 67.0 |
| Java 24 | 68 | 68.0 |
| Java 25 | 69 | 69.0 |
| Java 26 | 70 | 70.0 |

These milestones are for **interpreting bytecode**, not a guarantee that every program from an older Java release will run 100% on a newer JVM. The binary format may be supported by the newer JVM, but changed/removed APIs, reflection encapsulation, the module system, dependencies, or JNI can still cause the application to fail.

For Java SE 12 and later, minor `65535` indicates a classfile that **depends on preview features of the corresponding release**. For example, `65.65535` is a Java 21 preview classfile: it must run on **Java 21** with `--enable-preview`; you must not assume Java 22/24 will load it just because it supports major 65. Passing `--enable-preview` on a different JVM release does not make old preview bytecode compatible either.

### 2.1. Newer JVMs Generally Support Older Classfiles; the Reverse Is Not True

JDK 21 supports classfile major 61. However, JDK 17 does not understand major 65. Typical result:

~~~text
java.lang.UnsupportedClassVersionError:
  ... class file version 65.0,
  this version of the Java Runtime only recognizes
  class file versions up to 61.0
~~~

This is a **shortened summary of the message**, not a requirement that the stack trace match verbatim across all JVMs. You should not fix this by changing the build `JAVA_HOME` while forgetting to check the production runtime, or by editing a `java.version` string in a manifest.

Ask: **which class being loaded has a higher major version than the JVM?** That class could be the agent, helper, main app, a transitive library, runtime-generated bytecode, or a higher-versioned entry selected from a JAR.

### 2.2. Checking Major and Minor Versions with `javap`

Once you have the class files:

~~~bash
javap -verbose agent17/agent/VersionAgent.class
javap -verbose helper17/helper/Probe.class
javap -verbose app21/demo/Target.class
~~~

In the output, look for `minor version` and `major version`. With the build commands in section 6, the relevant results are:

~~~text
agent17/agent/VersionAgent.class -> major version: 61
helper17/helper/Probe.class     -> major version: 61
app21/demo/Target.class        -> major version: 65
~~~

This is a **summary of the results**, not the full verbatim output of `javap -verbose`. To inspect classes inside a JAR, you can use `javap -verbose -classpath agent17.jar agent.VersionAgent` and `javap -verbose -classpath helper17.jar helper.Probe`. When a class has multiple variants in a Multi-Release JAR, you must determine the **entry actually selected** by the runtime, not guess based on a class with the same name under `META-INF/versions`.

## 3. `javac --release` Differs from `--source` / `--target`

A safe build targeting Java 17:

~~~bash
javac --release 17 -d out src/demo/Main.java
~~~

`--release 17` means **three things at once**: use the corresponding language rules, emit class files targeting Java 17, and **check against the public platform APIs available in Java 17**. This is usually the preferred choice when using a newer JDK to build code that must run on an older JVM.

A setup with only:

~~~bash
javac --source 17 --target 17 -d out src/demo/Main.java
~~~

can produce major 61, but **does not automatically guarantee** that the code is checked against APIs introduced after Java 17 if the compiler uses the newer JDK's platform classes without configuring the corresponding target platform. Therefore, seeing `major=61` alone is not enough to confirm Java API compatibility. `--release` handles standard platform APIs much more reliably.

**Limitations of `--release`:** it does not check the bytecode/API compatibility of **every third-party JAR**; if a dependency was built for Java 21, the compiler might refuse to load it or a code path might only fail at runtime. Nor does it verify the class loader/module graph, JNI ABI, or reflection. You must inventory dependencies and test on the **actual minimum JVM**.

### 3.1. Two Different Kinds of Errors When Trying to Use a New API

For example, an agent that only uses `java.lang.instrument`, `Path.of`, and `JarFile`—all of which exist in Java 17—fits `--release 17`.

However, if the agent source imports a new standard API available only since JDK 24, such as `java.lang.classfile.ClassFile`:

~~~java
// Just a snippet illustrating an API not available on JDK 17.
import java.lang.classfile.ClassFile;
~~~

then a `javac --release 17` build cannot succeed: that API did not exist in Java 17. **Do not** compile the agent with JDK 24, keep the JAR named `agent17.jar`, and assume it will run on Java 17. If the tool needs the standard JDK 24 Class-File API **inside the target JVM**, the target JVM must also provide that API. For Java 17, consider a compatible bytecode library or perform transformations **offline on a newer JVM/toolchain and then distribute verified classfiles targeting 17**.

Similarly, `--release 17` does not allow using a Java 21 language feature that requires Java 21 syntax. You must decide the minimum runtime for **each artifact**, rather than picking a single setting for the entire repository.

## 4. Minimum Level of the Agent and Libraries Inside the Agent

A Java agent starts with:

~~~bash
java -javaagent:agent17.jar=helper17.jar -cp app17 demo.Main
~~~

The JVM loads the class specified in the `Premain-Class` manifest attribute and invokes:

~~~java
public static void premain(String options, Instrumentation inst)
~~~

If `agent.VersionAgent` was compiled to major 65 while the runtime is Java 17 (which only accepts up to 61), the JVM can **abort before invoking `premain` and before the application's `main`**. This is not a bug in transformer logic, because the agent class itself has not even loaded successfully.

You must check:

- The `Premain-Class` and all nested/anonymous classes such as `VersionAgent$1.class`.
- All dependencies actually loaded by the agent: parsers, exporters, metrics APIs, logging frameworks, bytecode toolkits.
- Whether the JDK APIs used by the agent exist in the minimum runtime.
- Package/loader/module access of the agent in Java 9+.
- Whether preview features or MR-JAR entries with a version higher than the runtime are used.
- Whether a startup agent or dynamic attach agent has the corresponding manifest entry (`Premain-Class` vs `Agent-Class`).

**Important:** an agent class with major 61 may load on Java 17, but if it executes a method referencing a new API only present in Java 21, the result can be `NoSuchMethodError` or another linkage error. A version header **does not replace** checking platform APIs and dependency ABI.

### 4.1. Why the JAR Manifest Is Not Where You "Set the Java Version"

The `Premain-Class` manifest attribute only tells the JVM which class to load to invoke `premain`. Attributes like `Can-Retransform-Classes: true` or `Can-Redefine-Classes: true` declare capabilities the agent wants to use; they do **not** lower the bytecode target. The `Multi-Release: true` attribute allows selecting class entries by runtime when properly structured, but it does **not** make a major 65 class in the root JAR run on Java 17.

An artifact label like `agent-jdk17.jar`, an `Implementation-Version` field, or build metadata is distribution information, **not** a substitute for the JVM's class-file format check.

## 5. Helper Bytecode: A Failure Point Often Discovered Late

A transformer can inject an instruction equivalent to:

~~~text
invokestatic helper/Probe.state:()Ljava/lang/String;
~~~

If the instrumented class executes this instruction, the JVM must resolve `helper.Probe` and the `state()` method in the appropriate loader/module. When `helper/Probe.class` has major 65 but the JVM is Java 17, the result can be `UnsupportedClassVersionError` **at the time the helper is loaded**; that moment can be much later than startup if the helper is only referenced on a rarely executed code path.

Beyond the version header, helpers have their own constraints:

1. **Visibility:** the loader of the class containing the invocation must be able to find the helper; the agent being able to load the helper does not automatically prove the app/child/bootstrap loader can see it.
2. **Package/module:** readable/exported/open must match the kind of reference and reflective access; a correct `ClassDesc` or class name does not grant permission by itself.
3. **Method contract:** name, descriptor, and static/instance kind must match. Errors can be `NoSuchMethodError`/`IncompatibleClassChangeError`.
4. **Dependencies:** a major 61 helper that calls a major 65 dependency can still fail on Java 17.
5. **Deployment location:** `appendToSystemClassLoaderSearch` adds the helper JAR to the system loader search; `appendToBootstrapClassLoaderSearch` is a separate mechanism for bootstrap classes—they are not interchangeable.
6. **Phase/class loading:** if the helper triggers loading of a complex framework right inside `ClassFileTransformer.transform`, there is a risk of reentrancy, recursion, and overhead; preinitialize and filter carefully.

This leads to a CI requirement: **build the helper at a minimum runtime compatible with the target classes from which it may be called**, while not overlooking that all of the helper's dependencies must also stay within the set of APIs/bytecode that JVM understands.

### 5.1. A "Java 17 Helper" Is Not Necessarily Safe for Java 17

For example, `helper/Probe.class` is major 61, but it calls `thirdparty.Library.someMethod()` from a JAR whose `Library.class` is major 65. If that code path is executed on Java 17, the JVM cannot load the dependency. Worse, a major 61 classfile can still link to a newer JDK method if the build bypassed platform API checks. Therefore, you must inspect the **closure of the dependency graph** and run integration tests on the lowest supported JDK.

For helpers placed in the **bootstrap class loader**, dependency visibility is even stricter: supporting classes loaded by bootstrap must only link against classes that the bootstrap loader can define. Do not put an entire logging framework that depends on the system/app loader into bootstrap and assume matching the Java version is enough.

## 6. Runnable Demo: Java 17 Agent, Java 17/21 Helper, and Java 17/21 Application

The experiment has four source files and one manifest. We intentionally **keep the Java source code identical** across builds of different versions, changing only `--release`. That way, when an error case occurs, the clearly observable cause is **classfile major**, not different business logic.

### 6.1. Directory Structure

~~~text
version-demo/
  helper/
    Probe.java
  agent/
    VersionAgent.java
  demo/
    Target.java
    Main.java
  MANIFEST.MF

  helper17/   (build output)
  helper21/   (build output)
  agent17/    (build output)
  agent21/    (build output)
  app17/      (build output)
  app21/      (build output)

  helper17.jar  helper21.jar
  agent17.jar   agent21.jar
~~~

Names like `helper17`/`app21` are output directories, **not** Java package names. Place the source files at the exact paths shown in the diagram.

### 6.2. `helper/Probe.java`

~~~java
package helper;

public final class Probe {
    public static String state() {
        return "ready";
    }
}
~~~

`Probe` is a simple helper with no dependencies outside standard Java. Use this same source to compile both class major 61 and 65 builds.

### 6.3. `agent/VersionAgent.java`

~~~java
package agent;

import helper.Probe;
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.nio.file.Path;
import java.security.ProtectionDomain;
import java.util.jar.JarFile;

public final class VersionAgent {
    public static void premain(String options, Instrumentation inst)
            throws Exception {

        try (JarFile file = new JarFile(Path.of(options).toFile())) {
            inst.appendToSystemClassLoaderSearch(file);
        }

        System.out.println("AGENT=started");
        System.out.println("HELPER=" + Probe.state());

        inst.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(
                    ClassLoader loader,
                    String name,
                    Class<?> redefining,
                    ProtectionDomain domain,
                    byte[] data) {

                if ("demo/Target".equals(name)) {
                    int major = ((data[6] & 0xff) << 8)
                            | (data[7] & 0xff);
                    System.out.println("TARGET_MAJOR=" + major);
                }
                return null;
            }
        });
    }
}
~~~

**Part-by-part explanation:**

1. `VersionAgent` has `public static premain(String, Instrumentation)`; the JVM calls it before `demo.Main.main` when `-javaagent` is present.
2. `options` is the string after `=` in `-javaagent:agent17.jar=helper17.jar`. The demo requires this value to be an existing JAR path; a production agent must validate null/path.
3. `new JarFile(...); inst.appendToSystemClassLoaderSearch(file)` adds the helper JAR to the system loader search before `Probe.state()` is called. The helper is not on `-cp app17` or `-cp app21`.
4. `AGENT=started` is printed before resolving `Probe`; if the helper version is too new, you can observe that AGENT started and then failed.
5. `ClassFileTransformer` has had the five-parameter overload for a long time; in Java 9+, the overload taking an additional `Module` has a default implementation that delegates to this overload. Choosing the five-parameter form keeps the code compatible with Java 17 and easy to read.
6. `"demo/Target"` is the JVM internal binary name (with `/`); the transformer prints only when it sees the exact target class. `data` contains the classfile bytes at the current transformer step and **must not be modified in place**.
7. `data[6]`, `data[7]` are the two bytes of `major_version`, unsigned big-endian. `& 0xff` avoids Java's signed-byte issue; shifting left by 8 bits and ORing yields the exact major version.
8. `return null` means the transformer **does not modify bytecode**. The demo illustrates receiving bytecode from a different application version; it is **not** a tool that downgrades classfiles or injects helpers into Target.
9. Using `System.out.println` inside a callback is only for a small-class experiment; production instrumentation must avoid synchronous logging on the hot path and manage errors/metrics separately.
10. `Agent.class` and the helper load in the system loader under a standard launcher configuration. Custom loaders/named modules have additional rules; the demo does not prove that every loader sees the helper after appending.

**Limitations:** the transformer receives data provided by the JVM; if another transformer ran earlier, the bytes may already have been modified. Printing the major version only measures **the classfile at the callback**; it does not prove a tool can fully parse every classfile version or rewrite frames/constant pools correctly.

### 6.4. `demo/Target.java`

~~~java
package demo;

public final class Target {
    public static String value() {
        return "hello";
    }
}
~~~

### 6.5. `demo/Main.java`

~~~java
package demo;

public final class Main {
    public static void main(String[] args) {
        System.out.println("APP=" + Target.value());
    }
}
~~~

`Main` references `Target.value()`, causing the JVM to load `demo.Target` when the program runs. The comparison target is Target's header, not performance or the correctness of a bytecode injection.

### 6.6. `MANIFEST.MF`

~~~text
Manifest-Version: 1.0
Premain-Class: agent.VersionAgent

~~~

Keep the trailing newline and blank line. Because redefine/retransform is not used, the demo **does not need** `Can-Redefine-Classes` or `Can-Retransform-Classes`. Only `Premain-Class` is needed so the JVM knows which class contains the entrypoint.

### 6.7. Building with a JDK 21 or Newer Compiler

Use a `javac` that supports both `--release 17` and `--release 21`, such as `javac` from JDK 21/24. From the `version-demo/` directory:

~~~bash
javac --release 17 -d helper17 helper/Probe.java
javac --release 21 -d helper21 helper/Probe.java

javac --release 17 -cp helper17 -d agent17 agent/VersionAgent.java
javac --release 21 -cp helper17 -d agent21 agent/VersionAgent.java

javac --release 17 -d app17 demo/Target.java demo/Main.java
javac --release 21 -d app21 demo/Target.java demo/Main.java

jar --create --file helper17.jar -C helper17 .
jar --create --file helper21.jar -C helper21 .
jar --create --file agent17.jar --manifest MANIFEST.MF -C agent17 .
jar --create --file agent21.jar --manifest MANIFEST.MF -C agent21 .
~~~

**Important note on the agent compile step:** both agent builds are compiled with `-cp helper17`. The `agent21` build is just a major 65 class variant due to `--release 21`, while Probe's public interface and source code remain unchanged. At runtime, the `-javaagent` option determines whether `helper17.jar` or `helper21.jar` is loaded, not the classpath used during compilation.

Packaging `-C agent17 .` is necessary because the agent source contains an anonymous transformer, so the compiler generates an extra class `agent/VersionAgent$1.class`. If the JAR only contains `VersionAgent.class` and omits the anonymous class, you can hit `NoClassDefFoundError` even when the main class's major version is completely compatible.

### 6.8. Checking Actual Major Versions After Build

Run:

~~~bash
javap -verbose agent17/agent/VersionAgent.class
javap -verbose agent21/agent/VersionAgent.class
javap -verbose helper17/helper/Probe.class
javap -verbose helper21/helper/Probe.class
javap -verbose app17/demo/Target.class
javap -verbose app21/demo/Target.class
~~~

You should see:

~~~text
agent17/agent/VersionAgent.class = major 61
agent21/agent/VersionAgent.class = major 65
helper17/helper/Probe.class     = major 61
helper21/helper/Probe.class     = major 65
app17/demo/Target.class        = major 61
app21/demo/Target.class        = major 65
~~~

These six results **were verified by directly reading the 8-byte header of the generated class files**. `javap` displays them as `major version: 61` or `major version: 65`. Reading header bytes is useful when inventorying thousands of JAR entries, though it does not replace a class-file parser for bytecode modification tasks.

## 7. Two Successful Run Matrices

To test on two JVMs, **select a specific Java executable** instead of relying on PATH. On Linux/macOS there are typically `$JAVA17_HOME/bin/java` and `$JAVA21_HOME/bin/java` if the environment names variables that way. On Windows, use paths to `java.exe` inside the two JDK installations, such as PowerShell variables `$java17`/`$java21` pointing to the respective executables. Do not hardcode the lesson author's machine paths as default paths for learners.

If a machine only has one JDK, you can still build the classfiles and inspect major versions, but proving runtime mismatches requires JVMs at the target versions being tested.

### 7.1. Success Case A — Java 17 JVM

Using **java** from JDK 17:

~~~bash
java -javaagent:agent17.jar=helper17.jar -cp app17 demo.Main
~~~

**Exact standard output verified on Corretto 17:**

~~~text
AGENT=started
HELPER=ready
TARGET_MAJOR=61
APP=hello
~~~

Stages:

1. Java 17 JVM loads agent class major 61.
2. Agent appends helper JAR and calls helper major 61.
3. Transformer receives `demo/Target` major 61, prints the info, and returns `null`.
4. Application Java code runs and prints `APP=hello`.

Each loaded class belongs to the set of classfile versions supported by the Java 17 JVM; the APIs in the demo also exist in Java 17.

### 7.2. Success Case B — Java 21 JVM

Using **java** from JDK 21, keeping the Java 17 agent/helper while upgrading the application:

~~~bash
java -javaagent:agent17.jar=helper17.jar -cp app21 demo.Main
~~~

**Exact standard output verified on Microsoft OpenJDK 21:**

~~~text
AGENT=started
HELPER=ready
TARGET_MAJOR=65
APP=hello
~~~

This is a key case: **agent bytecode major 65 is not required to instrument an application with major 65**. Agent 61 works because the Java 21 JVM loads classfile major 61 and helper major 61, while the simple callback understands the common header of classfile major 65. For a **transformer that actually rewrites code**, you must still ensure the parser/builder supports Java 21 classfile features and attributes; compiling the agent on Java 17 alone does not prove that.

### 7.3. Compact Compatibility Matrix

| Runtime JVM | Agent major | Helper major | App major | Demo result |
| --- | ---: | ---: | ---: | --- |
| Java 17 | 61 | 61 | 61 | **PASS** |
| Java 21 | 61 | 61 | 65 | **PASS** |
| Java 17 | 61 | 61 | 65 | **FAIL**: app `Main` cannot be loaded |
| Java 17 | 65 | 61 | 61 | **FAIL**: agent cannot be loaded |
| Java 17 | 61 | 65 | 61 | **FAIL**: helper cannot be loaded |
| Java 21 | 65 | 61 | 61 | Classfile versions **allowed**; still needs runtime tests to claim functional compatibility |

This matrix describes **the exact source/JARs of the demo**. In a real application, there are also dependencies, generated proxies, preview features, loader/module resolution, and Java API linkage. Do not use a table of major numbers to replace full integration tests.

## 8. Three Real Errors: Application, Agent, and Helper

The following cases use the `java` executable **of Java 17**. Each run is a fresh JVM so that a previous error does not affect the next test.

### 8.1. Java 21 App on Java 17 JVM

~~~bash
java -javaagent:agent17.jar=helper17.jar -cp app21 demo.Main
~~~

The agent/helper lines appeared:

~~~text
AGENT=started
HELPER=ready
~~~

Then the process failed with the main error info (abbreviated from the test run):

~~~text
java.lang.UnsupportedClassVersionError: demo/Main
class file version 65.0
this version of the Java Runtime only recognizes class file versions up to 61.0
~~~

Because `demo.Main` is already major 65, the JVM cannot load the **main class**. Therefore `Target` is never observed by the transformer, and there is no `TARGET_MAJOR=65`/`APP=hello` in this failure case. Agent startup can succeed **while the application still fails to start**, because the application version is too high for the runtime.

**How to handle:** run app21 on Java 21+ if the environment supports it; or **recompile the app with `--release 17`**, adjust incompatible APIs/dependencies/features, and test on JDK 17. Do not merely change the major header from 65 to 61.

### 8.2. Java 21 Agent on Java 17 JVM

~~~bash
java -javaagent:agent21.jar=helper17.jar -cp app17 demo.Main
~~~

Main error info observed:

~~~text
java.lang.UnsupportedClassVersionError: agent/VersionAgent
class file version 65.0
this version of the Java Runtime only recognizes class file versions up to 61.0
~~~

In this case the JVM cannot load the `Premain-Class`, so **`premain` does not start**; the application does not run either. Some JVMs may print additional diagnostics when the instrumentation process fails/aborts before `main`. Do not mistake this for a helper JAR or `JarFile` error.

**How to handle:** release agent root/classes/dependencies whose classfiles and APIs match Java 17; in the demo, use `agent17.jar`. You must check anonymous/nested classes inside the agent JAR as well, not just the main entry file.

### 8.3. Java 21 Helper on Java 17 JVM

~~~bash
java -javaagent:agent17.jar=helper21.jar -cp app17 demo.Main
~~~

In the test, the agent printed:

~~~text
AGENT=started
~~~

Then the main error:

~~~text
Caused by: java.lang.UnsupportedClassVersionError: helper/Probe
class file version 65.0
this version of the Java Runtime only recognizes class file versions up to 61.0
~~~

Agent major 61 loads fine. However, when `premain` calls `Probe.state()` after appending the JAR, helper class major 65 cannot be loaded. `premain` does not complete, and the JVM aborts before the application. This demonstrates that **an incompatible helper JAR can break startup even when the main agent JAR has the right version**.

If the helper is only referenced after an instrumented method runs, the same error can appear **later**, not necessarily in `premain`. The timing depends on when class resolution and execution actually need the helper.

### 8.4. Do Not Fix the Wrong Layer

| Which class name appears in the error? | Layer to check first | Priority action |
| --- | --- | --- |
| `agent/VersionAgent` | Agent bytecode/JAR | Inspect `Premain-Class` and all agent dependencies |
| `helper/Probe` | Helper bytecode/JAR | Inspect helper and the class loader location that actually loads it |
| `demo/Main` or `demo/Target` | Application bytecode/JAR | Inspect app artifact, runtime JDK, and `--release` |
| Parser throws an unrecognized classfile error | Transformer/toolkit | Check whether the parser library supports that classfile version/features |
| JVM throws `VerifyError` after transform | Bytecode output | Check frames, max stack, descriptors, and classfile output |
| `NoSuchMethodError`/`NoClassDefFoundError` | API/linkage/dependency | Check JDK APIs and runtime libraries, loader/module access |

`UnsupportedClassVersionError` refers to **the file currently being loaded by the JVM**. It does not automatically tell you which JAR that file came from if multiple class loaders/JARs have duplicate classes; you must cross-check the source/layer/class loader and the actual artifact list.

## 9. Three Compatibility Thresholds That Must Be Managed Separately

A clear release design:

~~~text
minimumRuntimeAgent       = 17
minimumRuntimeHelper      = 17
minimumRuntimeApplication = 21  (for the app21 build)
effectiveRuntimeMinimum   = 21  (for the app21 + agent17 + helper17 set)
~~~

This is a **control model** based on the demo's bytecode/APIs. There is no single JVM field that recomputes this number for you in place of dependency testing.

In a real project, a system may have multiple groups:

- **Agent startup classes** must be compatible with the JVM before `premain` can run.
- **Agent transformer implementation** may use a parser that can read multiple classfile versions; parser compatibility with target bytecode must be tested.
- **Helper injected into the app** must be compatible with the JVM and accessible from the app's defining loader/module.
- **Generated classes** produced by the transformer must have valid classfile major/minor and attributes for the target JVM, and every invoked helper must link.
- **App/library classes** may be produced by the compiler at different Java levels; the runtime only loads classes actually referenced along execution paths, so production tests must cover those paths.
- **Multi-Release JAR variants** may provide separate implementations for Java 17/21; the variant selection path must be tested.

Therefore, a "minimum supported JDK" for **the whole product** is usually the lowest level that satisfies every component that actually needs to run, not the smallest version written in a single manifest.

## 10. Transformer Output Must Be Compatible with the Target JVM, Not Just Input

When the JVM loads a class, `ClassFileTransformer.transform` receives `classfileBuffer` and can:

- Return `null`: do not transform the bytes in this pass.
- Return a new `byte[]`: the transformed classfile must be well-formed and valid for the JVM to verify/define/redefine/retransform.

A serious bug is when a parser/builder automatically emits a **classfile major newer than the runtime**. For example:

~~~text
Input app major 61 (Java 17)
  -> transformer uses a library that builds classfile with default major 65
  -> output major 65
  -> Java 17 JVM cannot define the class
~~~

This does not become safe just because `VersionAgent.class` is still major 61. The transformer output is **a new classfile** that the JVM must understand.

### 10.1. Invariants to Check in the Pipeline

For instrumentation that **only injects hooks** and has no reason to bump the classfile version:

1. **Read classfile major/minor from the input**; do not assume every class in the JVM has the same major version.
2. **Verify that the parser supports the target classfile**: Java 21 has records, sealed classes, bytecode attributes, and language features different from older classfiles; an older library may fail to parse them properly.
3. **Keep a valid classfile major** for the runtime, typically preserving the input's major/minor when generating insert-only output.
4. **Emit valid frames/StackMapTable/constant pool/attributes** after adding instructions.
5. **Do not introduce opcodes or class attributes that only have meaning in a different classfile version** rejected by the runtime.
6. **Do not create references to unresolvable helpers/APIs** or ones inaccessible through the real loader/module.
7. **Verify output** and run on the lowest supported JVM, including exception paths, constructors, concurrency, and multiple class loaders.
8. When using redefine/retransform, obey schema-change restrictions; do not add fields/methods and assume you are only instrumenting a method body.

If a library emits Java 21 bytecode by default, set an explicit class writer target appropriate for Java 17 when genuinely supported. However, **lowering the major number does not automatically make a new class's semantics compatible with Java 17** if it still contains structures, instructions, or API references only available in newer Java versions.

### 10.2. Not Every Java 21 Feature Can Be Downgraded

`--release 17` requires source compatible with Java 17 language/APIs. A class compiled for Java 21 may use features/attributes that Java 17 does not understand. To support Java 17, you must **design and compile an implementation with semantics suitable for Java 17**, not "fake" bytecode 65 into 61.

If an application uses a JDK API added in Java 21, a transformer cannot automatically translate that call into an API present in Java 17. A true bytecode downgrade is a semantics/API/metadata transformation problem much larger than changing two version bytes.

## 11. Preview Classfiles and Java Releases Are Tightly Coupled

A preview-dependent classfile can have a version like:

~~~text
major = 65  (Java 21)
minor = 65535 (preview)
~~~

Main rule: a preview classfile of **Java N** can only be loaded on **Java N** when preview is enabled as supported by the JVM, not on Java N+1. Usually both compiler and runtime need the appropriate `--enable-preview`:

~~~bash
# Example recipe with Java 21 compiler/runtime when source has preview:
javac --enable-preview --release 21 SomePreviewClass.java
java --enable-preview SomePreviewClass
~~~

This is a **configuration recipe**, not a standalone source class example: `SomePreviewClass.java` must actually use a preview feature present in that exact release. Do not mechanically add `--enable-preview` to the entire agent distribution just to fix a major mismatch; it does **not** make Java 17 understand major 65.

A release build targeting multiple JVMs should prefer **stable language features** and classfile minor 0 in common agent/helper code, unless there is a clear reason and a separate preview matrix.

## 12. Multi-Release JARs Help Distribute Multiple Implementations, Without Breaking Major Rules

A Multi-Release JAR (MR-JAR) has in its main manifest:

~~~text
Multi-Release: true
~~~

and can contain:

~~~text
agent.jar
  META-INF/MANIFEST.MF
  helper/Probe.class                       (base, major 61)
  META-INF/versions/21/helper/Probe.class  (Java 21 variant, major <= 65)
~~~

On a runtime supporting MR-JARs, the class loader can select the highest matching versioned entry **not exceeding** the Java runtime feature version, falling back to base. When running on Java 17, the Java 21 entry is not selected; when running on Java 21, the Java 21 entry can be selected. Base classes must still be compatible with the declared minimum runtime.

**Do not mistake `META-INF/versions/21` for classfile major 21:** the number `21` in the path is the **Java SE release**, whereas a Java 21 classfile has major **65**.

Several important constraints:

- `Multi-Release: true` must be set in the main manifest.
- Versioned entries must follow the `META-INF/versions/N` structure with N >= 9.
- `.class` files in entry N must have a major version not exceeding the classfile version for Java N.
- The public/protected API of a variant must be compatible with the base according to the JAR specification rules.
- MR-JARs **are not supported by the bootstrap class loader in the same way** as classpath/modulepath JARs. When appending an MR-JAR to the boot classpath, the JAR is treated as a regular JAR according to the JAR specification; you must test separately and not assume every helper variant will be selected automatically.
- If you want different Java 17/21 behavior, you must build/test **each variant** on the corresponding JVM.
- An MR-JAR does not fix an incompatible classfile in the root, does not fix parser/toolkit bugs, and does not open modules/access automatically.

In an agent, MR-JARs can be useful for distributing API-specific adapter code, but you must pay attention to how the JVM loads **agent classes**, helper classes, and bootstrap classes. Do not bundle all variants into one JAR and assume every loader will pick the right one.

## 13. Build Pipeline: Manage Agent/Helper/App as Three Products

A mono-repo might consist of three subprojects:

~~~text
root/
  agent-core/        -> min Java 17
  helper-runtime/    -> min Java 17
  sample-app/        -> Java 17 or Java 21
~~~

Each subproject needs to declare its own bytecode/API level. If using the Maven Compiler Plugin, you can set it in **each module's** `pom.xml`:

~~~xml
<properties>
  <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

A Java 21-only app can use `21` in the app's module. This is an **illustrative configuration snippet**, not a standalone Maven POM; the project still needs plugins, dependencies, packaging, and a proper agent JAR manifest.

With Gradle Groovy DSL in the agent/helper project:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

App21 uses `options.release = 21`. Do not assume that a Gradle/Maven toolchain running on Java 21/24 will automatically produce the right source/target version; the project must explicitly define and verify the actual output.

**Lock down the artifact contract:**

- `agent17.jar` contains all agent classes at major <= 61 (except managed MR-JAR variants).
- `helper17.jar` contains helper classes at major <= 61, with all transitive dependencies suitable for the target JVM.
- `app21` may have major 65 and is only deployed on Java 21+.
- If transformer output needs to run on Java 17, it must be a classfile accepted by the Java 17 verifier/runtime.
- Build metadata records the minimum Java release, helper loader type, and list of supported JDKs, not just the file name.

### 13.1. Inventory Nested Classes and Dependencies as Well

`javap -verbose` on a single class is a starting point, not enough for a distribution. Inventory:

~~~bash
jar --list --file agent17.jar
jar --list --file helper17.jar
~~~

Check all `.class` entries, including anonymous/nested classes and dependencies shaded into the JAR. `VersionAgent$1.class` must be accounted for; a high-level class hidden inside the JAR might only be loaded when a feature is enabled.

For transitive JARs not packaged into the agent, check dependency versions across the build graph. `jdeps` can help identify package/module/API dependencies and `--multi-release` when analyzing MR-JARs, though it cannot replace integration tests on the real runtime and class-loader topology.

### 13.2. Why Testing Only on the Latest JDK Is Not Enough

JDK 24 can load both major 61 and 65, so both class builds can run successfully there. That **does not prove** major 65 agent/helper parts are compatible with JDK 17. You must test on the **minimum supported JDK**; if supporting both Java 17 and 21, test at least:

- JVM 17 + agent17 + helper17 + app17.
- JVM 21 + agent17 + helper17 + app21.
- JVM 17 + agent17 + helper21 + app17 must fail as expected for a negative test.
- JVM 17 + agent21 + helper17 + app17 must fail before premain.
- JVM 17 + agent17 + helper17 + app21 must fail due to app major 65.
- JVM 21 + real transformer processing app21 class files, ensuring output passes the verifier and behaves correctly.
- If preview/MR-JAR is present, also run each supported variant/release.

**Use each Java version as a real test environment**, rather than just invoking `javac --release` and testing solely on JDK 24.

## 14. Bytecode Toolkit Compatibility

An agent may be compiled for Java 17 yet use a parser/rewriter library that does not recognize Java 21 classfiles. For example, an older library version might report "unsupported class file major version 65" when attempting to parse input. This is **different** from `UnsupportedClassVersionError` thrown by the JVM when loading the library class itself:

- **Parser library does not support 65:** a Java 21 JVM can load the agent/library successfully, but the agent explicitly throws an exception when reading Target.class major 65.
- **Library.class itself is major 65 on JVM 17:** the JVM throws `UnsupportedClassVersionError` before the parser even has a chance to run.
- **Invalid transformer output:** the JVM can throw `ClassFormatError`/`VerifyError`/linkage errors when defining the class after transformation.
- **Missing runtime Java API:** you can hit `NoSuchMethodError`, `NoClassDefFoundError`, or other errors even when the class major version is valid.

Proper management:

1. Identify the **range of classfile versions** supported by the transformation library, not just the library's minimum Java runtime.
2. Pin and test the bytecode toolkit version on classfiles containing real records/sealed classes/lambdas/attributes.
3. If an unsupported classfile version is encountered, apply a clear policy: skip transformation and return `null` if telemetry is optional; or fail in a controlled manner if transformation is mandatory.
4. Do not modify input or output headers to "get past" the parser; fix it with an updated toolkit or an appropriate pipeline.
5. Also evaluate application bytecode **after multiple transformers run together**: the input a transformer receives may have already passed through an earlier stage.

## 15. Other Errors That Should Not Be Misattributed to Bytecode Version

| Error | Priority question |
| --- | --- |
| `UnsupportedClassVersionError` | Which class has a higher/preview major/minor compared to the JVM? |
| `NoClassDefFoundError` | Does the class/dependency exist in this loader/module; what is the underlying root cause? |
| `ClassNotFoundException` | Could the ClassLoader not find the requested class; are search path/module correct? |
| `NoSuchMethodError` | Did the agent/helper compile against an API with that method while the actual runtime class lacks it? |
| `IncompatibleClassChangeError` | Static/instance method, class/interface, or ABI mismatch? |
| `IllegalAccessError` | Package/module/visibility or different loader identity? |
| `ClassFormatError` | Is the structure of classfile output/constant pool/attributes valid? |
| `VerifyError` | Are operand stack, frames, descriptors, and control flow generated by the transformer valid? |
| Other `LinkageError` | Are there duplicate classes, version skew, loader constraints, or changed definitions? |
| `IllegalClassFormatException` from transformer | Parser/transformer reports input classfile is invalid per contract |
| `ExceptionInInitializerError` | Did static initialization of helper/agent/dependency fail? |

A `NoClassDefFoundError` can have a **cause** involving `UnsupportedClassVersionError`. Read both the root cause and the binary class name instead of looking only at the top-level exception.

**Error timing also matters:** before `premain` points toward agent class/manifest; inside `premain` after startup logs points toward helper/dependency; after `main` or on a specific request points toward application/injected helper paths. This is an investigation heuristic, not a replacement for stack traces.

## 16. Multi-JVM Packaging and Deployment

### 16.1. Images/Containers and Service Launchers

Check the **runtime inside the container/service**, rather than inferring from `java -version` on a developer machine. For example, a build image uses JDK 24 while the runtime image contains JRE 17: if the app artifact was compiled to major 65, the runtime environment will still fail.

With multi-stage Docker builds, lock down the pairing:

~~~text
Build stage: JDK 24 + javac --release 17/21 per artifact
Runtime image Java 17: agent17 + helper17 + app17
Runtime image Java 21: agent17 + helper17 + app21
~~~

Do not use a Java 21 dependency in helper17 just because the build stage runs JDK 24. Pin tags/digests of runtime images and run smoke tests on the actual image to be deployed.

### 16.2. Dynamic Agent Attach and Already-Loaded Classes

With dynamic attach, the target JVM is already running with a fixed Java release. `Agent-Class` and the agent's dependencies must be compatible with **that JVM**, even if the tool sending the attach command is run with a newer JDK. You cannot use a newer CLI JDK to "upgrade" the bytecode loading capability of an already-running target JVM.

With retransform/redefine, classfile output is also subject to schema-change restrictions. A Java agent must verify capabilities, `isModifiableClass`, class loader/module, and classfile format before installing new bytes. Do not interpret "agent attached successfully" as "the newest helper/API can run inside an old VM".

### 16.3. Using Bytecode Helpers in System/Bootstrap

If a helper is appended to the system class loader search, a class defined by the bootstrap loader **does not automatically** see the helper. If a bootstrap helper is needed, you must use an appropriate arrangement such as `appendToBootstrapClassLoaderSearch` and restrict the helper's dependencies to classes visible to bootstrap.

In both styles, the helper major version must still be supported by the target JVM. Moving a major 65 file from the system loader to the bootstrap loader on Java 17 does **not** make it valid.

## 17. Pre-Release CI/CD Checklist for Agents

- [ ] Determine the **minimum JVM version** of the environment where the agent will run (not just the build JDK).
- [ ] Determine the target release and check **every** class in the agent, helper, nested classes, shaded JARs, and external dependencies.
- [ ] Use `javac --release N` for sources belonging to minimum release N; check actually used APIs, not just headers.
- [ ] Package the manifest with the right `Premain-Class`/`Agent-Class` for the startup mode, without mixing with Main-Class.
- [ ] Check bytecode major/minor of the root and MR-JAR variants.
- [ ] Test agent + helper + app on the **lowest JDK** and all supported runtimes.
- [ ] Test newer JVMs with newer app classfiles to ensure the transformer understands their format.
- [ ] When a transformer returns a new `byte[]`, verify major/minor, constant pool, frames, method descriptors, and redefinition constraints.
- [ ] Verify class loader/module resolution of the helper at **the exact class containing the hook**.
- [ ] Test rare request paths, lazy loading, and dynamic proxies (not just startup).
- [ ] Test preview features on the exact Java release or avoid using them in common artifacts.
- [ ] Test Multi-Release JARs on each runtime and examine bootstrap helpers separately.
- [ ] Distinguish platform API, binary ABI, compiler config, and classfile format errors.
- [ ] Have a safe rollback plan: revert the artifact/agent version; do not attempt to rewrite headers on production classes.
- [ ] Clearly document classfile version support, runtime support, and parser support in release notes.

## 18. Self-Check Questions

1. Can an agent with `major 61` process an application class with `major 65` on a Java 21 JVM? What conditions beyond major version need testing?
2. Why does `helper major 65` not run on Java 17 even though the agent is `major 61`?
3. What major version does a Java 21 classfile use? What about Java 17 and Java 24?
4. How does using JDK 24 `javac --release 17` differ from running the application on a Java 17 JVM?
5. Does `--source 17 --target 17` guarantee checking against JDK 17 public platform APIs the same way `--release 17` does?
6. Which byte offset in the classfile header holds `major_version`?
7. Why is `& 0xff` needed when reading unsigned bytes using Java `byte`?
8. Does a classfile with `65.65535` run on Java 24 with `--enable-preview`? Why or why not?
9. In the example, what does `AGENT=started` appearing followed by a helper load failure tell you about the failure stage?
10. Why must `VersionAgent$1.class` be packaged and have its classfile version checked separately?
11. If a transformer tool uses a parser that does not yet support major 65, will a Java 21 JVM automatically fix it for the tool?
12. Why is preserving the input major version usually safer than bumping the major version when only injecting hooks?
13. Can a Multi-Release JAR select the Java 21 variant on a Java 17 JVM?
14. Why does an entry `META-INF/versions/21` not mean the classfile major is 21?
15. If a helper is in the unnamed module of the system loader, can every bootstrap/plugin class see it?
16. Why can't an `UnsupportedClassVersionError` of app21 be fixed by changing the `Premain-Class` manifest?
17. In a Docker multi-stage build, which Java version determines whether bytecode can be loaded in production?
18. How do you separate an agent runtime mismatch error from a transformer classfile output error?
19. When bytecode major versions are compatible, why can `NoSuchMethodError`/`IllegalAccessError`/`VerifyError` still occur?
20. What CI matrix would you write for two builds app17/app21 and one agent17/helper17?

## 19. Conclusion

**There are three compatibility layers to account for separately**: agent Java bytecode, helper bytecode, and application/transformer output bytecode. Those layers do not need to be the same version—a Java 17 agent together with a Java 17 helper can work with a Java 21 application on a Java 21 JVM—but **each class loaded by the JVM must fit that runtime itself**, and the entire API/dependency/loader/module chain must link.

`javac --release` is the practical way to build code with a controlled target release; `javap -verbose` and header inspection help detect major/minor versions; testing on the lowest JDK catches real-world failures. Constraints such as preview features, MR-JARs, bytecode toolkit support, helper visibility, and verifier output must be handled individually.

The lesson's experiment reproduces three sources of `UnsupportedClassVersionError`: **app**, **agent**, and **helper**. That is an important diagnostic criterion before broad deployment: identify the exact layer where the error originates and fix the right artifact or runtime, rather than blindly upgrading or downgrading the Java version.

### Official Documentation

- [Java Virtual Machine Specification, Chapter 4 – Class File Format](https://docs.oracle.com/javase/specs/jvms/se24/html/jvms-4.html): `magic`, `major_version`, `minor_version`, and classfile versions.
- [Oracle JDK 17 – javac tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): `--release`, `--source`, `--target`, and platform API restrictions.
- [Oracle JDK 17 – java.lang.instrument](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): `-javaagent`, `Premain-Class`, helper visibility, and startup lifecycle.
- [Oracle JDK 17 – ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): `classfileBuffer`, `transform`, and returning `null` when not modifying bytes.
- [Oracle JDK 17 – Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): appending helper JARs, redefine/retransform, and interaction with class loaders.
- [Oracle JDK 17 – JAR File Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html): `Multi-Release: true`, versioned entries, and class selection rules.
- [Oracle JDK 21 – Preview Features](https://docs.oracle.com/en/java/javase/21/language/preview-language-and-vm-features.html): `--enable-preview` and release binding.
- [Apache Maven Compiler Plugin – Setting --release](https://maven.apache.org/plugins/maven-compiler-plugin-4.x/examples/set-compiler-release.html): configuring release per Maven module.
