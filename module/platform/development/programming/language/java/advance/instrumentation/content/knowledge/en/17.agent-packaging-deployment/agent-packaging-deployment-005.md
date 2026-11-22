# Do Not Depend on Unsupported Internal JDK Bytecode Processing Classes

## 1. Why is this a requirement for packaging and deploying a Java agent?

A Java agent may work fine on a development machine, yet fail immediately when moved to another JDK or runtime if the agent **relies directly on internal JDK bytecode processing classes**, for example `jdk.internal.org.objectweb.asm.ClassReader`. Such classes are implementation details of the JDK, not a public programming contract for applications. Working on one JDK version **does not mean stable support**.

In Java 9+, the module system also restricts access to internal packages. A `jdk.internal...` import can be rejected right at compile time; if you force the compiler with `--add-exports`, at runtime it may hit `IllegalAccessError` because the target JVM does not have the corresponding flag. Even if temporarily “opened,” the internal class version can change in a JDK update outside the agent’s control.

**Main objective of this lesson:** design, package, and test an agent capable of processing bytecode without **linking to unsupported internal JDK APIs**. Preferred approach:

1. Use **`java.lang.instrument`** — the official API to obtain `Instrumentation`, register transformers, and retransform or redefine classes.
2. For Java 17/21, use a **public, version-managed** bytecode processing library such as OW2 ASM or Byte Buddy, instead of the internal ASM copy inside the JDK.
3. Package the required dependencies **into the agent JAR** or arrange a controlled class loader; consider **shading and relocating** to avoid version collisions with the target application's libraries.
4. If deploying on a minimum of **JDK 24+**, you can use the public `java.lang.classfile` API standardized in JDK 24 (JEP 484). **Do not use this API when you need to run on JVM 17/21**.
5. Verify the bytecode target version, manifest, and dependency graph, and test on real JVMs with `jdeps --jdk-internals` along with `-Xverify:all`.

This lesson includes three experiments: an **intentional failure** when importing internal ASM; a **real Java 17+ agent** using ASM from Maven, shading, and successfully injecting a probe; and an example of the **public JDK 24 Class-File API** that can parse and transform a Java 17 classfile.

## 2. Distinguishing supported APIs from implementation details

### 2.1. Quick identification table

| Group | Example | Assessment when writing a Java agent |
|---|---|---|
| Java SE public API | `java.lang.instrument.Instrumentation`, `ClassFileTransformer` | Documented and supported within the scope of the Java SE version |
| Java SE public Class-File API from JDK 24 | `java.lang.classfile.ClassFile`, `ClassModel` | Publicly available from JDK 24; not present on 17/21 |
| External library with its own releases | `org.objectweb.asm.ClassReader`, `org.objectweb.asm.commons.AdviceAdapter` | Valid if dependencies are declared, a suitable version is chosen, and distributed properly |
| External instrumentation library | `net.bytebuddy.*` | Valid if dependencies and runtime compatibility are managed |
| JDK internal package | `jdk.internal.org.objectweb.asm.*` | **Do not use as a production dependency**; no compatibility contract for apps |
| JDK internal/compiler implementation | Some `com.sun.tools.javac.*` or `jdk.internal.*` | Must check the actual API contract; do not assume supported just because it compiles with flags |
| Documented JDK-specific API | E.g. module `jdk.attach` with `com.sun.tools.attach.VirtualMachine` | Can be a **published JDK-specific API**; do not equate every `jdk.*`/`com.sun.*` name with unsupported |

**Key takeaway:** package names can be an indicator, **not the sole classification criterion**. The decisive boundary is whether the API has public documentation and a compatibility/support contract for applications or is merely an internal implementation detail inside the JDK.

### 2.2. Two ASM packages with different responsibilities

~~~text
org.objectweb.asm.ClassReader
  -> Official OW2 ASM, declared from org.ow2.asm:asm
  -> development team manages versions and releases independently
  -> you actively package the required dependencies

jdk.internal.org.objectweb.asm.ClassReader
  -> ASM copy residing inside the JDK, internal package of java.base
  -> not a public application library
  -> JDK may upgrade/modify the API without guaranteeing compatibility with the agent
~~~

Even though the class names share the same suffix, **do not swap imports between the two packages as if they were two equivalent supported implementations**. An agent importing `jdk.internal.org.objectweb.asm` depends on a specific JDK shape and can be blocked by JPMS.

### 2.3. “Present on the machine” does not mean “properly packaged”

Some developers think that because `jdk.internal.org.objectweb.asm` is already built into the Java runtime, using it saves JAR size and simplifies deployment. This creates a **hidden dependency on the vendor and target JVM version**. What you save at build time can turn into hard-to-fix runtime errors, especially when the agent is deployed independently across hundreds of JVMs.

Conversely, if you use official OW2 ASM, you can pin versions, have checksums, a dependency inventory, security updates, and auditable build artifacts.

## 3. Why does module encapsulation cause internal code to fail?

Since Java 9, internal packages are not exported to the unnamed module or application modules by default, except for documented exceptions. `jdk.internal.org.objectweb.asm` resides in `java.base` but is **not exported as a public Java SE API**.

### 3.1. Compile-time error

An intentionally wrong example, file **`InternalAsmDemo.java`**:

~~~java
import jdk.internal.org.objectweb.asm.ClassReader;

public final class InternalAsmDemo {
    public static void main(String[] args) {
        System.out.println(
                "internal-class=" + ClassReader.class.getName());
    }
}
~~~

With a modern JDK, run:

~~~bash
javac -d outInternal InternalAsmDemo.java
~~~

Normally `javac` rejects it and explicitly states that the package in `java.base` is **not visible/not exported** to the unnamed module. Even if using `javac --release 17`, APIs that are not part of Java 17 supported symbols do not become valid APIs either.

**This is an intentional negative test**. Do not solve it by switching the source to another internal import.

### 3.2. Forcing compilation with --add-exports still does not make it a public API

On the test JDK, the command below allows compiling the experiment:

~~~bash
javac --add-exports java.base/jdk.internal.org.objectweb.asm=ALL-UNNAMED -d outInternal InternalAsmDemo.java
~~~

However, running **without runtime export**:

~~~bash
java -cp outInternal InternalAsmDemo
~~~

fails with **`IllegalAccessError`** because classes in the unnamed module are not exported the corresponding package by `java.base`.

If run again with the export flag:

~~~bash
java --add-exports java.base/jdk.internal.org.objectweb.asm=ALL-UNNAMED -cp outInternal InternalAsmDemo
~~~

the experiment on JDK 24.0.2 prints:

~~~text
internal-class=jdk.internal.org.objectweb.asm.ClassReader
~~~

This is only a **workaround to demonstrate access control**, not a production architecture. To run the agent on other machines, you must ensure the same flags are passed to every JVM, and **even then** the JDK still does not promise to keep internal APIs stable.

**Flag distinction:** `--add-exports` opens access to a package's public types under module rules; `--add-opens` mainly opens **deep reflection**. Do not use `--add-opens` as a default cure-all for source import or bytecode linkage errors.

### 3.3. Checking static dependencies with jdeps

After forcing compilation solely for verification purposes:

~~~bash
jdeps --jdk-internals outInternal/InternalAsmDemo.class
~~~

On the tested JVM, `jdeps` reports:

~~~text
InternalAsmDemo.class -> java.base
   InternalAsmDemo -> jdk.internal.org.objectweb.asm.ClassReader  JDK internal API (java.base)
~~~

`jdeps` also warns that JDK internal APIs are implementation details that may be removed or changed incompatibly. This is an **important QA tool** before publishing an agent JAR.

**Limitations of jdeps:** it performs static dependency analysis via classfiles and does not guarantee detecting internal class names assembled via strings and invoked through reflection, runtime-generated code, or native dependencies. Therefore, combine it with source scanning, dependency graphs, and behavioral testing.

## 4. Deployment risks when tied to internal ASM

### 4.1. Instability across JDK updates

The ASM copy embedded in the JDK serves **the JDK's own needs**, not semantic versioning for applications. Methods, constructors, constants, and internal patches may differ from the ASM release you find on Maven Central. The agent risks `NoSuchMethodError`/`NoSuchFieldError` or different parsing behavior after a JDK upgrade.

### 4.2. Differences between build servers and production JVMs

An agent compiled on JDK X with `--add-exports` may:

- fail to compile on CI/JDK Y;
- compile, yet fail on the target JVM without runtime `--add-exports`, causing `IllegalAccessError`;
- link, yet fail to understand the classfile major version/attributes of application classes;
- depend on different vendor-specific internals.

**Test on the actual supported runtime matrix**, rather than treating the developer's machine as the single source of truth.

### 4.3. Flags are operational debt

Requiring the operations team to add `--add-exports java.base/jdk.internal.org.objectweb.asm=ALL-UNNAMED` to every application just so the agent can run increases deployment coupling. This is a strong exception to JPMS and should be flagged and bounded if used only temporarily for migration.

### 4.4. Avoid overly broad negative policies

Not all `com.sun.*`, `sun.*`, `jdk.*` packages have the same support status. For example, `jdk.attach` has public JDK-specific documentation. The safe rule is: **rely only on official APIs that have a contract for the target runtime**, and do not use an implementation namespace directly just because it is on the classpath/boot layer.

## 5. Choosing a supported bytecode processing approach

| Requirement | Solution | Minimum JDK runtime | Notes |
|---|---|---|---|
| Java agent receives class bytes, installs transformer | `java.lang.instrument` | Java 5+ (many capabilities since Java 6/9) | Instrumentation management API; does not provide a general-purpose bytecode parser/visitor before JDK 24 |
| Java 17/21/24, need low-level bytecode reading/modifying | Official **OW2 ASM** `org.ow2.asm` | Depends on chosen ASM release | Choose an ASM release that understands the target JVM's classfile major version |
| Want easier advice/interception declaration | **Byte Buddy** | Depends on Byte Buddy release and VM | High-level library; requires packaging/compatibility testing |
| JVM is JDK 24+ only and want public JDK API | **`java.lang.classfile`** | **JDK 24** | Standardized under JEP 484; unavailable on Java 17/21 |
| Only need telemetry without modifying Java method bodies | JFR, JVM metrics, or published APIs | Depends on API and runtime | Avoid bytecode dependencies when unnecessary |
| Existing code uses `jdk.internal.org.objectweb.asm` | Switch to OW2 ASM or public Class-File API if appropriate | Per selection | Do not stop at adding flags; control the dependency graph |

**Recommendation in this lesson:** because an agent typically needs to support Java 17 and above, the hands-on section uses **OW2 ASM 9.11.1** and **Maven Shade Plugin 3.6.2**, both of which are **public** dependencies declared by version. The example is compiled with `--release 17` and run with `-Xverify:all`.

If a project chooses Byte Buddy, it must likewise pin versions, verify classfile compatibility, and package dependencies properly. Do not treat using an external library as a reason to skip verification.

## 6. End-to-end: Java 17 agent with self-packaged OW2 ASM

The hands-on program **does not import any JDK internal package**. The agent:

1. Uses `java.lang.instrument.Instrumentation` to register a `ClassFileTransformer`.
2. Filters specifically for class `demo.Service` when loaded by the JVM.
3. Uses OW2 ASM `ClassReader`, `ClassVisitor`, `ClassWriter`, and `AdviceAdapter` to insert a `System.out.println("agent:enter-hello")` statement upon entering the `hello()` method.
4. Preserves the method's `"hello"` return value.
5. Packages ASM `org.objectweb.asm` **inside the agent JAR** and **relocates** it to `demo.agent.shaded.asm` to avoid package collisions with another ASM version in the application.
6. Runs via `-javaagent`, without passing any `--add-exports` or `--add-opens`.

This experiment helps distinguish the two approaches:

~~~text
WRONG API CONTRACT:
  import jdk.internal.org.objectweb.asm.ClassReader;

CORRECT DEPENDENCY SCOPE:
  import org.objectweb.asm.ClassReader;
  (dependency org.ow2.asm:asm is declared and packaged)
~~~

**Note:** With shading, the source still imports `org.objectweb.asm.*` at compile time, while the plugin **rewrites bytecode and moves class files** in the final JAR. Do not manually change Java imports to the shaded package in source code.

### 6.1. Project structure

~~~text
safe-asm-agent/
├── pom.xml
├── src/
│   └── main/
│       └── java/
│           └── demo/
│               └── Agent.java
├── app/
│   └── demo/
│       ├── Service.java
│       └── Main.java
├── app-out/               # created during build
└── target/                # created by Maven
    └── safe-asm-agent-1.0.0.jar
~~~

`app` contains the demo code **not included in the agent JAR**. `mvn package` packages the agent and ASM into a standalone artifact; then `javac` compiles the application targeting Java 17.

## 7. Maven POM: pin versions and relocate ASM

File **`pom.xml`**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>safe-asm-agent</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.ow2.asm</groupId>
      <artifactId>asm</artifactId>
      <version>9.11.1</version>
    </dependency>
    <dependency>
      <groupId>org.ow2.asm</groupId>
      <artifactId>asm-commons</artifactId>
      <version>9.11.1</version>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.0</version>
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
                  <pattern>org.objectweb.asm</pattern>
                  <shadedPattern>demo.agent.shaded.asm</shadedPattern>
                </relocation>
              </relocations>

              <transformers>
                <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                  <manifestEntries>
                    <Premain-Class>demo.Agent</Premain-Class>
                  </manifestEntries>
                </transformer>
              </transformers>

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
            </configuration>
          </execution>
        </executions>
      </plugin>
    </plugins>
  </build>
</project>
~~~

**Explanation of each part:**

- `maven.compiler.release=17`: the agent's source and output classfiles target Java 17, without depending on Java 24 compile-time APIs.
- `org.ow2.asm:asm` and `asm-commons`: two public OW2 ASM libraries managed by Maven, not using the JDK's internal ASM copy.
- `asm-commons` provides `AdviceAdapter`. Maven downloads any required transitive dependencies according to the dependency graph.
- `maven-shade-plugin` runs in the `package` phase to produce an **agent JAR containing dependencies**.
- `relocations` renames `org.objectweb.asm` to the private namespace `demo.agent.shaded.asm` in the final JAR; both `asm` and `asm-commons` are relocated together.
- `ManifestResourceTransformer` writes `Premain-Class: demo.Agent` into the main manifest so `-javaagent` finds the right entry point.
- `META-INF/*.SF`, `*.DSA`, `*.RSA` are excluded from the uber JAR because the original signatures of dependency JARs **are no longer valid after merging/relocating**. This does not mean disabling supply-chain verification: the build must still verify source dependencies, checksums/signatures, and organizational policy.
- `createDependencyReducedPom=false` keeps the example predictable without replacing the POM with a reduced version in this lesson; library-publishing projects may handle this differently.
- **Do not enable `minimizeJar` blindly**; classes used via reflection, `ServiceLoader`, module/service descriptors, or bootstrap may be missed by static dependency analyzers.

**Version selection:** 9.11.1 and 3.6.2 are the versions built and tested in this lesson. For real-world projects, still verify support windows, security patches, and dependency update schedules rather than keeping them frozen indefinitely.

## 8. Java agent source: using only Instrumentation and public ASM

File **`src/main/java/demo/Agent.java`**:

~~~java
package demo;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.commons.AdviceAdapter;

public final class Agent {
    public static void premain(
            String options, Instrumentation inst) {

        inst.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(
                    ClassLoader loader,
                    String name,
                    Class<?> redefining,
                    ProtectionDomain domain,
                    byte[] bytes) {

                if (!"demo/Service".equals(name)) {
                    return null;
                }

                ClassReader reader = new ClassReader(bytes);
                ClassWriter writer = new ClassWriter(
                        reader, ClassWriter.COMPUTE_MAXS);

                ClassVisitor visitor = new ClassVisitor(
                        Opcodes.ASM9, writer) {

                    @Override
                    public MethodVisitor visitMethod(
                            int access,
                            String method,
                            String desc,
                            String sig,
                            String[] exceptions) {

                        MethodVisitor mv = super.visitMethod(
                                access, method, desc, sig, exceptions);

                        if (mv == null
                                || !"hello".equals(method)
                                || !"()Ljava/lang/String;".equals(desc)) {
                            return mv;
                        }

                        return new AdviceAdapter(
                                Opcodes.ASM9,
                                mv, access, method, desc) {

                            @Override
                            protected void onMethodEnter() {
                                visitFieldInsn(
                                        Opcodes.GETSTATIC,
                                        "java/lang/System",
                                        "out",
                                        "Ljava/io/PrintStream;");

                                visitLdcInsn(
                                        "agent:enter-hello");

                                visitMethodInsn(
                                        Opcodes.INVOKEVIRTUAL,
                                        "java/io/PrintStream",
                                        "println",
                                        "(Ljava/lang/String;)V",
                                        false);
                            }
                        };
                    }
                };

                reader.accept(visitor, 0);
                return writer.toByteArray();
            }
        }, false);
    }
}
~~~

### 8.1. Purpose of each API

- `Instrumentation` is supplied by the JVM via `premain`; the agent does not instantiate this interface itself.
- `ClassFileTransformer` receives the classfile `byte[]` when a class is defined; it returns `null` if no class modification is made, or a new `byte[]` when transformed.
- `name` uses the **internal JVM name** `demo/Service`, not `demo.Service`.
- `ClassReader` reads the target class's classfile; `ClassWriter` produces the new bytes.
- `AdviceAdapter.onMethodEnter` inserts a `println` call at the start of the `hello` method.
- `COMPUTE_MAXS` lets ASM compute `max_stack/max_locals` needed for simple insertions; it does not mean every control-flow change is automatically valid. If adding branches/exception handlers or complex frames, you need an appropriate `COMPUTE_FRAMES` strategy and verifier testing alongside class hierarchy/class loader awareness.
- `Opcodes.ASM9` is ASM's **API version constant** used in visitors, not the classfile major version or dependency version number 9.11.1.
- `addTransformer(..., false)` requests transformation only on initial class loading/appropriate redefinition; the example does not request retransformation. If you need to instrument **already-loaded** classes, you must explicitly design for `Can-Retransform-Classes` capability, `addTransformer(transformer, true)` with `retransformClasses`, and respect structural change limits.
- The agent intentionally instruments only one demo class; it does not instrument `java.*`, its own ASM, or helper classes, avoiding class loading recursion and deadlocks.

**Why insert `System.out.println`?** Because the target only needs to resolve an existing public JDK API, avoiding making the lesson depend on loading helper classes from another class loader. In production, replace synchronous logging with safe/low-overhead telemetry while controlling module/package access.

### 8.2. Avoiding class loading order errors

With `-javaagent`, the JVM calls `premain` **before `Main.main`**. Only afterward does `Main` instantiate `Service`, so the transformer has the opportunity to receive `Service`'s classfile when it is defined. If `Service` was already loaded before registering the transformer, this startup example does not automatically update the existing class. When late attach is needed, you must use retransform/redefine within VM limits.

### 8.3. Why not import jdk.internal?

The source above only imports:

~~~java
org.objectweb.asm.ClassReader
org.objectweb.asm.ClassVisitor
org.objectweb.asm.ClassWriter
org.objectweb.asm.MethodVisitor
org.objectweb.asm.Opcodes
org.objectweb.asm.commons.AdviceAdapter
~~~

These are APIs **from declared Maven dependencies**. The final JAR relocates them to `demo.agent.shaded.asm`. There is not a single import or invocation of `jdk.internal.org.objectweb.asm`. Therefore, the agent does not need operators to add `--add-exports java.base/jdk.internal.org.objectweb.asm=ALL-UNNAMED`.

## 9. Standalone test application

File **`app/demo/Service.java`**:

~~~java
package demo;

public final class Service {
    public String hello() {
        return "hello";
    }
}
~~~

File **`app/demo/Main.java`**:

~~~java
package demo;

public final class Main {
    public static void main(String[] args) {
        System.out.println("app:begin");
        System.out.println(
                "result=" + new Service().hello());
        System.out.println("app:end");
    }
}
~~~

The application code **does not import ASM**. It only uses Java APIs; that is a deployment goal: the app does not need to know which tool the agent uses to process bytecode and does not need to install the same ASM version.

### 9.1. Create directory

In the `safe-asm-agent` root directory:

~~~bash
mkdir -p app-out
~~~

With PowerShell:

~~~powershell
New-Item -ItemType Directory -Force app-out
~~~

### 9.2. Build and run commands

~~~bash
mvn -q -DskipTests package
javac --release 17 -d app-out app/demo/Service.java app/demo/Main.java
java -Xverify:all -javaagent:target/safe-asm-agent-1.0.0.jar -cp app-out demo.Main
~~~

If the build is in a Maven environment with an internal dependency proxy, configure repositories/mirrors according to organizational procedures. Do not download JARs from untrusted sources and put them into a production agent. The lab machine had Maven 3.9.12, javac 24.0.2 compiling with `--release 17`, and JVM 24.0.2 for execution.

**Actual stdout:**

~~~text
app:begin
agent:enter-hello
result=hello
app:end
~~~

There are four independent conclusions:

1. `mvn package` produced an agent JAR with a valid manifest.
2. The JVM loaded `Agent.premain` and registered the transformer.
3. `ClassFileTransformer` read `demo/Service` properly and inserted the probe before `hello`'s logic.
4. The return value `hello` is unchanged; running with `-Xverify:all` produced no `VerifyError`.

If run **without `-javaagent`**:

~~~bash
java -cp app-out demo.Main
~~~

The application output will lack the `agent:enter-hello` line while still having `app:begin`, `result=hello`, `app:end`. This is a useful control when explaining the effect of instrumentation.

### 9.3. Inspecting the JAR after shading

~~~bash
jar tf target/safe-asm-agent-1.0.0.jar
~~~

In the tested build:

- `demo/Agent.class` exists.
- `demo/agent/shaded/asm/ClassReader.class` **is in the JAR**.
- `org/objectweb/asm/ClassReader.class` **is no longer under the unrelocated name** in the final JAR.
- `jdk/internal/org/objectweb/asm/ClassReader.class` **does not exist**.
- `META-INF/MANIFEST.MF` contains `Premain-Class: demo.Agent`.

You can view the manifest:

~~~bash
unzip -p target/safe-asm-agent-1.0.0.jar META-INF/MANIFEST.MF
~~~

`unzip` is an OS-dependent utility; if not available on the machine, use `jar xf` into a temporary inspection directory or read the entry using Java `JarFile`. **Do not edit the manifest inside an agent JAR after it has been signed/released** without an appropriate repackaging and re-signing step.

### 9.4. jdeps on the final artifact

~~~bash
jdeps --jdk-internals target/safe-asm-agent-1.0.0.jar
~~~

The goal is to find **static** dependencies on JDK internal APIs in the final artifact. A clean scan **does not guarantee** all reflection/runtime-generated code is safe; also scan source/pom/transitive dependencies and run integration tests.

Also test the `--multi-release` flag when inspecting a real **multi-release JAR**, so version-specific entries are not missed.

## 10. Why are shading/relocation important for a Java agent?

### 10.1. The agent runs inside another application's JVM

A Java agent is not just an ordinary app library: it is loaded inside the target application's JVM and can be affected by **classpath, system/boot class loader, module boundaries, and multiple agents**. If the agent packages ASM as plain `org.objectweb.asm` while the app already has a different ASM version, class loading can pick an unexpected version and cause:

- `NoSuchMethodError` or `NoSuchFieldError` when ASM APIs differ;
- `LinkageError` because classes from two versions are incompatible;
- different parser/visitor behavior with newer classfile major versions;
- results that cannot be reproduced between test and production.

**Shading** bundles dependencies into the deployable artifact; **relocation** changes namespaces to reduce the probability of binary name conflicts. The two operations are related but **not synonymous**.

### 10.2. Use a private namespace, not under jdk.internal

In `pom.xml`:

~~~xml
<relocations>
  <relocation>
    <pattern>org.objectweb.asm</pattern>
    <shadedPattern>demo.agent.shaded.asm</shadedPattern>
  </relocation>
</relocations>
~~~

The `demo.agent.shaded.asm` namespace belongs to the agent's control, not `jdk.internal.*`. Do not relocate ASM to `jdk.internal.org.objectweb.asm`: that is an internal package of `java.base` and not a place to deploy your library.

### 10.3. Shading risks that still require QA

- Relocation updates bytecode references and class entry names, but class names used in **strings/reflection** may not be updated the way you expect.
- Resource names in `META-INF/services`, framework metadata, or provider declarations may require dedicated resource transformers.
- Signed artifacts have old signatures that are no longer valid after merging, so the example configuration strips signature metadata. Supply-chain controls must be performed **before packaging** and on the newly released artifact.
- Do not relocate public packages that the agent's API intends to share with the application, unless there is a clear compatibility strategy.
- Do not apply `minimizeJar` if the tool cannot analyze classes used via reflection or dynamic class loading.
- If packaging the agent as a multi-release JAR or attaching to a modular application, check manifest/resources/classfile versions in the **final JAR**, not just the `target/classes` output.

### 10.4. The bootstrap class loader does not automatically see every helper

If a transformer inserts a call to a helper class located inside the agent JAR, the instrumented class may be loaded by a class loader **that cannot see the helper**. Especially when instrumenting bootstrap classes, calling a helper from the system classloader is not always valid.

Ways to handle this include:

- Designing probes to call only APIs available in bootstrap modules when sufficient (as in the demo).
- Supplying a minimal helper JAR to bootstrap via `Instrumentation.appendToBootstrapClassLoaderSearch` per the API contract, with control over signed JARs, dependencies, and package boundaries.
- Using `Instrumentation.redefineModule` to add read/export/open edges when module accessibility is genuinely needed; this method does not change class loader placement and does not make helper classes appear on its own.
- Placing the helper in a loader that both the target and agent can validly link against.

**Do not put the entire parser/ASM/Jackson/logging stack into bootstrap just for convenience**. That expands coupling and can cause class loading failures during JVM startup.

## 11. Public Class-File API of JDK 24+: no JDK internals needed

Starting in **JDK 24**, `java.lang.classfile` is a public Java platform API to parse, generate, and transform classfiles. It was standardized by **JEP 484**, following preview stages in JDK 22 (JEP 457) and JDK 23 (JEP 466).

Officially documented types:

- `java.lang.classfile.ClassFile`: parse/build/transform context.
- `java.lang.classfile.ClassModel`: model of a parsed class.
- `java.lang.classfile.ClassTransform`: represents a transformation.
- `ClassFile.of()`: creates a context.
- `ClassFile.parse(...)`: parses class bytes.
- `ClassFile.transformClass(...)`: produces class bytes from a transformation.
- `ClassFile.verify(...)`: verifies class bytes per the API.

**Important constraint:** code linking to `java.lang.classfile` **does not run on Java 17/21** because this package does not exist on those runtimes. If the agent must support 17/21, use appropriate ASM/Byte Buddy or publish separate/multi-release artifacts with designed and tested dispatch.

### 11.1. Practical example without ASM

File **`Sample.java`**:

~~~java
public final class Sample {
    public static int twice(int input) {
        return input * 2;
    }
}
~~~

File **`PublicClassfileDemo.java`**, running on **JDK 24+**:

~~~java
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.lang.classfile.ClassTransform;
import java.nio.file.Files;
import java.nio.file.Path;

public final class PublicClassfileDemo {
    public static void main(String[] args)
            throws Exception {
        ClassFile api = ClassFile.of();
        ClassModel model = api.parse(
                Files.readAllBytes(Path.of(args[0])));

        byte[] copy = api.transformClass(
                model, ClassTransform.ACCEPT_ALL);

        System.out.println(
                "name=" + model.thisClass().asInternalName());
        System.out.println(
                "major=" + model.majorVersion());
        System.out.println(
                "copy-valid=" + api.verify(copy).isEmpty());
    }
}
~~~

This program uses the **pass-through transform** `ClassTransform.ACCEPT_ALL` to demonstrate the public API and verify the generated classfile; it **does not inject a probe into any method**. For actual instrumentation, you must provide an appropriate `ClassTransform`/`MethodTransform`/`CodeTransform`, manage stack maps, and verify the output.

### 11.2. Build and run on JDK 24+

Create two output directories:

~~~bash
mkdir -p out17 out24
~~~

Build:

~~~bash
javac --release 17 -d out17 Sample.java
javac -d out24 PublicClassfileDemo.java
java -Xverify:all -cp out24 PublicClassfileDemo out17/Sample.class
~~~

**Tested stdout on JDK 24.0.2:**

~~~text
name=Sample
major=61
copy-valid=true
~~~

Explanation: `Sample.class` was built for Java 17, so its classfile major version is **61**; the public JDK 24 API reads and regenerates a valid classfile. **Do not equate reading a Java 17 classfile with a JDK 24 tool with running that tool on JVM 17**.

### 11.3. Do not force --release 17 for code importing java.lang.classfile

If `PublicClassfileDemo.java` imports `java.lang.classfile`, compiling on JDK 24 with `javac --release 17 ...` will **fail**: `--release 17` restricts APIs to Java SE 17, and `java.lang.classfile` was not yet an API in that release.

Choose technology only after establishing the **minimum runtime**. An agent artifact compiled on Java 24 typically has classfile major **68**, which JVM 17 cannot load directly. If you need to run on both 17 and 24, the simplest approach is an **ASM agent built targeting 17** as in sections 6–9; consider multi-release packaging only when it brings real value and the operations team can test all variants.

## 12. Java version and classfile major version compatibility

| Target JVM | Typical max classfile major | Public Class-File API? | Deployment approach to consider |
|---|---:|---|---|
| Java 17 | 61 | No | `java.lang.instrument` + packaged ASM/Byte Buddy |
| Java 21 | 65 | No | `java.lang.instrument` + bytecode-65-compatible ASM/Byte Buddy |
| Java 24 | 68 | Yes, standard from 24 | Can use `java.lang.classfile` or supported ASM/Byte Buddy |
| Newer Java | Depends on release | Yes if still within supported APIs | Check new classfile major versions, library support, and compatibility matrix |

Three things must be distinguished:

1. **Agent source/API release:** `--release 17` or `--release 24` determines the agent's bytecode and which APIs it can call.
2. **Target classfile major version:** an app targeting Java 24 can produce classfile major 68 that an older ASM does not understand, even if the agent runs on JVM 24.
3. **JVM running the agent:** must be able to load the agent's own bytecode and all shaded dependencies; a lower target classfile **does not automatically guarantee** the bytecode processing library supports the newer JVM's classfile format.

The **ASM library version** and the constant `Opcodes.ASM9` are also two different concepts. `Opcodes.ASM9` is the visitor API level, not a requirement for ASM artifact version `9.0` or classfile major 9.

### 12.1. When does a multi-release agent JAR make sense?

A `Multi-Release: true` JAR can contain implementations optimized per runtime version, but combining a Java 17 base agent with Java 24 Class-File API code requires:

- the base JAR's agent entry point remains loadable on JVM 17;
- Java 24 classes are loaded only when the runtime version matches;
- `META-INF/versions/24/...` is packaged strictly per multi-release JAR rules;
- base classes do not accidentally hold constant pool references to `java.lang.classfile`, which would cause link errors on Java 17;
- testing the full Java 17, 21, 24+ matrix as well as Java class loaders/module layers.

**This is a complex option, not a default requirement.** If you only need an agent for Java 17+, using an appropriate ASM version is usually simpler and easier to control.

## 13. Verifying the artifact, not just source code

### 13.1. Minimum verification workflow

~~~text
Source and POM
    |
    +--> scan imports; does jdk.internal.* appear?
    |
    +--> verify dependency versions, licenses, checksums/policy
    |
Build --release 17
    |
    +--> Maven Shade creates agent JAR with correct manifest
    |
    +--> jar tf checks relocated dependencies
    |
    +--> jdeps --jdk-internals on final artifact
    |
Integration Test
    |
    +--> JVM 17/21/24 in support matrix
    +--> -Xverify:all
    +--> run against real target application
    +--> telemetry, classloader, module edges, overhead
    |
Release
    |
    +--> immutable artifact + checksum/SBOM + rollback
~~~

If the build has the agent and app in separate repositories, CI should explicitly version the **agent artifact**, **target Java releases**, and **external bytecode libraries**. An agent producing valid bytecode on Java 17 is not guaranteed to recognize every classfile on Java 24 if its ASM version is too old.

### 13.2. Scanning source and binaries

Sample command from the project root on systems with `grep`:

~~~bash
grep -R -n -E 'jdk[.]internal[.]org[.]objectweb[.]asm|sun[.]misc|com[.]sun[.]tools[.]javac' src
~~~

This command finds **signals that need review**, not that every match is definitely an unsupported API in the same context. On Windows PowerShell you can use:

~~~powershell
Get-ChildItem -Path src -Recurse -File -Include *.java |
    Select-String -Pattern 'jdk\.internal\.org\.objectweb\.asm|sun\.misc|com\.sun\.tools\.javac'
~~~

After building:

~~~bash
jdeps --jdk-internals target/safe-asm-agent-1.0.0.jar
jar tf target/safe-asm-agent-1.0.0.jar
~~~

If `jdeps` reports a dependency on `jdk.internal.org.objectweb.asm`, trace the **source or transitive dependency** creating that reference, and replace/fix it directly in the build rather than hiding the error with a launcher flag.

### 13.3. Dependency reports and reproducibility

~~~bash
mvn dependency:tree
mvn -q -DskipTests package
~~~

The dependency tree report helps identify which ASM/Byte Buddy versions are being pulled in, but ultimately you must inspect the **shaded artifact** because that is the actual deployed JAR.

In CI, lock repository mirrors, verify checksums, store SBOM/license inventories, run security scanning, and store artifact checksums. If signing is used, sign the artifact **after** the shading/relocation step. Test the exact JAR file that will be released, not just the `target/classes` directory.

## 14. Common limitations and errors

| Symptom | Cause to investigate | Resolution |
|---|---|---|
| `package jdk.internal... is not visible` at compile time | Importing JDK internal ASM blocked by JPMS | Switch to official `org.objectweb.asm`; do not use flags as a long-term strategy |
| `IllegalAccessError` when running the agent | Links to internal package that the JVM does not export | Remove JDK internal dependency; flags are only for migration testing |
| `InaccessibleObjectException` during reflection | Package/module not open to caller | Check if reflection is truly needed; use public APIs or minimal module access |
| `NoClassDefFoundError: org/objectweb/asm/...` | ASM not packaged into the agent JAR | Check `mvn package`, `jar tf`, and dependency scopes |
| `NoClassDefFoundError` with shaded package | Incorrect relocation/transformer/manifest or class loader | Check packages after shading, bytecode references, and resource paths |
| `NoSuchMethodError` in ASM/Byte Buddy | Runtime loads a different library version than compile time | Relocate, pin versions, check loader resolution and final JAR |
| `Unsupported class file major version` | Bytecode library does not recognize newer classfiles | Upgrade library release appropriately and test on target runtime |
| `UnsupportedClassVersionError` | Agent/dependency classfile compiled for a newer JVM | Build with `--release` matching minimum runtime |
| `VerifyError` / `ClassFormatError` | Transformer generates invalid bytecode or frames | Test with `-Xverify:all`, method signatures, stack maps, control flow |
| `ClassCircularityError` or startup hang | Transformer triggers circular loading of class/ASM/helper | Filter classes tightly, avoid self-instrumentation and heavy work in callbacks |
| JVM reports missing `Premain-Class` | Manifest missing or miswritten by shade | Inspect `META-INF/MANIFEST.MF` of the final agent JAR |
| `Premain-Class` present but ASM does nothing | Agent misses class loading, wrong class name filter | Check `-javaagent` before app, callback, loader, and target `demo/Service` |
| `UnsupportedOperationException` on retransform | Missing capability or unsupported schema change | Check manifest/`isRetransformClassesSupported` and target structure |
| Agent runs on 24, fails on 17 | Code uses `java.lang.classfile` or targets 24 | Use public external ASM targeting 17 or a separate artifact variant |
| `jdeps` scan passes but runtime internal reflection still fails | Reflection/dynamic names not detected by static analysis | Scan strings, configs, integration tests, and runtime logs |

**Classify the error before fixing:** compile-time module export, runtime access control, missing shaded dependency, classfile major incompatibility, and invalid transformed bytecode **are different root causes**. Do not apply `--add-opens` to all of these errors.

### 14.1. Check the manifest before suspecting ASM

A JAR containing only `demo.Agent.class` without `Premain-Class` will **not be launched by the JVM as a Java agent**. This case is unrelated to ASM. Use `jar tf` and extract the manifest, then check the `demo.Agent` entry name and the `public static void premain(String, Instrumentation)` method in source.

### 14.2. Distinguish agent exceptions from app exceptions

A transformer can throw an exception or return invalid bytes; depending on the phase, the JVM may continue with other transformers or reject the class definition. A probe that inadvertently inserts `println` too early into a bootstrap/core class can cause class loading recursion. Set tight filters and treat transformer error handling as a critical part of deployment.

## 15. Extended scenarios

### 15.1. Application already has its own ASM

If the app uses an older ASM version to generate proxies while the agent uses a newer ASM version, **do not assume the two versions are compatible just because the class names match**. Package relocation in the agent reduces conflicts, but does not solve everything if the agent itself inserts references to shaded ASM into application classes.

**Proper design:** ASM is **a tool for building class bytes inside the agent**, while bytecode injected into the target should preferably call only **public Java APIs or helpers with clear loader visibility**. Never let app methods accidentally depend directly on the agent's ASM parser.

### 15.2. Multiple agents

A JVM can load multiple agents via multiple `-javaagent` flags. Each transformer has its own lifecycle and order. An agent using shaded ASM avoids breaking another agent's dependencies, yet **transformed bytes are still processed sequentially through the transformer pipeline**. Avoid inserting the same probe multiple times; ensure idempotence, markers, and clear target class boundaries.

### 15.3. Classloaders and JPMS

An agent JAR running in the JVM does not mean every target class can see the agent's classes. To avoid `IllegalAccessError`, `NoClassDefFoundError`, or module resolution failures:

- inspect the target's `ClassLoader` and `Module` in the callback;
- avoid injecting helper references if the helper is not accessible;
- open `reads`/`exports`/`opens` only when genuinely necessary;
- do not use JDK internal classes as a way to “dodge” classloader errors;
- do not arbitrarily modify the `java.base` boot module or deploy shaded ASM into `java.*` packages.

### 15.4. Testing across different JDK vendors

Public APIs reduce risk but do not replace testing. Different JVM vendors and minor updates can have differences in performance, classloading, and classfile support. Establish a clear support matrix: Java 17, 21, 24+ if those are the runtimes your organization uses. Update the agent when the bytecode processing library does not yet support a new classfile version.

## 16. Practice exercises

### Exercise A — find the dependency flaw

Agent code imports `jdk.internal.org.objectweb.asm.ClassReader` and uses `--add-exports` in CI. Explain three risks when deploying to a JVM without the flag and when upgrading the JDK.

**Answer:** runtime may throw `IllegalAccessError`; internal APIs have no compatibility contract; build/runtime become tightly coupled to internal flags and versions.

### Exercise B — changed import without fixing packaging

You switch to `org.objectweb.asm.ClassReader`, Maven compiles successfully, yet in production the agent throws `NoClassDefFoundError: org/objectweb/asm/ClassReader`. Where is the mistake?

**Answer:** the library is missing from the runtime loader. You need to package ASM (or configure a valid classpath/loader); try shading/relocation and `jar tf` on the final artifact.

### Exercise C — compare shading and relocation

Why can merely bundling `asm.jar` into an uber JAR still cause conflicts if the app also has `org.objectweb.asm.*`? What does relocating `org.objectweb.asm -> demo.agent.shaded.asm` help with? Does it automatically make the app find all of the agent's helpers?

**Answer:** class binary names still collide without relocation. Changing the namespace isolates the dependency; however, it **does not automatically solve** helper visibility/module access or resource names.

### Exercise D — verify probe impact

Run `safe-asm-agent` from sections 6–9 **with** and **without** `-javaagent`. Compare stdout. Why is only one line `agent:enter-hello` added while `result=hello` remains unchanged?

### Exercise E — try scanning JDK internals

Compile `InternalAsmDemo` with `--add-exports` and then run `jdeps --jdk-internals`. Explain why build success is not enough to conclude an API is supported. Then remove the internal import and rescan the artifact.

### Exercise F — choosing the JDK 24 Class-File API

Use `PublicClassfileDemo` to parse Java 17 major 61 `Sample.class`. If you try to compile `PublicClassfileDemo` itself with `--release 17`, predict the result and explain based on API availability.

### Exercise G — try changing control flow

Use ASM to extend the transformer to add a branch or exception handler. Why might the `COMPUTE_MAXS` configuration in the demo be insufficient? Try `COMPUTE_FRAMES` with a hierarchy resolver that sees the right target classes, then check with `-Xverify:all` including exception paths.

### Exercise H — build a support matrix

The agent must run on Java 17 and 24, with target classfiles having major 61 or 68. Define an ASM version supporting both, build with target release 17, test on JVM 17/24, and define a handling process if a new classfile major version appears. Do not decide based solely on the CI machine's Java version.

### Check questions

1. **Is importing `jdk.internal.org.objectweb.asm` a supported API?** — No.
2. **Is `org.objectweb.asm` provided by the JDK as a Java SE API?** — No; it is an external library whose dependency must be managed.
3. **Does using `--add-exports` turn a JDK internal class into a public API?** — No.
4. **Which command detects static JDK internal dependencies?** — `jdeps --jdk-internals`.
5. **What is the Java SE public API for instrumentation?** — `java.lang.instrument`.
6. **In which release was the public Class-File API finalized?** — JDK 24.
7. **Can `java.lang.classfile` be used on Java 17?** — No.
8. **Are shading and relocation the same thing?** — No; one bundles dependencies, the other renames namespaces.
9. **Why is it necessary to inspect the final JAR?** — Because shading/manifest/packaging can make the artifact differ from the compile output.
10. **Does `-Xverify:all` prove everything will work correctly in production?** — No; you still need to test classloaders, behavior, concurrency, performance, and the runtime matrix.

## 17. Release checklist and conclusion

### Before building

- [ ] No unintended imports or bytecode references to `jdk.internal.org.objectweb.asm` or JDK private packages.
- [ ] Use `java.lang.instrument` to obtain transformers/Instrumentation.
- [ ] If a parser is needed for Java 17/21, declare official ASM/Byte Buddy with a version compatible with the classfile major versions.
- [ ] If using `java.lang.classfile`, set **minimum runtime to JDK 24**.
- [ ] Pin dependencies and verify supply-chain/source/license/patch policies.
- [ ] Set `maven.compiler.release` to the **lowest JVM** that must be supported.

### When packaging

- [ ] Ensure the agent JAR has `Premain-Class` and/or `Agent-Class` depending on the entry points actually implemented.
- [ ] Package ASM/Byte Buddy runtime dependencies into the agent or configure loaders properly.
- [ ] Relocate dependency packages that risk collision, avoiding `jdk.internal.*`/`java.*` namespaces.
- [ ] Check resource transformers, service metadata, and signatures after shading.
- [ ] Do not use `minimizeJar` without verifying reflection/ServiceLoader/bootstrap usage.
- [ ] Inspect final `jar tf`, manifest, and `jdeps --jdk-internals`.

### Before releasing

- [ ] Run the agent on real JVMs in the support matrix, not just the build machine.
- [ ] Run `-Xverify:all` in tests and inspect transformed class bytes.
- [ ] Confirm probes are inserted at the right points without altering business return/exception behavior.
- [ ] Check differences between startup agent and attach agent if both are supported.
- [ ] Check classloader/module visibility and bootstrap instrumentation.
- [ ] Test applications that have a different ASM dependency version and multiple agents.
- [ ] Check rollback, logging, overhead, and JIT/GC/latency when the agent is enabled.
- [ ] Attach artifact checksums, release notes, SBOM, and clear run instructions.

**Conclusion:** a Java agent can use official JDK APIs to receive bytecode, combined with an **independently managed bytecode processing library** (OW2 ASM/Byte Buddy), and package dependencies properly. Do not use the JDK's internal ASM copy as an excuse to depend on `jdk.internal.org.objectweb.asm`. For JDK 24+, `java.lang.classfile` is the standard public choice; for Java 17/21, use an external library with clear releases and an appropriate build target.

**Three mandatory checks:** (1) build without internal `--add-exports`; (2) final artifact contains no static references to JDK internal APIs; (3) agent JAR runs with `-Xverify:all` and produces correct output on target JVMs. This is the foundation for deploying stable instrumentation, rather than relying on implementation details that can change without notice.

### Official documentation and further resources

- [Java SE 17 — java.lang.instrument](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): agent JAR, `-javaagent`, `premain`, `agentmain`, manifest capabilities.
- [Java SE 17 — Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): registering transformers, class retransform/redefine, bootstrap class loader support, and module graph.
- [Java SE 17 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): callback and rules for returning transformed bytes.
- [Oracle JDK Migration Guide — JDK internal APIs / jdeps](https://docs.oracle.com/en/java/javase/20/migrate/migrating-jdk-8-later-jdk-releases.html): strong encapsulation, migration, and detecting JDK internals.
- [JEP 261 — Module System](https://openjdk.org/jeps/261): module encapsulation and `--add-exports`/`--add-opens`.
- [JEP 484 — Class-File API](https://openjdk.org/jeps/484): standardized API in JDK 24.
- [Java SE 24 — java.lang.classfile.ClassFile](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassFile.html): parse/transform/generate and `ClassFile.of()`.
- [OW2 ASM](https://asm.ow2.io/): public library and official releases/documentation.
- [Apache Maven Shade — Relocating Classes](https://maven.apache.org/plugins/maven-shade-plugin/examples/class-relocation.html): rationale for relocation and dependency package configuration.
- [Byte Buddy](https://bytebuddy.net/): higher-level bytecode manipulation/instrumentation framework.
