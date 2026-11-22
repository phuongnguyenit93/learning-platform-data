# Packaging the agent JAR and META-INF/MANIFEST.MF structure

## 1. Lesson objectives

In Java Instrumentation, a **startup agent** is code loaded by the JVM at startup via the **\`-javaagent\`** parameter. Agents typically install instrumentation hooks, register a **ClassFileTransformer**, or initialize telemetry before the application executes the **\`main\`** method.

This lesson focuses on **packaging and declaring the entry point** for a startup agent: creating a properly structured JAR file, writing **\`META-INF/MANIFEST.MF\`**, building with JDK/Gradle tools, running with **\`-javaagent\`**, inspecting artifacts, and identifying startup errors. The lesson does not require implementing bytecode rewriting; a valid agent can simply log in **\`premain\`** to prove that loading succeeded.

After this lesson, you will be able to:

1. Explain why a JAR file containing an agent class is still **not enough** if it lacks the right manifest attribute.
2. Distinguish between **\`Premain-Class\`**, **\`Main-Class\`**, **\`Agent-Class\`**, and **\`Launcher-Agent-Class\`**.
3. Compile and package an agent JAR yourself that can run on Java 17+.
4. Inspect entries in the JAR, manifest contents, and the invocation order of **\`premain\`** before **\`main\`**.
5. Troubleshoot errors caused by wrong class names, wrong paths, malformed manifests, missing dependencies, or inappropriate capability flags.

## 2. How does the JVM find a startup agent?

Example command:

~~~bash
java -javaagent:out/startup-agent.jar=lab -cp out/app demo.app.HelloApp
~~~

Component breakdown:

- **\`-javaagent:out/startup-agent.jar\`**: instructs the JVM to load the JAR containing the agent at startup.
- **\`=lab\`**: the agent's options string; the JVM passes the raw string **\`lab\`** to **\`premain\`**, without parsing key/value pairs inside it.
- **\`-cp out/app\`**: the classpath containing the application's main class.
- **\`demo.app.HelloApp\`**: the application class with **\`public static void main(String[] args)\`**.

Conceptual sequence:

~~~text
java launcher
   |
   v
JVM receives -javaagent:path[=options]
   |
   v
Open agent JAR, read META-INF/MANIFEST.MF
   |
   v
Look up Premain-Class attribute -> load agent class
   |
   v
Invoke agent's public static void premain(...)
   |
   +--> agent can register transformers / initialize telemetry
   |
   v
premain returns normally
   |
   v
Invoke application's main(...)
~~~

According to the **\`java.lang.instrument\`** specification, when using **\`-javaagent\`**, the manifest **must have \`Premain-Class\`** in the *main section*. The JVM prefers the signature:

~~~java
public static void premain(String agentArgs, Instrumentation inst)
~~~

If the class does not have the two-parameter signature, the JVM tries:

~~~java
public static void premain(String agentArgs)
~~~

Both must be **\`public static\`** and return **\`void\`**. The **\`Instrumentation\`** type belongs to the **\`java.lang.instrument\`** package. Use the two-parameter signature when you need the class transformation/retransformation API. If **\`premain\`** completes successfully, the JVM proceeds to run **\`main\`**; if no valid class/method is found or **\`premain\`** throws an unhandled exception, the JVM aborts application startup.

## 3. What does a valid agent JAR look like?

A JAR is a ZIP file with a structural convention. For example:

~~~text
startup-agent.jar
├── META-INF/
│   └── MANIFEST.MF
└── demo/
    └── agent/
        └── StartupAgent.class
~~~

Inside the JAR, the path **\`demo/agent/StartupAgent.class\`** must correspond to **\`package demo.agent;\`** and the class name **\`StartupAgent\`**. However, the value of **\`Premain-Class\`** is the **fully qualified binary name of the Java class**:

~~~text
Premain-Class: demo.agent.StartupAgent
~~~

Do not use incorrect values such as:

~~~text
Premain-Class: demo/agent/StartupAgent.class
Premain-Class: StartupAgent.java
Premain-Class: out/agent/demo/agent/StartupAgent.class
~~~

### 3.1. Minimal main manifest content

A source file **\`agent.mf\`** can contain:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.StartupAgent

~~~

In the snippet above, the **blank line at the end** terminates the *main section*. When using the **\`jar\`** tool with an external manifest file, make sure there is a trailing newline at the end of the file; a missing newline can cause the last line to be ignored. The manifest file is stored in the JAR at **\`META-INF/MANIFEST.MF\`**; when packaging with **\`jar --manifest\`**, the JDK creates this entry for you.

A more explicit configuration for the sample agent:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.StartupAgent
Can-Redefine-Classes: false
Can-Retransform-Classes: false

~~~

The two **\`Can-...\`** lines here are optional: if omitted, the default value is **\`false\`**. Do not set them to **\`true\`** when the example does not actually need that capability.

### 3.2. MANIFEST.MF syntax rules

- Each attribute is a line of the form **\`Attribute-Name: value\`**, with a **\`:\`** followed by a single space.
- **\`Manifest-Version: 1.0\`** must appear at the start of the main section; a manifest file may have per-entry JAR sections, but a startup agent's **\`Premain-Class\`** must be in the **main section**.
- A **blank line** separates sections. Placing **\`Premain-Class\`** after a blank line in the wrong position may cause it to no longer be a main attribute.
- Each physical line has a limit of **72 UTF-8 bytes**, not 72 Unicode characters. Long values are continued on a new line starting with **a single space**; reliable manifest-generation tools help avoid splitting bytes incorrectly.
- Attribute names within a section must not be duplicated. Content uses UTF-8; avoid generating a BOM or unusual control characters.
- A manifest is not JSON, YAML, or a plain **\`.properties\`** file; do not write **\`Premain-Class=...\`** or arbitrary indentation.

**Note:** You do not need to manually create a **\`META-INF\`** directory in the source directory for the example using **\`jar --manifest\`**. The tool will place the manifest at the standard path inside the JAR.

## 4. Complete hands-on practice on Java 17+

We will create **two separate artifacts**: the agent JAR and the application class. The source code is designed for learners to run themselves, with no external libraries.

### 4.1. Directory tree

Create the structure:

~~~text
agent-jar-lab/
├── agent.mf
├── src/
│   ├── agent/
│   │   └── java/
│   │       └── demo/
│   │           └── agent/
│   │               └── StartupAgent.java
│   └── app/
│       └── java/
│           └── demo/
│               └── app/
│                   └── HelloApp.java
└── out/                 # Created during the build step
    ├── agent/
    ├── app/
    └── startup-agent.jar
~~~

The files under **\`src\`** are the lab code; **\`out\`** holds the compiled output and JAR. The **\`out\`** directory does not need to exist at the start.

### 4.2. Startup agent code

File **\`src/agent/java/demo/agent/StartupAgent.java\`**:

~~~java
package demo.agent;

import java.lang.instrument.Instrumentation;

public final class StartupAgent {
    private StartupAgent() {}

    public static void premain(String agentArgs,
                               Instrumentation instrumentation) {
        System.out.println("agent-premain: " + agentArgs);
        System.out.println(
            "instrumentation-ready: " + (instrumentation != null)
        );
    }
}
~~~

**Explanation:** **\`premain\`** is the entry point invoked by the JVM because of **\`Premain-Class\`**, not **\`Main-Class\`**. The **\`instrumentation\`** parameter is the object provided by the JVM for the agent to instrument classes. The example only verifies that it was passed in; **no \`ClassFileTransformer\` is registered yet** and no bytecode is modified. A private constructor does not prevent the JVM from invoking the static **\`premain\`** method.

### 4.3. Application code to run

File **\`src/app/java/demo/app/HelloApp.java\`**:

~~~java
package demo.app;

public final class HelloApp {
    public static void main(String[] args) {
        System.out.println("app-main");
    }
}
~~~

This application has no knowledge of the agent code. It does not need to import **\`StartupAgent\`** and does not call **\`premain\`** directly.

### 4.4. Writing the agent.mf file

File **\`agent.mf\`**:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.StartupAgent
Can-Redefine-Classes: false
Can-Retransform-Classes: false

~~~

Save the file as UTF-8 and keep the **trailing newline**. The trailing blank line is shown to terminate the main section. The class name must match both the package and class in the source code from step 4.2.

### 4.5. Creating the build directories

In a Bash/Linux/macOS shell, inside the **\`agent-jar-lab\`** directory:

~~~bash
mkdir -p out/agent out/app
~~~

In PowerShell/Windows, use the equivalent command:

~~~powershell
New-Item -ItemType Directory -Force out/agent, out/app
~~~

### 4.6. Compiling and creating the JAR

The following JDK commands work in Bash or PowerShell, as long as the terminal is in the lab root directory:

~~~bash
javac --release 17 -d out/agent src/agent/java/demo/agent/StartupAgent.java
javac --release 17 -d out/app src/app/java/demo/app/HelloApp.java
jar --create --file out/startup-agent.jar --manifest agent.mf -C out/agent .
~~~

Command breakdown:

- **\`javac --release 17\`** compiles targeting the Java 17 API/language; use JDK 17 or newer that supports this option.
- **\`-d out/agent\`** saves **\`StartupAgent.class\`** into **\`out/agent/demo/agent/\`**; **\`-d out/app\`** does the same for the application.
- **\`jar --create\`** creates a new archive; **\`--file\`** sets the output JAR path.
- **\`--manifest agent.mf\`** merges the declared attributes into the JAR's manifest.
- **\`-C out/agent .\`** changes to the agent's class directory when adding contents; therefore the class enters the JAR at **\`demo/agent/StartupAgent.class\`** instead of having the wrong **\`out/agent/\`** prefix.
- Only classes under **\`out/agent\`** are included in the agent JAR; application classes live in **\`out/app\`** to be run with **\`-cp\`**.

The equivalent short option would be **\`jar cfm out/startup-agent.jar agent.mf -C out/agent .\`**. With the short syntax, **the order of \`f\` and \`m\` determines the order of the two arguments**; use the long version for readability and to avoid mistakes.

### 4.7. Running the application with the startup agent

~~~bash
java -javaagent:out/startup-agent.jar=lab -cp out/app demo.app.HelloApp
~~~

Stdout of the example:

~~~text
agent-premain: lab
instrumentation-ready: true
app-main
~~~

The output proves three things: the JVM read **\`Premain-Class\`** and invoked the right class; the string **\`lab\`** was passed into **\`agentArgs\`**; **\`premain\`** ran before the application's **\`main\`**. It does **not** yet prove that any method had bytecode injected.

Compare when running without the agent:

~~~bash
java -cp out/app demo.app.HelloApp
~~~

Stdout is only:

~~~text
app-main
~~~

## 5. Inspecting the JAR and manifest after building

You should not conclude that an agent is packaged correctly just because a **\`.jar\`** file was created.

### 5.1. Listing actual entries

~~~bash
jar --list --file out/startup-agent.jar
~~~

With the JDK and build commands above, the key entries include:

~~~text
META-INF/
META-INF/MANIFEST.MF
demo/
demo/agent/
demo/agent/StartupAgent.class
~~~

The listing must contain both **\`META-INF/MANIFEST.MF\`** and **\`demo/agent/StartupAgent.class\`**. A JAR containing only **\`.java\`** source files, or a class at the wrong package path, does not meet the example's requirements.

### 5.2. Reading main attributes with the Java API

Create **\`InspectJar.java\`** at the root of the lab directory:

~~~java
import java.util.jar.JarFile;

public class InspectJar {
    public static void main(String[] args) throws Exception {
        try (JarFile jar = new JarFile(args[0])) {
            var attrs = jar.getManifest().getMainAttributes();
            System.out.println(
                "Premain-Class=" + attrs.getValue("Premain-Class")
            );
            System.out.println(
                "class-present=" +
                (jar.getEntry("demo/agent/StartupAgent.class") != null)
            );
        }
    }
}
~~~

Run using Java 17+'s source-file launcher:

~~~bash
java InspectJar.java out/startup-agent.jar
~~~

Stdout:

~~~text
Premain-Class=demo.agent.StartupAgent
class-present=true
~~~

Using **\`JarFile.getManifest().getMainAttributes()\`** reads **the actually packaged manifest**, avoiding confusion between **\`agent.mf\`** in the source directory and **\`META-INF/MANIFEST.MF\`** in the final artifact. If **\`getManifest()\`** returns **\`null\`**, the JAR has no manifest to read; this example will fail and you need to recheck the build process.

### 5.3. Three layers of evidence that must align

| What to confirm | How to check | Expected result in the example |
|---|---|---|
| Manifest is present in the JAR | **\`jar --list\`** | Has **\`META-INF/MANIFEST.MF\`** |
| Entry point maps to the right class | **\`InspectJar\`** | **\`Premain-Class=demo.agent.StartupAgent\`**, class-present=true |
| JVM invokes the agent before the application | Run with **\`-javaagent\`** | **\`agent-premain\`** appears before **\`app-main\`** |

This is a simple yet valuable verification: if you only inspect the manifest file in source, you might miss the case where the build tool generates the JAR with a different manifest.

## 6. Manifest attributes related to Java agents

| Attribute | When to use | Meaning and notes |
|---|---|---|
| **\`Manifest-Version\`** | Standard manifest files | Starts the main section, e.g. **\`1.0\`** |
| **\`Premain-Class\`** | **Required for \`-javaagent\`** | Fully qualified name of the class defining **\`premain\`** |
| **\`Agent-Class\`** | Agent attached to a running JVM, if supported by the VM | Name of the class defining **\`agentmain\`**; does not replace **\`Premain-Class\`** for **\`-javaagent\`** |
| **\`Launcher-Agent-Class\`** | Agent bundled with an executable JAR, if supported by the launcher | Launcher invokes **\`agentmain\`** before **\`main\`**; this is a separate mechanism |
| **\`Main-Class\`** | Application JAR run with **\`java -jar\`** | Specifies **\`main\`**, does not make the JAR a startup agent |
| **\`Can-Redefine-Classes\`** | Agent needs **\`Instrumentation.redefineClasses\`** | Boolean; default **\`false\`**; also depends on VM support |
| **\`Can-Retransform-Classes\`** | Agent needs **\`Instrumentation.retransformClasses\`** | Boolean; default **\`false\`**; enable only when actually used |
| **\`Can-Set-Native-Method-Prefix\`** | Very specific cases involving native method prefixes | Boolean; default **\`false\`** |
| **\`Boot-Class-Path\`** | Need to provide classes to the bootstrap loader | Optional, affects low-level class loading; avoid adding unless required |
| **\`Class-Path\`** | Declare dependency JARs per JAR manifest rules | Relative URLs are resolved against the JAR context; corresponding libraries must be packaged/deployed |

**Capability flags are not an instrumentation operation.** For example, **\`Can-Retransform-Classes: true\`** only requests the ability to retransform; it does not transform classes on its own. In agent code, you can query **\`instrumentation.isRetransformClassesSupported()\`** before calling the API. A capability also depends on the JVM implementation, and redefine/retransform operations have their own limitations.

You should also not add **\`Can-Redefine-Classes: true\`** or **\`Boot-Class-Path\`** just "to be safe". The set of attributes should accurately reflect what the agent will actually do.

## 7. Distinguishing entry points by launch mode

The following three cases use the term "agent" but are not synonymous:

~~~text
A) JVM startup with -javaagent
   agent.jar + Premain-Class --> premain(...)
   app classes               --> main(...)

B) Attaching an agent to a running JVM (if supported)
   agent.jar + Agent-Class   --> agentmain(...)

C) Executable JAR containing a launcher agent (if supported)
   app.jar + Launcher-Agent-Class --> agentmain(...)
   app.jar + Main-Class           --> main(...)
~~~

- With **\`java -javaagent:agent.jar ...\`**, the JVM reads **\`Premain-Class\`**; even if **\`Agent-Class\`** is declared, it does not cause the JVM to invoke **\`agentmain\`** in this startup path.
- When attaching an agent after the JVM is running, **\`Agent-Class\`** and **\`agentmain\`** are the corresponding pair. The attach mechanism also depends on JVM version, configuration, and permissions, which is outside the scope of this startup packaging lesson.
- With an executable JAR having **\`Launcher-Agent-Class\`**, the Java launcher uses **\`agentmain\`** for the bundled agent; although it runs before **\`main\`**, it is still not the **\`-javaagent\`** mechanism.
- A JAR can contain multiple related attributes if it genuinely supports multiple launch modes, but **each launch mode reads the attribute appropriate to it**.

From this follows a very common mistake: **adding \`Main-Class: demo.agent.StartupAgent\` does not replace \`Premain-Class\`**. A class with **\`premain\`** that lacks the startup attribute still will not be loaded via **\`-javaagent\`** as expected.

## 8. Integrating packaging into Gradle

For a Gradle project using the **\`java\`** plugin, place the agent class at **\`src/main/java/demo/agent/StartupAgent.java\`**. Example **\`build.gradle\`** (Groovy DSL):

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.named('jar') {
    manifest {
        attributes(
            'Premain-Class': 'demo.agent.StartupAgent',
            'Can-Redefine-Classes': 'false',
            'Can-Retransform-Classes': 'false'
        )
    }
}
~~~

Run in a project with Gradle Wrapper:

~~~bash
./gradlew jar
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat jar
~~~

Normally the artifact is located in **\`build/libs/\`** named after the project and version. Inspect it with **\`jar --list\`** and **\`InspectJar\`** as in section 5, then launch using the actual JAR path.

### What Gradle does not do automatically

The default **\`jar\`** task packages the output of the configured source set and the declared manifest, but **does not automatically bundle all dependency JARs from \`implementation\` inside**. If the agent uses additional libraries, design a clear dependency distribution strategy (for example, accompanying dependency JARs and an appropriate loading path, or a *shaded/fat JAR* when needed), and verify by actually running the agent.

If you choose a shaded JAR, you must handle resource/**\`META-INF\`** conflicts, original JAR signatures, and proper relocation. Having a correct manifest alone is **not enough** if the JVM cannot load the library classes used by **\`StartupAgent\`**.

Do not mix the application's **\`Main-Class\`** into the agent JAR just for quick testing, unless the artifact is genuinely designed as a combined executable application and agent with both entry points clearly defined. The example in section 4 separates the two JARs/classpaths to make responsibilities easy to verify.

## 9. Class loading and dependency issues when packaging

A startup agent runs in the **same JVM** as the application, not in an independent process. The use of class loaders and agent code can affect application startup or behavior:

1. **Package names and class paths:** The manifest only supplies the class name; the JVM must still find the bytecode at the exact entry inside the JAR. Do not archive the **\`out/agent\`** directory itself as a path prefix inside the archive.
2. **External dependencies:** If the agent class references a helper class but the helper/JAR is not where the JVM searches, startup may fail with **\`ClassNotFoundException\`** or **\`NoClassDefFoundError\`**.
3. **Manifest \`Class-Path\`:** This attribute declares paths to additional JARs per the JAR specification. If used, relative paths must match the distribution layout (for example, **\`libs/helper.jar\`** alongside the agent); do not assume the application's **\`-cp\`** always resolves all of the agent's dependencies.
4. **Bootstrap classes:** The bootstrap loader's search path differs from the application's search path. **\`Boot-Class-Path\`** and appending JARs to the bootstrap search path are advanced topics; misconfiguration can cause conflicts with wide impact.
5. **Compatibility:** The agent class and its libraries must be compatible with the target Java runtime. For example, compiling with **\`--release 17\`** helps avoid producing class files that require a runtime newer than Java 17.
6. **Code running in \`premain\`:** Do not run long tasks, depend on services that are not yet ready, or throw unhandled errors. If the agent fails, **the application may fail to start**.

When distributing across multiple environments, use a tested JAR artifact, clearly specify versions and dependencies, and evaluate the trust of the agent's source because an agent has the ability to tamper with bytecode and JVM behavior.

## 10. Common errors and how to diagnose them

| Symptom | Cause to check | Resolution |
|---|---|---|
| JVM reports missing **\`Premain-Class\`** or fails to start with **\`-javaagent\`** | JAR was packaged with default settings without importing the agent manifest | Inspect **the manifest inside the JAR**, rebuild with **\`--manifest\`** |
| JVM cannot load the agent class | **\`Premain-Class\`** value does not match package/class name; wrong class entry | Compare **\`demo.agent.StartupAgent\`** with **\`demo/agent/StartupAgent.class\`** |
| JVM reports no suitable **\`premain\`** found | Wrong method name, not **\`public static\`**, wrong parameters, or wrong return type | Use one of the two signatures in section 2 |
| Class name is correct but startup fails when loading | Missing dependency class, incompatible Java version, or static initializer error | Check stack trace, dependencies, **\`javap\`**/**\`jar --list\`**, runtime JDK |
| JVM exits after logging in **\`premain\`** | Agent threw an unhandled exception/error | Read root cause; keep agent initialization lean, report useful errors |
| Only **\`app-main\`** appears, no **\`agent-premain\`** | Application was run without **\`-javaagent\`** or option was placed in the wrong position | Place **\`-javaagent\`** in the JVM options group **before** the main class name or **\`-jar\`** |
| **\`Can-Retransform-Classes\`** is declared but API is unavailable | JVM does not support it or manifest/build did not actually declare it properly | Check **\`isRetransformClassesSupported()\`**, packaged manifest, and VM limits |
| Manifest has **\`Premain-Class\`** in source but not in the JAR | Build config overwrites/imports wrong manifest, last line lacks newline, wrong section | Use **\`InspectJar\`**, check build task and **\`agent.mf\`** format |
| Running **\`java -jar startup-agent.jar\`** reports missing main | Agent JAR has no **\`Main-Class\`** and is not meant to run as an application | Use **\`java -javaagent:... -cp ...\`**; distinguish the two mechanisms |

### 10.1. JVM option placement matters

Correct:

~~~bash
java -javaagent:out/startup-agent.jar=lab -cp out/app demo.app.HelloApp
~~~

Also a valid JVM option when running an executable application JAR:

~~~bash
java -javaagent:out/startup-agent.jar=lab -jar my-app.jar
~~~

Conversely, strings placed **after** the main class name or **after \`-jar my-app.jar\`** are usually passed as **application arguments**, and are no longer interpreted by the Java launcher as an option to enable the agent:

~~~text
java -jar my-app.jar -javaagent:out/startup-agent.jar
                         ^ application argument, does not enable agent
~~~

### 10.2. Do not confuse file naming

- **\`agent.mf\`** is the input text file you create in the project directory.
- **\`META-INF/MANIFEST.MF\`** is the standard manifest entry **inside the built JAR**.
- **\`startup-agent.jar\`** is the packaged ZIP/JAR file passed to **\`-javaagent\`**.
- **\`demo.agent.StartupAgent\`** is the Java class name used in the **\`Premain-Class\`** attribute value.
- **\`demo/agent/StartupAgent.class\`** is the bytecode entry path inside the JAR.

These five strings are related to each other, but **cannot be used interchangeably**.

## 11. Practice exercises and self-check

### Exercise A — renaming the agent without breaking the manifest

Change the package from **\`demo.agent\`** to **\`lab.instrument\`** and move the file to **\`src/agent/java/lab/instrument/StartupAgent.java\`**. Then update **\`Premain-Class: lab.instrument.StartupAgent\`** and rebuild. Verify **\`lab/instrument/StartupAgent.class\`** in the JAR. If you only update the source without updating the manifest, explain why the JVM cannot find the class.

### Exercise B — passing configuration

Run:

~~~bash
java -javaagent:out/startup-agent.jar=mode=debug,tag=demo -cp out/app demo.app.HelloApp
~~~

Observe the agent log line: the string is passed verbatim as **\`mode=debug,tag=demo\`**. Write your own parser in the agent if you want to split **\`mode\`** and **\`tag\`**; the JVM does not automatically create a Map for this parameter.

### Exercise C — explicitly checking capability limits

In **\`premain\`**, try printing:

~~~java
System.out.println(
    "retransform-supported: " +
    instrumentation.isRetransformClassesSupported()
);
~~~

Compare when the manifest does/does not have **\`Can-Retransform-Classes: true\`** on your test JVM. Do not assume that every JVM supports it; the API reflects the actual capability negotiated when the agent starts. For the current lesson, there is no need to call **\`retransformClasses\`**.

### Self-assessment questions

**1. Is \`Main-Class\` required in an agent JAR run with \`-javaagent\`?**  
No. **\`Premain-Class\`** is required; **\`Main-Class\`** is for running an application with **\`java -jar\`**.

**2. Why is a Java class with \`premain\` not enough?**  
Because the launcher needs to know **which class contains the method** via the agent JAR's main manifest.

**3. Is \`Premain-Class: demo/agent/StartupAgent.class\` valid?**  
No. You must specify the fully qualified Java class name: **\`demo.agent.StartupAgent\`**.

**4. Does enabling \`Can-Retransform-Classes: true\` automatically modify classes?**  
No. This only declares the required capability; the agent must still call the corresponding API and obey VM capabilities.

**5. How can you prove the manifest actually made it into the JAR?**  
Use **\`jar --list\`** to confirm the entry and **\`JarFile.getManifest()\`** to read the packaged attributes; then run with **\`-javaagent\`**.

**6. If stdout shows \`agent-premain\` before \`app-main\`, does that prove bytecode was transformed?**  
No. It only proves the agent was loaded and **\`premain\`** ran successfully.

## 12. Conclusion and authoritative references

A startup agent using **\`-javaagent\`** must have a **valid JAR**, a **valid \`premain\` class**, and **\`Premain-Class\` in \`META-INF/MANIFEST.MF\`** pointing to the exact class name. After packaging, you must inspect the **contents of the actual JAR** and confirm that the **JVM invokes \`premain\` before \`main\`**. Only then should you add transformers, metrics, or more complex instrumentation features.

Official documentation:

- [Java SE 17 — java.lang.instrument package specification](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): specifies **\`-javaagent\`**, **\`premain\`** signatures, manifest entries, and JVM capabilities.
- [Java SE 17 — JAR File Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html): manifest syntax, sections, continuation lines, byte limits, and **\`Main-Class\`**/**\`Class-Path\`** attributes.
- [JDK jar command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html): creating and inspecting JARs with **\`--manifest\`**, **\`-C\`**, **\`--list\`**.