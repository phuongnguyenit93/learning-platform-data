# Agent Dependencies, Version Conflicts, and Library Class Name Isolation

> **Context:** Java Advance → Instrumentation → **Packaging and Deployment**. A Java agent attached to the JVM via `-javaagent` does not automatically have an isolated class loader. According to the `java.lang.instrument` specification, classes in the agent JAR are loaded by the **system class loader**, belonging to **that loader's unnamed module**. When the agent and the application both package a library with the **same binary name but different API versions**, the runtime may only define one version in the same loader. The result is linkage errors or hard-to-reproduce incorrect behavior. This article analyzes the root cause, packaging options, **shading and package relocation** mechanisms, resource/SPI blind spots, and verification strategies. Java 17+ and Maven Shade Plugin 3.6.2 examples were built/run on OpenJDK 24.

## 1. Why Can an Agent Dependency Break the Application?

Java class identity is the pair **binary name + defining class loader**, not `JAR filename + class name`. If two JARs both contain:

~~~text
org/example/codec/Codec.class
~~~

and both versions are looked up by the **same system class loader**, the JVM does not define two classes with the same name so that the agent uses one version and the app uses the other. The loader will determine a single class identity for that binary name. Callers compiled against a different API will link to the class defined by the JVM at runtime.

For example:

~~~text
                 JVM system class loader
                     /           \
  startup agent JAR /             \ application classpath JAR
  org.example.codec.Codec v1       org.example.codec.Codec v2
  has method agentOnly()           has method appOnly()
                     \            /
                      one binary name
                            |
                  one class is defined
                            |
              the other caller may miss its API
~~~

There is **no guarantee** across all JVMs/launchers that "the agent always wins" or "the app always wins". Loading can depend on classpath search, agent startup, resolution timing, and the actual class loader. What you can rely on is: **within the same defining loader, two versions of a class with the same binary name do not automatically become two independent versions**.

In contrast to this case, a plugin/container can use **two different custom class loaders** to define classes with the same binary name. In that case, they are **two different class identities**, and an object from loader A cannot automatically be cast to a class of the same name from loader B. Therefore, it is still necessary to design a public API boundary so that both sides can communicate.

### Real-World Errors

| Symptom | Common Cause | Nature |
|---|---|---|
| `NoSuchMethodError` | Caller compiled against v1 but runtime loads v2 missing the method/descriptor | Binary linkage error |
| `NoSuchFieldError` | Field was renamed, removed, or had its descriptor changed | Binary compatibility |
| `AbstractMethodError` | Interface/implementation belong to incompatible versions | Linkage when executing call |
| `IncompatibleClassChangeError` | Static/instance, class/interface, or hierarchy has changed | Incompatible binary definitions |
| `ClassNotFoundException` | Requested loader cannot find the class | Class lookup |
| `NoClassDefFoundError` | Dependency is not defined or prior linkage/init failed | Runtime loading/linkage |
| `ClassCastException` between two identically named classes | Two loaders define two type identities | Loader isolation without shared API |
| `ServiceConfigurationError` | Broken service descriptor, stale provider path, or incompatible class | Resource metadata/SPI |
| `ExceptionInInitializerError` | Static initializer of the library throws an exception | Runtime behavior/configuration |
| `SecurityException` with signed JAR | Signature metadata no longer matches after repackaging | Artifact integrity |

`NoSuchMethodError` is an **Error** caused by binary linkage, distinct from `NoSuchMethodException` thrown by the reflection API. Catching `NoSuchMethodError` in the demo is only for observing the conflict; a production agent must handle error states explicitly and must not pretend to operate normally when the library API is already incompatible.

## 2. Classifying Dependencies Before Choosing a Packaging Strategy

An agent typically has three layers:

1. **Agent implementation:** `premain`/`agentmain` entry point, transformer, configuration, instrumentation orchestration.
2. **Internal dependencies:** bytecode library (ASM/Byte Buddy), serializer, config parser, internal logger/exporter, utilities used by the agent.
3. **Bridge/shared API:** classes/interfaces that instrumented bytecode, the application, or bootstrap-defined classes need to reference directly.

Group 2 is usually a **relocation candidate**. Group 3 **cannot be relocated unconditionally**, because both sides must agree on the **binary name and class identity** if they need to communicate via an interface, cast, or method descriptor.

A BOM, Maven `dependencyManagement`, or Gradle version catalog only helps keep the build's dependency graph controlled. It **does not isolate the runtime namespace** between the agent and the app if they share the system loader. Transitive dependencies can also cause conflicts; the agent uses lib X which pulls in Y v1, and the app uses Y v2, even though neither imports Y directly.

### Four Design Questions

- Which classes must actually be present **when the agent runs**, not just at compile time?
- Which libraries should be private to the agent, and which APIs **must be shared**?
- Are class/package names embedded in `META-INF/services`, JSON/XML, `Class.forName`, resource bundles, or reflection strings?
- Does the transformed target class reside in the system, bootstrap, or custom loader; can it resolve the helper after instrumentation?

## 3. Thin JAR, Fat JAR, Shading, Relocation, and Classloader Isolation

| Option | What It Does | What Is Missing |
|---|---|---|
| Thin agent JAR | Agent JAR only contains implementation, dependencies on external path | Depends on runtime classpath and the app's library version |
| Fat/uber JAR | Bundles classes/resources of multiple dependencies into one JAR | **Does not change binary names by default**, conflicts can still occur |
| Shading + relocation | Bundles dependencies then **renames packages/binary names**, rewrites bytecode references | Not guaranteed to fix all resources, reflection strings, JNI, or helper visibility |
| Custom classloader isolation | Defines private libraries in a separate loader | Must handle parent/child delegation, class identity, target helpers, and JPMS |
| Separate bootstrap helper JAR | Minimal bridge for bootstrap-defined targets | Should not bundle all agent dependencies into bootstrap |
| Reducing dependencies | Reduces conflict surface, size, and CVEs | Does not replace functionality that is genuinely needed |

**A fat JAR is different from a relocated JAR.** If the output JAR still contains `org/apache/commons/lang3/StringUtils.class`, an application with Commons Lang of the same FQCN can still collide. With Maven Shade relocation:

~~~text
org/apache/commons/lang3/StringUtils.class
             |
             v
demo/agent/shadow/org/apache/commons/lang3/StringUtils.class
~~~

The shader must also rewrite the corresponding **class references** in the agent's bytecode so it looks up the relocated name. **Renaming JAR entries alone without rewriting references** will lead to new class lookup/linkage errors.

Private packages should be placed under a prefix owned by the agent, for example `com.company.product.agent.v1.shaded.*`. Two different agents both using the `shadow.*` prefix can still collide with each other. **Do not relocate `java.*` or public APIs that the application needs to share**.

## 4. Java 17+ Hands-On: Two Versions with the Same FQCN and the Consequences

This is a **Maven-free** lab to observe a class with the same name brought into the JVM by two JARs.

- Agent lib v1: `org.example.codec.Codec.agentOnly()`.
- App lib v2: `org.example.codec.Codec.appOnly()`.
- Both versions have `owner()` to display which version is loaded.
- Fixed case: the agent uses the class **`demo.agent.shadow.codec.Codec`** instead of the original name. This **simulates the result of relocation using source in a different package**, without using the Shade plugin yet; section 5 uses the actual plugin.

### 4.1 Directory Structure

~~~text
agent-dependency-lab/
├── bad-manifest.mf
├── good-manifest.mf
├── src/
│   ├── agent-lib/org/example/codec/Codec.java
│   ├── app-lib/org/example/codec/Codec.java
│   ├── agent/demo/agent/CollisionAgent.java
│   ├── app/demo/app/Main.java
│   ├── private-lib/demo/agent/shadow/codec/Codec.java
│   └── agent-relocated/demo/agent/PrivateAgent.java
└── out/
    ├── agent-lib/
    ├── app-lib/
    ├── agent/
    ├── app/
    ├── private-lib/
    ├── relocated-agent/
    ├── bad-agent.jar
    ├── good-agent.jar
    └── app-lib.jar
~~~

Run from the root directory `agent-dependency-lab`; requires JDK 17+ with `javac`, `jar`, and `java`.

### 4.2 Agent lib v1

File `src/agent-lib/org/example/codec/Codec.java`:

~~~java
package org.example.codec;

public final class Codec {
    private Codec() {}

    public static String owner() { return "AGENT_V1"; }

    public static String agentOnly() { return "AGENT_OK"; }
}
~~~

### 4.3 App lib v2

File `src/app-lib/org/example/codec/Codec.java`:

~~~java
package org.example.codec;

public final class Codec {
    private Codec() {}

    public static String owner() { return "APP_V2"; }

    public static String appOnly() { return "APP_OK"; }
}
~~~

**Two classes with the same binary name**: must be compiled into two separate output dirs. Do not compile both at once in a single `javac` invocation.

### 4.4 Unrelocated Agent

File `src/agent/demo/agent/CollisionAgent.java`:

~~~java
package demo.agent;

import java.lang.instrument.Instrumentation;
import org.example.codec.Codec;

public final class CollisionAgent {
    private CollisionAgent() {}

    public static void premain(String options, Instrumentation inst) {
        System.out.println("[AGENT] libOwner=" + Codec.owner());
        try {
            System.out.println("[AGENT] agentApi=" + Codec.agentOnly());
        } catch (NoSuchMethodError e) {
            // For lesson purposes only: do not abort JVM so we can observe the conflict.
            System.out.println("[AGENT] agentApi=MISSING");
        }
    }
}
~~~

The agent is **compiled** against v1. Its bytecode requires the method `Codec.agentOnly()`, but the runtime may have defined `Codec` v2. In that case, the JVM throws `NoSuchMethodError` because the method does not exist on the loaded class.

### 4.5 Application Compiled Against v2

File `src/app/demo/app/Main.java`:

~~~java
package demo.app;

import org.example.codec.Codec;

public final class Main {
    public static void main(String[] args) {
        System.out.println("[APP] libOwner=" + Codec.owner());
        try {
            System.out.println("[APP] appApi=" + Codec.appOnly());
        } catch (NoSuchMethodError e) {
            System.out.println("[APP] appApi=MISSING");
        }
    }
}
~~~

### 4.6 Agent Using a Private Namespace

File `src/private-lib/demo/agent/shadow/codec/Codec.java`:

~~~java
package demo.agent.shadow.codec;

public final class Codec {
    private Codec() {}

    public static String owner() { return "AGENT_PRIVATE_V1"; }

    public static String agentOnly() { return "AGENT_OK"; }
}
~~~

File `src/agent-relocated/demo/agent/PrivateAgent.java`:

~~~java
package demo.agent;

import java.lang.instrument.Instrumentation;
import demo.agent.shadow.codec.Codec;

public final class PrivateAgent {
    private PrivateAgent() {}

    public static void premain(String options, Instrumentation inst) {
        System.out.println("[AGENT] privateLib=" + Codec.owner());
        System.out.println("[AGENT] agentApi=" + Codec.agentOnly());
    }
}
~~~

The two binary names `demo.agent.shadow.codec.Codec` and `org.example.codec.Codec` are different; they can coexist in the system loader without colliding by name.

### 4.7 Manifests for Both Agents

`bad-manifest.mf`:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.CollisionAgent

~~~

`good-manifest.mf`:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.PrivateAgent

~~~

The manifest must have a trailing newline and a blank line after the main attributes. This lesson does not need `Agent-Class` or retransformation capability.

### 4.8 Build on macOS/Linux

~~~bash
mkdir -p out/agent-lib out/app-lib out/agent out/app out/private-lib out/relocated-agent

javac --release 17 -d out/agent-lib src/agent-lib/org/example/codec/Codec.java
javac --release 17 -cp out/agent-lib -d out/agent src/agent/demo/agent/CollisionAgent.java
javac --release 17 -d out/app-lib src/app-lib/org/example/codec/Codec.java
javac --release 17 -cp out/app-lib -d out/app src/app/demo/app/Main.java
javac --release 17 -d out/private-lib src/private-lib/demo/agent/shadow/codec/Codec.java
javac --release 17 -cp out/private-lib -d out/relocated-agent src/agent-relocated/demo/agent/PrivateAgent.java

jar --create --file out/bad-agent.jar --manifest bad-manifest.mf -C out/agent . -C out/agent-lib .
jar --create --file out/good-agent.jar --manifest good-manifest.mf -C out/relocated-agent . -C out/private-lib .
jar --create --file out/app-lib.jar -C out/app-lib .
~~~

Build on Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force -Path out/agent-lib, out/app-lib, out/agent, out/app, out/private-lib, out/relocated-agent | Out-Null

javac --release 17 -d out/agent-lib src/agent-lib/org/example/codec/Codec.java
javac --release 17 -cp out/agent-lib -d out/agent src/agent/demo/agent/CollisionAgent.java
javac --release 17 -d out/app-lib src/app-lib/org/example/codec/Codec.java
javac --release 17 -cp out/app-lib -d out/app src/app/demo/app/Main.java
javac --release 17 -d out/private-lib src/private-lib/demo/agent/shadow/codec/Codec.java
javac --release 17 -cp out/private-lib -d out/relocated-agent src/agent-relocated/demo/agent/PrivateAgent.java

jar --create --file out/bad-agent.jar --manifest bad-manifest.mf -C out/agent . -C out/agent-lib .
jar --create --file out/good-agent.jar --manifest good-manifest.mf -C out/relocated-agent . -C out/private-lib .
jar --create --file out/app-lib.jar -C out/app-lib .
~~~

Note: `jar -C out/agent . -C out/agent-lib .` **bundles classes**, without changing packages. "Bad" and "good" are packaged into two independent agent JARs. The application is in `out/app` and the v2 library is in `out/app-lib.jar`.

### 4.9 Running Three Scenarios

**Baseline, without agent**, Bash:

~~~bash
java -cp out/app:out/app-lib.jar demo.app.Main
~~~

PowerShell:

~~~powershell
java -cp "out/app;out/app-lib.jar" demo.app.Main
~~~

Stdout:

~~~text
[APP] libOwner=APP_V2
[APP] appApi=APP_OK
~~~

**With conflict**, Bash:

~~~bash
java -javaagent:out/bad-agent.jar -cp out/app:out/app-lib.jar demo.app.Main
~~~

PowerShell:

~~~powershell
java "-javaagent:out/bad-agent.jar" -cp "out/app;out/app-lib.jar" demo.app.Main
~~~

**Verified stdout on the lab's OpenJDK 24:**

~~~text
[AGENT] libOwner=APP_V2
[AGENT] agentApi=MISSING
[APP] libOwner=APP_V2
[APP] appApi=APP_OK
~~~

In this run, the JVM defined `org.example.codec.Codec` from the app's version. The agent is missing `agentOnly()`. A different launcher/timing could load v1, in which case the **app** would be missing `appOnly()`. This is a **shared binary name** issue, not that "the app version always has higher priority than the agent".

**After class name isolation**, Bash:

~~~bash
java -javaagent:out/good-agent.jar -cp out/app:out/app-lib.jar demo.app.Main
~~~

PowerShell:

~~~powershell
java "-javaagent:out/good-agent.jar" -cp "out/app;out/app-lib.jar" demo.app.Main
~~~

Verified stdout:

~~~text
[AGENT] privateLib=AGENT_PRIVATE_V1
[AGENT] agentApi=AGENT_OK
[APP] libOwner=APP_V2
[APP] appApi=APP_OK
~~~

The agent has its own namespace and the app still uses v2. This coexistence **does not automatically prove safety for ServiceLoader, resources, or cross-loader helpers**; it only proves there is no longer a duplicate class name in this case.

### 4.10 Inspecting JAR Entries

~~~bash
jar --list --file out/bad-agent.jar
jar --list --file out/good-agent.jar
jar --list --file out/app-lib.jar
~~~

Both `bad-agent.jar` and `app-lib.jar` contain `org/example/codec/Codec.class`; `good-agent.jar` contains `demo/agent/shadow/codec/Codec.class`. Inspect the output JAR **after packaging** rather than only checking `src`.

## 5. Maven Shade Hands-On: Relocating a Real Dependency

To avoid manually copying and renaming library source packages, use the **Apache Maven Shade Plugin**. This lesson uses the real dependency `org.apache.commons:commons-lang3:3.14.0`, builds with Shade Plugin `3.6.2`, and runs the agent JAR successfully on OpenJDK 24.

Relocation target:

~~~text
org/apache/commons/lang3/StringUtils.class
     -> demo/agent/shadow/org/apache/commons/lang3/StringUtils.class
~~~

This is just a library choice to illustrate the technique. A small agent does not need Commons Lang if the JDK already has sufficient APIs.

### 5.1 Project

~~~text
shaded-agent/
├── pom.xml
└── src/main/java/
    ├── demo/agent/ShadedAgent.java
    └── demo/app/SimpleMain.java
~~~

`src/main/java/demo/agent/ShadedAgent.java`:

~~~java
package demo.agent;

import java.lang.instrument.Instrumentation;
import org.apache.commons.lang3.StringUtils;

public final class ShadedAgent {
    private ShadedAgent() {}

    public static void premain(String options, Instrumentation inst) {
        System.out.println("[AGENT] shadedStringUtils="
                + StringUtils.isBlank("  "));
    }
}
~~~

The source **still imports the original package** to compile against the Maven dependency. The Shade Plugin rewrites class references and class entries in the **output artifact**.

`src/main/java/demo/app/SimpleMain.java`:

~~~java
package demo.app;

public final class SimpleMain {
    public static void main(String[] args) {
        System.out.println("[APP] main");
    }
}
~~~

### 5.2 Complete `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo.agent</groupId>
  <artifactId>shaded-agent</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.apache.commons</groupId>
      <artifactId>commons-lang3</artifactId>
      <version>3.14.0</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-shade-plugin</artifactId>
        <version>3.6.2</version>
        <executions>
          <execution>
            <phase>package</phase>
            <goals><goal>shade</goal></goals>
            <configuration>
              <createDependencyReducedPom>false</createDependencyReducedPom>
              <relocations>
                <relocation>
                  <pattern>org.apache.commons.lang3</pattern>
                  <shadedPattern>demo.agent.shadow.org.apache.commons.lang3</shadedPattern>
                </relocation>
              </relocations>
              <filters>
                <filter>
                  <artifact>*:*</artifact>
                  <excludes>
                    <exclude>META-INF/*.SF</exclude>
                    <exclude>META-INF/*.DSA</exclude>
                    <exclude>META-INF/*.RSA</exclude>
                  </excludes>
                </filter>
              </filters>
              <transformers>
                <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                  <manifestEntries>
                    <Premain-Class>demo.agent.ShadedAgent</Premain-Class>
                  </manifestEntries>
                </transformer>
                <transformer implementation="org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
              </transformers>
            </configuration>
          </execution>
        </executions>
      </plugin>
    </plugins>
  </build>
</project>
~~~

**Meaning:**

- `maven.compiler.release=17` controls the source/API/bytecode target of the **project**, but you still need to check the bytecode of **dependencies**.
- The plugin runs the `shade` goal in the `package` phase, building an **uber JAR**.
- `relocations` moves Commons Lang to the agent's namespace, while rewriting bytecode references supported by the plugin.
- `ManifestResourceTransformer` ensures the output `META-INF/MANIFEST.MF` contains `Premain-Class`.
- `ServicesResourceTransformer` merges/relocates descriptors in `META-INF/services`, if any; this Commons Lang example is **not intended to verify SPI**.
- Signature filters `META-INF/*.SF`, `*.DSA`, `*.RSA` remove old signature metadata that could become invalid after repackaging. If integrity signatures are needed, you must **re-sign the output artifact**, while preserving license/NOTICE files.
- `createDependencyReducedPom=false` is used for the lab. When publishing, you must review POM metadata and dependency exposure yourself.
- Do not enable `minimizeJar` to avoid removing classes loaded via reflection/SPI that static analysis cannot see.

### 5.3 Build and Run

In the root directory `shaded-agent`, Bash:

~~~bash
mvn -B -q -DskipTests package
jar --list --file target/shaded-agent-1.0.0.jar
java -javaagent:target/shaded-agent-1.0.0.jar -cp target/shaded-agent-1.0.0.jar demo.app.SimpleMain
~~~

PowerShell:

~~~powershell
mvn -B -q -DskipTests package
jar --list --file target/shaded-agent-1.0.0.jar
java "-javaagent:target/shaded-agent-1.0.0.jar" -cp target/shaded-agent-1.0.0.jar demo.app.SimpleMain
~~~

**Verified stdout:**

~~~text
[AGENT] shadedStringUtils=true
[APP] main
~~~

In the final JAR, verified entries include:

~~~text
META-INF/MANIFEST.MF
demo/agent/shadow/org/apache/commons/lang3/StringUtils.class
demo/agent/shadow/org/apache/commons/lang3/RandomStringUtils.class
~~~

These are **representative lines** from the listing, not the entire listing. There should no longer be a class at the original path `org/apache/commons/lang3/StringUtils.class` if relocation covers the package properly. The agent running successfully proves that the post-shading bytecode can use the library API in the new namespace.

**Do not relocate the entry point** `demo.agent.ShadedAgent` if the manifest still points to the original name. If the agent needs public classes shared with the app, clearly determine the class identity before deciding to include them in `relocations`.

### 5.4 If Using Gradle Shadow

GradleUp Shadow provides similar support via the `shadowJar` task and `relocate`. An **illustrative Kotlin DSL snippet** when the Shadow plugin is configured with the appropriate version:

~~~kotlin
tasks.named<com.github.jengelman.gradle.plugins.shadow.tasks.ShadowJar>("shadowJar") {
    relocate(
        "org.apache.commons.lang3",
        "demo.agent.shadow.org.apache.commons.lang3"
    )
    manifest {
        attributes["Premain-Class"] = "demo.agent.ShadedAgent"
    }
}
~~~

This snippet **has not been tested in this article**. Modern versions use the plugin ID `com.gradleup.shadow`; you need to declare `plugins`, dependencies, Java toolchain, and check the task type API/imports for the exact Shadow version. Do not treat this script snippet as a complete build file. The official documentation also mentions an option to rewrite string constants; evaluate it carefully when a library uses reflection.

## 6. Blind Spots Where Shading Can Miss

Renaming class binary names does not mean all metadata is updated.

### `META-INF/services` and `ServiceLoader`

A Java SPI may have a resource:

~~~text
META-INF/services/org.example.spi.CodecProvider
  org.example.codec.impl.DefaultCodecProvider
~~~

If the provider class is relocated while the descriptor file keeps the old name, `ServiceLoader.load(...)` may fail to find the implementation or throw `ServiceConfigurationError`. Maven Shade's `ServicesResourceTransformer` helps merge and rename service/provider descriptors. **However**, you must test the actual SPI on the **final shaded JAR**, because a framework with its own custom metadata does not necessarily use `META-INF/services`.

For an SPI interface shared with the app, consider **keeping the public interface unchanged** and only relocating the appropriate implementation; if both sides use two differently relocated interfaces, they cannot cast or properly implement the shared API.

### Reflection and Strings

For example:

~~~java
Class.forName("org.example.codec.impl.DefaultCodecProvider");
~~~

Some shading tools can rewrite string constants, but cannot guarantee rewriting every value generated dynamically from env/config, JSON/XML, URLs, or runtime string concatenation. After relocation, check:

- `Class.forName(...)` and `MethodHandles` using fixed or dynamic class names.
- Resource bundles, `getResource(...)`, `ServiceLoader`, custom plugins.
- YAML/JSON/XML configs containing FQCNs; serializer/deserializer registries.
- Java serialization may carry class names, and data compatibility needs separate handling.
- Framework metadata such as Log4j plugin cache, Spring factories, config merging.

Do not just search code imports; run **integration tests on the final JAR** covering rare initialization paths.

### Multi-Release JARs and Module Descriptors

A dependency may contain `META-INF/versions/9/...`, `META-INF/versions/17/...`, or class files targeting higher JDK versions. Shading must preserve class structures/version-specific variants and proper manifest metadata. At the same time, `module-info.class` or `Automatic-Module-Name` may no longer reflect the new artifact after merging/rewriting.

An agent JAR run via `-javaagent` normally resides in the **unnamed module of the system loader**, while the target application may use **named modules**. Relocation does not automatically open/export packages of named modules, does not create an additional class loader, and does not change the class file target version of a dependency. Building with `--release 17` alongside a dependency requiring Java 21 can still hit `UnsupportedClassVersionError` on a Java 17 runtime.

### JNI/Native Assets and Signed JARs

If a library contains `.dll`, `.so`, `.dylib`, or JNI symbol names tied to a package, renaming Java class names does not automatically rename native libraries/symbols. Native linkage must be tested separately.

If merging signed JARs, old `META-INF/*.SF`/`*.RSA`/`*.DSA` entries may become invalid after bytes change. The Maven filters example removing old signature metadata is a **packaging technique**, not a substitute for supply-chain verification. Preserve licenses/NOTICE, verify checksums/signatures, and re-sign the output when required by your process.

### `minimizeJar` and Reflective Classes

The minimizer can strip classes that static analysis does not see, while the agent loads them via `ServiceLoader`, reflection, generated bytecode, or plugin discovery.

~~~text
At build time: Class has no direct reference -> removed
At runtime:    Class.forName(providerFromConfig) -> ClassNotFoundException
~~~

Do not enable `minimizeJar` reflexively. Only optimize after having thorough test coverage for feature paths, SPI, and dynamic class loading; if needed, retain the corresponding packages/classes using explicit filters.

## 7. Relocation Does Not Replace Classloader/Helper Design

A transformer can receive classes defined by the **bootstrap**, **system**, or a **custom loader**. The `loader` parameter of the callback describes the **target class loader**, which is not the Java agent's loader by default.

~~~text
Java agent implementation (system loader)
   ├── transformer + shaded ASM/codec (system)
   │
   ├── instrument application target (system)
   ├── instrument plugin target (custom loader)
   └── instrument java.base target (bootstrap loader)
                      |
           injected code calls system-only helper?
                      |
           bootstrap does not delegate down to system
                      |
              NoClassDefFoundError
~~~

Even if the helper is relocated to `demo.agent.shadow.Helper`, the bootstrap loader still **cannot automatically see** a class loaded only by the system loader. A bridge must be designed:

~~~text
agent-implementation.jar          system loader
  premain/agentmain
  transformer, shaded internals
  exporter/configuration

bootstrap-bridge.jar              bootstrap loader search
  very small API, unique package
  does not link back to system-only implementation
~~~

Java Instrumentation provides `appendToBootstrapClassLoaderSearch(new JarFile(...))` and `Boot-Class-Path`. Do not put the entire fat agent JAR onto the bootstrap search just for "easy visibility" because it can pollute the core lookup namespace. The bootstrap helper should be minimal and only link against bootstrap-resolvable classes.

With custom/child-first classloaders, the app's loader may have different class naming/visibility. If you need to use an instrumented helper, test it directly on the target's loader; do not indiscriminately call `Class.forName(targetName)` inside a transformer as it can cause recursive loading or `LinkageError`.

### Module Access Is Independent of Relocation

A class defined by the system loader is usually in that loader's unnamed module, but a class of a named module can also be defined by the system loader. **Loader visibility, module readability, exports, and opens are distinct conditions**. Changing package names via shading does not automatically grant deep reflection access to private members of a named module. If needed, use valid JPMS mechanisms and scope permissions tightly.

## 8. Diagnosing Which Class Was Actually Loaded by the JVM

### Printing Runtime Identity and Origin

Illustrative code snippet inside an agent/app that already has a reference to the class:

~~~java
Class<?> type = org.example.codec.Codec.class;
System.out.println("name=" + type.getName());
System.out.println("loader=" + type.getClassLoader());
System.out.println("module=" + type.getModule());
var pd = type.getProtectionDomain();
var origin = (pd == null || pd.getCodeSource() == null)
        ? null : pd.getCodeSource().getLocation();
System.out.println("origin=" + origin);
~~~

`CodeSource` may be `null` for bootstrap or custom loaders; do not use it alone as absolute proof. However, it is useful when finding which JAR defined a specific class.

### JVM Class-Loading Logs

HotSpot supports:

~~~bash
java -Xlog:class+load=info -javaagent:out/bad-agent.jar -cp out/app:out/app-lib.jar demo.app.Main
~~~

PowerShell:

~~~powershell
java "-Xlog:class+load=info" "-javaagent:out/bad-agent.jar" -cp "out/app;out/app-lib.jar" demo.app.Main
~~~

The output is very long; search for `org.example.codec.Codec` and the `source: ...` line to see which version the runtime loaded. Do not leave this level of logging enabled indefinitely in production without accounting for overhead/log size.

### Maven Dependency Tree and JAR Listing

~~~bash
mvn dependency:tree
jar --list --file target/shaded-agent-1.0.0.jar
~~~

`dependency:tree` shows the graph resolved by Maven in the **project being built**, not where the JVM loaded classes from when combined with an application or other agents. `jar --list` verifies the actual artifact, but merely having a class in the JAR does not mean the JVM used it. You need to combine the compile graph, artifact listing, and runtime class-loading evidence.

### Workflow for Investigating `NoSuchMethodError`

1. Read the full **owner class, method name, and descriptor** in the stacktrace.
2. Verify the classloader, module, and source of the owner class **at runtime**.
3. Compare the compile-time API and runtime API via `javap -public -classpath ... <binaryName>` (substituting actual class name/path).
4. Inspect direct + transitive dependencies of the agent, app, and multiple agents.
5. Decide which dependencies must be relocated and which are shared public APIs.
6. Build the final shaded agent, and test startup, classloading, reflection, SPI, and required methods.
7. If the error turns into `NoClassDefFoundError` after relocation, check helper loader placement and resource paths; do not just change the prefix again.

## 9. Multiple Agents and Practical Limitations

The JVM can run:

~~~bash
java -javaagent:agentA.jar -javaagent:agentB.jar -cp app.jar demo.app.Main
~~~

The `premain` methods are invoked in the order `-javaagent` appears, but class loading/transformer ordering depends on registration, capabilities, and transformer groups. Command-line order **is not a version-pinning strategy** for libraries with the same name in the system loader.

If agent A and B both bundle `org.example.codec.Codec` from two versions, they can conflict. If both relocate into **a shared prefix** such as `shaded.codec`, they conflict again under the new name. Use a distinct prefix with clear ownership:

~~~text
com.company.agentA.shaded.codec.Codec
com.vendor.agentB.shaded.codec.Codec
~~~

If agents need the **same public tracing API**, agree on the contract and class identity instead of relocating the API on both sides and expecting casts/interop to work automatically. Do not let transformed app bytecode call private dependency implementations from a third-party agent without a stability guarantee.

Minimal testing: agent A, agent B, A+B and B+A when they interact, app using dependency v1/v2, app classpath/named modules, and bootstrap/custom loader targets if applicable. Enable controlled diagnostics to compare class origins and classfile transformations.

## 10. Common Pitfalls Table

| Wrong Design / Assumption | Consequence | How to Handle |
|---|---|---|
| Fat JAR equals isolation | Duplicate classes with the same FQCN | Shade + relocate internal dependencies |
| App/agent always prioritizes a deterministic version | Bugs only occur in certain environments | Do not rely on load order |
| BOM version pinning alone is enough | Runtime system loader still shares namespace | Test artifact against different app dependencies |
| Relocate all public APIs | Breaks class identity and interoperability | Keep API boundary consistent |
| Maven Shade automatically fixes all SPI/XML | Providers/configs are not merged | Resource transformers + runtime SPI tests |
| ServiceLoader descriptors still use old FQCNs | `ServiceConfigurationError` | Rewrite descriptors, test final JAR |
| Reflection with class strings is always rewritten | Dynamic configs bypass the shader | Integration tests + explicit mappings |
| Enable `minimizeJar` right away | Deletes providers used via reflection | Disable/allowlist before having coverage |
| Put the entire agent JAR on bootstrap | Pollutes loader namespace, reverse linking fails | Minimal bootstrap helper |
| Shading Java code automatically fixes native JNI | JNI exports still follow original symbols | Separate native linkage tests |
| Original signed JAR metadata remains valid | Verification/security errors | Filter old signatures, keep licenses, re-sign when needed |
| Testing on IDE classpath is enough | Final uber JAR differs significantly from dev | Smoke test `-javaagent:final.jar` |
| Having the right class in the JAR means the JVM used it | Runtime load source may differ | Class-loader logs/CodeSource |
| Classfile version depends on project `--release 17` | Transitive lib may require newer Java | Check compatibility of all classes |

## 11. Release Checklist

- [ ] List direct and transitive dependencies, licenses, versions, and CVE exposure.
- [ ] Classify internal implementation vs shared API/bridge.
- [ ] Relocate internal packages that may collide, using a unique prefix with clear ownership.
- [ ] Do not relocate JDK packages or accidentally alter shared API binary identity.
- [ ] Verify correct `Premain-Class`/`Agent-Class`, module/class loader placement, and manifest.
- [ ] Inspect JAR entries after shading: unintended original classes are gone, new classes are present.
- [ ] Test SPI/services, reflection, resource bundles, generated code, serialization, and JNI if used.
- [ ] Test multi-release JARs and classfile versions on the lowest supported JDK.
- [ ] Manage signatures/NOTICE/licenses and reproducible build/artifact hashes.
- [ ] Avoid minimizing before having sufficient integration coverage for reflective providers.
- [ ] Smoke-test the final JAR with app v1/v2, multiple agents, and named/custom/bootstrap loaders where relevant.
- [ ] Log class origin/loader diagnostics and bounded startup self-check results.
- [ ] Do not swallow linkage errors and assume the agent is working normally.
- [ ] Measure overhead/GC/memory after adding shaded dependencies.
- [ ] Have a safe disable/fallback mode and artifact rollback if rollout encounters errors.

## 12. Self-Check Questions

1. **What is class identity based on?** Binary name and defining class loader.
2. **Does bundling a dependency into the agent JAR isolate the namespace?** No, if class names are not changed.
3. **Why can an agent compiled against v1 still see v2?** The same runtime loader may have already defined a class with the same FQCN from the app.
4. **How does `NoSuchMethodError` differ from `NoSuchMethodException`?** Runtime linkage error vs reflective lookup exception.
5. **How does relocation differ from renaming a JAR entry?** The shader must also rewrite corresponding bytecode references/metadata.
6. **Should you relocate a public API that the app needs to cast?** Usually no, because it breaks class identity.
7. **What should be checked for SPI?** `META-INF/services` and provider names after merging/relocating.
8. **What is Maven Shade's `ManifestResourceTransformer` used for?** Writing manifest entries like `Premain-Class` in the final JAR.
9. **Why is `minimizeJar` risky?** Reflection/providers may not appear in the static reference graph.
10. **Does relocation solve `NoClassDefFoundError` when a bootstrap target calls a system helper?** No; proper helper loader placement is required.
11. **Are two agents that relocate to the same prefix isolated?** No; class names still collide.
12. **Does the dependency tree prove the runtime class source?** No; you must inspect loader/CodeSource/class-load logs.
13. **Does shading automatically make a dependency compatible with Java 17 if it requires JDK 21?** No.
14. **Was the Maven Shade plugin actually tested in this article?** Yes, with Commons Lang 3.14.0, and the output JAR ran successfully.
15. **How can you verify isolation more reliably than just checking build success?** Inspect the artifact, run the final JAR with an app having a different dependency version, and test SPI/reflection.

## 13. Official Documentation

- [Java SE 21 — Package `java.lang.instrument`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): agent classes, system class loader, unnamed module, manifest.
- [Java SE 21 — `Instrumentation`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): classloader search and transform APIs.
- [Java SE 21 — `ClassLoader`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): parent delegation, system loader, class identity.
- [Maven Shade — Usage](https://maven.apache.org/plugins/maven-shade-plugin/usage.html): uber JAR and plugin lifecycle.
- [Maven Shade — Relocating Classes](https://maven.apache.org/plugins/maven-shade-plugin/examples/class-relocation.html): rewriting class/package names.
- [Maven Shade — Resource Transformers](https://maven.apache.org/plugins/maven-shade-plugin/examples/resource-transformers.html): manifest and services merging.
- [Maven Shade — Selecting Contents](https://maven.apache.org/plugins/maven-shade-plugin/examples/includes-excludes.html): filters, signature entries, and minimize.
- [GradleUp Shadow — Relocation](https://gradleup.com/shadow/configuration/relocation/): Gradle namespace rewriting.
- [Java SE 21 — `ServiceLoader`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html): SPI resource contract and errors.
- [Java SE 21 — `NoSuchMethodError`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/NoSuchMethodError.html): binary linkage errors.
