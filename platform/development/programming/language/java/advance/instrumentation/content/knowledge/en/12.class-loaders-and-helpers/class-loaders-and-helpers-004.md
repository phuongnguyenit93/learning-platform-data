# `appendToBootstrapClassLoaderSearch` and `Boot-Class-Path`: Adding Helpers to the Bootstrap Class Loader

A Java agent often needs to inject calls to a **helper class** to measure timing, create traces, record metrics, or forward events to a collector. If the instrumented code belongs to a core JDK class, it may be defined by the **bootstrap class loader**, whereas the agent's classes are usually defined by the **system class loader**. A helper that only exists in the agent JAR is not guaranteed to be visible to the target class.

Two tools in `java.lang.instrument` directly address **bootstrap class lookup**:

1. **`Instrumentation.appendToBootstrapClassLoaderSearch(JarFile)`**: the agent proactively adds a JAR to the locations where the bootstrap loader searches for classes.
2. **Manifest `Boot-Class-Path`**: the agent pre-declares a list of additional paths in the JAR's main manifest, for the JVM to process when the agent starts.

Both only add **class search locations**. They **do not automatically instrument classes**, do not automatically load all classes in the JAR, do not replace an already defined `Class<?>`, and do not automatically grant all Java Platform Module System (JPMS) permissions.

This lesson belongs to the **Class Loaders and Helpers** section of Java Advance — instrumentation. The goal is to understand the differences between the two mechanisms, design a safe bootstrap helper, and run a Java 17+ example yourself that proves **the helper is genuinely defined by the bootstrap loader**.

## 1. Understanding Loader Identity Before Adding a Helper

In Java, a class is not distinguished by its binary name alone: the **defining class loader** is also a component that determines runtime identity. Two classes with the same name but defined by different loaders can be two distinct runtime types.

Simple model:

```text
                  JVM
                   |
         +---------+----------+
         |                    |
  Bootstrap loader       System loader
         |                    |
  java.lang.String        Agent entry class
  java.base classes       Application on -cp
  bootstrap helper        (depending on how it's run)
         |                    |
         +------ linkage -----+
               per JVM rules
```

Java APIs typically represent the bootstrap loader with **`null`**. For example:

```java
ClassLoader loader = someClass.getClassLoader();
System.out.println(loader == null ? "bootstrap" : loader.toString());
```

This is a **snippet inside a method** that has the variable `someClass`. A `null` result from `Class.getClassLoader()` means the class was defined by the bootstrap loader; it does not mean the class "has no loader".

| Class | Common defining loader | Notes |
|---|---|---|
| `java.lang.String` | Bootstrap | Core platform class |
| Agent class specified by `Premain-Class` | System | Agent JAR has a separate loader/module from the bootstrap helper |
| App class on `-cp` | System/application | Depends on environment and custom loaders |
| Helper in a JAR found by bootstrap | Bootstrap | Only when the class is actually defined by bootstrap |
| Class belonging to a plugin/custom loader | Custom loader | Must check actual delegation and module access |

A class in an appended JAR is **not guaranteed to be loaded**. The JVM only defines the class when it actually needs to look up that class and satisfies loading/linking conditions.

### 1.1. Why Does an Agent Need a Bootstrap-Defined Helper?

Suppose a transformer injects the bytecode:

```text
invokestatic com/example/agentbootstrap/BootstrapMarker.message:()Ljava/lang/String;
```

This is an **illustrative instruction**, not standalone Java source. When the target method runs, the JVM must resolve the symbolic reference to `BootstrapMarker`. If the target class is defined by the bootstrap loader, it does not by default search down into the agent's classes defined by the system loader.

Placing a **small helper** on the bootstrap search path can allow many classes belonging to loaders that delegate to bootstrap to find the same helper. However, this approach does not guarantee that every named module or custom loader can read or access the helper; the JPMS section at the end of this lesson explains more.

## 2. How Does the `appendToBootstrapClassLoaderSearch(JarFile)` API Work?

Signature:

```java
void appendToBootstrapClassLoaderSearch(java.util.jar.JarFile jarfile)
```

This is an instance method of `java.lang.instrument.Instrumentation`. You receive the `Instrumentation` object from the JVM through an entry point such as:

```java
public static void premain(String agentArgs, Instrumentation inst)
```

or:

```java
public static void agentmain(String agentArgs, Instrumentation inst)
```

The two signatures above are **illustrations of agent entry points**, not standalone programs.

A proper call pattern:

```java
import java.lang.instrument.Instrumentation;
import java.nio.file.Path;
import java.util.jar.JarFile;

// Place inside an agent class.
private static JarFile bootstrapJar;

public static void premain(String agentArgs, Instrumentation inst)
        throws Exception {
    Path helper = Path.of("dist", "boot-helper.jar")
            .toAbsolutePath().normalize();
    bootstrapJar = new JarFile(helper.toFile());
    inst.appendToBootstrapClassLoaderSearch(bootstrapJar);
}
```

The rules:

- The argument must be a **`JarFile`**, not a `String`, `Path`, URL, or directory.
- The JAR should contain the classes/resources that the **bootstrap loader** is permitted to search for instrumentation purposes.
- Only when the bootstrap loader's built-in search mechanism fails to find a class does it check the appended JARs.
- Can be called multiple times: the JVM searches the additional JARs **in the order of the append calls**.
- You must not assume that a later JAR will **override** a class already defined or previously found by bootstrap.
- `jarfile == null` causes the method to throw `NullPointerException`.
- The example keeps `JarFile` in a static field so the file is not closed immediately after appending. Resource management should match the actual agent/JVM lifecycle.

Calling `new JarFile(...)` can throw an `IOException` if the file does not exist, lacks read permissions, or is not a valid JAR. This is an error **in agent code**, not an error silently ignored like some invalid manifest paths.

### 2.1. Append Before the Target Class Needs the Helper

The JVM has a contract for **failed symbolic reference resolution**: a symbolic reference that has already failed resolution can continue to fail under the same rules if reused, even if the search path changes later.

```text
Target class A is already loaded
         |
         v
A references bootstrap helper H
         |
         v
Resolution of H fails
         |
         v
Agent appends JAR containing H
         |
         v
Cannot assume by default that
the same symbolic reference in A recovers
```

Therefore, you should **configure the helper early**, before the instrumented code executes for the first time. When dynamically attaching to a running JVM, be especially careful with already-loaded classes and previously failed references.

### 2.2. Bootstrap Append Is Not a Way to Replace Built-In JDK Classes

If the bootstrap loader has already defined or found a class from the runtime image, appending a new JAR **does not replace that class definition**. To modify the method bytecode of an already-loaded class, you must consider `ClassFileTransformer`, `retransformClasses`/`redefineClasses`, and their respective constraints.

## 3. Manifest `Boot-Class-Path`: Declaring Bootstrap JARs at Agent Startup

An agent JAR can contain a main manifest like the following:

```text
Manifest-Version: 1.0
Premain-Class: com.example.agent.BootstrapAgent
Boot-Class-Path: boot-helper.jar

```

Each header has a different responsibility:

- `Premain-Class`: the binary name of the **agent class** containing `premain(...)`, required when using `-javaagent`.
- `Boot-Class-Path`: **a list of locations where the bootstrap loader searches for helper classes**, optional.
- `Agent-Class`: if you want to support dynamic attach, it specifies the class containing `agentmain(...)`; it does not replace `Boot-Class-Path`.
- `Class-Path`: a header from the JAR File Specification, **not synonymous with** `Boot-Class-Path`.

The most important point: **a relative `Boot-Class-Path` is resolved relative to the absolute path of the agent JAR**, not the current working directory of the `java` command.

For example:

```text
project/
└── dist/
    ├── agent-manifest.jar
    └── boot-helper.jar
```

In the manifest of `dist/agent-manifest.jar`:

```text
Boot-Class-Path: boot-helper.jar
```

then the JVM uses `dist/boot-helper.jar` when resolving the relative path, even if the process was started from elsewhere.

### 3.1. Correct Path Syntax

According to the Java 17 `java.lang.instrument` package specification:

- The path list may consist of **multiple entries**, separated by **one or more spaces**.
- Each path has the syntax of the **path component of a hierarchical URI**.
- A path starting with `/` is treated as absolute; otherwise, it is relative to the agent JAR.
- The paths are searched **in the order listed**.
- Malformed or non-existent paths may be **ignored**.
- If the agent is started **after the JVM has already started**, paths that **do not represent a JAR file** will be ignored.
- `Boot-Class-Path` is optional; omitting this header does not automatically cause a valid agent to fail.

Example with two helpers:

```text
Boot-Class-Path: boot-helper.jar monitoring-helper.jar
```

To avoid confusing spaces used as separators with URI syntax, the hands-on example uses simple filenames without spaces. If you need complex OS paths, verify JDK-compatible encoding and inspect the actual manifest rather than concatenating strings by intuition.

### 3.2. Why Are Manifest Errors Often Hard to Spot?

Suppose the manifest has:

```text
Boot-Class-Path: boot-hepler.jar
```

while the actual JAR is named `boot-helper.jar`. Because a non-existent path may be ignored, the agent can still start and only fail when `Class.forName` or the target bytecode actually needs the helper.

Therefore, you must check **both**: the header in the final manifest inside the agent JAR and the helper file at the location where the JVM will look for it.

## 4. Comparing the API and the Manifest

| Aspect | `appendToBootstrapClassLoaderSearch` | `Boot-Class-Path` |
|---|---|---|
| Where configured | Agent Java code | Main manifest of the agent JAR |
| Input | A `JarFile` | One or more URI-style paths |
| Timing | When the agent **calls the method** | When the JVM processes the manifest at agent startup |
| Relative paths | Code chooses how to resolve (`Path`, working dir, etc.) | Relative to the **agent JAR** |
| Multiple JARs | Call multiple times; in call order | Path list; in listed order |
| Non-existent file | `JarFile` may throw an exception | Path may be ignored |
| Requires `Instrumentation` in code? | Yes | Not required just to declare |
| Usable in `agentmain`? | Yes, if the runtime allows dynamic agents | Yes, with the restriction on non-JAR entries at attach time |
| Auto-loads all classes? | No | No |
| Auto-instruments classes? | No | No |
| Replaces already-loaded classes? | No | No |

Choose the **manifest** if the helper JAR is packaged statically alongside the agent and you want minimal code. Choose the **API** if the helper path is determined by runtime configuration. Only place helpers in bootstrap when **loader visibility truly requires it**, avoiding using it as an "all-purpose classpath".

## 5. Complete Java 17+ Example: Same Helper, Two Ways to Add to Bootstrap

The example has three groups of classes:

- A helper packaged **separately** in `boot-helper.jar`.
- An agent with two modes: `api` and `manifest`.
- An application that directly calls the helper's method.

The key point: at **runtime**, the application's `-cp` contains only `out/app`, **without** the helper JAR. The bootstrap helper becomes available thanks to the agent. The example was run on **OpenJDK 21**, compiled with `javac --release 17`.

### 5.1. Directory Structure

```text
bootstrap-helper-demo/
├── src/
│   ├── helper/com/example/agentbootstrap/BootstrapMarker.java
│   ├── agent/com/example/agent/BootstrapAgent.java
│   └── app/demo/App.java
├── manifests/
│   ├── api.mf
│   └── manifest.mf
├── out/             (created during compilation)
│   ├── helper/
│   ├── agent/
│   └── app/
└── dist/            (three JARs created)
    ├── boot-helper.jar
    ├── agent-api.jar
    └── agent-manifest.jar
```

Create the source files and the two manifests according to the exact paths above. In the example, the package name `com.example.agentbootstrap` is a dedicated helper namespace, avoiding collisions with application or JDK packages.

### 5.2. `src/helper/com/example/agentbootstrap/BootstrapMarker.java`

```java
package com.example.agentbootstrap;

public final class BootstrapMarker {
    private BootstrapMarker() {}

    public static String message() {
        return "bootstrap-ok";
    }
}
```

The helper is very small: it only uses APIs from `java.lang` (visible to bootstrap). It **does not import** agent classes or application classes. This is an important principle: a bootstrap-defined helper must not assume it can arbitrarily link to classes defined by system or custom loaders.

### 5.3. `src/agent/com/example/agent/BootstrapAgent.java`

```java
package com.example.agent;

import java.lang.instrument.Instrumentation;
import java.nio.file.Path;
import java.util.jar.JarFile;

public final class BootstrapAgent {
    private static JarFile bootstrapJar;

    private BootstrapAgent() {}

    public static void premain(String agentArgs, Instrumentation inst)
            throws Exception {
        String mode;

        if (agentArgs != null && agentArgs.startsWith("api=")) {
            mode = "api";

            Path jarPath = Path.of(agentArgs.substring(4))
                    .toAbsolutePath()
                    .normalize();
            bootstrapJar = new JarFile(jarPath.toFile());

            // API mode: extend the bootstrap search path.
            inst.appendToBootstrapClassLoaderSearch(bootstrapJar);

        } else if ("manifest".equals(agentArgs)) {
            mode = "manifest";

            // The JVM already processed Boot-Class-Path in the manifest.
            // Do not call append here.
        } else {
            throw new IllegalArgumentException(
                    "Expected api=<jar> or manifest");
        }

        // A null loader requests the bootstrap loader.
        Class<?> marker = Class.forName(
                "com.example.agentbootstrap.BootstrapMarker",
                true,
                null);

        Object response = marker.getMethod("message").invoke(null);

        System.out.println("[agent] mode=" + mode);
        System.out.println("[agent] loader=" +
                (marker.getClassLoader() == null ? "bootstrap" : "other"));
        System.out.println("[agent] message=" + response);
    }
}
```

How the code works:

1. The JVM calls `premain` before application `main`.
2. If `agentArgs` starts with `api=`, the agent reads the trailing path, uses `Path` to convert it to an absolute path, opens the JAR, and calls `appendToBootstrapClassLoaderSearch`.
3. If `agentArgs == "manifest"`, the agent does not open the helper JAR via the API; the bootstrap search path is configured via the manifest.
4. After configuration, `Class.forName("...", true, null)` **requests the bootstrap loader** to load the helper.
5. `marker.getClassLoader() == null` proves the class was defined by bootstrap.
6. Reflection invokes `message()` to verify that the helper actually runs, not just that "the file exists in the JAR".
7. In the API branch, `JarFile` is kept in a static field and not closed immediately after appending.
8. There is no `ClassFileTransformer` in the example because the lesson tests **helper lookup/linkage**, not bytecode rewriting.

Using reflection here also avoids having the agent accidentally perform a link reference to the helper **before** calling append, which could make testing failed resolution confusing.

### 5.4. `src/app/demo/App.java`

```java
package demo;

import com.example.agentbootstrap.BootstrapMarker;

public final class App {
    private App() {}

    public static void main(String[] args) {
        System.out.println("[app] helper=" + BootstrapMarker.message());
    }
}
```

The application **imports the helper at compile time** but will **not** have the helper on the **runtime application classpath**. The bootstrap loader finds the helper from the agent's bootstrap path; the application loader can delegate the lookup to bootstrap.

If you try running the app with `-cp out/app` **without an agent**, the source syntax is still valid, but the helper is missing at runtime and a `NoClassDefFoundError` may occur. That is why the exercise requires one of the two agents.

### 5.5. The Two Manifests

`manifests/api.mf`:

```text
Manifest-Version: 1.0
Premain-Class: com.example.agent.BootstrapAgent

```

`manifests/manifest.mf`:

```text
Manifest-Version: 1.0
Premain-Class: com.example.agent.BootstrapAgent
Boot-Class-Path: boot-helper.jar

```

The trailing blank line in the manifest terminates the main section. The `Premain-Class` value is the **binary name** of the agent class. In manifest mode, `boot-helper.jar` is resolved relative to the location of `agent-manifest.jar`.

### 5.6. Compiling and Creating the JARs

Open a terminal in `bootstrap-helper-demo`, using JDK 17+:

```bash
mkdir out
mkdir out/helper
mkdir out/agent
mkdir out/app
mkdir dist
```

The directories only need to be created once. Then:

```bash
javac --release 17 -encoding UTF-8 -d out/helper src/helper/com/example/agentbootstrap/BootstrapMarker.java

javac --release 17 -encoding UTF-8 -d out/agent src/agent/com/example/agent/BootstrapAgent.java

javac --release 17 -encoding UTF-8 -cp out/helper -d out/app src/app/demo/App.java
```

The third command needs `-cp out/helper` **to compile App** because App imports `BootstrapMarker`. **Do not confuse** this compiler classpath with the application's runtime classpath.

Package the three JARs:

```bash
jar --create --file dist/boot-helper.jar -C out/helper .

jar --create --file dist/agent-api.jar --manifest manifests/api.mf -C out/agent .

jar --create --file dist/agent-manifest.jar --manifest manifests/manifest.mf -C out/agent .
```

Each `-C dir .` packages the contents of `dir` with the proper package structure at the root of the JAR.

Verify:

```bash
jar --list --file dist/boot-helper.jar
jar --list --file dist/agent-api.jar
jar --list --file dist/agent-manifest.jar
```

You should see:

```text
boot-helper.jar:
  com/example/agentbootstrap/BootstrapMarker.class

agent-api.jar / agent-manifest.jar:
  META-INF/MANIFEST.MF
  com/example/agent/BootstrapAgent.class
```

The list above is an **excerpt of the entries to check**, not the full output of `jar --list` (the archives also contain directory entries).

### 5.7. Running Mode A: Calling the Append API from `premain`

```bash
java -javaagent:dist/agent-api.jar=api=dist/boot-helper.jar -cp out/app demo.App
```

The JVM passes the literal string `api=dist/boot-helper.jar` into `agentArgs` of `premain`. The agent parses the `api=` prefix, opens the helper JAR, and appends it before loading the helper.

**Program stdout, excluding JVM diagnostics on stderr:**

```text
[agent] mode=api
[agent] loader=bootstrap
[agent] message=bootstrap-ok
[app] helper=bootstrap-ok
```

Verified working on OpenJDK 21 with bytecode compiled for Java 17.

### 5.8. Running Mode B: Using `Boot-Class-Path` in the Manifest

```bash
java -javaagent:dist/agent-manifest.jar=manifest -cp out/app demo.App
```

**Stdout:**

```text
[agent] mode=manifest
[agent] loader=bootstrap
[agent] message=bootstrap-ok
[app] helper=bootstrap-ok
```

The agent **does not** call `appendToBootstrapClassLoaderSearch` in this branch. The JVM reads `Boot-Class-Path: boot-helper.jar` from the manifest and adds the helper search location.

### 5.9. Why Do Both Results Match?

| What needs to be proven | API mode | Manifest mode |
|---|---|---|
| Is the helper on runtime `-cp`? | No | No |
| Mechanism adding helper to bootstrap search | API call | Manifest |
| Is the helper defined by bootstrap? | Yes (`getClassLoader()==null`) | Yes |
| Can the helper method run? | Yes | Yes |
| Can the app call the helper? | Yes | Yes |
| Does agent `premain` run before App `main`? | Yes | Yes |

Some HotSpot builds may print a **CDS/Class Data Sharing warning** on `stderr` when the bootstrap search path is extended. That message is **distinct from the stdout** above and does not by itself indicate that the append failed.

**This is the exact runtime example for the question:** "How can an application class link to a helper that is not on the runtime `-cp` yet is defined by the bootstrap loader?"

## 6. What Happens When a Helper Has Non-Bootstrap Dependencies?

The `java.lang.instrument` package specification advises: **supporting classes defined by the bootstrap loader must only link to classes that can be defined by the bootstrap loader**. There is no guarantee that the bootstrap loader can see all platform classes or application classes.

For example, you **should not** write a bootstrap helper that directly calls:

```java
// Illustrates a dangerous dependency in a bootstrap helper:
com.mycompany.application.ApplicationContext.current();
```

If `ApplicationContext` is only defined by an application/system/custom loader, the bootstrap loader may **fail to find** that class and throw `NoClassDefFoundError`.

Alternative design solutions:

- Keep the helper minimal, using only classes that bootstrap can load.
- Create a small interface/bridge, placing the forwarding flow to the agent service in an appropriate loader/module.
- Avoid having the helper depend on heavy logging frameworks, DI containers, agent implementations, or app classes.
- When state sharing is needed, carefully check loader identity, module boundaries, classloader GC eligibility, and reentrancy.

**Do not solve every dependency error by appending all of the agent's libraries to bootstrap.** That approach increases collision risk and causes linkage errors that are very hard to investigate.

## 7. Risk of Class Collisions and `IllegalAccessError`

The Javadoc for `appendToBootstrapClassLoaderSearch` warns of the case where a class loader `L` has the bootstrap loader as its parent, while a class `C` of `L` references a non-public supporting class such as `C$1`. If the bootstrap JAR accidentally contains a class `C$1` with the same name, delegation may cause it to be defined by bootstrap, creating a **different runtime package/class identity** and potentially causing `IllegalAccessError`.

This is why you must choose a **truly unique bootstrap helper package**. Do not place additional classes in packages already used by the application or other libraries. Do not package unrelated classes into the helper JAR.

A good package example in a real-world product might be:

```text
com.company.product.instrumentation.bootstrap.v1
```

The name above is a **convention suggestion**, not a JVM requirement. Replace it with a namespace owned by your organization and audit for collisions before release.

A few notes:

- Same binary name but different defining loaders can cause `ClassCastException` on cast, as they are not a common type.
- Same textual package name but different defining loaders are not necessarily considered the same runtime package.
- You cannot assume "a helper running in bootstrap always has more privileges" to bypass Java visibility or JPMS.
- An already-loaded helper class is not automatically replaced with a new version just because you append another JAR containing the same name.

## 8. JPMS: Loader Visibility Does Not Replace Module Readability

Since Java 9, in addition to class loaders, there are **modules**. A helper from a bootstrap JAR typically resides in the **unnamed module of the bootstrap loader**. Meanwhile, many platform classes reside in **named modules** such as `java.base`.

Example inside an agent:

```java
Class<?> helper = Class.forName(
        "com.example.agentbootstrap.BootstrapMarker", true, null);
Module module = helper.getModule();

System.out.println(module.isNamed());
System.out.println(module.getName());
```

This is an **illustrative snippet**, requiring appropriate context. For the helper in the example, the module is typically unnamed; `isNamed()` returns `false`, and `getName()` returns `null`.

### 8.1. Bootstrap Classes Do Not Automatically See All Application Classes

A helper defined by the bootstrap loader **cannot automatically load downward** into classes belonging only to system/custom loaders. Bootstrap is typically the parent in the delegation model; a parent does not look down to find all classes of its children.

### 8.2. Named Modules Still Enforce Module Readability Checks

If a class in a named module is instrumented to call a helper in the bootstrap unnamed module, the JVM may require a **readability edge** or appropriate access configuration. `appendToBootstrapClassLoaderSearch` and `Boot-Class-Path` do not automatically:

- Create all module read edges.
- Open all `exports`/`opens`.
- Call `Instrumentation.redefineModule`.
- Grant arbitrary reflection or native access permissions.

If you truly need to modify the module graph, you can study `Instrumentation.redefineModule(...)` and related permissions, then test on the specific module. You should not add broad read edges without understanding the agent's scope.

### 8.3. Custom Loaders May Have Different Search Models

Many class loaders use parent-first delegation, but some plugin/container loaders have their own policies. For applications with custom loaders or module layers, verify **how the target class actually resolves the helper** rather than only looking at the configured `Boot-Class-Path`.

## 9. Loading an Agent After JVM Startup (`agentmain`)

If the JVM supports dynamic attach, an agent JAR can declare:

```text
Manifest-Version: 1.0
Agent-Class: com.example.agent.DynamicBootstrapAgent
Boot-Class-Path: boot-helper.jar

```

This is an **illustrative manifest**; the `DynamicBootstrapAgent` class must exist and define a valid `agentmain` signature. The runnable example in Section 5 is a **startup agent** using `Premain-Class`, not a dynamic agent.

When running late:

1. The JVM must allow the attach/dynamic agent loading mechanism.
2. The agent is loaded via `Agent-Class` and `agentmain`, not via `Premain-Class`/`premain`.
3. `Boot-Class-Path` is still an agent manifest attribute, but **paths that do not represent a JAR file are ignored** when the agent starts after startup.
4. Inside `agentmain(String, Instrumentation)`, the agent can also call `appendToBootstrapClassLoaderSearch(new JarFile(...))` if the environment permits.
5. Adding a helper late **does not automatically fix already-failed symbolic references**, does not retransform all old classes, and does not replace already-loaded classes.
6. If the target class is already loaded and needs new calls injected, you must also design **retransformation/redefinition** within JVM capabilities and limits.
7. On JDK 21+, JEP 451 introduces warnings/policies related to **dynamic agent loading**; this is a separate concern from `Boot-Class-Path` and bootstrap helper lookup.

Do not confuse "declaring Boot-Class-Path means the JVM will auto-attach the agent": the two mechanisms have different responsibilities.

## 10. Distinguishing from `appendToSystemClassLoaderSearch`

`Instrumentation` also has the method:

```java
inst.appendToSystemClassLoaderSearch(jar);
```

This is an **illustrative snippet** with existing variables `inst` and `jar`; it adds a JAR to where the **system loader** searches for classes, not where the bootstrap loader searches for classes.

| Criterion | Bootstrap append | System append |
|---|---|---|
| Extended loader | Bootstrap | System |
| Helper `getClassLoader()` | May be `null` when defined by bootstrap | Usually the system loader when defined by system |
| Use case | Helpers needed by core/instrumented code | Helpers/app dependencies at the system layer |
| Risks | Package/class collisions in bootstrap, hard-to-see dependencies | Name collisions and custom system loader constraints |
| Modifies target class method body? | No | No |

If a custom system loader is configured, `appendToSystemClassLoaderSearch` also requires the loader to implement the `appendToClassPathForInstrumentation` contract. Do not treat the two APIs as equivalent and swap them back and forth when encountering errors.

## 11. Troubleshooting: Identifying the Right Error Type

| Observation | Cause to investigate |
|---|---|
| `new JarFile` throws IOException | Path, read permissions, missing or corrupted JAR |
| `Boot-Class-Path` is present but helper does not load | File is not next to the agent JAR per the relative path, typo, or wrong `.class` entry |
| `Class.forName(name, true, null)` throws `ClassNotFoundException` | Bootstrap has not found the class yet or the class entry is missing |
| App throws `NoClassDefFoundError` | Helper/dependency cannot be resolved from the relevant loader; may have already failed earlier |
| `helper.getClassLoader() != null` | Helper may have been defined by another loader; is there a duplicate class on the runtime classpath? |
| `IllegalAccessError` | Package-private access, loader identity, or module access |
| `ClassCastException` despite identical class names | Same name but different defining loaders |
| Append succeeds but instrumented method still errors | Need to check module read edges, dependencies, loader delegation, and resolution timing |
| Manifest path is just a directory during dynamic attach | Non-JAR entries may be ignored |
| CDS diagnostic appears on stderr | Does not mean append failed; check the helper loader and call result |
| Added JAR but running class does not change | Append is not retransform/redefine |
| Fails when run from a different working directory | API code is using a path relative to cwd; manifest is relative to the agent JAR |

A practical debugging workflow:

1. Check the **agent JAR** and **helper JAR** on the filesystem as seen by the JVM.
2. Read `META-INF/MANIFEST.MF` inside the final agent JAR (not just the `.mf` file used for packaging).
3. Inspect `jar --list --file dist/boot-helper.jar`; the `BootstrapMarker.class` entry must match the package.
4. For API mode, log the normalized helper path and confirm `JarFile` opened successfully.
5. Ensure append/manifest is processed **before** the target class resolves the helper.
6. Proactively call `Class.forName(helperBinaryName, true, null)` to test bootstrap lookup.
7. Verify `Class.getClassLoader() == null` and invoke a simple method.
8. If bootstrap loads it but the instrumented class still cannot call it, check module readability/access and parent delegation.
9. If a failed resolution already occurred, do not treat late append as a guaranteed fix.
10. For production agents, also check for collisions, helper dependencies, JDK versions, and the safety of the JAR source.

## 12. Common Design Mistakes

### 12.1. Putting the Entire Agent Framework on Bootstrap

An agent may depend on dozens of libraries. Putting all of them on bootstrap bloats the bootstrap namespace, increasing collision risks and dependencies from helpers down to lower class loaders. **Package only the minimal helper** into the bootstrap JAR.

### 12.2. Using Manifest `Class-Path` Instead of `Boot-Class-Path`

The two headers have different meanings. `Class-Path` does not automatically create bootstrap search entries under the agent contract. If you want a bootstrap helper, use `Boot-Class-Path` or the append API.

### 12.3. Mistakenly Assuming `Boot-Class-Path` Is Relative to the Working Directory

False. `Boot-Class-Path` is relative **to the absolute location of the agent JAR**. Only custom `Path.of(...)` paths written in API mode can depend on the working directory.

### 12.4. Calling the Helper Before Appending

If code has already attempted to resolve the helper and failed, the JVM may record the failed symbolic resolution. Append **before** any linkage path that needs the helper.

### 12.5. Failing to Verify the Defining Loader

Just because a class can be found via `Class.forName` using the system loader does not prove it was defined by bootstrap. Using `Class.forName(name, true, null)` and `getClassLoader() == null` allows a more specific check.

### 12.6. Using a Bootstrap Helper to Call Application Classes

A bootstrap helper does not automatically search down into custom/system loaders. Design the bridge and class/module accessibility properly; do not rely on the agent having instrumentation privileges as a pass to access every class.

### 12.7. Treating Append as a Way to Upgrade a Running JAR

Appending a path does not make the JVM discard existing class definitions. Modifying method bodies of already-loaded classes requires its own mechanism; changing class structure may require a new class loader or restarting under an appropriate architecture.

### 12.8. Failing to Distinguish Agent Errors from VM Diagnostics

A CDS warning may appear on stderr when the bootstrap path changes, even when the agent runs properly. Cross-check the helper's result and actual exceptions before concluding there is an error.

## 13. Self-Check Questions

**1.** What parameter type does `appendToBootstrapClassLoaderSearch` accept?

**Answer:** `java.util.jar.JarFile`; not `Path` or `String`.

**2.** What is `Boot-Class-Path: boot-helper.jar` resolved relative to?

**Answer:** The location of the **agent JAR**, not the working directory.

**3.** Does having `Boot-Class-Path` cause the JVM to automatically run `BootstrapMarker.message()`?

**Answer:** No. The header adds a class search location; a load request and a method call are required for it to run.

**4.** What proves that a helper was defined by the bootstrap loader?

**Answer:** `BootstrapMarker.class.getClassLoader() == null`, or using `Class.forName(name, true, null)` and checking the defining loader.

**5.** Why does the example `App` compile with `-cp out/helper` yet run with only `-cp out/app`?

**Answer:** The compiler needs to know the helper type at compile time. At runtime, the helper is provided by the bootstrap search path through the agent.

**6.** Does appending a JAR after a failed symbolic resolution guarantee that the same reference will be fixed?

**Answer:** No. The JVM has rules for failed resolution; you should append before the target needs the helper.

**7.** Can a bootstrap helper import any class defined by the system loader?

**Answer:** No. The helper must link to classes visible to the bootstrap loader; it does not automatically search down into child class loaders.

**8.** Should you put all of Byte Buddy/ASM, logging, and application libraries on bootstrap to "avoid ClassNotFoundException"?

**Answer:** No. That increases the risk of namespace collisions and dependency errors. Only include the necessary helper.

**9.** Can `Boot-Class-Path` be used together with `Agent-Class` for dynamic attach?

**Answer:** Yes, if the runtime supports dynamic agents; however, paths that do not represent a JAR are ignored when starting late.

**10.** Are `appendToSystemClassLoaderSearch` and `appendToBootstrapClassLoaderSearch` the same?

**Answer:** No. They extend **two different loaders**.

**11.** Does setting `Boot-Class-Path` automatically grant module read edges for all named modules?

**Answer:** No. JPMS access/readability is a separate responsibility, which may require `Instrumentation.redefineModule` per its contract.

**12.** If the agent prints a CDS warning on stderr yet the lines `loader=bootstrap` and `helper=bootstrap-ok` appear, can you conclude that loading the bootstrap helper failed?

**Answer:** No. In the example, the helper was defined by bootstrap and invoked successfully; a VM warning does not equate to an error.

## 14. Checklist When Releasing an Agent with a Bootstrap Helper

| Check | Expectation |
|---|---|
| Helper namespace | Unique, does not collide with JDK/application |
| Helper JAR contents | Only truly necessary classes and resources |
| Helper dependencies | Only uses classes visible to bootstrap |
| API path | Can be opened with `new JarFile(...)` and has a clear path |
| Manifest path | Relative to the agent JAR, exact filename and syntax |
| Actual manifest | Inspected from the final JAR |
| Timing | Helper is ready before the target resolves it |
| Loader identity | `getClassLoader() == null` for the bootstrap helper |
| JPMS | Check module readability/access with named modules |
| Dynamic attach | Runtime permits it, JAR entries are valid |
| No shadowing | No binary name collision with existing classes |
| Java version | Tested on target JDK versions |
| Resource lifetime | JAR is not closed prematurely |
| Runtime classpath test | Do not "accidentally" include the helper on `-cp` and invalidate the test |
| Observability | Clearly log agent mode, helper lookup, and specific errors |

## 15. Summary

- **`Instrumentation.appendToBootstrapClassLoaderSearch(JarFile)`**: the agent opens the JAR and proactively appends it to the bootstrap search path.
- **`Boot-Class-Path`**: the JVM reads the path list from the **main manifest of the agent JAR**; paths are relative to the agent JAR.
- Both **only make helper classes findable by bootstrap**, do not automatically instrument, do not automatically load all classes, and do not replace already-loaded classes.
- A bootstrap-defined helper has `Class.getClassLoader() == null`, but still requires handling **JPMS visibility** and valid dependencies.
- Keep the bootstrap helper **minimal**, in a dedicated package, and add the path **before** the target class attempts to resolve the helper.
- The Java 17+ example produced identical results via API mode and manifest mode, with the helper **absent from the runtime application classpath**.

## Official References

- Oracle Java 17 — [`Instrumentation.appendToBootstrapClassLoaderSearch(JarFile)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html).
- Oracle Java 17 — [`java.lang.instrument`: agent class loading and `Boot-Class-Path` manifest attribute](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html).
- Oracle Java 17 — [`ClassLoader` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html).
- Oracle Java 17 — [`Class.getClassLoader()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getClassLoader()).
- Oracle Java 17 — [`Instrumentation.redefineModule` and instrumentation APIs](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html).
- Oracle Java 17 — [Java Virtual Machine Specification — resolution and failed resolution (§5.4.3)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3).
- Oracle Java 17 — [JAR File Specification — manifest format](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html).
- OpenJDK — [JEP 451: Dynamic Agent Loading (JDK 21)](https://openjdk.org/jeps/451).
