# javap, jar, and jdeps in Investigating Bytecode, JARs, and Dependencies

## 1. Three Tools Serving Three Different Questions

When a Java application encounters **ClassNotFoundException**, **NoClassDefFoundError**, **NoSuchMethodError**, **UnsupportedClassVersionError**, JPMS/module path errors, or when a JAR is suspected of containing the wrong version of a class, reading the source code alone is not enough. The JVM executes **compiled class files** and loads them through the classpath, module path, ClassLoader, and runtime linking rules.

Three tools bundled with the JDK help collect evidence from actual artifacts:

- **javap** — *Java class file disassembler*: “What **bytecode, descriptors, constant pool, flags, and metadata** has this class been compiled into?”
- **jar** — *Java archive tool*: “**What entries does the JAR contain**, what manifest/module descriptor does it have, and does it have the right class/resource/provider files needed?”
- **jdeps** — *Java class dependency analyzer*: “Which **classes/packages/modules does the artifact's bytecode directly reference**, and which dependencies are missing or belong to JDK internal APIs?”

These three tools are **not equivalent** and do not by themselves tell you which defining loader the runtime actually chose. To conduct a real class-loading investigation, you must combine static evidence with runtime logs, exception/cause, classpath/module path, and **Class.getClassLoader()**.

### Guidance Table

| Symptom / Question | Start with | Why |
| --- | --- | --- |
| “Is Class X inside the JAR?” | **jar --list** | View the exact entry path of the class/resource. |
| “Does the JAR have module-info or only an automatic module?” | **jar --describe-module** | View the descriptor or the derived automatic module. |
| “What descriptor does the compiled method have?” | **javap -s -p** | See JVM types, overloads, return/parameters. |
| “Does the bytecode call invokevirtual or invokeinterface?” | **javap -c -p** | Disassemble instructions and symbolic references. |
| “Is the class file for Java 17 or a newer Java version?” | **javap -verbose** | View major/minor version. |
| “Is the application missing a library?” | **jdeps --missing-deps** | Find unresolved class references when a dependency path is missing. |
| “Which JAR/module does app.jar depend on?” | **jdeps -summary** | Summarize static dependencies. |
| “Which library's types is the public API exposing?” | **jdeps -apionly** | Restrict to signatures/API surface. |
| “Is a JDK internal API being called?” | **jdeps -jdkinternals** | Find static references to JDK internals. |
| “Which ClassLoader order is actually used?” | **Runtime evidence** | javap/jar/jdeps do not replace observing the JVM. |

## 2. Prerequisites and Diagnostic Principles

This article uses **Java 17+**, with examples verified on **OpenJDK 21**. All three tools are **JDK tools**, not applications automatically included in a minimal Java runtime.

Verify the toolchain:

~~~bash
java -version
javac -version
javap -version
jar --version
jdeps --version
~~~

Version number output depends on the machine. **Do not assume** the JDK tools point to the same Java runtime used to run production: PATH, JAVA_HOME, container images, and build runners may select a different Java version.

When investigating a deployment error, record at minimum:

1. The JDK version used by **javac** to build.
2. The JDK/JVM version running the application.
3. The actual classpath/module path of the process.
4. The actual deployed JAR, **not a JAR in another source/build directory**.
5. The full exception message/cause, including class name, method descriptor, module, and loader if present.
6. The source/manifest/module-info/resource entries of the artifact itself.
7. Any custom ClassLoader, plugin layer, TCCL, and parent/child delegation strategy.

**Principle:** inspect a specific artifact first, then investigate the artifact and loader selection path at runtime. A file containing a valid class **does not mean the JVM definitely loaded that class**.

## 3. Creating a Reproducible Example Set for Practice

We will build **two separate JARs**:

- **greeting-lib.jar** contains the **lab.api.Greeting** interface and the **lab.impl.GreetingImpl** implementation.
- **app.jar** contains **lab.app.Main**, compiled against the library but **without packaging the library's classes** into app.jar.

This allows us to examine a real error: app.jar has the Main entry, but if you run it and forget greeting-lib.jar, a runtime dependency will be missing.

Source structure:

~~~text
project/
└── src/
    ├── lab/
    │   ├── api/Greeting.java
    │   ├── impl/GreetingImpl.java
    │   └── app/Main.java
    ├── classes-lib/           (created during compilation)
    ├── classes-app/           (created during compilation)
    ├── libs/greeting-lib.jar  (created during packaging)
    └── app.jar                (created during packaging)
~~~

The output files are at the same level as **src/**; the tree above groups them conceptually. Run commands from the project directory.

### 3.1 Shared API Source

**src/lab/api/Greeting.java**:

~~~java
package lab.api;

public interface Greeting {
    String hello(String name);
}
~~~

### 3.2 Implementation Source

**src/lab/impl/GreetingImpl.java**:

~~~java
package lab.impl;

import lab.api.Greeting;

public final class GreetingImpl implements Greeting {
    public GreetingImpl() {
    }

    @Override
    public String hello(String name) {
        return "Hello, " + name;
    }
}
~~~

### 3.3 Application Source

**src/lab/app/Main.java**:

~~~java
package lab.app;

import lab.api.Greeting;
import lab.impl.GreetingImpl;

public final class Main {
    public static void main(String[] args) {
        Greeting greeting = new GreetingImpl();
        System.out.println(greeting.hello("Java"));
    }
}
~~~

### 3.4 Compiling and Packaging

From the project directory, create the necessary output directories:

~~~bash
mkdir -p classes-lib classes-app libs
javac --release 17 -g -d classes-lib src/lab/api/Greeting.java src/lab/impl/GreetingImpl.java
javac --release 17 -g -cp classes-lib -d classes-app src/lab/app/Main.java
jar --create --file libs/greeting-lib.jar -C classes-lib .
jar --create --file app.jar --main-class lab.app.Main -C classes-app .
~~~

The **-g** flag requests generating appropriate debugging information so that **javap -l** has line/local variable table data. **--release 17** ensures a compatible Java 17 class-file target and API set, even when using javac 21.

In **Windows PowerShell 5.x**, use:

~~~powershell
New-Item -ItemType Directory -Force classes-lib, classes-app, libs | Out-Null
javac --release 17 -g -d classes-lib src/lab/api/Greeting.java src/lab/impl/GreetingImpl.java
javac --release 17 -g -cp classes-lib -d classes-app src/lab/app/Main.java
jar --create --file libs/greeting-lib.jar -C classes-lib .
jar --create --file app.jar --main-class lab.app.Main -C classes-app .
~~~

If creating the source files on Windows, ensure UTF-8 encoding appropriate for the compiler environment; this example uses ASCII literals so it does not depend on the locale encoding.

### 3.5 Running with Full Dependencies

Linux/macOS:

~~~bash
java -cp "app.jar:libs/greeting-lib.jar" lab.app.Main
~~~

Windows PowerShell:

~~~powershell
java -cp "app.jar;libs/greeting-lib.jar" lab.app.Main
~~~

**Stdout from an actual run on OpenJDK 21:**

~~~text
Hello, Java
~~~

If you only run:

~~~bash
java -jar app.jar
~~~

in this setup, the command **does not put greeting-lib.jar on the classpath**. On OpenJDK 21, the result is:

~~~text
Error: Unable to initialize main class lab.app.Main
Caused by: java.lang.NoClassDefFoundError: lab/api/Greeting
~~~

**Why?** The JAR **app.jar** has **Main-Class**, but the manifest does not yet have **Class-Path** pointing to the library, and the java -jar command does not arbitrarily take an external -cp as an additional loading path. app.jar itself does not contain lab/api/Greeting.class. This is the fixture for using both **jar** and **jdeps** to find the cause.

## 4. The jar Tool: Inspecting the Exact Contents of an Archive

### 4.1 Listing Entries

Two equivalent ways:

~~~bash
jar --list --file libs/greeting-lib.jar
jar tf libs/greeting-lib.jar
~~~

For the example library JAR, the list includes:

~~~text
META-INF/
META-INF/MANIFEST.MF
lab/
lab/api/
lab/api/Greeting.class
lab/impl/
lab/impl/GreetingImpl.class
~~~

For app.jar:

~~~bash
jar --list --file app.jar
~~~

The entries include:

~~~text
META-INF/
META-INF/MANIFEST.MF
lab/
lab/app/
lab/app/Main.class
~~~

**Diagnostic conclusion:** **Greeting.class is not inside app.jar**. If the application launcher only uses app.jar without the library JAR, that dependency may be missing.

**JAR entry paths use /, not dots:** Class **lab.api.Greeting** corresponds to **lab/api/Greeting.class**. Having **Greeting.class** at the wrong package path may prevent the class loader from finding the right binary name.

### 4.2 Checking Package Names and Duplicate Entries

If you suspect duplicate versions of a class:

~~~bash
jar --list --file libs/greeting-lib.jar
jar --list --file app.jar
~~~

Compare the **full entry path**, not just the trailing filename. A JAR can contain multiple classes named **Helper.class** in different packages without any error.

**JAR A and JAR B both containing lab/api/Greeting.class does not prove there is a LinkageError.** The runtime may select one copy based on classpath order or delegation, or two loaders may validly define separate copies. You must check Class identity and type linking at runtime.

### 4.3 Viewing the Manifest

The manifest is located at **META-INF/MANIFEST.MF**. To read it using JDK tools, extract it separately into an empty directory and open the file:

~~~bash
mkdir -p inspect-app
cd inspect-app
jar --extract --file ../app.jar META-INF/MANIFEST.MF
cat META-INF/MANIFEST.MF
cd ..
~~~

On Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force inspect-app | Out-Null
Set-Location inspect-app
jar --extract --file ../app.jar META-INF/MANIFEST.MF
Get-Content META-INF/MANIFEST.MF
Set-Location ..
~~~

The manifest in the fixture has **Main-Class: lab.app.Main** due to **--main-class**, but does not have **Class-Path: libs/greeting-lib.jar**. Do not assume that **--main-class** packages dependencies.

**Security note:** Extract an untrusted JAR into a controlled separate directory; avoid extracting all entries indiscriminately into a directory containing project/sensitive files. Reviewing **jar --list** before extracting is a prudent check.

### 4.4 --verbose and --validate

~~~bash
jar --list --verbose --file app.jar
jar --validate --file app.jar
~~~

**--list --verbose** adds size, timestamp, and entry metadata; output may vary depending on how the archive was packaged. **--validate** checks archive validity according to the tool's rules, such as multi-release cases or module-related entries.

**Important:** A successful **jar --validate** **does not prove** that the application has all its dependencies, has the right class-loader policy, or can run without error. In the fixture, app.jar is valid as an archive, yet **java -jar app.jar** still fails due to the missing Greeting.

### 4.5 --describe-module and Automatic Modules

~~~bash
jar --describe-module --file libs/greeting-lib.jar
~~~

Because the fixture does not compile **module-info.java**, the tool reports that it **has no module descriptor** and derives the automatic module name from the JAR file:

~~~text
No module descriptor found. Derived automatic module.

greeting.lib automatic
requires java.base mandated
contains lab.api
contains lab.impl
~~~

That is the output observed with the filename **greeting-lib.jar** on JDK 21. An explicit modular JAR with **module-info.class** will have an actual descriptor, not just a derived automatic name.

**Do not be mistaken:**

- **Having a JAR file** does not mean it is an **explicit named module**.
- **Automatic-Module-Name** in the manifest can control the automatic module name, but does not create **module-info.class**.
- When a JAR is placed on the classpath, classes normally belong to the **unnamed module**, and do not automatically become a named module just because jar --describe-module derives an automatic name.
- When a JAR is placed on the module path, module resolution and the module graph determine which modules are actually used.

### 4.6 Special Entries to Look For

When diagnosing plugins/modules/SPI:

| Entry | Meaning |
| --- | --- |
| **META-INF/MANIFEST.MF** | Main-Class, Class-Path, Implementation-Version, Multi-Release... |
| **module-info.class** at root | Explicit module descriptor. |
| **META-INF/services/com.example.Service** | Provider-configuration file for classpath/automatic-module SPI according to the relevant model. |
| **META-INF/versions/17/...** | Version-specific class/resource in a multi-release JAR. |
| **package/name/Type.class** | Class bytecode in the corresponding package. |
| **META-INF/*.SF / *.RSA / *.DSA** | May be related to JAR signing. |
| **application.properties, config/...** | Resources that may be needed at runtime, which jdeps does not necessarily track. |

**Multi-Release Note:** Having an entry under **META-INF/versions/17** does not automatically guarantee that the JVM uses it; it requires **Multi-Release: true** in the manifest, the appropriate runtime version, and matching lookup rules. For an uncertain JAR, inspect both the base entry and the versioned entries.

## 5. The javap Tool: Looking Directly at the Class File Instead of Source

**javap** does not run the application and does not create instances of the analyzed class. It reads class files/JARs/modules and prints signatures, bytecode, constant pool, flags, or debug metadata depending on the options.

### 5.1 Core Commands

~~~bash
javap -classpath libs/greeting-lib.jar lab.impl.GreetingImpl
javap -classpath libs/greeting-lib.jar -p lab.impl.GreetingImpl
javap -classpath libs/greeting-lib.jar -s lab.impl.GreetingImpl
javap -classpath libs/greeting-lib.jar -c lab.impl.GreetingImpl
javap -classpath libs/greeting-lib.jar -v lab.impl.GreetingImpl
~~~

Use **-classpath** (or **-cp**) for the location containing the class files to inspect. This is the path for **javap to find the class**, and does not prove that the runtime application also selects that path.

Table of useful options:

| Option | Information |
| --- | --- |
| **-p / -private** | Shows private members as well, including synthetic members depending on the class. |
| **-c** | Disassembles bytecode instructions for each method. |
| **-s** | Prints JVM internal type descriptors. |
| **-l** | Prints the line number table and local variable table if the class file contains them. |
| **-v / -verbose** | Class-file version, constant pool, access flags, attributes, bootstrap methods... |
| **-sysinfo** | Path, size, timestamp, hash according to the tool/JDK. |
| **--module moduleName** | Inspects a class in the appropriate named module. |
| **--module-path path** | Specifies the module path for named modules. |

### 5.2 Observing Actual Bytecode

~~~bash
javap -classpath libs/greeting-lib.jar -c -p -s lab.impl.GreetingImpl
~~~

The output excerpt related to the **hello** method verified on OpenJDK 21 with javac --release 17:

~~~text
public java.lang.String hello(java.lang.String);
  descriptor: (Ljava/lang/String;)Ljava/lang/String;
  Code:
     0: aload_1
     1: invokedynamic #7,  0
     6: areturn
~~~

Constant pool numbering such as **#7** may change if the source/compiler/options differ. However, for the **exact fixture and toolchain** used, this is how the method's string concatenation is compiled via **invokedynamic**.

**Decoding:**

- **aload_1**: pushes local variable #1 (the parameter name) onto the operand stack.
- **invokedynamic**: invokes a dynamic call site linked by the JVM to an appropriate bootstrap method, which here handles string concatenation.
- **areturn**: returns a reference, in this case a String.

Do not read the -c output as Java source; it is **JVM bytecode disassembly**. The Java compiler may optimize or choose different bytecode from what a developer envisions from the source.

### 5.3 JVM Descriptors Are Key to Diagnosing NoSuchMethodError

The descriptor:

~~~text
(Ljava/lang/String;)Ljava/lang/String;
~~~

means the method accepts one **java.lang.String** and returns a **java.lang.String**.

Some examples:

| Java signature | JVM descriptor |
| --- | --- |
| void run() | **()V** |
| int sum(int a, int b) | **(II)I** |
| String hello(String x) | **(Ljava/lang/String;)Ljava/lang/String;** |
| void main(String[] args) | **([Ljava/lang/String;)V** |
| long[] values() | **()[J** |
| boolean test(Object o) | **(Ljava/lang/Object;)Z** |

When encountering:

~~~text
java.lang.NoSuchMethodError:
  'java.lang.String lib.Type.lookup(java.lang.String)'
~~~

inspect the **exact deployed lib.Type.class** with **javap -s -p**. The current source may have the method, while an older runtime JAR lacks that descriptor. Return type, parameters, and method name are essential parts of bytecode linking; overloads/erasure/bridge methods can cause the source form and the actual descriptor to differ.

**Do not fix it by arbitrarily renaming the class.** Check the compile-time vs. runtime artifacts and which ClassLoader was selected.

### 5.4 invokevirtual, invokestatic, invokeinterface

For app.jar:

~~~bash
javap -classpath app.jar -c -p -s lab.app.Main
~~~

Key bytecodes in the fixture:

~~~text
0: new           #7     // class lab/impl/GreetingImpl
3: dup
4: invokespecial #9     // constructor
7: astore_1
8: getstatic     #10    // Field java/lang/System.out
11: aload_1
12: ldc          #16     // String Java
14: invokeinterface #18,  2
19: invokevirtual #24    // PrintStream.println
22: return
~~~

The specific constant pool indices depend on the build, so this excerpt is representative output from the executed fixture. Meaning:

- **new** references the implementation class **lab.impl.GreetingImpl**.
- **invokespecial** calls the constructor.
- **invokeinterface** calls the interface method **lab.api.Greeting.hello**.
- **invokevirtual** calls the instance method of PrintStream.

If a dependency is missing or class identity does not match, an error may surface when the JVM has to **resolve** these symbolic references. javap shows **which names** the bytecode is **referencing**, rather than determining which loader source returns which Class.

### 5.5 Reading the Constant Pool, Class-File Major Version, and Attributes

~~~bash
javap -classpath libs/greeting-lib.jar -verbose lab.impl.GreetingImpl
~~~

Observed lines:

~~~text
major version: 61
flags: (0x0031) ACC_PUBLIC, ACC_FINAL, ACC_SUPER
this_class: #11     // lab/impl/GreetingImpl
...
Constant pool:
...
#7 = InvokeDynamic ...
~~~

**Major version 61 is the Java 17 class-file target.** Some common versions:

| Java target | Major version |
| --- | ---: |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

If a Java 17 runtime receives a class file with major version 65, it may throw **UnsupportedClassVersionError**; confirm with javap -v on the deployed artifact.

### 5.6 -l Only Helps When Debug Information Is Present

~~~bash
javap -classpath libs/greeting-lib.jar -l lab.impl.GreetingImpl
~~~

Because it was compiled with **-g**, the class file can contain **LineNumberTable** and **LocalVariableTable**. If the production build was compiled with **-g:none** or was shrunk/obfuscated, these tables may be missing.

**The absence of debug tables does not inherently make a class file wrong.** It only limits the ability to map bytecode ↔ source line/local variable name.

### 5.7 Compile-Time Artifacts Do Not Tell Everything About Runtime

A class file has the **lab.api.Greeting** interface in its constant pool, but that **does not prove** the JVM used the version of the interface in libs/greeting-lib.jar. If the classpath/module path has a different copy or a custom loader, a type mismatch may occur.

Use:

~~~java
System.out.println(lab.api.Greeting.class.getClassLoader());
System.out.println(lab.api.Greeting.class.getProtectionDomain()
        .getCodeSource());
~~~

This is a snippet that needs to be placed inside a valid method; **getCodeSource() may be null**, so production code must null-check it. Runtime logs combined with javap are needed to confirm which bytecode source was chosen.

## 6. jdeps: Analyzing the Dependency Graph from Bytecode

**jdeps** analyzes **static class-file dependencies** without running the application. It reads class files/JARs/directories and reports class/package/module dependencies according to the options.

### 6.1 Running Summary with the Full Library Path

~~~bash
jdeps -summary -cp libs/greeting-lib.jar app.jar
~~~

**Verified output on OpenJDK 21:**

~~~text
app.jar -> libs/greeting-lib.jar
app.jar -> java.base
~~~

This shows that bytecode in app.jar references classes in the library JAR and JDK java.base.

**Important syntax:** In JDK 21, the summary option is **-summary** or **-s**, **not --summary**. Mistakenly typing --summary will cause jdeps to report an unknown option. Check **jdeps --help** for the JDK you are using to get the exact option spelling.

### 6.2 Omitting the Library Path to See Missing Dependencies

~~~bash
jdeps -summary app.jar
~~~

Output in the fixture:

~~~text
app.jar -> java.base
app.jar -> not found
~~~

Looking deeper at the missing classes:

~~~bash
jdeps --missing-deps app.jar
~~~

Verified output:

~~~text
app.jar -> not found
   lab.app.Main -> lab.api.Greeting         not found
   lab.app.Main -> lab.impl.GreetingImpl    not found
~~~

The column spacing format is rendered by the tool; the class names and **not found** are the essential information.

**Read the meaning accurately:** jdeps could not find **the classes referenced by the bytecode on the current analysis path**. It does not prove that the class file does not exist anywhere on disk. You may not have passed **-cp**, may have used the wrong relative path, may be missing a transitive JAR, or may not have configured the module path.

Compare with runtime:

~~~text
java -jar app.jar
  -> NoClassDefFoundError: lab/api/Greeting

jdeps --missing-deps app.jar
  -> lab.api.Greeting not found
~~~

Two independent observations point to the same issue: the application artifact **does not have sufficient dependencies along the execution/analysis path**.

### 6.3 Viewing Class-Level Dependencies

~~~bash
jdeps -verbose:class -cp libs/greeting-lib.jar app.jar
~~~

Part of the verified output:

~~~text
app.jar -> libs/greeting-lib.jar
app.jar -> java.base
   lab.app.Main -> java.io.PrintStream           java.base
   lab.app.Main -> java.lang.Object              java.base
   lab.app.Main -> java.lang.String              java.base
   lab.app.Main -> java.lang.System              java.base
   lab.app.Main -> lab.api.Greeting              greeting-lib.jar
   lab.app.Main -> lab.impl.GreetingImpl         greeting-lib.jar
~~~

This is how you determine **which class in app.jar depends on which class**. If you have dozens of library JARs, -verbose:class helps pinpoint the dependency source within the set of artifacts provided for analysis.

Some related options:

| jdeps Option | Effect |
| --- | --- |
| **-s / -summary** | Summarizes archive/module dependencies. |
| **-verbose:class** | Shows class-level dependencies. |
| **-verbose:package** | Shows package-level dependencies. |
| **-v / -verbose** | More class-level dependencies per contract, equivalent to -verbose:class -filter:none. |
| **-cp / --class-path** | Specifies the classpath to search for referenced classes. |
| **--module-path** | Specifies the path for named modules. |
| **--missing-deps** | Focuses on dependencies that cannot be found. |
| **-apionly** | Analyzes only dependencies exposed in appropriate public/protected APIs. |
| **-jdkinternals** | Finds references to JDK internal APIs. |
| **--multi-release 17** | Selects the class-file view for a multi-release JAR by target version. |
| **--list-deps** | Lists module dependencies and relevant JDK internals. |
| **--print-module-deps** | Comma-separated module list, useful as input for jlink. |
| **--dot-output dir** | Outputs Graphviz DOT files to draw graphs. |

### 6.4 API-Only Does Not Mean All Runtime Dependencies

~~~bash
jdeps -apionly -verbose:class -cp libs/greeting-lib.jar app.jar
~~~

For the fixture, Main only has a public **main(String[])** and constructor; many internal implementation dependencies will not appear in the API-only output. If you use this result to build a full runtime dependency list, you may miss libraries.

**-apionly** helps understand dependencies exposed through public/protected contracts, and does not replace full bytecode analysis.

### 6.5 --list-deps and --print-module-deps

~~~bash
jdeps --list-deps -cp libs/greeting-lib.jar app.jar
jdeps --print-module-deps -cp libs/greeting-lib.jar app.jar
~~~

For the fixture, the verified commands return the JDK module dependencies:

~~~text
java.base
~~~

**Do not interpret this as needing only java.base to run the application.** The output consists of **module names**, not the full list of required third-party classpath JARs. The demo still needs greeting-lib.jar to run.

**--print-module-deps** can be used when building a **jlink custom runtime image** for a set of modules; classpath applications still need to be packaged/deployed with their corresponding third-party libraries.

## 7. What Blind Spots Does jdeps Have?

### 7.1 Dynamic Reflection

Example:

~~~java
Class<?> c = Class.forName(System.getProperty("plugin.class"));
~~~

If the class name only comes from config at runtime, the bytecode has no fixed class symbolic reference for that name. jdeps **cannot accurately infer all possible values from config/user input**. Therefore, jdeps may not report a plugin JAR that the actual runtime needs.

### 7.2 ServiceLoader and META-INF/services

~~~java
ServiceLoader<MyService> loader =
        ServiceLoader.load(MyService.class);
~~~

This snippet assumes an appropriate MyService and imports. ServiceLoader can find providers via **META-INF/services** or **provides** in named modules. jdeps does not replace inspecting the **provider-configuration file** and module descriptors, especially for plugins packaged outside app.jar.

A provider JAR that is not among static references from the consumer may not appear in the jdeps dependency list, yet is still needed when running ServiceLoader.

### 7.3 Custom ClassLoaders and Downloaded/Generated Classes

~~~java
byte[] bytes = downloadClassBytes();
Class<?> c = loader.defineOrLoad(...);
~~~

This is conceptual code and does not compile standalone. Classes from a database, network, runtime bytecode generation, or an encrypted JAR may not be in the input artifacts when jdeps runs.

**jdeps does not execute custom ClassLoaders**. The result depends on the files you pass in for analysis, not the entire class graph that will arise at runtime.

### 7.4 JNI, Native Libraries, and External Config

A class with a **native method** or one that loads a library via **System.loadLibrary** may need **.so / .dll / .dylib** or environment variables. jdeps focuses on class dependencies and does not prove that native binaries are compatible or present.

Similarly, resource paths, config files, SQL/schemas, network services, and reflective scanning conventions are not necessarily listed by jdeps.

### 7.5 Dynamic Proxies and invokedynamic

Static analysis can see the symbolic references in the class file, bootstrap methods, and API classes, but cannot guarantee that every runtime-generated proxy/hidden class/call-site target has been completely listed.

**Conclusion:** jdeps is a strong layer of evidence for **static references**, not an exact simulation of the entire runtime.

## 8. Investigating Java Modules and JPMS

### 8.1 Distinguishing Classpath from Module Path

In Java 9+, the same JAR can have multiple semantics when placed in different locations:

- **Classpath**: classes belong to the unnamed module of the corresponding loader.
- **Module path with explicit module-info.class**: a named module with an actual descriptor.
- **Module path with a JAR without module-info.class**: can become an **automatic module**.

**jar --describe-module** helps inspect whether an artifact is modular/automatic; **jdeps --module-path** helps analyze the module graph, while **javap module-info.class** helps inspect the bytecode descriptor.

### 8.2 Viewing the Module Descriptor

For an explicit modular JAR:

~~~bash
jar --describe-module --file some-module.jar
javap -p -v -classpath some-module.jar module-info
~~~

The second command may depend on how javap looks up class/module info; a simple option with a JAR like **javap -v some-module.jar** is not stable syntax for the descriptor. Prefer **jar --describe-module** or **javap --module-path path --module module.name module-info** depending on the specific environment.

For the fixture JAR **greeting-lib.jar**, **there is no module-info.class**, so do not fabricate a developer-written module descriptor with requires/exports.

### 8.3 jdeps on Modules

When two explicit modules are compiled/packaged:

~~~bash
jdeps --module-path mods --check my.app
jdeps --module-path mods --module my.app
jdeps --module-path mods --print-module-deps --module my.app
~~~

These are **sample commands with the placeholder module name my.app and path mods**, and do not apply directly to the classpath fixture above. Replace them with real module names; if the module path does not contain my.app, the tool will report an error.

**--check** analyzes the dependences and graph of a named module, which can help detect unnecessary requires, transitive relationships, and the reduced graph. **--module** specifies the root module to analyze. Do not use **--check** with an arbitrarily inferred JAR name if it is not yet on the proper module path.

### 8.4 jdeps --generate-module-info: A Suggestion, Not the Final Deployment Result

In some migration paths from classpath to JPMS, you can use:

~~~bash
jdeps --generate-module-info generated libs/greeting-lib.jar
~~~

The command analyzes the JAR to generate a suggested **module-info.java** in the output directory. Certain constraints apply: do not arbitrarily combine **--generate-module-info** with **--class-path** or **--dot-output**; check **jdeps --help** for the JDK in use.

**Do not commit/tag tool-generated module-info without reviewing it.** Static analysis may miss reflective access, services, optional runtime deps, qualified exports, or required opens. Review the module name, requires/exports/opens/uses/provides, and run integration tests.

### 8.5 Multi-Release JARs: Inspecting the Right Class Version for Each Java Version

If the manifest has:

~~~text
Multi-Release: true
~~~

the JAR may contain:

~~~text
com/example/Feature.class
META-INF/versions/11/com/example/Feature.class
META-INF/versions/17/com/example/Feature.class
~~~

In Java 17, the selected class may differ from the base; in Java 21, the version 17 copy or the highest matching version may be used if one exists.

With jdeps:

~~~bash
jdeps --multi-release 17 -summary multi.jar
jdeps --multi-release base -summary multi.jar
~~~

**multi.jar is an illustrative name**, not an artifact created in the fixture. Compare results between base and 17 when MR entries are present; different dependencies are a sign that a runtime version may require different classes/modules.

With javap, when you need to inspect specific **versioned class bytes**, identify the exact entry along the META-INF/versions/... path or use the **--multi-release** option if supported by the corresponding JDK/tool. Always check **javap --help** so you do not mistakenly apply a jdeps option.

## 9. Investigating Common Class-Loading Errors

### 9.1 ClassNotFoundException: Class Not Found by Name

Scenario:

~~~text
java.lang.ClassNotFoundException: lab.impl.GreetingImpl
~~~

Procedure:

1. **jar --list** the library JAR: is the **lab/impl/GreetingImpl.class** entry present?
2. Check the actual classpath/runtime loader: is that JAR provided?
3. **javap -classpath ... lab.impl.GreetingImpl**: can the class file be read by binary name?
4. **jdeps --missing-deps app.jar**: does it mention the needed class?
5. If using a custom loader, inspect parent delegation, child-first package filters, TCCL, and source locations.

If the JAR contains the class but **the runtime does not use that JAR**, do not randomly add a URL and conclude that you have fixed the loader policy.

### 9.2 NoClassDefFoundError: The JVM Cannot Define the Required Class

In the fixture:

~~~text
NoClassDefFoundError: lab/api/Greeting
~~~

**jdeps --missing-deps** and **jar --list** help find missing dependencies. However, NoClassDefFoundError can also appear because the class **failed initialization** earlier or due to another linkage issue. Inspect the full cause chain rather than assuming it is always due to a missing file.

### 9.3 NoSuchMethodError

Scenario where the build compiles against a newer library version but an older version is deployed:

~~~text
java.lang.NoSuchMethodError: ...
~~~

Use **javap -p -s** on the deployed class and **javap -c -v** on the calling class to check the expected name/descriptor. Then compare JAR versions and classpath order. jdeps can show which library the caller depends on, but **does not by itself prove compatible method linkage**.

A generic method may undergo erasure into a descriptor different from the source. Bridge methods, static vs. instance, access modifiers, and return descriptors also need to be checked. Do not compare method names alone.

### 9.4 UnsupportedClassVersionError

For example, compiling to class-file major 65 (Java 21) and running on Java 17, which only supports up to major 61:

~~~bash
javap -verbose -classpath app.jar lab.app.Main
~~~

Read the **major version** on the actual deployed artifact. Fix it by building with **javac --release 17** if the project supports Java 17 APIs, or by running on an appropriately newer JVM.

### 9.5 ClassCastException “X cannot be cast to X”

If the same binary name is defined by two loaders:

~~~text
Class com.example.Dto (LoaderA)
Class com.example.Dto (LoaderB)
~~~

**javap** can show the bytecode of both artifacts, **jar --list** can confirm both JARs contain com/example/Dto.class, and **jdeps** can show that the shared API type appears in signatures. However, to confirm the root cause, print at runtime:

~~~java
System.out.println(a.getName().equals(b.getName()));
System.out.println(a == b);
System.out.println(a.getClassLoader());
System.out.println(b.getClassLoader());
~~~

The snippet assumes a and b are existing **Class<?>** instances. If the names are equal but a != b, they are two runtime types. The solution is usually to share the API/DTO in one common defining loader and isolate the implementations separately.

### 9.6 LinkageError: Loading Constraint Violation

At the boundary between host/plugin, a method descriptor containing **api.Payload** may require two initiating loaders to agree on the Class for that name. If the plugin defines its own copy of api.Payload different from the host's, a **LinkageError** can occur.

**javap -s** shows which descriptor contains the sensitive type. **jar --list** shows whether the shared DTO class is redundantly packaged. **jdeps -verbose:class** shows caller references. Finally, **runtime loaders/stack trace** confirm the exact Class identities that were incorrectly linked.

**None of these three tools automatically fixes a loader constraint.** You must fix the shared API architecture, delegation, and class identity.

### 9.7 ServiceLoader Cannot Find Provider

Check **META-INF/services/fully.qualified.Service** in the classpath JAR or **module-info.class** with **provides ... with ...** in the named module. **jar --list** shows whether the service config file exists. **javap** confirms the provider class has the corresponding method/constructor; **jdeps** helps uncover the provider's direct dependencies.

If the provider is selected via reflection/service configuration, do not be surprised when jdeps analyzing only the consumer does not report the implementation JAR. The module graph/TCCL lifecycle is also important.

### 9.8 JPMS Module Not Found Error

Verify that the module JAR has **module-info.class** or an automatic module name, and pass the correct **--module-path** and root modules. Use:

~~~bash
jar --describe-module --file suspicious.jar
jdeps --module-path mods --check my.app
~~~

These commands are illustrated based on real module artifacts. **Module path** differs from the classpath; moving a file to the module path can change the module name, readability/exports, and service behavior.

## 10. Investigation Workflow by Layer of Evidence

~~~text
[0] Record runtime JDK, full error/cause, and launcher args
              |
              v
[1] jar --list: does the artifact have class/resource/config at the right path?
              |
              v
[2] jar --describe-module / manifest:
    module-info, Main-Class, Class-Path, Multi-Release?
              |
              v
[3] javap -p -s -c -v:
    bytecode, method descriptors, class version, references?
              |
              v
[4] jdeps -summary / --missing-deps / -verbose:class:
    which class/JAR/module is missing from the dependency graph?
              |
              v
[5] Runtime evidence:
    classpath/module path, ClassLoader, TCCL, Class.getModule,
    class-loading logs, jar/module resolver, plugin lifecycle
              |
              v
[6] Verify fix with a production-like deployment
~~~

Each layer of evidence answers a different question. A developer who sees **lab/impl/GreetingImpl.class** via jar --list still does not know:

- whether that class **is selected** at runtime;
- whether it has a **compatible method descriptor**;
- which ClassLoader defined it;
- whether a transitive dependency or JNI resource is missing;
- whether JPMS access rules allow the caller to use it.

Only by combining multiple pieces of evidence can you arrive at a solid root-cause conclusion.

## 11. Extended Practice: Diagnosing “Right JAR, Wrong Execution”

A typical bug is **having fixed and built the library, yet production still runs the old class**. Procedure:

1. Use **jar --list --file artifact.jar** to verify that the deployed JAR actually contains the expected path.
2. Use **javap -verbose -classpath artifact.jar package.Class** to compare the major version, method descriptors, constant pool, and timestamp/hash if needed.
3. Use **jdeps -verbose:class ... app.jar** to check static references to the expected library artifact.
4. Determine the exact startup **-cp**, **--module-path**, **-jar**, and manifest Class-Path. Do not confuse the local/test JVM command with production.
5. Attach class-loading logging on the failing JVM if appropriate:
   
   ~~~bash
   java -Xlog:class+load=info -cp "app.jar:libs/greeting-lib.jar" lab.app.Main
   ~~~

6. In diagnostic code, print Class.getClassLoader() and ProtectionDomain CodeSource when permitted.
7. Check whether the custom ClassLoader uses **parent-first**, **child-first**, or **caches already loaded classes**; the current Class cannot be changed merely by replacing the JAR file.
8. If two different Class identities already exist, inspect the shared API boundary and the method descriptors subject to loading constraints.
9. Verify the fix on the **exact runtime environment/loader configuration** experiencing the incident, not just on the unit test classpath.

**Note:** The **-Xlog:class+load** option is supported by HotSpot under Unified Logging; the detailed format varies by JVM/JDK. It is a separate runtime data source, not a feature of javap/jar/jdeps.

## 12. Limitations When Using the Three Tools

### 12.1 javap Does Not Prove the Class Was Loaded by the JVM

javap reads the specified artifact. A valid class file is not enough to prove the class loader chose it. It also does not tell you whether the class has been initialized, whether instances exist, or which references the Class object is holding.

### 12.2 jar Does Not “Resolve Dependencies” Just by Listing

jar --list inspects entries; a JAR can be completely valid yet still lack runtime dependencies. Main-Class is not Class-Path; Class-Path in the manifest has its own path resolution rules.

### 12.3 jdeps Is Not a Dynamic Tracer

Do not treat the static graph as complete for every Class.forName, ServiceLoader, JNI, dynamic plugin, or bytecode generation case. In particular, **--ignore-missing-deps** only changes how the tool handles/ignores missing dependencies; it **does not create the missing classes** or guarantee that the program will run.

### 12.4 Dependency Does Not Mean Compatibility

jdeps can see that class A depends on class B, but does not know whether runtime B has the expected **method descriptor** in the deployed version. javap and linkage tests complement this perspective.

### 12.5 The Version of the JDK Tools Also Affects Results

JDK tool options, class-file versions, the JPMS module graph, and disassembler formatting can change. If you run a very old javap on a class file from a newer JDK, it may not understand the new format. Prefer a toolchain matching the Java runtime/artifact under diagnosis and always check **--help**.

### 12.6 Do Not Treat Logging/Inspection as a Sandbox

A JAR from an untrusted source may contain unsafe zip entries, malware, or malicious bytecode. **jar --list/javap/jdeps do not execute the application main**, but extracting and trying to run an untrusted archive still requires an isolated environment, avoiding file overwrites, and following security procedures.

## 13. Command Cheat Sheet

### Bytecode and Signatures

~~~bash
javap -classpath libs/greeting-lib.jar lab.impl.GreetingImpl
javap -classpath libs/greeting-lib.jar -p -s lab.impl.GreetingImpl
javap -classpath libs/greeting-lib.jar -c lab.impl.GreetingImpl
javap -classpath libs/greeting-lib.jar -verbose lab.impl.GreetingImpl
javap -classpath libs/greeting-lib.jar -l lab.impl.GreetingImpl
~~~

### JAR and Manifest

~~~bash
jar --list --file libs/greeting-lib.jar
jar --list --verbose --file app.jar
jar --describe-module --file app.jar
jar --validate --file app.jar
~~~

### Static Dependencies

~~~bash
jdeps -summary app.jar
jdeps --missing-deps app.jar
jdeps -summary -cp libs/greeting-lib.jar app.jar
jdeps -verbose:class -cp libs/greeting-lib.jar app.jar
jdeps -apionly -verbose:class -cp libs/greeting-lib.jar app.jar
jdeps --list-deps -cp libs/greeting-lib.jar app.jar
jdeps --print-module-deps -cp libs/greeting-lib.jar app.jar
~~~

The commands above were run or cross-checked against tool help on OpenJDK 21; results depend on the specific files and JDK.

**Windows:** Use **;** when a classpath contains multiple entries, for example **"app.jar;libs/greeting-lib.jar"**. Commands with exactly one entry **-cp libs/greeting-lib.jar** do not need the separator changed.

## 14. Misconceptions to Avoid

**“jar --list has the class, so the JVM can definitely load it.”** False: classpath/module path, loader policy, access, and dependencies also matter.

**“If jar --validate passes, java -jar cannot fail.”** False: app.jar in the fixture is valid, yet lacks greeting-lib.jar.

**“javap -c gives the exact Java source.”** False: it disassembles JVM instructions and does not recover full source-level semantics.

**“If javap sees a method that the source code has, the runtime Class definitely has that method.”** False: javap may be reading a different artifact from the one the runtime chooses.

**“jdeps --missing-deps having no output means there are no dynamic dependencies.”** False: reflection/services/native/generated classes may fall outside the scope of static analysis.

**“jdeps --print-module-deps prints java.base, so third-party libraries can be omitted.”** False: it returns module names, not all library JARs.

**“Every JAR on the module path is an explicit named module.”** False: a JAR without module-info.class may be an automatic module.

**“Two JARs having a class with the same name definitely causes LinkageError.”** False: class name duplication alone is not enough; consider the defining loader and loading constraints.

**“Same getName() means same runtime Class.”** False: runtime identity also includes the defining ClassLoader.

**“javap/jdeps check code coverage or latency by themselves.”** False: they are static inspection/analysis tools; use a profiler/JFR/coverage agent if you need runtime behavior.

## 15. Self-Check Exercises

**Question 1.** After running jar --list app.jar, you see Main.class but do not see Greeting.class. Is that enough to conclude that app.jar is broken?

**Answer:** Not yet. It may be designed to use a separate dependency JAR. You must check the runtime classpath/manifest and jdeps.

**Question 2.** javap -verbose shows major version 61. Which Java release does it correspond to?

**Answer:** Java 17 class-file version.

**Question 3.** What descriptor does the Java method **String hello(String)** have?

**Answer:** **(Ljava/lang/String;)Ljava/lang/String;**.

**Question 4.** Why does javap -c show invokeinterface when Main calls Greeting.hello?

**Answer:** The static type of the variable in the fixture is the Greeting interface, and the method reference is compiled into invokeinterface.

**Question 5.** Why does jdeps -summary app.jar without a library path have a “not found” line?

**Answer:** Bytecode references to lab.api.Greeting and lab.impl.GreetingImpl could not be resolved by the tool from the currently available input/classpath.

**Question 6.** Does adding **-cp libs/greeting-lib.jar** to jdeps mean that JVM java -jar app.jar will automatically have the library?

**Answer:** No. That is jdeps's analysis configuration, and does not change the manifest or the JVM's runtime classpath.

**Question 7.** Why should -apionly not be used as a complete runtime dependency list?

**Answer:** It focuses on public/protected API signatures, omitting many dependencies inside the implementation.

**Question 8.** ServiceLoader finds providers via META-INF/services. Why might jdeps analyzing only the consumer not show the provider JAR?

**Answer:** Dependency discovery through resource/service metadata may not be reflected as a symbolic class reference in the consumer bytecode.

**Question 9.** What module form can a JAR without module-info.class take on the module path?

**Answer:** An automatic module under the module system; the name can be derived or use Automatic-Module-Name.

**Question 10.** Two different ClassLoaders both define com.example.Dto; what needs to be verified to know whether there is an issue?

**Answer:** Defining loader, Class identity, boundary API signatures, and constraints; two classes with the same name may be valid on their own.

**Question 11.** Which tool is typically used for “java.lang.NoSuchMethodError” to compare method descriptors between two versions?

**Answer:** **javap -s -p** on the exact artifacts; combined with javap -c -v on the caller.

**Question 12.** Why does java -jar app.jar in the fixture not run even though app.jar has Main-Class?

**Answer:** The manifest/launcher does not provide greeting-lib.jar, leaving lab.api.Greeting missing at runtime.

## 16. Summary

~~~text
JAVA CLASS LOADING / LINKING ERROR
                |
                v
       jar: right class/resource/JAR?
                |
                v
       javap: right bytecode, version, descriptor?
                |
                v
       jdeps: which static dependencies are missing or wrong?
                |
                v
       runtime: loader, module, classpath, API identity?
                |
                v
       fix artifact/deployment/loader policy
       then reproduce under the right JVM
~~~

**Remember three sentences:**

- **jar** verifies **exactly what was packaged**.
- **javap** verifies **exactly what was compiled**.
- **jdeps** verifies **what the bytecode statically references**.

All three assist in diagnostics, but **do not replace** runtime evidence about the actual defining loader, parent delegation, module accessibility, runtime-generated classes, and lifecycle.

### Official References

- Oracle Java SE 21 **javap command**: https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html
- Oracle Java SE 21 **jar command**: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jar.html
- Oracle Java SE 21 **jdeps command**: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeps.html
- Oracle Java SE 21 **ClassLoader API**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html
- Oracle Java SE 21 **JAR File Specification**: https://docs.oracle.com/en/java/javase/21/docs/specs/jar/jar.html
- Oracle JVMS **§4 Class File Format**: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html
- Oracle JVMS **§5 Loading, Linking, Initializing**: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html
