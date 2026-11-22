## 7. Quick Diagram: Which Issue, Which Page to Open?

~~~text
Symptom / question
    |
    +-- "Two classes have the same name but cannot be cast"
    |       JVMS 5.3 -> ClassLoader/Class Javadoc
    |       -> print Class.getClassLoader/getModule
    |
    +-- "Bytecode VerifyError"
    |       JVMS 4.9/4.10 + 5.4.1
    |       -> javap -v -p (Code/StackMapTable)
    |
    +-- "NoSuchMethodError/NoSuchFieldError"
    |       JVMS 5.4.3 + JLS Ch.13
    |       -> javap -c caller, javap -p runtime JAR
    |
    +-- "Static initializer has not run / ran early"
    |       JLS 12.4 + JVMS 5.5 + Class.forName Javadoc
    |       -> try Class.forName(..., false/true, loader)
    |
    +-- "getResource cannot find file in JAR"
    |       ClassLoader/Class/Module Javadoc
    |       -> jar --list, print resource URL/loader
    |
    +-- "ServiceLoader provider not a subtype"
    |       ServiceLoader Javadoc + JVMS 5.3
    |       -> compare Class identity of service and provider
    |
    +-- "IllegalAccessError / reflection is blocked"
    |       JVMS 5.4.4 + JLS 6.6 + AccessibleObject Javadoc
    |       -> check exports/opens/modules + javap
    |
    +-- "Split package / ModuleLayer cannot be created"
    |       ModuleLayer/Configuration Javadoc + JLS 7.7
    |       -> jar --describe-module; jdeps --check
    |
    +-- "Slow startup due to class loading?"
            JVMS 5.3/5.5 + ClassLoader Javadoc
            -> java -Xlog:class+load, JFR, startup profiling
~~~

Note: this is a **starting point** for lookup, not an automatic root-cause identifier. For example, `ClassCastException` can also occur simply because of incorrect cast logic without multiple loaders; `NoSuchMethodError` can be caused by binary incompatibility even when the classpath has only a single loader.

## 8. Detailed Lookup Table by Real-World Symptom

| Observation | Authoritative Source to Open First | Tools/Evidence | What to Verify |
| --- | --- | --- | --- |
| `ClassNotFoundException` | ClassLoader Javadoc; JVMS 5.3 | Runtime `-cp`/module path, JAR entries | Correct binary name, loader scope, is the resource present in the artifact? |
| `NoClassDefFoundError` | JVMS 5.4–5.5, JLS 12.4 | Full stack trace and cause, init logs | Missing dependency, failed initialization, or mismatched class definition? |
| `ClassCastException` with the same name | JVMS 5.3, Class.getClassLoader | Print both `Class<?>`, loader, and module | Same binary name but different defining loader? |
| `VerifyError` | JVMS 4.9–4.10 | `javap -v -p`, transformer output | Are operand stack, locals, frames, and version valid? |
| `ClassFormatError` | JVMS Chapter 4 | File bytes, `javap`, build steps | Invalid header/constant pool/attributes? |
| `UnsupportedClassVersionError` | ClassLoader Javadoc, JVMS 4.1 | `javap -v` for major version, `java -version` | Was the class compiled for a newer JDK than the runtime? |
| `NoSuchMethodError` | JVMS 5.4.3, JLS 13 | `javap -c` caller, `javap -p` runtime library | Do method name, descriptor, and version match compile-time? |
| `IllegalAccessError` | JVMS 5.4.4, JLS 13 | Caller/target classes, `Module.isExported` | Was binary visibility/module access changed? |
| `IllegalAccessException` | Method/Field Javadoc | Reflection callsite and modifiers | Does the caller have permission to invoke/get without suppressing checks? |
| `InaccessibleObjectException` | AccessibleObject, Module Javadoc | `isOpen`, `module-info.java`, launcher args | Is the package open to the caller module? |
| `ServiceConfigurationError` | ServiceLoader Javadoc | `META-INF/services`, `jar --list`, loader identity | Is the provider class a subtype of the exact service Class? |
| `LayerInstantiationException` | ModuleLayer Javadoc | Module names/packages/loader mapping | Overlapping packages, loader mapping, or split delegation? |
| `ResolutionException` | Configuration, java.lang.module Javadoc | `jar --describe-module`, module graph | Exports/readability/dependency conflict? |
| Resource returns null | ClassLoader/Class/Module Javadoc | `getResource` URL and `jar --list` | Resource name, slash, module encapsulation? |
| Class unloading does not occur | JLS 12.7, ClassLoader/JFR docs | Loader stats/JFR/heap analysis | Are there remaining references to the loader/static cache/thread/TCCL? |
| Slow startup or initial p99 | JVMS 5.3–5.5, JFR docs | Startup traces, JFR, class logging | Is it loading or initialization, I/O, JIT, DI/proxy? |

**Note when encountering an Error:** always collect the **full message and cause chain**, binary class names, runtime JDK version, and exact artifact/classloader; reading only the exception name can lead to misdiagnosis.

## 9. Runnable Java 17+ Demo: Connecting Documentation to Evidence

The small demo below creates a nested class, asks the JVM to find the class **without requesting initialization**, prints the loader identity, and then performs an **active use** that causes the static initializer to run. We then use `javap` and `jar` to cross-check the bytecode and packaging.

### 9.1. File Tree

~~~text
lookup-lab/
└── src/
    └── lab/
        └── Probe.java
~~~

### 9.2. File src/lab/Probe.java

~~~java
package lab;

public final class Probe {
    static final class Deferred {
        static {
            System.out.println("Deferred initialized");
        }

        static int number() {
            return 42;
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader loader = Probe.class.getClassLoader();

        Class<?> type = Class.forName(
                "lab.Probe$Deferred", false, loader);

        System.out.println("binary name: " + type.getName());
        System.out.println("same loader: "
                + (type.getClassLoader() == loader));
        System.out.println("module named: "
                + type.getModule().isNamed());

        System.out.println("value: " + Deferred.number());
    }
}
~~~

**Why this is valid Java 17:** `Class.forName(String, boolean, ClassLoader)` is defined in Javadoc with an initialization flag; `Class.getModule` has existed since Java 9. The `Deferred` class is a static nested class whose binary name is `lab.Probe$Deferred` according to JLS/JVMS naming rules.

### 9.3. Compiling

Linux/macOS (bash/zsh), from `lookup-lab`:

~~~bash
mkdir -p out/classes
javac --release 17 -d out/classes src/lab/Probe.java
java -cp out/classes lab.Probe
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out/classes | Out-Null
javac --release 17 -d out/classes src/lab/Probe.java
java -cp out/classes lab.Probe
~~~

**Exact stdout in this classpath demo:**

~~~text
binary name: lab.Probe$Deferred
same loader: true
module named: false
Deferred initialized
value: 42
~~~

Explanation:

1. `Class.forName("lab.Probe$Deferred", false, loader)` asks to look up the Class **without requesting to run `<clinit>`** for `Deferred`; therefore, the initialization line does not appear yet.
2. `type.getName()` prints the **binary name** with the `$` character for the nested class.
3. `Probe` and `Deferred` are defined by the loader from the same application classpath root; `same loader: true`.
4. They belong to the **unnamed module** when run with `-cp`, so `module named: false`.
5. The call `Deferred.number()` is an active use, forcing initialization before running the method body. The order of the last two lines reflects that.

**Do not confuse:** the result above proves that the API does not request initialization during the lookup step; it does not prove that the JVM did not perform any kind of class loading/linking earlier. The order of class-loading events in VM logs may differ.

## 10. Using javap to See Which Instructions the JVM Actually Receives

After compiling `Probe`, run:

~~~bash
javap -classpath out/classes -c -p lab.Probe
~~~

Items to look for in the output:

- `public static void main(java.lang.String[])`.
- A call to `java/lang/Class.forName` with a descriptor having two additional parameters: `boolean` and `ClassLoader`.
- A call to `lab/Probe$Deferred.number:()I`.
- Instructions involving `getstatic java/lang/System.out` and `invokevirtual java/io/PrintStream.println`.

To view detailed metadata:

~~~bash
javap -classpath out/classes -v -p lab.Probe
~~~

This is a tool for inspecting **classfiles**, providing the constant pool, major version, method descriptors, `Code` attributes, line tables, and (when present) `StackMapTable`.

**Do not copy the full long output of `javap -v` as an “immutable result”:** offsets, constant pool indexes, and bootstrap entries depend on the compiler/build. Use it to compare actual methods, opcodes, and descriptors of a specific artifact.

### 10.1. Inspecting a Nested Class Properly

In bash, zsh, or PowerShell, put the binary name containing `$` inside **single** quotes so the shell does not interpret the character:

~~~bash
javap -classpath out/classes -c -p 'lab.Probe$Deferred'
~~~

In some other environments such as Windows CMD, quoting rules differ; you can specify the path to the generated class file or escape the name according to your actual shell. When you see the static initializer output `static {};` or `<clinit>`, refer to JLS `12.4` and JVMS `5.5` rather than guessing from the Java source.

## 11. Using jar to Confirm Whether the Artifact Contains the Right Classfiles

From the `lookup-lab` directory:

~~~bash
jar --create --file out/probe.jar -C out/classes .
jar --list --file out/probe.jar
java -cp out/probe.jar lab.Probe
~~~

**Note:** The JAR above does **not** set `Main-Class` in its manifest, so the right command here is `java -cp out/probe.jar lab.Probe`, **not** `java -jar out/probe.jar`.

The `jar --list` output will contain at least:

~~~text
lab/Probe.class
lab/Probe$Deferred.class
~~~

The JAR may contain additional entries such as `META-INF/` and the output order may differ; it is not required for the output to consist solely of the two lines above.

`java -cp out/probe.jar lab.Probe` will produce **the same five-line stdout as in section 9.3**, because both the class and nested class reside properly at the JAR root. The `jar --list` command proves that the artifact contains the entries, **it does not by itself prove** that the application runtime loaded the class from that exact JAR if the classpath has multiple roots with conflicting names. To investigate the runtime origin, combine class-loading logs with inspection of the loader/Class.

### 11.1. Looking at the Module Descriptor

With a JAR that has `module-info.class` or an automatic module, try:

~~~bash
jar --describe-module --file some-library.jar
~~~

**This is a sample command**, requiring an actual JAR. If the artifact is an automatic module, the tool can report the derived module name; if it is not a modular JAR, read the output according to the tool's semantics. Do not assume every JAR has an explicit `module-info.java`.

## 12. Using jdeps to Inspect Dependencies Instead of Inferring from Imports

With the `out/probe.jar` just built:

~~~bash
jdeps --summary out/probe.jar
~~~

The purpose is to inspect dependencies at the module/archive level. For a demo using only standard APIs, look for the dependency on **java.base** in the output; how paths, archive names, and wording are presented is formatted by the tool, not a fixed transcript.

Other useful commands when you have a real artifact:

~~~bash
jdeps --verbose:class app.jar
jdeps --jdk-internals app.jar
jdeps --list-deps app.jar
~~~

- `--verbose:class`: class-level dependency edges within the scope observed by the analyzer.
- `--jdk-internals`: finds references to **JDK internal APIs**, useful when upgrading the JDK.
- `--list-deps`: lists module dependencies according to the analysis result.

For a multi-release JAR, use `--multi-release 17` when you need to analyze the view matching the target JDK:

~~~bash
jdeps --multi-release 17 --summary multi-release-app.jar
~~~

If you are checking a named module with a specific name on the module path:

~~~bash
jdeps --module-path mods --check module.name
~~~

The last two commands are **examples**: they require an actual `multi-release-app.jar` file, `mods` directory, or `module.name` to exist. Do not run them directly against `out/probe.jar` above to check `module.name`, because the demo runs on the classpath and has no explicit module descriptor.

**Limitations:** `jdeps` performs **static dependency analysis**. It cannot automatically know class names constructed from strings and loaded via reflection or plugin metadata, nor does it replace checking the actual runtime `ClassLoader`, `ServiceLoader`, and module resolution graph.
