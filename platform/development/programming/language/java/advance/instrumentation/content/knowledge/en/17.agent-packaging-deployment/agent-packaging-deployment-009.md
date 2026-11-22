# Inspecting Agent Provenance, JAR Contents, and Collected Data Scope

A Java agent running in the same JVM as an application can observe class loading, receive bytecode via `ClassFileTransformer`, inject logic into methods, and, depending on permissions/capabilities, request to retransform or redefine classes. This is a very useful mechanism for profiling, tracing, and security, but it also makes **deploying a JAR of unknown origin** a significant risk.

Before using `-javaagent`, do not just ask "Can this JAR run?", but answer three independent questions:

1. **Provenance**: Who created this exact artifact, from which source code/commit/build, through which distribution channel, and is there verifiable evidence?
2. **Contents and capabilities**: What classes, libraries, resources, entry points, manifest capabilities, native components, or dependencies are inside the JAR? What can it do inside the JVM?
3. **Data actually collected/processed/sent**: What classes, methods, and events does the agent observe; does it capture arguments/return values, headers, secrets, stack traces, or business data; where is the data sent, how long is it retained, and who can view it?

**These three answers must not be treated as one.** A SHA-256 matching a published release does not by itself prove the publisher is trustworthy; a valid digital signature does not by itself prove safe behavior; a `capture=false` configuration does not prove the runtime has no other collection paths either. This lesson belongs to the **Packaging and Deployment** section of Java Advance — instrumentation, focusing on the control chain before and after loading an agent.

The goal is to establish a **pre-execution inspection** process, test a Java 17+ agent that we create ourselves, distinguish strong/weak evidence, and build a "data collection contract" concrete enough for auditing.

## 1. Why Must a Java Agent Be Evaluated Like High-Privilege Code?

A Java agent using startup mode has the form:

```bash
java -javaagent:path/to/agent.jar=options -cp app-classes demo.Main
```

This is **illustrative syntax**; `path/to/agent.jar` and the application class must actually exist when used. The JVM reads the agent JAR's manifest, finds the class declared by `Premain-Class`, and then invokes `premain(...)` **before** the application `main`.

For runtimes that support dynamic loading, an agent can also be loaded into a running process via `Agent-Class`/`agentmain(...)`. Therefore, the scope of control does not end at command-line startup: dynamic agent loading permissions, attach tools, and JVM policies must also be examined.

An agent can:

- Register a `ClassFileTransformer` to receive `className`, loader/module, `ProtectionDomain`, `classfileBuffer`, and related information at transform time.
- Generate new bytecode to inject metrics/tracing into selected methods.
- When supported and granted the appropriate capability, call `retransformClasses` or `redefineClasses` to change the logic of already-loaded classes within JVM limits.
- Modify module readability/openness using `Instrumentation.redefineModule` according to the API contract.
- Append helper JARs to the bootstrap or system loader search path.
- Call standard Java APIs: files, network, threads, processes, environment, logging, reflection, and libraries that the agent can load.

Importantly: **having access to data does not mean data has been collected**, but an auditor must not rely solely on the agent's marketing claims to conclude "it cannot read that data."

For example, this callback can receive bytecode even without modifying it:

```java
@Override
public byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain domain,
        byte[] classfileBuffer) {

    if (!"demo/Work".equals(className)) {
        return null;
    }

    // Data processing decisions must be audited here.
    return null;
}
```

This is a **method snippet** in a class implementing `ClassFileTransformer`, not a runnable agent. Returning `null` only means **not modifying the bytes in this callback**; it does not by itself indicate that the agent does not log, retain the bytes, or transmit data in other branches.

Because an agent runs in the same JVM/process context as the application, a configuration restricting collection is a **conditional safeguard**, not an independent security sandbox.

## 2. Three Layers of Evidence: Integrity, Authenticity, and Provenance

| Evidence | What it confirms | What it does not prove on its own |
|---|---|---|
| **SHA-256 digest** compared against a trusted reference value | Current artifact bytes match a published/verified digest | Whether the digest publisher is trustworthy; whether the agent is safe |
| Verified **JAR signature** | Signed JAR entries have not been altered contrary to the signature; signer/certificate info is present | Whether the signer is approved by the organization; whether all entries are signed; that the code is harmless |
| **Trusted publisher/channel** | Artifact comes from an approved distribution channel/publisher | Whether the source code of the specific version matches the bytes |
| **Build provenance/attestation** | Evidence of where, how, and which commit/build pipeline produced the artifact, if verified | That the provenance statement is true merely because it exists; that any builder/signer is trustworthy |
| **SBOM/dependency inventory** | Lists declared/discovered internal components and dependencies | That there are no hidden dependencies or runtime vulnerabilities |
| **Static review** | Identifies visible code paths, APIs, resources, and configurations | That there are no obfuscated branches, reflection, dynamic loading, or environment-dependent behavior |
| **Runtime egress/data audit** | Data flows detected during testing | That all behavior is identical across all inputs/configs/production hosts |

A serious process requires **multiple mutually reinforcing pieces of evidence**, not just a single `sha256` value.

### 2.1. Checking SHA-256 with Trust Conditions

Example on PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 .\dist\scope-agent.jar
```

On Linux/macOS there is `sha256sum`:

```bash
sha256sum dist/scope-agent.jar
```

The command computes the digest of **the specific JAR on disk**. It must be compared with the SHA-256 value of the **exact version** provided through an authenticated channel: a signed release manifest, an approved internal artifact inventory, or a verified provenance/attestation.

It is **invalid** to take the SHA-256 of an unknown JAR, save it, and claim "provenance verified" without a trusted reference digest. That only proves the consistency of the copy with **itself**.

When downloading, copying, signing, or repackaging a JAR, bytes can change. The hash must be tied to the **final artifact that will actually be executed**, not a source file, intermediate JAR, or another cached copy.

### 2.2. JAR Signatures Do Not Replace Trust Policy

For a signed artifact, you can inspect:

```bash
jarsigner -verify -strict -verbose -certs release-agent.jar
```

This is an inspection command for **a real JAR named `release-agent.jar`**, not part of the demo example. Read all warnings and the exit code, checking **signer identity, trust chain, certificate validity, algorithms, and unsigned entries**. Depending on policy, an approved truststore/alias must be used rather than relying solely on certificates embedded in the JAR.

`-strict` makes severe warnings affect the exit code. Some cases: self-signed certificates, unverified chains, unsuitable algorithms, or JARs with **unsigned entries**. The line `jar verified` alone is not enough to assert that "the entire artifact complies with policy."

**Signing a JAR does not make every JVM automatically reject an unsigned `-javaagent`.** The Java Instrumentation specification places the responsibility for evaluating agent trust and JAR contents on the deployer/administrator; enforcing a signature/digest allowlist must be part of the deployment process or protective tooling that the organization actually controls.

### 2.3. Provenance Must Be Verified, Not Merely Attached

A provenance record is useful when it identifies:

```text
source repository/commit
        |
        v
CI workflow + trusted builder
        |
        v
build inputs / dependencies
        |
        v
signed build attestation + output digest
        |
        v
exact JAR deployed to the runtime environment
```

Under the SLSA model, build provenance describes **where, when, and how** an artifact was created. The recipient must still verify the attestation signature, builder identity, source revision, expected build workflow, and that the subject digest matches the received JAR.

A self-written JSON file named `provenance.json` sitting next to the agent **is not enough**. There must be a chain of trust across **source → build → artifact → deployment**.

## 3. Inspecting JAR Contents **Before Running Any Agent Code**

For an untrusted JAR: **do not start with** `java -javaagent:unknown.jar ...` to "see what it prints." `premain` is already executed **before** application `main`, so by that point it may already be too late to block side effects.

A reasonable order:

1. Place the JAR in an appropriate analysis environment, without granting unnecessary credentials or network access.
2. Verify the distribution path, version, digest, and signature/provenance evidence.
3. List entries, read the manifest, and detect classes/dynamic sources/nested artifacts.
4. Review bytecode, dependencies, entry points, config defaults, and collection flows.
5. Approve/finalize the data policy and deployment permissions.
6. **Only after passing the appropriate gates**, run it in an isolated test environment.
7. Compare actual output/egress/file writes against the approved contract, then decide on rollout.

Commands to inspect a JAR:

```bash
jar --list --file release-agent.jar
```

If you need to view the bytecode structure of a class present in the artifact:

```bash
javap -classpath release-agent.jar -c -p com.example.Agent
```

Both are **illustrative commands**, requiring a real JAR/class. `jar --list` lists entry names; `javap -c -p` provides disassembly and member declarations **without launching `premain`**. However, disassembly does not prove the entire behavioral flow, especially when the agent uses reflection, native libraries, or loads components over the network.

Be careful when handling untrusted files: JARs are ZIP-based and can cause high resource consumption or contain dangerous paths. Do not extract arbitrarily into sensitive directories; if deep analysis is needed, use an isolated environment with size/resource limits.

### 3.1. Manifest Keys That Must Be Read

| Manifest key | Meaning | Verification question |
|---|---|---|
| `Premain-Class` | Startup agent entry point | Does the class exist, and is the `premain` signature appropriate? |
| `Agent-Class` | Dynamic attach agent entry point | Is there a post-startup agent loading path that needs to be controlled? |
| `Launcher-Agent-Class` | Agent packaged with an executable JAR | Is there a secondary entry point when running `java -jar`? |
| `Can-Retransform-Classes` | Requests retransform capability | Does the agent need this capability? |
| `Can-Redefine-Classes` | Requests redefine capability | Is there an approved reason for replacing already-loaded methods? |
| `Can-Set-Native-Method-Prefix` | Requests native prefix capability | Is it genuinely needed? |
| `Boot-Class-Path` | Bootstrap helper path | Which additional JARs/paths are loaded? |
| `Class-Path` | Class-path dependencies | Are there hidden dependencies or ones outside the main artifact? |
| `Multi-Release` | JAR has versioned classes | Are there different implementations across JDK versions? |
| `Automatic-Module-Name` | Automatic module name when using the module path | Are there related module visibility/conditions? |

**A capability header set to `true` indicates a capability request, not proof that the code always uses it.** Conversely, a `false` header is not a guarantee that the agent does not call standard network/file APIs. Both content and behavior must be examined.

### 3.2. Do Not Look Only at Root `.class` Files

A JAR may contain:

- `META-INF/services/...`: ServiceLoader provider declarations.
- `META-INF/versions/N/...`: alternative implementations in a **multi-release JAR**.
- Nested JARs, configuration files, scripts, or resources.
- Native binaries such as `.so`, `.dll`, `.dylib`, JNI libraries.
- Manifest `Class-Path` pointing to JARs outside the main artifact.
- Helper JARs in `Boot-Class-Path` or appended by the agent via `Instrumentation`.
- Obfuscated classes, dynamic proxies, runtime-generated bytecode.

For a **multi-release JAR**, inspect both base entries and versioned entries matching the actual JDK. The JAR File Specification notes that the bootstrap loader does not apply multi-release behavior to JARs appended to the bootstrap search path like an ordinary library; do not infer bootstrap behavior from application loader behavior.

For a **signed JAR**, note that signatures generally apply per entry; if unsigned content is added after signing, older entries may still have valid signatures. Therefore, **coverage** and warnings must be checked, not merely whether "the JAR has `.RSA`/`.SF` in `META-INF`."

## 4. Inspecting Notable APIs and Behavioral Flows

When code-reviewing an agent (or comparing source against released bytecode), pay attention to the following categories:

| Category | APIs/signals that may appear | What must be concluded |
|---|---|---|
| Instrumentation | `addTransformer`, `retransformClasses`, `redefineClasses`, `redefineModule` | Exactly which classes are touched? |
| Class information | `getAllLoadedClasses`, `getInitiatedClasses`, `classfileBuffer` | Are class names/bytecode stored or transmitted? |
| Reflection/MethodHandle | `setAccessible`, `MethodHandles`, deep reflection | Does it exceed the approved observation scope? |
| Network | HTTP clients, sockets, gRPC, exporters | What are the host/port/protocol, TLS, credentials, and payload? |
| File/system | `Files`, logging, environment, system properties | Does it read/write sensitive directories or variables containing secrets? |
| Threads/scheduling | Background workers, executors, timers | Are there threads running outside hook execution? |
| Dynamic loading | `URLClassLoader`, `ServiceLoader`, plugin loaders | Is additional code loaded after JAR approval? |
| Native/exec | `System.loadLibrary`, JNI, `ProcessBuilder` | Does it require native/OS privileges? |
| Helper injection | `Boot-Class-Path`, bootstrap/system append | Does it add code into a broader-trust loader? |

A `grep` or `javap` search for these method names **is only a first step**. An agent can perform equivalent behavior through abstractions or indirect dependencies; not seeing a literal string **does not prove the absence of the behavior**.

If the packaged code is obfuscated, lacks source, or dependencies cannot be inspected, this is an **evidence gap** that must be explicitly stated and handled per risk policy, rather than marking it PASS.

## 5. Defining Data Scope: "Seen" Differs from "Collected"

In Java instrumentation there are at least four layers:

```text
JVM/API provides information to the callback
                |
                v
Agent reads or computes from that information
                |
                v
Agent stores in memory/buffer/log/file
                |
                v
Agent exports to network/exporter/collector
```

**Each layer** must be evaluated. For example, `classfileBuffer` is passed by the JVM into the callback, but if the agent only compares `className` and returns `null`, it does not necessarily store the bytes. However, the same JAR might have another callback, debug mode, or background task that sends data.

A generic claim like "the agent only collects metrics" is insufficient; **each field**, enabling condition, data type, sink, and retention must be specified.

### 5.1. Data Matrix to Record in the Review

| Data category | Examples | Recommended default when unnecessary |
|---|---|---|
| Method/class metadata | Binary name, descriptor, module, loader | Allowlist only what needs measurement; code names can also reveal internal structure |
| Timing/counts | Duration, invocation count, errors by type | Can be kept at aggregate level with stable labels |
| Argument values | Email, account ID, request payload, token | **Do not collect** without a specific legitimate requirement |
| Return values | Business objects or response body | **Do not collect** by default |
| Exception details | Class name, message, cause, stack trace | Distinguish error type name from message/stack that may contain sensitive data |
| HTTP metadata | Route template, status, headers, cookies | Do not log Authorization/Cookie or uncontrolled raw URL queries |
| SQL/database | Query template, bind variables, connection string | Do not log bind values, credentials, or full connection strings |
| Secrets/process state | Environment, system properties, JVM args | Strip tokens/passwords/secrets and unnecessary data |
| Bytecode/raw class | `classfileBuffer`, constant pool, source names | Do not export/log raw bytes if the goal is only timing |
| Heap/thread data | Heap dump, thread dumps, local values | Requires separate authorization, purpose, retention, and controls |
| Trace context | Trace ID, span ID, baggage | Do not assume all baggage is harmless; control fields |
| User behavior | Endpoint/call patterns, tenant labels | Assess sensitivity and intended use of aggregated data |

At minimum, answer:

- **Owner/purpose:** What problem is this data collected to address?
- **Trigger:** Only classes/methods in the allowlist or every class in the VM?
- **Data fields:** Specific field names, types, labels, granularity, and sampling.
- **Redaction:** **Where** does drop/redact/mask/hash happen? Before logging/spooling/exporting or after?
- **Destination:** Endpoint, TLS, receiving organization, storage region, any third parties?
- **Retention:** Memory queue, local file, server storage, backup; deleted after how long?
- **Access:** Who can view, export, modify configuration, or enable debug?
- **Evidence:** Source review, runtime config, packet/egress audit, and post-filter telemetry samples.

**Do not confuse masking with not collecting.** If a raw secret has already been written to a local file or sent to a collector before redaction, the risk has already occurred even if the final dashboard does not display the secret.

### 5.2. Collect as Little as Possible and Control Fields at the Source

For a performance-measuring agent, sufficient data might be:

```text
methodId = "demo.Service.process()I"
outcome = "NORMAL"
durationNanos = 240000
```

The duration value above is **illustrative only**, not a measurement from the running example in Section 8. There are no `args`, `returnValue`, raw `Throwable.getMessage()`, HTTP body, or access token.

When errors are needed, consider capturing only the **exception type** first; message/stack trace are separate fields that may contain file names, user input, SQL, URLs, or personal information. Audit metric labels as well (avoid high-cardinality and personal data).

The OWASP Logging Cheat Sheet and OpenTelemetry guidance on sensitive data both emphasize the principle of **data minimization**. If using a Collector, filter/attribute/redaction processors can be added, but they are an **additional defense layer**, not a justification for the agent collecting unauthorized data at the source.

## 6. A Verifiable Data Collection Scope Commitment

A clear policy might specify:

| Attribute | Test value |
|---|---|
| Purpose | Observe only class `demo.Work` loaded by the JVM |
| Agent entry point | `agent.SafeAgent.premain` |
| Allowlist | **Exactly** `demo/Work` |
| Default mode | Do not register transformer if option differs from `allow-demo-work` |
| Data printed | A fixed string `demo.Work` when callback matches |
| Data **not** logged | `classfileBuffer`, arguments/return, exceptions, headers, secrets, stack traces |
| Bytecode modification | None; transformer returns `null` |
| Network/file output from demo agent code | None in the written logic |
| Retransform capability | `false` in manifest |
| Destination | `System.out` of the demo JVM |
| Retention | Determined by whatever captures stdout in the test environment, **no automatic TTL from the agent** |

This is **the policy for an example whose source we control**, not a guarantee for an external JAR of unknown origin. `System.out` operations can still be captured and stored elsewhere by the logging platform — so downstream must also be analyzed.

A single `captureArgs=false` variable is not enough: error/debug log paths, sampling fallbacks, remote config, exporters, service providers, and fields automatically injected by frameworks must also be examined.

## 7. Complete Java 17+ Example: Inspect the JAR First, Then Run an Allowlisted Agent

The lab has four source files:

1. `agent.SafeAgent`: startup agent that observes only the **class name** `demo/Work`, without modifying bytecode.
2. `demo.Work`: a class to trigger a class-load callback.
3. `demo.DemoApp`: launcher that loads `Work` using `Class.forName`.
4. `audit.JarInspector`: a tool that **reads the manifest + JAR entry names**, computes SHA-256, and detects several signs requiring review; **does not load/execute agent classes**.

Important: **The JAR in this example is compiled by you from the source you are viewing**. The workflow for an external JAR must stop at the review step if it does not meet provenance/approval requirements. Do not apply `-javaagent` to an untrusted file just to test the output.

### 7.1. Directory Structure

```text
agent-audit-demo/
├── src/
│   ├── agent/
│   │   └── SafeAgent.java
│   ├── demo/
│   │   ├── Work.java
│   │   └── DemoApp.java
│   └── audit/
│       └── JarInspector.java
├── agent.mf
├── out/                    (generated when compiling)
│   ├── agent/
│   ├── app/
│   └── audit/
└── dist/
    └── scope-agent.jar     (generated when packaging the JAR)
```

### 7.2. `src/agent/SafeAgent.java`

```java
package agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class SafeAgent {
    public static void premain(String options, Instrumentation inst) {
        if (!"allow-demo-work".equals(options)) {
            System.out.println("[agent] collection=off");
            return;
        }

        inst.addTransformer(new NameOnlyTransformer(), false);
        System.out.println("[agent] allowlist=demo/Work");
    }

    private static final class NameOnlyTransformer
            implements ClassFileTransformer {
        @Override
        public byte[] transform(Module module, ClassLoader loader,
                String className, Class<?> classBeingRedefined,
                ProtectionDomain protectionDomain, byte[] classfileBuffer) {

            if ("demo/Work".equals(className)) {
                System.out.println("[agent] observed=demo.Work");
            }
            return null;
        }
    }
}
```

How to read it accurately:

- `premain` is the **entry point** when the JVM starts with `-javaagent`.
- Only when the option matches the exact string `allow-demo-work` does the agent register the transformer.
- `ClassFileTransformer.transform` will be called by the JVM for classes transformed via the corresponding mechanism after the transformer is registered. **The callback can still receive `classfileBuffer` of other classes**, even though the implementation only logs when `className` matches.
- **Exact** string comparison `"demo/Work"` (internal form uses `/`); other classes are not logged.
- The output is an **allowlisted class name**, not an argument or value of `Work.calculate`.
- `return null` leaves class bytes unchanged, **does not modify the body**, and no helper class is injected.
- On Java 17, the `transform(Module, ...)` overload can be overridden as shown.
- `Can-Retransform-Classes: false` means the agent **does not request the retransform callback capability**, not that it "no longer has any right to read JVM data."

Note that this is a demo **observing class loading only**, not method tracing. To actually measure method arguments/returns, new bytecode must be injected, which requires opening an additional review of the data being read.

### 7.3. `src/demo/Work.java`

```java
package demo;

public final class Work {
    public static int calculate(int number) {
        return number * 2;
    }
}
```

This class only serves as a target so the JVM performs a load of `demo.Work`. `calculate` is not called in the example, so **no method arguments or return values arise from this call**.

### 7.4. `src/demo/DemoApp.java`

```java
package demo;

public final class DemoApp {
    public static void main(String[] args) throws Exception {
        System.out.println("[app] start");
        Class<?> type = Class.forName("demo.Work");
        System.out.println("[app] loaded=" + type.getSimpleName());
        System.out.println("[app] done");
    }
}
```

The app explicitly calls `Class.forName("demo.Work")` **after** the `start` line to create an easily observable scenario. The app code has no `Work.class` or `new Work()` beforehand, avoiding linking to `Work` too early in the example.

### 7.5. `src/audit/JarInspector.java`: Inspecting Manifest, Entries, and Digest

```java
package audit;

import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.Enumeration;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.Set;
import java.util.jar.Attributes;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;
import java.util.jar.Manifest;

public final class JarInspector {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Usage: audit.JarInspector file.jar");
        }
        Path path = Path.of(args[0]);
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (var in = Files.newInputStream(path)) {
            byte[] buffer = new byte[8192];
            for (int n; (n = in.read(buffer)) != -1;) {
                digest.update(buffer, 0, n);
            }
        }
        String hex = HexFormat.of().formatHex(digest.digest());

        try (JarFile jar = new JarFile(path.toFile())) {
            Manifest manifest = jar.getManifest();
            if (manifest == null) {
                throw new IllegalArgumentException("Missing manifest");
            }
            Attributes attributes = manifest.getMainAttributes();
            String premain = attributes.getValue("Premain-Class");
            int files = 0, classes = 0, services = 0;
            int nestedJars = 0, nativeFiles = 0, versioned = 0, unsafe = 0;
            Set<String> names = new HashSet<>();

            Enumeration<JarEntry> entries = jar.entries();
            while (entries.hasMoreElements()) {
                JarEntry entry = entries.nextElement();
                if (entry.isDirectory()) continue;
                String name = entry.getName();
                files++;
                if (!names.add(name) || name.startsWith("/")
                        || name.contains("\\")
                        || Arrays.asList(name.split("/")).contains("..")) {
                    unsafe++;
                }
                if (name.endsWith(".class")) classes++;
                if (name.startsWith("META-INF/services/")) services++;
                if (name.endsWith(".jar")) nestedJars++;
                if (name.endsWith(".so") || name.endsWith(".dll")
                        || name.endsWith(".dylib")) nativeFiles++;
                if (name.startsWith("META-INF/versions/")) versioned++;
            }

            System.out.println("[inspect] premain=" + premain);
            System.out.println("[inspect] premainClassPresent=" +
                    (premain != null && jar.getJarEntry(
                            premain.replace('.', '/') + ".class") != null));
            System.out.println("[inspect] canRetransform=" +
                    attributes.getValue("Can-Retransform-Classes"));
            System.out.println("[inspect] bootClassPath=" +
                    attributes.getValue("Boot-Class-Path"));
            System.out.println("[inspect] files=" + files + " classes=" + classes);
            System.out.println("[inspect] services=" + services
                    + " nestedJars=" + nestedJars
                    + " nativeFiles=" + nativeFiles);
            System.out.println("[inspect] versioned=" + versioned
                    + " unsafeEntryNames=" + unsafe);
            System.out.println("[inspect] sha256Length=" + hex.length());
        }
    }
}
```

Explanation of usage and **limitations** of the inspector:

- `MessageDigest("SHA-256")` computes the actual digest of the file. The example only prints the **hex string length** so stdout does not depend on timestamps/bytes of each JAR build; when checking the actual digest, print/save `hex` or use `Get-FileHash`/`sha256sum`, then **compare against a trusted value**.
- `JarFile` opens the archive to inspect `Manifest` and `JarEntry`; it **does not initialize `SafeAgent`**, and does not call `premain`.
- `premainClassPresent` only checks whether the class file name exists; it **does not verify** the method signature or bytecode safety.
- The `services`, `nestedJars`, `nativeFiles`, and `versioned` counters flag several entry groups requiring review.
- `unsafeEntryNames` is a **basic** check, not a complete path traversal scanner for all platforms or a ZIP security scanner.
- It does not verify signing certificates, compare the digest against a trusted release, scan all dependencies, or prove the absence of network I/O.
- Inventorying entry names **is not equivalent** to inspecting behavior. Sensitive or hidden things can appear in classfile code, configs, strings, or dynamically loaded components.

Therefore, **do not** use an `unsafeEntryNames=0` output to conclude that the JAR is safe. It only says there were no signs in the example's small check set.

### 7.6. `agent.mf`: Manifest Intentionally Not Requesting Retransform Permission

```text
Manifest-Version: 1.0
Premain-Class: agent.SafeAgent
Can-Retransform-Classes: false

```

Keep the blank line terminating the main section. The manifest only requests the startup entry point; `Agent-Class` is not needed because the demo does not use dynamic attach, and no bootstrap helper JAR is needed.

If a real agent needs `Can-Redefine-Classes`, `Can-Retransform-Classes`, `Can-Set-Native-Method-Prefix`, or `Boot-Class-Path` capabilities, each such change must be **recorded in the approval record** along with the reason, rather than defaulting all values to `true`.

### 7.7. Compiling for Java 17 and Packaging

From the `agent-audit-demo` directory containing the source files and `agent.mf`, create the output directories:

```bash
mkdir out
mkdir out/agent
mkdir out/app
mkdir out/audit
mkdir dist
```

Directories only need to be created once. Using JDK 17+:

```bash
javac --release 17 -encoding UTF-8 -d out/agent src/agent/SafeAgent.java

javac --release 17 -encoding UTF-8 -d out/app src/demo/Work.java src/demo/DemoApp.java

javac --release 17 -encoding UTF-8 -d out/audit src/audit/JarInspector.java

jar --create --file dist/scope-agent.jar --manifest agent.mf -C out/agent .
```

`JarInspector` uses `HexFormat`, an API available in Java 17, so requiring `javac --release 17` is accurate. Do not put `DemoApp` into the agent JAR; the app and audit tool are kept separate to clearly show each artifact's role.

Result when packaging succeeds:

```text
dist/scope-agent.jar
out/agent/agent/SafeAgent.class
out/agent/agent/SafeAgent$NameOnlyTransformer.class
out/app/demo/Work.class
out/app/demo/DemoApp.class
out/audit/audit/JarInspector.class
```

The list above only enumerates notable files; there are also the manifest/resources and other output directories.

### 7.8. Run the **Inspector First**, Before Running the Agent

```bash
jar --list --file dist/scope-agent.jar

java -cp out/audit audit.JarInspector dist/scope-agent.jar
```

Stdout of **JarInspector** verified on OpenJDK 24.0.2, with source compiled using `--release 17`:

```text
[inspect] premain=agent.SafeAgent
[inspect] premainClassPresent=true
[inspect] canRetransform=false
[inspect] bootClassPath=null
[inspect] files=3 classes=2
[inspect] services=0 nestedJars=0 nativeFiles=0
[inspect] versioned=0 unsafeEntryNames=0
[inspect] sha256Length=64
```

`files=3`: the manifest and the agent's two class files (main class + nested transformer). `classes=2`: two class files. `bootClassPath=null`: the header is absent from the manifest, not a corrupted JAR. `sha256Length=64` only confirms the hex representation of the SHA-256 digest, **not the publisher**.

Read `jar --list` to see the **exact** entries, not just the counts. For a large JAR, you must also inspect `META-INF/services`, module descriptors, nested libs, native assets, `META-INF/versions`, configs, resources, and paths outside the manifest.

### 7.9. Checking the Signature of the **Unsigned Demo JAR**

```bash
jarsigner -verify -strict -verbose -certs dist/scope-agent.jar
```

Because the newly created JAR **is unsigned**, `jarsigner` in the test reported:

```text
jar is unsigned.
```

On OpenJDK 24.0.2, the command with `-strict` exited with code `16` for this example. Other environments/JDKs may present different diagnostics; do not use the number `16` as a universal "invalid signature" constant for all conditions.

**Do not misunderstand:** the demo is allowed to run in the lesson because we **have the source and compiled it ourselves in a test environment**, not because the signature check PASSED. For production artifacts, the organization must decide in advance which forms of verification are accepted, such as a trusted signer or an exact digest from an authenticated release channel. If policy requires a signature, the unsigned demo JAR must be rejected at a real deployment gate.

### 7.10. Only After Artifact Control: Running the Agent in Enabled Mode

```bash
java -javaagent:dist/scope-agent.jar=allow-demo-work -cp out/app demo.DemoApp
```

Actual verified stdout:

```text
[agent] allowlist=demo/Work
[app] start
[agent] observed=demo.Work
[app] loaded=Work
[app] done
```

Meaning:

- `premain` registers the allowlisted transformer before the application.
- The app prints `start`, then explicitly requests loading `demo.Work`.
- The transformer sees the matching class name and prints a predefined line.
- The app confirms the class is loaded, then finishes.
- **No arguments, return values, exception messages, HTTP bodies, or raw classfile bytes are logged** in the demo logic.

The last point is only an **observation of the reviewed demo code's output**. It does not allow inferring that another agent that only prints class names will not do anything else in the background.

### 7.11. Running the Agent in Disabled Mode

```bash
java -javaagent:dist/scope-agent.jar=off -cp out/app demo.DemoApp
```

Stdout:

```text
[agent] collection=off
[app] start
[app] loaded=Work
[app] done
```

`premain` ran but did not register the transformer, so there is no `[agent] observed=...` line. Lesson: **"collection=off" does not mean "no agent code executed."** When using `-javaagent`, the JVM still loads the agent class and calls `premain`; code can do other things besides the collector. This is why reviewing entry points remains important.

### 7.12. Running in a Controlled Isolated Environment

The two runs in Sections 7.10–7.11 **apply only to the source/JAR you created yourself** in the example. For external artifacts, before running, you must complete provenance inspection, exact-byte verification, code/dependency review, collection policy review, and approval.

When testing an external agent of unknown trustworthiness, consider a sandbox/process/container with restricted network egress, no production credentials, minimal filesystem, and non-sensitive synthetic data. A container alone **is not** absolute proof that an agent cannot cross a boundary; real permissions/isolations must be configured.

## 8. Why Is Inspecting the JAR Not Enough to Know What Data Is Exported?

An agent might be configured with:

```text
captureArguments=false
captureReturnValue=false
captureExceptionMessage=false
```

yet still collect data from:

- `System.getenv`, `System.getProperties`, JVM arguments, or configuration files.
- HTTP headers, SQL bind variables, thread context, span baggage.
- Exception messages and stack traces automatically attached by the SDK.
- An exporter enabling debug logging or local spooling on its own.
- Custom callbacks enabled after startup by remote config.
- Service providers or libraries located in `Class-Path`/nested JARs.
- A secondary endpoint for diagnostics, crash reports, or self-updates.

Therefore, inspection must proceed from **source → config → runtime behavior → destination**.

For example, an agent that only sends:

```text
duration_ms=12
route=/orders/{id}
status=200
```

still needs evaluation of whether `route` is truly a **template** (`/orders/{id}`) or is sometimes replaced by the actual URL containing an order ID, email, or access token. A metric label can become sensitive data if configuration is uncontrolled.

### 8.1. Testing Egress and File Writes

In an authorized test environment, you can:

1. Run the application with and without the agent under the **same workload/synthetic inputs**.
2. Record outbound connections/destinations and connection creation times.
3. Observe DNS, TLS destination metadata, proxy/exporter config, and disk spool/log locations.
4. Capture **synthetic payloads containing no real data** at a controlled test collector.
5. Search for prohibited fields across the **entire chain**: stdout, log files, temp directories, retry queues, collector attributes, storage/backend.
6. Toggle documented feature flags/debug modes, rather than testing only the default configuration.
7. Compare runtime egress against the endpoint allowlist and collection purpose.
8. Test behavior on exporter errors, timeouts, offline states, and retries: is data written to disk?
9. Check retention, RBAC, and deletion mechanisms at the collector/backend.
10. Pin test results to the running **artifact digest and config version**.

**Limitation of the test:** a network/payload audit on a single workload only reflects the code paths that were triggered. It must accompany static review, dependency inventory, provenance, and policy enforcement, not replace them.

## 9. Checking Entry Points, Loaders, and Post-Startup Dependencies

For a `-javaagent` agent, locate `Premain-Class` in the main manifest and the corresponding `public static void premain(String, Instrumentation)` or `public static void premain(String)` method. When an agent attaches dynamically, `Agent-Class` requires `agentmain`.

Do not assume all code begins and ends inside that method:

- `premain` can spawn background threads.
- The agent can register transformer callbacks for classes loaded later.
- `Class-Path` and `Boot-Class-Path` can pull in helpers/dependencies outside the agent JAR.
- The agent can use `Instrumentation.appendToBootstrapClassLoaderSearch`.
- Adding `ServiceLoader` providers can cause auxiliary code to be initialized lazily.
- Some code may reside in resources/nested JARs or be loaded dynamically.
- Constructors/static initializers of the agent/helper can have side effects before the collector is enabled.
- When attached, `agentmain` can take a different branch than startup `premain`.

**Claiming "I read `Premain-Class`" is not equal to "I reviewed all code that can run."** Initialization, dependencies, and lifecycle (start, reconfigure, stop, attach, detach/rollback if supported) must all be reviewed.

### 9.1. Checking the Right ClassLoader and Module

Agent classes are typically defined by the system loader; helpers may be placed on the bootstrap loader. This change does not automatically make all modules read/open. When an agent injects calls to a helper, check:

- Has the helper JAR been approved with its digest?
- Are there class/package names colliding with app/JDK classes?
- Does a bootstrap helper depend on a class defined only by the system/custom loader?
- Is `Instrumentation.redefineModule` or module read edges needed?
- Are the method/helper names within the bytecode modification allowlist?

Supply chain risk can lie in **auxiliary JARs**, not just the file after `-javaagent:`. Provenance reporting should cover the appropriate **transitive dependency closure**.

## 10. How to Manage Collection Configuration Auditably

A secure control plane should distinguish:

- **Artifact policy**: which agent version/digest/signer is permitted to run?
- **Instrumentation policy**: which classes/methods are permitted to be transformed or retransformed?
- **Capture policy**: which signals and fields may be collected?
- **Transport policy**: which data is permitted to be sent to which endpoint?
- **Retention/access policy**: who can view it and how long does the data persist?

When adjusting dynamically, record the **config version** with events to distinguish data produced by old and new configurations. An invocation that started before a filter change may finish afterward; if choosing per-invocation semantics, lock in filter/sampling/sink consistently rather than reading multiple versions on entry/exit.

Do not grant remote config permission to silently switch from `metadata-only` to `capture-args` without corresponding approval. For high-risk configurations, there should be a server-side policy gate that prevents enabling prohibited fields via a convenient control API.

### 10.1. Disabling Collection Does Not Mean Removing All Code

The lesson's example has an `off` mode: `premain` still runs but does not register the transformer. For production agents that have already injected hooks into classes, turning off `enabled` usually only makes the **hook skip recording events**; `removeTransformer` does not automatically restore already-instrumented bytecode on loaded classes either.

If regulations require no further data to be exported after disabling, **in-flight invocations**, queues, disk spools, and active exporters must be handled. A single `enabled=false` variable does not automatically clear buffers that already contain prior data.

### 10.2. Fail Closed for Sensitive Data

If configuration is invalid, the allowlist cannot be found, the exporter lacks authentication, or required consent/approval is missing:

- Do not fall back to `captureAll=true`.
- Do not enable debug to log raw payloads for "easier troubleshooting."
- Do not redirect data to an unapproved backup endpoint.
- Do not expose secrets in the agent's own exceptions/logs.
- Log a minimal configuration error without credentials.
- Decide between fail-closed startup or disabled telemetry according to deployment policy.

Refusing to collect when no valid policy is present is usually safer than falling back to the broadest collection mode.

## 11. Checking Dependency Vulnerabilities and Licensing

Do not scan only the class listed in `Premain-Class`. Agents commonly bundle:

- ASM/Byte Buddy and bytecode tooling.
- HTTP/gRPC exporters.
- JSON/serialization libraries.
- Logging frameworks.
- Compression/native libraries.
- SDKs for config, plugins, or autodiscovery.

A **dependency inventory or SBOM** tied to the artifact build is needed, checking versions, licenses, and vulnerabilities against policy, while cross-checking against the actual JAR. If shading/fat JARs are used, relocated package names can make identifying dependencies by `.class` path alone more difficult.

A clean dependency scan **does not prove** the agent does not read/leak data. It only answers one class of questions about components/versions and known issues.

When a CVE exists, distinguish "library has an affected version" from "code path is exploitable in this configuration." Do not assume harmlessness merely because the agent runs inside the JVM. Assess reachability and exposure, and have an update/rollback plan.

## 12. Interpreting Test Results Accurately

| Observation | What can be concluded | What must not be concluded |
|---|---|---|
| SHA-256 matches digest from an authenticated source | The file under review matches the reference bytes | That the code is safe or does not collect secrets |
| `jarsigner -verify` reports no errors | Signatures of relevant entries are valid under the tool/policy used | That the entire artifact has been authorized by the organization |
| `Premain-Class` exists | A declared entry point exists | That the method signature and code safety have been verified |
| `files=3 classes=2` in the example | Demo contents match the expected structure | That other large JARs also have only three files |
| `unsafeEntryNames=0` | No signs in the inspector's very small heuristic | That there are no ZIP/path/security problems |
| Agent prints `collection=off` | Demo code did not register the transformer in that branch | That the agent executed no instructions |
| No network seen in a single test | No egress observed under that workload | That the agent has no other exfiltration paths |
| No sensitive fields seen at the collector | The test pipeline did not detect that field where viewed | That the raw field was never written to logs/queues before redaction |
| Agent returns `null` from transformer | The callback did not alter bytes | That the callback did not read/store data |
| Runtime error-free | The program ran under test conditions | That the agent is approved for use on production data |

This table helps avoid getting "one PASS signal" and collapsing all three questions — **provenance — contents — data** — into an unproven conclusion.

## 13. Pre-Production Approval Workflow

A deployment gate can apply the following order:

### Gate A — Artifact and Provenance

1. Identify the approved publisher and release channel.
2. Pin the version, release tag, source commit, and build identifier.
3. Collect provenance/attestation/SBOM when required.
4. Verify the attestation signer/build identity and artifact subject digest.
5. Compute the SHA-256 of the JAR **that will run**, and compare against the trusted digest.
6. If policy requires a JAR signature, check `jarsigner -verify -strict -verbose -certs`, trust chain, and unsigned entries.
7. Record verification results in an approved record; do not accept uncontrolled mutable `"latest.jar"` paths.

### Gate B — Contents and Capabilities

1. List JAR entries; check manifest entry points/capabilities.
2. Analyze classes/dependencies/nested JARs/services/native components/multi-release.
3. Review code paths in `premain`, `agentmain`, static initializers, and background tasks.
4. Inspect `Class-Path`, `Boot-Class-Path`, and helper JARs separately.
5. Evaluate transformer filters, class loaders/modules, and retransform/redefine permissions.
6. Check dependency vulnerabilities/licensing against policy.
7. Confirm there are no unexplained source/code paths or establish an approved exception.

### Gate C — Data Collection/Egress

1. Finalize the class/method allowlist and required signals.
2. Enumerate exact collected fields, prohibited fields, sampling, and privacy classification.
3. Review debug/error/exception stack/correlation label branches.
4. Specify destination, TLS/auth, region, storage, retention, and authorized principals.
5. Test with **synthetic data**, combining log sources, network egress, disk writes, and collector payloads.
6. Ensure masking/dropping applies **before** steps that persist/send unauthorized raw fields.
7. Test the kill switch, remote config policy, rollback, and how residual data is deleted.

### Gate D — Rollout and Monitoring

1. Test on target JVM/application versions, avoiding JDK mismatches.
2. Canary rollout with small scope, measuring overhead, allocation, GC, class loading errors, and latency.
3. Compare egress/data fields against the baseline and approved config.
4. Record artifact digest, agent options, helper JAR digests, and policy version in the configuration system.
5. Monitor permission/destination/telemetry schema changes; reject unapproved releases.
6. Prepare rollback (often requiring a restart when installed bytecode cannot be guaranteed to be fully removed).
7. Review periodically because exporter configs, policies, endpoints, dependencies, and threat models change over time.

## 14. What Should an Audit Record Contain?

An audit entry can include:

| Field | Example record |
|---|---|
| Artifact | Name, version, verified release location |
| SHA-256 | **Actual digest** from final artifact, compared against reference source |
| Publisher/signer | Verified identity, certificate/trust policy |
| Build | Source commit, CI build run, build provenance digest |
| SBOM | SBOM version/digest and dependency review status |
| Manifest | `Premain-Class`, `Agent-Class`, `Boot-Class-Path`, `Can-*` |
| Runtime | JDK version, JVM flags, attach policy |
| Instrumentation allowlist | Permitted classes/methods/loaders/modules |
| Data fields | Permitted/prohibited list, purpose |
| Export | Hostname/region, TLS/auth, local spool |
| Retention | TTL, backup retention, deletion process |
| Test evidence | Static scan, jarsigner, egress, sampled payload, test result |
| Review decision | Reviewer, date, residual risks, conditions of use |
| Rollback | Removal procedure, post-removal check, owner |

Do not copy **secrets or sensitive raw payloads** into the audit record itself. The record proves policy and test results, not a place to duplicate data that needs protection.

Whenever the JAR, helper JAR, signer, collection config, endpoint, or privacy-affecting feature flag changes, re-evaluate the relevant parts and update the evidence.

## 15. Scenarios Requiring Rejection or Release Halt

**Scenario A — Digest is provided only by the JAR sender over the same unauthenticated channel.** There is no independent source of trust. Do not label `provenance verified` merely because the digest matches.

**Scenario B — The JAR has a signature, but a new `.class` file is unsigned.** Coverage and policy must be checked; do not accept based solely on the existence of a `.SF` file.

**Scenario C — The manifest has `Boot-Class-Path` pointing to a helper outside the approved release.** Both the helper JAR and its provenance/permissions must be inspected, not just the main agent JAR.

**Scenario D — The agent claims to measure only duration, but debug mode sends HTTP request bodies.** Data scope exceeds policy; do not release with the ability to enable this mode without controls and approval.

**Scenario E — The collector masks sensitive fields, but raw fields were already written to a local spool.** Redaction is placed too late; the pipeline must be changed to prevent capturing/sending raw data early.

**Scenario F — The agent is granted remote config capability without controlling who can enable argument capture.** A policy gate, RBAC/audit trail, and dynamic configuration checks are required.

**Scenario G — `Can-Retransform-Classes: true` even though the use case only needs load-time observation.** Not necessarily malicious, but increases requested capability without justification; requires explanation and appropriate restriction.

**Scenario H — Cannot determine where the agent sends data.** Do not infer "no egress." Code/dependency review + egress testing is required, or reject in sensitive environments.

**Scenario I — The JAR uses `Multi-Release: true`, but only the base version was reviewed.** Implementations that may be selected by the target runtime JDK must be inspected.

**Scenario J — The agent downloads code or config remotely after approval.** Source, integrity, permissions, and update state must be controlled; initial JAR approval does not automatically cover subsequently downloaded code.

## 16. Self-Check Exercises

**Question 1.** The SHA-256 hash of the downloaded file equals the hash on an unauthenticated page controlled by the sender itself. Has the publisher been verified?

**Answer:** No. The digest/release source and artifact provenance must be verified; a matching hash only confirms the bytes correspond to that digest.

**Question 2.** A validly signed JAR contains an exporter that automatically sends argument values. Can it be inferred that the agent complies with a "metadata-only" policy?

**Answer:** No. A signature does not prove behavior or data scope. Configuration and collection/egress paths must be reviewed.

**Question 3.** Does `Can-Retransform-Classes: false` prevent the agent from using network APIs?

**Answer:** No. The header only relates to the retransform capability; it does not restrict HTTP, file, or logging APIs.

**Question 4.** Does `return null` in `ClassFileTransformer.transform` mean the agent does not see the bytes?

**Answer:** No. The callback may have already received `classfileBuffer`; `return null` only leaves the byte definition unchanged for that transformation.

**Question 5.** Why must `Boot-Class-Path` be checked during supply chain review?

**Answer:** It can introduce additional helper JARs into the bootstrap search path, containing code not in the main JAR and having dependency/loader implications.

**Question 6.** `jarsigner` says `jar is unsigned` on the JAR created in the demo. Is this a signature PASS or FAIL?

**Answer:** There is no signature to verify. The demo can be used in a test environment we control; production must apply an approved verification policy, which may require signed artifacts.

**Question 7.** What helps prove that the "Authorization" data field is not stored before export?

**Answer:** Inspect source/config at the collection point, local logs/spools, queues, collector stages, and synthetic payloads; place drop/redaction before any place that persists or sends unauthorized raw fields.

**Question 8.** If the agent only prints `observed=demo.Work`, can it be concluded from stdout that it has no network side effects across all workloads?

**Answer:** No. Stdout from one test does not verify all background tasks or code branches. Static review and runtime egress monitoring must be combined.

**Question 9.** A JAR includes `META-INF/versions/21/...` while tests run on JDK 17. Should the versioned class be reviewed?

**Answer:** Yes if the artifact is intended for use on JDK 21 or newer; JDK 17 does not use that same implementation. Check against the deployment JVM matrix.

**Question 10.** Why does `JarInspector` reporting `unsafeEntryNames=0` not prove the JAR is safe?

**Answer:** It only has a small heuristic on entry names; it does not fully analyze ZIP/bytecode/behavior/trust/signatures/data egress.

**Question 11.** If collection is configured off, is `premain` still called?

**Answer:** Yes when `-javaagent` is run. The `off` mode in the demo still prints `[agent] collection=off`; not registering the transformer only limits that demo logic.

**Question 12.** Can `jarsigner -verify -strict` report a severe warning even when some entries are unsigned?

**Answer:** Yes. All entries, certificates/trust, warnings, and exit code must be examined per policy; not just a single summary line.

**Question 13.** Can data collected from an agent become sensitive if it consists only of class/method names?

**Answer:** Yes, it can. Class/method names, packages, and endpoint patterns can reveal internal architecture or business behavior, so purpose and allowlists are still required.

**Question 14.** When changing the exporter endpoint after deployment while the JAR stays unchanged, must the data scope be re-reviewed?

**Answer:** Yes. Destination/retention/access and where data is received are part of the data contract, not just the JAR code.

## 17. Summary

- Inspecting an agent requires three parallel tracks: **artifact provenance**, **JAR contents/capabilities**, and **actual data collected/processed/sent**.
- **SHA-256** requires a trusted reference digest; **JAR signatures** require checking coverage, signer, and trust; **provenance** must be verified rather than merely attached.
- Read `Premain-Class`, `Agent-Class`, `Can-*`, `Class-Path`, `Boot-Class-Path`, `Multi-Release`, resources, dependencies, and secondary execution paths **before running the agent**.
- A classfile transformer can **receive sensitive information** even when returning `null` and not transforming bytes. Separate "having read access" from "having stored/exported data."
- Apply **allowlists, data minimization, exporter controls, retention, and access controls**; review stdout, file spools, retry queues, and remote config as well.
- The Java 17+ example provides a **static JAR inspection tool**, and only then runs a self-created startup agent that captures an allowlisted class name without modifying bytecode.
- The output of a single command or a single test **is not enough** to conclude the entire agent is safe. Each release condition must be verified and clear evidence recorded.

## References

- Oracle JDK 17 — [`java.lang.instrument`: agent startup, dynamic loading, agent verification responsibility, and manifest attributes](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html).
- Oracle JDK 17 — [`Instrumentation` API and capabilities such as `retransformClasses`, `redefineModule`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html).
- Oracle JDK 17 — [`ClassFileTransformer` API and the `return null` contract](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html).
- Oracle JDK 17 — [JAR File Specification: manifest, signed JAR, multi-release JAR](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html).
- Oracle JDK 17 — [`jarsigner` manual: `-verify`, `-strict`, certificate checks, unsigned entries](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jarsigner.html).
- SLSA — [Build provenance specification and information to verify](https://slsa.dev/spec/v1.2/provenance).
- OWASP — [Logging Cheat Sheet: sensitive data and fields to avoid logging directly](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).
- OpenTelemetry — [Handling sensitive data: minimization, redaction, filtering](https://opentelemetry.io/docs/security/handling-sensitive-data/).
