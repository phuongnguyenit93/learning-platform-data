# Checking java.instrument, jdk.attach, and Required Modules in a Custom Runtime

When packaging a Java application with **jlink** or **jpackage** using a **custom runtime image**, the program may run fine on the development JDK while the Java agent fails to start, or an attach tool cannot load an agent into a running JVM. Common causes include **a stripped-down runtime missing required modules**, confusing the roles of **java.instrument** and **jdk.attach**, or missing non-module requirements (manifest, JVM support, OS permissions, class loader, modules for logging/JMX/JFR, and agent libraries).

Points to distinguish immediately:

- **java.instrument** provides **java.lang.instrument.Instrumentation**, **ClassFileTransformer**, and the mechanism supporting Java agents. The **target** runtime using **-javaagent** or receiving a dynamically loaded **Java agent** needs appropriate instrumentation capability, typically including this module.
- **jdk.attach** provides **com.sun.tools.attach.VirtualMachine**, **AttachProvider**, and the API for **a tool that actively connects to another JVM**. It is needed in the **attach client runtime**. On HotSpot Java 17+, **the target JVM does not necessarily need to contain jdk.attach** just to receive an agent from an external client.
- **Having the module does not guarantee the feature will work**. The agent JAR still needs a valid manifest/callback; attach also depends on the JVM implementation, OS permissions, PID namespace, JVM flags, and an agent JAR path readable by the target JVM.
- **jdeps is only a starting point**. It analyzes static dependencies detectable in class files; modules used via reflection, service loading, JNI, plugins, or agent mechanisms may need to be added manually when running **jlink --add-modules**.

This guide targets **Java 17 and above**, uses **Java 17 APIs and runnable build commands**, distinguishes three runtime images (running a startup agent, running an attach client, and both), provides an agent example with **premain + agentmain**, module probing with **ModuleFinder**, a real attach client, a missing-module negative test, and a deployment/CI checklist. Environment results explicitly note what depends on the JDK/vendor/OS.

## 1. Overview Diagram: Target Runtime and Tool Runtime

Imagine a service running on machine or container A, while an administrative tool needs to load an agent into that service:

~~~text
BUILD JDK (has jlink, jdeps, javac, jar)
    |
    |-- creates target runtime-image
    |      ├── java.base
    |      ├── java.instrument   <-- needed for Java agent on target side
    |      └── business/monitoring modules actually used
    |
    |-- creates client runtime-image
           ├── java.base
           └── jdk.attach       <-- contains Attach API on client side

PRODUCTION / TARGET PROCESS
  rt-target/bin/java -javaagent:probe-agent.jar ...  (startup agent)
          or
  rt-target/bin/java -cp ... Target                 (waiting for attach)
                     ^
                     | Attach API / JVM attach mechanism
                     |
ADMIN / CLIENT PROCESS
  rt-client/bin/java -cp ... AttachClient PID agent.jar
       |
       └── VirtualMachine.attach(PID), loadAgent(path), detach()
~~~

**Two processes can use two different runtime images.** If the agent is only started with **-javaagent**, **jdk.attach is typically not needed in the target image**. If the tool only performs attach from outside, **the client needs jdk.attach** but does **not require java.instrument** itself to call VirtualMachine.loadAgent. A target that wants to receive a **Java agent** still must have the Java instrumentation mechanism and attach permissions available.

In an application that *attaches to itself*, both roles live in one JVM; in that case, both modules/capabilities and self-attach restrictions must be considered. This is **not** a recommended workflow for every application.

## 2. Module Selection Table by Scenario

| Need | Executing Runtime | Module to Check | Other Conditions |
| --- | --- | --- | --- |
| Run **-javaagent:agent.jar** at startup | **Target JVM** | **java.instrument** | Premain-Class, valid premain, readable jar |
| Agent uses **ClassFileTransformer** | **Target JVM** | **java.instrument** | Correct classloader, valid bytecode, capabilities if needed |
| Attach API calls **VirtualMachine.attach(pid)** | **Client JVM** | **jdk.attach** | Supporting provider, PID, OS rights |
| Attach API calls **loadAgent(agent.jar)** | Client + Target | **jdk.attach on client**, **java.instrument on target** | Target allows attach, Agent-Class/agentmain, JAR visible on target |
| Client self-attaches to the same JVM | Same JVM | Usually **jdk.attach + java.instrument** | JVM self-attach policy, not allowed by default |
| **JMX / ManagementFactory** | JVM with that component | **java.management** | Export/management config, network if remote |
| **HotSpotDiagnosticMXBean** | JVM using that API | **jdk.management**, dependencies | Vendor/API availability dependent |
| **Java Flight Recorder APIs** | JVM using JFR | **jdk.jfr** | JVM JFR support, file/path/permissions |
| **Remote JMX management agent** | Target | May need **jdk.management.agent**, java.management.rmi, and dependencies | Network permissions, credentials/TLS, and management config |
| **Debug with JDWP** | Debug JVM | **jdk.jdwp.agent** or vendor-specific modules | -agentlib:jdwp, port/transport/security |
| **jcmd** as a serviceability tool | Runtime containing tool | **jdk.jcmd** and appropriate dependencies | Image has the tool; attach mechanism must still allow it |
| Logging using java.util.logging | Runtime containing code | **java.logging** | Handler config/file permissions |
| Framework using sun.misc.Unsafe | Runtime containing code | May need **jdk.unsupported** | Consider replacing internal API; check vendor |
| JDBC, XML, DNS, crypto providers, charsets, locale | Runtime containing code | **java.sql, java.xml, jdk.naming.dns, jdk.crypto.ec, jdk.charsets, jdk.localedata** when actually needed | Provider/service binding and runtime data |

The list above is **not a mandatory configuration for every application**. The goal of jlink is to bundle **the exact modules for the application + agent + tools** actually needed, along with their corresponding dependencies, not to cram every JDK module into an image to avoid errors.

### 2.1. java.instrument is the agent module, not the agent JAR

The **java.instrument** module only provides the Java platform API/VM integration. The **agent logic** still resides in the **agent.jar** you distribute, containing **Premain-Class**, **Agent-Class**, or both. Simply adding java.instrument to the image does not automatically generate a transformer, does not cause the agent to load automatically, and does not provide the agent's own libraries such as ASM/Byte Buddy.

A startup agent can be activated with:

~~~bash
rt-target/bin/java -javaagent:probe-agent.jar -cp out/classes Probe
~~~

Meanwhile, an agent loaded after startup uses a process with the Attach API to call **VirtualMachine.loadAgent(...)**. These are two paths at **different phases**; the same JAR can support both if the manifest and callbacks are fully declared.

### 2.2. jdk.attach does not “enable attach permission” in the target

**jdk.attach** contains the API used on the **client** side. A HotSpot target that does not contain this module can still accept external attach via the VM's attach mechanism, if the target has appropriate runtime support and is not blocked. Adding jdk.attach to the target **does not automatically fix**:

- The JVM being started with **-XX:+DisableAttachMechanism**.
- The OS/container preventing the client from seeing the PID or communicating over the attach socket.
- Different user/permissions, security policy, or an incompatible attach provider.
- The target lacking **java.instrument** or not supporting dynamic Java agent loading.
- Missing **Agent-Class/agentmain**, or the agent JAR existing only on the client's filesystem.

**Diagnose the right role:** when the client hits **NoClassDefFoundError: com/sun/tools/attach/VirtualMachine**, check **the client's jdk.attach**. When the target reports it cannot find the instrumentation library/module while running **-javaagent**, check **the target's java.instrument**.

## 3. How does jlink build a custom runtime?

**jlink** takes the **root modules** in **--add-modules**, resolves and packages their **transitive module dependencies**, and creates a runtime image for the OS/architecture of the build JDK.

~~~bash
# Image only for startup Java agent and target receiving agents.
jlink --add-modules java.base,java.instrument \
      --output rt-target

# Image for client calling Attach API.
jlink --add-modules java.base,jdk.attach \
      --output rt-client

# Image needing both roles in the same runtime.
jlink --add-modules java.base,java.instrument,jdk.attach \
      --output rt-full
~~~

These are **JDK build** commands, not run with **rt-target/bin/jlink**. Custom images typically do not contain development commands like **javac/jlink/jdeps/jar** unless you explicitly include those tool modules in the image. The image should be built with a JDK matching the target version, vendor, and OS/architecture; do not assume a Linux x86-64 image is portable to Windows or ARM.

**You do not need to list every transitive dependency manually.** For example, the jdk.attach module may pull in an attach provider module; inspect the actual output image rather than hardcoding a dependency list across all JDKs.

### 3.1. Module path syntax

If only linking JDK modules, **jlink** looks for them by default in the **jmods** directory of the build JDK. For truly modular applications, you can point **--module-path** to the application's JMOD/JAR directory along with the JDK modules and include the application module name in **--add-modules**.

~~~bash
# Reference example for a modular application with module demo.app in mods.
jlink --module-path "$JAVA_HOME/jmods:mods" \
      --add-modules demo.app,java.instrument,jdk.attach \
      --output rt-modular
~~~

The **:** separator between module-path entries suits Linux/macOS; Windows uses **;**. This example is only valid when **mods** already contains a valid demo.app module and JAVA_HOME points to a JDK with jmods. If the application is run on the **classpath**, you can create a runtime solely from JDK modules like the first three commands and **distribute the application JARs separately**.

### 3.2. Not every module is resolved in the boot layer

There are three states to distinguish:

1. Module **present in the build JDK** (the input set for jlink).
2. Module **linked into the runtime image** (visible via **--list-modules**).
3. Module **resolved into the boot layer of a specific process** (checkable via **ModuleLayer.boot().findModule(...)**).

For **named modules**, dependencies need to be resolved via **requires**, launcher root module selection, and when appropriate **--add-modules**. Having a module in the image is the condition for it to *be able* to be resolved; it does not by itself prove that classes in every process can already read that module.

**--add-modules jdk.attach** on an already-linked image that lacks jdk.attach **cannot conjure the module out of thin air**; you must rebuild the image with that module first.

## 4. Inspecting the Runtime Image Directly Before Deployment

Do not rely on the output of **java --list-modules** from the development JDK if production uses **rt-target/bin/java**. Always run the exact binary that production will use.

### 4.1. Checking version and java.home

~~~bash
./rt-target/bin/java -version

./rt-target/bin/java -XshowSettings:properties -version
~~~

In the properties output, check **java.home**, **java.version**, **java.vendor**, and **os.arch**. This helps detect when a container/app launcher is running the **system JDK** instead of the **custom runtime image** produced by the build. If the output is long, you can filter it in CI; however, capture stderr as well because version/settings commands usually print to stderr.

### 4.2. Listing modules actually present in the image

~~~bash
./rt-target/bin/java --list-modules
./rt-client/bin/java --list-modules
./rt-full/bin/java --list-modules
~~~

Example output structure (version tags depend on the build JDK):

~~~text
# rt-target:
java.base@<runtime-version>
java.instrument@<runtime-version>

# rt-client:
java.base@<runtime-version>
jdk.attach@<runtime-version>
jdk.internal.jvmstat@<runtime-version>

# rt-full:
java.base@<runtime-version>
java.instrument@<runtime-version>
jdk.attach@<runtime-version>
jdk.internal.jvmstat@<runtime-version>
~~~

This is an **illustration from the tested HotSpot build**, not a guarantee that dependent modules will have the exact same names/set on every JVM. Do not strip transitive modules from the image by manually manipulating files.

### 4.3. Viewing each module's description

~~~bash
./rt-full/bin/java --describe-module java.instrument
./rt-full/bin/java --describe-module jdk.attach
./rt-full/bin/java --validate-modules
~~~

**--describe-module** provides the module descriptor from the runtime image; **--validate-modules** helps check for certain module conflicts. If a module is missing, describe-module reports that it was not found. However, **--validate-modules succeeding** does not prove that the agent JAR is valid or that attach is permitted by the OS.

### 4.4. Distinguishing available vs. resolved modules in Java

You can check via the Java API:

~~~java
// Illustration snippet from a running JVM.
boolean available = java.lang.module.ModuleFinder.ofSystem()
        .find("java.instrument").isPresent();

boolean bootResolved = ModuleLayer.boot()
        .findModule("java.instrument").isPresent();
~~~

**ModuleFinder.ofSystem()** checks system modules available in the current runtime. **ModuleLayer.boot()** checks modules resolved for the process. The two checks answer two different questions. The complete program example in section 6 will print these values.

## 5. jdeps Helps Find Modules, but Cannot Find All Dynamic Dependencies

**jdeps** analyzes dependencies at the class file level and produces output suited for jlink:

~~~bash
jdeps --print-module-deps --multi-release 17 app.jar
jdeps --print-module-deps --multi-release 17 agent.jar
~~~

The output is usually a **comma-separated list of modules**. You can pass this list as input to **jlink --add-modules**, after verifying/merging any root modules used at runtime.

For the demo below, running the analysis on just the agent and client classes gives minimal results:

~~~bash
jdeps --print-module-deps probe-agent.jar
jdeps --print-module-deps out/classes/AttachClient.class
~~~

Output observed on the test JDK:

~~~text
java.base,java.instrument
java.base,jdk.attach
~~~

This clearly illustrates the roles: **RuntimeAgent** code uses **java.lang.instrument**, and **AttachClient** code imports **com.sun.tools.attach.VirtualMachine**. However, the **target application** might only import **java.base** in its source, while still needing **java.instrument** because an agent is specified with **-javaagent**. If you only run **jdeps app.jar**, you may **miss the critical module for the startup agent**.

### 5.1. Dependencies jdeps often cannot see completely

- **Class.forName("...")** and class names assembled dynamically from configuration.
- **ServiceLoader** and **provider modules** not made explicit when linking the image.
- Agents loaded via **-javaagent**, **Attach API**, or a JAR name outside the application JAR.
- Native JNI/JVM TI code calling Java classes or requiring external native libraries.
- Directory-based plugin discovery or custom classloaders.
- A library only calling code from a certain module under a feature flag or during error handling.
- Bytecode generation creating references to classes/helpers after the process has started.
- Deep reflection requiring **--add-opens**, which is a separate issue from simply having the module in the image.
- Multi-release JARs having classes that depend on different modules across JDK versions.

Do not use **--ignore-missing-deps** to hide problems and conclude the image is valid; only use it when you understand the ignored dependency and have a corresponding runtime test.

### 5.2. How to assemble module roots for a product

1. Run **jdeps** on **application artifacts** and the **agent JAR**, not just the main class.
2. Read source/config for **Attach API** usage or external monitoring tools.
3. Add **java.instrument** if the target uses a startup/dynamic Java agent.
4. Add **jdk.attach** **to the client runtime** if the client calls the Attach API.
5. Add appropriate JMX/JFR/logging/JDBC/service provider modules needed by the agent or app.
6. Run jlink with the verified root modules; do not rely on a fixed dependency list applied to every project.
7. Run smoke/integration tests **using the finished image**, not the full JDK.
8. Re-verify after every change to JDK/vendor, agent version, framework, OS image, or packaging configuration.

**jlink --bind-services** can pull in additional provider modules via service binding; evaluate its size impact and test it rather than treating it as a mandatory option for every agent.

## 6. Runnable Java 17 Example: Three Runtime Images, Startup Agent, and Attach

The example uses **four Java files and one manifest**. It uses no external libraries, requiring only JDK 17+ to compile and create images with jlink. Code:

- **Probe**: prints which modules are present in the runtime image and whether the jdk.attach module is resolved in the boot layer.
- **RuntimeAgent**: has **premain** for startup and **agentmain** for dynamic attach.
- **Target**: a running process creating a window of time for the client to attach.
- **AttachClient**: uses **VirtualMachine.attach(pid)** followed by **loadAgent**.

**This is an example for a test environment you control**, running two processes on the same machine/OS with an appropriate user. Do not attach to arbitrary processes you do not have permission to manage.

### 6.1. Directory structure

~~~text
runtime-modules-demo/
  src/
    Probe.java
    RuntimeAgent.java
    Target.java
    AttachClient.java
  agent.mf
  out/
    classes/               <- created by javac
  probe-agent.jar           <- created by jar
  rt-target/                <- created by jlink
  rt-client/                <- created by jlink
  rt-full/                  <- created by jlink
~~~

The classes in the **default package** are only to keep the learning commands simple. When packaging a product, use a proper package and ensure the manifest points to the exact **binary class name**.

### 6.2. File src/Probe.java

~~~java
import java.lang.module.ModuleFinder;

public final class Probe {
    private Probe() {
    }

    public static void main(String[] args) {
        System.out.println("HAS_INSTRUMENT="
                + ModuleFinder.ofSystem()
                        .find("java.instrument").isPresent());

        System.out.println("HAS_ATTACH="
                + ModuleFinder.ofSystem()
                        .find("jdk.attach").isPresent());

        System.out.println("ATTACH_RESOLVED="
                + ModuleLayer.boot()
                        .findModule("jdk.attach").isPresent());

        System.out.println("PROBE_OK");
    }
}
~~~

**ModuleFinder.ofSystem().find** does not import **java.lang.instrument** or **com.sun.tools.attach**. It only queries the module graph/catalog in the **runtime executing Probe**. This is useful when the probe must be able to run even on a minimal image without java.instrument or jdk.attach.

**ATTACH_RESOLVED** shows whether jdk.attach is already in the boot layer. If the image has the module but it is not resolved under the current launch mode, you may need appropriate **requires** or **--add-modules jdk.attach** configuration; --add-modules cannot substitute for the jlink inclusion step.

### 6.3. File src/RuntimeAgent.java

~~~java
import java.lang.instrument.Instrumentation;

public final class RuntimeAgent {
    private RuntimeAgent() {
    }

    public static void premain(
            String options, Instrumentation inst) {
        System.out.println("PREMAIN_OK");
        System.out.println("RETRANSFORM="
                + inst.isRetransformClassesSupported());
    }

    public static void agentmain(
            String options, Instrumentation inst) {
        System.out.println("AGENTMAIN_OK");
    }
}
~~~

Here **premain** receives **Instrumentation** directly from the JVM when **-javaagent** is active; **agentmain** receives Instrumentation when the agent is loaded after startup. Do not instantiate Instrumentation with new, and do not use a guessed singleton. To keep the exercise focused on **runtime modules**, the agent does not register a ClassFileTransformer.

**RETRANSFORM=false** in the sample output occurs because the manifest in this example **does not declare Can-Retransform-Classes: true**. Having java.instrument does not mean every optional capability is enabled. If a real agent needs retransform/redefine/native prefix, it must declare the needed capabilities in the manifest, check **isRetransformClassesSupported() / isRedefineClassesSupported() / isNativeMethodPrefixSupported()**, and handle class modification limits.

### 6.4. File src/Target.java

~~~java
public final class Target {
    private Target() {
    }

    public static void main(String[] args)
            throws InterruptedException {
        System.out.println("TARGET_READY");
        Thread.sleep(15000);
        System.out.println("TARGET_END");
    }
}
~~~

This class creates **a target JVM** that stays alive for 15 seconds so the client has a chance to attach. The duration is chosen for simplicity and is not suitable for tests running on very slow CI machines. In real production tests, use a service/ready signal with a controlled lifecycle rather than relying solely on sleep.

### 6.5. File src/AttachClient.java

~~~java
import com.sun.tools.attach.VirtualMachine;
import java.nio.file.Path;

public final class AttachClient {
    private AttachClient() {
    }

    public static void main(String[] args)
            throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: AttachClient PID agent.jar");
        }

        String pid = args[0];
        String agentJar = Path.of(args[1])
                .toAbsolutePath().toString();

        VirtualMachine vm = VirtualMachine.attach(pid);
        try {
            vm.loadAgent(agentJar, "smoke");
            System.out.println("ATTACH_OK");
        } finally {
            vm.detach();
        }
    }
}
~~~

**VirtualMachine.attach** in the **client process** opens a connection to the target according to the JDK/OS provider. **loadAgent** passes **the JAR path for the target to read** and causes the target to invoke **agentmain**, not premain. **finally** always detaches after a successful attach.

If the client runs in a different container or on a different filesystem, the **agentJar path must exist and be readable on the target**, not just on the client. The Java Attach API is typically a mechanism for interacting with a VM running in a provider-supported environment, not a protocol for loading arbitrary remote JARs over the Internet.

### 6.6. File agent.mf

~~~text
Manifest-Version: 1.0
Premain-Class: RuntimeAgent
Agent-Class: RuntimeAgent
~~~

Save the file with a **trailing newline**. **Premain-Class** serves **-javaagent**; **Agent-Class** serves **VirtualMachine.loadAgent**. One JAR can contain both. It is not necessary to add **Can-Retransform-Classes** if the example only prints logs. If the manifest lacks **Agent-Class**, the attach client may connect successfully, but **loadAgent** will fail because no suitable agent entry point is found.

### 6.7. Compile and create the JAR

In the root directory, with JDK 17+ and a POSIX shell:

~~~bash
mkdir -p out/classes

javac --release 17 -d out/classes \
    src/Probe.java src/RuntimeAgent.java \
    src/Target.java src/AttachClient.java

jar cfm probe-agent.jar agent.mf \
    -C out/classes RuntimeAgent.class
~~~

Notes:

- **javac --release 17** makes the code use Java 17-compatible APIs and corresponding class files.
- Compilation is performed with a **build JDK** that has **jdk.attach** (to compile AttachClient), not with an image containing only java.base.
- The agent JAR only needs **RuntimeAgent.class** and the manifest in this example; it does not need to package Probe/Target/AttachClient.
- The application/test files use **out/classes** as a separate classpath.
- If the source is modular, you must declare **requires java.instrument** or **requires jdk.attach** in the module that actually imports the API and compile with an appropriate module path; the default-package demo belongs to the unnamed module, so it has no module-info.java.

To inspect the JAR:

~~~bash
jar tf probe-agent.jar
jdeps --print-module-deps probe-agent.jar
jdeps --print-module-deps out/classes/AttachClient.class
~~~

Output of the last two jdeps commands on this test set:

~~~text
java.base,java.instrument
java.base,jdk.attach
~~~

### 6.8. Build the three runtime images

~~~bash
jlink --add-modules java.base,java.instrument \
      --output rt-target

jlink --add-modules java.base,jdk.attach \
      --output rt-client

jlink --add-modules java.base,java.instrument,jdk.attach \
      --output rt-full
~~~

Run jlink using the **image-building JDK 17+** and specify an output directory that does not yet exist. Do not re-run targeting an existing output name assuming jlink replaces it atomically; in a build pipeline, use a fresh build path, verify it, and then promote the artifact.

### 6.9. Test target containing only java.instrument

~~~bash
./rt-target/bin/java -cp out/classes Probe
~~~

Output:

~~~text
HAS_INSTRUMENT=true
HAS_ATTACH=false
ATTACH_RESOLVED=false
PROBE_OK
~~~

The startup agent still works:

~~~bash
./rt-target/bin/java \
    -javaagent:probe-agent.jar \
    -cp out/classes Probe
~~~

Output:

~~~text
PREMAIN_OK
RETRANSFORM=false
HAS_INSTRUMENT=true
HAS_ATTACH=false
ATTACH_RESOLVED=false
PROBE_OK
~~~

**Conclusion:** **-javaagent does not need jdk.attach** on the target in this example. java.instrument is linked into the image, the agent JAR has Premain-Class, and premain works.

### 6.10. Test client containing only jdk.attach

~~~bash
./rt-client/bin/java -cp out/classes Probe
~~~

Output observed on the tested HotSpot build:

~~~text
HAS_INSTRUMENT=false
HAS_ATTACH=true
ATTACH_RESOLVED=true
PROBE_OK
~~~

The client contains the Attach API so it can call VirtualMachine; it does not need java.instrument in the **client runtime itself** because it does not run a Java agent in the client. The jdk.attach module pulls in its required dependencies when jlink creates the image.

**Note on boot resolution:** With this demo's classpath configuration, jdk.attach is resolved in the boot layer as shown in the output. With named modules or other launch modes, check the process itself using **ModuleLayer.boot()**, and use **requires/--add-modules** when needed.

### 6.11. Test dynamic attach from client to target

On Linux/macOS with a POSIX shell, from the project directory:

~~~bash
# Run target in the background and save its PID.
./rt-target/bin/java -cp out/classes Target \
    > target.log 2>&1 &
TARGET_PID=$!

# Wait for target to print TARGET_READY.
sleep 1

# Client in another JVM, using the image with only jdk.attach.
./rt-client/bin/java -cp out/classes AttachClient \
    "$TARGET_PID" "$(pwd)/probe-agent.jar"

wait "$TARGET_PID"
cat target.log
~~~

In a HotSpot environment that allows attach, client output:

~~~text
ATTACH_OK
~~~

**Application** output in target.log:

~~~text
TARGET_READY
AGENTMAIN_OK
TARGET_END
~~~

**This ordering was observed in the simple example.** The target log may contain additional VM warnings/diagnostics, especially on newer JDKs. Warnings do not replace the **AGENTMAIN_OK** event. If attach is disallowed or the target has already exited before the client connects, **AttachNotSupportedException**, **IOException**, **AgentLoadException**, or **AgentInitializationException** may occur and must be diagnosed rather than attributed by default to missing modules.

On Windows, replace the shell background/PID handling with a workflow managing two terminals and the corresponding PID, using appropriate target/agent paths. PID mechanisms and permissions are OS-dependent.

**Tested result:** an equivalent codebase was built with **javac --release 17** and run on **OpenJDK 21 (Linux)**. The target image had only **java.base + java.instrument**, the client image had **java.base + jdk.attach**, and a separate attach client successfully loaded the agent into the target. This confirms the semantics that **the target does not need jdk.attach just to receive an agent** in the tested HotSpot environment; it is not a guarantee that every JVM vendor/OS behaves identically.

### 6.12. rt-full when both roles are needed

~~~bash
./rt-full/bin/java -cp out/classes Probe
~~~

Output:

~~~text
HAS_INSTRUMENT=true
HAS_ATTACH=true
ATTACH_RESOLVED=true
PROBE_OK
~~~

Use **rt-full** when a single runtime image genuinely runs an application that uses both instrumentation and the Attach API. If production only uses a startup agent, the **rt-target** image is a more minimal example; do not add jdk.attach just because the feature name sounds related.

## 7. Negative Test: Image Missing java.instrument

You can create a minimal image to observe the error:

~~~bash
jlink --add-modules java.base --output rt-minimal

./rt-minimal/bin/java \
    -javaagent:probe-agent.jar \
    -cp out/classes Probe
~~~

On the tested HotSpot Linux environment, the VM exits very early with a message similar to:

~~~text
Error occurred during initialization of VM
Could not find agent library instrument on the library path
Module java.instrument may be missing from runtime image.
~~~

The message is **shortened to convey the main point**; the HotSpot version, OS, and dynamic library loader may insert **libinstrument.so** along with other descriptions. Do not expect a byte-for-byte identical error string across all operating systems.

**The right fix:** rebuild the runtime image with **java.instrument**. You cannot fix this missing module by adding **--add-opens**, **--add-exports**, or **--add-modules java.instrument** to an image that already lacks that module. Access/resolution options do not synthesize the binaries of a module excluded from the image.

### 7.1. Conversely: client image missing jdk.attach

If **AttachClient.class** is compiled on a full JDK but run on a runtime without **jdk.attach**, loading/linking the **com.sun.tools.attach.VirtualMachine** API can fail with **NoClassDefFoundError** or a corresponding module resolution error. Therefore, run the AttachClient test **using rt-client/bin/java**, not the build JDK's java.

Having **jdk.attach** in the client still does not guarantee the attach provider will work against any target: PID, OS permissions, VM implementation, and attach mechanism still apply.

## 8. Distinguishing Present Modules, Resolved Modules, and JPMS Permissions

A class in a **named module** can still fail to call an agent's helper even when the runtime image has all the modules. Three separate aspects:

- **Presence**: the module has been included in the image by jlink.
- **Resolution/readability**: the module is in the module graph, and the caller module can read the callee module.
- **Access**: the callee's package is **exported** for ordinary public access or **opened** for deep reflection when needed.

If an agent injects bytecode into a class in the named module **com.example.app**, making that class call a helper in module **com.example.trace**, the app side may need a **read edge to com.example.trace** and the trace side must export the helper package. If a framework deep-reflects private fields of the app, the app module must **open that package to the reflecting module**. That is a matter of **Instrumentation.redefineModule / --add-reads / --add-exports / --add-opens**, which is **different** from missing **java.instrument/jdk.attach** in the runtime image.

~~~text
Has java.instrument          -> has Agent API mechanism
Has jdk.attach on client     -> has Attach API client
Has com.example.trace        -> helper module is available
App reads Trace              -> caller has read edge
Trace exports p to App       -> appropriate public API access
App opens q to Reflector     -> deep reflection if actually needed
~~~

**Do not habitually use --add-opens=ALL-UNNAMED** when the real problem is a missing Java module in the image or an unpackaged helper class. Broadly opening modules does not conjure missing libraries or methods, and it can widen reflective access scope.

## 9. Manifest/Capabilities Are Also Part of the Deployment Contract

An agent JAR may contain:

~~~text
Manifest-Version: 1.0
Premain-Class: com.example.agent.StartupAgent
Agent-Class: com.example.agent.DynamicAgent
Can-Redefine-Classes: true
Can-Retransform-Classes: true
Can-Set-Native-Method-Prefix: true
~~~

This is a **sample manifest with many capabilities** for an agent that actually needs them, **not the demo manifest**. Capability attributes are optional and should only be requested if needed.

| Manifest attribute | When is it used? |
| --- | --- |
| **Premain-Class** | Agent is enabled with **-javaagent** at startup |
| **Agent-Class** | Agent is loaded after startup via **Attach API/loadAgent** |
| **Can-Retransform-Classes** | Agent needs to retransform already-loaded classes if the JVM allows |
| **Can-Redefine-Classes** | Agent needs to redefine class definitions |
| **Can-Set-Native-Method-Prefix** | Agent needs a native method prefix to wrap native methods |

The presence of **java.instrument** does not automatically grant optional capabilities. Check at runtime using **Instrumentation** inside premain/agentmain:

~~~java
// Pseudocode inside the agent callback.
boolean canRetransform =
        inst.isRetransformClassesSupported();
boolean canRedefine =
        inst.isRedefineClassesSupported();
boolean canPrefix =
        inst.isNativeMethodPrefixSupported();
~~~

When a capability is missing, certain operations may throw **UnsupportedOperationException** or fail per the API. Do not just tweak the jlink image if the issue is a missing attribute in the manifest.

### 9.1. Agent JAR, libraries, and native binaries outside the JDK

A custom runtime image typically contains **JDK modules + related JDK native libraries**; it does not automatically bundle your agent JAR, ASM/Byte Buddy dependencies, application classes, or the agent's own native libraries if they are not part of the artifacts you ship.

Choose an appropriate packaging approach:

- Ship **agent.jar** alongside the app JAR and configure a valid **-javaagent** path.
- If the agent depends on external libraries, package dependencies properly (shaded/fat agent JAR or a classpath visible to the JVM), avoiding version collisions.
- If the agent uses its own JNI/JVMTI native library, ship the right binary for the OS/architecture and configure the native library search path.
- If the agent loads configs/certs/keystores from files, ensure the files and permissions exist in the runtime container.
- Check the **system class loader**, named/unnamed modules, and helper visibility when bytecode is injected.

jlink does not automatically guarantee that non-JDK artifacts are included in the final distribution. If using **jpackage**, re-check the **actual runtime-image inside the final package**, not just the intermediate image directory.

## 10. Attach: Non-Module Failure Causes

**VirtualMachine.attach(pid)** requires an environment supported by a provider, not a universal RPC client. A target that has jdk.attach can still fail to accept attach.

| Scenario | Common Symptom | Verification Direction |
| --- | --- | --- |
| Client runtime missing **jdk.attach** | Class/module linkage error before attach | Client --list-modules, ModuleFinder |
| Target runtime missing **java.instrument** | Startup agent fails; dynamic Java agent load may fail | Target --list-modules and -javaagent smoke test |
| **-XX:+DisableAttachMechanism** | Attach does not work | Target JVM command line |
| Incompatible user/permissions | AttachNotSupportedException/IOException | OS uid, ACL, security policy |
| Different PID namespace | Client cannot find the right PID | Container PID mapping / namespace |
| Target JVM already exited | Cannot attach | Process lifecycle |
| Different or unsupported provider/JVM | No compatible AttachProvider | Vendor, JDK version, jdk.attach module |
| Agent jar not on target filesystem | AgentLoadException or I/O error | Absolute target-readable JAR path |
| Manifest only has Premain-Class | loadAgent cannot find Agent-Class | JAR manifest |
| agentmain throws exception | AgentInitializationException | Target logs/exception |
| Self attach restricted | “Can not attach to current VM” or equivalent | Run client in a separate process, check JVM self-attach policy |
| Dynamic agent loading restricted in JDK/version | Warnings or loadAgent rejected | JEP/JDK release notes, flags, vendor |
| Missing helper module/permission | Agent starts but invocation fails | Module read/export/open and class loader |

On HotSpot Java 17, **-XX:+DisableAttachMechanism** disables the mechanism for attach tools. Do not automatically put **-Djdk.attach.allowAttachSelf=true** or attach-relaxing flags into production; self-attach carries its own security/operational implications.

### 10.1. Policy changes in JDKs after Java 17

Some newer JDKs emit warnings when **a Java agent is loaded dynamically**, following the direction of tightening JVM integrity controls (for example, **JEP 451** in JDK 21). Therefore, an example that runs cleanly on HotSpot Java 17 may print additional warnings on JDK 21, and default mechanisms/flags may change in subsequent JDK releases.

Do not use “no warning seen” or “the module still exists” as proof of attach capability. Read the release notes for the exact **vendor + JDK build being deployed**, and check flags such as **-XX:+EnableDynamicAgentLoading** if a specific JDK/issue requires it and operational policy allows it; **startup -javaagent** and **dynamic agent loading** have different policies.

## 11. Extended Modules When the Agent Uses Management and Observability

Not every instrumenting agent only needs java.instrument. If an agent measures class loading and then exports metrics, traces, or JFR/JMX, it may use additional modules:

### 11.1. Logging

An agent using **java.util.logging.Logger** needs the **java.logging** module. If it only uses **System.out.println**, java.base suffices for demo output. However, production logging may need file handlers, config, or external libraries, so output paths/write permissions must be tested.

### 11.2. JMX and management

Code calling **java.lang.management.ManagementFactory** needs **java.management**. If using HotSpot extensions such as **com.sun.management.HotSpotDiagnosticMXBean**, **jdk.management** may be needed. A remote JMX agent has its own requirements for **jdk.management.agent**, RMI modules, network security, and authentication. Do not just add **jdk.attach** because you see the word “management”.

### 11.3. Java Flight Recorder

When the app/agent actually imports **jdk.jfr.Recording** or JFR APIs, **jdk.jfr** must be checked. Not all profilers use sampling/JFR the same way. With a stripped-down runtime image, a missing module or provider can cause failures even while **ClassFileTransformer** still works.

### 11.4. Diagnostics and tools

Tools like **jcmd**, **jmap**, or JDWP depend on different modules/tools and JVM support. Do not expect **rt-target/bin/jcmd** to exist automatically just because the image has jdk.attach; **jdk.jcmd** is a separate requirement, and jlink has options that exclude native commands. You can choose to run tools outside the target container using an appropriate full JDK, if environment policy permits.

### 11.5. Providers/crypto/locale

An agent pushing telemetry over TLS, resolving DNS, processing XML/JSON via libraries, or using non-default charsets may need provider/locale modules that the main code does not use directly. **jdeps** does not guarantee visibility of every provider loaded dynamically by ServiceLoader. Review agent dependencies and test real scenarios before deciding to use **--bind-services** or add more modules.

## 12. Recommended CI/CD Workflow

~~~text
1. Analyze application (jdeps, module-info.java)
2. Analyze agent JAR + attach client + plugins
3. Assemble static and dynamic root modules
4. Create image with jlink from a version/vendor-pinned build JDK
5. Run the image/bin/java itself, not the host's java
6. Check --list-modules / ModuleFinder / ModuleLayer
7. Test startup -javaagent and correct premain
8. If attach is needed: test client (jdk.attach) -> target (java.instrument)
9. Test retransform/redefine/JMX/JFR if the product uses them
10. Package image + app + agent jar + configs/native libs
11. Smoke-test the final distribution under the real OS/container
12. Promote the artifact only after sufficient evidence
~~~

You can write a **check script** (POSIX shell):

~~~bash
set -eu

./rt-target/bin/java --list-modules \
  | grep '^java.instrument@'

./rt-client/bin/java --list-modules \
  | grep '^jdk.attach@'

./rt-target/bin/java -javaagent:probe-agent.jar \
  -cp out/classes Probe
~~~

This is an illustrative script, where **grep module@version** matches JDK modules that have versions in the image; some vendors/configurations may format this differently, so production CI can use **ModuleFinder** or parse the module name before the @ sign for certainty. This script only checks presence and startup; it **does not replace** an attach integration test.

**Do not automatically “fix” issues by adding all JDK modules** to the image and skipping smoke tests. Doing so defeats the purpose of reducing surface area/size, and still fails to fix manifest/permissions/provider errors.

## 13. Step-by-Step Failure Analysis

### 13.1. -javaagent does not run in custom runtime

Check order:

1. Confirm the command actually invokes **<image>/bin/java**, not java from PATH.
2. Does **--list-modules** in the image include **java.instrument**?
3. Does the agent JAR exist at the startup path of the **target process**?
4. Does the manifest have **Premain-Class** with the exact binary name?
5. Is the premain signature **public static void premain(String, Instrumentation)** or a supported overload?
6. Can the agent class and dependencies be loaded by the system class loader?
7. Does premain throw an exception? Does the transformer cause an error when defining a class?
8. Does the JVM vendor/architecture have full native instrumentation support?

### 13.2. Attach client missing API

1. Confirm the client is running with **rt-client/bin/java**.
2. Does the client's **ModuleFinder.ofSystem()** contain **jdk.attach**?
3. If the module is present but not resolved, check named module **requires jdk.attach** or launcher **--add-modules jdk.attach**.
4. Check **AttachProvider.providers()** if needed, along with the JVM implementation.
5. Do not confuse a Java module/linkage error on the client with a target PID/permission error.

### 13.3. Client can attach, but loadAgent fails

1. Distinguish **VirtualMachine.attach** succeeding from **vm.loadAgent** succeeding.
2. Does the target have **java.instrument**, and does the JVM allow dynamic agent loading?
3. Does the agent JAR have a valid **Agent-Class** and **agentmain**?
4. Can the target read the JAR's absolute path?
5. Are native/JVM platform policy, security flags, and module/class loader availability sufficient?
6. Did agentmain throw an exception or fail to find a helper/library?
7. Only report **AGENTMAIN_OK** or real instrumentation effect when the target confirms it ran; an **ATTACH_OK** printed by the client after loadAgent does not by itself prove business behavior.

### 13.4. Agent loads, but instrumentation has no effect

Module presence is sufficient, yet it could be that:

- The class to transform was already loaded before startup/attach.
- The transformer filters on the wrong internal class name/module/classloader.
- **Can-Retransform-Classes** was not granted even though the agent needs to modify already-loaded classes.
- The output bytecode is invalid, rejected by the JVM, or returns null.
- The helper module is not properly packaged/exported/opened/read.
- New code runs in an old active frame or a different classloader.
- A native or networking dependency of the agent is missing in the final distribution.

These are **runtime behavior/bytecode** issues, not fixed by jlink once the modules are already right.

## 14. Minimum Test Matrix

| Scenario | Image / Configuration | Expectation |
| --- | --- | --- |
| Target runtime has java.instrument | rt-target | HAS_INSTRUMENT=true |
| Target runtime lacks jdk.attach | rt-target | Startup -javaagent still yields PREMAIN_OK |
| Client runtime has jdk.attach | rt-client | HAS_ATTACH=true |
| Client runtime lacks java.instrument | rt-client | Attach API still works as client |
| Full runtime | rt-full | Both modules present |
| Image with only java.base | rt-minimal + -javaagent | JVM does not start agent, reports missing instrumentation |
| Agent JAR missing Premain-Class | Target startup | Agent startup fails |
| Agent JAR missing Agent-Class | Target dynamic loading | loadAgent fails |
| Target does not support attach | DisableAttachMechanism | Attach fails |
| Target in different PID namespace | Cross-container | Do not assume matching PIDs |
| Target missing JAR path | Agent path only on client filesystem | loadAgent fails |
| Self-attach | Client same PID as target | Depends on JVM policy, not default |
| Agent uses ManagementFactory | Image missing java.management | Management code may fail to link/load |
| Agent uses JFR | Image missing jdk.jfr | JFR APIs unavailable |
| Helper class in another named module | Modules present but missing reads/exports | Linkage/access error |
| Only jdeps on application JAR | Agent not analyzed | Risk of missing java.instrument |
| Agent/JDK build changed | Image not rebuilt | Module graph or behavior may change |
| Testing on host JDK instead of image | Wrong java binary run | Results differ from production |

## 15. Pre-Release Checklist for a Custom Runtime

- I know whether the product is a **startup agent**, **dynamic attach target**, **attach client**, or a combination.
- I distinguish **java.instrument on the target** from **jdk.attach on the client**.
- I ran **jdeps** for the application, agent, and attach tooling as appropriate.
- Dynamic dependencies from reflection, ServiceLoader, JNI, plugins, and telemetry have been reviewed.
- **jlink --add-modules** contains the necessary root modules and dependencies are resolved.
- I checked **<image>/bin/java --list-modules** directly on the distributed image.
- I verified **ModuleFinder.ofSystem** and when needed **ModuleLayer.boot** in a real process.
- The agent JAR has **Premain-Class** and/or **Agent-Class** with valid callbacks.
- Retransform/redefine/native prefix capabilities are declared/checked if the agent needs them.
- **-javaagent** is tested on the target image, not just on the build JDK.
- If using attach, **VirtualMachine.attach + loadAgent + agentmain** are tested end-to-end.
- Target PID, permissions, namespace, dynamic agent policy, and JAR path are verified.
- Agent helper classes, packages/modules, native libraries, and config files are all present in the distribution.
- Modules such as **java.management, jdk.management, jdk.jfr, java.logging, jdk.unsupported** are added only when actually needed.
- The pipeline uses an explicit JDK version/vendor, builds a fresh image when dependencies change, and tests the final **jpackage/container** artifact.
- I do not treat **module present** as proof of instrumentation effect; real methods/events/metrics must be tested.

## 16. Java 17 Standard References and Compatibility Notes

- [Java SE 17 — Module java.instrument](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/module-summary.html): module providing the Java instrumentation service.
- [Java SE 17 — java.lang.instrument package](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): -javaagent, Premain-Class, Agent-Class, premain/agentmain, and class loading.
- [Java SE 17 — Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): transformer, retransform/redefine capabilities, and module instrumentation.
- [Java SE 17 — jdk.attach](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.attach/module-summary.html): client Attach API.
- [Java SE 17 — VirtualMachine](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachine.html): attach, loadAgent, detach, and failure types.
- [JDK 17 — jlink](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jlink.html): --add-modules, --module-path, --output, service binding, and custom runtime images.
- [JDK 17 — jdeps](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html): --print-module-deps and limitations of static dependency analysis.
- [JDK 17 — java launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): --list-modules, --describe-module, --add-modules, and -XX:+DisableAttachMechanism.
- [JDK 17 — jpackage](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jpackage.html): packaging app images/custom runtimes.
- [OpenJDK JEP 451](https://openjdk.org/jeps/451): changes to warnings/policies for dynamic agent loading in JDKs after 17.

**Conclusion:** Select modules by **process role**, not just by technology name. **java.instrument belongs to the JVM running/receiving the Java agent; jdk.attach belongs to the tool calling the Attach API**. Use **jdeps + dynamic dependency checks** to determine jlink roots, verify **the exact image/bin/java**, and prove end-to-end behavior with **premain** or **VirtualMachine.attach → loadAgent → agentmain**. A present module cannot substitute for a valid manifest, VM/OS permissions, class loader visibility, and real behavior testing.
